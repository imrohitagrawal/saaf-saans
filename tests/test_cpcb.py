"""CPCB (data.gov.in) as the primary source, WAQI as the fallback.

The tests that matter most here are not about fetching. They are about the two
ways this integration can be wrong while looking right:

* **Units.** CPCB publishes concentrations in ug/m3; WAQI publishes AQI
  sub-indices on the US EPA scale. Both arrive as small integers beside a
  pollutant name. Running a CPCB value through the inversion that exists for
  WAQI inflates every reading in the app, and nothing on screen looks broken.
* **"NA".** The feed says ``"NA"`` when an instrument is down. Parsing it as a
  number raises; defaulting it to zero invents a reading. This app has spent
  two runs deleting invented readings.
"""
import json
import threading
import time
from datetime import timedelta

import pytest

from saafsaans.services import aqi_scale, clock, config, cpcb, waqi


def _recent_ist(hours_ago: int = 1) -> str:
    """A ``last_update`` the freshness check accepts, in the feed's own layout.

    Relative to now, deliberately. This was the literal
    ``"21-07-2026 19:00:00"``, which sat inside ``waqi.MAX_OBS_AGE`` (12 hours)
    only on the day it was written: from 2026-07-22 onward every reading built
    here was refused as stale, the WAQI fallback fired, and 21 tests in this
    file failed for a reason unrelated to what they assert. A fixture that
    encodes today's date expires; one that encodes an offset does not.
    """
    return (clock.now_ist() - timedelta(hours=hours_ago)).strftime("%d-%m-%Y %H:%M:%S")


def _recent_iso(hours_ago: int = 2) -> str:
    """The same idea in WAQI's layout: ``data.time.iso``, an ISO-8601 instant."""
    return (clock.now_ist() - timedelta(hours=hours_ago)).isoformat()


# Fixed once at import rather than per call, because FRESH_WAQI_ISO is asserted
# against as well as fed in, and the two must agree inside a single run.
FRESH_CPCB_WHEN = _recent_ist()
FRESH_WAQI_ISO = _recent_iso()


def rows(station, pm25=None, pm10=None, when=None, city="Delhi"):
    """The upstream shape: one record per pollutant per station."""
    if when is None:
        when = FRESH_CPCB_WHEN
    out = []
    for pollutant, value in (("PM2.5", pm25), ("PM10", pm10)):
        if value is not None:
            out.append({"station": station, "city": city, "pollutant_id": pollutant,
                        "avg_value": str(value), "last_update": when})
    return out


@pytest.fixture(autouse=True)
def _clean_caches():
    waqi.cache_clear()
    cpcb.cache_clear()
    yield
    waqi.cache_clear()
    cpcb.cache_clear()


@pytest.fixture
def feed(monkeypatch):
    """Serve a fixed record list for every city query. Returns the call log."""
    calls = []

    def install(records):
        def fake(city):
            calls.append(city)
            return list(records)
        monkeypatch.setattr(cpcb, "_fetch_city", fake)
        monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    install.calls = calls
    return install


# --------------------------------------------------------------- the unit trap
def test_a_cpcb_concentration_is_not_put_through_the_waqi_inversion(feed, monkeypatch):
    """The defect that would be invisible.

    ``aqi_scale.concentration`` inverts a US EPA sub-index into micrograms. It
    exists for WAQI. A CPCB value is ALREADY micrograms, so inverting it would
    silently inflate every reading -- the page would look entirely normal and
    every number on it would be wrong.

    Asserted two ways, because either alone can pass by accident: the AQI must
    equal what the CPCB scale makes of the RAW concentration, and the inversion
    must not be called at all during a CPCB fetch.
    """
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=63))

    def forbidden(*a, **k):
        pytest.fail("a CPCB concentration was run through the WAQI inversion")

    monkeypatch.setattr(waqi.aqi_scale, "concentration", forbidden)
    reading, status = waqi.get_aqi("ITO")

    assert status == "ok"
    assert reading["pm25"] == 53 and reading["pm10"] == 63
    expected = aqi_scale.cpcb_aqi(53.0, 63.0)
    assert reading["aqi"] == expected[0]


def test_the_inversion_would_actually_change_the_number(feed, monkeypatch):
    """Guards the test above from being vacuous.

    If inverting 53 happened to yield 53, the assertion proves nothing. This
    pins that the two readings genuinely differ, so the test has something to
    catch.
    """
    inverted = aqi_scale.concentration(53.0, "pm25")
    assert inverted is not None
    assert abs(inverted - 53.0) > 1.0, (
        "inversion is near-identity at this value; pick another fixture value")


# --------------------------------------------------------------------- "NA"
@pytest.mark.parametrize("bad", ["NA", "na", "", "  ", "-", None, "abc"])
def test_an_unusable_value_never_becomes_a_number(bad):
    assert cpcb._value(bad) is None


def test_a_negative_concentration_is_refused():
    """An instrument fault, not clean air."""
    assert cpcb._value("-5") is None


def test_a_station_whose_only_particulate_is_na_yields_no_reading(feed, monkeypatch):
    """Wazirpur on the day this was written: PM10 present, PM2.5 "NA".

    The reading must still be built from PM10 rather than discarded -- but a
    station where BOTH are NA must produce nothing at all, so the WAQI fallback
    is tried instead of a shell being returned.
    """
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    records = [{"station": "Bawana, Delhi - DPCC", "city": "Delhi",
                "pollutant_id": p, "avg_value": "NA",
                "last_update": "21-07-2026 19:00:00"} for p in ("PM2.5", "PM10")]
    feed(records)
    assert cpcb.values_for("Bawana") is None


