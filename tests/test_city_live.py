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
import html
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, normalize, waqi
from saafsaans.web.main import app

# All four fields: persona_applied requires the full set, and these pages are
# meant to be the ones an applied-persona reader sees, not the first-visit
# example state.
PERSONA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
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


def test_a_raising_feed_does_not_500_the_page(monkeypatch):
    """`_live_grid`'s comment asserted "get_aqi never raises by contract", and
    the contract was not enforced: `_fetch_uncached` wraps neither
    `config.waqi_token()` nor `_corroborates`, so a raise in either became a 500
    on /city rather than the ("fallback", no numbers) the comment promises. A
    page whose whole job is to degrade honestly must not be the page that dies.
    """
    def boom(locality, es_client=None):
        raise RuntimeError("upstream exploded")
    monkeypatch.setattr(waqi, "get_aqi", boom)
    with TestClient(app) as c:
        r = c.get("/city", params=PERSONA)
    assert r.status_code == 200
    rows = _rows(r.text)
    assert len(rows) == len(waqi.LOCALITIES)
    for loc, tile in rows.items():
        assert _tile_aqi(tile) == "--", (loc, tile)
        assert i18n.t("en", "ui", "tag_no_reading", "NO READING") in tile, loc


def test_a_hanging_feed_does_not_hold_the_page_for_every_locality(monkeypatch):
    """The sweep has a wall-clock budget, so a dead upstream costs one timeout
    for the page rather than ceil(21/8) stacked ones on a scale-to-zero machine.

    The feed here never returns. Without the budget this call blocks until all
    21 threads finish; with it the page renders inside the budget and says, for
    every station, exactly what is true: no reading.
    """
    import threading
    import time as _time
    from saafsaans.web import main as web_main

    release = threading.Event()
    monkeypatch.setattr(web_main, "_CITY_FETCH_BUDGET", 0.3)
    monkeypatch.setattr(waqi, "get_aqi",
                        lambda loc, es_client=None: (release.wait(30), None)[1]
                        or (waqi._fallback(loc), "fallback"))
    try:
        with TestClient(app) as c:
            start = _time.monotonic()
            r = c.get("/city", params=PERSONA)
            elapsed = _time.monotonic() - start
    finally:
        release.set()

    assert r.status_code == 200
    assert elapsed < 5, elapsed
    rows = _rows(r.text)
    for loc, tile in rows.items():
        assert _tile_aqi(tile) == "--", (loc, tile)


# ------------------------------------------------------- a held CPCB reading
#
# cpcb keeps the last good payload through a transient upstream failure rather
# than blanking a city. The numbers are real, but they are not "now", and the
# tile has to say so: a held reading is tagged and dated exactly as a stored
# one, and earns no band word and no severity colour.
def _held(monkeypatch, locality, *, retained=True):
    """Stub the feed so ``locality`` answers with a held (or live) reading."""
    obs = "2026-07-21T10:00:00+05:30"

    def get_aqi(loc, es_client=None):
        if loc != locality:
            return waqi._fallback(loc), "fallback"
        reading = waqi._reading(PM25[loc], PM25[loc] * 1.6, station=loc,
                                city="Delhi", stale=False, forecast=None,
                                obs_time=obs, retained=retained)
        return reading, "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)
    return obs


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_carries_its_own_number_and_its_own_age(monkeypatch, lang):
    """Number, tag, age, and no band word -- all four, because three of them
    are also true of a NO READING tile. Only the number tells them apart."""
    from saafsaans.web import main as web_main
    obs = _held(monkeypatch, "Rohini")
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    tile = _rows(body)["Rohini"]

    reading = waqi._reading(PM25["Rohini"], PM25["Rohini"] * 1.6,
                            station="Rohini", city="Delhi", stale=False,
                            forecast=None, obs_time=obs, retained=True)
    assert _tile_aqi(tile) == str(reading["aqi"]), tile
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in tile
    # The age is derived from the READING's own observation time, never from an
    # Elasticsearch row belonging to some other measurement.
    assert web_main._age_label(obs, lang) in tile
    band = normalize.band_for(reading["aqi"])[0]
    assert i18n.t(lang, "band_label", band, band) not in tile
    unknown = normalize.band_for(None)[3]
    assert f'class="station band-{unknown}"' in tile


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_when_it_is_not_held_is_live_and_banded(monkeypatch, lang):
    """The mirror. Same numbers, same station, ``retained`` False."""
    _held(monkeypatch, "Rohini", retained=False)
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    tile = _rows(body)["Rohini"]
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") not in tile
    unknown = normalize.band_for(None)[3]
    assert f'class="station band-{unknown}"' not in tile
    assert _tile_aqi(tile) not in (None, "--")


