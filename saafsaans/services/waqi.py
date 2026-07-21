"""Live AQI fetch from the WAQI feed API, with a demo-safe fallback.

``get_aqi`` never raises: on any failure — no token, station 404, timeout, bad
JSON, non-numeric AQI — it returns a reading whose every numeric field is None,
so nothing downstream can compute a severity from it. There is no stand-in
figure; see ``_fallback``. The WAQI status ("ok" / "fallback") is returned
*separately* from the reading so it is never written into the aqi-readings
index.
"""
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from . import aqi_scale, config, cpcb, es

# WAQI publishes hourly, and every render of every page asked it again: the
# fetch is blocking, sits on the request path, and the machine is one 256MB
# instance that scales to zero. Ten readers in the same minute meant ten round
# trips for a number that had not changed. One entry per locality, shared by
# every visitor to it.
#
# The indexing side matters as much. A reading was written to Elasticsearch on
# every render too, so aqi-readings grew with TRAFFIC rather than with
# OBSERVATIONS -- the same hourly figure stored hundreds of times, which is a
# false account of how often the city was measured and makes every aggregate
# over that index wrong. A cache hit indexes nothing, so the index now grows
# with what was actually observed.
_CACHE_TTL = 600            # a live reading; WAQI publishes hourly
_CACHE_TTL_FALLBACK = 60    # a failure, retried sooner
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(locality: str):
    """The cached ``(reading, status)`` for a locality, or None if stale."""
    with _CACHE_LOCK:
        hit = _CACHE.get(locality)
    if hit is None:
        return None
    stored_at, reading, status = hit
    # A RETAINED reading is served under status "ok" -- it carries real
    # numbers, and the page must not treat it as a no-reading turn -- but it
    # must not inherit the long TTL. ``cpcb._TTL_FAILURE`` is 60s precisely so
    # one timeout cannot blank a city for ten minutes; caching the held result
    # here for 600s made that fast retry invisible to the request path, so the
    # page went on saying the source was failing for ten minutes after it had
    # recovered. Freshness of the FETCH, not the status word, picks the TTL.
    fresh = status == "ok" and not (reading or {}).get("retained")
    ttl = _CACHE_TTL if fresh else _CACHE_TTL_FALLBACK
    if time.monotonic() - stored_at >= ttl:
        return None
    return reading, status


def _cache_put(locality: str, reading, status: str):
    with _CACHE_LOCK:
        _CACHE[locality] = (time.monotonic(), reading, status)


# One fetch per locality at a time. _CACHE_LOCK is held only long enough to
# read or write the dict -- it must NOT be held across the network call, or
# every locality would queue behind whichever one is talking to WAQI. But
# without a second lock, N readers arriving on a cold cache all miss, all
# fetch, and all index: the thundering herd, which is exactly the behaviour
# this cache exists to remove, surviving in the one case that matters (a
# machine waking from scale-to-zero with several people waiting).
_FETCH_LOCKS = {}


def _fetch_lock(locality: str):
    with _CACHE_LOCK:
        return _FETCH_LOCKS.setdefault(locality, threading.Lock())


def cache_clear():
    """Drop every cached reading. For tests, and for the seeding scripts.

    Clears the CPCB city cache too. They are separate caches -- one keyed by
    locality, one by city -- and a test that cleared only this one would still
    be served yesterday's CPCB payload.
    """
    with _CACHE_LOCK:
        _CACHE.clear()
        _FETCH_LOCKS.clear()
    cpcb.cache_clear()


TIMEOUT = 5

