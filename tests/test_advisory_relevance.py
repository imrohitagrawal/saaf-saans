"""Advisory relevance: an advisory the reader receives must apply to them.

The defect this file pins: the old in-process search filtered on the AQI band
alone and merely *scored* persona matches, so a child with asthma at AQI 450 was
served a senior's advisory with score 0 rather than not served it at all. Scoring
cannot exclude; only filtering can.
"""
import itertools
from pathlib import Path

import pytest

from saafsaans.data.advisories import ADVISORIES
from saafsaans.services import es
from saafsaans.services.normalize import ACTIVITY_MAP, AGE_MAP, CONDITION_MAP

# The reachable persona space, taken from the maps the UI itself normalizes
# through, so a new picker option lands in this sweep without an edit here.
CONDITIONS = sorted(set(CONDITION_MAP.values()))
ACTIVITIES = sorted(set(ACTIVITY_MAP.values()))
AGES = sorted(set(AGE_MAP.values()))
# One value inside every band boundary the corpus uses, plus the extremes.
AQI_VALUES = [0, 50, 51, 100, 101, 150, 151, 200, 201, 250, 300, 301, 350,
              400, 401, 450, 500, 999]


def test_the_sweep_covers_the_whole_reachable_persona_space():
    """If the maps were read wrongly this file would prove nothing on 0 personas."""
    assert len(CONDITIONS) == 5 and len(ACTIVITIES) == 4 and len(AGES) == 3


@pytest.mark.parametrize("condition,activity,age",
                         list(itertools.product(CONDITIONS, ACTIVITIES, AGES)))
def test_every_advisory_served_applies_to_the_reader(condition, activity, age):
    """The test that defines done: no persona, at any AQI, is ever handed an
    advisory written for a different persona."""
    for aqi in AQI_VALUES:
        docs = es.search_advisories(aqi, condition, activity, age, client=None)
        assert docs, f"no advisory at all for {condition}/{activity}/{age} @ {aqi}"
        for d in docs:
            assert es.applies_to(d, condition, activity, age), (
                f"{d['source']} {d['aqi_min']}-{d['aqi_max']} "
                f"{d['condition']}/{d['activity']}/{d['age_group']} served to "
                f"{condition}/{activity}/{age} @ {aqi}")


def test_a_senior_with_copd_is_not_given_the_heart_row():
    """Reproduction from the plan. The AHA 301-999 row is written for people who
    have heart disease; COPD is not heart disease."""
    docs = es.search_advisories(350, "copd", "stay_home", "senior", client=None)
    assert not any(d["condition"] == "heart" for d in docs)
    assert any(d["condition"] == "copd" for d in docs)


def test_a_child_with_asthma_is_not_given_a_senior_row():
    """Reproduction from the plan: at AQI 450 the corpus offered a child with
    asthma four rows, none of which applied."""
    docs = es.search_advisories(450, "asthma", "school_run", "child", client=None)
    assert not any(d["age_group"] == "senior" for d in docs)
    assert any(d["condition"] == "asthma" for d in docs)


def test_applies_to_does_not_hand_an_unstated_condition_to_asthma_advice():
    row = dict(condition="asthma", activity="any", age_group="any")
    assert not es.applies_to(row, "any", "any", "any")
    assert es.applies_to(row, "asthma", "any", "any")


def test_applies_to_defaults_missing_keys_to_any():
    """ES documents are external data and may be missing a field."""
    assert es.applies_to({}, "asthma", "commute", "child")


def test_specificity_counts_the_fields_that_name_this_persona():
    row = dict(condition="asthma", activity="outdoor_exercise", age_group="child")
    assert es.specificity(row, "asthma", "outdoor_exercise", "child") == 3
    assert es.specificity(dict(condition="any", activity="any", age_group="any"),
                          "asthma", "any", "any") == 0


def test_relevance_is_tagged_persona_or_general():
    docs = es.search_advisories(250, "heart", "any", "any", client=None)
    tagged = {d["source"]: d["relevance"] for d in docs}
    assert tagged, "nothing to tag"
    for d in docs:
        expected = (es.RELEVANCE_PERSONA
                    if es.specificity(d, "heart", "any", "any") >= 1
                    else es.RELEVANCE_GENERAL)
        assert d["relevance"] == expected
    assert any(d["relevance"] == es.RELEVANCE_PERSONA for d in docs)
    assert any(d["relevance"] == es.RELEVANCE_GENERAL for d in docs)


