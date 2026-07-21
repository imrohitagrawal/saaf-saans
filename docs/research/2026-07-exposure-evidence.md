# Research — personal exposure, protection and behaviour (July 2026)

Deep-research output. **Kill rate: 9 of 25 claims refuted (36%) — but only 20 of the 25
are enumerated in this file, so the headline cannot be reproduced from its own contents.**

> **Audit note, 2026-07-21.** What is recorded below is 9 refuted (R1–R4 individually,
> R5–R9 only as a shared pattern), 9 survived (D1–D9) and 2 search-layer (S1–S2) = **20**.
> Five claims are missing from the enumeration entirely, and five of the nine refutations
> (R5–R9) have no content recorded. Since this document's own instruction is "read the
> refutations first, they are the most valuable part", five unrecorded refutations defeat
> its stated purpose. The 36% arithmetic is correct *on the asserted 25*; it is not
> auditable from what is written here. Treat the kill rate as an unverified headline until
> the missing claims are written up or the denominator is corrected by re-derivation.

Read the refutations first. They are the most valuable part of this document: each one is a
claim that sounded right, that a reasonable person would have built on, and that did not
survive checking. Four of them were headed for the product.

**How to use this file.** Every claim below carries a verification status. Nothing marked
*search-layer only* may appear in user-facing prose (Hard Rule 5). Numbers marked *rank
order only* may never be printed as µg/m³.

---

## Part 1 — REFUTED (record these, and why)

### R1. "Home dominates personal dose" — REFUTED

The widely-quoted figures that people receive 67% / 89% of their PM exposure at home are
**time-budget artefacts, not evidence that home air is dirtier**. People spend most of
their hours indoors at home, so most of a cumulative dose accrues there *arithmetically*,
at whatever concentration. The statistic says nothing about where the concentration is
high, and nothing about where an intervention would pay.

*Why it mattered:* it was about to justify making the app home-centric — indoor advice
first, purifier guidance as the lead recommendation. It supports no such thing. A share of
exposure is not a marginal effect.

### R2. "Clean cooking energy is the primary recommendation" — REFUTED

Refuted **for this app's audience**, which is urban Delhi/NCR. The clean-cooking evidence
base is drawn from populations using solid biomass fuels. That is a serious global health
problem and it is not the exposure pathway of the app's users. Importing the recommendation
would be transplanting a finding across an incompatible population.

*Note the shape of this refutation:* the underlying research is sound. The error was
audience transfer. This is the most repeatable failure mode in the set.

### R3. "Ambient infiltration dominates indoor sources in the Delhi model" — REFUTED

Not supported as stated. The claim was traced back to the CONTAM simulation (D1 below) and
the model does not establish source apportionment of that kind — it models the effect of
filtration under assumed conditions. Reading a dominance conclusion out of it is reading
past what the model computes.

### R4. "Buses are lowest for black carbon" — REFUTED

Contradicted by the Delhi commute measurements themselves (D5): bus 113 µg/m³ sits above AC
car 89 and metro 72. The claim appears to come from conflating pollutants and cities. There
is no support here for telling anyone that a bus is the clean choice.

### R5–R9. Five further claims did not survive

The remaining refutations were variants of the same three errors and are recorded here as a
pattern rather than individually, because the pattern is what transfers:

- **Time-share read as causation** (the R1 shape).
- **Population transfer** — a finding from a different exposure regime applied to urban
  Delhi (the R2 shape).
- **Simulation read as measurement** — a modelled output quoted as an observed one (the R3
  shape).

Every one of the nine was plausible. Three were quantitative and therefore *more*
convincing, not less.

### A correction to the previous round's framing

The prior research round asserted there were **"ZERO Indian/LMIC studies"** on personal
exposure. **That framing was wrong and is withdrawn.** Indian evidence exists and is used
throughout this document:

- the **CHAI project** (Telangana, n = 50, 227 person-days) — personal exposure measurement;
- the **Kanpur** in-car study (120 trips);
- the **Delhi commute-mode** campaign (Maji et al. 2021);
- **Pant et al. 2017** (Delhi personal vs ambient).

