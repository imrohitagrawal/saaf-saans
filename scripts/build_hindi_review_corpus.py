"""The Hindi review corpus: every leaf string in `i18n.HI`, its English source,
and the surface it renders on -- Gate 5a Deliverable 1.

Reuses the walking logic `tests/test_health_claims.py` already relies on
(`_walk`, recursive over dicts/lists/tuples down to leaf strings) so a newly
added Hindi key cannot slip past this corpus the way a hand-maintained key
list would. See `docs/PLAN-gates.md` Gate 2a for that failure class.

English source, best-effort
----------------------------
There is no `i18n.EN` dict -- English defaults live at the fourth positional
argument of each `i18n.t(lang, group, key, english)` / `presenters._fmt(...)`
call site, or (192 of them) at the third argument of the Jinja `T(group, key,
english)` calls in `saafsaans/web/templates/*.html`. `test_health_claims.py`'s
own `_english_defaults()` reads only the Python side and says so in a comment
at `main.py:748-751`: a Jinja-only default "ships checked in Hindi and
unchecked in English" by that test's own design. This script reads both, plus
`normalize.GLOSSARY` and `normalize.CONDITION_HELP` directly for the two groups
whose per-key English lives in a real dict rather than at a literal call site,
and treats `locality` specially (`i18n.place` falls back to the key itself).

A leaf key reached only through a dynamic call site (an f-string key, e.g.
`f"cond_{condition_kw}"`) has no literal English to recover this way. Those
rows carry `english: None` rather than a guess -- constraint (i), honesty over
polish, never fabricate.

Surface, best-effort
---------------------
`GROUP_SURFACE` below is a manual map from each `i18n.HI` top-level group to
the page(s) that group's strings render on, worked out once by grepping every
call site's enclosing route in `saafsaans/web/main.py` and
`saafsaans/web/presenters.py` (each entry's comment names the call site where
relevant). It is a label for a human reviewer to navigate by, not a
machine-verified fact.

Run:
    .venv/bin/python -m scripts.build_hindi_review_corpus

Prints the corpus size and writes the corpus as JSON to the path given by
`--out` (default: scratch, not committed). The corpus itself is derived
entirely from committed source, so two runs against the same commit produce
byte-identical JSON -- there is no timestamp, no randomness, no filesystem
ordering dependency (file lists are sorted before walking).
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re

from saafsaans.data import advisories as advisories_data
from saafsaans.services import i18n, normalize, risk
from saafsaans.services import llm as llm_service
from saafsaans.web import presenters

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "saafsaans"
TEMPLATES = PACKAGE / "web" / "templates"

# --- Which page each i18n.HI group renders on, best-effort ----------------
# "Today" covers `/`; "City Pulse" covers `/city`; "Guide" covers `/guide`.
# No group here renders exclusively on `/system` -- verified: no `i18n.t`
# call site sits inside `main.py`'s `system()` route (main.py:1319-1450).
GROUP_SURFACE = {
    "verdict": "Today",
    # risk._HEADLINE is never rendered by any template (test_health_claims.py's
    # own comment); i18n.HI["headline"] is its Hindi counterpart and is
    # therefore reachable only through the API contract, not a page.
    "headline": "Today (API contract only -- not rendered on any page)",
    "band_advice": "Today",
    "band_label": "Today / City Pulse / Guide",
    "aqi_meaning": "Today",
    "hero": "Today",
    "window": "Today",
    "compare": "Today",
    "driver": "Today",
    "persona": "Today",
    "prov": "Today / City Pulse",
    "who": "Today",
    "day": "Today",
    "condition_help": "Today",
    "advisory": "Today (Q&A)",
    "answer": "Today (Q&A)",
    "a11y": "City Pulse",
    "city": "City Pulse",
    "glossary": "Guide",
    "guide": "Guide",
    "ui": "Shared (nav, controls, footer -- every page)",
    "locality": "Shared (place names -- Today & City Pulse)",
}

# Today and City Pulse first (reader impact), then shared surfaces, then
# Guide/System. Ties keep the corpus's own key order (Python sort is stable).
_RANK_TERMS = (("Today", 0), ("City Pulse", 1), ("Shared", 2), ("Guide", 3))


def _surface_rank(surface: str) -> int:
    for term, rank in _RANK_TERMS:
        if term in surface:
            return rank
    return 4  # System, or anything unclassified


def _walk(node, path=()):
    """Yield ``(dotted.path, string)`` for every leaf string under ``node``.

    Mirrors `tests/test_health_claims.py::_walk` exactly (dict/list/tuple
    recursion down to leaf strings) so this corpus and that test's corpus can
    never disagree about what counts as a leaf.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk(value, path + (str(i),))
    elif isinstance(node, str):
        yield path, node