# The threshold the legend used to promise.  Pinned per language because it is
# a CLAIM, not a spelling: the legend defined CACHED as "older than three
# hours" while the page tags readings that can be minutes old.
_THREE_HOURS = {"en": "three hours", "hi": "तीन घंटे"}


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_cached_legend_matches_when_the_tag_is_actually_shown(monkeypatch, lang):
    """A held reading five minutes old is tagged CACHED, so the legend must not
    tell the reader the tag means older than three hours."""
    from datetime import datetime, timedelta, timezone
    from saafsaans.web import main as web_main

    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    def get_aqi(loc, es_client=None):
        if loc != "Rohini":
            return waqi._fallback(loc), "fallback"
        return waqi._reading(PM25[loc], PM25[loc] * 1.6, station=loc, city="Delhi",
                             stale=False, forecast=None, obs_time=recent,
                             retained=True), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    monkeypatch.setattr(web_main, "waqi", waqi)
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text

    tile = _rows(body)["Rohini"]
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in tile
    assert web_main._age_label(recent, lang) in tile, "a five-minute-old tag"
    # Read off the RENDERED page rather than out of the corpus: an English
    # default read back through i18n.t with an empty fallback returns "", and
    # every absence assertion below it would pass on nothing.
    legend = html.unescape(re.search(
        r'<p class="caption">(.*?)</p>', body, re.S).group(1))
    assert i18n.t(lang, "ui", "tag_cached", "CACHED") in legend, (
        "this is not the tag legend")
    assert _THREE_HOURS[lang] not in legend, (
        "the legend states a three-hour threshold the page does not apply")


# ------------------------------------- one particulate is not two particulates
#
# The grid sorts worst-first and so invites the reader to compare tiles against
# each other. A CPCB index can be produced from a single particulate -- measured:
# Wazirpur's PM2.5 instrument was down and its 119 came from PM10 alone -- and
# that figure is not comparable with a neighbour's 119 from two. The Today page
# says so beside the reading; the tile showed a bare number.
def _mixed(monkeypatch, single):
    """Every locality reports both particulates except those in ``single``,
    which report PM10 only."""
    def get_aqi(locality, es_client=None):
        pm25 = None if locality in single else PM25[locality]
        reading = waqi._reading(pm25, 180.0, station=locality, city="Delhi",
                                stale=False, forecast=None,
                                obs_time="2026-07-21T10:00:00+05:30",
                                source="cpcb")
        return reading, "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_single_particulate_tile_is_marked_and_the_others_are_not(monkeypatch, lang):
    """Both directions in one render, so "mark everything" and "mark nothing"
    are both failures rather than one of them being a pass."""
    single = {"Wazirpur", "ITO"}
    _mixed(monkeypatch, single)
    with TestClient(app) as client:
        rows = _rows(client.get("/city", params={**PERSONA, "lang": lang}).text)

    tag = i18n.t(lang, "ui", "tag_partial", "PART")
    marked = {loc for loc, markup in rows.items() if tag in markup}
    assert marked == single, (lang, marked)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_partial_tag_explains_itself_in_the_legend(monkeypatch, lang):
    """A tag word with no legend entry is a code, not an explanation -- and the
    legend is the one place this page defines its own vocabulary."""
    _mixed(monkeypatch, {"Wazirpur"})
    with TestClient(app) as client:
        body = html.unescape(client.get("/city", params={**PERSONA, "lang": lang}).text)
    assert i18n.t(lang, "ui", "tag_partial", "PART") in body
    assert i18n.t(lang, "ui", "tag_partial_legend",
                  "PART means that station measured only part of what goes into "
                  "the number, so its figure is not directly comparable with the "
                  "others. Open the station to see what it did measure.") in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_partial_tag_carries_its_definition_at_the_row(monkeypatch, lang):
    """Same device as the cached/no-reading tags: the definition rides on the
    tag itself in `title`, so the reader is not sent back up to the legend
    from the row where the tag is met."""
    _mixed(monkeypatch, {"Wazirpur"})
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    rows = _rows(body)
    part_def = i18n.t(lang, "ui", "tag_partial_def",
                      "Worked out from only part of what goes into the number, "
                      "so not directly comparable with the other stations.")
    assert f'title="{part_def}"' in rows["Wazirpur"], rows["Wazirpur"]
    # The screen-reader half, and its partner: the id being described must
    # exist, or the description dangles.
    assert 'aria-describedby="tag-def-partial"' in rows["Wazirpur"], rows["Wazirpur"]
    assert 'id="tag-def-partial"' in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_an_empty_trend_reconciles_the_number_in_its_header(monkeypatch, lang):
    """Observed live at AQI 341: the trend header stated a figure two lines
    above "No readings stored yet", and reconciling the two -- one current
    reading against a stored history that does not exist -- was left to the
    reader. Both directions: the caveat renders when a number sits over the
    empty state, and must NOT render when there is no number to reconcile.
    Removing the caveat in city.html fails the first half; rendering it
    unconditionally fails the second."""
    note = i18n.t(lang, "ui", "no_trend_number_note",
                  "The figure in the header is the latest single reading we "
                  "can show; this curve is drawn only from stored history, so "
                  "a number can sit above an empty chart until that history "
                  "builds.")
    empty = i18n.t(lang, "ui", "no_trend_before", "No readings stored for")

    _live(monkeypatch)                # the feed answers; the index holds nothing
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    assert empty in body, (lang, "no empty state, so this proves nothing")
    assert note in body, (lang, "a header figure over the empty state is unreconciled")

    _live(monkeypatch, only=set())    # nothing answers: no figure in the header
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    assert empty in body, (lang, "no empty state, so this proves nothing")
    assert note not in body, (lang, "the reconciliation renders with nothing to reconcile")


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_tile_marker_never_names_a_particulate(monkeypatch, lang):
    """Hard rule: PM2.5 and PM10 belong in the Guide, the System views and the
    provenance panel. This grid is none of those, so the marker says what the
    reader can act on without naming an instrument."""
    _mixed(monkeypatch, {"Wazirpur"})
    with TestClient(app) as client:
        body = client.get("/city", params={**PERSONA, "lang": lang}).text
    grid = body[body.find('class="station-list"'):]
    grid = grid[:grid.rfind("</a>")]
    for token in ("PM2.5", "PM10", "µg/m", "ug/m"):
        assert token not in grid, (lang, token)


