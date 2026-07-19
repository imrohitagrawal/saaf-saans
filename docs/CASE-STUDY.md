# SaafSaans — a decision record

What was built, what the evidence said, and why the follow-up was cancelled.

Written 2026-07-20. Every number here is reproducible from this repository or from the
cited sources. Where something is unverified or self-reported, it says so.

---

## 1. Timeline

| Date | Event |
|---|---|
| Before 18 Jul | Built for a hackathon as a 4-tab Streamlit app. Did not place. |
| 18–19 Jul | Post-mortem; wedge identified as the failure, not build quality. |
| 19 Jul | Migrated Streamlit → FastAPI + Jinja2. Approved design implemented. |
| 19 Jul | 45-agent adversarial code review → 24 confirmed defects, fixed. |
| 19 Jul | Tagged `v1.0.0`, pushed. |
| 20 Jul | Three research studies on the planned phase 2 → premise did not survive. |
| 20 Jul | **Phase 2 as specced cancelled.** Effort redirected to finishing v1. |

The hackathon placement is self-reported and not independently verifiable.

## 2. The artifact, measured

Reproduce any of these from a clone:

| Metric | Value | How to check |
|---|---|---|
| Tests | **186 passing** | `pytest -q` |
| Test files | 13 | `ls tests/test_*.py` |
| Application Python | 2,750 lines | `find saafsaans -name '*.py' \| xargs wc -l` |
| CSS + templates | 925 lines | `wc -l saafsaans/web/static/app.css saafsaans/web/templates/*.html` |
| Test code | 1,712 lines | `find tests -name '*.py' \| xargs wc -l` |
| Commits | 19 | `git log --oneline \| wc -l` |
| v0.9 → v1.0.0 | 34 files, +1,024 / −1,739 | `git diff --shortstat v0.9-streamlit..v1.0.0` |

Test code is 62% the size of application code. The rebuild **removed** 715 more lines
than it added.

Three tests are unusual and worth naming, because they encode claims the documentation
makes rather than behaviour the code exhibits:

- `test_dark_severity_ramp_is_monotonic_in_luminance` — parses the stylesheet, computes
  WCAG relative luminance, asserts severity tracks contrast in **both** themes.
- `test_band_chip_word_and_control_borders_meet_contrast` — computes contrast ratios for
  every band chip and control border from the stylesheet.
- `test_pages_carry_no_javascript` — asserts the app ships zero `<script>` tags.

## 3. What the adversarial code review found

45 agents across five dimensions (docs accuracy, dead code, accessibility, privacy,
correctness). Every finding was then attacked by an independent refuter instructed to
default to "not a defect." **24 survived.**

The worst was in the documentation, not the code:

> **The README claimed the persona is never written to any index. It was false.**
> `locality` was written to `app-telemetry` on every request, deliberately, to power the
> Observability dashboard. Age, condition and activity never were.

For a product whose stated value is honesty about its own data, an untrue privacy
statement is the most damaging possible defect. It is the same failure as the original
build's uncited risk weights: a claim that sounded rigorous and wasn't checked.

Others, condensed:

- **Numbers whose labels lied.** "blocked, last 7 days" aggregated the entire index;
  "questions answered" counted blocked and errored turns.
- **Stale data shown as live.** Any stored reading counted as current regardless of age.
- **Accessibility asserted, not measured.** `aria-pressed` on `<a>` elements (unsupported);
  no `<main>`; no skip link; section titles as `div`s; a focus ring clipped by
  `overflow: hidden`; a severity ramp that was **non-monotonic in dark mode while the
  README claimed otherwise**.
- **Seeding was not idempotent.** `setup_indices.py` used generated document ids, so each
  run appended another copy of the 34 advisories. Three runs left 102 documents, and
  answers cited the same source twice.
- **Tests wrote to the production index.** Every `pytest` run inflated the dashboards the
  app displays.

## 4. What the research found

Three studies, 172 agents, ~4.76M tokens, each claim attacked by independent refuters
before counting.

**Kill rates matter more than findings.** In the evidence study, **7 of 14 claims were
refuted** — a 50% failure rate on claims that had already passed a first pass. Two of my
own confident statements about a government forecast product died there.

### The premise did not survive

