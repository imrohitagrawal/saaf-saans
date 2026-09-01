# Gate 5 — persona truth, and the Hindi sign-off

Written 2026-09-01. Revised the same day after a four-lens review found three of
its numbers wrong, its central linguistic argument unsound, and its Hindi fix
table pointed at a template the app does not render on the surface complained
about. What that review changed is recorded in §10.

**Every number in this document is produced by `scripts/measure_gate5.py`.** Run
it and compare; do not trust the transcription:

```
env OPENROUTER_API_KEY= WAQI_TOKEN= ELASTIC_URL= ELASTIC_API_KEY= \
    ELASTIC_CLOUD_ID= .venv/bin/python -m scripts.measure_gate5
```

The gate ledger entry lives in [`../../PLAN-gates.md`](../../PLAN-gates.md)
under Gate 5 and points here.

---

## 1. Why this gate exists

Four problems, reported by the owner and by a Hindi reviewer. One further defect
was found while confirming the second.

### 1.1 The verdict headline barely varies

`presenters._VERDICTS` is keyed on the **risk band**, a five-value bucket. The
persona picks a bucket and is then discarded, so two unlike people who bucket
the same get byte-identical text.

| AQI | distinct verdicts across 60 personas | split |
| --- | --- | --- |
| 40  | **1** | 60 |
| 120 | 2 | 38 / 22 |
| 180 | 2 | 38 / 22 |
| 300 | 2 | 51 / 9 |

240 states produce **four distinct sentences**. And the headline of every one of
the 60 personas is byte-identical at AQI 120 and at AQI 180 — a 60-point swing
moves nobody. The line is insensitive to the air as well as to the reader.

> **Scope.** Those are four sample AQI values, not the whole range. All five
> verdicts are reachable somewhere in 0–500. The "four distinct sentences" claim
> is about these four samples and must not be restated without them.

### 1.2 The headline names the wrong organ

At AQI 180, **38 of 60** personas receive *"Today is hard on lungs like yours"*.
**19 of those chose a non-lung condition** — 10 Heart condition, 9 Pregnancy.
The app tells a pregnant reader her lungs are the problem. `normalize.py:228`
already knows better: it describes pregnancy as raising sensitivity to fine
particles linked to lower birth weight and preterm birth. The headline overrides
the correct explanation with the wrong organ.

### 1.3 Impossible personas are selectable

`today.html:207-221` renders three independent `<select>` elements over flat
lists. There is no cross-field validation in `main.py` or `normalize.py`, and
zero JavaScript by design, so nothing constrains the combination.
**Child + Pregnancy is selectable**, and the app renders a full health advisory
for a pregnant child — verified live: `GET /?age=Child&condition=Pregnancy&
activity=Outdoor+exercise` returns 200 and renders `FOR A CHILD WHO IS PREGNANT`
with a risk score. Senior + Pregnancy likewise.

Not caught by any gate or review round to date.

### 1.4 Adolescence is not represented

The three age options map onto specific EPA brackets (`main.py:1493-1495`):

| option | EPA Table 6-2 bracket |
| --- | --- |
| Child  | 6 to <11 years |
| Adult  | 21 to <31 years |
| Senior | 61 to <71 years |

**Ages 11 to 20 map to no option.** A parent picking "Child" for a 16-year-old
gets a 6-to-10-year-old's breathing rate; a 17-year-old picking "Adult" gets a
21-to-30-year-old's.

`risk.py:71-72` records that only three of EPA's fourteen brackets were carried,
so the adolescent rows exist in a source the app already cites. That makes this
a gap to close rather than a claim to invent.

> **Two honest qualifications.**
> **(a)** Adolescence is not the only gap. Ages 0–6, 31–61 and 71+ are also
> served by a bracket that is not theirs; a 45-year-old is scored on the 21–30
> rate exactly as a 16-year-old is. Adolescence is being closed first because it
> was asked for and because the exertion term makes it the most consequential —
> not because it is the only one.
> **(b) REFUTED 2026-09-01, by reading the table.** The first draft asserted
> that adolescents carry the highest exertion rates in Table 6-2. A review
> demoted it to a hypothesis; reading the source then killed it. The highest
> high-intensity mean is **51 to <61 (5.3e-2)**; Teen and Youth are both 4.9e-2,
> mid-table. The case for 5b therefore rests on (a) alone, as that draft said it
> would have to: the bracket is simply wrong for that body. Measured cost of the
> current mis-bracketing for a 13-year-old — **14% understated** on a school run
> (scored 2.2e-2 as a child, correct 2.5e-2), 13% at rest.

