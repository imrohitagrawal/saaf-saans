"""The eight things the evidence forbids this app from saying.

`docs/research/2026-07-exposure-evidence.md` ends with a copy-review checklist
derived from the evidence above it. Until now that checklist was prose: a human
read the strings and decided. On 2026-08-31 the owner chose to run the remaining
gates with no human stops, which removes the reader. This file is what replaces
them.

It is not a substitute for a person and does not claim to be. It catches the
eight specific claim shapes the evidence rules out. It cannot catch a sentence
that is fluent, sourced, and simply wrong -- and it cannot read Hindi for sense
at all. The unverified-Hindi banner stays up for that reason.

Two design choices, both load-bearing:

**It sweeps the corpus, not a list of keys.** Every string in `i18n.HI` and in
`risk.BAND_ADVICE`/`risk._HEADLINE` is walked, so a rule cannot be outflanked by
adding a new key. The Devanagari floor was policed by hand-maintained selector
lists for months and every audit found another place a list had missed; that is
Gate 2a. A hand-maintained key list here would fail the same way, and this gate
guards health guidance given to people with asthma, COPD and pregnancies.

**Every rule ships with two partners.** A rule that matches nothing passes
silently forever, and so does a rule pointed at an empty corpus. So each rule is
proven to fire on a violation and proven not to fire on the compliant sentence
it must allow, and the sweep is proven to have actually reached the strings.
"""
import pathlib
import re

import pytest

from saafsaans.services import i18n, risk
from saafsaans.web import presenters

# --- The corpus ------------------------------------------------------------
# Everything a reader can be shown that carries advice. `i18n.HI` is the whole
# Hindi side; BAND_ADVICE and _HEADLINE are the English sentences that have no
# Hindi-side equivalent to walk because their Hindi lives in HI already.


