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
    assert first["pm25_avg"] == 55
    assert first["pm25_max"] == 95
    assert set(first) == {"date", "pm25_avg", "pm25_max", "category"}


def test_daily_outlook_categories_and_sort():
    rows = forecast.daily_outlook(SAMPLE_FORECAST)
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-07-18"]["category"] == "Moderate"   # 55 µg/m3
    assert by_date["2026-07-19"]["category"] == "Very Poor"  # 130 µg/m3
    assert by_date["2026-07-20"]["category"] == "Good"       # 25 µg/m3
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
