"""City Pulse and Today must answer from the same source of truth.

The defect these guard against: /city had no live path at all. Its only data
call was ``metrics.station_grid``, which reads the Elasticsearch aqi-readings
index, and that index is written from exactly one place -- ``waqi``'s cache-miss
path -- when a visitor loads the HOME page for one locality. Nothing back-filled
the other twenty. So production served, in the same minute:

    /?locality=Rohini   ->  LIVE   AQI 86   SATISFACTORY
    /city               ->  Rohini SAMPLE   (and "median AQI 358" over 21 tiles)

Every test here is written as a PROPERTY over all 21 localities and both
languages, not against the numbers that happened to be on screen that day.
"""
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, waqi
from saafsaans.web.main import app

PERSONA = {"age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise", "theme": "light"}

# A distinct, in-range PM2.5 per locality, so a tile showing another station's
# figure is a visible failure rather than a coincidence. Deliberately spread
# across several CPCB bands.
PM25 = {loc: 20.0 + 11 * i for i, loc in enumerate(waqi.LOCALITIES)}


def _live(monkeypatch, only=None):
    """Stub WAQI live for ``only`` (default: every locality). Records the calls."""
    calls = []

    def get_aqi(locality, es_client=None):
        calls.append(locality)
        if only is not None and locality not in only:
            return waqi._fallback(locality), "fallback"
        pm25 = PM25[locality]
        reading = waqi._reading(pm25, pm25 * 1.6, station=locality, city="Delhi",
                                stale=False, forecast=None,
                                obs_time="2026-07-21T10:00:00+05:30")
        return reading, "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)
    return calls


def _rows(body):
    """{english locality: rendered tile}. Keyed by identity, not by label."""
    found = re.findall(r'<a class="station .*?</a>', body, re.S)
    out = {}
    for lang in ("en", "hi"):
        for loc in waqi.LOCALITIES:
            out.setdefault(i18n.place(lang, loc), loc)
    return {out[re.search(r'class="nm">([^<]+)<', r).group(1)]: r for r in found}


def _tile_aqi(tile):
    m = re.search(r'class="n">([^<]*)<', tile)
    return m.group(1).strip() if m else None


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_city_asks_the_live_feed_for_every_locality(monkeypatch, lang):
    """The root cause, asserted directly: /city must perform a live lookup.

    Before the fix the handler contained no call to ``waqi.get_aqi`` at all, so
    this fails on the old code no matter what the feed returns.
    """
    calls = _live(monkeypatch)
    with TestClient(app) as c:
        assert c.get("/city", params={**PERSONA, "lang": lang}).status_code == 200
    assert set(calls) == set(waqi.LOCALITIES), sorted(set(waqi.LOCALITIES) - set(calls))


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_city_and_today_never_disagree_about_a_station(monkeypatch, lang):
    """THE property. For every locality, the number City Pulse prints for it is
    the number the Today page prints for it, at the same moment.

    Checked over all 21 rather than a sampled few, because the failure was
    total: 21 of 21 tiles disagreed with Today in production.
    """
    _live(monkeypatch)
    with TestClient(app) as c:
        city = _rows(c.get("/city", params={**PERSONA, "lang": lang}).text)
        for loc in waqi.LOCALITIES:
            today = c.get("/", params={**PERSONA, "locality": loc, "lang": lang}).text
            hero = re.search(r'class="hero-pill">AQI (\d+)', today)
            assert hero, (loc, lang, "Today rendered no AQI for a live reading")
            assert _tile_aqi(city[loc]) == hero.group(1), (
                loc, lang, _tile_aqi(city[loc]), hero.group(1))


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_live_station_is_never_tagged_as_something_we_lack(monkeypatch, lang):
    """A live tile carries no CACHED and no NO READING tag, in either language."""
    _live(monkeypatch)
    with TestClient(app) as c:
        rows = _rows(c.get("/city", params={**PERSONA, "lang": lang}).text)
    assert len(rows) == len(waqi.LOCALITIES)
    for loc, tile in rows.items():
        for key, english in (("tag_cached", "CACHED"),
                             ("tag_no_reading", "NO READING")):
            assert i18n.t(lang, "ui", key, english) not in tile, (lang, loc, tile)


