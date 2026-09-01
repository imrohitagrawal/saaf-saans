"""Gate 5 package 5b: Teen and Youth ages, and server-side pregnancy restriction.

See docs/superpowers/specs/2026-09-01-persona-truth-design.md section 3.
tests/test_epa_table.py already pins the two new EPA rates cell-by-cell
against tests/epa_table_6_2.json; this file covers the rest of the package --
that the two ages are wired consistently everywhere the three old ones were,
that adding them does not silently rescale an existing persona's score, that
neither carries the ungrounded susceptibility bump, and that Pregnancy is
refused server-side for Child, Teen and Senior with a visible, honest notice
rather than a silent fallback.

WHAT TURNS EACH TEST RED:

- ``test_five_ages_are_offered_in_every_map`` / ``test_teen_and_youth_normalise_...``:
  removing "Teen"/"Youth" from any one of AGES, normalize.AGE_MAP or
  risk.INHALATION_RATES while leaving it in the others.
- ``test_teen_and_youth_carry_no_susceptibility_bump``: adding either key to
  risk.AGE_SUSCEPTIBILITY_PTS.
- ``test_dose_points_for_every_pre_existing_persona_is_unchanged``: changing
  any pre-existing rate, or adding a row at or above adult/high's 5.0e-2 --
  either rescales ``_DOSE_SCALE`` and moves every number in the table below.
- ``test_teen_and_youth_labels_carry_their_numeric_range``: dropping the
  numeric range from either picker option label, in either language.
- ``test_all_88_reachable_combinations_render``: any reachable combination
  raising or returning non-200.
- ``test_pregnancy_cannot_render_for_a_blocked_age_whatever_the_activity``:
  commenting out the downgrade in ``main.read_persona`` -- verified by hand,
  2026-09-01, by removing the guard and re-running this file: all twelve
  (age, activity) cases turned red, each showing "who is pregnant" and the
  birth-weight advisory for a Child, a Teen or a Senior.
- ``test_a_blocked_pair_says_so_on_the_page``: removing the notice paragraph,
  or its ``pregnancy_blocked_age`` computation in main.py.
- ``test_pregnancy_still_renders_for_the_two_permitted_ages``: the
  non-vacuity partner -- proves the guard does not also block the ages it
  must allow.
"""
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import normalize, risk
from saafsaans.web import main as web_main
from saafsaans.web.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- The five ages, wired consistently --------------------------------------
def test_five_ages_are_offered_in_every_map():
    assert web_main.AGES == ["Child", "Teen", "Youth", "Adult", "Senior"]
    assert set(normalize.AGE_MAP) == set(web_main.AGES)
    assert {normalize.norm_age(a) for a in web_main.AGES} == set(risk.INHALATION_RATES)


def test_teen_and_youth_normalise_to_their_own_keyword():
    assert normalize.norm_age("Teen") == "teen"
    assert normalize.norm_age("Youth") == "youth"


def test_teen_and_youth_use_their_own_epa_row_not_a_neighbours():
    """Sanity check that the two new ages are actually wired into scoring, not
    merely present in the table and otherwise unreachable. ``stay_home``
    (sedentary): the only activity level where all five ages' rates happen to
    be pairwise distinct, so any two colliding proves a lookup is wrong."""
    ratios = {age: risk.inhalation_ratio(age, "stay_home")
              for age in ("child", "teen", "youth", "adult", "senior")}
    assert len(set(ratios.values())) == 5, ratios


# --- No susceptibility bump (constraint: grounded half only) ----------------
def test_teen_and_youth_carry_no_susceptibility_bump():
    assert "teen" not in risk.AGE_SUSCEPTIBILITY_PTS
    assert "youth" not in risk.AGE_SUSCEPTIBILITY_PTS
    assert risk.AGE_SUSCEPTIBILITY_PTS.get("teen", 0) == 0
    assert risk.AGE_SUSCEPTIBILITY_PTS.get("youth", 0) == 0


# --- The rescaling hazard, closed by measurement -----------------------------
# Measured on master at c441b82, before this package, with
# `.venv/bin/python -c "..."` walking risk.dose_points over the three
# pre-existing ages and every activity keyword.
_PRE_EXISTING_DOSE_POINTS = {
    ("child", "outdoor_exercise"): 13, ("child", "school_run"): 9,
    ("child", "commute"): 5, ("child", "stay_home"): 1, ("child", "any"): 1,
    ("adult", "outdoor_exercise"): 14, ("adult", "school_run"): 10,
    ("adult", "commute"): 6, ("adult", "stay_home"): 0, ("adult", "any"): 0,
    ("senior", "outdoor_exercise"): 14, ("senior", "school_run"): 10,
    ("senior", "commute"): 6, ("senior", "stay_home"): 1, ("senior", "any"): 1,
}


def test_dose_points_for_every_pre_existing_persona_is_unchanged():
    for (age, act), expected in _PRE_EXISTING_DOSE_POINTS.items():
        assert risk.dose_points(age, act) == expected, (age, act)


def test_teen_and_youth_high_intensity_stays_below_the_existing_ceiling():
    """G5-R4. Teen and Youth's high-intensity rates are both 4.9e-2 --
    confirmed, not assumed -- below adult/high's 5.0e-2, so `_MAX_RATIO`
    (derived from the table's maximum) is still set by adult, and no
    pre-existing persona's dose_points can have moved."""
    assert risk.INHALATION_RATES["teen"]["high"] < risk.INHALATION_RATES["adult"]["high"]
    assert risk.INHALATION_RATES["youth"]["high"] < risk.INHALATION_RATES["adult"]["high"]
    assert risk.INHALATION_RATES["adult"]["high"] == max(
        r for by_age in risk.INHALATION_RATES.values() for r in by_age.values())


