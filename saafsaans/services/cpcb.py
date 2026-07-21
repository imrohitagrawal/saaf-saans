"""CPCB readings from data.gov.in -- the upstream WAQI mirrors.

Why this source, and why it goes first
--------------------------------------
WAQI republishes Indian government monitoring data. Reading CPCB directly
removes a hop, and the hop was costing real coverage: on 21 July 2026 WAQI
answered for 12 of the 21 localities this app offers, while CPCB answered for
20 of them in the same minute. ITO in particular had been stale in WAQI's
mirror since 23 June -- long enough that the app served a fabricated stand-in
in its place -- while CPCB was publishing it hourly throughout.

WAQI is kept as the fallback rather than removed. It covered Wazirpur on the
day this was written, when CPCB's PM2.5 instrument there was down, so the two
sources genuinely cover for each other. Neither is trusted alone.

The unit trap
-------------
**CPCB's ``avg_value`` is a concentration in ug/m3. WAQI's ``iaqi`` values are
AQI sub-indices on the US EPA scale.** They look identical -- small integers
against a pollutant name -- and they are not the same quantity. ``waqi.py``
inverts its values through ``aqi_scale.concentration`` before anything treats
them as micrograms; CPCB values must NOT go through that inversion, or every
reading in the app is silently inflated. This module therefore returns
concentrations only, and lets ``waqi._reading`` build the reading contract, so
there is still exactly one constructor for the shape.

Shape of the upstream
---------------------
One record per pollutant per station, so rows must be grouped by station::

    {"station": "ITO, Delhi - CPCB", "pollutant_id": "PM2.5",
     "avg_value": "53", "last_update": "21-07-2026 19:00:00"}

Three properties of the feed that are load-bearing here, all measured rather
than assumed:

* ``avg_value`` is the string ``"NA"`` when an instrument is down -- 26 of 315
  Delhi rows on the day this was written. Parsing it as a number raises;
  defaulting it to zero invents a reading, which is the defect this app has
  spent two runs removing. Both are refused: ``None`` means no value.
* ``last_update`` is ``DD-MM-YYYY HH:MM:SS`` in IST, not ISO and not UTC.
* ``limit=1000`` times out; ``limit=300`` answers. Delhi has 315 rows, so the
  city needs paging.

One fetch serves every locality in a city, which is why this module caches by
city rather than by locality: rendering City Pulse used to mean one upstream
call per station.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from saafsaans.services import config

# "Real time Air Quality Index from various locations", Central Pollution
# Control Board / Ministry of Environment, Forest and Climate Change, published
# on data.gov.in under the Government Open Data License - India.
RESOURCE = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
ENDPOINT = "https://api.data.gov.in/resource/"

# What the reader is told this source is called, in one place, so the Guide,
# the provenance panel and the tests cite the same fact instead of three
# hand-written spellings. SOURCE_HOST is the site a reader can actually open,
# not the API subdomain ENDPOINT points at; a test asserts it stays a suffix of
# that hostname, so changing the endpoint moves the prose.
SOURCE_NAME = "CPCB"
SOURCE_HOST = "data.gov.in"

# Measured: 1000 times out, 300 answers. Delhi returns 315 rows, so paging is
# not optional -- a single limit=300 call silently drops ITO's PM2.5, which is
# how this integration was nearly designed around a gap that did not exist.
PAGE = 300
MAX_PAGES = 4
# This fetch sits on the request path of a 256MB machine that scales to zero,
# so the timeout is a page-load budget, not a patience setting. api.data.gov.in
# is measurably flaky -- an SSL handshake timed out after 20s and the next two
# attempts answered in 0.5s -- and the first version of this module made a
# reader wait the full 20s for that. DEADLINE bounds the whole paged fetch, so
# a slow first page cannot be followed by three more.
TIMEOUT = 8
DEADLINE = 15

# Which upstream city query answers for a locality. The five NCR cities are
# their own queries; everything else rides on the Delhi one.
CITY_OF = {
    "Noida": "Noida", "Greater Noida": "Greater Noida", "Gurugram": "Gurugram",
    "Ghaziabad": "Ghaziabad", "Faridabad": "Faridabad",
}
DEFAULT_CITY = "Delhi"

# The app's label -> the CPCB station name, where reducing both to letters and
# digits is not enough to match them. Matched against the part before the first
# comma, so "Sector - 62, Noida - IITM" is keyed by "Sector - 62". Every entry
# was checked against the live feed.
STATION_ALIAS = {
    "Dwarka": "NSIT Dwarka",
    "Okhla": "Okhla Phase-2",
    "RK Puram": "R K Puram",
    # The NCR entries name a city, and CPCB has several stations in each. These
    # three point at the SAME station FEED_MAP already pinned for WAQI -- the
    # choice was made there and is only being mirrored, not invented. The
    # station's own name is what the page displays, so the reader is never told
    # a sector reading is a city-wide one.
    #
    # Greater Noida and Ghaziabad are deliberately absent. FEED_MAP gives them a
    # bare city slug rather than a station, so there is no existing choice to
    # mirror, and picking one of Ghaziabad's five would be this file inventing a
    # decision about whose air represents the city. They stay on WAQI, and show
    # NO READING when it has nothing.
    "Noida": "Sector - 62",         # FEED_MAP @11865
    "Gurugram": "Sector-51",        # FEED_MAP @12816
    "Faridabad": "Sector 11",       # FEED_MAP @12813
}

# "Delhi (city)" is an aggregate the app computes, not a station anyone
# operates, so it has no CPCB row and must not be looked up as one.
NOT_A_STATION = {"Delhi (city)"}

# A success is good for as long as the upstream publishes (hourly). A FAILURE
# is retried far sooner: one timeout used to blank a whole city for ten
# minutes, which was observed live -- Gurugram fell back to NO READING while
# its four stations were reporting normally. Mirrors waqi's split TTLs, and for
# the same reason.
_TTL = 600
_TTL_FAILURE = 60
# How long the last GOOD payload may be re-served through an upstream failure.
# Bounded from the last successful fetch, never from the failure, so a source
# that stays down ages out instead of pinning yesterday's air on the page.
# Three hours matches the age at which City Pulse already calls a reading held
# rather than current, and MAX_OBS_AGE (12h) is still the outer bound because
# the retained payload keeps its own obs_time.
_TTL_RETAIN = 3 * 3600
_cache: dict = {}
# Deliberately a SECOND dict rather than a third element in _cache's tuple:
# _cache's 2-tuple shape is asserted directly by tests, and the two have
# different lifetimes -- _cache holds failures, this holds only successes.
_last_good: dict = {}
_lock = threading.Lock()

# One upstream fetch per city at a time. ``waqi._FETCH_LOCKS`` cannot collapse
# this herd: those locks are keyed by LOCALITY while this cache is keyed by
# CITY, so eight different Delhi localities hold eight different waqi locks and
# all eight miss the same empty "Delhi" entry. Measured: ``main._live_grid``
# submits 21 localities to an 8-worker pool, and a cold /city render made eight
# Delhi fetches of up to four HTTP requests each.
#
# The accepted tradeoff, stated because it is a change and not a free win:
# seven of the eight workers now WAIT on a cold Delhi miss, bounded by DEADLINE
# (15s), while ``main._CITY_FETCH_BUDGET`` is 6.0s. Stragglers are abandoned by
# that budget and render NO READING or CACHED rather than a number. That is
# strictly better than eight independent 15s fetches, but it moves WHICH
# localities land inside the budget on a cold render.
_FETCH_LOCKS: dict = {}


def _fetch_lock(city: str):
    with _lock:
        return _FETCH_LOCKS.setdefault(city, threading.Lock())


def available() -> bool:
    return bool(config.cpcb_key())


def _normalise(name: str) -> str:
    """Letters and digits only, lowercased.

    Mirrors ``waqi._normalise``: the upstream writes "R K Puram" where the UI
    writes "RK Puram", and "ITO, Delhi - CPCB" where the UI writes "ITO".
    """
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _value(raw):
    """A concentration in ug/m3, or None.

    ``"NA"`` is what the feed publishes when an instrument is down. It is not
    zero and it is not a reading; the only honest answer is that there is no
    value. Anything unparseable is treated the same way.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.upper() == "NA":
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    # A negative concentration is an instrument fault, not clean air.
    return value if value >= 0 else None