def test_persona_rows_rank_above_general_ones():
    docs = es.search_advisories(250, "heart", "any", "any", client=None)
    scores = [es.specificity(d, "heart", "any", "any") for d in docs]
    assert scores == sorted(scores, reverse=True)


def test_rank_advisories_never_mutates_its_input():
    before = [dict(d) for d in ADVISORIES]
    ranked = es.rank_advisories(ADVISORIES, 250, "heart", "any", "any", k=4)
    assert [dict(d) for d in ADVISORIES] == before
    assert all("relevance" not in d for d in ADVISORIES)
    assert all("relevance" in d for d in ranked)


def test_rank_advisories_returns_docs_unchanged_when_nothing_applies():
    """The ES-external-data case: a hit whose persona fields match nobody must
    still be shown rather than leaving the reader with an empty panel."""
    docs = [dict(source="X", aqi_min=0, aqi_max=999, condition="asthma",
                 activity="any", age_group="any", advice="a")]
    ranked = es.rank_advisories(docs, 250, "copd", "any", "any", k=4)
    assert [d["source"] for d in ranked] == ["X"]


def test_rank_advisories_falls_back_to_the_nearest_band():
    ranked = es.rank_advisories(ADVISORIES, 10000, "any", "any", "any", k=4)
    assert ranked
    assert all(d["aqi_max"] == 999 for d in ranked)


# --- Where relevance becomes visible to the reader -------------------------
PERSONA_ASTHMA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
                  "activity": "Outdoor exercise", "theme": "light"}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from saafsaans.web.main import app
    with TestClient(app) as c:
        yield c


def test_the_provenance_panel_separates_the_two_kinds_of_guidance(client):
    """The panel listed every source under one heading, so guidance chosen for
    the air alone looked as though it had been chosen for the reader."""
    client.post("/ask", params=PERSONA_ASTHMA, data={"question": "Can I jog?"})
    opened = client.get("/", params={**PERSONA_ASTHMA, "prov": "0"}).text
    assert "Written for your persona" in opened
    assert "General guidance for this air quality" in opened
    # The heading test_web.py pins must survive alongside them.
    assert "Published guidance used" in opened


def _stored_sources():
    """Every advisory dict held in the in-RAM transcript store."""
    from saafsaans.web import main as web_main
    return [s for store in web_main._TRANSCRIPTS.values()
            for turn in store["turns"] for s in turn.get("sources", [])]


def test_a_group_with_nothing_in_it_gets_no_heading(client):
    """An empty group must not print a heading over nothing."""
    client.post("/ask", params=PERSONA_ASTHMA, data={"question": "Can I jog?"})
    sources = _stored_sources()
    assert sources
    for source in sources:
        source["relevance"] = es.RELEVANCE_PERSONA
    opened = client.get("/", params={**PERSONA_ASTHMA, "prov": "0"}).text
    assert "Written for your persona" in opened
    assert "General guidance for this air quality" not in opened


def test_a_turn_stored_before_relevance_existed_still_renders(client):
    """The in-RAM transcript store survives this code change within one process
    lifetime, and its turns carry no relevance key at all."""
    client.post("/ask", params=PERSONA_ASTHMA, data={"question": "Can I jog?"})
    for source in _stored_sources():
        source.pop("relevance", None)
    opened = client.get("/", params={**PERSONA_ASTHMA, "prov": "0"})
    assert opened.status_code == 200
    assert "src-tag" in opened.text
    assert "Written for your persona" not in opened.text
    assert "General guidance for this air quality" in opened.text


def test_the_template_and_the_ranker_agree_on_the_tag_value():
    """The template compares against a literal. If the constant were renamed
    without it, every row would silently fall into the general group."""
    template = (Path(__file__).resolve().parents[1]
                / "saafsaans/web/templates/today.html").read_text()
    assert f"'{es.RELEVANCE_PERSONA}'" in template


def test_every_row_has_a_translated_key_shape():
    """Guards the nine new rows against a typo in a field that is part of the
    i18n key: an unknown keyword would silently never match a persona."""
    for a in ADVISORIES:
        assert a["condition"] in set(CONDITION_MAP.values()) | {"any"}
        assert a["activity"] in set(ACTIVITY_MAP.values()) | {"any"}
        assert a["age_group"] in set(AGE_MAP.values()) | {"any"}
        assert a["aqi_min"] <= a["aqi_max"]
