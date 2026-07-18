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
    assert normalize.aqi_category(50)[:2] == ("Good", "green")
    assert normalize.aqi_category(100)[:2] == ("Good", "green")
    assert normalize.aqi_category(101)[:2] == ("Moderate", "orange")
    assert normalize.aqi_category(200)[:2] == ("Moderate", "orange")
    assert normalize.aqi_category(201)[:2] == ("Poor", "red")
    assert normalize.aqi_category(300)[:2] == ("Poor", "red")
    assert normalize.aqi_category(301)[0] == "Very Poor"
    assert normalize.aqi_category(400)[0] == "Very Poor"
    assert normalize.aqi_category(401)[0] == "Severe"
    assert normalize.aqi_category(999)[0] == "Severe"


def test_aqi_category_defensive():
    assert normalize.aqi_category(None)[0] == "Unknown"
    assert normalize.aqi_category("-")[0] == "Unknown"
    assert normalize.aqi_category(-5)[0] == "Good"  # clamped for color


def test_aqi_meaning_covers_every_category():
    for label in ("Good", "Moderate", "Poor", "Very Poor", "Severe", "Unknown"):
        assert label in normalize.AQI_MEANING
        assert normalize.aqi_meaning(label)
    # unknown label falls back rather than raising
    assert normalize.aqi_meaning("bogus") == normalize.AQI_MEANING["Unknown"]


def test_glossary_has_core_terms():
    for term in ("AQI", "PM2.5", "PM10", "Dominant pollutant", "Risk score"):
        assert term in normalize.GLOSSARY
        assert len(normalize.GLOSSARY[term]) > 20
