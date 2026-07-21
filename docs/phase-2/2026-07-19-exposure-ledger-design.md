# SaafSaans Exposure Ledger — Design

Date: 2026-07-19
Status: **partially superseded.** Written before phase 1 finished, so it is stale in
three places, all resolved in [`INHERITED-FROM-V1.md`](INHERITED-FROM-V1.md),
which wins wherever the two disagree:

1. It describes v1 as a Streamlit app. v1 was migrated to **FastAPI + Jinja2** and
   shipped as `v1.0.0`; that stack and its token system are inherited, not rebuilt.
2. It treats **Postgres vs Elasticsearch as an open decision**. It is decided: Postgres
   + TimescaleDB.
3. It assumes the frontend starts from nothing. A working design system, the
   `presenters.py` pattern, and 186 tests carry over.

The wedge, the citation discipline, and the uncertainty policy below all still stand.

## Context

The previous SaafSaans (`~/Projects/saaf-saans`) was a 4-tab Streamlit "Command Center":
pick a persona from four dropdowns, see a live AQI number, chat about it. It was
submitted to a hackathon and did not reach the top 15.

The post-mortem identified the failure as **wedge selection, not execution quality**:

1. **Undifferentiated core loop.** IQAir, AQI.in, SAFAR and Google Maps already show
   AQI plus canned health advice. Nothing in the loop was defensible.
2. **The demo showcased plumbing, not value.** Two of four tabs (Observability,
   Security) demonstrated our own infrastructure. Nobody prompt-injects an
   air-quality bot; the red-team button read as sponsor-checklist compliance.
3. **No agency.** "Wear an N95, stay indoors" is what every Delhi resident already
   knows and largely cannot act on. The unmet need was never information.
4. **Retrieval theater.** `data/advisories.py` held 34 hardcoded rows behind an
   Elasticsearch BM25 query that returned results identical to a dict lookup.
5. **Invented numbers.** `services/risk.py` was the app's headline figure and its
   weights (COPD=18, heart=16, outdoor_exercise=14) cite nothing. The docstring
   said "documented weights"; the documentation was us.
6. **No evidence.** No user validated it, and no number quantified its impact.

This spec defines the rebuild. It keeps the domain (air quality → personal health
decision) and changes the wedge.

**Intended outcome:** a product whose headline number is *your* inhaled dose in
micrograms, computed from live measured concentrations and published physiological
constants, which tells you which single change to your day saves the most exposure —
and then proves, after the fact, how much it actually saved.

## Product definition

**Headline:** `You inhaled 312 µg of PM2.5 today.`

Not an AQI. A quantity, about the user, that no competing product displays.

Three pillars:

1. **Ledger** — dose accumulates over days and weeks, broken down by day-segment.
2. **Counterfactual** — perturb one segment, recompute, rank by µg saved.
   *"Shift your run 06:30→18:00: −84 µg (27%)."*
3. **Proof** — when a suggestion is taken, recompute the avoided dose from the real
   measured concentrations in both windows. `This week SaafSaans avoided 1,240 µg
   for you — 18% below baseline.` Auditable against raw station data.

Pillar 3 is the outcome metric v1 completely lacked. It is the demo closer.

### Input tiers

The concentration is **always live and measured**. Only the schedule is assumed.

- **Tier 1 — Standing schedule.** Preset day templates (Office commuter, WFH,
  Parent + school run, Runner) prefill a segmented day; user drags to adjust.
  ~20s to first number. Cold start only, not the product.
- **Tier 2 — Live exposure timer.** A "Heading out" button starts a session that
  samples measured µg/m³ at the nearest station every few minutes and integrates
  against the segment's activity level. Stop on return. This is **measured**
  exposure, not modelled. No GPS, no background permission, no mobile app —
  it runs in a browser tab.

### Non-goals for v1

- Google Timeline / location-history import (Tier 3) — deferred.
- Background GPS tracking or a native mobile app.
- Institutional/B2B dashboards (schools, worksites).
- LLM chat. The old app's chat was the least differentiated surface. Natural-language
  explanation may return later as a thin layer *over* the computed ledger, never as
  the primary interaction.
- Prompt-injection guard, security dashboard, red-team simulation.