def test_a_station_with_only_pm10_still_reads(feed):
    feed(rows("Wazirpur, Delhi - DPCC", pm10=125))
    values = cpcb.values_for("Wazirpur")
    assert values["pm10"] == 125 and values["pm25"] is None


# ------------------------------------------------------------------ timestamps
def test_the_feed_date_is_read_as_day_first_ist_not_iso():
    """``21-07-2026`` is 21 July 2026 in IST.

    Parsed as ISO it would be year 21, which does not raise -- it produces a
    date two thousand years off that every freshness check then treats as
    ancient. The offset matters as much: without it the reading is read as UTC
    and appears five and a half hours older than it is.
    """
    iso = cpcb._obs_time("21-07-2026 19:00:00")
    assert iso.startswith("2026-07-21T19:00:00")
    assert "+05:30" in iso


@pytest.mark.parametrize("bad", ["", None, "2026-07-21", "not a date", "99-99-2026 19:00:00"])
def test_an_unparseable_date_is_none_rather_than_a_wrong_date(bad):
    assert cpcb._obs_time(bad) is None


def test_a_stale_cpcb_reading_is_refused(feed, monkeypatch):
    """ITO sat a month stale in WAQI's mirror and was served as live. The same
    must not become possible through this source."""
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=63, when="23-06-2026 02:00:00"))
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["aqi"] is None


# -------------------------------------------------------------- source order
def test_cpcb_is_preferred_over_waqi(feed, monkeypatch):
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=63))
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get",
                        lambda *a, **k: pytest.fail("WAQI was called while CPCB had a reading"))
    reading, status = waqi.get_aqi("ITO")
    assert status == "ok" and reading["pm25"] == 53


def test_waqi_is_tried_when_cpcb_has_nothing(feed, monkeypatch):
    """The fallback must be reachable, or having one is a fiction.

    Wazirpur is the real case: CPCB's PM2.5 instrument was down and WAQI still
    carried the station.
    """
    feed([])  # CPCB answers, with nothing for anybody
    called = []

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            called.append(1)
            return {"status": "ok", "data": {
                "aqi": 199, "city": {"name": "Wazirpur, Delhi"},
                "iaqi": {"pm25": {"v": 163}, "pm10": {"v": 147}},
                "time": {"iso": FRESH_WAQI_ISO}}}

    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp())
    reading, status = waqi.get_aqi("Wazirpur")
    assert called, "WAQI was never tried"
    assert status == "ok"


def test_with_no_cpcb_key_nothing_is_fetched_from_it(monkeypatch):
    monkeypatch.setattr(config, "cpcb_key", lambda: "")
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: pytest.fail("fetched CPCB without a key"))
    assert cpcb.values_for("ITO") is None


# ---------------------------------------------------------- station matching
def test_every_locality_the_app_offers_is_either_mapped_or_deliberately_not(feed):
    """A locality that silently matches nothing renders NO READING for ever.

    Written over the real picker list rather than a copy, so a locality added
    to the app fails here instead of quietly losing its CPCB source.
    """
    feed(rows("ITO, Delhi - CPCB", pm25=1))
    for locality in waqi.LOCALITIES:
        if locality in cpcb.NOT_A_STATION:
            assert cpcb.values_for(locality) is None
            continue
        city = cpcb.CITY_OF.get(locality, cpcb.DEFAULT_CITY)
        assert city, f"{locality} has no city query"
        assert cpcb._normalise(cpcb.STATION_ALIAS.get(locality, locality))


@pytest.mark.parametrize("label,station", [
    ("RK Puram", "R K Puram, Delhi - DPCC"),
    ("Dwarka", "NSIT Dwarka, Delhi - CPCB"),
    ("Okhla", "Okhla Phase-2, Delhi - DPCC"),
    ("ITO", "ITO, Delhi - CPCB"),
])
def test_the_aliases_match_the_spellings_the_feed_actually_uses(feed, label, station):
    feed(rows(station, pm25=40, pm10=60))
    values = cpcb.values_for(label)
    assert values is not None, f"{label} did not match {station!r}"


def test_a_station_is_not_matched_on_a_partial_name(feed):
    """"Okhla" must not match "Okhla Phase-2" by accident, and vice versa --
    the alias makes it explicit. A substring rule would also make "Noida" match
    "Greater Noida", which is a different city's air under the wrong name."""
    feed(rows("Greater Noida, UP - UPPCB", pm25=40, city="Greater Noida"))
    assert cpcb.values_for("Noida") is None


def test_the_delhi_aggregate_is_never_looked_up_as_a_station(feed):
    """"Delhi (city)" is computed, not operated. Asking CPCB for it would
    either miss or match some unrelated station."""
    feed(rows("ITO, Delhi - CPCB", pm25=53))
    assert cpcb.values_for("Delhi (city)") is None


# ------------------------------------------------------------------- caching
def test_one_upstream_call_serves_every_locality_in_a_city(feed):
    """City Pulse renders twenty-one localities. Per-locality fetching is what
    made that page fire twenty-one upstream calls per render."""
    feed(rows("ITO, Delhi - CPCB", pm25=53) + rows("DTU, Delhi - CPCB", pm25=46))
    cpcb.values_for("ITO")
    cpcb.values_for("DTU")
    cpcb.values_for("Rohini")
    assert feed.calls == ["Delhi"], f"expected one Delhi fetch, got {feed.calls}"