def test_a_live_reading_outranks_a_stored_row(monkeypatch):
    """The live feed is the measurement; a stored row is a record of an older
    one. When both exist the tile must show the live figure -- otherwise the
    page can print a number from hours ago with no tag saying so."""
    from saafsaans.web import main as web_main
    _live(monkeypatch, only={"Rohini"})
    monkeypatch.setattr(web_main.metrics, "station_grid",
                        lambda client, locs: [{"station": "Rohini", "aqi": 999,
                                               "ts": "2026-07-21T00:00:00+00:00"}])
    monkeypatch.setattr(web_main, "get_client", lambda: object())
    with TestClient(app) as c:
        tile = _rows(c.get("/city", params=PERSONA).text)["Rohini"]
    live_expected = waqi._reading(PM25["Rohini"], PM25["Rohini"] * 1.6,
                                  station="Rohini", city="Delhi", stale=False,
                                  forecast=None, obs_time=None)["aqi"]
    assert _tile_aqi(tile) == str(live_expected), tile
    assert "999" not in tile


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_silent_feed_falls_back_to_the_last_stored_reading_with_its_age(
        monkeypatch, lang):
    """Owner decision C: show the last REAL reading and how old it is.

    Never a stand-in. The tile must carry the stored figure, the CACHED tag and
    an age -- and the age must be a real elapsed time, not the page clock.
    """
    from datetime import datetime, timedelta, timezone
    from saafsaans.web import main as web_main
    _live(monkeypatch, only=set())        # the feed answers for nobody
    nine_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    monkeypatch.setattr(web_main.metrics, "station_grid",
                        lambda client, locs: [{"station": "ITO", "aqi": 143,
                                               "ts": nine_hours_ago}])
    monkeypatch.setattr(web_main, "get_client", lambda: object())
    with TestClient(app) as c:
        rows = _rows(c.get("/city", params={**PERSONA, "lang": lang}).text)

    ito = rows["ITO"]
    assert _tile_aqi(ito) == "143", ito
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in ito, ito
    assert "9 " + i18n.t(lang, "ui", "age_unit_hours", "H") in ito, ito

    # And a station with neither a feed nor a stored row gets no number at all.
    rohini = rows["Rohini"]
    assert _tile_aqi(rohini) == "--", rohini
    assert i18n.t(lang, "ui", "tag_no_reading", "NO READING") in rohini, rohini


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_stale_tile_keeps_its_number_and_age_but_loses_its_band(monkeypatch, lang):
    """A stored reading is a fact about WHEN IT WAS TAKEN, so it keeps its
    number and gains its age -- and loses the band word and the severity colour,
    which state today's air. Saying "Severe" beside a nine-hour-old figure is
    the sample defect in a slower form.
    """
    from datetime import datetime, timedelta, timezone
    from saafsaans.services import normalize
    from saafsaans.web import main as web_main
    _live(monkeypatch, only=set())
    old = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    monkeypatch.setattr(web_main.metrics, "station_grid",
                        lambda client, locs: [{"station": "ITO", "aqi": 401,
                                               "ts": old}])
    monkeypatch.setattr(web_main, "get_client", lambda: object())
    with TestClient(app) as c:
        tile = _rows(c.get("/city", params={**PERSONA, "lang": lang}).text)["ITO"]

    assert _tile_aqi(tile) == "401", tile                    # the fact survives
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in tile
    for band in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"):
        assert i18n.t(lang, "band_label", band, band) not in tile, (lang, band)
    # ...and the colour, which says the same thing without words.
    assert "band-%s" % normalize.band_for(401)[3] not in tile, tile
    assert "band-%s" % normalize.band_for(None)[3] in tile, tile


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_live_tile_does_keep_its_band(monkeypatch, lang):
    """The mirror of the test above. Stripping the band everywhere would pass
    that one; the band must survive exactly where it is earned."""
    from saafsaans.services import normalize
    _live(monkeypatch)
    with TestClient(app) as c:
        rows = _rows(c.get("/city", params={**PERSONA, "lang": lang}).text)
    for loc, tile in rows.items():
        aqi = int(_tile_aqi(tile))
        band = normalize.band_for(aqi)
        assert i18n.t(lang, "band_label", band[0], band[0]) in tile, (lang, loc)
        assert "band-%s" % band[3] in tile, (lang, loc, tile)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_recent_stored_row_is_not_promoted_to_live(monkeypatch, lang):
    """The two pages must not disagree about whether a measurement exists.

    /city used to call a stored row "live" when it was under three hours old,
    and the home page had no such grace. So a row measured 2h50m ago rendered on
    /city as an untagged, undated tile with the band word and the severity
    colour ramp, while /?locality=<the same station> in the same minute said
    NO READING and printed nothing. The three-hour window is gone: live means
    the feed answered now.

    Deliberately a row TWO HOURS AND FIFTY MINUTES old -- inside the old
    freshness window. The existing coverage all used nine-hour rows, which is
    why this shipped.
    """
    from datetime import datetime, timedelta, timezone
    from saafsaans.services import normalize
    from saafsaans.web import main as web_main
    _live(monkeypatch, only=set())            # the feed answers for nobody
    recent = (datetime.now(timezone.utc) - timedelta(hours=2, minutes=50)).isoformat()
    monkeypatch.setattr(web_main.metrics, "station_grid",
                        lambda client, locs: [{"station": "ITO", "aqi": 401,
                                               "ts": recent}])
    monkeypatch.setattr(web_main, "get_client", lambda: object())
    with TestClient(app) as c:
        body = c.get("/city", params={**PERSONA, "lang": lang}).text
    tile = _rows(body)["ITO"]

    assert _tile_aqi(tile) == "401", tile                 # the fact survives
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in tile, tile
    for band in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"):
        assert i18n.t(lang, "band_label", band, band) not in tile, (lang, band, tile)
    assert "band-%s" % normalize.band_for(401)[3] not in tile, tile

    # ...and no median, because nothing is reporting now. One stored figure is
    # not the city's central tendency.
    sub = re.search(r'class="page-sub">([^<]*)<', body).group(1)
    assert "401" not in sub, sub


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_median_is_printed_when_stations_are_reporting(monkeypatch, lang):
    """The mirror. Suppressing the median unconditionally would pass the test
    above, and a page that never states the city's air is not the goal. When
    stations ARE reporting, the median is written and the sentence names how
    many stations it was taken across."""
    import statistics
    _live(monkeypatch)                        # every locality answers live
    with TestClient(app) as c:
        body = c.get("/city", params={**PERSONA, "lang": lang}).text
    sub = re.search(r'class="page-sub">([^<]*)<', body).group(1)
    aqis = sorted(int(_tile_aqi(t)) for t in _rows(body).values())
    expected = int(statistics.median(aqis))
    assert str(expected) in sub, (lang, expected, sub)
    assert str(len(waqi.LOCALITIES)) in sub, (lang, sub)