| Claim under test | Evidence |
|---|---|
| Air-quality information changes behaviour | One positive health outcome (≈25% fewer asthma ED visits, CI 1–47%) against **six nulls**. The *Lancet Planetary Health* authors conclude alerts alone have limited public-health effect. |
| People act on repeated warnings | Response to a **second consecutive alert day falls to ~2%**, statistically indistinguishable from zero. Delhi's hazardous season is 60–120 consecutive days. |
| A daily exposure ledger would retain users | Lifestyle self-monitoring: **70% abandon within 100 days, >95% by 300.** |
| Push messaging changes habits | **Kilkari** — 10M+ subscribers, the world's largest maternal voice programme — returned a **null** on its primary outcome (RCT, n=5,095). |
| Masks are a reliable protective action | Cochrane (11 studies, 3,372 participants): **very low certainty**, "may have little or no impact on physiological markers." A well-powered US trial (n=50) found N95s did **not** mitigate near-roadway effects. |
| "The best hours to go out tomorrow are 2–4pm" | IITM's Delhi model: **r = 0.5 for hourly PM2.5 at 24h** (R² ≈ 0.25), with systematic range compression. **WAQI's API returns daily rows only** — no timestamp on the minimum. The data cannot say *when*. |

### Assumptions that were simply wrong

- **"Nobody personalises by health condition."** AQI.in already offers Asthma, Heart,
  COPD, Sinus and returns tailored text.
- **"Hindi is unserved."** WAQI already supports Hindi for the numbers. What is unserved
  is the *advice*.
- **"Telegram, because WhatsApp costs per conversation."** WhatsApp Business is **₹0** for
  reply-driven use — service messages and everything inside an open 24-hour window are
  free. The cost concern was backwards.
- **"Outdoor workers are the target."** Correct that they are unserved — but every
  behavioural study measures *retreating indoors* or *skipping discretionary exercise*,
  neither available to an auto driver or a mason. The systematic review contains **zero
  Indian or LMIC studies.**

### What did survive

- Vernacular language is the **primary adoption barrier** in India, and it buys trust.
- Digital-first delivery **widened inequity** in CoWIN and Kilkari.
- **Pull beats push**: an IVR channel workers dial into reached **81% completion**; a push
  channel reached **~39% retention**.
- What predicts action is **comprehension, perceived severity, self-efficacy and
  clinician endorsement** — not demographics.
- Delhi's school RCT found **risk compensation**: HEPA purifiers crowded out protective
  behaviour. Any feature signalling "you are protected" is a hazard.

## 5. The decision

**Phase 2 as specified — a personal inhaled-dose exposure ledger — was cancelled.**

Not because it was hard, but because the evidence placed it in the product category with
the worst documented retention, dependent on a daily habit the literature says does not
form, in a market where the differentiating feature had already been built by others.

Effort was redirected to finishing v1: correcting the false privacy claim, fixing the 24
defects, and shipping something honest and complete rather than something larger.

## 6. What this demonstrates — and what it does not

**Reasonable claims:**

- Diagnosing failure by cause rather than symptom. The original loss was attributed to
  wedge selection, not code quality, and that diagnosis held up.
- Building verification that outlives the author: tests that compute contrast ratios from
  the stylesheet and assert documented claims, not just behaviour.
- Using adversarial review deliberately — refuters instructed to default to "not a
  defect," so surviving findings mean something. 50% of claims died in one study.
- Correcting a false claim in one's own documentation once found, in public, in the commit
  message.
- Cancelling committed work on evidence.

**What it does not demonstrate — a sceptical reader will ask these:**

- **No real users.** Zero people outside the author have used this. Every usability claim
  is reasoning, not observation.
- **Not deployed.** It runs locally. There is no public URL.
- **Written with heavy AI assistance.** The code was largely produced by an AI assistant
  under direction. The human contribution was problem selection, quality standards,
  rejecting inadequate output, and the decision to stop — not line-by-line authorship.
  Anyone reading this should weight it accordingly.
- **The research was AI-conducted.** Sources are cited and adversarially verified, but a
  human did not read every paper.
- **No peer review.** Single developer, no external code review.
- **The hackathon result is self-reported.**
- **The product was never tested against its own hypothesis.** Whether it changes
  behaviour is unknown, because nobody used it.

## 7. What would be done differently

- **Test the premise before building.** The research that killed phase 2 would have cost a
  fraction of building phase 1 and could have run first.
- **Write the claim, then verify it.** Both the false privacy statement and the
  non-monotonic ramp were documentation written ahead of measurement.
- **Isolate side-effecting tests from the first commit**, rather than discovering that the
  suite was polluting the dashboards it displays.
- **Separate the audience from the artifact earlier.** Two rebuild attempts failed because
  a generic shell was restyled rather than redesigned.

## 8. Open items

- Deploy v1 publicly.
- Hindi for the *advice*, not just the numbers — the one evidence-backed improvement.
- Read CDSCO's Oct 2025 draft guidance on medical device software before any health-advice
  product ships. It could not be retrieved during research and is the most
  decision-relevant unread document.
- Put v1 in front of two or three real people and record what actually happens.
