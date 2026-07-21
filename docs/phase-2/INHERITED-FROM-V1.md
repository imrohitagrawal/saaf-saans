# Phase 1 → Phase 2: what carries over

Written 2026-07-20, at the close of phase 1.

Phase 1 is [`~/Projects/saaf-saans`](../../saaf-saans), tagged `v1.0.0` — a Delhi
air-quality companion whose headline is the **ambient AQI**, with a personal risk score
layered on top.

Phase 2 is this repository — an **exposure ledger** whose headline is **inhaled dose in
micrograms**. Same domain, same service layer, different wedge.

This file records what to take, what to leave, and what phase 1 learned the hard way.
The design spec (`docs/phase-2/2026-07-19-exposure-ledger-design.md`) predates
phase 1's completion and is stale where the two disagree — **this file wins**.

---

## Inherit — port these, do not rewrite

| From v1 | Why |
|---|---|
| `services/waqi.py`, `es.py`, `guard.py`, `normalize.py`, `config.py`, `metrics.py` | Framework-independent, tested, and already handle timeouts, fallbacks and field whitelists. ~1,100 lines that work. |
| `web/presenters.py` **as a pattern** | Copy and geometry live outside both the templates and the services, so wording and arithmetic are unit-testable. This is why v1's copy could be fixed without touching a route. |
| `web/static/app.css` token system | Full light/dark pairs, a six-step severity ramp that is monotonic in luminance in **both** themes, per-band sky tokens. Measured, not guessed. |
| FastAPI + Jinja2 + zero JavaScript | Already built and proven in v1. The app ships no `<script>` tags; every control is a link or a form. |
| The test discipline | 186 tests, including some that compute contrast ratios straight from the stylesheet so accessibility cannot regress silently. |
| `data/advisories.py` (34 rows) | Still the grounding corpus for any advice text. |

## Leave behind

- **AQI as the headline.** Phase 1 already occupies that ground; repeating it is what made
  the original submission indistinguishable from IQAir and SAFAR.
- **`services/risk.py`.** Its weights (COPD +18, heart +16…) cite nothing. Phase 2 replaces
  the invented arithmetic with `dose = concentration × inhalation rate × duration`, where
  the rates come from the **US EPA Exposure Factors Handbook 2011, Table 6-2**.
- **WAQI as the data source.** Its terms forbid commercial use *and* archiving, and it has
  **no history endpoint** — an exposure ledger is historical by definition. Move to
  **OpenAQ v3** (real µg/m³, archive from 2016) with **data.gov.in CPCB** as cross-check.
  Both need free API keys.
- **Elasticsearch as the primary store.** v1's only genuine search workload was 34 rows.
  Phase 2's workload is time-series plus relational (users, schedules, segments, dose
  events) — **Postgres + TimescaleDB**. This is now decided, not open.

## Do not repeat — what the review found

Phase 1 closed with a 45-agent adversarial review. 24 findings survived refutation. The
ones that are really lessons, not bugs:

1. **A false claim in the README.** It said the persona is never indexed; locality was
   being indexed deliberately. Write what the code does, then check it.
2. **Numbers whose labels lied.** "blocked, last 7 days" aggregated the whole index;
   "questions answered" counted blocked and errored turns. Derive a number from the same
   window its label names.
3. **Stale data shown as live.** City Pulse marked any stored reading as current. In a
   health tool, freshness is a correctness property, not a nicety.
4. **Accessibility asserted rather than measured.** `aria-pressed` on links (unsupported),
   no `<main>`, no skip link, section titles as `div`s, a focus ring clipped by
   `overflow: hidden`, and a severity ramp that was **non-monotonic in dark mode while the
   README claimed otherwise**. Compute contrast; do not eyeball it.
5. **Seeding that was not idempotent.** `setup_indices.py` used generated ids, so each run
   tripled the corpus and answers cited the same source twice.
6. **Tests writing to the production index.** Every `pytest` run inflated the dashboards
   the app displays. Isolate side-effecting tests from day one.

## The wedge, restated

> **You inhaled 312 µg of PM2.5 today.**
> You'd expect 180 by now. 61% came from the 07:10 school run.
> Shift it to 09:15: **−84 µg**.

Three parts, in priority order:

1. **Ledger** — dose accumulates and is attributable by segment of the day.
2. **Counterfactual** — perturb one segment, recompute, rank by µg saved.
3. **Proof** — after a suggestion is taken, compute the µg actually avoided from the real
   measured concentrations in both windows. *This is the metric phase 1 never had.*

Every constant carries a `source` field. Uncertainty is displayed, not hidden: no Delhi
F_inf distribution exists in the literature, so it is a user-adjustable slider with a
stated range rather than a hard-coded number.

## Open before coding starts

- OpenAQ v3 and data.gov.in API keys (free; both were verified blocked without them).
- **Headline framing:** consumed (`312 µg`) or remaining (`188 µg of headroom`)? Leaning
  consumed with a pacing line — in a Delhi November, "remaining" hits zero before 09:00
  and an app that always says you failed stops being opened.
- Whether phase 2 keeps the v1 design language (IBM Plex, sky hero) or takes a new brief.
  The tokens carry over cleanly either way.
