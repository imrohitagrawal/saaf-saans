# Gate 5 — persona truth, and the Hindi sign-off

Written 2026-09-01, from owner feedback plus four measurements taken against
`4688916`. Every number below was measured, not estimated; the command that
produced it is named beside it.

This is the design document. The gate ledger entry lives in
[`../../PLAN-gates.md`](../../PLAN-gates.md) under Gate 5 and points here.

---

## 1. Why this gate exists

Four problems, reported by the owner and by a Hindi reviewer. Three of them
were confirmed by measurement; the fourth was confirmed by reading the rendered
page. One further defect was found while confirming the first and is folded in.

### 1.1 The verdict headline barely varies — measured

`presenters._VERDICTS` is keyed on the **risk band**, a five-value bucket. The
persona picks a bucket and is then discarded, so two unlike people who bucket
the same get byte-identical text.

Swept all 60 persona combinations at four AQI levels:

| AQI | distinct verdicts across 60 personas |
| --- | --- |
| 40  | **1** |
| 120 | 2 (31 / 29) |
| 180 | 2 (**identical 31 / 29**) |
| 300 | 2 (44 / 16) |

240 states produce **four distinct sentences**. Rows 120 and 180 are the sharp
finding: a 60-point AQI swing moves the headline for **zero** personas, so the
line is insensitive to the air as well as to the reader.

### 1.2 The headline names the wrong organ — measured

At AQI 180, 29 of 60 personas receive *"Today is hard on lungs like yours"*.
**Ten of them selected Heart condition or Pregnancy** — nine pregnancy
combinations and Senior/Heart/Outdoor exercise. The app tells a pregnant
reader her lungs are the problem. `normalize.py:228` already knows better: it describes
pregnancy as raising sensitivity to fine particles linked to lower birth weight
and preterm birth. The headline overrides the correct explanation with the
wrong organ.

### 1.3 Impossible personas are selectable — found while confirming 1.2

`today.html:207-221` renders three independent `<select>` elements over flat
lists. There is no cross-field validation in `main.py` or `normalize.py`, and
zero JavaScript by design, so nothing constrains the combination.
**Child + Pregnancy is selectable**, and the app renders a full health advisory
for a pregnant child. Senior + Pregnancy likewise.

Not caught by any gate or review round to date.

### 1.4 Adolescence is not represented at all — measured

The three age options map onto specific EPA brackets (`main.py:1493-1495`):

| option | EPA Table 6-2 bracket |
| --- | --- |
| Child  | 6 to <11 years |
| Adult  | 21 to <31 years |
| Senior | 61 to <71 years |

**Ages 11 to 21 map to nothing.** A parent picking "Child" for a 16-year-old
gets a 6-to-10-year-old's breathing rate; a 17-year-old picking "Adult" gets a
21-to-30-year-old's.

`risk.py:71-72` records that only three of EPA's fourteen brackets were
carried. The adolescent rows therefore exist in a source the app already cites,
which makes this a gap to close rather than a claim to invent.

Adolescents also carry the highest exertion rates in the table, and the dose
term is multiplicative in exertion — so the teenager exercising outdoors is
close to the worst inhaled dose the app can compute, and today it cannot
compute it.

### 1.5 A new visitor is not told what the app is for — read from the render

The English homepage's orientation sentence is the fourteenth line of text,
after twelve lines of masthead and navigation:

> "The AQI is one number for everyone. This page scores it for your body and
> your plans."

That answers *"why us instead of AQI"*. It does not answer *"what is this, and
what will it tell me"*. It presumes the reader knows what AQI is, already
minds that it is one-size-fits-all, and already wants a personalised
alternative. A first-time visitor holds none of those.

Three faults compound:

- It is a **differentiator, not an orientation** — competitive positioning
  aimed at someone who has used an air-quality app before.
- **The decision the app supports is never stated.** Its actual job is
  "should I go out, and how hard should I push?" That sentence appears nowhere.
- **There is no "what is this" surface anywhere.** The Guide opens "Every
  number and term on this site, in plain language" and is a glossary. It
  defines AQI, PM2.5 and CPCB; it never says who the app is for.

The example persona compounds it further: the reader meets
`EXAMPLE — FOR AN ADULT WITH ASTHMA, PLANNING OUTDOOR EXERCISE` before knowing
that a persona concept exists.

---

## 2. Decisions taken

Each was put to the owner and chosen by them.