def _python_english_defaults() -> dict:
    """``{(group, key): english}`` from every literal 4-arg call to a function
    named ``t`` or ``_fmt`` (``i18n.t(lang, group, key, english)`` and
    ``presenters._fmt(lang, group, key, english, **fields)`` share that shape)
    across every ``.py`` file in the package. A call whose group or key is
    built at runtime (an f-string, a variable) is skipped -- it cannot be
    resolved without running the app, and this script does not.
    """
    out: dict = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 4:
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in ("t", "_fmt"):
                continue
            group_arg, key_arg, eng_arg = node.args[1], node.args[2], node.args[3]
            if not (isinstance(group_arg, ast.Constant) and isinstance(group_arg.value, str)
                    and isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str)
                    and isinstance(eng_arg, ast.Constant) and isinstance(eng_arg.value, str)):
                continue
            out.setdefault((group_arg.value, key_arg.value), eng_arg.value)
    return out


# Matches the Jinja `T('group', 'key', 'english')` / `T('group', 'key',
# "english")` call shape used across the templates -- group and key are
# always single-quoted; the English default uses whichever quote lets it
# contain an apostrophe without escaping (see e.g. guide.html's
# `"India's national scale..."`).
_TEMPLATE_T = re.compile(
    r"""\bT\(\s*'([a-zA-Z0-9_]+)'\s*,\s*'([a-zA-Z0-9_]+)'\s*,\s*"""
    r"""(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""",
    re.S,
)


def _template_english_defaults() -> dict:
    """``{(group, key): english}`` from literal ``T('group', 'key', 'english')``
    calls in the Jinja templates. A call whose key is a loop variable (e.g.
    ``T('glossary', term, text)``) does not match and is skipped -- those two
    groups are covered exactly, not best-effort, by
    ``_dict_backed_defaults`` instead.
    """
    out: dict = {}
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text()
        for m in _TEMPLATE_T.finditer(text):
            group, key, single, double = m.groups()
            out.setdefault((group, key), single if single is not None else double)
    return out