### 1.5 A new visitor is not told what the app is for

The English homepage's orientation sentence is the **thirteenth** line of text,
after twelve lines of masthead and navigation (the first being the
visually-hidden skip link, so eleven are visible):

> "The AQI is one number for everyone. This page scores it for your body and
> your plans."

That answers *"why us instead of AQI"*. It does not answer *"what is this, and
what will it tell me"*. It presumes the reader knows what AQI is, already minds
that it is one-size-fits-all, and already wants a personalised alternative.

- **The decision the app supports is never stated.** Its job is "should I go
  out, and how hard should I push?" That sentence appears nowhere.
- **No surface answers "what is this".** The Guide opens "Every number and term
  on this site, in plain language". It carries a glossary, an FAQ and a
  methodology section — and no statement of who the app is for.
- The reader meets `EXAMPLE — FOR AN ADULT WITH ASTHMA…` at line 18, before the
  explanation at lines 28–30.

> **A tracked document disagrees with this section.** `DESIGN.md:229-231`
> describes the same sentence as "the `page-sub` line **that says what the page
> is**". One of the two is wrong, and they cannot both ship. Resolving that is
> the first task of 5d, not a side effect of it — see §6.

---

## 2. Decisions taken

| # | Decision | Chosen |
| --- | --- | --- |
| D1 | How the verdict should vary | Key it to the **driver**, not the band alone |
| D2 | Impossible age + condition pairs | **Restrict server-side** (no JavaScript) |
| D3 | Hindi scope | **Full corpus pass**, reviewer sign-off, banner removed |
| D4 | Adolescence | **Split**: Teen (11-15) and Youth (16-20), five age options |
| D5 | Teen + pregnancy | Permitted on **Youth and Adult** only |
| D6 | Order | **5b, then 5c, then 5a.** Revised — see below |
| D7 | Plan location | Design doc here; Gate 5 summary in `PLAN-gates.md` |
| D8 | Hindi review instrument | A published **Artifact** page, browser-only |
| D9 | Gendered Hindi person-nouns | **Generic masculine**, recorded as a decision |