# UI locality -> WAQI feed slug, or None where WAQI has no station for that
# locality at all. Two path forms exist: ``<city>/<station>`` by name and
# ``@<uid>`` by numeric station id. The named form silently resolves to an
# unrelated station for some slugs -- the ``noida`` slug returned the Anand
# Vihar, Delhi station byte-for-byte -- so every station whose named slug was
# wrong or missing is pinned by uid instead, which cannot drift onto another
# station. Each entry below was fetched and its data.city.name checked against
# the locality it is mapped to.
#
# No slug here is trusted on its own: get_aqi re-checks the returned station
# name against the locality on every fetch (see _corroborates), so a feed that
# starts answering for somewhere else yields no reading at all, rather than
# being shown as this locality's air.
FEED_MAP = {
    # --- Delhi stations ---
    "Anand Vihar": "delhi/anand-vihar",
    "ITO": "delhi/ito",
    "Rohini": "@10117",             # Shaheed Sukhdev College, Rohini
    "RK Puram": "delhi/r.k.-puram",
    "Punjabi Bagh": "delhi/punjabi-bagh",
    "Mandir Marg": "delhi/mandir-marg",
    "Dwarka": "@10119",             # NIMR, Sector 8, Dwarka
    "Najafgarh": "@10120",          # Bramprakash Ayurvedic Hospital, Najafgarh
    "Wazirpur": "@10114",           # Delhi Institute of Tool Engineering
    "Jahangirpuri": "@10113",       # ITI Jahangirpuri
    "Okhla": "@10116",              # DITE Okhla
    # WAQI carries no station for these two. Mapping them to anything else
    # would be showing another neighbourhood's air under their name, so they
    # get no feed and render as NO READING unless we hold a stored one.
    "Ashok Vihar": None,
    "Nehru Nagar": None,
    "Patparganj": "@10704",         # Mother Dairy Plant, Parparganj
    "DTU": "delhi/dtu",
    "Delhi (city)": "delhi",
    # --- NCR cities ---
    "Noida": "@11865",              # Sector - 62, Noida
    "Greater Noida": "greater-noida",
    "Gurugram": "@12816",           # Sector-51, Gurugram
    "Ghaziabad": "ghaziabad",
    "Faridabad": "@12813",          # Sector 11, Faridabad
}
CITY_FEED = "delhi"

# How old a feed's own observation time may be before the reading stops being
# treated as live. The stations report hourly, but WAQI's mirror of them lags:
# on 2026-07-20 the laggiest healthy Delhi station was five hours behind the
# clock, so the 3-hour window main.py uses for stored readings would have
# discarded stations that were working. No window at all let the ``delhi/ito``
# feed serve a four-week-old reading with status "ok". Twelve hours accepts the
# lag actually observed while still refusing that. It does not guarantee a
# reading from the current calendar day, and is not meant to.
MAX_OBS_AGE = timedelta(hours=12)

# Locality label -> the spelling that actually appears in the feed's station
# name, for the few where they differ. Kept deliberately tiny: a locality
# missing from here just has to match on its own name, and the failure mode of
# a missing alias is a false mismatch, which shows no reading. The
# opposite error -- accepting the wrong station -- is the one that would put a
# false claim on screen, and no entry here can cause it.
FEED_NAME_ALIASES = {
    "Patparganj": "Parparganj",   # the feed spells it with an r
    "Delhi (city)": "Delhi",      # the city feed answers from a Delhi station
}

# Region grouping for the UI (picker + City Pulse grid subheaders). The last
# entry of each list is kept in the same order as FEED_MAP.
REGIONS = {
    "Delhi": ["Anand Vihar", "ITO", "Rohini", "RK Puram", "Punjabi Bagh",
              "Mandir Marg", "Dwarka", "Najafgarh", "Wazirpur", "Jahangirpuri",
              "Okhla", "Ashok Vihar", "Nehru Nagar", "Patparganj", "DTU",
              "Delhi (city)"],
    "NCR": ["Noida", "Greater Noida", "Gurugram", "Ghaziabad", "Faridabad"],
}
LOCALITIES = REGIONS["Delhi"] + REGIONS["NCR"]

