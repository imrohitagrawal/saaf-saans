"""Seeding must be idempotent.

The README tells people to run setup_indices.py, and an earlier version used
auto-generated document ids -- so every run appended another full copy of the 34
advisories. Retrieval then returned the same guidance several times in one
answer, which the user saw as duplicate sources in the provenance panel.
"""
from saafsaans.data.advisories import ADVISORIES
from saafsaans.setup_indices import advisory_id


def test_every_advisory_gets_a_distinct_stable_id():
    ids = [advisory_id(a) for a in ADVISORIES]
    assert len(set(ids)) == len(ADVISORIES), "advisory ids collide -- rows would overwrite"


def test_advisory_id_is_stable_across_calls_and_dict_order():
    a = ADVISORIES[0]
    reordered = {k: a[k] for k in reversed(list(a))}
    assert advisory_id(a) == advisory_id(reordered)


def test_advisory_id_changes_when_the_row_identity_changes():
    a = dict(ADVISORIES[0])
    b = {**a, "source": "SOME-OTHER-SOURCE"}
    assert advisory_id(a) != advisory_id(b)


def test_advisory_id_survives_missing_fields():
    assert advisory_id({})
