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

import pytest

from saafsaans.services import aqi_scale, config, cpcb, waqi


def rows(station, pm25=None, pm10=None, when="21-07-2026 19:00:00", city="Delhi"):
    """The upstream shape: one record per pollutant per station."""
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
                "time": {"iso": "2026-07-21T17:00:00+05:30"}}}

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
    """Deliberately unmapped: FEED_MAP gives these a bare city slug, so there is
    no existing choice to mirror and this module must not invent one. If
    somebody adds an alias, they have made a decision about whose air
    represents the city and this test should be the thing that makes them say
    so out loud."""
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
        out[locality] = cpcb._stations("Delhi")

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
            results[city] = cpcb._stations(city)
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