## Scientific grounding

Every constant in the engine carries a `source` field. This is the direct remedy for
the `risk.py` failure and is the product's main credibility asset.

| Quantity | Value / range | Source |
|---|---|---|
| Inhalation rate by age × activity | 14 age groups × 5 activity levels, m³/min. Adult 21–31: sedentary 4.2e-3, light 1.2e-2, moderate 2.6e-2, high 5.0e-2. Child 6–11 high: 4.2e-2 | US EPA, *Exposure Factors Handbook 2011*, Ch. 6, **Table 6-2**, EPA/600/R-09/052F |
| Potential dose formula | `dose(µg) = C(µg/m³) × IR(m³/min) × t(min)` | US EPA, *Guidelines for Exposure Assessment*, EPA/600/Z-92/001 (1992); EPA ExpoBox inhalation route |
| Indoor infiltration factor F_inf | 0.30–0.82 (PM2.5, review of 21 studies) | Chen C. & Zhao B. (2011), *Atmos. Environ.* 45(2):275–288 |
| Delhi indoor/outdoor ratio | I/O 1.10–1.72; indoor 98.3±51.2 vs outdoor 67.7±33.2 µg/m³ | Ali et al. (2025), *Discover Environment* 3:265 |
| Air purifier reduction | ~50% realistic sustained; ~80% closed correctly-sized room, no indoor sources | US EPA (2018), *Residential Air Cleaners: A Technical Summary*, 3rd ed.; Vyas et al. (2016) *PLoS ONE* 11(12):e0167999 |
| CPCB AQI PM2.5 breakpoints | 0–30 / 31–60 / 61–90 / 91–120 / 121–250 / 250+ | CPCB, *National Air Quality Index* (2014), Table 3.11 |
| Cigarette equivalence | `cig/day ≈ PM2.5(µg/m³) / 22` | Muller & Muller, Berkeley Earth (2015) — **see caveat below** |

### Uncertainty policy

Being visibly honest about what we do not know is a feature. Three rules:

1. **EPA rates its own Table 6-2 confidence as "Medium."** The app says so, on the page.
2. **No Delhi-measured F_inf distribution exists in the literature.** F_inf is therefore
   a user-adjustable slider with a stated range, never a hard-coded constant.
3. **Cigarette equivalence is a Berkeley Earth blog post, never peer-reviewed.** The
   confidence interval on its underlying mortality estimate implies the true factor
   is somewhere in 16–50 µg/m³ per cigarette, and PGIMER pulmonologists have publicly
   called the framing misleading. It therefore ships as a **clearly-labelled secondary
   framing** — always with `≈`, always computed from µg/m³ and never from AQI, with
   the source linked and the weakness stated inline. It is never the headline.

### Why the engine must not run on AQI

Three independent reasons, any one of which is disqualifying:

1. CPCB AQI is a **24-hour rolling average**. Feeding it into a minute-resolution dose
   integral smooths away exactly the peaks a personal-exposure tool exists to reveal.
2. AQI is the **max across pollutants**. A Delhi station AQI is not necessarily the
   PM2.5 sub-index — it can be PM10 during dust events or O3 in summer.
3. The top band is open-ended (`250+`), so **AQI > 400 is not invertible** without
   inventing a breakpoint.

The engine consumes µg/m³ directly. This is the technical spine of the product.

## Data sources

| Source | Role | Live | µg/m³ | History | Licence |
|---|---|---|---|---|---|
| **OpenAQ v3** | **Primary** | Yes | Yes | 2016+ | Per-source `commercialUseAllowed` |
| data.gov.in CPCB | Live cross-check | Yes | No (AQI sub-indices) | No | GODL-India, attribution required |
| CAMS / Open-Meteo | Forecast + gap-fill | Yes | Yes (modelled grid) | Yes | Copernicus, attribution |
| ~~WAQI~~ | **Dropped** | Yes | Partial | **No** | Non-commercial; forbids archiving |

WAQI is dropped for **capability**, not licensing: it has no history endpoint, and an
exposure *ledger* is historical by definition. Its ToS separately forbids building an
archive from its feed. The clean OpenAQ licence is a bonus that keeps a real launch open.

