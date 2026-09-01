"""Gate 5a Deliverable 4 -- the pinning test.

Every leaf string in `i18n.HI` must sit in exactly one of two committed
records: `docs/hindi-review/signed_off.json` (empty today -- no Hindi
reviewer exists yet, Deliverable 2 is not started) or
`docs/hindi-review/unreviewed.json` (auto-generated, so it cannot drift from
the corpus by hand-editing -- see `scripts/generate_hindi_unreviewed_list.py`).

This does not gate anything else. It does not touch the review banner, and it
does not decide what "signed off" means for a string -- it only proves,
mechanically, that every current string is accounted for, so a future
reviewer's sign-off can move one key at a time from `unreviewed.json` to
`signed_off.json` with the suite catching any key that falls through the
crack in between.
"""
import json
import pathlib

import pytest

from saafsaans.services import i18n

from scripts.build_hindi_review_corpus import GROUP_SURFACE, _walk

RECORD_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs" / "hindi-review"


def _load(name: str) -> list:
    return json.loads((RECORD_DIR / name).read_text())


def real_leaf_keys() -> set:
    return {".".join(path) for path, _hindi in _walk(i18n.HI)}


def check_coverage(leaf_keys, signed_off_keys, unreviewed_keys) -> list:
    """Every problem with this partition, as a list of human-readable strings.

    Empty means: every leaf key is in exactly one of the two sets, and
    neither set carries a key that is not a leaf at all. This is the pure
    logic the pinning test below asserts over the real corpus and records --
    kept separate so the bite-proof cases can exercise it directly, without
    needing to actually mutate `i18n.HI` or the committed JSON files.
    """
    signed_off_keys = set(signed_off_keys)
    unreviewed_keys = set(unreviewed_keys)
    leaf_keys = set(leaf_keys)
    problems = []

    duplicated = signed_off_keys & unreviewed_keys
    for key in sorted(duplicated):
        problems.append(f"{key}: listed as both signed-off and unreviewed")

    accounted = signed_off_keys | unreviewed_keys
    for key in sorted(leaf_keys - accounted):
        problems.append(f"{key}: in i18n.HI but on neither list -- fails closed")

    for key in sorted(signed_off_keys - leaf_keys):
        problems.append(f"{key}: signed off but not a leaf string in i18n.HI")
    for key in sorted(unreviewed_keys - leaf_keys):
        problems.append(f"{key}: unreviewed but not a leaf string in i18n.HI")

    return problems


# --- The pinning test itself, over the real corpus and the real records ---

def test_every_current_hindi_string_is_accounted_for():
    """Fails closed: a leaf string in `i18n.HI` that is in neither committed
    record turns this test -- and so the suite -- red. Proven directly below
    (`test_an_orphan_key_fails_closed`) without needing to mutate `i18n.HI` or
    the JSON files themselves.
    """
    problems = check_coverage(
        real_leaf_keys(),
        (row["key"] for row in _load("signed_off.json")),
        (row["key"] for row in _load("unreviewed.json")),
    )
    assert problems == [], "\n".join(problems)


# --- Bite-proof, both directions -------------------------------------------

def test_an_orphan_key_fails_closed():
    """A key in neither list turns the check red. Turns green again the
    moment that key is added to either set -- proving the direction of the
    failure, not just that *a* failure occurred.
    """
    leaves = {"verdict.Low", "verdict.Moderate"}
    signed_off = set()
    unreviewed = {"verdict.Low"}  # verdict.Moderate is the orphan

    problems = check_coverage(leaves, signed_off, unreviewed)
    assert any("verdict.Moderate" in p and "neither list" in p for p in problems)

    fixed = check_coverage(leaves, signed_off, unreviewed | {"verdict.Moderate"})
    assert fixed == []


def test_a_key_listed_on_both_sets_fails_closed():
    """A key wrongly duplicated across signed-off and unreviewed is itself a
    defect -- it means either the generator and the hand-maintained file have
    drifted, or a sign-off was recorded without removing the key from the
    unreviewed list. Both are worth a red suite, not a silent double-count.
    """
    leaves = {"verdict.Low"}
    signed_off = {"verdict.Low"}
    unreviewed = {"verdict.Low"}

    problems = check_coverage(leaves, signed_off, unreviewed)
    assert any("verdict.Low" in p and "both" in p for p in problems)

    fixed = check_coverage(leaves, signed_off, unreviewed - {"verdict.Low"})
    assert fixed == []


# --- Non-vacuity partner ----------------------------------------------------
# Mirrors tests/test_health_claims.py:276-298's shape: assert the set that is
# actually populated today (unreviewed, not signed-off -- nothing is signed
# off yet) is non-empty, and reaches at least the Today surface and the three
# key prefixes the design doc names.

def test_the_unreviewed_list_is_not_vacuous():
    rows = _load("unreviewed.json")
    keys = [row["key"] for row in rows]
    assert len(keys) > 300, "the unreviewed list should hold the whole corpus, not a stub"

    today_groups = {g for g, surface in GROUP_SURFACE.items() if "Today" in surface}
    assert any(key.split(".", 1)[0] in today_groups for key in keys), (
        "the unreviewed list does not cover the Today surface at all"
    )

    for prefix in ("verdict.", "band_advice.", "persona."):
        assert any(key.startswith(prefix) for key in keys), (
            f"no unreviewed key starts with {prefix!r}"
        )


def test_the_signed_off_list_is_empty_today_and_says_why():
    """Constraint (i), honesty over polish: no reviewer exists, so nothing is
    signed off, and this is asserted rather than left to be inferred from an
    empty file with no explanation. If this test ever needs to change because
    a real sign-off landed, `unreviewed.json` must shrink by exactly the same
    keys -- `test_every_current_hindi_string_is_accounted_for` polices that.
    """
    assert _load("signed_off.json") == []
