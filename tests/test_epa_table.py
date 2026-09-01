"""The inhalation rates in risk.py must equal the published table, cell by cell.

`risk.INHALATION_RATES` is the grounded half of the risk score -- `risk.py:70-72`
says so, and `HEURISTIC_NOTICE` tells the reader those numbers come from the US
EPA. Until now nothing checked that they do. The rates were three hand-typed
dicts with a comment naming their source, and a comment is satisfied by writing
it beside a fabricated number.

`tests/epa_table_6_2.json` is a transcription of EPA EFH 2011 Table 6-2 with its
provenance. These tests make the code and the source two artefacts that have to
agree, so editing either one alone goes red.

WHAT TURNS EACH TEST RED, which is the only evidence a test works:

- ``test_every_shipped_rate_equals_the_published_table``: change any digit of any
  rate in ``risk.INHALATION_RATES``, or any matching value in the fixture.
- ``test_the_fixture_still_holds_the_table_it_claims_to``: truncate the fixture,
  empty ``brackets``, or drop a bracket the app maps onto. Its partner to the
  test above -- an empty fixture would otherwise make that one pass having
  compared nothing, which is the vacuous-sweep defect
  ``tests/test_health_claims.py`` already guards against by the same means.
- ``test_the_app_maps_each_age_onto_a_bracket_the_table_publishes``: add an age
  to ``risk.INHALATION_RATES`` without adding its bracket to the fixture map.
  This is the one that fires when Gate 5 package 5b adds Teen and Youth.
"""
import json
import pathlib

import pytest

from saafsaans.services import risk

_FIXTURE = pathlib.Path(__file__).parent / "epa_table_6_2.json"
TABLE = json.loads(_FIXTURE.read_text(encoding="utf-8"))
BRACKETS = TABLE["brackets"]
AGE_TO_BRACKET = TABLE["app_bracket_for_age"]
LEVELS = ("sedentary", "light", "moderate", "high")


def test_the_fixture_still_holds_the_table_it_claims_to():
    """Non-vacuity partner. An empty fixture must fail here, not pass silently."""
    assert len(BRACKETS) == 14, "EPA Table 6-2 publishes 14 age brackets"
    for name, row in BRACKETS.items():
        assert set(row) == set(LEVELS), f"{name} is missing an activity level"
        assert all(isinstance(v, float) and v > 0 for v in row.values()), name
    # The bracket every remaining assertion depends on, named explicitly, so a
    # rename in the fixture cannot quietly empty the comparison below.
    assert "21 to <31" in BRACKETS
    assert TABLE["_source"]["units"] == "m3/minute"


@pytest.mark.parametrize("age", sorted(AGE_TO_BRACKET))
def test_the_app_maps_each_age_onto_a_bracket_the_table_publishes(age):
    assert age in risk.INHALATION_RATES, (
        f"{age} is mapped to an EPA bracket but is not a rate the app carries")
    assert AGE_TO_BRACKET[age] in BRACKETS


def test_every_age_the_app_scores_has_a_bracket_recorded_for_it():
    """The mirror of the test above -- a new age must bring its provenance.

    Without this, 5b could add "teen" to INHALATION_RATES and the sweep below
    would simply not look at it.
    """
    assert set(risk.INHALATION_RATES) == set(AGE_TO_BRACKET), (
        "every age in INHALATION_RATES needs its EPA bracket recorded in "
        f"{_FIXTURE.name}")


@pytest.mark.parametrize("age,level", [(a, lv) for a in sorted(AGE_TO_BRACKET)
                                       for lv in LEVELS])
def test_every_shipped_rate_equals_the_published_table(age, level):
    published = BRACKETS[AGE_TO_BRACKET[age]][level]
    shipped = risk.INHALATION_RATES[age][level]
    assert shipped == pytest.approx(published, rel=0, abs=1e-12), (
        f"{age}/{level} ships {shipped} but Table 6-2 publishes {published} "
        f"for {AGE_TO_BRACKET[age]}")


def test_the_baseline_is_the_bracket_the_score_says_it_is():
    """BASELINE_RATE is "a sedentary adult"; that must be EPA's 21-to-<31 row."""
    assert risk.BASELINE_RATE == pytest.approx(
        BRACKETS["21 to <31"]["sedentary"], rel=0, abs=1e-12)
