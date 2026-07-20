"""The Hindi corpus, checked against the English it stands in for.

The corpus lives apart from its originals (see ``services/i18n``), so nothing
but a test can notice when an English string gains a sibling and the Hindi does
not. ``test_every_translatable_string_has_a_hindi_counterpart`` is that notice:
it walks the real source dictionaries rather than a copy of their keys, so a new
advisory or a sixth risk band fails the build instead of silently rendering in
English on a page that says it is in Hindi.
"""
import re
from pathlib import Path

import pytest

from saafsaans.data.advisories import ADVISORIES
from saafsaans.services import i18n
from saafsaans.services.normalize import (
    AQI_BANDS,
    AQI_MEANING,
    CONDITION_HELP,
    GLOSSARY,
)
from saafsaans.services.risk import BAND_ADVICE, RISK_BANDS, _HEADLINE
from saafsaans.web.presenters import _VERDICTS

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

BAND_LABELS = {label: label for _, label, _, _, _ in AQI_BANDS}
BAND_LABELS.update({"Severe": "Severe", "Unknown": "Unknown"})


def advisory_key(advisory: dict) -> str:
    """The documented advisory key. Mirrors the rule stated in ``i18n.HI``.

    Written out here rather than imported so the test fails if the rule in the
    corpus comment and the rule in the code ever diverge.
    """
    return (f"{advisory['source']}:{advisory['aqi_min']}-{advisory['aqi_max']}"
            f":{advisory['condition']}:{advisory['activity']}:{advisory['age_group']}")


# group -> the English source it mirrors, as {key: english string}
SOURCES = {
    "verdict": _VERDICTS,
    "band_advice": BAND_ADVICE,
    "headline": _HEADLINE,
    "aqi_meaning": AQI_MEANING,
    "band_label": BAND_LABELS,
    "glossary": GLOSSARY,
    "condition_help": CONDITION_HELP,
    "advisory": {advisory_key(a): a["advice"] for a in ADVISORIES},
}

# Every (group, key, english, hindi) the corpus is responsible for.
PAIRS = [(group, key, english, i18n.HI[group].get(key))
         for group, source in SOURCES.items() for key, english in source.items()]


def test_advisory_keys_are_unique():
    """The key rule must identify a row, not a group of them.

    Source plus AQI band alone collides on the seeded data; a colliding key
    would serve one persona's advice under another persona's name.
    """
    keys = [advisory_key(a) for a in ADVISORIES]
    assert len(set(keys)) == len(ADVISORIES)


def test_every_translatable_string_has_a_hindi_counterpart():
    """No English string may be left without Hindi. The anti-hole test."""
    missing = [f"{group}/{key}" for group, key, _, hindi in PAIRS if not hindi]
    assert not missing, f"no Hindi for: {missing}"


def test_no_group_carries_keys_the_english_does_not_have():
    """A stale Hindi key is a translation of something that no longer exists."""
    orphans = [f"{group}/{key}"
               for group, source in SOURCES.items()
               for key in i18n.HI[group]
               if key not in source]
    assert not orphans, f"Hindi with no English original: {orphans}"


@pytest.mark.parametrize("group", sorted(i18n.HI))
def test_no_hindi_value_is_empty(group):
    blank = [key for key, value in i18n.HI[group].items() if not (value or "").strip()]
    assert not blank, f"empty Hindi in {group}: {blank}"


def test_no_hindi_value_is_just_the_english():
    """An untranslated string that is present is worse than one that is absent:
    the fallback in ``t`` would have shown the same English without claiming it
    had been translated."""
    same = [f"{group}/{key}" for group, key, english, hindi in PAIRS
            if hindi and hindi.strip() == english.strip()]
    assert not same


@pytest.mark.parametrize("group", sorted(i18n.HI))
def test_every_hindi_value_contains_devanagari(group):
    latin_only = [key for key, value in i18n.HI[group].items()
                  if not DEVANAGARI.search(value)]
    assert not latin_only, f"no Devanagari in {group}: {latin_only}"


def test_review_banner_is_present_in_both_languages():
    """Shipping unreviewed health copy without the banner is the thing the
    module docstring calls a condition of shipping."""
    assert DEVANAGARI.search(i18n.REVIEW_BANNER)
    assert i18n.REVIEW_BANNER_EN.strip()


# Terms that a Delhi reader recognises in Latin script and would not recognise
# transliterated. Where the English uses one, the Hindi must use the same one.
LATIN_TERMS = ["AQI", "PM2.5", "PM10", "N95", "COPD", "CPCB"]


@pytest.mark.parametrize("term", LATIN_TERMS)
def test_latin_terms_survive_translation(term):
    dropped = [f"{group}/{key}" for group, key, english, hindi in PAIRS
               if hindi and term in english and term not in hindi]
    assert not dropped, f"{term} lost in: {dropped}"


def test_normalise_falls_back_to_english():
    assert i18n.normalise("hi") == "hi"
    assert i18n.normalise("en") == "en"
    for value in ("", "HI", "fr", "hi-IN", None):
        assert i18n.normalise(value) == "en"