def _obs_time(raw):
    """``"21-07-2026 19:00:00"`` (IST) as an ISO-8601 string, or None.

    The feed states neither a timezone nor an ISO layout. Parsing it as ISO
    yields a wrong date rather than an error -- "21-07-2026" would read as year
    21 -- so the format is stated explicitly and the +05:30 offset attached,
    because everything downstream compares against UTC.
    """
    if not raw:
        return None
    try:
        naive = datetime.strptime(str(raw).strip(), "%d-%m-%Y %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return naive.replace(tzinfo=timezone(timedelta(hours=5, minutes=30))).isoformat()


def _fetch_city(city: str):
    """Every record for one city, paged. Raises on transport failure."""
    records = []
    started = time.monotonic()
    for page in range(MAX_PAGES):
        if page and time.monotonic() - started > DEADLINE:
            break
        query = urllib.parse.urlencode({
            "api-key": config.cpcb_key(), "format": "json",
            "limit": PAGE, "offset": page * PAGE, "filters[city]": city,
        })
        request = urllib.request.Request(
            f"{ENDPOINT}{RESOURCE}?{query}",
            headers={"User-Agent": "SaafSaans/1.0"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = json.load(response)
        batch = payload.get("records") or []
        records.extend(batch)
        if len(batch) < PAGE:
            break
    return records


def _stations(city: str):
    """``({station name: {...}}, retained)`` for a city.

    Cached per city and not per locality: one upstream call answers for every
    station in it, and City Pulse asks for twenty-one in a row.

    ``retained`` is True when the payload is the last good one being held
    through an upstream failure rather than a fresh answer. The caller has to
    say so on screen; serving a held reading as a live one would be the same
    class of defect as the stand-in figures this app spent two runs deleting.
    """
    hit = _cached(city)
    if hit:
        return hit, False

    with _fetch_lock(city):
        # Re-probe inside the lock: while this thread queued, the thread that
        # held it has already filled the cache. Without this re-probe the queue
        # still produces one upstream fetch each as it files through, which is
        # the herd arriving late rather than not at all.
        hit = _cached(city)
        if hit:
            return hit, False
        if hit is not None:
            # The empty FAILURE MARKER, still inside its short TTL. It is a
            # cache hit and it is falsy, so returning it here would blank the
            # city for the whole failure window -- exactly the bug retention
            # exists to fix, surviving in the second render onwards. Fall
            # through to the retained payload instead.
            return _retained(city)
        return _fetch_and_store(city)


def _cached(city: str):
    """The cached grouping for a city, or None when there is nothing fresh.

    ``{}`` and ``None`` are different answers: ``{}`` is a live failure marker
    inside its TTL, ``None`` is nothing usable in the cache at all.
    """
    with _lock:
        hit = _cache.get(city)
    if not hit:
        return None
    stored_at, grouped = hit
    ttl = _TTL if grouped else _TTL_FAILURE
    return grouped if time.time() - stored_at < ttl else None


def _retained(city: str):
    """``(payload, True)`` when the last good fetch is still within bounds.

    The bound runs from the last SUCCESSFUL fetch. A failure never rewrites
    that timestamp, so a source that stays down ages out rather than pinning
    an old payload forever.
    """
    with _lock:
        held = _last_good.get(city)
    if held and time.time() - held[0] < _TTL_RETAIN:
        return held[1], True
    return {}, False


def _fetch_and_store(city: str):
    """Fetch one city and cache the result. Caller holds the city fetch lock."""
    try:
        records = _fetch_city(city)
    except Exception:
        records = None
    if records is None:
        # Cache the failure too, briefly. A source that is down stays down for
        # a while, and retrying per render turns a slow upstream into a slow
        # site -- the same reasoning as waqi's fallback cache.
        with _lock:
            _cache[city] = (time.time(), {})
        # One transient timeout used to blank a whole city -- observed live,
        # Gurugram went NO READING while all four of its stations were
        # reporting. api.data.gov.in is measurably flaky (an SSL handshake
        # timed out at 20s; the next two attempts answered in 0.5s). Keep
        # serving what we last actually measured, marked, bounded and dated by
        # its own obs_time rather than by our fetch time.
        return _retained(city)

    grouped: dict = {}
    for row in records:
        name = row.get("station")
        if not name:
            continue
        slot = grouped.setdefault(name, {"pm25": None, "pm10": None, "obs_time": None})
        pollutant = (row.get("pollutant_id") or "").upper()
        value = _value(row.get("avg_value"))
        if pollutant == "PM2.5" and value is not None:
            slot["pm25"] = value
        elif pollutant == "PM10" and value is not None:
            slot["pm10"] = value
        # Every row for a station carries the same last_update; keep the first
        # that parses so a single malformed row cannot blank the timestamp.
        if slot["obs_time"] is None:
            slot["obs_time"] = _obs_time(row.get("last_update"))

    with _lock:
        _cache[city] = (time.time(), grouped)
        if grouped:
            _last_good[city] = (time.time(), grouped)
    return grouped, False


def values_for(locality: str):
    """``{"pm25":, "pm10":, "station":, "city":, "obs_time":, "retained":}``.

    None means CPCB has nothing usable for this locality and the caller should
    try its next source. A station that answers but has neither particulate is
    None as well: a row carrying only NO2 cannot produce a CPCB AQI, and
    returning it would stop the fallback from being tried.

    ``retained`` True means these numbers are the last good ones being held
    through an upstream failure, not a fresh answer. They are still real
    measurements with their own ``obs_time``; what changes is what the page is
    allowed to call them.
    """
    if not available() or locality in NOT_A_STATION:
        return None

    city = CITY_OF.get(locality, DEFAULT_CITY)
    stations, retained = _stations(city)
    if not stations:
        return None

    wanted = _normalise(STATION_ALIAS.get(locality, locality))
    match = None
    for name, slot in stations.items():
        # "ITO, Delhi - CPCB" -> "ITO". Comparing against the whole string
        # would also match a station whose suffix happens to contain the name.
        if _normalise(name.split(",")[0]) == wanted:
            match = (name, slot)
            break
    if match is None:
        return None

    name, slot = match
    if slot["pm25"] is None and slot["pm10"] is None:
        return None
    return {"pm25": slot["pm25"], "pm10": slot["pm10"],
            "station": name.split(",")[0].strip(),
            "city": city, "obs_time": slot["obs_time"], "retained": retained}


def cache_clear():
    with _lock:
        _cache.clear()
        _FETCH_LOCKS.clear()
        # Without this the suite becomes order-dependent: a later test inherits
        # an earlier test's payload through the retention path.
        _last_good.clear()
