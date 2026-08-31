"""The Devanagari Floor Rule, measured in a real browser.

DESIGN.md: "Hindi text is never letter-spaced, never uppercased, never below
12px (12.5px floor on labels)". Reconciled against how this stylesheet
actually uses that number: every existing `:lang(hi)` size rule in app.css
sets exactly 12.5px, never 12px, so 12.5px is the floor this file enforces
uniformly -- the 12px clause in DESIGN.md is the absolute cliff below which
matras stop resolving at all, and this codebase has already chosen to hold
every labelled and unlabelled string above it.

Root cause (docs/PLAN-gates.md, Gate 2a): the floor used to be policed by
hand-maintained CSS selector lists in tests/test_a11y.py -- a size-floor list
scoped to `.caveat` only, a Python re-implementation of specificity for the
tracking reset, and an uppercase carve-out sweep that reads only top-level
rules with an `endswith` coverage clause. Every one of those is a static
analysis of the STYLESHEET SOURCE. A selector list cannot notice its own
omissions, a specificity re-implementation does not know about `!important`,
and neither can see a rule buried in an `@media` block it was never taught to
open.

This file asks a different question: not "what does the stylesheet say",
but "what did the browser actually paint". It renders every Hindi page for
real, walks the live DOM, and reads `getComputedStyle` on every element whose
OWN text contains a Devanagari codepoint (U+0900-U+097F). That is the
resolved cascade -- specificity, `@media`, `!important`, inheritance and all
-- so none of those three blind spots can hide a violation from it, structurally,
not because this file happens to check for them.

What it still cannot see: a Devanagari string injected through CSS
`content: "..."` on a `::before`/`::after` pseudo-element (this stylesheet
has none -- grepped, the only `content:` is the empty viewport probe), and any
Devanagari that a future dynamic feature composes client-side, since this
site ships no JavaScript to do that with. Both are named here rather than
silently assumed away.

The three old guards stay in tests/test_a11y.py rather than being deleted:
this file's stated scope is app.css plus one new test file, and the old
guards still pass, cost nothing, and catch a same-class regression before a
browser is ever launched. This file is the authority on whether the floor
actually holds; they are a cheap first line that can go stale without the
floor itself moving, which is exactly the failure this file exists to catch
regardless.
"""
import re

import pytest

from tests.test_viewport_browser import _chrome_session, served  # noqa: F401

DEVANAGARI_FLOOR = 12.5

PERSONA_QS = ("locality=Anand+Vihar&age=Adult&condition=Asthma"
              "&activity=Outdoor+exercise&theme=light&lang=hi")

# Every Hindi state a reader can reach that was not already in test_a11y.py's
# hindi_pages fixture, plus the ones that are. `security-sim` is the one this
# batch adds: GET alone renders `.sim-note` (main.py reads `sim=1` off the
# query string, no POST, no Elasticsearch), and no existing test -- browser or
# Python -- ever requested that URL in Hindi, which is exactly why
# `.sim-note`'s 12px stayed invisible through every prior audit.
PAGES = {
    "today": f"/?{PERSONA_QS}",
    "today-first-visit": "/?theme=light&lang=hi",
    "today-term-open": f"/?{PERSONA_QS}&term=PM2.5",
    "city": f"/city?{PERSONA_QS}",
    "guide": f"/guide?{PERSONA_QS}",
    "system": f"/system?{PERSONA_QS}",
    "security": f"/system?{PERSONA_QS}&view=security",
    "security-sim": f"/system?{PERSONA_QS}&view=security&sim=1",
}


# Shared by both eval scripts below. `document.fonts.ready` resolves once
# every font FONT-LOADING has already started for is settled -- it does not
# guarantee the browser has finished the reflow/style-recalc that font's
# arrival triggers, nor that navigation has reached a stable document. Reading
# `getComputedStyle` right after `fonts.ready` chased an intermittent flake
# (documented in this batch's PR description): about 1 run in 25 read a
# tracking or size value from a layout pass that had not yet incorporated the
# just-swapped font. `readyState === 'complete'` plus two chained
# `requestAnimationFrame`s -- the standard "wait for style/layout to actually
# settle" idiom, since a single frame can still land mid-recalc -- closes that
# window. Not a proof it can never race again, only a mitigation verified
# against the specific flake this file measured.
_SETTLED = """
    function frame() { return new Promise(function (r) { requestAnimationFrame(r); }); }
    function ready() {
      return document.fonts.ready.then(function () {
        if (document.readyState !== 'complete') {
          return new Promise(function (r) {
            window.addEventListener('load', r, {once: true});
          });
        }
      }).then(frame).then(frame);
    }
"""

