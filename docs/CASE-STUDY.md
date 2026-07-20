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

Reproduce any of these from a clone. Two columns because the `v1-closure` branch changed
most of them; the `v1.0.0` figures are kept so the earlier version of this document stays
checkable rather than quietly overwritten.

| Metric | at `v1.0.0` | at `v1-closure` | How to check |
|---|---|---|---|
| Tests | 186 passing | **363 passing** | `pytest -q` |
| Test files | 13 | 16 | `ls tests/test_*.py` |
| Application Python | 2,750 lines | 4,305 lines | `find saafsaans -name '*.py' \| xargs wc -l` |
| CSS + templates | 925 lines | 1,089 lines | `wc -l saafsaans/web/static/app.css saafsaans/web/templates/*.html` |
| Test code | 1,712 lines | 3,668 lines | `find tests -name '*.py' \| xargs wc -l` |
| Commits | 19 | 46 at `a021623` | `git log --oneline a021623 \| wc -l` |
| v0.9 → v1.0.0 | 34 files, +1,024 / −1,739 | — | `git diff --shortstat v0.9-streamlit..v1.0.0` |
| v1.0.0 → v1-closure | — | 44 files, +4,523 / −383 | `git diff --shortstat master..v1-closure` |

Test code is **85%** the size of application code, up from 62%. The v1.0.0 rebuild **removed**
715 more lines than it added; the closure branch adds, because most of it is either a
correction with a test pinning it or the Hindi corpus.

Three tests are unusual and worth naming, because they encode claims the documentation
makes rather than behaviour the code exhibits:

- `test_dark_severity_ramp_is_monotonic_in_luminance` — parses the stylesheet, computes
  WCAG relative luminance, asserts severity tracks contrast in **both** themes.
- `test_band_chip_word_and_control_borders_meet_contrast` — computes contrast ratios for
  every band chip and control border from the stylesheet.
- `test_pages_carry_no_javascript` — asserts the app ships zero `<script>` tags.

The closure branch adds a fourth kind: tests whose subject is an *absence*.
`test_no_page_repeats_the_false_never_logged_claim` walks every page and fails on the
wording of a privacy claim that was once true-sounding and false. A defect that has been
fixed twice in two places is worth a test that watches for it in all of them.

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

## 8. The transferable asset is the method, not the app

The application is a Delhi air-quality tool. The **method** is domain-independent and is
written up separately in [`METHODOLOGY.md`](METHODOLOGY.md).

The single strongest piece of evidence in this whole record is a kill rate:

> In the evidence study, **7 of 14 claims were refuted** — a 50% failure rate on claims
> that had already survived a first pass. In the decision-gap study, 4 of 30 were killed.
> Two of those were claims this author had already stated confidently in conversation.

That number matters because it proves the process **rejects things**. A review that
confirms everything it looks at is not a review. Most descriptions of "AI-assisted
development" cannot show a kill rate at all, because nothing was ever set up to fail.

## 9. Open items, in order of value

1. **Put v1 in front of five or six real people and write down what confuses them.**
   Still the cheapest available improvement by a wide margin: it converts the weakest part
   of this record (§6 — no observed usage) into the strongest. A facilitator script and a
   per-participant recording sheet are ready in [`USER-TEST.md`](USER-TEST.md) and
   [`user-test-sheet.md`](user-test-sheet.md), including the wording to use, the wording
   that leads and must be avoided, and a check on whether the facilitator contaminated the
   session. **Do this before the Hindi sign-off** — the test will change the English copy,
   and a translation signed off against copy that then moves has to be reviewed twice.
2. **Deploy publicly.** A reader currently has to clone and run it. A URL is worth more
   than another feature.
3. **Hindi sign-off.** The translation is drafted, committed and gated behind a banner; one
   fluent Delhi Hindi speaker needs to read `services/i18n.py` end to end, checking the
   health instructions hardest — anything about an inhaler, a mask or seeking care must
   carry identical force, neither softened nor strengthened. The banner comes out only then.
4. **Read CDSCO's Oct 2025 draft guidance on medical device software.** It could not be
   retrieved during research and is the most decision-relevant unread document; it governs
   whether personalised health advice can legally ship in India.

## 10. If this is published

Two failure modes to avoid.

**Do not lead with the scale numbers.** "217 agents, 4.9M tokens" reads as spectacle and
invites the reply *"so you ran a lot of automation."* The defensible headline is the
decision:

> *I cancelled my own follow-up project after the evidence contradicted it — here is the
> evidence.*

The counts are support for that claim, not the claim itself.

**Do not omit §6.** The limitations are what make the rest credible. A reader will assume
heavy AI assistance whether or not it is stated; stating it first is the difference
between candour and being caught. The same applies to "no real users" — it is the obvious
first question, and answering it before it is asked is worth more than hiding it.

## 10a. The closure run, 20 July 2026

An unattended run worked a closure brief across six phases on the `v1-closure` branch. Each
phase was adversarially reviewed before merge, with the kill rate recorded.

