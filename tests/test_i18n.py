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


# The share card lives in <head>, where there is no template to interleave
# fragments with, so these are the keys whose values legitimately carry a
# placeholder. There is no longer a `share_title_sample`: a fallback carries no
# AQI, so it takes the no-reading card and there is no band to hedge.
SHARE_KEYS = {"share_title", "share_no_reading", "share_held", "share_for"}


def test_every_exempted_key_really_is_a_share_card_key():
    """Guards the exemption above from being used as a way to go green.

    SHARE_KEYS is hand-written, and the test it feeds only ever gets LOOSER as
    the set grows -- so a key added here to silence a genuine stray placeholder
    would never be noticed. Every member must actually be requested by
    ``main.today_share_card``, which is the only builder allowed to substitute
    into a translated string; anything else with a placeholder is a defect.
    """
    import inspect

    from saafsaans.web import main

    source = inspect.getsource(main.today_share_card)
    for key in SHARE_KEYS:
        assert f'"{key}"' in source, (
            f"{key} is exempted from the placeholder rule but is not a share "
            f"card key")


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


# Polite-imperative endings in Hindi. A line that carries none of them is
# describing a state rather than telling the reader what to do.
#
# Matched at the END OF A TOKEN, not anywhere in the string. Substring matching
# was the rule until 2026-08-31, and it was blind: "में" ends in "ें" and "लिए"
# ends in "िए", so "आज की हवा बाहर मेहनत वाले कामों में भारी है।" -- a pure
# description with no instruction in it -- satisfied the check. Those two words
# and their spelling variants are the exclusions; the -ाइए forms (चलाइए,
# बिताइए) are added because the polite imperative takes the independent vowel
# after a vowel stem and the matra "िए" does not appear in them at all.
# "आइए"/"आइये" are the same ending after a stem that leaves the vowel
# independent ("बाहर घूम आइए"); without them the rule rejects a real
# imperative, which is the mirror of the hole it was written to close.
_IMPERATIVE = ("िए", "िये", "ाइए", "ाइये", "आइए", "आइये",
               "एँ", "ाएँ", "ें", "ाएं")
# Common words that end in an imperative ending and are not imperatives.
_NOT_IMPERATIVE = {"में", "लिए", "लिये", "नहीं", "कहीं", "यहीं", "वहीं",
                   "किए", "किये"}


def carries_an_imperative(text: str) -> bool:
    """True when some whole word in ``text`` is a polite imperative."""
    for token in re.split(r"[\s।,;:—\-]+", text):
        token = token.strip("।.,;:!?()")
        if not token or token in _NOT_IMPERATIVE:
            continue
        if any(token.endswith(ending) for ending in _IMPERATIVE):
            return True
    return False


# Descriptions with no instruction in them. Three of these passed the substring
# rule; they are kept as data so the rule cannot quietly go back to it.
_DESCRIPTIONS_NOT_INSTRUCTIONS = (
    "आज की हवा बाहर मेहनत वाले कामों में भारी है।",
    "आज की हवा बाहर मेहनत वाले काम के लिए भारी है।",
    "आज हवा बहुत ख़राब है।",
    "यह हवा आपके फेफड़ों के लिए ठीक नहीं है।",
)


def test_every_hindi_verdict_tells_the_reader_what_to_do():
    """The Very High verdict once read "आज आपके फेफड़ों को घर के अंदर रहने की
    ज़रूरत है।" -- the only one of the five with no instruction in it, and
    softer in tone than the *less* severe High band above it. So escalating
    from High to Very High made the message weaker.

    That is the same defect this project already documented in its colour ramp,
    one layer up: severity has to increase monotonically with the band, and a
    ramp that reverses is worst exactly where it matters most. Colour was
    caught by computing luminance; this one needed a Hindi speaker to read it.
    Swept over every key in ``i18n.HI["verdict"]``, not ``risk.RISK_BANDS``:
    since Gate 5 package 5c, High/Very High/Extreme each carry five driver
    variants and there is no bare "High" key to iterate by band alone.
    """
    for key, verdict in i18n.HI["verdict"].items():
        assert carries_an_imperative(verdict), (key, verdict)


def test_the_hindi_verdicts_are_all_different():
    """Two keys sharing a line would flatten the ramp, or collapse two
    drivers into one sentence, just as effectively."""
    verdicts = list(i18n.HI["verdict"].values())
    assert len(set(verdicts)) == len(verdicts)


