"""WAQI fetch: live parse, wrong-station and stale-feed guards, bad data -> sample."""
from datetime import datetime, timedelta, timezone

import pytest

from saafsaans.services import aqi_scale, waqi, config


def _iso(hours_ago):
    """An ISO timestamp the given number of hours before now, in IST."""
    ist = timezone(timedelta(hours=5, minutes=30))
    return (datetime.now(ist) - timedelta(hours=hours_ago)).isoformat()


class Resp:
    def __init__(self, status_code=200, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._payload


OK_PAYLOAD = {"status": "ok", "data": {
    "aqi": 312,
    "iaqi": {"pm25": {"v": 250.5}, "pm10": {"v": 400.0}},
    "dominentpol": "pm25",
    "city": {"name": "Anand Vihar, Delhi"},
}}


def test_no_token_returns_stale_no_http(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    calls = []
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: calls.append(1))
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True
    # The sample's AQI is derived from its concentrations, never stored, so
    # the assertion has to derive it the same way rather than read it back.
    sample = waqi.SAMPLES["ITO"]
    assert reading["pm25"] == sample["pm25"]
    assert reading["aqi"] == aqi_scale.cpcb_aqi(sample["pm25"], sample["pm10"])[0]
    assert calls == []  # no network call attempted


def test_fallback_varies_by_locality(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    aqis = {loc: waqi.get_aqi(loc)[0]["aqi"] for loc in waqi.SAMPLES}
    # These moved when the samples stopped carrying a hand-written AQI and
    # started deriving it from their own concentrations on the CPCB scale.
    # Anand Vihar's PM2.5 of 380 is past CPCB's last published breakpoint, so
    # it reports the floor of Severe rather than an invented interpolation.
    assert aqis["Anand Vihar"] == 401
    assert aqis["Rohini"] == 267
    assert len(set(aqis.values())) >= 4  # localities are visibly distinct
    # Unknown locality falls back to the Delhi default sample.
    assert waqi.get_aqi("Nowhere")[0]["aqi"] == waqi.get_aqi("Delhi (city)")[0]["aqi"] == 369


def test_all_localities_have_feed_and_sample():
    # Every UI locality must resolve to both a feed and a mock sample.
    for loc in waqi.LOCALITIES:
        assert loc in waqi.FEED_MAP, f"{loc} missing feed"
        assert loc in waqi.SAMPLES, f"{loc} missing sample"
    # Regions partition LOCALITIES with no overlaps.
    assert set(waqi.LOCALITIES) == set(waqi.REGIONS["Delhi"]) | set(waqi.REGIONS["NCR"])
    assert len(waqi.LOCALITIES) >= 20


def test_fallback_carries_sample_dominant_pollutant(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    # Gurugram's sample declares an ozone driver -> best-window can vary. Ozone
    # is not one of the two particulates the app's own index is built from, so
    # it belongs to feed_dominant; dominant_pollutant names whichever
    # particulate actually drove our number, and can only ever be pm25 or pm10.
    gurugram = waqi.get_aqi("Gurugram")[0]
    assert gurugram["feed_dominant"] == "o3"
    assert gurugram["dominant_pollutant"] in ("pm25", "pm10")
    assert waqi.get_aqi("Rohini")[0]["feed_dominant"] is None


def test_live_ok(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, OK_PAYLOAD))
    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "ok"
    # The payload's iaqi values are US EPA sub-indices; the reading carries the
    # concentrations behind them and an index on India's scale.
    assert reading["feed_aqi"] == 312
    assert reading["pm25"] == 200.9
    assert reading["pm10"] == 504.0
    assert reading["aqi"] == 401
    assert reading["aqi_beyond_scale"] is True
    # PM10 at 504 µg/m3 is the worse of the two on the CPCB scale, so it is
    # what drove the index -- even though the feed named pm25 as its dominant.
    assert reading["dominant_pollutant"] == "pm10"
    assert reading["feed_dominant"] == "pm25"
    assert reading["stale"] is False


def test_station_404_does_not_borrow_the_city_feed(monkeypatch):
    # A station feed that 404s used to be retried against the Delhi city feed,
    # which answers from a different station -- so the locality was shown
    # another neighbourhood's air. It must degrade to its labelled sample.
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        if "anand-vihar" in url:
            return Resp(404)
        return Resp(200, OK_PAYLOAD)

    monkeypatch.setattr(waqi.requests, "get", fake_get)
    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "fallback"
    assert reading["stale"] is True
    assert len(urls) == 1
    assert all("feed/delhi/?token" not in u for u in urls)


def test_ncr_feed_failure_does_not_borrow_delhi(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        if "gurugram" in url:
            return Resp(404)          # NCR feed down
        return Resp(200, OK_PAYLOAD)  # Delhi city feed would succeed

    monkeypatch.setattr(waqi.requests, "get", fake_get)
    reading, status = waqi.get_aqi("Gurugram")
    # Must NOT fall back to the Delhi city feed for an NCR city.
    assert status == "fallback"
    assert reading["stale"] is True
    assert all("feed/delhi/?token" not in u for u in urls)


def test_timeout_returns_stale(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")

    def boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(waqi.requests, "get", boom)
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True


def test_non_numeric_aqi_falls_back(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = {"status": "ok", "data": {"aqi": "-", "iaqi": {}, "city": {"name": "Delhi"}}}
    # No headline number and no particulates -> nothing to show.
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("Delhi (city)")
    assert status == "fallback"
    assert reading["stale"] is True


def test_missing_pm25_no_crash(monkeypatch):
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = {"status": "ok", "data": {"aqi": 150, "iaqi": {}, "dominentpol": "o3",
                                        "city": {"name": "Delhi"}}}
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("Delhi (city)")
    assert status == "ok"
    assert reading["pm25"] is None
    # No particulate means no index this app can honestly compute. Falling back
    # to the feed's own number would put a US EPA figure under Indian band
    # names, which is exactly the defect the conversion exists to remove.
    assert reading["aqi"] is None
    assert reading["feed_aqi"] == 150
    assert reading["feed_dominant"] == "o3"


# --- the feed must be who it claims to be ----------------------------------
def _payload(city_name, obs_time=None):
    data = {"aqi": 312, "iaqi": {"pm25": {"v": 250.5}, "pm10": {"v": 400.0}},
            "dominentpol": "pm25", "city": {"name": city_name}}
    if obs_time is not None:
        data["time"] = {"iso": obs_time}
    return {"status": "ok", "data": data}


def test_wrong_station_is_never_shown_as_this_locality(monkeypatch):
    # The live 'noida' slug returned the Anand Vihar, Delhi station verbatim,
    # and the app labelled it Noida. Delhi's air must not be shown as Noida's.
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = _payload("Anand Vihar, Delhi, Delhi, India", _iso(1))
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("Noida")
    assert status == "fallback"
    assert reading["stale"] is True
    # ...and the same payload IS accepted for the locality it really is.
    assert waqi.get_aqi("Anand Vihar")[1] == "ok"


def test_corroboration_tolerates_punctuation_and_longer_station_names():
    # The feed's station names carry punctuation and extra words the UI labels
    # do not; matching must survive that without accepting a different station.
    assert waqi._corroborates("RK Puram", "R.K. Puram, Delhi, Delhi, India")
    assert waqi._corroborates("Dwarka", "National Institute of Malaria "
                                        "Research, Sector 8, Dwarka, Delhi, India")
    assert waqi._corroborates("Patparganj", "Mother Dairy Plant, Parparganj, Delhi")
    assert waqi._corroborates("Delhi (city)", "Major Dhyan Chand National "
                                              "Stadium, Delhi, Delhi, India")
    assert not waqi._corroborates("Noida", "Anand Vihar, Delhi, Delhi, India")
    assert not waqi._corroborates("Faridabad", "Dr. Karni Singh Shooting "
                                               "Range, Delhi, Delhi, India")
    assert not waqi._corroborates("Rohini", "")


def test_localities_without_a_feed_make_no_request(monkeypatch):
    # WAQI has no station for these, so they are mapped to None rather than to
    # a neighbouring station. They must not fetch anything at all.
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    calls = []
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: calls.append(1))
    for loc in [l for l, feed in waqi.FEED_MAP.items() if feed is None]:
        reading, status = waqi.get_aqi(loc)
        assert status == "fallback"
        assert reading["stale"] is True
    assert calls == []


def test_every_feed_slug_is_pinned_or_named_for_its_locality():
    # Guards the mapping against a silent edit back to a slug that resolves
    # elsewhere: a slug is either a station uid (@nnnn), the Delhi city feed,
    # or a path that names the locality it is mapped to.
    for locality, feed in waqi.FEED_MAP.items():
        if feed is None or feed.startswith("@") or feed == waqi.CITY_FEED:
            continue
        expected = waqi._normalise(waqi.FEED_NAME_ALIASES.get(locality, locality))
        assert expected in waqi._normalise(feed), f"{locality} -> {feed}"


# --- a stale feed is not a live reading ------------------------------------
def test_month_old_observation_is_not_reported_live(monkeypatch):
    # The live 'delhi/ito' feed returned status "ok" with a four-week-old
    # observation, and the UI stamped it LIVE.
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = _payload("ITO, Delhi, Delhi, India", "2026-06-23T02:00:00+05:30")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["stale"] is True


def test_observation_within_the_window_stays_live(monkeypatch):
    # Real feeds lag several hours behind the clock; that is still live.
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    payload = _payload("ITO, Delhi, Delhi, India", _iso(5))
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
    reading, status = waqi.get_aqi("ITO")
    assert status == "ok"
    assert reading["stale"] is False
    assert reading["obs_time"] is not None


def test_freshness_boundary_is_twelve_hours():
    assert waqi.MAX_OBS_AGE == timedelta(hours=12)
    assert not waqi._obs_too_old(_iso(11))
    assert waqi._obs_too_old(_iso(13))


def test_missing_or_unparseable_obs_time_is_not_treated_as_stale(monkeypatch):
    # No timestamp is no evidence of staleness. Dropping these would delete
    # every reading from a feed that simply does not publish an observation
    # time, which is a bigger hole than the one the check exists to close.
    assert waqi._obs_too_old(None) is False
    assert waqi._obs_too_old("") is False
    assert waqi._obs_too_old("not a date") is False

    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    for payload in (_payload("ITO, Delhi", None), _payload("ITO, Delhi", "whenever")):
        monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp(200, payload))
        reading, status = waqi.get_aqi("ITO")
        assert status == "ok"
        assert reading["stale"] is False


# --- the reading is fetched once, not once per reader ----------------------
def test_repeat_readers_of_a_locality_share_one_upstream_fetch(monkeypatch):
    """The fetch is blocking and sits on the request path, on one 256MB
    machine that scales to zero. Ten readers in the same minute meant ten
    round trips for a number WAQI only republishes hourly."""
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    calls = []

    def _counted(*a, **k):
        calls.append(1)
        return Resp(200, _payload("Anand Vihar, Delhi, Delhi, India", _iso(1)))

    monkeypatch.setattr(waqi.requests, "get", _counted)
    first = waqi.get_aqi("Anand Vihar")
    for _ in range(9):
        assert waqi.get_aqi("Anand Vihar") == first
    assert len(calls) == 1, f"{len(calls)} upstream fetches for 10 readers"


def test_a_different_locality_is_not_served_another_ones_reading(monkeypatch):
    """The cache key is the locality. Serving Rohini's air as Dwarka's would be
    the mislabelling bug this module already has a corroboration check for."""
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    seen = []

    def _by_feed(url, *a, **k):
        seen.append(url)
        name = "Anand Vihar, Delhi, Delhi, India" if "anand" in url.lower() \
            else "Dwarka, Delhi, Delhi, India"
        return Resp(200, _payload(name, _iso(1)))

    monkeypatch.setattr(waqi.requests, "get", _by_feed)
    waqi.get_aqi("Anand Vihar")
    waqi.get_aqi("Dwarka")
    assert len(seen) == 2, "the second locality was served from the first's entry"


def test_a_cache_hit_writes_nothing_to_elasticsearch(monkeypatch):
    """aqi-readings grew with TRAFFIC rather than with OBSERVATIONS: the same
    hourly figure was stored on every render, which is a false account of how
    often the city was measured and makes every aggregate over it wrong."""
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get",
                        lambda *a, **k: Resp(200, _payload(
                            "Anand Vihar, Delhi, Delhi, India", _iso(1))))
    indexed = []
    monkeypatch.setattr(waqi.es, "index_reading",
                        lambda client, doc: indexed.append(doc))

    for _ in range(10):
        waqi.get_aqi("Anand Vihar", es_client=object())
    assert len(indexed) == 1, (
        f"{len(indexed)} documents written for one observation")


def test_a_stale_entry_is_refetched(monkeypatch):
    """A cache that never expires is a different bug: the page would show
    yesterday's air. The entry must age out."""
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    calls = []
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: (
        calls.append(1), Resp(200, _payload(
            "Anand Vihar, Delhi, Delhi, India", _iso(1))))[1])

    waqi.get_aqi("Anand Vihar")
    assert len(calls) == 1
    # Age every entry past the live TTL without sleeping through it.
    with waqi._CACHE_LOCK:
        for key, (stored_at, reading, status) in list(waqi._CACHE.items()):
            waqi._CACHE[key] = (stored_at - waqi._CACHE_TTL - 1, reading, status)
    waqi.get_aqi("Anand Vihar")
    assert len(calls) == 2, "a stale entry was served instead of refetched"


def test_a_failing_station_is_retried_sooner_than_a_good_one(monkeypatch):
    """A failure is cached too -- hammering a down station once per render is
    how a slow upstream becomes a slow site -- but on a shorter clock."""
    assert waqi._CACHE_TTL_FALLBACK < waqi._CACHE_TTL
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    calls = []
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: (
        calls.append(1), Resp(500, {}))[1])

    reading, status = waqi.get_aqi("Anand Vihar")
    assert status == "fallback"
    waqi.get_aqi("Anand Vihar")
    assert len(calls) == 1, "the failing station was refetched immediately"

    with waqi._CACHE_LOCK:
        for key, (stored_at, r, s) in list(waqi._CACHE.items()):
            waqi._CACHE[key] = (stored_at - waqi._CACHE_TTL_FALLBACK - 1, r, s)
    waqi.get_aqi("Anand Vihar")
    assert len(calls) == 2, "the failure was cached for the full live TTL"