def test_clearing_the_waqi_cache_also_clears_the_cpcb_one(feed):
    feed(rows("ITO, Delhi - CPCB", pm25=53))
    cpcb.values_for("ITO")
    assert feed.calls == ["Delhi"]
    waqi.cache_clear()
    cpcb.values_for("ITO")
    assert feed.calls == ["Delhi", "Delhi"], "the CPCB cache survived cache_clear"


def test_an_upstream_failure_is_absorbed(monkeypatch):
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")

    def boom(city):
        raise OSError("upstream down")

    monkeypatch.setattr(cpcb, "_fetch_city", boom)
    assert cpcb.values_for("ITO") is None


def test_paging_stops_at_a_short_page(monkeypatch):
    """Delhi returns 315 rows against a 300 page size. A single page silently
    drops the tail -- which is how ITO's PM2.5 was nearly declared missing."""
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    # A full page is exactly PAGE records; rows() yields one per pollutant.
    full = rows("A, Delhi - X", pm25=1, pm10=2) * (cpcb.PAGE // 2)
    assert len(full) == cpcb.PAGE
    pages, seen = [full, rows("B, Delhi - X", pm25=2)], []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        seen.append(url)
        index = len(seen) - 1
        batch = pages[index] if index < len(pages) else []
        return FakeResponse({"records": batch})

    monkeypatch.setattr(cpcb.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cpcb.json, "load", lambda fh: json.loads(fh.read()))
    records = cpcb._fetch_city("Delhi")
    assert len(seen) == 2, f"expected two pages then stop, got {len(seen)}"
    assert len(records) == 300 + 1
    assert "offset=300" in seen[1]


# ------------------------------------------------------------------- NCR
@pytest.mark.parametrize("label,station", [
    ("Noida", "Sector - 62, Noida - IITM"),
    ("Gurugram", "Sector-51, Gurugram - HSPCB"),
    ("Faridabad", "Sector 11, Faridabad - HSPCB"),
])
def test_the_ncr_aliases_point_at_the_station_feed_map_already_chose(feed, label, station):
    """These mirror FEED_MAP's pinned WAQI station rather than picking a new
    one. If the alias drifts off that station the app starts showing a
    different neighbourhood's air under the city's name."""
    feed(rows(station, pm25=77, pm10=86, city=label))
    values = cpcb.values_for(label)
    assert values is not None, f"{label} did not match {station!r}"
    assert values["city"] == label


@pytest.mark.parametrize("label", ["Greater Noida", "Ghaziabad"])
def test_the_cities_with_no_pinned_station_are_left_to_waqi(feed, label):
    """Deliberately unmapped. FEED_MAP gives these a bare city slug rather than
    a pinned station -- which does not mean no station answers for that slug,
    only that nobody chose one HERE. Picking one would be a decision about
    whose air represents the city, and this test exists to make whoever makes
    it say so out loud."""
    assert label not in cpcb.STATION_ALIAS
    feed(rows(f"Somewhere, {label} - UPPCB", pm25=30, city=label))
    assert cpcb.values_for(label) is None


def test_a_failed_city_fetch_is_retried_sooner_than_a_good_one(feed, monkeypatch):
    """One timeout must not blank a whole city for the full cache life.

    Observed live: Gurugram rendered NO READING while its four stations were
    reporting, because a single failed fetch was cached for ten minutes.
    """
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    calls = []

    def flaky(city):
        calls.append(city)
        if len(calls) == 1:
            raise OSError("transient")
        return rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram")

    monkeypatch.setattr(cpcb, "_fetch_city", flaky)
    assert cpcb.values_for("Gurugram") is None          # the failure

    # Inside the failure TTL, no refetch; past it, one more attempt.
    assert cpcb.values_for("Gurugram") is None
    assert len(calls) == 1, "refetched inside the failure TTL"

    with cpcb._lock:                                     # age the failure out
        stored_at, grouped = cpcb._cache["Gurugram"]
        cpcb._cache["Gurugram"] = (stored_at - cpcb._TTL_FAILURE - 1, grouped)

    values = cpcb.values_for("Gurugram")
    assert len(calls) == 2, "a failed city was never retried"
    assert values is not None and values["pm25"] == 77


def test_a_good_city_fetch_is_not_refetched_inside_its_ttl(feed):
    """The mirror of the test above: the shorter TTL must apply only to
    failures, or the cache stops doing its job."""
    feed(rows("ITO, Delhi - CPCB", pm25=53))
    cpcb.values_for("ITO")
    with cpcb._lock:
        stored_at, grouped = cpcb._cache["Delhi"]
        cpcb._cache["Delhi"] = (stored_at - cpcb._TTL_FAILURE - 1, grouped)
    cpcb.values_for("ITO")
    assert feed.calls == ["Delhi"], "a good payload expired at the failure TTL"


def test_paging_stops_at_the_deadline(monkeypatch):
    """The fetch blocks a page render on a machine that scales to zero. A slow
    upstream must cost one slow page, not four."""
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    clock = {"t": 0.0}
    monkeypatch.setattr(cpcb.time, "monotonic", lambda: clock["t"])

    class FakeResponse:
        def read(self):
            return json.dumps({"records": rows("A, Delhi - X", pm25=1, pm10=2)
                               * (cpcb.PAGE // 2)}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    pages = []

    def slow(request, timeout=None):
        pages.append(1)
        clock["t"] += cpcb.DEADLINE  # each page burns the whole budget
        return FakeResponse()

    monkeypatch.setattr(cpcb.urllib.request, "urlopen", slow)
    monkeypatch.setattr(cpcb.json, "load", lambda fh: json.loads(fh.read()))
    cpcb._fetch_city("Delhi")
    assert len(pages) == 2, f"expected to stop at the deadline, fetched {len(pages)} pages"


def test_the_request_timeout_is_a_page_load_budget():
    """Pinned because it is a user-facing number, not a tuning constant: the
    first version used 20s and a reader waited all of it for a handshake that
    was never going to complete."""
    assert cpcb.TIMEOUT <= 10
    assert cpcb.DEADLINE <= 20


# ------------------------------------------------------- the thundering herd
#
# Every test below MUST stub ``config.cpcb_key``. Without it ``available()``
# short-circuits, ``values_for`` returns None before reaching the fetch, and a
# herd test passes with a counter of zero -- green while measuring nothing.
def test_one_cold_miss_produces_one_upstream_fetch_not_eight(monkeypatch):
    """Measured on a cold /city render: eight workers, eight Delhi fetches.

    ``waqi._FETCH_LOCKS`` cannot collapse this. Those are keyed by locality,
    and these are eight DIFFERENT localities sharing one CPCB city entry.
    """
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    localities = ["ITO", "DTU", "Rohini", "Dwarka",
                  "Okhla", "Wazirpur", "Najafgarh", "Punjabi Bagh"]
    barrier = threading.Barrier(len(localities))
    released = threading.Event()
    calls = []

    def slow(city):
        calls.append(city)
        # Hold the first fetch open until every thread has had its chance to
        # arrive, so a missing lock shows up as extra calls rather than as a
        # race the test happens to win.
        released.wait(5)
        return rows("ITO, Delhi - CPCB", pm25=53) + rows("DTU, Delhi - CPCB", pm25=46)

    monkeypatch.setattr(cpcb, "_fetch_city", slow)
    out = {}

    def worker(locality):
        barrier.wait(5)
        out[locality] = cpcb._stations("Delhi")[0]

    threads = [threading.Thread(target=worker, args=(loc,)) for loc in localities]
    for thread in threads:
        thread.start()
    # Every thread is either inside the fetch or queued on the city lock by now.
    time.sleep(0.2)
    released.set()
    for thread in threads:
        thread.join(5)

    assert calls == ["Delhi"], f"one cold miss made {len(calls)} upstream fetches"
    assert len(out) == len(localities)
    payloads = list(out.values())
    assert all(payload == payloads[0] for payload in payloads)
    assert payloads[0], "every worker got an empty payload"


def test_a_second_city_is_not_blocked_by_a_slow_first_city(monkeypatch):
    """The lock is per city, not global.

    A single global lock passes the test above and fails this one: Gurugram
    would queue behind Delhi's fetch instead of running beside it. Gated on an
    Event released only once both fetches are in flight, never on the clock.
    """
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    both_in_flight = threading.Barrier(2, timeout=5)

    def fetch(city):
        both_in_flight.wait()       # raises BrokenBarrierError if serialised
        return rows(f"Sector-51, {city} - CPCB", pm25=77, city=city)

    monkeypatch.setattr(cpcb, "_fetch_city", fetch)
    results = {}

    def worker(city):
        try:
            results[city] = cpcb._stations(city)[0]
        except Exception as exc:    # noqa: BLE001 - recorded, asserted below
            results[city] = exc

    threads = [threading.Thread(target=worker, args=(city,))
               for city in ("Delhi", "Gurugram")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert set(results) == {"Delhi", "Gurugram"}
    for city, result in results.items():
        # A serialised fetch breaks the barrier, ``_fetch_and_store`` absorbs
        # the exception and caches the EMPTY failure marker -- which is still a
        # dict. So the payload itself is asserted, not merely its type.
        assert result, f"{city} did not fetch concurrently: {result}"
        assert f"Sector-51, {city} - CPCB" in result


# ----------------------------------------------------------------- retention
#
# One transient timeout used to blank a whole city: observed live, Gurugram
# rendered NO READING while all four of its stations were reporting. These
# tests assert BOTH halves every time -- the numbers came back AND the flag
# says they are held. Numbers without the flag is the dangerous half-fix: it
# serves an old reading as a live one.
def _age_the_cache(city, seconds):
    with cpcb._lock:
        stored_at, grouped = cpcb._cache[city]
        cpcb._cache[city] = (stored_at - seconds, grouped)


def test_a_transient_failure_serves_the_last_good_payload(feed, monkeypatch):
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram"))
    good = cpcb.values_for("Gurugram")
    assert good["pm25"] == 77 and good["retained"] is False

    _age_the_cache("Gurugram", cpcb._TTL + 1)
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("transient")))

    held = cpcb.values_for("Gurugram")
    assert held is not None, "one timeout blanked the whole city"
    assert held["pm25"] == 77 and held["pm10"] == 86
    assert held["retained"] is True, "a held payload was served as a fresh one"
    # The age the reader sees is the MEASUREMENT's age, not our fetch time.
    assert held["obs_time"] == good["obs_time"]


def test_a_second_render_inside_the_failure_window_is_also_served(feed, monkeypatch):
    """The failure marker is a cache HIT and it is falsy.

    A re-serve written only in the ``except`` branch rescues exactly one call:
    the next render reads ``(t, {})`` back out of the cache, sees a hit, and
    blanks the city for the rest of the failure TTL.
    """
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram"))
    cpcb.values_for("Gurugram")
    _age_the_cache("Gurugram", cpcb._TTL + 1)
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("transient")))

    first = cpcb.values_for("Gurugram")
    second = cpcb.values_for("Gurugram")
    assert first is not None and second is not None, "the second render blanked"
    assert second["pm25"] == 77
    assert second["retained"] is True


def test_a_retained_payload_past_the_bound_is_not_served(feed, monkeypatch):
    """Held, not kept forever. The bound runs from the last SUCCESS."""
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, city="Gurugram"))
    cpcb.values_for("Gurugram")
    _age_the_cache("Gurugram", cpcb._TTL + 1)
    with cpcb._lock:
        stored_at, grouped = cpcb._last_good["Gurugram"]
        cpcb._last_good["Gurugram"] = (stored_at - cpcb._TTL_RETAIN - 1, grouped)
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("transient")))
    assert cpcb.values_for("Gurugram") is None


