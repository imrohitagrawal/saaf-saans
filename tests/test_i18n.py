"""The Hindi corpus, checked against the English it stands in for.

The corpus lives apart from its originals (see ``services/i18n``), so nothing
but a test can notice when an English string gains a sibling and the Hindi does
not. ``test_every_translatable_string_has_a_hindi_counterpart`` is that notice:
it walks the real source dictionaries rather than a copy of their keys, so a new
advisory or a sixth risk band fails the build instead of silently rendering in
English on a page that says it is in Hindi.
"""
import ast
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


# A handful of entries are correct with no Devanagari in them at all, and both
# kinds have to be exempted by rule rather than by name, or the exemption
# becomes a list somebody adds an untranslated string to.
#
#   * pure format frames -- "{who}, {condition}" -- where every word the reader
#     sees arrives through a field and the only thing being translated is the
#     order and the punctuation between them;
#   * a value that is nothing but a term this file keeps in Latin on purpose
#     ("COPD" as a picker label).
_PLACEHOLDER = re.compile(r"{\w+}")


def _carries_translatable_text(value: str) -> bool:
    remainder = _PLACEHOLDER.sub("", value)
    for term in LATIN_TERMS + ["FFP2", "SpO2", "N95", "WHO", "WAQI"]:
        remainder = remainder.replace(term, "")
    return bool(re.search(r"[A-Za-zऀ-ॿ]", remainder))


@pytest.mark.parametrize("group", sorted(i18n.HI))
def test_every_hindi_value_contains_devanagari(group):
    latin_only = [key for key, value in i18n.HI[group].items()
                  if _carries_translatable_text(value) and not DEVANAGARI.search(value)]
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


# --- Every key the code asks for -------------------------------------------
# ``ui``, ``guide`` and the sentence groups (``answer``, ``window``, ``driver``,
# ``persona``, ``compare``, ``who``, ``prov``, ``day``) have no English source
# dictionary to walk: their strings live inline at the call site as the fallback
# argument of ``i18n.t`` / ``T`` / ``presenters._fmt``. The keys are therefore
# read back out of the code rather than listed here.
#
# An earlier version of this file pinned a hand-written list, which passed green
# while every key the templates actually asked for was missing. Two agents'
# hand-written lists then disagreed with each other. So the rule is now absolute:
# nothing in this section may name a key. Every key checked below comes either
# from parsing the source or from the same dictionaries the source indexes by.

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "saafsaans"


class _CallVisitor(ast.NodeVisitor):
    """Collect ``(group, key)`` from every translation call in one module.

    A call whose group or key is an expression rather than a literal is
    recorded as unreadable rather than skipped -- being skipped is exactly how
    the missing keys stayed hidden last time.
    """

    def __init__(self):
        self.found = set()
        self.unreadable = []

    def visit_Call(self, node):
        self.generic_visit(node)
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "t"
                and isinstance(func.value, ast.Name) and func.value.id == "i18n"):
            args = node.args[1:]          # drop lang
        elif isinstance(func, ast.Name) and func.id == "_fmt":
            args = node.args[1:]          # drop lang
        elif isinstance(func, ast.Name) and func.id == "T":
            args = node.args              # the template helper is already bound
        else:
            return
        literals = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    else None for a in args[:2]]
        if len(literals) < 2 or None in literals:
            self.unreadable.append(ast.unparse(node))
            return
        self.found.add(tuple(literals))


def _scan_python():
    found, unreadable = set(), []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        visitor = _CallVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        found |= visitor.found
        unreadable += [f"{path.name}: {call}" for call in visitor.unreadable]
    return found, unreadable


# ``{{ T('ui', 'nav_today', 'Today') }}`` in a Jinja template. Parsed as a
# Python call so a key spelled with an escape or a nested quote is read the same
# way the template engine reads it.
_TEMPLATE_CALL = re.compile(r"(?<![A-Za-z_.])T\(")


def _template_call_args(source: str, start: int) -> str:
    depth, quote, i = 1, None, start
    while i < len(source) and depth:
        char = source[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return source[start:i]


def _scan_templates():
    found, unreadable = set(), []
    for path in sorted((PACKAGE / "web/templates").glob("*.html")):
        source = path.read_text(encoding="utf-8")
        for match in _TEMPLATE_CALL.finditer(source):
            inner = _template_call_args(source, match.end())
            try:
                call = ast.parse("f(" + inner + ")", mode="eval").body
            except SyntaxError:
                unreadable.append(f"{path.name}: T({inner})")
                continue
            literals = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str)
                        else None for a in call.args[:2]]
            if len(literals) < 2 or None in literals:
                unreadable.append(f"{path.name}: T({inner})")
                continue
            found.add(tuple(literals))
    return found, unreadable


