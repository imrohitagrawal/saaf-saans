"""Gate 5 package 5c: the verdict, keyed to its driver.

See docs/superpowers/specs/2026-09-01-persona-truth-design.md section 4.
Design doc section 1.2 measured 19 of 38 non-lung personas at AQI 180 told
"hard on lungs like yours" -- the headline named the wrong organ. This
package fixes the FIRST of section 1.1's two defects (no variation by
reader); it explicitly does not fix the second (no variation by air -- see
the design doc and presenters.verdict_for's own docstring).

WHAT TURNS EACH TEST RED:

- ``test_verdict_driver_precedence``: reordering the if/elif chain in
  ``presenters.verdict_driver`` (e.g. checking age before condition).
- ``test_high_bands_have_five_distinct_driver_variants``: collapsing any two
  of the five per-band variants onto the same text, or removing a variant.
- ``test_low_and_moderate_ignore_the_driver``: giving Low or Moderate a
  driver-specific variant, which the design doc's own scope note forbids --
  those severities claim no organ effect to get wrong.
- ``test_no_persona_receives_a_contradicting_organ_claim``: any driver
  variant naming an organ word that does not match its own key (a "lungs"
  variant containing "heart", for instance) -- or ``verdict_driver``
  returning the wrong driver for a persona.
- ``test_distinct_verdict_count_meets_the_exit_criterion``: the 88 x 4 sweep
  producing fewer than 12 distinct sentences.
- ``test_rendered_verdict_names_the_right_organ``: reverting the
  ``main.today()`` driver wiring turns this red -- verified by hand,
  2026-09-01, by calling ``pr.verdict_for(band)`` with no driver at the call
  site: every persona in the sweep reverted to the "none" line and the
  organ-specific assertions failed.
"""
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import normalize, risk, waqi
from saafsaans.web import main as web_main
from saafsaans.web import presenters as pr
from saafsaans.web.main import app

BLOCKED_PREGNANCY_AGES = ("Child", "Teen", "Senior")


def _reachable_88():
    for age in web_main.AGES:
        for cond in web_main.CONDITIONS:
            if cond == "Pregnancy" and age in BLOCKED_PREGNANCY_AGES:
                continue
            for act in web_main.ACTIVITIES:
                yield age, cond, act


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- Driver precedence -------------------------------------------------
def test_verdict_driver_precedence():
    assert pr.verdict_driver("asthma", "adult") == "lungs"
    assert pr.verdict_driver("copd", "adult") == "lungs"
    assert pr.verdict_driver("heart", "adult") == "heart"
    assert pr.verdict_driver("pregnancy", "adult") == "pregnancy"
    assert pr.verdict_driver("any", "child") == "age"
    assert pr.verdict_driver("any", "senior") == "age"
    assert pr.verdict_driver("any", "adult") == "none"
    assert pr.verdict_driver("any", "teen") == "none"
    assert pr.verdict_driver("any", "youth") == "none"


def test_condition_always_outranks_age():
    """The design doc's open sub-decision, resolved: a senior with COPD is
    told about lungs, not age. Bite: swapping the if/elif order in
    verdict_driver so age is checked first turns this red for every one of
    the four conditions crossed with child/senior."""
    for condition_kw, driver in (("asthma", "lungs"), ("copd", "lungs"),
                                 ("heart", "heart"), ("pregnancy", "pregnancy")):
        for age_kw in ("child", "senior"):
            assert pr.verdict_driver(condition_kw, age_kw) == driver, \
                (condition_kw, age_kw)


def test_unrecognised_condition_falls_through_to_age_or_none():
    """Matches normalize.norm_condition's own "any" fallback for a label it
    does not recognise -- an unrecognised condition must never be scored (or
    worded) as though it were one of the four named ones."""
    assert pr.verdict_driver("nonsense", "senior") == "age"
    assert pr.verdict_driver("nonsense", "adult") == "none"


# --- verdict_for / verdict_key -------------------------------------------
_DRIVERS = ("none", "lungs", "heart", "pregnancy", "age")
_SEVERITY_BANDS = ("High", "Very High", "Extreme")


def test_high_bands_have_five_distinct_driver_variants():
    for band in _SEVERITY_BANDS:
        texts = {pr.verdict_for(band, driver) for driver in _DRIVERS}
        assert len(texts) == 5, (band, texts)


def test_low_and_moderate_ignore_the_driver():
    """Design doc section 4 scope: this package fixes only the wrong-organ
    defect, and Low/Moderate never claimed an organ to get wrong."""
    for band in ("Low", "Moderate"):
        texts = {pr.verdict_for(band, driver) for driver in _DRIVERS}
        assert len(texts) == 1, (band, texts)


def test_verdict_for_default_driver_is_none():
    for band in _SEVERITY_BANDS:
        assert pr.verdict_for(band) == pr.verdict_for(band, "none")


def test_unknown_band_or_driver_falls_back_to_the_cautious_line():
    assert pr.verdict_for("nonsense") == pr.verdict_for("High")
    assert pr.verdict_for("High", "nonsense") == pr.verdict_for("High", "none")
    assert pr.verdict_for("nonsense", "lungs") == pr.verdict_for("High", "none")


def test_verdict_key_matches_what_verdict_for_resolves_to():
    """main.today() asks verdict_key for the i18n key and verdict_for for the
    English fallback -- they must agree, or a driver's Hindi translation
    would be served under the wrong key and silently lost."""
    from saafsaans.services import i18n

    for band in _SEVERITY_BANDS:
        for driver in _DRIVERS:
            key = pr.verdict_key(band, driver)
            assert key in i18n.HI["verdict"], (band, driver, key)
            assert pr._VERDICTS[key] == pr.verdict_for(band, driver)