| Phase | What it did | Kill rate |
|---|---|---|
| A | Six persona walkthroughs of the running site | **60%** (10 of 25 survived) |
| B | Grounded the risk score; corrected the data claims | 3 defects raised on the diff, all fixed |
| C | Hindi for the advice, behind an unreviewed banner | 8 defects, 2 of them high |
| D | Feed integrity, bounded transcripts, share preview, measured a11y | 6 defects |
| E | Deployment prepared and the container actually run | — |
| F | This record, and a final review of the whole branch | **38%** (50 examined) |

Two supporting studies ran alongside: a verification of the WAQI data question (**51
conclusions, 31% killed**) and a repo-wide review (**47 findings, 64% killed**).

**The risk score is now half-grounded and says so.** Activity and age were re-derived from
the US EPA Exposure Factors Handbook 2011 Table 6-2, transcribed from the EPA chapter PDF
rather than from a summary of it, and pinned by a test. EPA rates its own confidence in that
table Medium, which the app repeats where the score is explained. The condition weights
stayed uncited because no citable multiplier exists — they are labelled an unvalidated
clinical heuristic in the UI, not only in the README.

**The app was misreporting its own data, and four of the six personas noticed without being
able to name why.** Both faults are recorded in section 11.

**The Hindi is drafted and gated.** The verdict, band advice, AQI meanings, glossary, Guide
and all 34 advisories are translated and committed — never machine-translated at request
time. Every Hindi page carries a banner stating no Hindi speaker has checked it. The persona
sentence, comparison line and driver chips remain English and the module says so.

**Roughly half the station feeds were broken.** Auditing all 21 found 11 returning 404 —
and because the code retried the Delhi city feed on a 404, those 11 localities had been
serving one central Delhi station's reading under 11 different neighbourhood names. The
`noida` slug returned Anand Vihar, Delhi byte-for-byte. Seven feeds served month-old
readings with `status: "ok"`, which the UI stamped LIVE. The fix checks the feed's own
station name against the locality on every fetch, so the table is no longer the only
defence.

### What the Phase A walkthrough was, and was not

Six agents walked the running site as six personas. They are **heuristic reviewers, not
users** — they cannot be genuinely ignorant, they have no stakes, and they do not see a
rendered page. Where a finding depended on visual rendering they were required to say so.
Each finding was then attacked by an independent refuter defaulting to rejection.

**This is not the user test.** Open item 1 in section 9 stands untouched. Nothing here
should be read as having put this in front of a person.

### The correction that created a new defect

The scale correction made a latent bug reachable. Before it, the app always had
an AQI, because it used WAQI's — the number on the wrong scale. Afterwards a feed with no
usable particulate correctly yields no index at all, and `compute_risk` coerced that `None`
to zero. Zero is the cleanest possible air, so the hero offered *"A good day to breathe —
enjoy it outside"* on a page that simultaneously said UNKNOWN and *"treat conditions as
unhealthy until you can confirm"*.

Nobody wrote that bug. It was created by fixing a different one, and the only thing that
caught it was reviewing the whole branch again at the end rather than trusting the
per-phase reviews that had each passed. **Fixing something correctly is not the same as
leaving the system correct.**

### The most useful finding was about a process, not a defect

The 45-agent review in section 3 found the false privacy claim in the README and it was
fixed there. This run found the same claim still live in the site footer on all four pages
and in the Guide, while `locality` went on being written to telemetry.

The original fix corrected the sentence the finding pointed at. It did not ask where else
that belief had been written down. **A finding is about a sentence; the defect is about a
belief, and beliefs are usually recorded more than once.** The repair now has a test that
walks every page and fails on the old wording, which is the only version of this fix that
stays fixed.

## 11. Decisions taken autonomously

An unattended run on 20 July 2026 worked through a closure brief on the `v1-closure`
branch. The brief said to take the owner's decisions where the work needed them and record
each one here. These are those decisions, with the reasoning, for review.

### The brief asked for a WHO line that could not honestly be written

The brief specified this sentence:

> *Today you breathed in about **ten times** more pollution than the World Health
> Organization says is safe in a day.*

It shipped in a different shape, because that sentence asserts three things the app cannot
support. It claims a **daily average**, from a single near-instantaneous station reading.
It claims an **inhaled dose**, which needs the exposure model this project deliberately
cancelled. And it treats 15 µg/m³ as a **daily ceiling**, which is not what it is: WHO
defines the 24-hour AQG level as the 99th percentile of a year's daily means, so three or
four days above it still meet the guideline (WHO AQG 2021, p. 88).

What ships compares the air **right now** against a guideline defined over a whole day, and
says so in those words rather than hiding the mismatch. Both qualifications are in the
Guide. The phrasing is also "six times **as much as**" rather than "six times **more
than**" — the loose form literally means seven times, and overstating by one multiple every
time is exactly the failure this repository exists to record.

### The app was misreporting its own data, in two ways

Neither was in the brief. Both were found while building B1, and both are the same class as
the false privacy claim.