The correct statement is that Indian personal-exposure studies are **few and small**, not
absent. The difference matters: "none exists" licenses ignoring the question, "few and
small" licenses using them with stated uncertainty.

---

## Part 2 — SURVIVED (verified; sources given except where flagged)

> **Audit note, 2026-07-21.** This part was headed "verified, with sources", and three of
> its nine entries name no author, journal or year: **D1** ("2026 meta-analysis, 27 RCTs"),
> **D2** ("17 sham-controlled RCTs") and **D5** ("the Detroit gap"), the last of which the
> document itself calls "the most important single finding". D3, D4, D6 and D8 are properly
> cited. This matters most for D1 and D2, because those are the two the copy-review
> checklist at the end of this file converts into hard product prohibitions: someone
> checking whether the meta-analysis covers this app's population has nothing to follow —
> the same audience-transfer failure this document records as R2, with no way to detect it.
> The findings are left in place, flagged, rather than deleted: they are load-bearing for
> rules that make the product *more* cautious, and removing them would relax those rules on
> the strength of a citation gap.

### D1. Personal protective measures show NO lung-function benefit

2026 meta-analysis, **27 RCTs**. FEV1 **SMD 0.04**; PEF **0.00**; FVC **0.00**.
**⚠ Source not captured** — no author, journal or year recorded; see the audit note above.
GRADE certainty: **low to very low**.

**Product consequence: the app must never promise a health outcome.** Not "you will breathe
better", not "this protects your lungs". The app's product is information for a decision
(see [decision 0004](../decisions/0004-value-proposition.md)).

### D2. …but "purifiers do nothing" is ALSO false

The same body of evidence shows real physiological effects on other endpoints:

- Systolic BP **−3.94 mmHg**, 95% CI **−7.00 to −0.89**, **17 sham-controlled RCTs**.
  **⚠ Source not captured** — see the audit note at the head of Part 2.
- Significant **FeNO** (airway inflammation) reduction.

**Product consequence:** the app must not overcorrect into nihilism. D1 and D2 together
give the only defensible position: *measurable physiological effects, no demonstrated
lung-function benefit, low certainty throughout.*

### D3. Filtration cuts indoor PM2.5 by 11–82%

Zhu et al., *Indoor Air* 2021, review of **54 articles**. Range **11–82%**.
**Overall certainty: VERY LOW.**

**Product consequence: no specific number may ever be promised.** The range spans nearly
the whole possible space. "A purifier reduces indoor PM2.5 by X%" is unwritable for any X.

### D4. The Delhi CONTAM model: 103 → ~29 µg/m³

Liao et al., *IJERPH* 2019. Modelled reduction from 103 to about 29 µg/m³ under
**idealised all-day use**.

Three caveats, all load-bearing:

1. It is a **simulation, not a measurement**.
2. "Idealised all-day use" is not how anyone runs a purifier.
3. **IJERPH was delisted from Web of Science in 2023.** Not a refutation of this paper, but
   it lowers the venue's weight and must be disclosed wherever the number is used.

### D5. The Detroit gap: 53% personal vs 60% indoor

Measured. Indoor concentration fell 60%; **personal** exposure fell only **53%** — because
people leave the filtered room.
**⚠ Source not captured** — no author, journal or year recorded, for the finding this
document calls its most important. See the audit note at the head of Part 2.

**This is the most important single finding in the document.** It is the general form of
the whole exposure problem: an intervention's effect on a *place* systematically overstates
its effect on a *person*, because people move. R1's error is a special case of ignoring
this.

### D6. Delhi commute modes — RANK ORDER ONLY

Maji et al. 2021:

| Mode | µg/m³ |
| --- | --- |
| Rickshaw | 266 |
| Walking | 259 |
| Non-AC car | 149 |
| Bus | 113 |
| AC car | 89 |
| Metro | 72 |

**Never surface these as stable µg/m³ figures.** Single winter campaign, one uncalibrated
photometer, **CV ~60%**. The rank order is usable; the numbers are not.

