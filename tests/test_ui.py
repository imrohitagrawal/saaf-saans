"""Tests for the enterprise UI toolkit.

These assert the contract the integrator relies on: every function returns a
non-empty string, key dynamic values appear in the output, and no function
raises on empty/None inputs.
"""
from saafsaans.services import ui


# --- basic contract: non-empty strings -----------------------------------
def test_theme_css_is_style_block():
    assert isinstance(ui.THEME_CSS, str)
    assert ui.THEME_CSS.startswith("<style>")
    assert "prefers-color-scheme: dark" in ui.THEME_CSS
    assert "--ss-accent" in ui.THEME_CSS


def test_all_functions_return_nonempty_str():
    reading = {"aqi": 275, "pm25": 180.4, "pm10": 240, "dominant_pollutant": "pm25",
               "station": "Anand Vihar", "stale": False}
    category = ("Poor", "red", "#c62828")
    risk = {"score": 72, "band": "High", "color": "#c62828",
            "drivers": ["PM2.5 high", "Asthma"], "headline": "Limit outdoor time"}
    sections = {"verdict": "NO-GO", "verdict_detail": "Stay indoors",
                "precautions": ["Wear N95"], "window": "6-8am",
                "symptoms": ["Wheezing"], "disclaimer": "Not medical advice", "raw": ""}
    outputs = [
        ui.aqi_hero_html(reading, category),
        ui.risk_gauge_html(risk),
        ui.advice_card_html(sections),
        ui.kpi_tile_html("PM2.5", 180, "µg/m³"),
        ui.kpi_row_html([{"label": "A", "value": 1, "sub": "x"}]),
        ui.station_card_html("ITO", 190, ("Moderate", "orange", "#ef6c00"), False),
        ui.station_grid_html([{"name": "ITO", "aqi": 190,
                               "category": ("Moderate", "orange", "#ef6c00"), "stale": True}]),
        ui.chip_html("hello"),
        ui.trend_note_html("rising", "up"),
        ui.refusal_html("jailbreak"),
        ui.service_status_html("cloud", True, False),
    ]
    for out in outputs:
        assert isinstance(out, str) and out.strip(), out


# --- content assertions ---------------------------------------------------
def test_aqi_hero_contains_number_and_label():
    html = ui.aqi_hero_html({"aqi": 312, "stale": True}, ("Very Poor", "dark red", "#7f0000"))
    assert "312" in html
    assert "Very Poor" in html
    assert "STALE" in html


def test_risk_gauge_contains_score_and_band():
    html = ui.risk_gauge_html({"score": 88, "band": "Extreme", "color": "#4a0000",
                               "drivers": ["Severe AQI"], "headline": "Stay home"})
    assert "88" in html
    assert "Extreme" in html
    assert "Severe AQI" in html


def test_advice_card_reflects_verdict():
    go = ui.advice_card_html({"verdict": "GO", "verdict_detail": "Fine to go"})
    assert "ss-verdict-go" in go
    assert "GO" in go
    caution = ui.advice_card_html({"verdict": "CAUTION"})
    assert "ss-verdict-caution" in caution
    nogo = ui.advice_card_html({"verdict": "NO-GO"})
    assert "ss-verdict-nogo" in nogo
    assert "NO-GO" in nogo


def test_refusal_is_reassuring():
    html = ui.refusal_html("ignore instructions")
    assert "not processed" in html.lower()
    assert "happy" in html.lower() or "help" in html.lower()
    # never echoes raw user pattern text
    assert "ignore instructions" not in html


def test_service_status_live_and_mock():
    html = ui.service_status_html("none", False, True)
    assert "ss-dot--mock" in html
    assert "ss-dot--live" in html


