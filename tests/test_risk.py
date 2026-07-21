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
    assert r["band"] in RISK_BANDS
    # unknown keywords score neutral, no crash
    r2 = compute_risk(150, "bogus", "bogus", "bogus")
    assert 0 <= r2["score"] <= 100


def test_a_missing_reading_is_not_scored_as_clean_air():
    """This used to assert that None scored the same as 0, which is how the
    hero came to say "A good day to breathe -- enjoy it outside" on a page that
    also said UNKNOWN and "treat conditions as unhealthy until you can
    confirm". Absence of evidence was being rendered as evidence of absence, in
    the only direction that can get somebody hurt."""
    unknown = compute_risk(None, "any", "any", "any")
    clean = compute_risk(0, "any", "any", "any")
    assert unknown["score"] > clean["score"]
    assert unknown["band"] not in ("Low", "Moderate")
    # ...and the driver says why, rather than inventing an AQI of 0.
    assert unknown["drivers"][0] == "No reading — treated as unhealthy"
    assert not any("AQI 0" in d for d in unknown["drivers"])
    # It sits where the Unknown band's own advice already pointed: treat it as
    # unhealthy, which is the Poor band's starting point.
    assert unknown["score"] == compute_risk(250, "any", "any", "any")["score"]


def test_every_band_has_actionable_advice():
    from saafsaans.services.risk import band_advice, RISK_BANDS
    for band in RISK_BANDS:
        assert band_advice(band)
    # compute_risk surfaces the advice line in its dict
    r = compute_risk(320, "copd", "outdoor_exercise", "senior")
    assert r["advice"]
    assert isinstance(r["advice"], str)


# --- Grounding: the weights must be traceable ------------------------------
def test_every_weight_carries_a_source():
    """The previous model's weights were uncited numbers that looked derived.

    Every weight must now name where it came from, and must declare honestly
    whether it is grounded in a published figure or is the author's ordering.
    """
    rows = risk.weight_table()
    assert rows
    for row in rows:
        assert row["source"], row
        assert isinstance(row["grounded"], bool), row
        assert row["value"] is not None, row
    tables = {row["table"] for row in rows}
    assert tables == {"inhalation_rates", "condition_pts",
                      "age_susceptibility_pts", "aqi_base_pts"}


def test_only_the_inhalation_rates_are_claimed_as_grounded():
    """Nothing but the EPA table may claim to be published.

    If a future edit marks the condition weights grounded, this fails -- which
    is the point: the honesty of the model is the thing under test.
    """
    for row in risk.weight_table():
        assert row["grounded"] is (row["table"] == "inhalation_rates"), row
        if row["grounded"]:
            assert "Exposure Factors Handbook" in row["source"]
        else:
            assert "Unvalidated" in row["source"] or "design choice" in row["source"]


def test_inhalation_rates_match_the_published_table():
    """EPA EFH 2011 Table 6-2, mean column, m3/min, for the three age bands
    the persona picker offers. Transcription errors here would silently move
    every score, so the figures are pinned."""
    assert risk.INHALATION_RATES == {
        "child":  {"sedentary": 4.8e-3, "light": 1.1e-2, "moderate": 2.2e-2, "high": 4.2e-2},
        "adult":  {"sedentary": 4.2e-3, "light": 1.2e-2, "moderate": 2.6e-2, "high": 5.0e-2},
        "senior": {"sedentary": 4.9e-3, "light": 1.2e-2, "moderate": 2.6e-2, "high": 4.7e-2},
    }
    # The bracket labels for these three ages used to sit beside the rates as
    # risk.EPA_AGE_BANDS, and this line checked the two dicts covered the same
    # ages. Nothing rendered that dict -- the Guide carries its own translated
    # copy -- so it was deleted and the check moved to where the surviving copy
    # lives: test_web.test_the_guide_labels_every_age_in_the_rate_table.


def test_the_intensity_order_covers_the_rate_table_least_first():
    """The Guide renders the rate table through this order, so it must name
    every column exactly once and must not drift away from the rates it
    labels. There used to be a second private copy in web/main.py, free to
    disagree with this one."""
    for age, rates in risk.INHALATION_RATES.items():
        assert list(risk.INTENSITY_ORDER) == sorted(rates, key=rates.get), age
    assert set(risk.INTENSITY_ORDER) == set(risk.ACTIVITY_INTENSITY.values())


def test_dose_points_are_ratios_of_published_rates():
    # A resting adult is the baseline and scores nothing extra.
    assert risk.inhalation_ratio("adult", "stay_home") == 1.0
    assert risk.dose_points("adult", "stay_home") == 0
    # The heaviest published cell anchors the top of the range.
    assert risk.dose_points("adult", "outdoor_exercise") == risk.DOSE_MAX_PTS
    # Ratios are the published rates divided by the sedentary adult rate.
    assert round(risk.inhalation_ratio("child", "outdoor_exercise"), 3) == 10.0
    assert round(risk.inhalation_ratio("senior", "commute"), 3) == 2.857


def test_dose_rises_with_exertion_for_every_age():
    for age in ("child", "adult", "senior"):
        pts = [risk.dose_points(age, a) for a in
               ("stay_home", "commute", "school_run", "outdoor_exercise")]
        assert pts == sorted(pts), (age, pts)
        assert pts[0] < pts[-1]