| # | Decision | Chosen |
| --- | --- | --- |
| D1 | How the verdict should vary | Key it to the **driver**, not the band alone |
| D2 | Impossible age + condition pairs | **Restrict server-side** (no JavaScript) |
| D3 | Hindi scope | **Full corpus pass**, reviewer sign-off, banner removed |
| D4 | Adolescence | **Split**: Teen (11-15) and Youth (16-20), five age options |
| D5 | Teen + pregnancy | Permitted on **Youth and Adult** only |
| D6 | Order | Hindi, then ages, then verdict, then orientation |
| D7 | Plan location | Design doc here; Gate 5 summary in `PLAN-gates.md` |
| D8 | Hindi review instrument | A published **Artifact** page, browser-only for the reviewer |

### The persona space after D4 and D5 — measured

```
5 ages x 5 conditions x 4 activities = 100 combinations
blocked (pregnancy on Child/Teen/Senior) =  12
reachable                                =  88
```

---

## 3. Package 5a — the Hindi corpus pass

**Corpus size: 515 Hindi strings** (counted by walking `i18n.HI`; the 640
figure quoted elsewhere in the repo is the health-claims corpus across both
languages, and is a different set).

The scarce resource is the human reviewer, so the package is shaped around
their time rather than around the code.

**Deliverable 1 — the review instrument (mine).** A published Artifact page
carrying every Hindi string with its key, its English source, the surface it
renders on, and a verdict control. Ordered by reader impact: hero, verdicts,
persona, band advice first; System and Guide last. A reviewer who runs out of
time has still covered what readers actually meet. Private on publish; the
owner chooses who receives the link.