# --- Picker labels carry the numeric range -----------------------------------
def test_teen_and_youth_labels_carry_their_numeric_range():
    """5a.1: no single Hindi noun can carry "11 to <16" or "16 to <21", so the
    range goes in the option label itself, in both languages."""
    for lang in ("en", "hi"):
        labels = web_main._option_labels(lang)
        assert re.search(r"11\D+15", labels["Teen"]), (lang, labels["Teen"])
        assert re.search(r"16\D+20", labels["Youth"]), (lang, labels["Youth"])


# --- The whole reachable persona space ---------------------------------------
PREGNANCY_BLOCKED_AGES = ("Child", "Teen", "Senior")


def _reachable_age_conditions():
    return [(age, cond) for age in web_main.AGES for cond in web_main.CONDITIONS
            if not (cond == "Pregnancy" and age in PREGNANCY_BLOCKED_AGES)]


def test_the_persona_space_after_5b_is_88_reachable_combinations():
    assert len(_reachable_age_conditions()) * len(web_main.ACTIVITIES) == 88


def test_all_88_reachable_combinations_render(client):
    for age, cond in _reachable_age_conditions():
        for act in web_main.ACTIVITIES:
            r = client.get("/", params={"age": age, "condition": cond,
                                        "activity": act, "locality": "Anand Vihar",
                                        "theme": "light"})
            assert r.status_code == 200, (age, cond, act)


# --- Pregnancy restricted server-side ----------------------------------------
def test_read_persona_downgrades_a_blocked_pregnancy_pair():
    from starlette.requests import Request

    def _req(qs: str) -> Request:
        return Request({"type": "http", "query_string": qs.encode(),
                        "headers": [], "method": "GET"})

    for age in PREGNANCY_BLOCKED_AGES:
        persona = web_main.read_persona(_req(f"age={age}&condition=Pregnancy"))
        assert persona["condition"] == "Fit", (age, persona)
    for age in ("Youth", "Adult"):
        persona = web_main.read_persona(_req(f"age={age}&condition=Pregnancy"))
        assert persona["condition"] == "Pregnancy", (age, persona)


@pytest.mark.parametrize("age", PREGNANCY_BLOCKED_AGES)
@pytest.mark.parametrize("activity", ("Outdoor exercise", "Commute",
                                      "School run", "Stay home"))
def test_pregnancy_cannot_render_for_a_blocked_age_whatever_the_activity(
        client, age, activity):
    """D2/D5. Verified by hand, 2026-09-01: commenting out the downgrade in
    main.read_persona turns every one of these twelve cases red -- the body
    then contains "who is pregnant" and the birth-weight advisory.

    Not opened with edit=1: the editor's own opt-help list explains every
    option including Pregnancy regardless of which is selected, so it would
    make "preterm birth" appear on the page whatever the persona is. The
    closed-editor caveat, keyed on ``persona.condition`` alone, is the
    surface that would leak an unrefused Pregnancy."""
    body = client.get("/", params={"age": age, "condition": "Pregnancy",
                                   "activity": activity, "locality": "Anand Vihar",
                                   "theme": "light"}).text
    assert "who is pregnant" not in body, (age, activity)
    assert "preterm birth" not in body, (age, activity)
    assert "Pregnancy raises risk" not in body, (age, activity)
    assert "riskier for you than for an average adult" in body, (age, activity)


def test_pregnancy_still_renders_for_the_two_permitted_ages(client):
    """Non-vacuity partner: the guard must not also refuse the ages D5 allows."""
    for age in ("Youth", "Adult"):
        body = client.get("/", params={"age": age, "condition": "Pregnancy",
                                       "activity": "Outdoor exercise",
                                       "locality": "Anand Vihar",
                                       "theme": "light"}).text
        assert "who is pregnant" in body, age
        assert "preterm birth" in body, age
        assert "instead" not in body, age  # no blocked-pair notice


@pytest.mark.parametrize("age", PREGNANCY_BLOCKED_AGES)
def test_a_blocked_pair_says_so_on_the_page(client, age):
    """Constraint (i): a silent fallback answers a question the reader did
    not ask. Checked in both languages."""
    for lang in ("en", "hi"):
        body = client.get("/", params={"age": age, "condition": "Pregnancy",
                                       "activity": "Outdoor exercise",
                                       "locality": "Anand Vihar", "theme": "light",
                                       "lang": lang}).text
        assert "pregnancy_blocked_notice" not in body  # never a raw key
        marker = "instead" if lang == "en" else "सेहतमंद"
        assert marker in body, (age, lang, body[:4000])


def test_no_notice_when_pregnancy_was_not_asked_for(client):
    body = client.get("/", params={"age": "Child", "condition": "Fit",
                                   "activity": "Outdoor exercise",
                                   "locality": "Anand Vihar",
                                   "theme": "light"}).text
    assert "instead" not in body


# --- Hindi terms (D9) ---------------------------------------------------
def test_persona_sentence_uses_the_decided_hindi_terms_for_teen_and_youth():
    from saafsaans.web import presenters as pr

    teen = pr.persona_sentence({"age": "Teen", "condition": "Fit",
                                "activity": "Stay home"}, lang="hi")
    youth = pr.persona_sentence({"age": "Youth", "condition": "Fit",
                                 "activity": "Stay home"}, lang="hi")
    assert "किशोर" in teen, teen
    assert "युवा" in youth, youth


def test_guide_no_longer_claims_three_age_groups(client):
    """guide/researched_intro hardcoded "the three age groups this site
    offers"; there are now five."""
    en = client.get("/guide", params={"theme": "light"}).text
    assert "three age groups" not in en
    hi = client.get("/guide", params={"theme": "light", "lang": "hi"}).text
    assert "तीनों" not in hi