def test_a_failure_with_no_previous_payload_is_still_blank(monkeypatch):
    """The mirror. Retention holds what we measured; it invents nothing."""
    monkeypatch.setattr(config, "cpcb_key", lambda: "test-key")
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("down")))
    assert cpcb.values_for("Gurugram") is None


def test_a_live_payload_is_never_marked_retained(feed):
    """The other mirror: the flag must distinguish, not decorate."""
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=90))
    assert cpcb.values_for("ITO")["retained"] is False


def test_clearing_the_cache_drops_the_last_good_payload(feed, monkeypatch):
    """Without this the suite is order-dependent: a later test would be served
    an earlier test's numbers through the retention path."""
    feed(rows("ITO, Delhi - CPCB", pm25=53))
    cpcb.values_for("ITO")
    assert cpcb._last_good
    cpcb.cache_clear()
    assert not cpcb._last_good
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("down")))
    assert cpcb.values_for("ITO") is None


def test_a_retained_reading_is_not_indexed_again(feed, monkeypatch):
    """aqi-readings must grow with OBSERVATIONS, not with traffic.

    Re-indexing one held observation on every cache miss is the exact defect
    waqi's module docstring records as fixed.
    """
    indexed = []

    class FakeClient:
        def index(self, **kwargs):
            indexed.append(kwargs)

    from saafsaans.services import es
    monkeypatch.setattr(es, "index_reading",
                        lambda client, reading: indexed.append(reading))
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=90))
    waqi.get_aqi("ITO", es_client=FakeClient())
    assert len(indexed) == 1

    _age_the_cache("Delhi", cpcb._TTL + 1)
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("transient")))
    for _ in range(3):
        # Only the locality cache: waqi.cache_clear() would also drop the CPCB
        # retention this test is about.
        with waqi._CACHE_LOCK:
            waqi._CACHE.clear()
        reading, status = waqi.get_aqi("ITO", es_client=FakeClient())
        assert reading["retained"] is True and status == "ok"
    assert len(indexed) == 1, "a held observation was indexed again"