**Deliverable 2 — verdicts (the reviewer's).**

**Deliverable 3 — application (mine).** One commit per surface, never batched,
so a disputed string is revertible without unpicking the rest.

**Deliverable 4 — the pinning test (mine).** Every shipped Hindi string must be
either in the signed-off set or explicitly marked unreviewed. Editing a
signed-off string turns it red.

This is what makes the banner removal honest. Without it, "reviewed" decays
silently the first time anyone tweaks a word, and the repo has no way to
notice — which is the same defect class as a stale claim in prose.

**Three items already known to be in scope:**

1. **`age_adult`: एक बड़ा व्यक्ति → एक वयस्क.** बड़ा carries both "grown-up"
   and "elder", and the picker also offers बुज़ुर्ग, so the reader must guess
   which distinction is meant. वयस्क is the standard unambiguous term.
   बालिग़ was considered and rejected: it carries a legal age-of-majority
   connotation that is wrong in a health context.

2. **The persona sentence is a finite clause where a noun phrase belongs.**
   The kicker is `"इनके लिए: {persona}"` and the template is
   `"{who}, {condition}, {place} में {activity}"`, rendering:

   > इनके लिए: एक बच्चा, जो सेहतमंद है, नोएडा में बाहर कसरत **करने वाले हैं**

   Three faults with one root cause. (a) After "इनके लिए:" Hindi requires a
   noun phrase; "करने वाले हैं" is a finite predicate, so the colon introduces
   a complete sentence. The English works because "an adult with asthma,
   planning outdoor exercise" is a *label*. The Hindi turned the label into an
   assertion. (b) "एक बच्चा" is singular against plural "वाले हैं" — passable
   as honorific for बुज़ुर्ग, plainly wrong for a child. (c) वाला/वाली/वाले
   inflects for gender and there is no gender field, so every reader is
   addressed as masculine.

   **Proposed fix — verbal nouns, which inflect for neither gender nor number:**

   | key | current | proposed |
   | --- | --- | --- |
   | `activity_exercise` | बाहर कसरत करने वाले हैं | बाहर कसरत |
   | `activity_commute` | बाहर आने-जाने वाले हैं | बाहर आना-जाना |
   | `activity_school_run` | बच्चे को स्कूल छोड़ने-लाने वाले हैं | बच्चे को स्कूल छोड़ना-लाना |
   | `activity_stay_home` | घर पर ही रहने वाले हैं | घर पर रहना |
   | `with_activity_and_place` | `{who}, {condition}, {place} में {activity}` | `{who}, {condition} — {place} में {activity}` |

   Renders: **इनके लिए: एक बच्चा, जो सेहतमंद है — नोएडा में बाहर कसरत**

   The structural diagnosis is grammar and is checkable. The exact wording is a
   candidate for the reviewer to arbitrate, not a finished translation.

3. **Gender-marked nouns.** एक बच्चा is masculine (एक बच्ची feminine), and
   किशोर for Teen carries the same problem (किशोरी). Decide once, corpus-wide.

**Exit criteria**

- [ ] Reviewer sign-off recorded in the repo, naming the reviewer and the date.
- [ ] Every one of the 515 strings carries a verdict, or is explicitly listed
      as unreviewed with a reason.
- [ ] The unverified-Hindi banner is removed.
- [ ] The pinning test exists and **bites**: changing one signed-off string
      turns it red, proven by doing it and reverting.
- [ ] Full suite green on master; count recorded.

---

## 4. Package 5b — Teen and Youth

**Depends on:** nothing. Runs in parallel with the reviewer's work on 5a.

- Read EPA Exposure Factors Handbook 2011 **Table 6-2** rows for
  **11 to <16 years** and **16 to <21 years**. Cite them exactly as the
  existing three rows are cited. **These values are read off the source, never
  recalled** — an invented rate is the one thing this repository forbids
  outright.
- Extend `risk.INHALATION_RATES`, `main._epa_rows` bands, the age lists in
  `main.py` and `normalize.py`, and both language corpora.
- **Validation (D2, D5):** pregnancy is permitted on Youth and Adult only.
  Child, Teen and Senior fall back to Fit. Server-side, because the
  zero-JavaScript rule stands.
- **No susceptibility bump for Teen or Youth.** `risk.py:143-144` marks the
  susceptibility term as "our own judgement, not grounded". The whole value of
  this package is that it lands in the *grounded* half of the score; an
  invented weight on top would spend exactly that.

**Exit criteria**

- [ ] All 88 reachable combinations render without error.
- [ ] Each of the 12 blocked combinations is provably unreachable, one test
      each, each proven to fail if the guard is removed.
- [ ] The Guide's EPA table shows five rows, each with its own cited bracket.
- [ ] The two new rates are traceable to Table 6-2 in a comment, in the same
      form as the existing three.
- [ ] Full suite green on master; count recorded.

---

## 5. Package 5c — the verdict, keyed to its driver

**Depends on 5b** — the persona space it sweeps has to be final first.

Pick the wording from the dominant driver rather than the band alone:

```
Asthma / COPD  -> lungs
Heart          -> heart
Pregnancy      -> its own line, matching normalize.py:228
Age alone      -> age
```

Severity stays banded; only the clause naming *why this reader* is driver-keyed.

**Open sub-decision, to be brought to the owner rather than guessed:** which
driver wins when a reader is both a senior *and* has COPD. That rule determines
the wording and is a judgement call, not a lookup.

**Exit criteria**

- [ ] No persona receives an organ claim its own condition contradicts. Swept
      over all 88, both languages.
- [ ] The distinct-verdict count is measured and recorded, the same way the
      current 4 was measured.
- [ ] Every new sentence passes the evidence checklist, per sentence, per
      language, recorded in the pull request.
- [ ] The driver-precedence rule is written down where the code can be read
      against it.
- [ ] Full suite green on master; count recorded.

---

## 6. Package 5d — first-screen orientation

**Owner-directed. Not scheduled here.**

This is the header and banner redesign that `PLAN-gates.md` already defers to
Gate 4 pending an owner decision, and §1.5 is the evidence for why it is worth
doing. Options to be brought when the earlier packages land.

Direction, for the record, not yet approved: replace the differentiator line
with a plain statement of job and audience, and move the AQI contrast beneath
it, where it becomes the reason to trust the answer rather than the opening
claim.

---

## 7. Risks

| # | Risk | Package | Mitigation |
| --- | --- | --- | --- |
| R1 | An invented inhalation rate ships for Teen or Youth | 5b | Values read off Table 6-2 and cited in the same commit; a reviewer checks the citation, not the number's plausibility |
| R2 | The banner comes down over a corpus that was not really reviewed | 5a | The pinning test, proven to bite. Sign-off names a person and a date |
| R3 | The driver rewrite reintroduces a health claim | 5c | The existing `test_health_claims.py` sweep plus the per-sentence checklist |
| R4 | 5c is built against a persona space 5b then changes | 5c | Ordering is a hard dependency, stated here and in the gate ledger |
| R5 | Blocking pregnancy combinations silently changes a stored persona | 5b | The fallback is tested explicitly, and a blocked pair falls to Fit rather than erroring |
| R6 | The reviewer's Hindi verdicts are applied wrongly by an agent | 5a | One commit per surface; the reviewer sees the rendered page, not the dictionary |

---

## 8. What this gate does not do

- It does not re-open the exposure ledger, push notifications, the forecast
  "best hours" feature, mask health-benefit claims, or WhatsApp. All cancelled
  on recorded evidence.
- It does not touch the zero-JavaScript rule. D2's validation is server-side
  precisely so it need not.
- It does not address the ragged foot, Appendix B's advisory backlog, or the
  five live findings recorded separately in the 2026-09-01 analysis
  (`.env.example`'s missing `CPCB_API_KEY`, the Guide's unconditional source
  claim, the monotonic/wall-clock split, the unthrottled `/city`, and the
  guard's cross-script bypasses). Those are their own packages.