def _dict_backed_defaults() -> dict:
    """English defaults reached through a *variable* key at the call site, so
    the literal-argument scans above cannot see them, but where the English
    itself still lives in one committed Python dict that this script can
    import and walk directly -- not a guess, the same value the call site
    would have used.

    ``glossary`` / ``condition_help``: rendered via a Jinja loop
    (``T('glossary', term, text)``); the English lives in
    ``normalize.GLOSSARY`` / ``normalize.CONDITION_HELP`` (verified:
    ``set(normalize.GLOSSARY) == set(i18n.HI["glossary"])``, same for
    ``condition_help``).

    ``verdict`` / ``band_advice`` / ``headline``: keyed on the risk band (or
    band + driver), from ``presenters._VERDICTS``, ``risk.BAND_ADVICE``,
    ``risk._HEADLINE``.

    ``aqi_meaning``: ``normalize.AQI_MEANING``, called as
    ``normalize.aqi_meaning(l)``.

    ``band_label``: the fallback is the category label itself
    (`main.py:710`: ``i18n.t(lang, "band_label", data["category"][0],
    data["category"][0])``) -- identity, like ``locality``.

    ``driver.cond_*`` / ``driver.act_*`` / ``driver.age_*``:
    ``risk._COND_LABEL`` / ``risk._ACT_LABEL`` / ``risk._AGE_LABEL``, each
    keyed by the normalized keyword the f-string key is built from.

    ``persona.age_*`` / ``persona.condition_*`` / ``persona.activity_*``:
    ``presenters._AGE_KEYS``/``_AGE_PHRASE``,
    ``_CONDITION_KEYS``/``_CONDITION_PHRASE``,
    ``_ACTIVITY_KEYS``/``_ACTIVITY_PHRASE`` -- each KEYS dict maps the option
    value to the i18n key; the matching PHRASE dict maps it to the English.

    ``compare.reason_*``: ``presenters._CONDITION_REASON_KEYS``/
    ``_CONDITION_REASON`` and ``_AGE_REASON_KEYS``/``_AGE_REASON``, same
    shape.

    ``day.mon`` .. ``day.sun``: ``presenters._WEEKDAYS``, a tuple of
    ``(key, english)`` pairs.

    ``who.multiple_N``: ``presenters._MULTIPLE_WORDS``, keyed by the integer
    multiple.

    ``answer.activity_*`` / ``answer.precaution_*``:
    ``llm._ACTIVITY_KEYWORDS``, a list of ``(keywords, slug, label,
    precaution)`` tuples.

    ``ui.risk_band_*``: the fallback is the band name itself
    (`today.html`: ``T('ui', 'risk_band_' ~ risk.band, risk.band)``) --
    identity, over `risk.BAND_ADVICE`'s band names (Low/Moderate/High/Very
    High/Extreme), not `normalize.AQI_MEANING`'s CPCB category names -- the
    two are different scales that happen to share "Moderate".

    ``ui.risk_notice``: ``risk.HEURISTIC_NOTICE``.

    ``advisory.<key>``: `main.py:348-351` builds the key as
    ``f"{source}:{aqi_min}-{aqi_max}:{condition}:{activity}:{age_group}"``
    over each seeded row and falls back to that row's own ``advice`` --
    reproduced here from ``saafsaans.data.advisories.ADVISORIES``.
    """
    out: dict = {}
    for key, value in normalize.GLOSSARY.items():
        out[("glossary", key)] = value
    for key, value in normalize.CONDITION_HELP.items():
        out[("condition_help", key)] = value
    for key, value in presenters._VERDICTS.items():
        out[("verdict", key)] = value
    for key, value in risk.BAND_ADVICE.items():
        out[("band_advice", key)] = value
    for key, value in risk._HEADLINE.items():
        out[("headline", key)] = value
    for label in normalize.AQI_MEANING:
        out[("aqi_meaning", label)] = normalize.aqi_meaning(label)
        out[("band_label", label)] = label
    # `ui.risk_band_*` names the persona-adjusted RISK band (Low/Moderate/
    # High/Very High/Extreme, `risk.BAND_ADVICE`'s keys) -- a different scale
    # from `band_label`'s CPCB measurement category (Good/Satisfactory/...,
    # `normalize.AQI_MEANING`'s keys). Conflating the two was the first draft
    # of this function's bug: it left every `ui.risk_band_*` key unresolved
    # because "Low"/"High"/"Extreme" are not CPCB category names.
    for band in risk.BAND_ADVICE:
        out[("ui", f"risk_band_{band}")] = band
    for kw, label in risk._COND_LABEL.items():
        out[("driver", f"cond_{kw}")] = label
    for kw, label in risk._ACT_LABEL.items():
        out[("driver", f"act_{kw}")] = label
    for kw, label in risk._AGE_LABEL.items():
        out[("driver", f"age_{kw}")] = label
    for option, key in presenters._AGE_KEYS.items():
        out[("persona", key)] = presenters._AGE_PHRASE.get(option, "an adult")
    for option, key in presenters._CONDITION_KEYS.items():
        out[("persona", key)] = presenters._CONDITION_PHRASE.get(option, "in good health")
    for option, key in presenters._ACTIVITY_KEYS.items():
        out[("persona", key)] = presenters._ACTIVITY_PHRASE.get(option, "")
    for option, key in presenters._CONDITION_REASON_KEYS.items():
        out[("compare", key)] = presenters._CONDITION_REASON.get(option, "")
    # `_reasons`' own `.get(condition, "reason_condition")` /
    # `.get(condition, "your health condition")` fallback pair, for a
    # condition not in `_CONDITION_REASON_KEYS` -- unreachable via the five
    # persona conditions today, kept as a documented fallback the key exists
    # for (`presenters.py:339-340`).
    out[("compare", "reason_condition")] = "your health condition"
    for option, key in presenters._AGE_REASON_KEYS.items():
        out[("compare", key)] = presenters._AGE_REASON.get(option, "")
    for key, english in presenters._WEEKDAYS:
        out[("day", key)] = english
    for n, word in presenters._MULTIPLE_WORDS.items():
        out[("who", f"multiple_{n}")] = word
    for _keywords, slug, label, precaution in llm_service._ACTIVITY_KEYWORDS:
        out[("answer", f"activity_{slug}")] = label
        out[("answer", f"precaution_{slug}")] = precaution
    out[("ui", "risk_notice")] = risk.HEURISTIC_NOTICE
    out[("guide", "source_unvalidated")] = risk.SOURCE_UNVALIDATED
    for doc in advisories_data.ADVISORIES:
        key = (f"{doc.get('source')}:{doc.get('aqi_min')}-{doc.get('aqi_max')}"
               f":{doc.get('condition')}:{doc.get('activity')}:{doc.get('age_group')}")
        out[("advisory", key)] = doc.get("advice") or ""
    return out