# --------------------------------------------------- which source answered
#
# The panel has to name the source it used, and nothing else in the reading
# identifies it: feed_aqi is None on a CPCB reading AND on a WAQI station whose
# own headline figure was "-". So the reading carries the answer.
def test_a_cpcb_reading_names_cpcb_as_its_source(feed):
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=90))
    reading, status = waqi.get_aqi("ITO")
    assert status == "ok"
    assert reading["source"] == "cpcb"


def test_a_waqi_reading_names_waqi_as_its_source(monkeypatch):
    monkeypatch.setattr(config, "cpcb_key", lambda: "")
    monkeypatch.setattr(config, "waqi_token", lambda: "token")

    class Resp:
        status_code = 200

        def json(self):
            return {"status": "ok", "data": {
                "aqi": 210, "city": {"name": "ITO, Delhi"},
                "iaqi": {"pm25": {"v": 160}, "pm10": {"v": 90}}}}

    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp())
    reading, status = waqi.get_aqi("ITO")
    assert status == "ok"
    assert reading["source"] == "waqi"


def test_a_reading_with_no_source_claims_neither(monkeypatch):
    """The fallback, and any reading rebuilt from Elasticsearch: ``source`` is
    not indexed, so it comes back None and the panel names nothing."""
    monkeypatch.setattr(config, "cpcb_key", lambda: "")
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    reading, status = waqi.get_aqi("ITO")
    assert status == "fallback"
    assert reading["source"] is None
    from saafsaans.services import es
    assert "source" not in es.READING_FIELDS


# ------------------------------------------------------- choosing one source
#
# The rule and the prohibition. The two sources do not publish the same
# quantity (docs/decisions/0005-averaging-window.md: CPCB's avg_value is a
# rolling 24-hour mean, WAQI's iaqi a sub-index of the latest hour), so a
# reading must come from ONE of them, whole. Every property below that does not
# depend on the policy is asserted under BOTH settings of the flag.
FLAGS = [False, True]


def _waqi_pair(monkeypatch, pm25=163, pm10=147, station="Wazirpur, Delhi"):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            iaqi = {}
            if pm25 is not None:
                iaqi["pm25"] = {"v": pm25}
            if pm10 is not None:
                iaqi["pm10"] = {"v": pm10}
            return {"status": "ok", "data": {
                "aqi": 199, "city": {"name": station}, "iaqi": iaqi,
                "time": {"iso": FRESH_WAQI_ISO}}}

    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Resp())


@pytest.mark.parametrize("flag", FLAGS)
def test_no_reading_ever_mixes_the_two_sources(feed, monkeypatch, flag):
    """The prohibition, under both policies.

    The measured Wazirpur shape: CPCB has PM10 only, WAQI has both. Whatever
    is served, every field of it came from ONE candidate -- no borrowing a
    PM2.5 from the other source to fill the gap.
    """
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", flag)
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    _waqi_pair(monkeypatch)
    reading, status = waqi.get_aqi("Wazirpur")
    assert status == "ok"

    from_cpcb = (129.0, None)
    got = (reading["pm10"], reading["pm25"])
    if reading["source"] == "cpcb":
        assert got == from_cpcb
        assert reading["feed_aqi"] is None
    else:
        assert reading["source"] == "waqi"
        assert reading["pm25"] is not None and reading["pm10"] is not None
        assert reading["obs_time"] == FRESH_WAQI_ISO


