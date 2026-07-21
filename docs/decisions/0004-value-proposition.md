# 0004 — The value proposition: the same air is not the same dose for you

**Status: DECIDED 2026-07-21.** The differentiator is the personal delta. It already
exists in code and is buried.

Every other Delhi air-quality product answers *"how bad is the air?"* — a question with one
answer for eight million people. This app answers *"how bad is it **for you**, today, given
what you are planning?"* That is the only thing here that a dashboard cannot do.

## Assumptions

1. That a reader already has access to an AQI number from a dozen free sources, so
   re-displaying one adds nothing.
2. That personal variation in *dose* and *susceptibility* is large enough to change a
   decision.
3. That a reader can act on a comparison ("you vs a healthy adult") more readily than on
   an absolute index.

Assumption 2 is the load-bearing one, and it is only partly evidenced — see Risks.

## Analysis

### The delta already exists

`saafsaans/web/presenters.py:218-232` computes and renders exactly this sentence:

> A healthy adult with the same plans as you would be at {baseline}. Your {score} comes
> from {reasons} — the gap is your body, not the air.

with two fallbacks: `gap_plain` ("Your {score} is higher than theirs") when no reasons
resolve, and `same` ("A healthy adult … would be at {baseline} too — that's you today")
when there is no gap.

This is the product. It is a sentence that no dashboard on the market prints.

### It is buried

> **The table below was re-measured at HEAD on 2026-07-21 and is now pinned.** As
> originally written it was taken from a page that no longer exists: nodes 13 and 14 were
> `◌ SAMPLE — not a reading` and `AQI 400 · VERY POOR`, both produced by the hardcoded
> winter stand-in that [0002](0002-sample-data-honesty.md) deleted. It was also unpinned,
> which is the failure `CASE-STUDY.md:32` is cited elsewhere in these docs as the precedent
> against. Two audits are given, because the answer differs by state and the original gave
> no state at all.

**With a reading** (feed stubbed live at PM2.5 250 / PM10 400; ITO, Senior, Asthma,
Outdoor exercise), measured at commit `5146e9e`:

| Position | Content |
| --- | --- |
| 13 | `ITO` |
| 14 | `● LIVE · 10:00 AM` |
| 15 | `AQI 400 · VERY POOR` |
| 17 | the verdict `<h1>` |
| **20** | the terse chip `healthy adult, same plans · 79` |
| **29** | the full sentence, at byte offset 5468 (chip at 4347) |

The differentiating claim is the **29th** text node, roughly 1.1 KB below a terse chip that
states the same comparison without explaining it. Everything above it — the index, the
band, the verdict — is the commodity part, the part every competitor has. The original
argument therefore survives its own correction: the positions moved by one or two, the
byte gap shrank from 1.3 KB to 1.1 KB, and the conclusion is unchanged.

**In the shipped configuration** (no `WAQI_TOKEN`, no `ELASTIC_*` — what a visitor to
saafsaans.stackclimb.com actually gets when the feed is silent), the audit cannot be run at
all: node 14 is `◌ NO READING`, and `grep 'healthy adult'` over the rendered page returns
nothing. The comparison sentence and the chip are both suppressed, deliberately — both
quote risk scores computed from an assumed AQI. **So in the state the site is most often
in, the differentiator does not render at all.** That is a stronger version of this
document's own thesis than the one it was written with, and it is the state any "raise the
delta" work has to answer for first.

*(Correcting the record: an earlier note in this session cited positions 7 and 16 and the
phrase "the gap is yours". Both were wrong. The real positions are 19 and 29 and the real
phrase is "the gap is your body, not the air" — `grep -rn 'gap is yours'` returns no
matches. Pinning a misquoted string is the exact failure mode CASE-STUDY §10b logs.)*

### Why "dose, not concentration" is the right frame

The research supports the frame at the level of **rank order and mechanism**, and refuses
to support it at the level of numbers. Both halves matter:

- **Where you are changes your dose more than which day it is.** Delhi commute modes
  (Maji et al. 2021): rickshaw 266, walking 259, non-AC car 149, bus 113, AC car 89,
  metro 72 µg/m³. That is a ~3.7× spread across choices a person makes in a single
  morning. **Surface as rank order only** — a single winter campaign, one uncalibrated
  photometer, CV ~60%.
- **A specific, actionable lever exists.** Kanpur in-car study, 120 trips: windows-open
  197.6 vs AC with recirculation OFF 124.9 µg/m³, recirculation ON lower still. The
  **recirculation button** is the lever — not "AC on". Cabin filter age matters: ~55%
  reduction new vs 39% aged.
- **Ambient monitors are an imperfect but season-dependent proxy.** Pant et al. 2017:
  ambient explains r² = 0.51 of personal exposure in Delhi winter, 0.21 in summer (tiny
  n = 12 / n = 6). This cuts **both ways**, and the app must not misuse it: in the Nov–Jan
  season the app is most about, the ambient monitor is the *stronger* proxy. "AQI is
  uninformative" would be a misreading of this source.