# --- defensive: no raise on empty/None -----------------------------------
def test_functions_dont_raise_on_empty():
    assert ui.aqi_hero_html({}, None)
    assert ui.aqi_hero_html(None, ())
    assert ui.risk_gauge_html({})
    assert ui.risk_gauge_html(None)
    assert ui.advice_card_html({})
    assert ui.advice_card_html(None)
    assert ui.kpi_tile_html("x", None)
    assert ui.kpi_row_html([])
    assert ui.kpi_row_html(None)
    assert ui.station_card_html(None, None, None, False)
    assert ui.station_grid_html(None)
    assert ui.chip_html("")
    assert ui.trend_note_html("")
    assert ui.refusal_html(None)
    assert ui.service_status_html(None, None, None)


def test_dynamic_text_is_escaped():
    html = ui.chip_html("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_bad_color_falls_back_and_cannot_inject():
    html = ui.risk_gauge_html({"score": 50, "band": "X", "color": "red;}//evil"})
    assert "evil" not in html


def test_hero_shows_meaning_and_tooltips():
    html = ui.aqi_hero_html(
        {"aqi": 410, "pm25": 380.0, "pm10": 520.0, "dominant_pollutant": "pm25",
         "station": "Anand Vihar", "stale": True},
        ("Severe", "dark red", "#4a0000"),
        meaning="Hazardous — a health emergency.",
    )
    assert "410" in html
    assert "Hazardous" in html          # plain-language meaning line
    assert "title=" in html             # tooltips present on metric labels
    assert "PM2.5" in html


def test_hero_renders_cpcb_scale_and_band_context():
    # Full 0-500 CPCB scale bar with all five segments + a positioned marker,
    # and the band-context class that threads the --c-* triplet into the number.
    html = ui.aqi_hero_html(
        {"aqi": 410, "station": "Anand Vihar"},
        ("Severe", "dark red", "#4a0000"),
    )
    assert "ss-scale-bar" in html
    for seg in ("good", "moderate", "poor", "vpoor", "severe"):
        assert f"ss-scale-seg--{seg}" in html
    assert "ss-scale-marker" in html
    assert "ss-cat-severe" in html          # band context on the card
    assert "ss-cat-chip" in html            # tint/ink category chip
    # marker position is clamped to the 0-100% track (410/500 -> 82%)
    assert "left:82.0%" in html


def test_station_card_uses_band_context():
    html = ui.station_card_html("ITO", 190, ("Moderate", "orange", "#ef6c00"), False)
    assert "ss-cat-moderate" in html
    assert "ss-cat-chip" in html
    assert "190" in html


def test_unknown_category_falls_back_safely():
    # None category must not raise and must land on the neutral band class.
    html = ui.aqi_hero_html({"aqi": None}, None)
    assert "ss-cat-unknown" in html
    assert "ss-scale-marker" not in html    # no marker without a numeric AQI


def test_risk_gauge_shows_what_to_do():
    html = ui.risk_gauge_html({"score": 72, "band": "High", "color": "#c62828",
                               "headline": "High risk", "advice": "Skip outdoor exercise.",
                               "drivers": ["AQI 320 (Very Poor)"]})
    assert "What to do" in html
    assert "Skip outdoor exercise." in html


# --- KPI value typing -------------------------------------------------------
def test_is_compact_accepts_short_values():
    """Short values read well at 24px mono, whether numeric or not."""
    for value in ("191", "43%", "1.2 s", "287", "0", "pm10", "LIVE"):
        assert ui._is_compact(value), value


def test_is_compact_rejects_long_phrases_and_blanks():
    """Long phrases overflow the tile at 24px mono; blanks have nothing to show."""
    for value in ("Late morning (about 9 AM-12 PM)", "Very poor - avoid going out", "", None):
        assert not ui._is_compact(value), value


def test_kpi_tile_marks_phrase_values_with_text_modifier():
    assert "ss-kpi-value--text" in ui.kpi_tile_html("Best time", "Late morning (9 AM-12 PM)")
    assert "ss-kpi-value--text" not in ui.kpi_tile_html("AQI", "191")