def test_the_flag_off_keeps_the_cpcb_single_particulate_reading(feed, monkeypatch):
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", False)
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    _waqi_pair(monkeypatch)
    reading, _status = waqi.get_aqi("Wazirpur")
    assert reading["source"] == "cpcb"
    assert reading["pm10"] == 129.0 and reading["pm25"] is None


def test_the_flag_on_takes_waqi_whole_when_it_has_both(feed, monkeypatch):
    """The mirror. Implemented and tested even though it ships off, so the
    branch cannot rot into something that has never run."""
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", True)
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    _waqi_pair(monkeypatch)
    reading, _status = waqi.get_aqi("Wazirpur")
    assert reading["source"] == "waqi"
    assert reading["pm25"] is not None and reading["pm10"] is not None


@pytest.mark.parametrize("flag", FLAGS)
def test_a_partial_cpcb_reading_survives_when_there_is_no_waqi_token(feed, monkeypatch, flag):
    """Losing a real partial reading would be worse than the defect being
    fixed. Ashok Vihar and Nehru Nagar have no WAQI station at all."""
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", flag)
    monkeypatch.setattr(config, "waqi_token", lambda: "")
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    reading, status = waqi.get_aqi("Wazirpur")
    assert status == "ok" and reading["source"] == "cpcb"
    assert reading["pm10"] == 129.0


@pytest.mark.parametrize("flag", FLAGS)
def test_a_partial_cpcb_reading_survives_a_feed_404(feed, monkeypatch, flag):
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", flag)
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")

    class Missing:
        status_code = 404

        @staticmethod
        def json():
            return {}

    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: Missing())
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    reading, status = waqi.get_aqi("Wazirpur")
    assert status == "ok" and reading["source"] == "cpcb"


@pytest.mark.parametrize("flag", FLAGS)
def test_a_partial_cpcb_reading_survives_a_feed_that_answers_for_elsewhere(
        feed, monkeypatch, flag):
    """_corroborates rejects it, and the partial reading must not go with it."""
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", flag)
    feed(rows("Wazirpur, Delhi - DPCC", pm10=129))
    _waqi_pair(monkeypatch, station="Anand Vihar, Delhi")
    reading, status = waqi.get_aqi("Wazirpur")
    assert status == "ok" and reading["source"] == "cpcb"


@pytest.mark.parametrize("flag", FLAGS)
def test_a_two_particulate_cpcb_reading_never_triggers_a_waqi_call(feed, monkeypatch, flag):
    monkeypatch.setattr(waqi, "PREFER_TWO_PARTICULATES", flag)
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get",
                        lambda *a, **k: pytest.fail("WAQI was called"))
    feed(rows("ITO, Delhi - CPCB", pm25=53, pm10=90))
    reading, _status = waqi.get_aqi("ITO")
    assert reading["source"] == "cpcb"


def test_the_flag_ships_off():
    """Deliberate, and argued in docs/decisions/0005-averaging-window.md: the
    two sources publish different quantities, so preferring WAQI's pair over
    CPCB's single particulate swaps the quantity the CPCB scale is defined on
    for one it is not. Flipping this is a decision, not a tidy-up."""
    assert waqi.PREFER_TWO_PARTICULATES is False


# ------------------------------------------------------ what the tables encode
def test_the_addressable_locality_count_matches_the_docstring():
    """A TABLE-DRIFT GUARD, and nothing more.

    It checks that the number written in cpcb.__doc__ still equals what the
    tables in this module actually encode. It is NOT evidence of coverage:
    whether those 18 localities match a station the feed is publishing today
    is a fact about the feed that no offline test can assert, and no prose may
    cite this test as if it did.
    """
    import re

    unaliased_ncr = [loc for loc in waqi.REGIONS["NCR"]
                     if loc not in cpcb.STATION_ALIAS]
    addressable = (len(waqi.LOCALITIES) - len(cpcb.NOT_A_STATION)
                   - len(unaliased_ncr))

    # Anchored to its own sentence: the docstring also contains 12, 21, 26,
    # 300, 315 and 1000, and a loose \d+ would match whichever came first.
    match = re.search(r"address AT MOST (\d+) of the (\d+) localities",
                      cpcb.__doc__)
    assert match, "the addressability sentence is no longer in the docstring"
    assert int(match.group(1)) == addressable
    assert int(match.group(2)) == len(waqi.LOCALITIES)


# ------------------------------------------- a held payload is not an answer
#
# Retention exists to beat NO READING, not to beat the fallback. Before it was
# added, a CPCB transport failure made values_for return None and WAQI was
# tried; if a held payload short-circuits that, retention has silently replaced
# "fall back to the live source" with "serve the stale primary".
def _waqi_live(monkeypatch, pm25=163, pm10=147, station="Wazirpur, Delhi"):
    """A live WAQI feed answering for Wazirpur. Returns the call log."""
    calls = []

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok", "data": {
                "aqi": 280, "city": {"name": station},
                "iaqi": {"pm25": {"v": pm25}, "pm10": {"v": pm10}},
                "time": {"iso": FRESH_WAQI_ISO}}}

    def fake_get(url, *a, **k):
        calls.append(url)
        return Resp()

    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", fake_get)
    return calls