# --- What to do, not only what to avoid ------------------------------------
# Three of the five band-advice lines opened with a prohibition, in both
# languages, and so did the High headline and the Extreme verdict -- the first
# substantive sentence on the page. A reader with a school run to do was told
# what not to do and left to work out the rest.
#
# "Prohibition-only" is not decidable by machine. What is decidable is whether
# the sentence OPENS with one, which is the shape the defect actually took and
# is where a reader in a hurry stops reading. The opening is the first clause:
# everything before the first band separator, danda, full stop, em dash or
# comma. Both languages are searched the same way -- an earlier draft matched
# English at the start of the clause and Hindi anywhere inside it, which is two
# rules wearing one name.
# No bare "no" in the list. It flagged "There is no need to change your plans
# today." -- a positive instruction -- and none of the sentences this rule was
# written against needs it.
_EN_PROHIBITION = re.compile(
    r"\b(?:do not|don'?t|never|avoid|skip|refrain from|steer clear|stay off)\b",
    re.I)
# मत and नहीं are unambiguous. A bare न is the negator only as its own word --
# inside a word (रहने, कने) it is an ordinary consonant, so it is matched only
# when neither neighbour is Devanagari. The avoid-verbs are listed because
# Hindi has no single word for English's "avoid": बचें, छोड़ दें and टाल दें each
# carry it, and without them the Hindi half of this rule was weaker than the
# English half over the same defect.
# The bare न is matched only when the verb after it makes the clause a
# prohibition. Hindi puts the negator before the verb, not at the front of the
# sentence, so "any standalone न" flagged well-formed positive instructions --
# "जब तक कोई रीडिंग न मिले, ... N95 पहनें।" (the shipped no-reading lever),
# "बाहर वही काम रखिए जो टाला न जा सके।", "तबीयत ठीक न लगे तो डॉक्टर को दिखाइए।"
# All three tell the reader to do something.
_HI_PROHIBITION = re.compile(
    r"(?:मत|नहीं|बच(?:ें|िए|ना)|छोड़\s*द|टाल\s*द"
    r"|(?<![\u0900-\u097F])न\s+"
    r"(?:करें|कीजिए|कीजिये|करिए|जाएँ|जाएं|जाइए|निकलें|निकलिए|रखें|रखिए|पहनें))")

# The sentences this rule was written against, quoted rather than imported:
# they no longer exist in the source, so importing them is impossible, and
# reading the rule's own input off the shipped strings would make the partner
# test below circular.
_REPLACED_PROHIBITIONS = {
    "en": ("Skip outdoor exercise. Keep trips short and wear an N95 outside.",
           "Do not go outdoors. Seal windows, keep a purifier running, and "
           "seek care if you feel unwell.",
           "High risk -- avoid outdoor exertion today",
           "Don't go out unless you must — this air is dangerous for you."),
    "hi": ("बाहर कसरत मत कीजिए। बाहर जाना कम रखिए और बाहर N95 मास्क पहनिए।",
           "बाहर मत निकलिए। खिड़कियाँ बंद रखिए, प्यूरीफ़ायर चलाते रहिए, और तबीयत "
           "ख़राब लगे तो डॉक्टर को दिखाइए।",
           "ज़्यादा ख़तरा -- आज बाहर मेहनत वाला काम न करें",
           "बहुत ज़रूरी न हो तो बाहर मत निकलिए — यह हवा आपके लिए ख़तरनाक है।"),
}


# Rephrasings that mean the same thing and dodged an earlier draft of the rule.
# Kept as data next to the rule so widening it stays honest: each of these must
# be caught, and every shipped sentence must still pass.
_NOT_PROHIBITIONS = {
    "en": ("There is no need to change your plans today.",
           "Keep the day as planned.",
           "Move exercise indoors today."),
    "hi": ("जब तक कोई रीडिंग न मिले, बाहर का कोई भी काम कम समय का रखें और N95 पहनें।",
           "बाहर वही काम रखिए जो टाला न जा सके।",
           "तबीयत ठीक न लगे तो डॉक्टर को दिखाइए।"),
}

