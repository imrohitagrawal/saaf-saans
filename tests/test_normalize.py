from saafsaans.services import normalize


def test_condition_map():
    assert normalize.norm_condition("Fit") == "any"
    assert normalize.norm_condition("None") == "any"  # back-compat
    assert normalize.norm_condition("Asthma") == "asthma"
    assert normalize.norm_condition("Heart condition") == "heart"
    assert normalize.norm_condition("Pregnancy") == "pregnancy"
    assert normalize.norm_condition("COPD") == "copd"
    assert normalize.norm_condition("Unknown") == "any"  # safe default


def test_activity_map():
    assert normalize.norm_activity("Outdoor exercise") == "outdoor_exercise"
    assert normalize.norm_activity("Commute") == "commute"
    assert normalize.norm_activity("School run") == "school_run"
    assert normalize.norm_activity("Stay home") == "stay_home"
    assert normalize.norm_activity("???") == "any"


def test_age_map():
    assert normalize.norm_age("Child") == "child"
    assert normalize.norm_age("Adult") == "adult"
    assert normalize.norm_age("Senior") == "senior"
    assert normalize.norm_age("???") == "any"


def test_aqi_category_buckets():
    """All six official CPCB bands, at both edges of each."""
    assert normalize.aqi_category(0)[0] == "Good"
    assert normalize.aqi_category(50)[0] == "Good"
    # 51-100 is CPCB "Satisfactory", a distinct band -- not part of "Good".
    assert normalize.aqi_category(51)[0] == "Satisfactory"
    assert normalize.aqi_category(100)[0] == "Satisfactory"
    assert normalize.aqi_category(101)[0] == "Moderate"
    assert normalize.aqi_category(200)[0] == "Moderate"
    assert normalize.aqi_category(201)[0] == "Poor"
    assert normalize.aqi_category(300)[0] == "Poor"
    assert normalize.aqi_category(301)[0] == "Very Poor"
    assert normalize.aqi_category(400)[0] == "Very Poor"
    assert normalize.aqi_category(401)[0] == "Severe"
    assert normalize.aqi_category(999)[0] == "Severe"


def test_aqi_category_defensive():
    assert normalize.aqi_category(None)[0] == "Unknown"
    assert normalize.aqi_category("-")[0] == "Unknown"
    assert normalize.aqi_category(-5)[0] == "Good"  # clamped for color


def test_band_slug_maps_every_band_to_a_css_token():
    """Templates colour by slug, so every band needs a distinct g1-g6 token."""
    slugs = [normalize.band_slug(v) for v in (25, 75, 150, 250, 350, 450)]
    assert slugs == ["g1", "g2", "g3", "g4", "g5", "g6"]
    assert normalize.band_slug(None) == "gx"


def test_aqi_meaning_covers_every_category():
    for label in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor",
                  "Severe", "Unknown"):
        assert label in normalize.AQI_MEANING
        assert normalize.aqi_meaning(label)
    # unknown label falls back rather than raising
    assert normalize.aqi_meaning("bogus") == normalize.AQI_MEANING["Unknown"]


def test_glossary_has_core_terms():
    for term in ("AQI", "PM2.5", "PM10", "Dominant pollutant", "Risk score"):
        assert term in normalize.GLOSSARY
        assert len(normalize.GLOSSARY[term]) > 20


def test_glossary_expands_every_acronym_and_unit_shown_in_the_ui():
    """Terms stamped on the pages were never spelled out anywhere on the site."""
    expansions = {
        "CPCB": "Central Pollution Control Board",
        "PM2.5": "micrometres",
        "PM10": "micrometres",
        "µg/m³": "Micrograms per cubic metre",
    }
    for term, expansion in expansions.items():
        assert term in normalize.GLOSSARY
        assert len(normalize.GLOSSARY[term]) > 20
        assert expansion in normalize.GLOSSARY[term]


def test_unit_entry_describes_the_unit_not_the_sites_numbers():
    """What the figures on the site are measured in is a separate question, so
    the unit definition must not assert anything about them."""
    text = normalize.GLOSSARY["µg/m³"].lower()
    for claim in ("pm2.5", "aqi", "delhi", "this site", "the reading"):
        assert claim not in text


def test_n95_entry_explains_the_mask_without_claiming_a_benefit():
    """Cochrane rates the mask evidence very low certainty; the glossary says
    what an N95 is and stops there."""
    text = normalize.GLOSSARY["N95"]
    assert len(text) > 20
    assert "mask" in text.lower()
    for claim in ("%", "protect", "effective", "prevent", "block", "reduce",
                  "safe", "filters out", "keeps out"):
        assert claim not in text.lower()


def test_dark_severity_ramp_is_monotonic_in_luminance():
    """Severity must track contrast-against-background in BOTH themes.

    A sequential scale whose luminance wanders is not a scale -- it was the
    specific defect that made the official CPCB ramp unusable here, so the
    replacement must not repeat it.
    """
    import re
    from pathlib import Path

    css = Path(__file__).resolve().parents[1] / "saafsaans/web/static/app.css"
    text = css.read_text()

    def lum(h):
        h = h.lstrip("#")
        chans = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(chans[0]) + 0.7152 * f(chans[1]) + 0.0722 * f(chans[2])

    def ramp(block):
        chunk = text.split(block, 1)[1]
        return [re.search(rf"--g{n}: (#[0-9A-Fa-f]{{6}})", chunk).group(1) for n in range(1, 7)]

    light = [lum(c) for c in ramp(":root {")]
    dark = [lum(c) for c in ramp('[data-theme="dark"] {')]
    assert light == sorted(light, reverse=True), "light ramp must darken with severity"
    assert dark == sorted(dark), "dark ramp must brighten with severity"


def test_band_chip_word_and_control_borders_meet_contrast():
    """The band word must be readable on every band, and a control's only visual
    boundary must clear 3:1 -- both were failing before this test existed."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "saafsaans/web/static/app.css").read_text()

    def lum(h):
        h = h.lstrip("#")
        ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(ch[0]) + 0.7152 * f(ch[1]) + 0.0722 * f(ch[2])

    def ratio(a, b):
        la, lb = lum(a), lum(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    def tok(block, name):
        chunk = css.split(block, 1)[1]
        return re.search(rf"{name}: (#[0-9A-Fa-f]{{6}})", chunk).group(1)

    # The chip word takes --text, not the band ink, so it passes on every tint.
    assert "color: var(--text); border: 1px solid var(--ink)" in css
    for block, text_tok in ((":root {", "--text"), ('[data-theme="dark"] {', "--text")):
        text = tok(block, text_tok)
        for n in range(1, 7):
            tint = tok(block, f"--n{n}")
            assert ratio(text, tint) >= 4.5, (block, n, ratio(text, tint))

    for block in (":root {", '[data-theme="dark"] {'):
        assert ratio(tok(block, "--border-s"), tok(block, "--surface")) >= 3.0, block