def _hold_delhi(feed, monkeypatch, **values):
    """Prime a good Delhi payload, then make the next fetch fail."""
    feed(rows("Wazirpur, Delhi - DPCC", **values))
    assert cpcb.values_for("Wazirpur")["retained"] is False
    _age_the_cache("Delhi", cpcb._TTL + 1)
    monkeypatch.setattr(cpcb, "_fetch_city",
                        lambda city: (_ for _ in ()).throw(OSError("transient")))


def test_a_live_waqi_reading_beats_a_held_cpcb_one(feed, monkeypatch):
    """The measured Wazirpur case: CPCB holds a PM10-only 119 while WAQI is
    publishing both particulates for the same station."""
    _hold_delhi(feed, monkeypatch, pm10=129)
    calls = _waqi_live(monkeypatch)

    reading, status = waqi.get_aqi("Wazirpur")

    assert status == "ok"
    assert calls, "WAQI was never asked, so the held payload short-circuited it"
    assert reading["source"] == "waqi"
    assert reading["retained"] is False
    # Whole, never merged: every field came from the one source that answered.
    assert reading["pm25"] is not None and reading["pm10"] is not None


def test_a_held_cpcb_payload_is_still_served_when_waqi_has_nothing(feed, monkeypatch):
    """The mirror. Preferring live must not throw away a real held reading when
    there is no live one -- that would reinstate the blank city retention
    exists to remove."""
    _hold_delhi(feed, monkeypatch, pm25=63, pm10=330)
    monkeypatch.setattr(config, "waqi_token", lambda: "")

    reading, status = waqi.get_aqi("Wazirpur")

    assert status == "ok"
    assert reading["source"] == "cpcb"
    assert reading["retained"] is True
    assert reading["pm25"] == 63 and reading["pm10"] == 330


def test_a_fresh_cpcb_reading_still_beats_a_live_waqi_one(feed, monkeypatch):
    """The narrowing's other mirror: only a HELD payload defers to WAQI. A
    fresh CPCB answer must still win outright, or this change would have
    quietly reversed the primary source."""
    feed(rows("Wazirpur, Delhi - DPCC", pm25=63, pm10=330))
    calls = _waqi_live(monkeypatch)

    reading, status = waqi.get_aqi("Wazirpur")

    assert status == "ok"
    assert reading["source"] == "cpcb"
    assert calls == [], "WAQI was called for a locality CPCB had already answered"


def test_a_held_reading_is_cached_on_the_short_ttl(feed, monkeypatch):
    """cpcb._TTL_FAILURE is 60s so one timeout cannot blank a city for ten
    minutes. Caching the held result under waqi's 600s "ok" TTL made that fast
    retry invisible to the request path: the page went on saying the source was
    failing for ten minutes after it had recovered."""
    _hold_delhi(feed, monkeypatch, pm25=77, pm10=86)
    monkeypatch.setattr(config, "waqi_token", lambda: "")

    reading, _status = waqi.get_aqi("Wazirpur")
    assert reading["retained"] is True

    # Age the locality cache past the FAILURE ttl but not past the live one.
    with waqi._CACHE_LOCK:
        for key, (stored_at, r, s) in list(waqi._CACHE.items()):
            waqi._CACHE[key] = (stored_at - waqi._CACHE_TTL_FALLBACK - 1, r, s)
    assert waqi._CACHE_TTL_FALLBACK + 1 < waqi._CACHE_TTL
    assert waqi._cache_get("Wazirpur") is None, \
        "a held reading was pinned for the full live TTL"

    # And the recovery it exists to allow: CPCB's own failure marker ages out
    # after _TTL_FAILURE, and the very next render serves the fresh figure
    # rather than the held one. This is what the 600s pin made unreachable.
    _age_the_cache("Delhi", cpcb._TTL_FAILURE + 1)
    feed(rows("Wazirpur, Delhi - DPCC", pm25=120, pm10=140))
    reading, _status = waqi.get_aqi("Wazirpur")
    assert reading["retained"] is False and reading["pm25"] == 120


# ------------------------------- a successful-but-empty answer is still a miss
def test_an_empty_but_successful_response_serves_the_last_good_payload(feed, monkeypatch):
    """Retention used to branch on ``records is None``, which is set only when
    _fetch_city RAISES. A 200 carrying no rows (rate limit, key quota, a
    re-indexed resource, an unrecognised filters[city]) yielded records == []
    -> grouped == {} -> stored and returned as no reading, skipping _retained
    entirely while a complete payload sat in _last_good. Same user-visible
    defect as the timeout, on the other failure mode."""
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram"))
    assert cpcb.values_for("Gurugram")["pm25"] == 77
    _age_the_cache("Gurugram", cpcb._TTL + 1)

    feed([])  # answers normally, publishes nothing
    held = cpcb.values_for("Gurugram")

    assert held is not None, "an empty response blanked a city we hold a payload for"
    assert held["pm25"] == 77 and held["retained"] is True


def test_two_consecutive_renders_agree_about_an_empty_response(feed, monkeypatch):
    """The first render blanked the city and the second served the held payload,
    because the empty grouping was filed as a failure marker and _stations'
    marker path calls _retained. One upstream state, two answers."""
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram"))
    cpcb.values_for("Gurugram")
    _age_the_cache("Gurugram", cpcb._TTL + 1)

    feed([])
    first = cpcb.values_for("Gurugram")
    second = cpcb.values_for("Gurugram")

    assert first is not None and second is not None
    assert (first["pm25"], first["retained"]) == (second["pm25"], second["retained"])


def test_an_empty_response_with_nothing_held_is_still_no_reading(feed):
    """The mirror. Retention must not conjure a reading for a city we never
    successfully measured."""
    feed([])
    assert cpcb.values_for("Gurugram") is None