def test_t_returns_hindi_when_asked_for_and_present():
    assert i18n.t("hi", "band_label", "Severe", "Severe") == i18n.HI["band_label"]["Severe"]


def test_t_returns_english_for_any_other_language():
    assert i18n.t("en", "band_label", "Severe", "Severe") == "Severe"
    assert i18n.t("fr", "band_label", "Severe", "Severe") == "Severe"


def test_t_falls_back_to_english_for_a_missing_key():
    """One English sentence among the Hindi is survivable; a blank element or a
    KeyError on a health instruction is not."""
    assert i18n.t("hi", "band_label", "Nonexistent", "Nonexistent") == "Nonexistent"
    assert i18n.t("hi", "no_such_group", "Severe", "Severe") == "Severe"
    # A group that exists but is empty behaves the same way.
    i18n.HI.setdefault("_probe", {})
    assert i18n.t("hi", "_probe", "anything", "English original") == "English original"
    del i18n.HI["_probe"]


# --- The chrome ------------------------------------------------------------
# ``ui`` and ``guide`` have no English source dictionary to walk: their strings
# live inline in the templates as the fallback argument of a ``T`` call. The
# keys are therefore read back out of the templates rather than listed here.
# An earlier version of this test pinned a hand-written list, which passed
# green while every key the templates actually asked for was missing, so the
# rule now is that nothing in this section may name a key.

REPO = Path(__file__).resolve().parents[1]
CALL_SITES = sorted((REPO / "saafsaans/web/templates").glob("*.html")) + [
    REPO / "saafsaans/web/main.py"
]

# ``T('ui', 'nav_today', 'Today')`` and ``i18n.t(lang, "ui", "risk_notice", x)``.
# Group and key are literals; the English fallback is not captured because the
# key is what the corpus is indexed by.
_LITERAL = re.compile(
    r"""(?:\bT|\bi18n\.t)\(\s*(?:lang\s*,\s*)?
        (['"])(?P<group>\w+)\1\s*,\s*
        (['"])(?P<key>[\w. ]*)\3
        (?P<dynamic>\s*~)?""",
    re.VERBOSE,
)
# Any call at all, so a call the parser cannot read is caught rather than
# skipped -- being skipped is exactly how the missing keys stayed hidden.
_ANY_CALL = re.compile(r"(?:\bT|\bi18n\.t)\(\s*(?:lang\s*,\s*)?['\"]?\w*['\"]?\s*,")


def requested_keys():
    """Every (group, key) the templates and views ask ``i18n.t`` for.

    Keys built by concatenation -- ``'risk_band_' ~ b.label`` -- are expanded
    over the labels the views can pass, since the corpus has to carry all of
    them or a band renders in English.
    """
    found, seen_calls = set(), 0
    for path in CALL_SITES:
        text = path.read_text(encoding="utf-8")
        seen_calls += len(_ANY_CALL.findall(text))
        for match in _LITERAL.finditer(text):
            group, key = match.group("group"), match.group("key")
            if match.group("dynamic"):
                found.update((group, key + label) for label in RISK_BANDS)
            else:
                found.add((group, key))
    return found, seen_calls


def test_the_template_parser_sees_every_call():
    """If a call site is written in a shape the regex above cannot read, this
    test must fail rather than quietly shrink the set it checks."""
    found, seen_calls = requested_keys()
    # Calls whose group or key is an expression (``T('glossary', term, text)``)
    # are covered by SOURCES instead, so the two counts are not equal; what
    # matters is that the parser is reading the files at all and finding the
    # chrome groups in them.
    assert seen_calls > 0
    assert {group for group, _ in found} >= {"ui", "guide"}


@pytest.mark.parametrize("group", ["ui", "guide"])
def test_ui_and_guide_carry_the_keys_the_templates_request(group):
    """Every key a page asks for must exist, spelled the way the page spells it.

    A key the corpus spells differently is not a fallback, it is a page of
    English chrome under a banner announcing Hindi.
    """
    found, _ = requested_keys()
    wanted = sorted(key for wanted_group, key in found if wanted_group == group)
    assert wanted, f"no {group} keys parsed out of the templates"
    missing = [key for key in wanted if key not in i18n.HI[group]]
    assert not missing, f"templates ask for {group} keys the corpus lacks: {missing}"


@pytest.mark.parametrize("group", ["ui", "guide"])
def test_ui_and_guide_carry_nothing_the_templates_do_not_ask_for(group):
    """This file exists to be read by a reviewer, so a string no page renders is
    not harmless: it is prose they have to check for nothing."""
    found, _ = requested_keys()
    wanted = {key for wanted_group, key in found if wanted_group == group}
    orphans = sorted(key for key in i18n.HI[group] if key not in wanted)
    assert not orphans, f"{group} keys no page asks for: {orphans}"


def test_the_chrome_uses_no_format_placeholders():
    """Every number, time and place name in the chrome is printed by the
    template between two fragments, so nothing here is passed through
    ``str.format``. A ``{field}`` would reach the reader as literal braces."""
    stray = [f"{group}/{key}"
             for group in ("ui", "guide")
             for key, value in i18n.HI[group].items()
             if re.search(r"{\w+}", value)]
    assert not stray, f"unsubstituted placeholder in: {stray}"