def _keys_built_at_runtime():
    """Keys the code composes from a lookup table, expanded over that table.

    ``i18n.t(lang, "driver", f"cond_{condition_kw}", ...)`` asks for one key per
    entry in ``risk._COND_LABEL``. The corpus has to carry all of them or a chip
    renders in English, so the expansion walks the real dictionary rather than a
    copy of its keys. Every source imported here is the one the call site
    itself indexes by, so a new condition or a sixth weekday fails this file.
    """
    from saafsaans.services import llm, risk
    from saafsaans.web import presenters as pr

    keys = set()
    keys |= {("driver", f"cond_{kw}") for kw in risk._COND_LABEL}
    keys |= {("driver", f"act_{kw}") for kw in risk._ACT_LABEL}
    keys |= {("driver", f"age_{kw}") for kw in risk._AGE_LABEL}
    keys |= {("persona", key) for key in pr._AGE_KEYS.values()}
    keys |= {("persona", key) for key in pr._CONDITION_KEYS.values()}
    keys |= {("persona", key) for key in pr._ACTIVITY_KEYS.values()}
    keys |= {("compare", key) for key in pr._CONDITION_REASON_KEYS.values()}
    keys |= {("compare", key) for key in pr._AGE_REASON_KEYS.values()}
    # The fallback key ``_reasons`` passes when the condition is not in the map.
    keys.add(("compare", "reason_condition"))
    keys |= {("who", f"multiple_{value}") for value in pr._MULTIPLE_WORDS}
    keys |= {("day", key) for key, _ in pr._WEEKDAYS}
    for _, slug, _, _ in llm._ACTIVITY_KEYWORDS:
        keys |= {("answer", f"activity_{slug}"), ("answer", f"precaution_{slug}")}
    # ``T('ui', 'risk_band_' ~ b.label, b.label)`` -- one label per risk band.
    keys |= {("ui", f"risk_band_{label}") for label in RISK_BANDS}
    return keys


def requested_keys():
    """Every ``(group, key)`` the application asks ``i18n.t`` for."""
    python_keys, python_unreadable = _scan_python()
    template_keys, template_unreadable = _scan_templates()
    return (python_keys | template_keys | _keys_built_at_runtime(),
            python_unreadable + template_unreadable)


# Groups whose keys come from an English source dictionary instead of a call
# site, because the call passes the source's own key through as a variable.
# "locality" is keyed by waqi.LOCALITIES rather than by literal call sites --
# see test_the_locality_names_match_the_localities_the_app_offers, which
# checks it against that list instead.
_SOURCE_KEYED = set(SOURCES) | {"locality"}


def test_the_call_site_parser_reads_the_whole_package():
    """If the parser stopped reading files, every test below would pass on an
    empty set. Assert it found the shape of the real application first."""
    found, _ = requested_keys()
    groups = {group for group, _ in found}
    assert groups >= {"ui", "guide", "answer", "window", "driver",
                      "persona", "compare", "who", "prov", "day"}
    assert len(found) > 200


def test_every_unreadable_call_is_covered_some_other_way():
    """A call whose key the parser cannot read is only safe if something else
    supplies that key: an English source dictionary, or the runtime expansion
    above. Anything else is a hole the size of the last one.

    The two exceptions are the forwarding helpers -- ``main._translator`` and
    ``presenters._fmt`` -- whose group and key are their own parameters. They
    request nothing; their callers do, and the parser reads those.
    """
    _, unreadable = requested_keys()
    covered = _SOURCE_KEYED | {group for group, _ in _keys_built_at_runtime()}
    forwarders = ("i18n.t(lang, group, key, english)",)
    uncovered = [call for call in unreadable
                 if not call.endswith(forwarders)
                 and not any(f"'{group}'" in call or f'"{group}"' in call
                             for group in covered)]
    assert not uncovered, f"translation calls nothing checks: {uncovered}"


def test_the_corpus_carries_every_key_the_code_requests():
    """The anti-hole test for everything assembled in Python.

    A key the corpus lacks is not a fallback anyone notices: it is one English
    sentence in the middle of a Hindi page, under a banner announcing Hindi.
    """
    found, _ = requested_keys()
    missing = sorted(f"{group}/{key}" for group, key in found
                     if key not in i18n.HI.get(group, {}))
    assert not missing, f"the code asks for keys the corpus lacks: {missing}"


def test_the_locality_names_match_the_localities_the_app_offers():
    """The locality group is keyed by data, not by literal call sites -- nothing
    greps as i18n.t(lang, "locality", "Rohini", ...) because it is reached
    through i18n.place() over waqi.LOCALITIES. So it is checked against that
    list directly: a station added to the picker without a Devanagari name
    would silently render Latin inside a Hindi sentence."""
    from saafsaans.services import waqi
    needed = set(waqi.LOCALITIES) | set(waqi.REGIONS)
    have = set(i18n.HI["locality"])
    assert needed <= have, f"no Devanagari name for: {sorted(needed - have)}"
    assert have <= needed, f"Devanagari name for a place the app never shows: {sorted(have - needed)}"


def test_the_corpus_carries_nothing_the_code_never_asks_for():
    """This file exists to be read by a reviewer, so a string no page renders is
    not harmless: it is prose they have to check for nothing."""
    found, _ = requested_keys()
    orphans = sorted(f"{group}/{key}"
                     for group, entries in i18n.HI.items()
                     if group not in _SOURCE_KEYED
                     for key in entries
                     if (group, key) not in found)
    assert not orphans, f"corpus keys no page asks for: {orphans}"


