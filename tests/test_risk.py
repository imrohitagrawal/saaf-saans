from saafsaans.services import risk
from saafsaans.services.risk import compute_risk, RISK_BANDS


def test_shape_has_all_keys():
    r = compute_risk(150, "asthma", "commute", "adult")
    assert set(r) == {"score", "band", "color", "drivers", "headline", "advice"}
    assert isinstance(r["score"], int)
    assert r["band"] in RISK_BANDS
    assert r["color"].startswith("#")
    assert isinstance(r["drivers"], list) and r["drivers"]
    assert isinstance(r["headline"], str) and r["headline"]


def test_score_clamped_within_0_100():
    for aqi in (-100, 0, 50, 250, 500, 9999):
        for cond in ("any", "copd"):
            for act in ("stay_home", "outdoor_exercise"):
                for age in ("any", "senior"):
                    s = compute_risk(aqi, cond, act, age)["score"]
                    assert 0 <= s <= 100


def test_monotonic_in_aqi():
    # Same persona: higher AQI must never lower the score.
    prev = -1
    scores = []
    for aqi in (30, 80, 150, 250, 350, 450):
        s = compute_risk(aqi, "asthma", "commute", "child")["score"]
        assert s >= prev
        scores.append(s)
        prev = s
    # And strictly higher across the AQI buckets.
    assert scores[0] < scores[-1]
    assert len(set(scores)) == len(scores)


def test_condition_ordering():
    # copd >= heart >= asthma >= none at fixed aqi/activity/age.
    def s(cond):
        return compute_risk(200, cond, "commute", "adult")["score"]

    assert s("copd") >= s("heart") >= s("asthma") >= s("any")


def test_activity_ordering():
    def s(act):
        return compute_risk(200, "asthma", act, "adult")["score"]

    assert s("outdoor_exercise") >= s("commute") >= s("stay_home")


def test_band_boundaries():
    # Band is derived purely from score thresholds: <20,<40,<60,<80,else.
    assert risk._band_for(0)[0] == "Low"
    assert risk._band_for(19)[0] == "Low"
    assert risk._band_for(20)[0] == "Moderate"
    assert risk._band_for(39)[0] == "Moderate"
    assert risk._band_for(40)[0] == "High"
    assert risk._band_for(59)[0] == "High"
    assert risk._band_for(60)[0] == "Very High"
    assert risk._band_for(79)[0] == "Very High"
    assert risk._band_for(80)[0] == "Extreme"
    assert risk._band_for(100)[0] == "Extreme"


def test_band_colors_match_contract():
    expected = {
        "Low": "#2e7d32",
        "Moderate": "#ef6c00",
        "High": "#c62828",
        "Very High": "#7f0000",
        "Extreme": "#4a0000",
    }
    for band, hex_ in expected.items():
        # find a score in that band
        assert risk._band_for({"Low": 10, "Moderate": 30, "High": 50,
                               "Very High": 70, "Extreme": 100}[band])[1] == hex_


def test_drivers_non_empty_and_aqi_first():
    r = compute_risk(320, "copd", "outdoor_exercise", "senior")
    assert r["drivers"]
    assert r["drivers"][0].startswith("AQI 320")
    assert len(r["drivers"]) <= 3


def test_defensive_invalid_aqi():
    r = compute_risk(None, "any", "any", "any")
    assert r["score"] == compute_risk(0, "any", "any", "any")["score"]
    assert r["band"] in RISK_BANDS
    # unknown keywords score neutral, no crash
    r2 = compute_risk(150, "bogus", "bogus", "bogus")
    assert 0 <= r2["score"] <= 100


def test_every_band_has_actionable_advice():
    from saafsaans.services.risk import band_advice, RISK_BANDS
    for band in RISK_BANDS:
        assert band_advice(band)
    # compute_risk surfaces the advice line in its dict
    r = compute_risk(320, "copd", "outdoor_exercise", "senior")
    assert r["advice"]
    assert isinstance(r["advice"], str)