def test_a_tile_with_both_particulates_is_never_marked(monkeypatch):
    """The mirror at the unit level: _partial is about ONE of two, not about
    anything being absent. A reading with neither has no index and never
    reaches a tile."""
    from saafsaans.web.main import _partial

    both = waqi._reading(80.0, 160.0, station="ITO", city="Delhi", stale=False,
                         forecast=None, obs_time=None)
    only25 = waqi._reading(80.0, None, station="ITO", city="Delhi", stale=False,
                           forecast=None, obs_time=None)
    only10 = waqi._reading(None, 160.0, station="ITO", city="Delhi", stale=False,
                           forecast=None, obs_time=None)
    neither = waqi._reading(None, None, station="ITO", city="Delhi", stale=False,
                            forecast=None, obs_time=None)
    assert _partial(both) is False
    assert _partial(only25) is True
    assert _partial(only10) is True
    assert neither["aqi"] is None and _partial(neither) is False
    assert _partial(None) is False


def test_the_city_fetch_pool_is_shared_by_the_whole_process(monkeypatch):
    """One pool, not one per request.

    _live_grid built a ThreadPoolExecutor per call and shut it down with
    wait=False, which does not cancel queued work. The invariant only shows up
    under a SLOW upstream, and that is deliberate in this test: with fast tasks
    the workers finish, the per-request executor is garbage collected and its
    threads are joined, so both spellings measure the same 7 threads. Under a
    slow one the eight workers are still occupied when the budget expires and the
    response goes out, so N concurrent renders held 8N threads -- each with its
    own TLS session -- on a 256MB machine. /city is not rate-limited, on the
    reasoning that the 600s memo caps upstream CALLS; it does, and calls were
    never the resource that ran out first.

    Asserted as thread-count growth rather than as the pool object's identity, so
    a rewrite that keeps the property passes however it spells it.
    """
    import threading
    import time as _time

    from saafsaans.web import main as web_main

    release = threading.Event()

    def slow(loc, es_client=None):
        release.wait(10)
        return {"aqi": None}, "fallback"

    monkeypatch.setattr(web_main.waqi, "get_aqi", slow)
    monkeypatch.setattr(web_main, "_CITY_FETCH_BUDGET", 0.05)

    try:
        before = threading.active_count()
        for _ in range(4):
            web_main._live_grid(None)      # each returns on the budget, workers stuck
        peak = threading.active_count()
    finally:
        release.set()
        _time.sleep(0.2)

    # Four renders against a hung upstream. A shared pool is capped at eight
    # workers however many renders pile up; a per-request pool adds a fresh eight
    # each time, so the count climbs past any fixed bound.
    assert peak - before <= web_main._CITY_FETCH_WORKERS, (before, peak)


