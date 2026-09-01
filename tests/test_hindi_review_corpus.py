"""Gate 5a Deliverable 1 -- the review corpus, mechanically checked.

`scripts/build_hindi_review_corpus.py` is a data-generation tool, not
user-facing behaviour, but its two promises are still testable and worth
pinning: it must not drop or duplicate a leaf string, and every group actually
present in `i18n.HI` must be classified to a surface. Both are structural
invariants a hand-maintained list would drift from silently -- exactly the
failure class `docs/PLAN-gates.md` Gate 2a records for the Devanagari floor.
"""
from saafsaans.services import i18n

from scripts import build_hindi_review_corpus as corpus_builder


def _leaf_count(node) -> int:
    return sum(1 for _ in corpus_builder._walk(node))


def test_the_corpus_has_exactly_one_row_per_leaf_string():
    """Turns red if `_walk` or `build_corpus` drops or duplicates a key --
    e.g. change `build_corpus`'s loop to `for path, hindi in
    list(_walk(i18n.HI))[:-1]` and one row goes missing.
    """
    rows = corpus_builder.build_corpus()
    assert len(rows) == _leaf_count(i18n.HI)
    assert len({r["key"] for r in rows}) == len(rows), "a key repeated in the corpus"


def test_every_group_in_i18n_hi_is_classified_to_a_surface():
    """Turns red the moment a new top-level group is added to `i18n.HI`
    without a matching entry in `GROUP_SURFACE` -- proven by removing one now
    and re-checking.
    """
    assert set(i18n.HI.keys()) <= set(corpus_builder.GROUP_SURFACE.keys())

    trimmed = dict(corpus_builder.GROUP_SURFACE)
    del trimmed[next(iter(i18n.HI.keys()))]
    assert not (set(i18n.HI.keys()) <= set(trimmed.keys())), (
        "removing one group's mapping should break coverage -- the assertion "
        "above is not vacuous"
    )


def test_the_corpus_carries_no_unclassified_surface():
    rows = corpus_builder.build_corpus()
    assert all(r["surface"] != "Unclassified" for r in rows)


def test_every_current_string_has_a_recovered_english_source():
    """Every leaf string in `i18n.HI` at this commit resolves to a literal or
    dict-backed English default (see `_dict_backed_defaults`'s docstring for
    the full list of sources). This is a measured fact about the corpus
    today, not a guarantee about tomorrow's: a key reached only through a
    genuinely novel dynamic call site will need a new resolver added here,
    the same way each of the ones already listed was found. Turns red if a
    resolver above regresses (e.g. delete the `risk.BAND_ADVICE` loop from
    `_dict_backed_defaults`) -- every `band_advice.*` row loses its English.
    """
    rows = corpus_builder.build_corpus()
    missing = [r["key"] for r in rows if r["english"] is None]
    assert missing == [], f"{len(missing)} rows with no recovered English: {missing[:10]}"


def test_the_corpus_orders_today_and_city_before_guide():
    """Reader-impact ordering (design doc §5, Deliverable 1): Today and City
    Pulse strings first. Checked with one known key from each end rather than
    a substring match on the surface label, so a relabelling of `GROUP_SURFACE`
    that keeps the ranking correct does not need to update this test.
    """
    rows = corpus_builder.build_corpus()
    keys = [r["key"] for r in rows]
    assert keys.index("verdict.Low") < keys.index("guide.sub")
    assert keys.index("city.summary") < keys.index("guide.sub")


def test_the_corpus_is_reproducible():
    """Exit criterion: running the builder twice against the same source
    produces the same corpus. No timestamp, no randomness, no unsorted
    filesystem walk feeds into it.
    """
    assert corpus_builder.build_corpus() == corpus_builder.build_corpus()


def test_the_measured_size_is_reported_against_the_design_docs_515():
    """`docs/superpowers/specs/2026-09-01-persona-truth-design.md` pins the
    corpus at 515 leaf strings, commit `450188c`, and says explicitly that
    5b/5c will have added strings by the time 5a runs. This does not assert
    an exact count -- that would be the constant-under-test antipattern -- it
    only proves the comparison the script prints is against a real, larger
    corpus, not a shrunk one silently passing as compliant.
    """
    rows = corpus_builder.build_corpus()
    assert len(rows) > 515