**Blocked on:** free API keys for OpenAQ v3 (`X-API-Key` header required) and
data.gov.in (the shared public demo key is globally rate-limited). Verified 2026-07-19.

## Architecture

```
apps/
  api/                    FastAPI
    providers/
      openaq.py           primary: measurements in µg/m³, live + historical
      cpcb.py             data.gov.in cross-check
      base.py             Provider protocol + fixture/mock provider
    engine/
      exposure.py         dose = C × IR × t; EPA Table 6-2 lookup
      indoor.py           C_in = F_inf·C_out + (E/V)/(a+k+ηλ)
      timeline.py         a day as ordered segments
      counterfactual.py   perturb → recompute → rank by µg saved
      constants.py        every value carries {value, unit, source, confidence}
    routes/
  web/                    Next.js + TypeScript + Tailwind + shadcn/ui
```

### Module contracts

- **`exposure.py`** — pure, no I/O. `dose(concentration_series, age_band, activity,
  duration) -> DoseResult`. Deterministic and exhaustively unit-testable, like the old
  `risk.py` but with cited rather than invented constants.
- **`indoor.py`** — pure. Single-compartment steady-state mass balance. Takes
  `f_inf`, air-exchange rate, purifier CADR, room volume, indoor source term.
  Returns indoor concentration **with an uncertainty band**, not a point estimate.
- **`timeline.py`** — a day is an ordered list of `Segment(start, end, location,
  indoor|outdoor, activity_level)`. Templates are seed data for this structure.
- **`counterfactual.py`** — the product. Given a timeline and real concentration
  history, enumerate legal perturbations (shift a segment in time, change transport
  mode, close windows, run purifier), recompute total dose for each, rank by µg saved.
- **`providers/base.py`** — a `Provider` protocol so the engine is testable against
  recorded fixtures with zero network. Every provider is timeout-bounded.

### Open decision: Elasticsearch or Postgres?

v1 used Elasticsearch. Its only genuine search workload was 34 advisory rows, which is
why that choice read as resume-driven rather than motivated.

The new workload is a **time-series concentration store plus relational user data**
(users, schedules, segments, suggestions taken, avoided-dose events). That is squarely
Postgres + TimescaleDB territory. Elasticsearch would again be a dependency chosen for
how it sounds rather than what it does.

**Recommendation: Postgres + TimescaleDB.** Elasticsearch remains available if a real
search surface appears later.

## Frontend

Next.js + TypeScript + Tailwind + shadcn/ui, designed using the `ui-ux-pro-max` and
`frontend-design` skills (both enabled 2026-07-19; neither was used for v1, which was
577 lines of hand-written HTML strings injected through
`st.markdown(unsafe_allow_html=True)`).

Charts go through the `dataviz` skill — also available during v1 and also never invoked.

Core screens: onboarding (template pick → day builder), today (headline dose +
segment breakdown + top counterfactual), ledger (week/month accumulation + avoided
dose), live timer.

## Verification

- **Unit** — engine modules are pure; property-test dose monotonicity (more time,
  higher concentration, or higher exertion never lowers dose) and verify Table 6-2
  lookups against values transcribed directly from the EPA PDF.
- **Golden case** — one worked example computed by hand from published constants,
  asserted end-to-end, with the arithmetic shown in the test docstring.
- **Provider contract tests** — run against recorded fixtures, no network.
- **Live smoke** — fetch real Delhi PM2.5 from OpenAQ, assert plausible ranges.
- **Falsifiability check** — the avoided-dose figure must be reproducible by hand
  from raw station data. If a reviewer cannot audit it, it does not ship.
- **Real users** — 1–2 colleagues run it for a week. Not statistically meaningful,
  and will be described as such rather than dressed up as validation.

## Milestones

1. Repo scaffold, provider protocol, fixtures, `constants.py` with citations.
2. `exposure.py` + `indoor.py` + tests. Golden case passes.
3. OpenAQ + CPCB providers live against real keys.
4. `timeline.py` + templates; `counterfactual.py` + ranking.
5. Next.js frontend, designed via the UI skills.
6. Live exposure timer (Tier 2).
7. Avoided-dose proof metric.
8. Deploy; colleague testing; README with the full citation table.