_DEVANAGARI_SWEEP_JS = _SETTLED + """
(function () {
  return ready().then(function () {
    var DEVANAGARI = /[\\u0900-\\u097F]/;
    var out = [];
    var all = document.body.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      var own = '';
      for (var j = 0; j < el.childNodes.length; j++) {
        var n = el.childNodes[j];
        if (n.nodeType === 3) { own += n.textContent; }
      }
      if (!DEVANAGARI.test(own)) { continue; }
      var cs = getComputedStyle(el);
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: el.className && el.className.baseVal !== undefined
             ? el.className.baseVal : String(el.className || ''),
        text: own.trim().replace(/\\s+/g, ' ').slice(0, 50),
        fontSize: parseFloat(cs.fontSize),
        letterSpacing: cs.letterSpacing,
        textTransform: cs.textTransform
      });
    }
    return out;
  });
})()
"""

# The escape hatch (finding 3): every static `lang="en"` carrier this app
# ships, queried directly rather than swept for, because the defect is a
# missing per-element re-declaration and a blanket sweep of `[lang="en"]`
# would just as easily paper over a font-family this file never checked
# either. `.sysbar .l` is the one mono-context case -- it must keep the mono
# face, not fall onto the generic body-face fix, so it gets its own
# assertion instead of sharing the others' expectation.
_LANG_EN_JS = _SETTLED + """
(function () {
  return ready().then(function () {
    function first(el) {
      var el2 = document.querySelector(el);
      if (!el2) { return null; }
      return getComputedStyle(el2).fontFamily.split(',')[0].replace(/["']/g, '').trim();
    }
    return {
      noticeEn: first('.notice-en'),
      sysbarL: first('.sysbar .l'),
      wordmarkTracking: (function () {
        var b = document.querySelector('.wordmark b');
        return b ? getComputedStyle(b).letterSpacing : null;
      })()
    };
  });
})()
"""


@pytest.fixture(scope="module")
def browser():
    with _chrome_session() as session:
        yield session


@pytest.fixture(scope="module")
def devanagari_sweep(served, browser):
    """Every Devanagari-bearing element's computed style, across every page."""
    found = []
    for name, path in PAGES.items():
        browser.load(f"{served}{path}", 1200, seconds=1.2)
        rows = browser.evaluate(_DEVANAGARI_SWEEP_JS)
        for row in rows:
            row["page"] = name
            found.append(row)
    return found


def test_the_sweep_actually_found_devanagari(devanagari_sweep):
    """A guard on the guard: an empty sweep proves nothing, and would pass
    every assertion below by omission -- exactly the shape of bug this file
    exists to catch in the fixture itself, not just in app.css."""
    assert len(devanagari_sweep) > 30, (
        f"only {len(devanagari_sweep)} Devanagari elements found across "
        f"{len(PAGES)} pages -- the sweep or the fixture is broken")
    pages_seen = {row["page"] for row in devanagari_sweep}
    assert pages_seen == set(PAGES), (
        "some pages rendered no Devanagari at all: "
        f"missing {set(PAGES) - pages_seen}")


def test_no_devanagari_renders_below_the_floor(devanagari_sweep):
    """Bites on `.sim-note`: 12px, in the Hindi security-sim render, invisible
    to every prior guard because none of them ever asked GET
    /system?view=security&sim=1&lang=hi -- this fixture does."""
    small = [f"{r['page']}: {r['tag']}.{r['cls']} at {r['fontSize']}px "
             f"-- {r['text']!r}"
             for r in devanagari_sweep if r["fontSize"] + 0.01 < DEVANAGARI_FLOOR]
    assert not small, ("Devanagari below the %spx floor:\n  " % DEVANAGARI_FLOOR
                       + "\n  ".join(sorted(set(small))))


