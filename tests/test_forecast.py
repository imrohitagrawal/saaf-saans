"""Forecast helpers: daily_outlook parsing + best_window diurnal heuristic."""
from saafsaans.services import forecast


SAMPLE_FORECAST = {
    "daily": {
        "pm25": [
            {"day": "2026-07-18", "avg": 55, "min": 20, "max": 95},
            {"day": "2026-07-19", "avg": 130, "min": 80, "max": 260},
            {"day": "2026-07-20", "avg": 25, "min": 10, "max": 40},
        ],
        "pm10": [{"day": "2026-07-18", "avg": 120, "min": 60, "max": 200}],
    }
}


def test_daily_outlook_parses_rows():
    rows = forecast.daily_outlook(SAMPLE_FORECAST)
    assert len(rows) == 3
    first = rows[0]
    assert first["date"] == "2026-07-18"
    # 55 in the feed is a US EPA sub-index, not micrograms: it inverts to
    # 14.3 µg/m3. Reading it as a concentration overstated the day by 4x.
    assert first["pm25_avg"] == 14
    assert first["pm25_max"] == 33
    assert set(first) == {"date", "pm25_avg", "pm25_max", "category"}


def test_daily_outlook_categories_and_sort():
    rows = forecast.daily_outlook(SAMPLE_FORECAST)
    by_date = {r["date"]: r for r in rows}
    # Bands now apply to real concentrations. The sub-indices 55/130/25 invert
    # to about 14 / 47 / 6 µg/m3, which is a materially calmer -- and correct --
    # picture than the old reading of those same numbers as micrograms.
    assert by_date["2026-07-18"]["category"] == "Good"        # ~14 µg/m3
    assert by_date["2026-07-19"]["category"] == "Satisfactory"  # ~47 µg/m3
    assert by_date["2026-07-20"]["category"] == "Good"        # ~6 µg/m3
    # sorted ascending by date
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)


def test_daily_outlook_empty_and_none():
    assert forecast.daily_outlook(None) == []
    assert forecast.daily_outlook({}) == []
    assert forecast.daily_outlook({"daily": {}}) == []
    assert forecast.daily_outlook({"daily": {"pm25": []}}) == []
    assert forecast.daily_outlook("not a dict") == []


def test_daily_outlook_skips_malformed_rows():
    bad = {"daily": {"pm25": [
        {"day": "2026-07-18", "avg": "x", "max": 10},   # non-numeric avg
        {"avg": 10, "max": 10},                          # no day
        {"day": "2026-07-19", "avg": 40, "max": 80},     # good
    ]}}
    rows = forecast.daily_outlook(bad)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-19"


def test_best_window_shape_for_all_severities():
    for aqi in (80, 250, 380):
        win = forecast.best_window(aqi)
        assert set(win) == {"window", "rationale"}
        assert isinstance(win["window"], str) and win["window"]
        assert isinstance(win["rationale"], str) and win["rationale"]


def test_best_window_high_aqi_says_no_safe_window():
    win = forecast.best_window(380)
    assert "no safe outdoor window" in win["window"].lower()


def test_best_window_works_without_forecast():
    win = forecast.best_window(80, forecast=None)
    assert win["window"]
    assert "pattern" in win["rationale"].lower()


def test_best_window_varies_by_dominant_pollutant():
    ozone = forecast.best_window(180, dominant_pollutant="o3")
    traffic = forecast.best_window(180, dominant_pollutant="no2")
    particulate = forecast.best_window(180, dominant_pollutant="pm25")
    # Ozone -> morning; traffic -> midday; the three differ from each other.
    assert "morning" in ozone["window"].lower()
    assert "midday" in traffic["window"].lower()
    windows = {ozone["window"], traffic["window"], particulate["window"]}
    assert len(windows) == 3
    # Rationale explains the pollutant driver in plain terms.
    assert "ozone" in ozone["rationale"].lower()
    assert "traffic" in traffic["rationale"].lower()


def test_best_window_high_aqi_overrides_pollutant():
    for pol in ("o3", "no2", "pm25"):
        win = forecast.best_window(380, dominant_pollutant=pol)
        assert "no safe outdoor window" in win["window"].lower()


# --- Language --------------------------------------------------------------
# The window is the site's "if you must go out" answer, so it has to be
# readable by the person the page is written for.

import re

import pytest

from saafsaans.services import i18n

LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’.\-]{2,}")


def _stub_hindi(monkeypatch, *groups):
    """Answer every lookup in whole groups with a Devanagari marker.

    Phase 1 writes no Hindi. The marker proves the sentence is routed through
    ``i18n.t``; a sentence typed inline stays English and this test names it.
    """
    real = i18n.t

    def fake(lang, group, key, english):
        return "अनुवादित" if lang == "hi" and group in groups else real(
            lang, group, key, english)

    monkeypatch.setattr(i18n, "t", fake)


@pytest.mark.parametrize("aqi,dominant", [
    (350, "pm25"),   # no safe window
    (250, "pm25"),   # Poor tail
    (150, "o3"),     # ozone clause + Moderate tail
    (150, "no2"),    # traffic-gas clause
    (60, "pm10"),    # no severity tail
])
def test_the_window_leaves_no_english_sentence_in_hindi(monkeypatch, aqi, dominant):
    _stub_hindi(monkeypatch, "window")
    w = forecast.best_window(aqi, dominant_pollutant=dominant, lang="hi")
    stray = LATIN_RUN.findall(w["window"] + " " + w["rationale"])
    assert not stray, f"still written in English: {sorted(set(stray))}"


@pytest.mark.parametrize("aqi,dominant", [(350, "pm25"), (250, "o3"), (60, "no2")])
def test_the_window_is_unchanged_english_by_default(aqi, dominant):
    assert forecast.best_window(aqi, dominant_pollutant=dominant) == \
        forecast.best_window(aqi, dominant_pollutant=dominant, lang="en")


def test_the_rationale_sentences_are_joined_with_one_space():
    """The tail used to be concatenated onto the clause. Assembling it from
    separately translated sentences must not change the English spacing."""
    r = forecast.best_window(250, dominant_pollutant="o3")["rationale"]
    assert "  " not in r
    assert r.endswith("wear an N95.")
    assert "This is a general pattern, not an hourly station forecast." in r


def test_the_outlook_category_uses_the_shared_band_words():
    """The forecast band and the live reading band are the same seven words, so
    they come from one group -- a second copy could drift from what the reading
    card says today's air is called."""
    rows = forecast.daily_outlook(SAMPLE_FORECAST, lang="hi")
    assert [r["category"] for r in rows] == [
        i18n.HI["band_label"][label]
        for label in (r["category"] for r in forecast.daily_outlook(SAMPLE_FORECAST))
    ]


def test_the_outlook_is_unchanged_english_by_default():
    assert forecast.daily_outlook(SAMPLE_FORECAST) == \
        forecast.daily_outlook(SAMPLE_FORECAST, lang="en")


def test_the_hindi_window_says_which_half_of_the_day():
    """English suffixes AM/PM; Hindi marks the time of day before the number.
    Dropping the marker left "क़रीब 11 से 3 बजे" readable as 11pm to 3am -- an
    ambiguity in the single line that tells somebody when it is safer to go
    outside."""
    from saafsaans.services import i18n
    marks = ("सुबह", "दोपहर", "शाम", "रात")
    for key in ("o3", "no2", "winter", "default"):
        value = i18n.HI["window"][key]
        assert any(m in value for m in marks), (key, value)
        # ...and the marker has to be inside the bracket with the clock times,
        # not only in the label before it.
        bracket = value[value.index("(") + 1:value.index(")")]
        assert any(m in bracket for m in marks), (key, bracket)


def test_the_season_is_decided_in_india_not_on_the_server(monkeypatch):
    """best_window called date.today() for the month, so on the UTC container
    the season changed 5.5 hours late at every boundary -- including the one
    into November, when Delhi's air turns and this advice matters most.

    Frozen at 20:00 UTC on 31 October, which is already 01:30 on 1 November in
    Delhi: the winter rationale must be the one a Delhi reader gets.
    """
    from datetime import datetime

    from saafsaans.services import clock, forecast

    seen = {}
    monkeypatch.setattr(forecast, "_is_winter",
                        lambda month: seen.setdefault("month", month) and False)
    monkeypatch.setattr(clock, "now_ist",
                        lambda: datetime(2026, 11, 1, 1, 30, tzinfo=clock.IST))
    forecast.best_window(180, "pm25", "en")

    assert seen["month"] == 11, (
        f"the season was decided from month {seen['month']}, not India's 11")