def _walk(node, path=()):
    """Yield ``(dotted.path, string)`` for every leaf string under ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk(value, path + (str(i),))
    elif isinstance(node, str):
        yield ".".join(path), node


def _english_defaults():
    """Every English string passed as the fallback to ``i18n.t(lang, g, k, english)``.

    The Hindi side is one dict and walks itself. The English side is not: it lives
    as the fourth argument at each call site, so there is no object to iterate.
    Listing those call sites by hand would rot the first time someone added one --
    the failure this module's docstring is about.

    So they are read out of the syntax tree instead. Any call to ``t`` or
    ``i18n.t`` with four positional arguments contributes its fourth, when that
    argument is a literal string. A call built from a variable is skipped and
    cannot be checked here; that is a real limit, and it is why the dict sweep
    below is kept rather than replaced.
    """
    import ast

    root = pathlib.Path(__file__).resolve().parent.parent / "saafsaans"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 4:
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "t":
                continue
            arg = node.args[3]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                rel = path.relative_to(root.parent)
                yield f"{rel}:{node.lineno}", arg.value


def corpus():
    """Every user-facing advice string, with a path naming where it came from."""
    rows = list(_walk(i18n.HI, ("i18n.HI",)))
    rows += list(_walk(risk.BAND_ADVICE, ("risk.BAND_ADVICE",)))
    rows += list(_walk(risk._HEADLINE, ("risk._HEADLINE",)))
    # The sentence a reader actually meets. `risk._HEADLINE` is rendered by no
    # template at all -- it exists only in compute_risk()'s return contract --
    # while `presenters._VERDICTS` is the <h1> at the top of Today, and carries
    # the bluntest health statement on the page. This file shipped on
    # 2026-08-31 sweeping the one nobody sees and not the one everybody does.
    rows += list(_walk(presenters._VERDICTS, ("presenters._VERDICTS",)))
    rows += list(_english_defaults())
    return rows


# --- The eight rules -------------------------------------------------------
# Each entry: the checklist item, the pattern, one sentence that MUST be caught,
# and one that MUST be allowed. The allowed twin is not decoration -- it is what
# stops a rule being tightened into something that blocks honest copy. Several
# of these sentences are close paraphrases of strings the app already ships.

# Spans words but not sentences. A bare full stop or danda ends the span; a full
# stop followed by a digit does not, because "PM2.5" is one token and an earlier
# draft of D3 silently failed on exactly that -- its own violation sentence went
# uncaught until the partner test below refused it.
_NEAR = r"(?:[^.।]|\.\d)"

RULES = [
    (
        "D1 no promised health outcome",
        # A promise about the reader's body. Not "wear a mask" (an action) but
        # "this will protect your lungs" (an outcome). D1: personal protective
        # measures showed no lung-function benefit in the RCTs.
        #
        # The present tense is here because the future tense alone left a hole
        # the size of the rule. "It protects your lungs" and "यह आपके फेफड़ों की
        # रक्षा करता है" are the same promise as "it will protect them", and
        # until 2026-08-31 neither was caught. Widened, not loosened: the
        # 640-string corpus gains no hit, and the allowed twin below still
        # passes, so nothing honest was blocked to close it.
        # Third person, passive and the Hindi plural are here for the same
        # reason as the present tense: "a respirator protects the lungs",
        # "your lungs are protected", "मास्क आपके फेफड़ों को बचाते हैं" are the
        # same promise as the second-person singular, and each shipped green
        # under an adversarial pass on 2026-08-31.
        re.compile(
            r"(?:will|going to)\s+(?:protect|prevent|stop|cure|heal|fix)\b"
            r"|(?:protects?|prevents?|shields?|safeguards?)"
            r"\s+(?:the|his|her|their|you|your)\b"
            r"|(?:are|is)\s+(?:protected|shielded|safeguarded)\b"
            r"|will\s+thank\s+you\b"
            r"|keeps?\s+(?:you|your)\b" + _NEAR + r"{0,30}"
            r"\b(?:safe|healthy|clear|protected)\b"
            r"|guarantee(?:s|d)?\b|ensures?\s+(?:you|your)\b"
            r"|बचाएगा|बचाएगी|सुरक्षित\s+रखेगा|सुरक्षित\s+रखत[ेीा]|रोकेगा"
            r"|ठीक\s+कर\s+देगा|रक्षा\s+कर|बचात[ेीा]|बचाव\s+करत[ेीा]",
            re.IGNORECASE),
        "An N95 will protect your lungs from damage.",
        "Wear an N95 outdoors.",
    ),
    (
        "D2 no purifier dismissed as useless",
        # D1 and D2 together: the app must not overcorrect into nihilism.
        re.compile(
            r"purifiers?\s+(?:do\s?n[o']?t|don't|do not|never)\s+(?:work|help)\b"
            r"|purifiers?\s+(?:are|is)\s+(?:useless|pointless|a\s+waste)\b"
            r"|no\s+point\s+(?:in\s+)?(?:a\s+|an\s+)?purifier"
            r"|प्यूरीफ़ायर\s+बेकार|प्यूरीफ़ायर\s+से\s+कोई\s+फ़ायदा\s+नहीं",
            re.IGNORECASE),
        "Air purifiers are useless, do not bother.",
        "Run an air purifier indoors.",
    ),
    (
        "D3 no specific filtration percentage",
        # The evidence range is 11-82%. Any single figure misrepresents it.
        re.compile(
            r"\d{1,3}\s?%" + _NEAR + r"{0,40}(?:filtrat|filter|purif|प्यूरीफ़ायर|फ़िल्टर)"
            r"|(?:filtrat|filter|purif|प्यूरीफ़ायर|फ़िल्टर)" + _NEAR + r"{0,40}\d{1,3}\s?%",
            re.IGNORECASE),
        "A purifier cuts indoor PM2.5 by 60%.",
        "A purifier lowers indoor PM2.5.",
    ),
    (
        "D4/D6 no ug/m3 figure for a commute mode",
        # D6 supports RANK ORDER ONLY. A per-mode concentration is a modelled or
        # single-campaign figure wearing the clothes of a measurement.
        re.compile(
            r"(?:bus|metro|auto|rickshaw|car|walk|cycl|बस|मेट्रो|ऑटो|कार|पैदल|साइकिल)"
            + _NEAR + r"{0,60}\d+\s?(?:µg|ug|μg|माइक्रोग्राम)"
            r"|\d+\s?(?:µg|ug|μg)" + _NEAR + r"{0,60}"
            r"(?:bus|metro|auto|rickshaw|car|walk|cycl|बस|मेट्रो|ऑटो|कार|पैदल|साइकिल)",
            re.IGNORECASE),
        "The bus exposes you to 113 µg/m³ on that route.",
        "A closed car takes in less than an open auto.",
    ),
    (
        "D6 never stop walking",
        # Tainio: the active-travel benefit outlasts the pollution penalty far
        # past Delhi's concentrations. Telling people to stop walking is a net
        # health harm.
        re.compile(
            r"stop\s+walking\b|do\s?n[o']?t\s+walk\b|don't\s+walk\b|never\s+walk\b"
            r"|avoid\s+walking\b|पैदल\s+(?:मत|न)\s+(?:चल|जा)",
            re.IGNORECASE),
        "Stop walking to work until the air clears.",
        "Walk a shorter route, and go slower.",
    ),
    (
        "D7 recirculation, never use the AC",
        # D7: it is the recirculation setting that does the work, not cooling.
        # "Use the AC" sends people to the wrong button.
        re.compile(
            r"(?:use|turn\s+on|switch\s+on|put\s+on)\s+the\s+(?:a\.?c\.?|air\s?con)\b"
            r"|ए\.?सी\.?\s+(?:चला|चालू|ऑन)",
            re.IGNORECASE),
        "Use the AC when you drive through traffic.",
        "Set the car vents to recirculate.",
    ),
    (
        "D8 never ambient AQI is uninformative",
        # D8 cuts both ways: the proxy is imperfect AND it is the best signal a
        # reader has. Dismissing it leaves them with nothing.
        re.compile(
            r"(?:aqi|एक्यूआई)" + _NEAR + r"{0,40}"
            r"(?:mean(?:s|ing)?\s+nothing|is\s+meaningless|is\s+useless|tells?\s+you\s+nothing"
            r"|बेकार|कोई\s+मतलब\s+नहीं)"
            r"|ignore\s+the\s+(?:aqi|number)",
            re.IGNORECASE),
        "Ignore the AQI, it tells you nothing about your air.",
        "The AQI is a city-wide average, not your doorstep.",
    ),
    (
        "D4 no modelled figure presented as measured",
        # A future-tense concentration is always modelled: this app holds daily
        # forecast averages and no hourly concentration source at all.
        re.compile(
            r"(?:will\s+be|expect(?:ed)?\s+to\s+be|by\s+\d{1,2}\s?(?:am|pm))"
            + _NEAR + r"{0,40}\d+\s?(?:µg|ug|μg|aqi)"
            r"|\d+\s?(?:µg|ug|μg)" + _NEAR + r"{0,30}(?:tomorrow|tonight|later|कल|शाम\s+तक)",
            re.IGNORECASE),
        "By 7 pm the air will be 84 µg/m³.",
        "Later hours are usually calmer than the afternoon.",
    ),
]

IDS = [name for name, *_ in RULES]


# --- The gate --------------------------------------------------------------

@pytest.mark.parametrize("name,pattern,violation,allowed", RULES, ids=IDS)
def test_no_shipped_string_breaks_the_checklist(name, pattern, violation, allowed):
    """The whole corpus, against one rule.

    Turns red when: any string in i18n.HI, risk.BAND_ADVICE or risk._HEADLINE
    starts saying the thing this rule forbids.
    """
    hits = [(path, text) for path, text in corpus() if pattern.search(text)]
    assert not hits, (
        f"{name} violated in {len(hits)} string(s):\n"
        + "\n".join(f"  {p}: {t[:120]}" for p, t in hits[:8]))


@pytest.mark.parametrize("name,pattern,violation,allowed", RULES, ids=IDS)
def test_every_rule_catches_its_own_violation(name, pattern, violation, allowed):
    """The partner the sweep above needs.

    The sweep asserts an ABSENCE, and an absence is satisfied by a pattern that
    matches nothing at all -- replace any regex with `(?!)` and the sweep stays
    green for ever. This proves each rule fires on the sentence it exists to
    stop, so the green above is a result rather than a silence.
    """
    assert pattern.search(violation), f"{name} does not catch: {violation!r}"


@pytest.mark.parametrize("name,pattern,violation,allowed", RULES, ids=IDS)
def test_every_rule_permits_the_honest_sentence(name, pattern, violation, allowed):
    """The other partner, against over-reach.

    A rule tightened until it blocks honest copy is worse than no rule: the next
    author deletes it rather than argues with it. Each `allowed` sentence is the
    nearest compliant thing to its violation -- the action without the promised
    outcome, the rank order without the figure, recirculation instead of the AC.
    """
    assert not pattern.search(allowed), f"{name} wrongly blocks: {allowed!r}"


def test_the_sweep_actually_reaches_the_strings():
    """A check that counts nothing needs a partner proving the thing exists.

    Every assertion above is over `corpus()`. If it returned an empty list --
    a renamed `i18n.HI`, a `_walk` that stopped recursing -- all eight sweeps
    would pass having read nothing, and this file would report a clean corpus it
    never opened.

    The floors are deliberately far below the real counts (503 Hindi leaves and
    10 English sentences as at 2026-08-31) so ordinary copy work never trips
    them; they catch a corpus that collapsed, not one that changed.
    """
    rows = corpus()
    paths = [p for p, _ in rows]
    assert len(rows) > 300, f"corpus collapsed to {len(rows)} strings"
    assert any(p.startswith("i18n.HI.") for p in paths), "no Hindi strings swept"
    # The two sources added on 2026-08-31, each with its own reason to be here.
    # Without these two lines, deleting either from corpus() is invisible: the
    # eight sweeps would go on passing over a smaller corpus, which is the exact
    # silence this file exists to prevent.
    assert any(p.startswith("presenters._VERDICTS.") for p in paths), \
        "the on-screen hero headline is not being swept"
    assert sum(1 for p in paths if p.startswith("saafsaans/")) > 50, \
        "no English i18n.t defaults swept -- the AST walk found nothing"
    assert any(p.startswith("risk.BAND_ADVICE.") for p in paths), "no band advice swept"
    assert any(p.startswith("risk._HEADLINE.") for p in paths), "no headlines swept"

    # And that it reached the specific sentences this gate exists for: the five
    # band_advice lines are the ones that speak to a person with a condition.
    for band in ("Low", "Moderate", "High", "Very High", "Extreme"):
        assert f"risk.BAND_ADVICE.{band}" in paths, f"{band} advice not swept"
        assert f"i18n.HI.band_advice.{band}" in paths, f"{band} Hindi advice not swept"


def test_both_languages_are_swept_for_every_band():
    """The English corpus is not the whole corpus.

    R4 in the risk register: no Hindi speaker has verified the draft, and the
    suite cannot catch a fluent-but-wrong sentence. What it CAN do is refuse to
    let the Hindi side go unchecked for the eight claim shapes. A gate that read
    only English would pass a Hindi string promising a health outcome.
    """
    en = {p for p, _ in corpus() if p.startswith("risk.")}
    hi = {p for p, _ in corpus() if p.startswith("i18n.HI.band_advice")
          or p.startswith("i18n.HI.headline")}
    assert len(en) == 10, f"expected 5 advice + 5 headline in English, got {len(en)}"
    assert len(hi) == 10, f"expected 5 advice + 5 headline in Hindi, got {len(hi)}"


# D1's present tense, added 2026-08-31. The RULES table carries one violation
# per rule, and D1's is future-tense, so the branch that closes the present-
# tense hole would otherwise ship with nothing proving it fires.
D1_PRESENT_TENSE = (
    "Run a purifier in the room you use most; it protects your lungs.",
    "An N95 keeps your lungs safe.",
    "This mask shields you from fine particles.",
    "प्यूरीफ़ायर चलाइए, यह आपके फेफड़ों की रक्षा करता है।",
    "N95 आपको बचाता है।",
    # Third person, passive and the Hindi plural. All five shipped green under
    # an adversarial pass before these branches existed.
    "A respirator protects the lungs on a day like this.",
    "Your lungs are protected by a good mask.",
    "Your lungs will thank you for it.",
    "मास्क आपके फेफड़ों को बचाते हैं।",
    "अच्छे मास्क आपके फेफड़ों की रक्षा करते हैं।",
)
# The nearest compliant sentences to those five: the same actions, with the
# outcome taken out. If one of these ever fails, D1 has been tightened into
# something that blocks the copy this app has to write.
D1_STILL_ALLOWED = (
    "Run a purifier in the room you use most.",
    "Wear a well-fitted N95 outdoors.",
    "A purifier lowers indoor PM2.5.",
    "जिस कमरे में आप ज़्यादातर रहते हैं वहाँ प्यूरीफ़ायर चलाइए।",
    "बाहर N95 पहनें।",
)


def _d1():
    return next(pattern for name, pattern, _v, _a in RULES if name.startswith("D1"))


@pytest.mark.parametrize("sentence", D1_PRESENT_TENSE)
def test_d1_catches_a_promise_made_in_the_present_tense(sentence):
    """Turns red when: D1 loses its present-tense branch, at which point
    "it protects your lungs" ships as freely as "it will protect your lungs"
    was blocked."""
    assert _d1().search(sentence), sentence


@pytest.mark.parametrize("sentence", D1_STILL_ALLOWED)
def test_d1_still_permits_the_action_without_the_outcome(sentence):
    """The partner against over-reach. Widening a rule until it blocks honest
    copy is worse than not widening it: the next author deletes the rule rather
    than argue with it."""
    assert not _d1().search(sentence), sentence