# There is deliberately NO table of stand-in concentrations here any more.
#
# There used to be one: 21 hand-written winter PM2.5/PM10 pairs, served
# whenever the feed did not answer. Because the AQI was derived from them
# through the real CPCB scale, an invented number arrived on screen wearing the
# same clothes as a measurement -- ITO's 250/410 became "AQI 400 - VERY POOR"
# and the verdict "Don't go out unless you must - this air is dangerous for
# you." in July, off a figure nobody measured anywhere. Two localities
# (Ashok Vihar, Nehru Nagar) have no WAQI station at all, so for them that was
# not a rare failure mode: it was every render, forever.
#
# The table is gone rather than merely disconnected, because a disconnected
# table is a loaded gun left on the table for the next change to pick up. What
# is not in the file cannot come back by accident, and the test that used to
# require every locality to have a sample now requires the opposite.

_API = "https://api.waqi.info/feed/{feed}/?token={token}"


def _reading(pm25, pm10, *, station, city, stale, forecast, obs_time,
             feed_aqi=None, feed_dominant=None, retained=False, source=None):
    """Assemble the reading contract from two particulate concentrations.

    One constructor for both the live and the fallback path, so the two cannot
    describe the same fields differently -- which is how the previous version
    ended up with hand-written sample AQIs that no longer matched the scale
    they were supposedly on.

    ``aqi`` is deliberately ``None`` when neither particulate is usable. The
    obvious alternative -- falling back to ``feed_aqi`` -- would put a US EPA
    number under Indian band names, which is the defect this whole change
    exists to remove.
    """
    scored = aqi_scale.cpcb_aqi(pm25, pm10)
    aqi, dominant, beyond = scored if scored else (None, None, False)
    return {
        "aqi": aqi,
        "aqi_beyond_scale": beyond,
        "pm25": pm25,
        "pm10": pm10,
        "dominant_pollutant": dominant,
        # WAQI's own number, on its own scale, kept for the provenance panel so
        # a sceptical reader can see both figures and that they differ.
        "feed_aqi": feed_aqi,
        "feed_dominant": feed_dominant,
        "station": station,
        "city": city,
        "stale": stale,
        # NOT the same field as ``stale``, and deliberately not folded into it.
        # ``stale`` is true on exactly one path -- ``_fallback``, which returns
        # no numbers at all -- and ``llm.py`` appends "we have no reading for
        # this area" to it. A retained reading has real numbers; what it lacks
        # is a fresh fetch behind them. Folding the two would print "we have no
        # reading for this area" beside a number.
        "retained": retained,
        # Which upstream this reading actually came from: "cpcb", "waqi", or
        # None when there is no reading. The provenance panel has to name it,
        # and it cannot be inferred from the other fields -- feed_aqi is None
        # on a CPCB reading AND on a WAQI station whose own headline was "-".
        # Deliberately NOT in es.READING_FIELDS: a reading rebuilt from the
        # index therefore has source None and claims neither, which is correct
        # and is its own test.
        "source": source,
        "forecast": forecast,
        "obs_time": obs_time,
    }


def _fallback(locality: str = None):
    """The reading returned when there is no live measurement: no numbers.

    Every field a severity claim could be computed from is None. That is the
    whole point. ``aqi=None`` routes the page into the Unknown path, which is
    already correct and already tested: no band word, no CPCB verdict, no
    band advice, no WHO multiple, no go-outside window, and no advisory
    retrieval keyed on a band that was never measured.

    Suppressing the number is not the same as saying nothing. What the reader
    is owed instead -- this station's last REAL reading and how old it is --
    comes from the aqi-readings index, which is what the app actually observed,
    and is attached by the caller (see ``main._last_real_reading``). It is not
    attached here because this value is cached, and a cached "last reported
    23 June" would itself go stale.
    """
    return _reading(
        None, None,
        station=locality or "Delhi",
        city="Delhi", stale=True, forecast=None, obs_time=None)