def _grid_with(monkeypatch, *, silent):
    """Render /city where the first ``silent`` localities report nothing."""
    from saafsaans.services import waqi as w
    from saafsaans.web import main as web_main

    quiet = set(list(w.LOCALITIES)[:silent])

    def feed(loc, es_client=None):
        if loc in quiet:
            return w._fallback(loc), "fallback"
        return w._reading(60.0, 90.0, station=loc, city="Delhi", stale=False,
                          forecast=None, obs_time=None, retained=False,
                          source="cpcb"), "ok"

    monkeypatch.setattr(w, "get_aqi", feed)
    monkeypatch.setattr(web_main, "waqi", w)
    with TestClient(web_main.app) as client:
        return client.get("/city", params={"lang": "en"}).text


def test_the_band_column_collapses_only_when_no_station_has_a_band(monkeypatch):
    """The band cell is a fixed 76px column so the numbers line up down the list,
    and `.station .nm` is `flex: 1`, so a per-tile collapse moves that tile's
    number 76px right of its neighbours.

    `.station .bd:empty { width: 0 }` did exactly that. It was written for the
    no-source configuration where 21 of 21 tiles are empty and the column is dead
    weight -- and it was correct there. The moment a real CPCB key was deployed
    the mixed case appeared: 19 stations reporting, 2 not, and two numbers
    visibly out of column on the live site. A ragged list is a worse defect than
    a dead column, and no test saw it because every fixture until now made all
    the tiles agree.

    Asserted on the class the stylesheet keys off, in BOTH directions -- an
    always-on or always-off rule fails one of them.
    """
    mixed = _grid_with(monkeypatch, silent=2)
    assert 'class="bd"></span>' in mixed, (
        "no empty band cell in the fixture, so this proves nothing")
    assert "station-list no-bands" not in mixed, (
        "the band column collapsed while 19 stations still had a band word")

    nothing = _grid_with(monkeypatch, silent=len(waqi.LOCALITIES))
    assert "station-list no-bands" in nothing, (
        "the column stayed 76px wide with nothing in it")


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_the_trend_header_dates_its_figure_the_same_way_the_tile_does(monkeypatch, lang):
    """One page must not say two things about one number.

    The header printed `LAST 24 H · AQI 312` bare while the tile ten lines below
    dated that identical 312 as `CACHED · 13 H OLD`. `selected_aqi` is read out of
    the tile's own row, so it is the same figure -- a reader comparing them had no
    way to know that, and the undated one looks current.

    Both directions asserted: the tag appears on a held reading and is ABSENT on
    a live one, so a header that always tagged itself would fail too.
    """
    from saafsaans.services import i18n as i18n_mod
    from saafsaans.web import main as web_main

    def feed(retained):
        def f(loc, es_client=None):
            return waqi._reading(190.0, 300.0, station=loc, city="Delhi",
                                 stale=False, forecast=None, obs_time=None,
                                 retained=retained, source="cpcb"), "ok"
        return f

    cached = i18n_mod.t(lang, "ui", "tag_cached", "CACHED")

    def header(retained):
        monkeypatch.setattr(waqi, "get_aqi", feed(retained))
        monkeypatch.setattr(web_main, "waqi", waqi)
        with TestClient(web_main.app) as client:
            body = client.get("/city", params={"lang": lang}).text
        found = re.search(r'class="row trend-head">(.*?)</div>', body, re.S)
        assert found, (lang, "the trend header did not render")
        return re.sub(r"<[^>]+>", " ", found.group(1))

    assert cached in header(retained=True), (
        lang, "a held figure is undated in the trend header")
    assert cached not in header(retained=False), (
        lang, "a live figure is tagged as cached in the trend header")