**And never say "stop walking."** Active-travel health benefit generally exceeds the
exposure penalty (Tainio et al.). Telling a person in Delhi to stop walking would be a
net-harm recommendation derived from a partial view of their health.

### D7. The recirculation button, not "AC on"

Kanpur in-car study, **120 trips**: windows-open **197.6** vs AC with recirculation **OFF**
**124.9** µg/m³; recirculation **ON** lower still. Cabin filter age matters — roughly
**55% reduction when new vs 39% aged**.

**Product consequence:** the actionable lever is the *recirculation button*. "Use the AC" is
the wrong instruction; a car with AC on and recirculation off is drawing outside air
through an aged filter.

### D8. Ambient monitors as a proxy — and why this cuts both ways

Pant et al. 2017: ambient monitors explain **r² = 0.51** of personal exposure in Delhi
**winter**, **0.21** in **summer**. Sample sizes are tiny: **n = 12 / n = 6**.

**Do not misuse this.** The obvious reading — "ambient AQI is uninformative, so personal
measurement is required" — inverts the seasonal detail. In the **Nov–Jan** season this app
is most about, the ambient monitor is the **stronger** proxy, not the weaker one. The
source undermines an ambient-only approach in summer and *supports* it in winter.

This is also the empirical backstop for the app's whole design: an ambient station reading,
personalised by susceptibility and activity, is a defensible instrument in the season that
matters.

### D9. CHAI — Indian personal-exposure evidence exists

CHAI project, Telangana, **n = 50**, **227 person-days**. Small, and real. Cited here
principally to retire the "no Indian evidence" framing (above), and as the first place to
look for the confirming study named in
[decision 0004](../decisions/0004-value-proposition.md)'s falsification section.

---

## Part 3 — SEARCH-LAYER ONLY (NOT adversarially verified)

> Everything in this section was found at the search layer and **not** put through
> adversarial verification. It is load-bearing for
> [decision 0003](../decisions/0003-notifications-and-the-pull-ritual.md), which is why
> that decision names the risk explicitly. **Do not put any of it in user-facing prose.**

### S1. The day-2 alert collapse has an ECONOMIC mechanism

Graff Zivin & Neidell, **NBER WP 14209**. The drop in response after the first day of a
multi-day alert episode is driven by **cost**, not attention: postponing an outdoor
activity one day is cheap, postponing many days is not.

Also: **short reprieves reset willingness to respond.** A clean day mid-episode restores
responsiveness to the next alert.

*Why it matters:* an attentional mechanism implies alert design can fix the collapse. An
economic one implies it cannot, and that alerting on days 2–5 spends credibility on days
where compliance was never available. See 0003.

### S2. The Delhi schools cluster-RCT

~**9,000 students**, **2 years**. The **education** arm — comprehension, not hardware —
raised protective behaviour, with **positive peer spillovers**. **Purifiers** were **partly
offset by risk compensation**.

*Why it matters:* the thing that moved behaviour was people understanding their situation.
Risk compensation on the hardware arm is the behavioural mirror of D5's Detroit gap — an
intervention's effect on a place is eroded by what the person then does.

---

## What this evidence forbids the app from saying

A checklist, derived above, usable as a copy review:

1. No promised health outcome, ever (D1).
2. No specific filtration percentage (D3).
3. No µg/m³ figure for a commute mode (D6).
4. Never "stop walking" (D6, Tainio).
5. Never "use the AC" — say recirculation (D7).
6. Never "ambient AQI is uninformative" (D8).
7. Never a modelled figure presented as measured (D4).
8. Never a purifier dismissed as useless (D2).

## What would falsify this document

- A large, well-powered RCT finding a lung-function benefit would overturn D1 and change
  the app's permitted claims — this is the single most consequential open question.
- A Delhi personal-exposure study with n in the hundreds would replace D8's r² values,
  which currently rest on n = 12 / n = 6.
- Adversarial verification of S1 and S2 could move them into Part 2 — or refute them, in
  which case 0003 loses its evidential basis and rests on the architectural block alone.
- A repeat commute campaign with calibrated instruments would either promote D6's numbers
  out of rank-order-only status, or refute the ordering.