# ------------------------------ a locality with no pinned station costs nothing
def test_a_locality_with_no_pinned_station_makes_no_upstream_call(feed):
    """Greater Noida and Ghaziabad are in CITY_OF but have no STATION_ALIAS, and
    no CPCB station's pre-comma segment normalises to their names -- so each one
    used to issue a full paged city fetch (up to MAX_PAGES requests at TIMEOUT
    each) that structurally could not match. On a cold /city render those two
    held two of the eight pool workers for the whole fetch budget, so localities
    that would have rendered LIVE rendered NO READING instead."""
    feed(rows("Sanjay Nagar, Ghaziabad - UPPCB", pm25=80, pm10=120,
              city="Ghaziabad"))
    for locality in ("Greater Noida", "Ghaziabad", "Delhi (city)"):
        assert cpcb.values_for(locality) is None, locality
    assert feed.calls == [], f"upstream was called for: {feed.calls}"


def test_a_locality_with_a_pinned_station_still_fetches(feed):
    """The mirror, or the guard above could be short-circuiting everything."""
    feed(rows("Sector-51, Gurugram - HSPCB", pm25=77, pm10=86, city="Gurugram"))
    assert cpcb.values_for("Gurugram")["pm25"] == 77
    assert feed.calls == ["Gurugram"]


def test_the_unaddressable_set_is_derived_from_the_tables():
    """Written out by hand it would drift: pinning a Ghaziabad station in
    STATION_ALIAS must make that locality addressable in the same edit."""
    assert cpcb.UNADDRESSABLE == {"Delhi (city)", "Greater Noida", "Ghaziabad"}
    assert all(loc not in cpcb.STATION_ALIAS for loc in cpcb.UNADDRESSABLE)
    for loc in cpcb.STATION_ALIAS:
        assert loc not in cpcb.UNADDRESSABLE, loc


# ------------------------------- a live reading must carry a NUMBER to win
def test_a_numberless_waqi_reading_does_not_beat_a_held_cpcb_payload(feed, monkeypatch):
    """Measured on a real CPCB outage: every Delhi tile rendered "--" while
    cpcb.values_for was returning pm25 53 / pm10 90 on that very render. The
    held payload was reachable the whole time; it lost one layer up.

    ``_fetch_feed`` passes through a reading whose ``aqi`` is None when the feed
    carried a headline value but no invertible particulate -- its guard is ``aqi
    is None AND feed_aqi is None``, an ``and``, and that is deliberate so the
    provenance panel can show WAQI's own figure. ``_choose`` then preferred such
    a reading over a held payload purely for being non-None, trading real
    numbers for a blank. And because it is not ``retained``, ``_cache_get`` gave
    it the 600s TTL, so the blank outlived CPCB's recovery by ten minutes.
    """
    _hold_delhi(feed, monkeypatch, pm25=53, pm10=90)

    class OzoneOnly:
        """The right station, a headline AQI, and nothing to invert."""
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok", "data": {
                "aqi": 412, "city": {"name": "Wazirpur, Delhi"},
                "iaqi": {"o3": {"v": 30}},
                "time": {"iso": FRESH_WAQI_ISO}}}

    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(waqi.requests, "get", lambda *a, **k: OzoneOnly())

    reading, status = waqi.get_aqi("Wazirpur")

    assert status == "ok"
    # The whole point: a number reaches the tile.
    assert reading["aqi"] is not None, "the city would render -- for every tile"
    assert reading["source"] == "cpcb" and reading["retained"] is True
    assert (reading["pm25"], reading["pm10"]) == (53.0, 90.0)


def test_a_live_waqi_reading_with_a_number_still_beats_a_held_payload(feed, monkeypatch):
    """The mirror, and it is the reason the guard tests the NUMBER rather than
    simply preferring CPCB whenever it holds something: a genuinely live WAQI
    reading must still win, or retention quietly becomes "serve the stale
    primary" -- the defect _choose's retained branch exists to prevent."""
    _hold_delhi(feed, monkeypatch, pm25=53, pm10=90)
    calls = _waqi_live(monkeypatch)

    reading, status = waqi.get_aqi("Wazirpur")

    assert status == "ok" and calls
    assert reading["source"] == "waqi" and reading["retained"] is False
    assert reading["aqi"] is not None


def test_a_numberless_reading_is_retried_on_the_short_clock(monkeypatch):
    """The second half. Serving the held payload fixes the render; without this
    a numberless reading that DOES get served still earns the 600s TTL and pins
    whatever it produced for ten minutes past the upstream's recovery."""
    monkeypatch.setattr(config, "waqi_token", lambda: "tok")
    monkeypatch.setattr(config, "cpcb_key", lambda: "")

    class OzoneOnly:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok", "data": {
                "aqi": 412, "city": {"name": "ITO, Delhi"},
                "iaqi": {"o3": {"v": 30}},
                "time": {"iso": FRESH_WAQI_ISO}}}

    calls = []
    monkeypatch.setattr(waqi.requests, "get",
                        lambda *a, **k: (calls.append(1), OzoneOnly())[1])

    waqi.get_aqi("ITO")
    assert len(calls) == 1
    with waqi._CACHE_LOCK:
        for key, (stored_at, r, s) in list(waqi._CACHE.items()):
            waqi._CACHE[key] = (stored_at - waqi._CACHE_TTL_FALLBACK - 1, r, s)
    waqi.get_aqi("ITO")
    assert len(calls) == 2, (
        "a reading with no number was cached for the full live TTL")
