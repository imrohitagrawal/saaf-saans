"""Presentation-layer tests: the copy and the geometry the design specifies."""
from saafsaans.web import presenters as p

PERSONA = {"age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise", "locality": "Anand Vihar"}


# --- Verdict ---------------------------------------------------------------
def test_verdict_covers_every_risk_band():
    from saafsaans.services import risk
    for band in risk.RISK_BANDS:
        assert p.verdict_for(band)


def test_verdict_falls_back_to_the_cautious_line():
    """An unknown band must never produce a reassuring headline."""
    assert p.verdict_for("nonsense") == p.verdict_for("High")


# --- Persona ---------------------------------------------------------------
def test_persona_kicker_matches_the_design():
    assert p.persona_kicker(PERSONA) == \
        "FOR AN ADULT WITH ASTHMA, PLANNING OUTDOOR EXERCISE"


def test_persona_kicker_omits_a_neutral_condition():
    fit = {**PERSONA, "condition": "Fit"}
    assert p.persona_kicker(fit) == "FOR AN ADULT, PLANNING OUTDOOR EXERCISE"


def test_persona_line_matches_the_design():
    assert p.persona_line(PERSONA) == "Adult · asthma · outdoor exercise · Anand Vihar"


# --- Comparison ------------------------------------------------------------
def test_comparison_line_explains_a_positive_gap():
    line = p.comparison_line(56, 44, PERSONA)
    assert "healthy adult" in line and "44" in line and "56" in line
    assert "your asthma + outdoor exercise" in line


def test_comparison_line_handles_equal_and_lower_scores():
    assert "that's you today" in p.comparison_line(44, 44, PERSONA)
    lower = p.comparison_line(38, 44, {**PERSONA, "activity": "Stay home"})
    assert "Good call" in lower and "38" in lower


def test_comparison_line_without_persona_factors_still_reads():
    plain = {"age": "Adult", "condition": "Fit", "activity": "Stay home"}
    assert p.comparison_line(50, 44, plain)


# --- Scale geometry --------------------------------------------------------
def test_scale_position_matches_the_designed_marker():
    """The design places AQI 191 at 38.2% across the six-segment bar."""
    assert p.scale_position(191) == 38.2


def test_scale_position_at_every_band_boundary():
    assert [p.scale_position(v) for v in (0, 50, 100, 200, 300, 400, 500)] == \
        [0.0, 10.0, 20.0, 40.0, 60.0, 80.0, 100.0]


def test_scale_position_clamps_and_survives_junk():
    assert p.scale_position(9999) == 100.0
    assert p.scale_position(-5) == 0.0
    assert p.scale_position(None) == 0.0
    assert p.scale_position("-") == 0.0


# --- City ------------------------------------------------------------------
def test_median_aqi_ignores_missing_readings():
    assert p.median_aqi([{"aqi": 204}, {"aqi": 191}, {"aqi": 143}, {"aqi": None}]) == 191
    assert p.median_aqi([{"aqi": 100}, {"aqi": 200}]) == 150
    assert p.median_aqi([]) == 0


def test_sparkline_renders_svg_and_declines_thin_data():
    svg = str(p.sparkline_svg([{"aqi": 100}, {"aqi": 150}, {"aqi": 120}]))
    assert svg.startswith("<svg") and "<polyline" in svg and "<circle" in svg
    assert 'role="img"' in svg and "aria-label" in svg
    # One point cannot make a line; the caller shows an empty state instead.
    assert str(p.sparkline_svg([{"aqi": 100}])) == ""
    assert str(p.sparkline_svg(None)) == ""


def test_sparkline_survives_a_flat_series():
    """Identical values must not divide by zero."""
    assert str(p.sparkline_svg([{"aqi": 120}] * 5)).startswith("<svg")


# --- Provenance ------------------------------------------------------------
def test_provenance_never_disguises_a_fallback_as_live():
    assert p.provenance_chip("ok", "2:00 PM") == "● LIVE · 2:00 PM"
    assert "CACHED" in p.provenance_chip("fallback", "2:00 PM")
    assert "cached sample" in p.grounding_note("fallback", "2:00 PM")
    assert "live reading" in p.grounding_note("ok", "2:00 PM")


def test_pct_guards_zero_and_junk():
    assert p.pct(5, 10) == "50.0%"
    assert p.pct(5, 0) == "0%"
    assert p.pct(None, 10) == "0%"
    assert p.pct(50, 10) == "100.0%"   # clamped


# --- Outlook ----------------------------------------------------------------
def test_outlook_rows_drop_past_days_and_label_today():
    """WAQI returns days already gone; the first row must always be today."""
    from datetime import date
    today = date(2026, 7, 19)
    rows = p.outlook_rows([
        {"date": "2026-07-17", "pm25_avg": 138},
        {"date": "2026-07-19", "pm25_avg": 146},
        {"date": "2026-07-20", "pm25_avg": 156},
    ], today=today)
    assert [r["label"] for r in rows] == ["Today", "Mon 20"]
    assert rows[0]["is_today"] is True and rows[1]["is_today"] is False


def test_outlook_rows_caps_at_five_and_survives_junk():
    from datetime import date
    many = [{"date": f"2026-07-{d}", "pm25_avg": 100} for d in range(19, 30)]
    assert len(p.outlook_rows(many, today=date(2026, 7, 19))) == 5
    assert p.outlook_rows([{"date": "not-a-date", "pm25_avg": 1}]) == []
    assert p.outlook_rows(None) == []
