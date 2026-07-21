# 0001 — Zero JavaScript

**Status: OPEN. NOT DECIDED.** Recorded 2026-07-21.

This document exists because the rule is currently enforced by a test and asserted in the
README, but no evidence for it was ever written down. Nothing here changes the rule. The
rule stays as it is until the evidence named at the bottom is gathered.

## Assumptions

The rule as it stands assumes, without any recorded measurement:

- that the audience is on constrained devices and constrained networks, so a script
  payload is a real cost;
- that "no `<script>` at all" is meaningfully better than "the page is fully useful before
  any script runs";
- that nothing the product will ever want to do requires client-side code.

None of these three is supported by a number anywhere in this repository.

## Analysis

**What the design brief actually said.** `docs/design-brief-v1.md:275-276`, verbatim:

> - Vanilla JavaScript is available and welcome, **but the page must be fully useful and
>   readable before any JS runs.** Progressive enhancement, not an SPA.

That is a *permission with a constraint*. It permits JavaScript and requires the page to
work without it.

**What it became.** `README.md:70-72`, verbatim:

> **No JavaScript.** Not "degrades gracefully" — the app ships zero `<script>` tags. Every
> control is a link or a form, and disclosure state rides in the query string, which is
> also what gives the "opening one definition closes another" behaviour. A test asserts
> this.

**No document in this repository records the transition** from the first to the second.
There is no study, no benchmark, no measurement, no user report. A search of `README.md`
and `docs/*.md` for `2G`, `low-end`, `weak signal`, `budget phone`, `data cost` returns
exactly one hit — `docs/USER-TEST.md:26` — and it is an assertion, not a measurement.

Be precise about the relationship: the brief **permits** JS and the rule **forbids** it.
That is a hardening, not a contradiction. Saying the brief "contradicts" the rule
overstates it, and pinning the wrong claim is the failure mode this project logs
(CASE-STUDY §10b, "Five tests that could not fail").

## Data points

| Claim | Evidence |
| --- | --- |
| The brief permitted JS | `docs/design-brief-v1.md:275-276` (quoted above) |
| The README forbids it | `README.md:70-72` |
| A test pins it | `tests/test_web.py:48` `test_pages_carry_no_javascript`, asserting `"<script" not in ...text.lower()` at `:52`; a second assertion at `tests/test_web.py:729` |
| No measurement exists | grep over `README.md` + `docs/*.md` for device/network terms: 1 hit, `docs/USER-TEST.md:26`, an assertion |
| It blocks web push | The Push API requires a registered service worker, and a service worker is a script. No `<script>` means no registration call, so push cannot be built without breaking this rule. See [0003](0003-notifications-and-the-pull-ritual.md) |

**The zero-JS test's bite is unverified.** It was read, not mutated. Nobody has added a
`<script>` tag and watched it go red. Under this project's own standing lesson — *a test
that cannot fail is worse than no test* — the enforcement claim is weaker than it looks.

## The real benefits of zero JavaScript (the case FOR the rule)

This is not a one-sided document. The rule has bought real things:

1. **It is a forcing function on state.** Because disclosure state has to ride in the query
   string, every expandable definition is addressable, shareable and back-button-correct.
   That is the "opening one definition closes another" behaviour the README names. A JS
   implementation would almost certainly have used hidden local state and lost it.
2. **No hydration gap.** There is no window in which the page is visible but not yet
   interactive, and no possibility of a script error leaving a health page half-dead.
3. **Nothing to audit for leaks.** The privacy work (CASE-STUDY §11, "The false privacy
   claim was still on every page") was tractable partly because there is no client-side
   code that could beacon the persona anywhere. `tests/test_privacy.py` can enumerate
   third-party origins because the only one is the font host.
4. **The constraint produced the design.** Server-rendered forms and links are why the app
   works with the browser rather than around it.

These are genuine, and they are also **arguments for "progressive enhancement" as much as
for "zero"**. Each one survives a build where scripts exist but the page is complete
without them. That is exactly why the question is open rather than closed.

## What changed our mind

Nothing yet — and that is the finding. What changed was our *confidence*: we discovered the
rule has no recorded basis. It was inherited, hardened and then enforced mechanically, and
the mechanism made it feel decided. An enforced rule and an evidenced rule are different
things.

## What we kept

The rule, unchanged. Zero `<script>` tags. `tests/test_web.py:48` stays. Nothing in this
run touches it.

## What we are modifying

Nothing in the code. Only the record: this rule is now logged as an open question with a
named falsification path instead of an unexamined constant.

## Risks accepted

- **We keep paying a cost we have not priced.** If the constraint is unnecessary, we are
  spending design effort on it every time a feature wants client state.
- **The blocked feature stays blocked.** Web push is unavailable while this stands. That
  is accepted for now, but for an independent reason (see [0003](0003-notifications-and-the-pull-ritual.md)):
  the evidence for push is weak on its own merits, so the architectural block is not
  currently the binding constraint. If the evidence for push ever strengthened, this
  document would become urgent.
- **We may be defending an aesthetic as an ethic.** Worth naming explicitly.

## What would falsify it

Falsify the RULE (i.e. justify relaxing to the brief's original "progressive enhancement"):

1. A measurement of the actual audience's devices and connections showing that a small,
   deferred script is not a material cost — from the user test in `docs/USER-TEST.md`,
   which is already written and unrun.
2. A concrete user-valued feature that (a) cannot be built server-rendered, and (b) has
   evidence behind it. Push is currently (a) but not (b).
3. A demonstration that the query-string state model breaks down — e.g. a URL that becomes
   unshareable or unreadable because too much disclosure state is encoded in it.

Falsify the CASE FOR RELAXING (i.e. confirm the rule should stay hard):

4. A measurement showing the audience is on devices/networks where any script is a real
   cost.
5. A demonstration that "progressive enhancement" cannot be *mechanically enforced*. The
   current rule's strength is that `"<script" not in body` is a one-line, unarguable check.
   "The page is fully useful before JS runs" has no such check. If nobody can write a test
   that bites for the weaker rule, the stronger rule wins on enforceability alone — and
   this project's own history (CASE-STUDY §10b) says prose rules drift and tested rules do
   not.

**First step, cheapest by far:** mutate `tests/test_web.py:48`. Add a `<script>` tag to a
template, confirm the test goes red, remove it. Until that is done we do not actually know
the rule is enforced at all.