# --- No organ claim contradicts the condition -----------------------------
_ORGAN_WORDS_EN = {"lungs": "lungs", "heart": "heart", "pregnancy": "pregnancy"}
_ORGAN_WORDS_HI = {"lungs": "फेफड़ों", "heart": "दिल", "pregnancy": "गर्भावस्था"}


def test_no_persona_receives_a_contradicting_organ_claim():
    """Swept over all 88 reachable personas (post-5b), all three severity
    bands, both languages. Bite: hand-editing one variant's organ word (e.g.
    making High_heart say "lungs") fails at the (band, driver) pair whose
    own key names the other organ."""
    from saafsaans.services import i18n

    for age, cond, act in _reachable_88():
        condition_kw = normalize.norm_condition(cond)
        age_kw = normalize.norm_age(age)
        driver = pr.verdict_driver(condition_kw, age_kw)
        for band in _SEVERITY_BANDS:
            for lang, words in ((None, _ORGAN_WORDS_EN), ("hi", _ORGAN_WORDS_HI)):
                text = (pr.verdict_for(band, driver) if lang is None else
                        i18n.HI["verdict"][pr.verdict_key(band, driver)])
                for organ, word in words.items():
                    if organ == driver:
                        continue
                    assert word not in text, (age, cond, act, band, driver, organ, text)


def test_the_organ_word_the_driver_promises_is_actually_there():
    """The positive partner: the check above proves absence, which is
    trivially true of a variant that names no organ at all. This proves the
    right word actually ships for the three organ-bearing drivers."""
    from saafsaans.services import i18n

    for driver, en_word in (("lungs", "lungs"), ("heart", "heart"),
                            ("pregnancy", "pregnancy")):
        for band in _SEVERITY_BANDS:
            assert en_word in pr.verdict_for(band, driver), (band, driver)
            hi_word = _ORGAN_WORDS_HI[driver]
            assert hi_word in i18n.HI["verdict"][pr.verdict_key(band, driver)], \
                (band, driver)


# --- Constraints preserved (presenters.py:68-83's rules) -------------------
def test_no_verdict_variant_says_indoors():
    for text in pr._VERDICTS.values():
        assert "indoors" not in text.lower(), text


def test_every_verdict_variant_carries_an_instruction():
    """Every one of the seventeen must have an em-dash clause after the
    situation -- the same shape the pre-5c five already held."""
    for key, text in pr._VERDICTS.items():
        assert "—" in text, (key, text)


# --- Distinct-count exit criterion -----------------------------------------
def test_distinct_verdict_count_meets_the_exit_criterion():
    """Design doc section 4: "distinct verdicts across the 88 x 4 sweep is at
    least 12", measured before (band only) and after (band + driver) on the
    same post-5b persona space. Reproduced by scripts/measure_gate5.py
    section 7, which records both figures for the PR: before 5, after 16.
    """
    reachable = list(_reachable_88())
    sample_aqi = (40, 150, 220, 350)  # crosses every band the 88 can reach
    before, after = set(), set()
    for aqi in sample_aqi:
        for age, cond, act in reachable:
            out = risk.compute_risk(aqi, normalize.norm_condition(cond),
                                    normalize.norm_activity(act),
                                    normalize.norm_age(age))
            band = out["band"]
            before.add(pr.verdict_for(band))
            driver = pr.verdict_driver(normalize.norm_condition(cond),
                                       normalize.norm_age(age))
            after.add(pr.verdict_for(band, driver))
    assert len(before) < len(after), (len(before), len(after))
    assert len(after) >= 12, (len(after), sorted(after))


# --- Rendered page ----------------------------------------------------------
def _feed(monkeypatch, pm25):
    def get_aqi(loc, es_client=None):
        return (waqi._reading(pm25, pm25 * 1.6, station=loc, city="Delhi",
                              stale=False, forecast=None,
                              obs_time="2026-09-01T10:00:00+05:30"), "ok")
    monkeypatch.setattr(waqi, "get_aqi", get_aqi)


@pytest.mark.parametrize("age,condition,expect,forbid", (
    ("Child", "COPD", "lungs", ("heart", "pregnancy")),
    ("Senior", "Heart condition", "heart", ("lungs", "pregnancy")),
    ("Youth", "Pregnancy", "pregnancy", ("lungs", "heart")),
    ("Senior", "Fit", "body like yours", ("lungs", "heart", "pregnancy")),
))
def test_rendered_verdict_names_the_right_organ(monkeypatch, client, age,
                                                 condition, expect, forbid):
    """End-to-end: the actual <h1> on / names the persona's own driver and no
    other. AQI 250 -> High for a Fit senior and worse for anyone else, so
    every case here lands on a driver-bearing band."""
    _feed(monkeypatch, pm25=250.0)
    body = client.get("/", params={"age": age, "condition": condition,
                                   "activity": "Outdoor exercise",
                                   "locality": "Anand Vihar",
                                   "theme": "light"}).text
    h1 = re.search(r'<h1 class="verdict">([^<]*)</h1>', body).group(1)
    assert expect in h1, (age, condition, h1)
    for word in forbid:
        assert word not in h1, (age, condition, h1)


def test_rendered_verdict_in_hindi_names_the_right_organ(monkeypatch, client):
    _feed(monkeypatch, pm25=250.0)
    body = client.get("/", params={"age": "Child", "condition": "COPD",
                                   "activity": "Outdoor exercise",
                                   "locality": "Anand Vihar", "theme": "light",
                                   "lang": "hi"}).text
    h1 = re.search(r'<h1 class="verdict">([^<]*)</h1>', body).group(1)
    assert "फेफड़ों" in h1, h1
    assert "दिल" not in h1, h1
    assert "गर्भावस्था" not in h1, h1