_ALSO_PROHIBITIONS = {
    "en": ("Head out, but do not exercise outdoors.",
           "Refrain from outdoor exertion.",
           "Steer clear of the roadside today.",
           "Stay off the main roads this afternoon.",
           # After the dash, which is where every verdict puts its instruction.
           "Today is dangerous for you — do not go out, never exercise "
           "outdoors, and avoid the roadside.",
           "High risk -- avoid the roadside"),
    "hi": ("बाहर जाने से बचें, घर के अंदर रहें।",
           "बाहर कसरत छोड़ दीजिए।",
           "आज बाहर का काम टाल दें।",
           "बाहर की मेहनत से बचिए।",
           "आज का दिन आपके लिए ख़तरनाक है — बाहर मत निकलिए।",
           "अत्यधिक ख़तरा -- बाहर मेहनत वाला काम न करें"),
}


def _band_keyed_sentences(lang):
    """Every sentence a risk band can put in front of a reader, by group.

    All three groups, not two. `presenters._VERDICTS` is the <h1> and is also
    the share card's og:description, and it was changed by the same package
    that added this rule -- a rule over the two invisible-to-the-reader sets
    and not over the visible one would be the exact hole PLAN-gates.md's
    2026-08-31 correction is about.

    "verdict" walks `presenters._VERDICTS` by its own keys, not by
    `risk.RISK_BANDS`: since Gate 5 package 5c, High/Very High/Extreme each
    carry five driver variants ("High_lungs", "High_heart", ...), and
    `_VERDICTS` has no bare "High" key any more. band_advice and headline
    stay one-per-band.
    """
    from saafsaans.services import risk
    from saafsaans.web import presenters

    for key, text in presenters._VERDICTS.items():
        yield "verdict", key, i18n.t(lang, "verdict", key, text)
    for band in risk.RISK_BANDS:
        for group, source in (("band_advice", risk.BAND_ADVICE),
                              ("headline", risk._HEADLINE)):
            yield group, band, i18n.t(lang, group, band, source[band])


def _clauses(text: str):
    """Every clause in the sentence, in order.

    EVERY clause, not the first. Two earlier drafts judged only the opening and
    both were blind in the same place: the em dash separates the situation from
    the instruction in all ten verdicts, so a rule that stops at the dash never
    reads a single verdict's instruction. "Today is dangerous for you -- do not
    go out, never exercise outdoors, and avoid the roadside." passed, as the
    <h1> and as the share card description, carrying the literal sentence this
    package removed.

    No comma in the split set. A draft had one, and it cut the clause so short
    that "Head out, but do not exercise outdoors." was judged on "Head out".
    """
    body = text.replace("--", "—")
    return [c.strip() for c in re.split(r"[.।;—]", body) if c.strip()]


def _opening(text: str) -> str:
    """The clause a reader meets first. Reporting only -- the rule reads all."""
    clauses = _clauses(text)
    return clauses[0] if clauses else ""


def _is_prohibition(text: str, lang: str) -> bool:
    pattern = _HI_PROHIBITION if lang == "hi" else _EN_PROHIBITION
    return any(pattern.search(clause) for clause in _clauses(text))


@pytest.mark.parametrize("lang", ("en", "hi"))
def test_no_band_keyed_sentence_opens_with_a_prohibition(lang):
    """Turns red when: any of the twenty-seven sentences a band can put in
    front of a reader starts by naming what not to do instead of what to do."""
    offenders = [f"{group}/{band}: {text}"
                 for group, band, text in _band_keyed_sentences(lang)
                 if _is_prohibition(text, lang)]
    assert not offenders, "opens with a prohibition:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("lang", ("en", "hi"))
def test_the_prohibition_rule_catches_the_sentences_it_replaced(lang):
    """The partner. The rule above asserts an ABSENCE, and an absence is
    satisfied by a pattern that matches nothing -- replace either regex with
    `(?!)` and it passes for ever over a corpus it never judged.

    So it is run against the four sentences per language that shipped until
    2026-08-31, one from each of the three groups plus the Extreme verdict,
    all of which it must catch; and against the twenty-seven that ship now,
    none of which it may.

    What it does NOT claim: a prohibition moved out of the opening clause is
    not caught. "Keep trips short and wear an N95 outside. Skip outdoor
    exercise." passes. The rule is about the sentence a reader meets first,
    and it says so in its name."""
    for old in _REPLACED_PROHIBITIONS[lang]:
        assert _is_prohibition(old, lang), (lang, old)
    # Four more per language, none of which the rule caught in an earlier
    # draft: three because the opening was cut at a comma, and the Hindi
    # avoid-verbs because the word list had no equivalent of "avoid".
    for phrasing in _ALSO_PROHIBITIONS[lang]:
        assert _is_prohibition(phrasing, lang), (lang, phrasing)
    # And the other direction, which is where a widened rule does its damage:
    # positive instructions that happen to contain a negator. Hindi puts the
    # negator before the verb, so a rule matching any standalone न flagged the
    # shipped no-reading lever.
    for positive in _NOT_PROHIBITIONS[lang]:
        assert not _is_prohibition(positive, lang), (lang, positive)
    for group, band, text in _band_keyed_sentences(lang):
        assert not _is_prohibition(text, lang), (lang, group, band)