def test_children_do_not_breathe_more_air_than_adults():
    """The uncomfortable consequence of using real numbers, asserted so it
    cannot be quietly reversed: per minute a 6-11 year old moves LESS air than
    an adult at the same exertion. Their extra vulnerability is therefore
    carried by the susceptibility term, which is labelled unvalidated, and not
    smuggled into the term that claims to be published."""
    assert risk.INHALATION_RATES["child"]["high"] < risk.INHALATION_RATES["adult"]["high"]
    assert risk.dose_points("child", "outdoor_exercise") < risk.dose_points("adult", "outdoor_exercise")
    # ...and yet a child still scores higher overall, via susceptibility.
    child = compute_risk(300, "any", "outdoor_exercise", "child")["score"]
    adult = compute_risk(300, "any", "outdoor_exercise", "adult")["score"]
    assert child > adult


def test_unknown_persona_keywords_are_scored_at_rest_not_exercising():
    """A bad label must fall to the least alarming assumption, never the worst."""
    assert risk.dose_points("bogus", "bogus") == 0
    assert risk.inhalation_ratio("bogus", "bogus") == 1.0


def test_staying_home_no_longer_claims_a_discount():
    """The old model subtracted 6 points for staying home, implying indoor air
    is cleaner. Delhi indoor PM2.5 tracks outdoor closely, so that discount was
    never evidenced. Staying home now scores lowest purely because a resting
    body inhales least -- and the driver list must not claim otherwise."""
    r = compute_risk(300, "asthma", "stay_home", "adult")
    assert r["score"] == compute_risk(300, "asthma", "any", "adult")["score"]
    assert not any("home" in d.lower() for d in r["drivers"])


def test_the_heuristic_notice_names_both_halves_of_the_model():
    notice = risk.HEURISTIC_NOTICE
    assert "EPA" in notice
    assert "not a validated" in notice


# --- Language --------------------------------------------------------------
# The chips under the score say why it is what it is. They were the last piece
# of the Today page still in English under a Hindi banner.

import re

import pytest

from saafsaans.services import i18n

LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’.\-]{2,}")


def _stub_hindi(monkeypatch, *groups):
    """Answer every lookup in whole groups with a Devanagari marker.

    Phase 1 writes no Hindi. The marker proves the chip is routed through
    ``i18n.t``; a label typed inline stays English and this test names it.
    """
    real = i18n.t

    def fake(lang, group, key, english):
        return "अनुवादित" if lang == "hi" and group in groups else real(
            lang, group, key, english)

    monkeypatch.setattr(i18n, "t", fake)


@pytest.mark.parametrize("aqi,condition,activity,age", [
    (199, "asthma", "outdoor_exercise", "adult"),
    (350, "copd", "school_run", "child"),
    (80, "heart", "commute", "senior"),
    (150, "pregnancy", "stay_home", "adult"),
    (None, "any", "any", "any"),
])
def test_the_drivers_leave_no_english_in_hindi(monkeypatch, aqi, condition,
                                               activity, age):
    _stub_hindi(monkeypatch, "driver", "band_label")
    drivers = compute_risk(aqi, condition, activity, age, lang="hi")["drivers"]
    stray = {w for d in drivers for w in LATIN_RUN.findall(d)}
    assert not stray, f"still written in English: {sorted(stray)}"


def test_the_aqi_chip_takes_its_band_word_from_the_shared_group():
    """The chip and the reading card name the same air. A second copy of the
    seven band words could drift; this reuses band_label."""
    chip = compute_risk(199, "any", "any", "adult", lang="hi")["drivers"][0]
    assert i18n.HI["band_label"]["Moderate"] in chip
    assert "199" in chip
    assert "Moderate" not in chip


def test_the_chip_is_one_template_so_hindi_can_reorder_it(monkeypatch):
    """Not "AQI " + n + " (" + band + ")": Hindi does not put the parenthetical
    where English does, and a concatenation would fix the English order."""
    monkeypatch.setitem(i18n.HI, "driver", {"aqi": "{band} — AQI {aqi}"})
    assert compute_risk(199, "any", "any", "adult", lang="hi")["drivers"][0] == \
        f"{i18n.HI['band_label']['Moderate']} — AQI 199"


def test_the_drivers_are_unchanged_english_by_default():
    for args in [(199, "asthma", "outdoor_exercise", "adult"),
                 (None, "copd", "commute", "senior")]:
        assert compute_risk(*args) == compute_risk(*args, lang="en")


def test_headline_and_advice_stay_english_keys_for_the_call_site_to_translate():
    """today.html asks for ``T('band_advice', risk.band, risk.advice)``, keyed
    on the band this returns. Translating them here would hand that lookup a
    Hindi key and lose the translation rather than add one."""
    r = compute_risk(350, "copd", "outdoor_exercise", "senior", lang="hi")
    assert r["band"] in RISK_BANDS
    assert r["headline"] == risk._HEADLINE[r["band"]]
    assert r["advice"] == risk.BAND_ADVICE[r["band"]]


def test_every_driver_label_has_a_key_a_translator_can_find():
    """The keys are derived from the persona vocab, so a new condition or
    activity arrives with its key already named rather than silently English."""
    for kw in risk._COND_LABEL:
        assert kw in risk.CONDITION_PTS
    for kw in risk._ACT_LABEL:
        assert kw in risk.ACTIVITY_INTENSITY
    for kw in risk._AGE_LABEL:
        assert kw in risk.AGE_SUSCEPTIBILITY_PTS
