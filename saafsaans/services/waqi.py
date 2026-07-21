"""Live AQI fetch from the WAQI feed API, with a demo-safe fallback.

``get_aqi`` never raises and (in practice) always returns a reading: on any
failure — no token, station 404, timeout, bad JSON, non-numeric AQI — it
returns a clearly-labelled cached sample so the demo cannot die. The WAQI
status ("ok" / "fallback") is returned *separately* from the reading so it is
never written into the aqi-readings index.
"""
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from . import aqi_scale, config, es

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
    ttl = _CACHE_TTL if status == "ok" else _CACHE_TTL_FALLBACK
    if time.monotonic() - stored_at >= ttl:
        return None
    return reading, status


def _cache_put(locality: str, reading, status: str):
    with _CACHE_LOCK:
        _CACHE[locality] = (time.monotonic(), reading, status)


def cache_clear():
    """Drop every cached reading. For tests, and for the seeding scripts."""
    with _CACHE_LOCK:
        _CACHE.clear()


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
# starts answering for somewhere else degrades to a labelled sample rather than
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
    # get no feed and always render as the labelled cached sample.
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
# a missing alias is a false mismatch, which shows a labelled sample. The
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

# Labelled per-locality fallback samples used whenever live data is unavailable
# (no token, or a failed fetch). Distinct values per locality so the UI visibly
# reacts to the picker even in mock mode; a few carry a non-PM dominant
# pollutant so the best-time-window advice also varies. All are stale=True.
#
# These are CONCENTRATIONS in micrograms per cubic metre, and always were --
# pm10 exceeds pm25 in every row, which is what makes them physically coherent
# and is exactly what the live feed's sub-indices were not. The AQI is derived
# from them through the CPCB scale rather than stored, so a sample can never
# drift away from the scale it is supposed to sit on.
SAMPLES = {
    "Anand Vihar": {"pm25": 380.0, "pm10": 520.0},
    "ITO": {"pm25": 250.0, "pm10": 410.0, "dom": "no2"},
    "Rohini": {"pm25": 110.0, "pm10": 210.0},
    "RK Puram": {"pm25": 190.0, "pm10": 330.0},
    "Punjabi Bagh": {"pm25": 220.0, "pm10": 360.0},
    "Mandir Marg": {"pm25": 150.0, "pm10": 260.0},
    "Dwarka": {"pm25": 175.0, "pm10": 300.0},
    "Najafgarh": {"pm25": 130.0, "pm10": 240.0},
    "Wazirpur": {"pm25": 300.0, "pm10": 460.0},
    "Jahangirpuri": {"pm25": 350.0, "pm10": 500.0},
    "Okhla": {"pm25": 200.0, "pm10": 340.0},
    "Ashok Vihar": {"pm25": 260.0, "pm10": 420.0},
    "Nehru Nagar": {"pm25": 270.0, "pm10": 430.0},
    "Patparganj": {"pm25": 185.0, "pm10": 320.0},
    "DTU": {"pm25": 140.0, "pm10": 250.0},
    "Delhi (city)": {"pm25": 210.0, "pm10": 320.0},
    "Noida": {"pm25": 165.0, "pm10": 290.0, "dom": "no2"},
    "Greater Noida": {"pm25": 180.0, "pm10": 310.0},
    "Gurugram": {"pm25": 120.0, "pm10": 220.0, "dom": "o3"},
    "Ghaziabad": {"pm25": 230.0, "pm10": 380.0},
    "Faridabad": {"pm25": 195.0, "pm10": 335.0},
}
_DEFAULT_SAMPLE = SAMPLES["Delhi (city)"]


_API = "https://api.waqi.info/feed/{feed}/?token={token}"


def _reading(pm25, pm10, *, station, city, stale, forecast, obs_time,
             feed_aqi=None, feed_dominant=None):
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
        "forecast": forecast,
        "obs_time": obs_time,
    }


def _fallback(locality: str = None):
    base = SAMPLES.get(locality, _DEFAULT_SAMPLE)
    return _reading(
        base["pm25"], base["pm10"],
        station=f"{locality or 'Delhi'} (cached sample)",
        city="Delhi", stale=True, forecast=None, obs_time=None,
        feed_dominant=base.get("dom"))


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
    # with status "ok"; the locality degrades to its labelled sample instead.
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
        feed_dominant=data.get("dominentpol"))
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

    token = config.waqi_token()
    if not token:
        return _fallback(locality), "fallback"

    feed = FEED_MAP.get(locality, CITY_FEED)
    if not feed:
        return _fallback(locality), "fallback"

    reading = None
    try:
        reading = _fetch_feed(feed, token)
    except Exception:
        reading = None

    if reading is None:
        # Cached too, on a shorter TTL: a station that is down stays down for
        # a while, and hammering it once per render is how a slow upstream
        # becomes a slow site.
        result = (_fallback(locality), "fallback")
        _cache_put(locality, *result)
        return result

    # A feed that answers for somewhere else is not this locality's air. The
    # previous version had no such check and presented the Anand Vihar, Delhi
    # station as Noida's reading. There is also no city-feed retry any more:
    # borrowing another station whenever one 404s is the same mislabelling by
    # a slower route, and this check would reject its result anyway.
    if not _corroborates(locality, reading["city"]):
        result = (_fallback(locality), "fallback")
        _cache_put(locality, *result)
        return result

    try:
        # Index under the canonical UI locality label (not WAQI's verbose
        # city.name) so live readings share one key space with seed data and
        # the aqi_trend/station_grid filters match. Display keeps the real name.
        es.index_reading(es_client, {**reading, "station": locality})
    except Exception:
        pass  # indexing must never affect the returned reading
    # Stored AFTER indexing, so the one render that actually fetched is also
    # the one render that writes. Every reader served from the cache adds
    # nothing to aqi-readings.
    _cache_put(locality, reading, "ok")
    return reading, "ok"


if __name__ == "__main__":
    r, status = get_aqi("Delhi (city)")
    print(f"[{status}] Delhi AQI = {r['aqi']} "
          f"(PM2.5={r['pm25']}, dominant={r['dominant_pollutant']}, stale={r['stale']})")