def test_every_hindi_band_advice_tells_the_reader_what_to_do():
    """The sibling of test_every_hindi_verdict_tells_the_reader_what_to_do.

    Not leading with a prohibition is not the same as saying anything. A Hindi
    line that only describes the air would pass the rule above and leave the
    reader with nothing, so the advice line carries the same polite-imperative
    floor the verdict already carries.

    Turns red when: a Hindi band advice becomes a description rather than an
    instruction."""
    from saafsaans.services import risk
    for band in risk.RISK_BANDS:
        advice = i18n.HI["band_advice"][band]
        assert carries_an_imperative(advice), (band, advice)


def test_no_band_advice_carries_a_character_html_escaping_changes():
    """tests/test_unknown_aqi.py counts `risk.BAND_ADVICE[band]` in the page
    body WITHOUT unescaping it, so an apostrophe turns that assertion into a
    search for a string the page cannot contain and the test passes having
    matched nothing.

    That was live until 2026-08-31: `BAND_ADVICE["Moderate"]` contained
    "you're", and the count assertion was green only because its fixtures land
    on High and Extreme. A constraint kept by luck is not a constraint.

    Turns red when: any band advice gains ' " & < or >."""
    from markupsafe import escape
    from saafsaans.services import risk
    unsafe = {band: text for band, text in risk.BAND_ADVICE.items()
              if str(escape(text)) != text}
    assert not unsafe, f"escaping changes these, so the count test goes blind: {unsafe}"
    # The partner: prove the check can see one. Without this, an escape() that
    # stopped escaping anything would leave the sweep above green for ever.
    assert str(escape("Skip it, you're done.")) != "Skip it, you're done."


@pytest.mark.parametrize("description", _DESCRIPTIONS_NOT_INSTRUCTIONS)
def test_the_imperative_rule_rejects_a_sentence_that_only_describes(description):
    """The partner both imperative tests need.

    They assert a PRESENCE, and a presence is satisfied by a check that returns
    True for everything -- which is what the substring rule did. Three of these
    four sentences passed it, because "में" and "लिए" carry the endings it was
    looking for. Swapping a Hindi band advice for one of them left the whole
    file green.

    Turns red when: the rule goes back to matching an ending anywhere in the
    string instead of at the end of a word."""
    assert not carries_an_imperative(description), description


# --- The ramp, pinned -------------------------------------------------------
# A REGRESSION GUARD, not a bite-proof, and labelled so on purpose -- the same
# form and the same reason as GOLDEN_WINDOWS in test_window_at_the_hour.py.
#
# `presenters._VERDICTS` claims to be monotone in words as well as in colour,
# and nothing could check it: an adversarial pass reversed all five English
# verdicts, so Extreme printed "Today is an easy one for you", and the whole
# suite stayed green. Severity order in prose is not decidable by machine, and
# no rule here pretends to decide it. What this does is make any change to the
# seventeen sentences a reader can meet first show up as a diff a person has
# to read, with the bands (and, since Gate 5 package 5c, the drivers within
# each band) in order beside them.
GOLDEN_VERDICTS = """
Low                  | Today is an easy one for you — go and use it.
Moderate             | Today is manageable for you — take it at an easy pace.
High_none            | Today is hard on you — cut the exertion.
High_lungs           | Today is hard on lungs like yours — cut the exertion.
High_heart           | Today is hard on a heart like yours — cut the exertion.
High_pregnancy       | Today is hard on you and your pregnancy — cut the exertion.
High_age             | Today is hard on a body like yours — cut the exertion.
Very High_none       | Today is a serious strain for you — keep it to what has to be done.
Very High_lungs      | Today is a serious strain on lungs like yours — keep it to what has to be done.
Very High_heart      | Today is a serious strain on a heart like yours — keep it to what has to be done.
Very High_pregnancy  | Today is a serious strain on you and your pregnancy — keep it to what has to be done.
Very High_age        | Today is a serious strain on a body like yours — keep it to what has to be done.
Extreme_none         | Today is dangerous for you — let only the unavoidable take you outside.
Extreme_lungs        | Today is dangerous for lungs like yours — let only the unavoidable take you outside.
Extreme_heart        | Today is dangerous for a heart like yours — let only the unavoidable take you outside.
Extreme_pregnancy    | Today is dangerous for you and your pregnancy — let only the unavoidable take you outside.
Extreme_age          | Today is dangerous for a body like yours — let only the unavoidable take you outside.
"""