**The pollutant figures were not concentrations.** `iaqi.pm25.v` from the WAQI feed is an
AQI sub-index; the UI rendered it with the literal label `µg/m³`. WAQI's own field
documentation says "Individual AQI for the PM2.5". Across a sample of 237 stations
worldwide the dominant pollutant's sub-index equalled `data.aqi` in **237 of 237** cases,
and 91% of stations reported PM2.5 above PM10 — impossible for mass concentrations, since
PM10 contains PM2.5. Four of the six Phase A personas independently noticed something wrong
here without being able to name the cause.

**The scale was not India's.** The number was credited to CPCB and bucketed with CPCB band
boundaries. WAQI publishes on the US EPA scale worldwide and states specifically for India
that it moved every Indian station onto that scale in January 2016, warning that its figures
will therefore differ from India's own National AQI portal. The scales are not close: 60
µg/m³ of PM2.5 is CPCB 100 "Satisfactory" and US EPA about 154 "Unhealthy".

**Decision: convert rather than relabel.** The smaller fix was to delete the `µg/m³` label
and rename the bands to the US EPA ones. That would have been honest and cost almost
nothing. It was rejected because it makes the product worse for the people it is for — a
Delhi resident checking this against any other Indian source would see a different number
under different words. Instead the feed's sub-index is inverted through the EPA table WAQI
actually uses, and India's index is computed from the resulting concentrations. The
trade-off, disclosed on the page and in the Guide: the result uses **two** pollutants where
CPCB uses up to eight and requires at least three, so on a gas-dominated day the official
figure would be higher. The provenance panel shows both numbers so a reader can watch them
disagree.

### Three places where a gap was left visible instead of filled

- **CPCB publishes its top category open-ended** ("PM2.5 above 250" → 401–500), so there is
  no upper concentration to interpolate towards. Values past the last breakpoint report the
  floor of Severe with a flag rather than an invented slope. A verification agent was sent
  to find whether CPCB publishes an upper bound and was cut off by a session limit before
  answering; the question is open, and the code says so.
- **A feed with no usable particulate yields no AQI at all**, and the page shows `--`. The
  obvious fallback — use WAQI's own number — would put a US figure under Indian band names,
  which is the defect being removed.
- **Children's extra vulnerability stayed unvalidated.** Grounding age in EPA's published
  inhalation rates has an uncomfortable consequence: a 6–11 year old moves *less* air per
  minute than an adult, so a purely rate-based model scores a child as safer. The reasons
  children are more affected are real but do not reduce to a citable number, so those weights
  sit in a term labelled unvalidated rather than beside a citation they do not have. A test
  asserts the inversion so it cannot be quietly reversed.

### Two claims were deleted rather than softened

- **"Staying home" no longer subtracts 6 points.** That discount assumed indoor air is
  cleaner; in Delhi indoor PM2.5 tracks outdoor closely and the claim was never evidenced.
  Staying home still scores lowest, but now only because a resting body inhales least.
- **The "you scored below the baseline" message is gone.** An exhaustive sweep of the input
  space shows the case cannot occur. Copy for an unreachable state can never be shown and
  never be checked. A test now pins the property, so if a future weight makes the case
  reachable the suite fails and the branch gets written.

### The false privacy claim was still on every page

The 45-agent review corrected the README and stopped there. The site footer went on saying
"Persona stays in session — never logged" on all four pages, and the Guide said the persona
"is never written to a database", while `locality` was written to `app-telemetry` on every
request. The fix had moved the sentence rather than retiring the claim. Both surfaces now
say what the code does, and a test walks every page and fails on the old wording.

That this survived a 45-agent review is the most useful thing in this section. The review
found the claim; the fix was applied where the finding pointed, not everywhere the claim
lived. **A finding is about a sentence. The defect is about a belief, and beliefs are
usually written down more than once.**

### Findings recorded but not acted on in this run

- The `noida` feed slug returns the Anand Vihar, Delhi station byte-for-byte. Any UI
  labelling it Noida is mislabelling Delhi data.
- The `delhi/ito` slug returned a reading four weeks stale with `status: "ok"`, which the
  freshness check would have presented as live.
- Every render of `/` makes a live, uncached, synchronous WAQI fetch on the hot path. Still
  open: a per-locality TTL memo is the obvious fix and was not made, because it is a
  behaviour change to the freshness story rather than a correction, and this run was closing
  v1 rather than tuning it.
- `_TRANSCRIPTS` was unbounded and the session cookie unsigned. **Both were fixed** — the
  store is capped at 500 LRU sessions of 20 turns, and the cookie is validated as a
  canonical v4 uuid rather than signed, with the docstring stating what that does not
  protect against.
- The test suite was calling the live WAQI and OpenRouter APIs on every run, so its results
  depended on Delhi's weather and on model output. **Fixed**; the suite went from three
  minutes to half a second, and that runtime had been visible the whole time without anyone
  asking why.

### Phase A was a heuristic evaluation, not user testing

Six agents walked the running site as six personas. They are **heuristic reviewers, not
users**: they cannot be genuinely ignorant, they have no stakes, and they do not see a
rendered page. Where a finding depended on visual rendering they were required to say so.
25 findings were raised and each was attacked by an independent refuter instructed to
default to rejection; **10 survived, a 60% kill rate**. This does not substitute for the
open item at the top of section 9 — putting v1 in front of real people — and nothing here
should be read as having done that.