def test_no_devanagari_renders_letter_spaced(devanagari_sweep):
    """Reads the resolved value, not the reset rule's own selector -- so a
    reset that is present in the source but loses the cascade (an
    `!important` on a later rule, a rule inside a media block the old sweep
    never opened) still shows up here as a spaced string."""
    def spaced(value):
        return value not in ("normal", "0px", "0em", "0")

    found = [f"{r['page']}: {r['tag']}.{r['cls']} letter-spacing "
             f"{r['letterSpacing']} -- {r['text']!r}"
             for r in devanagari_sweep if spaced(r["letterSpacing"])]
    assert not found, ("Devanagari rendered with letter-spacing:\n  "
                       + "\n  ".join(sorted(set(found))))


def test_no_devanagari_renders_uppercased(devanagari_sweep):
    """Devanagari is unicameral: `text-transform: uppercase` reaching it is
    invisible in the rendered glyphs and only shows up here, in the computed
    style, not in a screenshot."""
    found = [f"{r['page']}: {r['tag']}.{r['cls']} -- {r['text']!r}"
             for r in devanagari_sweep if r["textTransform"] == "uppercase"]
    assert not found, ("Devanagari rendered uppercased:\n  "
                       + "\n  ".join(sorted(set(found))))


@pytest.fixture(scope="module")
def lang_en(served, browser):
    """`.sysbar .l` only renders with a populated `by_event` telemetry map,
    which `served` never has (Elasticsearch is stubbed to `None`). Stubbed
    here rather than skipped, so the mono-context assertion actually runs
    instead of trusting that a face which is correct in isolation stays
    correct once real rows are on the page."""
    from saafsaans.services import metrics

    real = metrics.telemetry_kpis
    metrics.telemetry_kpis = lambda client: {
        "by_event": {"chat_completed": 3, "guard_blocked": 1},
        "by_locality": [], "total": 4}
    try:
        # /system, not /: .sysbar .l (the mono-context lang="en" case) only
        # renders on System, and .notice-en / .wordmark both render on every
        # page's shared header and banner, so one page load covers all three.
        browser.load(f"{served}/system?{PERSONA_QS}", 1200, seconds=1.2)
        return browser.evaluate(_LANG_EN_JS)
    finally:
        metrics.telemetry_kpis = real


def test_the_lang_en_escape_hatch_actually_restores_the_latin_face(lang_en):
    """Finding 3: `*:lang(en)` used to redirect the `--body`/`--mono`
    variables and nothing ever re-read them into `font-family` for an
    element with no font-family rule of its own, so a `lang="en"` span on a
    Hindi page still inherited the Devanagari face its Hindi ancestor had
    already resolved into. `.notice-en` is exactly that span -- no
    font-family rule anywhere above it in this file before this batch."""
    assert lang_en["noticeEn"] is not None, "the review banner did not render"
    assert lang_en["noticeEn"] != "Anek Devanagari", (
        ".notice-en (lang=\"en\") is rendering in the Hindi face")


def test_a_mono_context_lang_en_span_keeps_the_mono_face(lang_en):
    """The escape hatch's generic fix must not overcorrect: `.sysbar .l`
    (the event name in System's Hindi telemetry table) is `lang="en"`
    because it is a stored index value, not prose, and it must stay in the
    mono face the rest of that row is in -- falling onto the generic
    body-face fix would be a new, different defect."""
    assert lang_en["sysbarL"] is not None, "no telemetry rows rendered"
    assert lang_en["sysbarL"] != "Anek Devanagari"
    assert lang_en["sysbarL"] != "IBM Plex Sans", (
        ".sysbar .l fell onto the body face instead of staying mono")


def test_the_latin_wordmark_keeps_its_own_tracking_on_a_hindi_page(lang_en):
    """Finding 7: the broad Devanagari tracking reset
    (`html *:lang(hi):lang(hi)`) is scoped to computed language, not to
    script, so it also matched `.wordmark b` -- Latin text ("SaafSaans")
    that inherits `lang="hi"` from `<html>` because nothing marks it
    otherwise. The reset's job is protecting Devanagari from tracking;
    losing the brand's own -.01em display tracking on every Hindi page is
    collateral the rule was never meant to cause, so app.css now excludes
    `.wordmark b` from the reset by name rather than accepting the loss."""
    assert lang_en["wordmarkTracking"] not in (None, "normal"), (
        ".wordmark b lost its display tracking on the Hindi page")