def _normalise(name: str) -> str:
    """Lowercase a place name down to its letters and digits.

    Station names carry punctuation the UI labels do not ("R.K. Puram" vs
    "RK Puram"), so both sides are reduced before comparison.
    """
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _corroborates(locality: str, city_name: str) -> bool:
    """True when the feed's own station name backs up the locality label.

    This is the check that catches a slug quietly resolving to a different
    station: the feed says who it is, so nothing has to be taken on trust from
    the mapping table above.
    """
    expected = _normalise(FEED_NAME_ALIASES.get(locality, locality))
    return bool(expected) and expected in _normalise(city_name)


def _obs_too_old(obs_time) -> bool:
    """True only when the feed states an observation time and it is too old.

    A feed that omits the timestamp, or states one that cannot be parsed, is
    NOT called stale -- there is no evidence either way, and dropping those
    would silently delete every reading from a feed that simply does not
    publish a time.
    """
    if not obs_time:
        return False
    try:
        dt = datetime.fromisoformat(str(obs_time).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) > MAX_OBS_AGE


def _fetch_feed(feed: str, token: str):
    """GET one feed. Returns parsed reading dict or None (not usable)."""
    resp = requests.get(_API.format(feed=feed, token=token), timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    payload = resp.json()  # may raise ValueError -> handled by caller
    if payload.get("status") != "ok":
        return None
    data = payload.get("data") or {}
    aqi_raw = data.get("aqi")
    try:
        feed_aqi = int(aqi_raw)  # "-" or None from an offline station
    except (TypeError, ValueError):
        # An offline station used to make the whole reading unusable. It no
        # longer has to: the app computes its own index from the particulates,
        # so a feed that still carries pm25/pm10 is fine without a headline aqi.
        feed_aqi = None
    iaqi = data.get("iaqi") or {}

    def pollutant(name):
        node = iaqi.get(name)
        if isinstance(node, dict) and "v" in node:
            try:
                return float(node["v"])
            except (TypeError, ValueError):
                return None
        return None

    city = (data.get("city") or {}).get("name") or "Delhi"
    # Additive: WAQI also returns a multi-day pollutant forecast and an
    # observation timestamp. Captured here for the forecast module; both are
    # optional and default to None when absent so the reading shape is stable.
    forecast = data.get("forecast")
    if not isinstance(forecast, dict):
        forecast = None
    obs_time = (data.get("time") or {}).get("iso")
    # An observation from weeks ago is not a live reading, whatever the feed's
    # status field says. Treated as unusable here so it can never reach the UI
    # with status "ok"; the locality falls back to no reading instead.
    if _obs_too_old(obs_time):
        return None

    # The feed's iaqi values are AQI sub-indices on the US EPA scale, not
    # concentrations -- see services/aqi_scale.py for the proof. Invert them
    # before anything downstream treats them as micrograms.
    reading = _reading(
        aqi_scale.concentration(pollutant("pm25"), "pm25"),
        aqi_scale.concentration(pollutant("pm10"), "pm10"),
        station=city, city=city, stale=False, forecast=forecast,
        obs_time=obs_time, feed_aqi=feed_aqi,
        feed_dominant=data.get("dominentpol"), source="waqi")
    # No usable particulate and no feed number either: nothing to show.
    if reading["aqi"] is None and feed_aqi is None:
        return None
    return reading


def get_aqi(locality: str, es_client=None):
    """Return ``(reading, status)`` where status is "ok" or "fallback".

    On a successful live fetch the reading is also indexed into aqi-readings
    when ``es_client`` is connected.
    """
    cached = _cache_get(locality)
    if cached is not None:
        return cached

    with _fetch_lock(locality):
        # Re-probe: while this thread waited for the lock, the thread that held
        # it may have filled the cache. Without this the queue behind a slow
        # fetch still produces one fetch each as they file through.
        cached = _cache_get(locality)
        if cached is not None:
            return cached
        return _fetch_uncached(locality, es_client)


def _fetch_cpcb(locality: str):
    """A reading built from CPCB's own concentrations, or None.

    CPCB is asked first because it is the upstream WAQI republishes. The dated
    coverage counts that stood here have been removed: they were a live
    measurement nobody can re-take, and an unsupportable claim goes rather than
    gets renumbered. ``cpcb``'s module docstring states the structural bound
    that IS checkable instead.

    ``cpcb.values_for`` returns micrograms, so they are passed to ``_reading``
    unconverted. They must NEVER go through ``aqi_scale.concentration``, which
    exists to invert WAQI's US-EPA sub-indices -- running a concentration
    through it would inflate every number in the app. That is the one way this
    function can be wrong without anything looking wrong.
    """
    try:
        values = cpcb.values_for(locality)
    except Exception:
        return None
    if not values:
        return None
    if _obs_too_old(values["obs_time"]):
        return None
    reading = _reading(
        values["pm25"], values["pm10"],
        station=values["station"], city=values["city"],
        stale=False, forecast=None, obs_time=values["obs_time"],
        retained=values.get("retained", False), source="cpcb")
    # No usable particulate means no CPCB AQI. Returning the shell would stop
    # the WAQI fallback being tried, which is the whole point of having one.
    return reading if reading["aqi"] is not None else None


# Whether a CPCB reading built from ONE particulate should make us look at
# WAQI before serving it.
#
# Shipped False, which is today's behaviour: a CPCB reading that produced an
# index wins outright and WAQI is consulted only when CPCB produced none.
#
# It is False and not True because docs/decisions/0005-averaging-window.md
# concludes, by measurement, that the two sources do not publish the same
# quantity: CPCB's avg_value is a rolling 24-hour mean and WAQI's iaqi is a
# sub-index of the latest hourly concentration. Preferring WAQI's pair over
# CPCB's single particulate would therefore swap the quantity the CPCB scale
# is defined on for one it is not, to gain a second pollutant. That trade has
# not been argued, so it is not made.
#
# The consequence is stated plainly rather than buried: a station like
# Wazirpur, whose CPCB PM2.5 instrument is down, still publishes an index from
# PM10 alone and still understates the air. This flag does not fix that. What
# fixes the DISHONESTY is the caption saying which particulates were actually
# measured; what would fix the UNDERSTATEMENT is a decision this run does not
# have the evidence to make.
PREFER_TWO_PARTICULATES = False


def _choose(cpcb_reading, waqi_reading):
    """Pick ONE reading. Never merge them.

    The two candidates are never combined field by field -- no taking CPCB's
    PM10 beside WAQI's PM2.5, no borrowing one number to fill a gap in the
    other. ``docs/decisions/0005-averaging-window.md`` establishes by
    measurement that they publish different quantities (a rolling 24-hour mean
    against the latest hourly value), so a merged reading would be an average
    of two things that are not the same thing, wearing one timestamp and one
    station name. Every field of what is returned came from one source.
    """
    if cpcb_reading is None:
        return waqi_reading
    # A HELD CPCB payload is not a CPCB answer. ``cpcb`` failed; what is on
    # offer is the last good fetch being re-served. Retention exists to beat
    # NO READING, not to beat the fallback -- before it was added, a CPCB
    # transport failure made ``values_for`` return None and WAQI was tried, so
    # keeping the held payload here would have quietly replaced "fall back to
    # the live source" with "serve the stale primary". Measured: Wazirpur held
    # a PM10-only index of 119 while WAQI was publishing 280 for the same
    # station, and WAQI was never called.
    #
    # This is a different axis from PREFER_TWO_PARTICULATES below, which weighs
    # a FRESH CPCB reading against WAQI and declines to swap one quantity for
    # another to gain a pollutant. Here CPCB has produced nothing new at all,
    # so there is no fresh 24-hour mean to protect: the choice is between a
    # live measurement and an old one, and live wins. Still never merged --
    # whichever is returned is returned whole.
    if cpcb_reading["retained"]:
        return waqi_reading if waqi_reading is not None else cpcb_reading
    if not _wants_second_opinion(cpcb_reading):
        return cpcb_reading
    # One particulate at CPCB, both at WAQI: take WAQI's reading WHOLE.
    if (waqi_reading is not None
            and waqi_reading["pm25"] is not None
            and waqi_reading["pm10"] is not None):
        return waqi_reading
    # WAQI had no token, no station, did not answer, answered for somewhere
    # else, or is no better off. Keep what CPCB measured -- losing a real
    # partial reading would be a worse defect than the one being fixed.
    return cpcb_reading


def _wants_second_opinion(cpcb_reading) -> bool:
    """True when CPCB produced an index from a single particulate AND policy
    says to look at the fallback before serving it."""
    return (PREFER_TWO_PARTICULATES
            and (cpcb_reading["pm25"] is None or cpcb_reading["pm10"] is None))


def _serve(locality: str, reading, es_client):
    """Index (when there is something new to index) and cache the winner."""
    # A retained reading is an observation we already indexed when it was
    # fresh. Indexing it again on every 600s cache miss is precisely the
    # "index grows with traffic rather than observations" defect recorded at
    # the top of this file as fixed.
    if not reading.get("retained"):
        try:
            # Index under the canonical UI locality label (not WAQI's verbose
            # city.name) so live readings share one key space with seed data
            # and the aqi_trend/station_grid filters match. Display keeps the
            # real name.
            es.index_reading(es_client, {**reading, "station": locality})
        except Exception:
            pass  # indexing must never affect the returned reading
    # Stored AFTER indexing, so the one render that actually fetched is also
    # the one render that writes. Every reader served from the cache adds
    # nothing to aqi-readings.
    _cache_put(locality, reading, "ok")
    return reading, "ok"


def _fetch_uncached(locality: str, es_client):
    """The cache miss path. Caller must hold this locality's fetch lock."""
    cpcb_reading = _fetch_cpcb(locality)
    # Short-circuit only on a FRESH CPCB answer. A retained one falls through
    # to the WAQI fetch below so ``_choose`` has a live candidate to prefer;
    # returning here would leave that preference unreachable.
    if (cpcb_reading is not None
            and not cpcb_reading["retained"]
            and not _wants_second_opinion(cpcb_reading)):
        return _serve(locality, cpcb_reading, es_client)

    token = config.waqi_token()
    feed = FEED_MAP.get(locality, CITY_FEED)
    attempted = bool(token and feed)

    waqi_reading = None
    if attempted:
        try:
            waqi_reading = _fetch_feed(feed, token)
        except Exception:
            waqi_reading = None
        # A feed that answers for somewhere else is not this locality's air.
        # The previous version had no such check and presented the Anand
        # Vihar, Delhi station as Noida's reading. There is also no city-feed
        # retry any more: borrowing another station whenever one 404s is the
        # same mislabelling by a slower route, and this check would reject its
        # result anyway.
        if waqi_reading is not None and not _corroborates(locality,
                                                          waqi_reading["city"]):
            waqi_reading = None

    winner = _choose(cpcb_reading, waqi_reading)
    if winner is None:
        result = (_fallback(locality), "fallback")
        if attempted:
            # Cached on the shorter TTL: a station that is down stays down for
            # a while, and hammering it once per render is how a slow upstream
            # becomes a slow site. Not cached when nothing was even asked --
            # there is no upstream state to remember.
            _cache_put(locality, *result)
        return result
    return _serve(locality, winner, es_client)


if __name__ == "__main__":
    r, status = get_aqi("Delhi (city)")
    print(f"[{status}] Delhi AQI = {r['aqi']} "
          f"(PM2.5={r['pm25']}, dominant={r['dominant_pollutant']}, stale={r['stale']})")