def _locality_defaults() -> dict:
    """``i18n.place(lang, name)`` calls ``t(lang, "locality", name, name)`` --
    the English default for every locality key is the key itself, a proper
    noun that is never translated (`i18n.py`'s own docstring says so).
    """
    return {("locality", key): key for key in i18n.HI.get("locality", {})}


def _english_map() -> dict:
    merged: dict = {}
    merged.update(_python_english_defaults())
    for source in (_template_english_defaults(), _dict_backed_defaults(),
                   _locality_defaults()):
        for k, v in source.items():
            merged.setdefault(k, v)
    return merged


def build_corpus() -> list:
    """Every leaf string in ``i18n.HI``, ordered by reader impact.

    Each row: ``key`` (dotted), ``group``, ``hindi``, ``english`` (``None``
    when no literal default was found), ``surface``.
    """
    eng_map = _english_map()
    rows = []
    for path, hindi in _walk(i18n.HI):
        group, key = path[0], ".".join(path[1:])
        rows.append({
            "key": ".".join(path),
            "group": group,
            "hindi": hindi,
            "english": eng_map.get((group, key)),
            "surface": GROUP_SURFACE.get(group, "Unclassified"),
        })
    rows.sort(key=lambda r: _surface_rank(r["surface"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=None,
                         help="write the corpus as JSON to this path")
    args = parser.parse_args()

    rows = build_corpus()
    missing_english = sum(1 for r in rows if r["english"] is None)
    unclassified = sum(1 for r in rows if r["surface"] == "Unclassified")

    print(f"corpus size: {len(rows)} leaf strings")
    print(f"design doc's figure at commit 450188c: 515")
    print(f"drift: {len(rows) - 515:+d}")
    print(f"rows with no literal English default found: {missing_english}")
    print(f"rows with an unclassified surface: {unclassified}")

    if args.out:
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