Note the internal tension, which is the honest version: the personal delta the app
currently computes is driven by *susceptibility* (age, conditions) and *planned exertion*,
not by *location choice*. The commute evidence is the strongest quantitative support for
"same air, different dose," and it is about a variable the app does not yet use.

### What the app must never say

The 2026 meta-analysis (27 RCTs) found **no lung-function benefit** from personal
protective measures: FEV1 SMD 0.04, PEF 0.00, FVC 0.00, low/very-low GRADE. So the value
proposition is **information, not outcome**. The app helps you decide; it must never
promise you will be healthier. Equally, "purifiers do nothing" is also false (systolic BP
−3.94 mmHg, 95% CI −7.00 to −0.89, 17 sham-controlled RCTs), so the app must not sneer at
mitigation either. Full detail and the refuted claims:
[`research/2026-07-exposure-evidence.md`](../research/2026-07-exposure-evidence.md).

## Data points

| Claim | Evidence |
| --- | --- |
| The delta sentence exists | `saafsaans/web/presenters.py:218-232`, three variants |
| It renders at text-node 29, byte offset 5468 | Rendered at `5146e9e`, feed stubbed live: `/?locality=ITO&age=Senior&condition=Asthma&activity=Outdoor+exercise` |
| The chip renders at 20 | same render |
| Neither renders at all with no reading | same URL, shipped empty-credential env |
| Commute mode spread ~3.7× | Maji et al. 2021 — **rank order only** |
| Recirculation is the lever | Kanpur, 120 trips: 197.6 → 124.9 µg/m³ |
| Ambient proxy is season-dependent | Pant et al. 2017, r² 0.51 winter / 0.21 summer, n = 12 / 6 |
| No lung-function benefit from personal measures | 2026 meta-analysis, 27 RCTs |
| The risk score is half-grounded | `README.md:195-199`; CASE-STUDY §11 "Three places where a gap was left visible" |

## What changed our mind

We had been treating the comparison sentence as a *supporting detail* — a nice touch below
the reading. The position audit reversed it: the app leads with the commodity (an index and
a band anyone can get) and buries the differentiator 29 nodes down. The product's actual
claim is not in the product's most prominent position.

Second, the commute data changed what "personal" means. We had scoped personal to *who you
are* (age, conditions). The evidence says *where you will be in the next hour* moves dose
by more than most susceptibility differences do — and the app does not ask.

## What we kept

- The comparison sentence, its wording and all three variants. It is correct copy.
- The refusal to promise outcomes. This is now formally the value proposition's boundary.
- The visible gap around the risk score's grounding (`README.md:195-199`): the exposure
  factors are EPA-sourced, the susceptibility weights are not validated, and the app says
  so. That honesty stays.

## What we are modifying

Nothing in code in this run — this document records the position, not the rebuild. What it
licenses next, in order:

1. **Raise the delta.** The full sentence should sit with the verdict, not 1.3 KB below the
   terse chip. The chip and the sentence currently say the same thing twice, the terse one
   first.
2. **Do not add commute mode yet.** It is the strongest lever in the evidence and the
   weakest in measurement precision (CV ~60%). If it ships, it ships as **rank order with
   no µg/m³ figure**, and never as "stop walking" — active-travel health benefit generally
   exceeds the exposure penalty (Tainio et al.).
3. This depends on [0002](0002-sample-data-honesty.md) landing first. **It has landed**
   (see 0002's status header), which is why the audit above has two halves. A personal delta
   computed from a fabricated 400 is worse than a buried one — it makes the *differentiating*
   claim the fabricated one.

## Risks accepted

- **The susceptibility weights driving the delta are not validated.** The gap between 79
  and 91 is a modelled difference, not a measured one. The app discloses this; the value
  proposition nonetheless rests on it.
- **A comparison can be read as reassurance.** "A healthy adult would be at 79" may read as
  "79 is fine". Untested.
- **Personalisation costs privacy surface.** The persona is deliberately not logged
  (`tests/test_privacy.py`); any richer personalisation must not quietly reverse that.
- **The frame may simply not be what people want.** Nobody has watched a real person use
  this. §6 of the case study — "no observed usage" — remains the weakest part of the whole
  record.

## What would falsify it

1. **User testing shows readers ignore or misread the comparison** and want only the
   number. `docs/USER-TEST.md` and `docs/user-test-sheet.md` are written and unrun; this is
   the cheapest available test and it directly attacks the core claim.
2. **Evidence that personal variation is small relative to day-to-day ambient variation** in
   Delhi's Nov–Jan range. If a bad day is bad for everyone by roughly the same margin, the
   delta is a rounding error and the app is a dashboard with extra steps.
3. **A competitor shipping the same personalisation**, which would move the differentiator
   from the delta to the honesty (0002) — a defensible but different position.
4. Conversely, confirming evidence would be a measured personal-exposure study in Delhi
   showing susceptibility- and activity-driven dose differences of the same order as the
   commute-mode spread. The CHAI project (Telangana, n = 50, 227 person-days) is the
   nearest Indian personal-exposure work and is the place to look first.