**D6 was reversed by review, with the owner's agreement.** The first draft ran
Hindi first, on the reasoning that the reviewer is the scarce resource. That is
the failure `docs/CASE-STUDY.md:253-260` already records: *"a translation signed
off against copy that then moves has to be reviewed twice."* 5b adds Hindi age
strings and must edit `guide/researched_intro`, which hardcodes **तीनों** ("the
three age groups"); 5c rewrites the five verdict strings the reviewer would
already have approved — and would likely have approved as *good Hindi*, because
the wrong-organ sentence is fluent. English settles first. The reviewer is
engaged once, over a corpus that has stopped moving.

### The persona space after 5b

```
5 ages x 5 conditions x 4 activities = 100 combinations
pregnancy blocked on Child/Teen/Senior =  12
reachable                              =  88
```

---

## 3. Package 5b — Teen and Youth *(first)*

- The rates are **already transcribed and pinned**. `tests/epa_table_6_2.json`
  carries all 14 brackets of EPA EFH 2011 Table 6-2 (Mean column, m³/minute, pp.
  6-4/6-5) with its provenance, and `tests/test_epa_table.py` asserts
  `risk.INHALATION_RATES` equals it cell by cell. The twelve values covering the
  three brackets already shipped matched the source exactly on transcription,
  which is the evidence that both are right. Teen (11 to <16) is
  5.4e-3/1.3e-2/2.5e-2/4.9e-2; Youth (16 to <21) is 5.3e-3/1.2e-2/2.6e-2/4.9e-2.
  **Still never write a rate from memory or round one to taste** — add the age to
  `INHALATION_RATES` and to the fixture's bracket map, and the test will hold you
  to the published figures. Adding an age without recording its bracket is red by
  design.
- Extend `risk.INHALATION_RATES`, `main._epa_rows` bands, the age lists in
  `main.py` and `normalize.py`, and both language corpora.
- **Validation (D2, D5):** pregnancy permitted on Youth and Adult only. Child,
  Teen and Senior fall back to Fit — **and the page says so**. A silent
  downgrade hands a Senior who picked Pregnancy the sentence "No condition that
  makes polluted air riskier for you than for an average adult", which answers a
  question she did not ask. Constraint (i) is "Honesty over polish".
- **No susceptibility bump for Teen or Youth.** `risk.py:143` marks the
  susceptibility term `# --- Susceptibility (not grounded) ---`; the phrase
  "our own judgement, not a validated medical model" is `HEURISTIC_NOTICE` at
  `risk.py:66-67`. The value of this package is that it lands in the *grounded*
  half of the score; an invented weight on top would spend exactly that.
- **The rescaling consequence — real hazard, closed by measurement.**
  `_MAX_RATIO` (`risk.py:108`) is derived from `INHALATION_RATES` itself, and
  `_DOSE_SCALE` from it, so a new row above the current maximum would rescale
  `dose_points` for **every existing persona** (at +10%, an adult on outdoor
  exercise goes 14 → 13). **It does not fire here:** Teen and Youth
  high-intensity are both 4.9e-2, below adult/high's 5.0e-2, so `_MAX_RATIO` is
  unchanged and no existing score moves. Confirm that rather than assuming it —
  the exit criterion below still requires before/after figures, because the
  guard is what makes the next row safe too.
- **Hindi terms (D9, and see §5).** `किशोर` for Teen, `युवा` for Youth. `युवा`
  is form-invariant. `किशोर` is not, and is generic-masculine per D9.

**Exit criteria**

- [ ] All 88 reachable combinations render without error.
- [ ] Each of the 12 blocked combinations **cannot produce a rendered persona
      containing the pregnancy advisory, whatever the query string** — one test
      each, each proven to fail with the guard removed. (Not "unreachable": the
      `<select>` and the URL both still accept the pair.)
- [ ] A blocked pair renders a visible line naming what was changed and why, in
      both languages, tested.
- [ ] The Guide's EPA table shows five rows, each with its own cited bracket.
- [x] **Done 2026-09-01, ahead of the package.** The two new rates are
      reproduced from a committed transcription of Table 6-2 (source, page and
      URL cited) and `tests/test_epa_table.py` asserts `risk.INHALATION_RATES`
      equals it cell by cell. Proven to bite by three named mutations: changing
      one digit of one rate (1 red), emptying the fixture (17 red — the
      non-vacuity partner), and adding an age with no bracket recorded (1 red).
      A citation in a comment was never sufficient: it is satisfied by writing
      the comment beside a hallucinated number.
- [ ] `dose_points` for every pre-existing persona is recorded before and after.
      Any change is stated in the pull request with its cause, or `_DOSE_SCALE`
      is pinned so there is none.
- [ ] Full suite green on master; count recorded.

---

## 4. Package 5c — the verdict, keyed to its driver *(second)*

Depends on 5b: the persona space it sweeps must be final.

Pick the wording from the dominant driver rather than the band alone:

```
Asthma / COPD  -> lungs
Heart          -> heart
Pregnancy      -> its own line, matching normalize.py:228
Age alone      -> age
```

**Open sub-decision for the owner:** which driver wins when a reader is both a
senior *and* has COPD. A judgement call, not a lookup.

**What this package does NOT fix, stated so the gate cannot appear to close it.**
§1.1 found two defects: no variation by reader, and no variation by air. This
package addresses the first only. Severity stays banded, so after 5c ships, AQI
120 and AQI 180 will *still* produce identical headlines for all personas. If
that is to be fixed it needs a severity clause that reads the AQI rather than
the band, and that is not scheduled here.

**Constraints the existing verdict set carries** (`presenters.py:68-83`), which
a rewrite must preserve: none of the five may say "indoors" — placement is the
advice line's job; the ramp must not reverse; and every verdict must carry an
instruction, because a describe-only verdict is the defect
`tests/test_i18n.py::test_every_hindi_verdict_tells_the_reader_what_to_do` was
written for.

**Exit criteria**

- [ ] No persona receives an organ claim its own condition contradicts. Swept
      over all 88, both languages.
- [ ] Distinct verdicts across the 88 × 4 sweep is **at least 12**, measured
      before and after on the same post-5b space, both figures recorded. (A bare
      "count it and record it" is satisfied by recording "4, unchanged".)
- [ ] The constraints at `presenters.py:68-83` still hold, and
      `test_every_hindi_verdict_tells_the_reader_what_to_do` is green.
- [ ] Every new sentence passes the evidence checklist, per sentence, per
      language, recorded in the pull request.
- [ ] The driver-precedence rule is written where the code can be read against it.
- [ ] Full suite green on master; count recorded.

---

## 5. Package 5a — the Hindi corpus pass *(last)*

**Corpus size: 515 leaf strings in `i18n.HI`.** Distinct from the health-claims
corpus, which spans both languages and currently measures 649 — note that
`PLAN-gates.md:861` and `tests/test_health_claims.py:124` both still say 640,
which is itself stale and should be re-pinned when convenient.

5b and 5c will have added strings by the time this runs. The count is pinned at
`450188c`; the exit criteria are written against "the corpus at sign-off", not
against 515.

**Deliverable 1 — the review instrument.** A published Artifact page carrying
every Hindi string with its key, its English source, the surface it renders on,
and a verdict control. Ordered by reader impact. Private on publish.

**Deliverable 2 — verdicts, from the reviewer.**

**Deliverable 3 — application.** One commit per surface.

**Deliverable 4 — the pinning test**, with a non-vacuity partner. See below.

### 5a.1 The words

**`age_adult`: एक बड़ा व्यक्ति → एक वयस्क.** बड़ा reads as both "grown-up" and
"elder", and the picker also offers बुज़ुर्ग, so the contrast is unclear.
वयस्क is the standard unambiguous term. Two caveats to put to the reviewer:
वयस्क is not wholly free of a legal-threshold sense either (`केवल वयस्कों के लिए`),
and it is tatsama-Sanskritic against a corpus that is markedly Hindustani
(बुज़ुर्ग, ख़राब, इलाक़ा, तबीयत). No colloquial alternative is unambiguous —
जवान excludes the middle-aged, प्रौढ़ is too narrow, बड़े reproduces the problem.
**A second, independent reason to make the change:** `एक बड़ा व्यक्ति` is
masculine-marked (बड़ा agrees with व्यक्ति); `एक वयस्क` is form-invariant.

**The root cause is that the picker never shows the bracket.** No Hindi noun can
carry "21 to <31". With five options and two overlapping words (see below), put
the range in the option label itself in both languages — `किशोर (11–15 साल)`,
`युवा (16–20 साल)`. That dissolves the बड़ा/बुज़ुर्ग problem outright.

**किशोर and युवा.** `किशोर` is the right word for an adolescent and the wrong
word for 11–15 *specifically*: India's Rashtriya Kishor Swasthya Karyakram
defines किशोर as **10–19**, so it spans both proposed brackets. `युवा` is
standard for the older bracket and is form-invariant. Neither word can carry the
boundary alone, which is why the numeric range in the label is not a nicety.

### 5a.2 The sentence

The kicker is `"इनके लिए: {persona}"`. The live render today is:

> इनके लिए: एक बच्चा, जो सेहतमंद है, बाहर कसरत **करने वाले हैं**

**Why this is wrong — the argument that survives a native reviewer.** The first
draft of this document claimed Hindi requires a noun phrase after a colon. **That
is false** — `एक बात याद रखिए: आज हवा ख़राब है।` is ordinary Hindi. The real
argument is that this one string is reused in frames that put a **postposition
after it**. `ui.share_for` is `"यह सलाह {who} के लिए है।"`, and a finite clause
cannot precede `के लिए`. It must be a noun phrase because of where it is *used*.

Two further faults, both real:

- **No overt subject agrees with the verb.** With `एक बच्चा` (3sg) as subject,
  agreement demands `करने वाला है`. `वाले हैं` is licensed only by an elided
  honorific `आप` — which the section heading `आपका ब्यौरा` ("your details")
  actively invites. A label needing subject-recovery is a bad label either way.
- **Gender is guessed.** `वाला/वाली/वाले` inflects; there is no gender field, so
  every woman is addressed in masculine.

**The fix — all four shapes, not one.** The first draft listed only
`with_activity_and_place`. The kicker calls
`persona_sentence(with_place=False)`, so it uses **`with_activity`** — the fix as
first written would have left the reported sentence untouched.

| key | current | proposed |
| --- | --- | --- |
| `activity_exercise` | बाहर कसरत करने वाले हैं | बाहर कसरत |
| `activity_commute` | बाहर आने-जाने वाले हैं | बाहर आना-जाना |
| `activity_school_run` | बच्चे को स्कूल छोड़ने-लाने वाले हैं | बच्चे को स्कूल छोड़ना-लाना |
| `activity_stay_home` | घर पर ही रहने वाले हैं | घर पर रहना |
| `with_activity` | `{who}, {condition}, {activity}` | `{who}, {condition} — {activity}` |
| `with_activity_and_place` | `{who}, {condition}, {place} में {activity}` | `{who}, {condition} — {place} में {activity}` |
| `with_place` | `{who}, {condition}, {place} में` | `{who}, {condition} — {place} में` |
| `plain` | `{who}, {condition}` | unchanged |
| `ui.share_for` | `यह सलाह {who} के लिए है।` | `यह सलाह इनके लिए है: {who}` |

**The strongest argument for the verbal nouns is one the first draft missed:**
the picker's own labels already use exactly these forms — `ui.act_outdoor_exercise`
is `बाहर कसरत`, `ui.act_stay_home` is `घर पर रहना`. This makes `persona`
consistent with `ui`; the corpus already made this choice once.

**Four surface defects that travel with this change:**

1. **`share_for` is not fixed by the table alone.** After the activity change it
   reads *"यह सलाह … बाहर कसरत के लिए है।"* — "this advice is for outdoor
   exercise". `के लिए` attaches to the nearest noun. It needs the rewrite above,
   and its head noun should be oblique. This is the forwarded share card.
2. **Two em-dashes in one line on the first-visit page.**
   `ui.example_for_before` already ends in one. Pick one owner of that dash.
3. **`today.html:167` appends a Latin full stop** after the persona. Once the
   phrase is a noun phrase the correct terminator is none — not a danda either.
   Almost certainly one of Appendix B's two Latin-full-stop items.
4. **Dropping the verb loses plan-ness.** English keeps "planning". The proposed
   strings are byte-identical to the picker options, which imports the defect
   `presenters.py` names for English — *"reads as a database row, not as a
   description of a person"*. Cheapest repair that adds no gender or number:
   prefix `आज` — `एक वयस्क, जिसे अस्थमा है — आज नोएडा में बाहर कसरत`. **Reviewer call.**

**A caution for whoever edits this next:** the four strings are not one
grammatical category. `बाहर कसरत` is a plain noun phrase; the other three are
`-ना` infinitives which **must** go oblique before any postposition
(`आने-जाने का`). No template may place a postposition after `{activity}`. Write
this into the corpus comment.

### 5a.3 Removing the banner

The first draft's exit criteria were five independent bullets, and they were
vacuous: mark all strings "unreviewed", and criterion 2 passes; criterion 3
("banner is removed") was unconditional; the pinning test then pinned an empty
set and bit on nothing. The repo already fixed this class once —
`tests/test_health_claims.py:276-298` pairs its sweep with `assert len(rows) > 300`
and four `assert any(...)` partners.

**Six surfaces assert the banner stays** and must move in the same commit:
`docs/INDEX.md:74` (**"Not removable"** — flat, no mechanism, and it is the first
file the reading order sends a new session to), `PRODUCT.md:76` and `:90-91`,
`README.md:23` and `:188-191`, `docs/CASE-STUDY.md:261-264`,
`saafsaans/services/i18n.py:26-27`, and standing constraint (h) at
`PLAN-gates.md:218-219` — which §3 of that file pastes verbatim into every
subagent prompt, so leaving it stale actively misinforms later work.

**Removing the banner turns five tests red**, measured by doing it:

```
tests/test_a11y.py::test_no_class_in_the_stylesheet_is_unreachable
tests/test_devanagari_floor.py::test_the_lang_en_escape_hatch_actually_restores_the_latin_face
tests/test_hindi_completeness.py::test_the_english_review_banner_needs_no_allowlist_seeding
tests/test_web.py::test_hindi_switches_the_content
tests/test_web.py::test_the_review_banner_is_on_every_hindi_page_and_no_english_one
```

Four are bookkeeping. The second is **Gate 2a finding 3** — the `lang="en"`
escape hatch — and `.notice-en` is its only subject. Deleting the banner leaves
that guard with nothing to assert, and the path of least resistance during test
repair is to delete a guard shipped nine days earlier. It must be re-pointed at
another `lang="en"` island, not removed.

`base.html:135-138` also nests the `.persona-path` escape hatch *inside* the
banner block, so deleting the block deletes the Hindi first-visit route into the
persona editor. And `base.html:121` records the banner as the first child of
`<main>`, so the skip link currently lands on it.

**Exit criteria**

- [ ] Every string in the corpus **at sign-off** carries a verdict, or is on an
      explicit unreviewed list that names each one and its reason.
- [ ] The unreviewed list contains **no string rendered on `/` or `/city`** in
      the persona-applied, held-reading or no-reading states.
- [ ] The pinning test exists, loads the signed-off set from a **committed
      record naming the reviewer and the date**, and carries a non-vacuity
      partner: the set is non-empty, covers at least the Today surface, and
      contains the known keys `verdict.*`, `band_advice.*` and `persona.*`.
- [ ] The pinning test **fails closed**: a Hindi string in neither the
      signed-off set nor the unreviewed list turns the suite red.
- [ ] Proven to bite, by editing one signed-off string and reverting.
- [ ] The banner is removed **only after** the two criteria above hold, and all
      six asserting surfaces plus constraint (h) are updated in the same commit.
- [ ] The `lang="en"` escape hatch still has a tested subject on a Hindi page.
- [ ] `.persona-path` and the skip-link target are re-anchored.
- [ ] D9 (generic masculine) is written to `docs/decisions/` with its reasoning.
- [ ] Full suite green on master; count recorded.

---

## 6. Package 5d — first-screen orientation

**Owner-directed. Not scheduled.**

This is the header and banner redesign that `PLAN-gates.md`'s Gate 4 already
defers pending an owner decision — the same item, not a second one. Gate 4's
"fold problem" bullet and `DESIGN.md:236` both need a cross-reference so the
ledger does not read as two independent entries.

**First task, before any redesign:** resolve §1.5's contradiction with
`DESIGN.md:229-231`. One of them is wrong today.

---

## 7. Risks

Prefixed `G5-` because `PLAN-gates.md` §5 already owns bare `R1`–`R10`.

| # | Risk | Package | Mitigation |
| --- | --- | --- | --- |
| G5-R1 | An invented inhalation rate ships | 5b | A committed transcription of the two Table 6-2 rows, and a test asserting the table equals it cell by cell. A citation in a comment is **not** a mitigation — it is satisfied by writing one beside a fabricated number |
| G5-R2 | The banner comes down over a corpus not really reviewed | 5a | The coverage floor and the non-vacuity partner in §5a.3 |
| G5-R3 | The banner comes down and later work adds unreviewed Hindi | all | D6's reversal: 5a runs last. The pinning test fails closed, so a later string cannot ship silently |
| G5-R4 | Adding teen rates silently rescales every existing score | 5b | **Closed by measurement 2026-09-01** — Teen and Youth high-intensity are 4.9e-2, below adult/high's 5.0e-2, so `_MAX_RATIO` does not move. Before/after `dose_points` still recorded, because the guard is what makes the next row safe |
| G5-R5 | A blocked pregnancy pair silently answers a different question | 5b | The page states what was changed; tested in both languages |
| G5-R6 | The driver rewrite reintroduces a health claim | 5c | `test_health_claims.py` plus the per-sentence checklist |
| G5-R7 | The reviewer's verdicts are applied wrongly | 5a | One commit per surface, **and** a second cheap pass over the rendered app after application — "one commit per surface" makes a bad application revertible, not detectable |
| G5-R8 | A usage limit kills a run mid-flight (global R7) | 5a | A human sits between build and banner removal with unbounded latency. A half-finished 5a must leave the banner **up**; that is the safe default and is stated so nobody "tidies" it |

---

## 8. What this gate does not do

- It does not re-open the exposure ledger, push notifications, the forecast
  "best hours" feature, mask health-benefit claims, or WhatsApp.
- It does not touch the zero-JavaScript rule. D2's validation is server-side
  precisely so it need not.
- **It does not fix the AQI-insensitivity half of §1.1.** See §4.
- It does not close the 0–6, 31–61 or 71+ age-bracket gaps. See §1.4(a).
- It does not address the ragged foot, or Appendix B **except** for the four
  Hindi items 5a necessarily touches: `headline/Moderate`'s "आराम बरतें" (which
  Appendix B itself says "needs a corpus-wide pass" — this is that pass),
  `band_advice/Moderate`'s missing comparand, the English/Hindi strictness
  mismatch, and the two Latin-full-stop items.