GOLDEN_VERDICTS_HI = """
Low                  | आज का दिन आपके लिए आसान है — बाहर निकलिए और दिन का फ़ायदा उठाइए।
Moderate             | आज का दिन आपके लिए ठीक-ठाक है — रफ़्तार आराम की रखिए।
High_none            | आज का दिन आपके लिए मुश्किल है — आज मेहनत कम कीजिए।
High_lungs           | आज का दिन आपके जैसे फेफड़ों के लिए मुश्किल है — आज मेहनत कम कीजिए।
High_heart           | आज का दिन आपके जैसे दिल के लिए मुश्किल है — आज मेहनत कम कीजिए।
High_pregnancy       | आज का दिन आपके और आपकी गर्भावस्था के लिए मुश्किल है — आज मेहनत कम कीजिए।
High_age             | आज का दिन आपके जैसे शरीर के लिए मुश्किल है — आज मेहनत कम कीजिए।
Very High_none       | आज का दिन आप पर भारी पड़ रहा है — आज सिर्फ़ वही काम कीजिए जो ज़रूरी हैं।
Very High_lungs      | आज का दिन आपके जैसे फेफड़ों पर भारी पड़ रहा है — आज सिर्फ़ वही काम कीजिए जो ज़रूरी हैं।
Very High_heart      | आज का दिन आपके जैसे दिल पर भारी पड़ रहा है — आज सिर्फ़ वही काम कीजिए जो ज़रूरी हैं।
Very High_pregnancy  | आज का दिन आप और आपकी गर्भावस्था पर भारी पड़ रहा है — आज सिर्फ़ वही काम कीजिए जो ज़रूरी हैं।
Very High_age        | आज का दिन आपके जैसे शरीर पर भारी पड़ रहा है — आज सिर्फ़ वही काम कीजिए जो ज़रूरी हैं।
Extreme_none         | आज का दिन आपके लिए ख़तरनाक है — बाहर सिर्फ़ वही काम कीजिए जो टल ही न सकें।
Extreme_lungs        | आज का दिन आपके जैसे फेफड़ों के लिए ख़तरनाक है — बाहर सिर्फ़ वही काम कीजिए जो टल ही न सकें।
Extreme_heart        | आज का दिन आपके जैसे दिल के लिए ख़तरनाक है — बाहर सिर्फ़ वही काम कीजिए जो टल ही न सकें।
Extreme_pregnancy    | आज का दिन आपके और आपकी गर्भावस्था के लिए ख़तरनाक है — बाहर सिर्फ़ वही काम कीजिए जो टल ही न सकें।
Extreme_age          | आज का दिन आपके जैसे शरीर के लिए ख़तरनाक है — बाहर सिर्फ़ वही काम कीजिए जो टल ही न सकें।
"""


@pytest.mark.parametrize("lang,golden",
                         (("en", GOLDEN_VERDICTS), ("hi", GOLDEN_VERDICTS_HI)),
                         ids=("en", "hi"))
def test_the_verdict_ramp_is_what_a_reader_gets(lang, golden):
    """Turns red when: any of the seventeen verdicts a reader can meet first
    changes, in either language, including a change that only reorders them.

    It cannot see whether the new order is monotone -- that is a reading, and it
    is the reviewer's, not this file's. It can refuse to let the order change
    without a person seeing it."""
    from saafsaans.web import presenters

    rows = [f"{key:<20} | {i18n.t(lang, 'verdict', key, text)}"
            for key, text in presenters._VERDICTS.items()]
    assert "\n".join(rows) == golden.strip(), (
        "the verdict ramp changed; keys are in presenters._VERDICTS order")