def test_format_fields_survive_translation():
    """A Hindi sentence may reorder ``{score}`` and ``{baseline}``; it may not
    rename or drop one. ``presenters._fmt`` would fall back to the English
    sentence, and ``llm._fill`` would leave the braces on screen for the
    reader."""
    from saafsaans.web import presenters as pr

    mismatched = []
    for group, key in requested_keys()[0]:
        hindi = i18n.HI.get(group, {}).get(key)
        if not hindi:
            continue
        english = _ENGLISH_DEFAULTS.get((group, key))
        if english is None:
            continue
        if set(_PLACEHOLDER.findall(english)) != set(_PLACEHOLDER.findall(hindi)):
            mismatched.append(f"{group}/{key}")
    assert not mismatched, f"format fields changed in: {mismatched}"


def _english_defaults():
    """``(group, key) -> english`` for every call whose fallback is a literal.

    Only literals: a fallback read out of ``risk.SOURCE_EPA`` is not text this
    file can compare against without importing half the application.
    """
    defaults = {}

    class Visitor(_CallVisitor):
        def visit_Call(self, node):
            ast.NodeVisitor.generic_visit(self, node)
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "t"
                    and isinstance(func.value, ast.Name) and func.value.id == "i18n"):
                args = node.args[1:]
            elif isinstance(func, ast.Name) and func.id in ("T", "_fmt"):
                args = node.args[1:] if func.id == "_fmt" else node.args
            else:
                return
            values = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str)
                      else None for a in args[:3]]
            if len(values) == 3 and None not in values:
                defaults[(values[0], values[1])] = values[2]

    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        Visitor().visit(ast.parse(path.read_text(encoding="utf-8")))
    for path in sorted((PACKAGE / "web/templates").glob("*.html")):
        source = path.read_text(encoding="utf-8")
        for match in _TEMPLATE_CALL.finditer(source):
            inner = _template_call_args(source, match.end())
            try:
                call = ast.parse("f(" + inner + ")", mode="eval").body
            except SyntaxError:
                continue
            values = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str)
                      else None for a in call.args[:3]]
            if len(values) == 3 and None not in values:
                defaults[(values[0], values[1])] = values[2]
    return defaults


_ENGLISH_DEFAULTS = _english_defaults()


SHARE_KEYS = {"share_title", "share_no_reading", "share_for"}


def test_the_chrome_uses_no_format_placeholders():
    """Every number, time and place name in the chrome is printed by the
    template between two fragments, so nothing there is passed through
    ``str.format``. A ``{field}`` would reach the reader as literal braces.

    The share-card keys are the documented exception: they live in <head> where
    there is no template to interleave fragments with, so the value has to be
    substituted into the string. They use ``str.replace`` rather than
    ``str.format`` precisely so a stray or mistranslated brace cannot raise on
    a path that runs on every single page render."""
    stray = [f"{group}/{key}"
             for group in ("ui", "guide")
             for key, value in i18n.HI[group].items()
             if key not in SHARE_KEYS and _PLACEHOLDER.search(value)]
    assert not stray, f"unsubstituted placeholder in: {stray}"


def test_the_share_card_placeholders_survive_translation():
    """If a translation drops {place} the card silently loses the locality; if
    it renames one, the brace reaches the reader."""
    for key, fields in (("share_title", {"{place}", "{band}"}),
                        ("share_no_reading", {"{place}"}),
                        ("share_for", {"{who}"})):
        value = i18n.HI["ui"][key]
        assert set(_PLACEHOLDER.findall(value)) == fields, (key, value)


# Polite-imperative endings in Hindi. A verdict that lacks one is describing a
# state rather than telling the reader what to do.
_IMPERATIVE = ("िए", "िये", "एँ", "ें")


def test_every_hindi_verdict_tells_the_reader_what_to_do():
    """The Very High verdict once read "आज आपके फेफड़ों को घर के अंदर रहने की
    ज़रूरत है।" -- the only one of the five with no instruction in it, and
    softer in tone than the *less* severe High band above it. So escalating
    from High to Very High made the message weaker.

    That is the same defect this project already documented in its colour ramp,
    one layer up: severity has to increase monotonically with the band, and a
    ramp that reverses is worst exactly where it matters most. Colour was
    caught by computing luminance; this one needed a Hindi speaker to read it.
    """
    from saafsaans.services import risk
    for band in risk.RISK_BANDS:
        verdict = i18n.HI["verdict"][band]
        assert any(m in verdict for m in _IMPERATIVE), (band, verdict)


def test_the_hindi_verdicts_are_all_different():
    """Two bands sharing a line would flatten the ramp just as effectively."""
    from saafsaans.services import risk
    verdicts = [i18n.HI["verdict"][b] for b in risk.RISK_BANDS]
    assert len(set(verdicts)) == len(verdicts)