- **Five live findings from the 2026-09-01 review are NOT covered and are not
  recorded anywhere else yet:** `.env.example`'s missing `CPCB_API_KEY`, the
  Guide's unconditional source claim, the waqi/cpcb monotonic-vs-wall-clock
  split, the unthrottled `/city`, and the guard's cross-script bypasses. **These
  must be added to `PLAN-gates.md` Appendix B by name** — the first draft
  deferred them to a document that does not exist, in a public repo.

---

## 9. What the review changed

Recorded because a plan that hides its own corrections is the defect it exists
to prevent. Four independent lenses reviewed the first draft.

**Wrong, and corrected:**
- Three measured numbers. The sweep bypassed `normalize` and handed
  `compute_risk` unrecognised keys (`heart_condition`, `fit`), silently scoring
  those personas as having no condition. Real figures are worse: 38/22 not
  31/29, 51/9 not 44/16, **19 of 38** wrong-organ not 10 of 29.
- The claim "the command that produced it is named beside it" was false — no
  command was named. `scripts/measure_gate5.py` now exists so it is true.
- The linguistic premise. "Hindi requires a noun phrase after a colon" is false;
  the `ui.share_for` postposition argument replaces it.
- The Hindi fix table pointed only at `with_activity_and_place`; the kicker uses
  `with_activity`, so the fix missed the reported defect entirely.
- `risk.py:143-144` was quoted with wording that lives at `risk.py:66-67`.
- "Ages 11 to 21" → 11 to 20. "Fourteenth line" → thirteenth.
- D6's ordering reversed.

**Missed, and added:** the `_MAX_RATIO` rescaling; the five tests the banner
removal reds; the six surfaces asserting the banner stays; `share_for`, the
double em-dash and the Latin full stop; the vacuous exit criteria; the
`DESIGN.md` contradiction; the dangling reference in §8; that किशोर spans both
brackets; that the picker labels already use the proposed verbal-noun forms.

**Refuted later, by reading the source (2026-09-01):** §1.4(b)'s
adolescent-exertion hypothesis, and G5-R4's rescaling risk. Both were marked
uncertain rather than asserted, which is why finding them false cost a paragraph
each rather than a merged falsehood.

**Rejected:** that four tests fail on `fontTools` and it must be installed —
an artefact of a reviewer running system `python3` rather than `.venv/bin/python`;
fontTools 4.63.0 is present and those 26 tests pass. Glyph coverage for every
proposed string, including `किशोर` and `युवा`, was checked separately against the
shipped faces and is complete. A hypothesis that the shorter kicker would breach
the ragged-foot ceiling was measured and refuted by the reviewer who raised it.
