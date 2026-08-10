# SaafSaans — gated delivery plan

Written 2026-08-10, immediately after Gate 0 (deploy) completed and was verified.

This file is the contract between a **main orchestrator** session and the
**sub-orchestrators** it spawns, one per gate. It is tracked by git on purpose:
`.claude/` and `.impeccable/` are untracked and do **not** exist inside an isolated
worktree, so anything under them must be read by absolute path or pasted into a
subagent's prompt verbatim. `PRODUCT.md` and `DESIGN.md` **are** tracked and will be
present in every worktree — read them both in full before touching anything.

---

## 1. How this document is used

- The **main orchestrator** owns this file. It never edits product code itself.
- For each gate, in order, it spawns **one sub-orchestrator**, which owns the whole
  cycle for that gate (plan → adversarial review → build → code review → merge).
- The main orchestrator's only job between gates is to **verify the gate's exit
  criteria against the repo and the running app** — not against the
  sub-orchestrator's report.
- A gate is closed only when its **Exit criteria** below are all true, each backed by
  a command whose output the main orchestrator has seen.

### Gate order (strictly sequential — never parallel)

```
--- BEFORE PROMOTION -------------------------------------------------
Gate 0    deploy + verify                                DONE 2026-08-10
Gate 0.5  viewport telemetry                             ~1 day    <- next
Gate 1a   the window must be true at the hour it is read ~1-2 days
Gate 1b   copy: orientation + advice + activity ratio    ~1.5 days
Gate 1c   card alignment                                 ~2 hours
Gate 1d   deploy + verify the whole batch                ~1 hour
          >>> PROMOTE HERE <<<
--- AFTER PROMOTION --------------------------------------------------
Gate 2    correctness debt (3 groups)                    ~2-3 days
Gate 3    test guards that bite                          ~1-2 days
Gate 4    decided by real usage, not in advance          unscheduled
```

**"Go live" means PROMOTE.** The app has been deployed at
`saafsaans.stackclimb.com` for months and now runs master. Nothing below is
blocked on infrastructure; the gates are what should be true before you send
anyone to it.

**On telemetry timing:** Gate 0.5 collects almost nothing before promotion,
because there is almost no traffic before promotion. Its value is being *in
place when traffic arrives* — which is exactly why it is built first and
deployed with the Gate 1 batch, not after.

**Why sequential:** every gate touches `app.css`, `tests/test_a11y.py`,
`tests/test_web.py`, or `i18n.py`. Parallel gates would collide in the shared working
tree. Within a gate, read-only work (review, audit, verification) fans out wide;
writes serialize, or use `isolation: "worktree"` across genuinely disjoint files.

---

## 2. Orchestration protocol (every sub-orchestrator follows this)

0. **Read first, in full:** `PRODUCT.md`, `DESIGN.md`, and this file. All three are
   tracked and present in a worktree.
1. **Sync check.** `git fetch origin`, confirm `master == origin/master`, confirm a
   clean tree (only `.claude/`, `.impeccable/`, `PRODUCT.md` untracked), run the full
   suite and record the baseline count. If master moved, merge/rebase cleanly and
   re-verify green **before** any work.
2. **Fresh branch** off master: `gate<N>-<slug>`.
3. **Requirements review** — a fan of read-only subagents restates the goal, finds
   every file involved, and lists what must not regress.
4. **Exhaustive plan** — one planner produces the implementation plan: exact files,
   exact tests, the exact mutation that must turn each new test RED.
5. **Plan review** — an independent reviewer, plus **one adversarial reviewer whose
   job is to reject the plan**. Both must be satisfied, or the plan is revised.
6. **Build** — TDD, bite-proof, worktree-isolated. Test first → RED for the expected
   reason → implement → GREEN → revert only the implementation → RED again → restore
   → GREEN. The revert-proof is reported with real command output.
7. **Code review** — a fan of independent read-only reviewers: correctness,
   test-depth, design-system + a11y, and one adversarial PR reviewer.
8. **Fix loop — hard cap of 2 cycles.** After the second cycle, stop. Record every
   unresolved finding as a leftover in this file's Appendix B. Never loop further.
9. **Merge** into master, rerun the full suite **on master**, then push.
   Never `git push --force`. Never `git branch -D` (safe delete only).
10. **Hand back** to the main orchestrator with the gate's exit evidence.

### How to report a stop

When a gate hits a checkpoint that belongs to the owner, do not guess and do not
stall silently. Report exactly four things, in this order, in plain language:

1. **Where things stand now** — the current behaviour, measured, not described.
2. **What is being asked of the owner** — the decision, stated as a choice between
   named options, not as an open question.
3. **What changes after each option** — what the product does differently, and what it
   costs, for each choice.
4. **A concrete example** — one specific reader, one specific moment, showing what
   each option would mean for them.

Then give a recommendation in a few bullets. A stop that does not do all five is not
a stop, it is an interruption.

**Budget note:** a prior autonomous run hit a weekly usage limit mid-flight. Every
workflow must be resumable — prefer one gate per run, and record progress here as it
completes so a fresh session can pick up without re-deriving anything.

---

## 3. Standing constraints (paste verbatim into every subagent prompt)

- **(a) Zero JavaScript, strictly.** Every feature works with full-page-load
  mechanics only. Any proposal needing JS is out of scope.
- **(b) Obey DESIGN.md's named rules:** Never-Colour-Alone, Monotone Severity (binds
  tints as well as inks), Quiet Caveat, Devanagari Floor, Flat-On-Paper, Steady Digits.
- **(c) Read the impeccable reference docs by ABSOLUTE path** — that directory is
  untracked and absent from worktrees:
  `/Users/rohitagrawal/Projects/saaf-saans/.claude/skills/impeccable/reference/craft-floor.md`
  plus the command doc that matches the work (`polish.md`, `harden.md`, `clarify.md`,
  `audit.md`, `critique.md`).
- **(d) Every change is TDD and bite-proof** — see protocol step 6. A test that passes
  when the feature is absent is worthless. Never write a check that goes red when the
  bug is fixed.
- **(e) Comment style:** measurement or reason. Never narration, never "this fix",
  never an issue number.
- **(f) Evidence discipline:** re-verify every finding against current source before
  building. If it is already resolved or not reproducible, say so plainly and move on.
  That is a correct outcome, not a failure.
- **(g) Health-claim gate (Gates 1 and 3 especially).** Every user-facing sentence
  about air, dose, or behaviour must trace to `docs/research/2026-07-exposure-evidence.md`.
  Its own copy-review checklist forbids: a promised health outcome (D1); a specific
  filtration percentage (D3); a µg/m³ figure for a commute mode (D6); "stop walking"
  (D6); "use the AC" — say recirculation (D7); "ambient AQI is uninformative" (D8);
  a modelled figure presented as measured (D4); dismissing a purifier as useless (D2).
- **(h) Hindi parity.** Every copy change ships in both languages. No Hindi speaker has
  verified the draft; the banner saying so must stay until one has.
- **(i) Honesty over polish.** A sample must never drive severity. Absences are stated,
  never fabricated: no testimonials, no clinical validation, no named users.

### Repo facts a subagent cannot discover from a worktree

- Interpreter: `/Users/rohitagrawal/Projects/saaf-saans/.venv/bin/python` (absolute).
- Run tests with the working dir as cwd so the local package wins:
  `cd <dir> && /Users/.../.venv/bin/python -m pytest tests/ -q`
- Run the app offline, zero API keys: `... -m uvicorn saafsaans.web.main:app --port <free port>`
- `.env` and `.venv` are gitignored and absent from worktrees; copy `.env` in if needed.
- Views: `/` Today, `/city` City Pulse, `/system` System, `/guide` Guide. `?lang=hi` for Hindi.
- Deploy is **manual** — there is no CI workflow. `fly deploy` from the repo root.
- `requirements.txt` carries three test-only dependencies with their reasons:
  `fonttools`/`brotli` (read the shipped woff2 glyph tables) and `websocket-client`
  (drive headless Chrome over the DevTools protocol for computed-style assertions).

---

## 4. The gates

### Gate 0 — Ship what exists — **DONE 2026-08-10**

**Goal:** close the gap between merged and shipped.

Completed and verified:

- [x] `master` == `origin/master` at `4d65d37`, full suite **1341 passing**.
- [x] `fly deploy` succeeded; machine `80e449c6253118` (bom) reached a good state, 1/1 checks.
- [x] **Verified by the running build, not by `/health`:** live `app.css?v=70ad07b4495d`
      is byte-identical to local master's hash; the Google Fonts CDN `<link>` is gone
      (self-hosted subsetted woff2 now serve); `/guide` serves 4
      `tabindex="0" role="region"` scroll ports from this round's fix.
- [x] All four views plus `?lang=hi` return 200.

Note for the record: production had been running a build that predated the entire
self-hosted font effort. Merged is not shipped.

---

### Gate 0.5 — Viewport telemetry (the "deeper fix") — **NEXT**

**Goal:** stop guessing whether users are on a phone or a desktop. Every layout
decision after this one should be answered by data, not by assumption.

**Why first:** it must be live and collecting *while* Gates 1–3 run, or its answer
arrives too late to inform them. It is also the smallest, safest change in the plan.

**Why it matters:** `PRODUCT.md` asserts "they check on a phone." That is a design
assumption, never measured. The app records **no** device or viewport data anywhere
(verified: no user-agent, viewport, or device field in `metrics.py`, `es.py`, or
`main.py`). Meanwhile `PRODUCT.md` also names evaluators — judges, recruiters, peers —
who open links on a laptop, so the desktop two-column view may well be the majority
first impression.

**THE OWNER DECISION AT THIS GATE — resolve before building**

*Where things stand now.* The app records nothing about the device: no user-agent, no
viewport, no device field anywhere in `metrics.py`, `es.py` or `main.py` (verified).
`PRODUCT.md` says "they check on a phone"; that has never been measured. It also names
evaluators — judges, recruiters, peers — who open links on a laptop. So we do not know
whether the one-column phone layout or the two-column desktop layout is the majority
experience, and every layout argument is currently opinion against opinion.

*What is being asked of you.* Choose the measurement method. Three options:

- **Option A — CSS media-query probe (no JavaScript).** The stylesheet declares a
  background image per width band; the browser fetches only the one whose media query
  matches, so the server learns the real viewport band from which URL was requested.
  Real viewport, no user-agent parsing, no fingerprinting, zero JS. Costs one extra
  small request per page load, and needs `Cache-Control: no-store` on the probe or
  repeat visits stop reporting.
- **Option B — coarse user-agent class (no JavaScript).** Parse the UA server-side into
  phone / tablet / desktop, store only the bucket, discard the string. No extra
  request. But it answers a *different question*: device class, not viewport. A desktop
  browser at a 500px window counts as desktop; a tablet is a coin flip.
- **Option C — a JavaScript beacon.** Exact viewport, one tiny script. Requires
  relaxing the zero-JavaScript rule, which `PRODUCT.md` records as **open, not
  decided** — so this is a legitimate choice, but it is a product-level one and it is
  yours alone.

*What changes after each.* With **A**, layout decisions become evidence-based and the
zero-JS rule survives intact; the System view can honestly say "viewport bands, by page
load." With **B**, you get a cheaper, coarser answer and must label it "device class,
not viewport" forever. With **C**, you get the most precise data and the product loses
the constraint that currently makes it unusual.

*A concrete example.* A recruiter opens the link on a MacBook and drags the window to
half the screen — about 700px wide. **A** records "medium" and tells you the truth: the
two-column layout is what they saw. **B** records "desktop" and you would keep
optimising a 1120px layout they never looked at. **C** records 700px exactly, and costs
you the zero-JS claim.

**Recommendation**

- **Take Option A.** It answers the question actually asked (viewport, not device),
  keeps the zero-JS rule, and needs no new dependency.
- **Do not take C for this.** Spending the product's most distinctive constraint on an
  analytics detail is a bad trade; if zero-JS is ever relaxed, it should be for a
  reader-facing gain, not a metric.
- **B is the fallback** if the extra request proves unacceptable — but write "device
  class, not viewport" on the System view and never let it be quoted as a viewport
  figure.
- **Whichever you pick, count page loads and say so.** Without cookies or identifiers
  this cannot count people, and the System view must not imply otherwise.

**Action items**

1. Record a **coarse viewport/device bucket** per request — a small fixed set of bands
   (e.g. narrow / medium / wide), resolved by the chosen method above.
3. **Privacy floor, non-negotiable:** no raw user-agent string stored, no IP, no
   fingerprinting, no per-user identifier. A counter per bucket, nothing more.
4. Surface the breakdown on the **System** view, in the proof register (mono, flat),
   with a caveat naming the method's limits.
5. Tests: the bucket function, the privacy property (assert the raw UA never reaches
   storage), and the System rendering in both languages.

**Exit criteria**

- [ ] Full suite green on master, count recorded.
- [ ] Deployed, and the System view shows a non-zero bucket count from real traffic.
- [ ] A test proves no raw user-agent or IP is persisted — and it bites when mutated.

---

### Gate 1 — The window must be true, then the advice, then the cards

**Goal:** stop being another app that says "don't go out." Give a reader a lever they
did not know they had — and make sure the lever is not pointing at a time that has
already passed.

**Why this outranks real defects:** a reader who bounces at a prohibition never reaches
the bug. And the copy rewrite *leans on* the window, so the window must be true first.

#### 1a. The window must be true at the hour it is read — **do this first**

**Verified defect (2026-08-10, 17:52 IST).** `forecast.best_window()` reads
`clock.today_ist().month` for the season and **never reads the hour**. Measured at
17:52 IST, every driver returns a window already in the past:

| Driver | Returned window | Status at 17:52 |
|---|---|---|
| PM2.5 (non-winter) | "Late morning (about 9 AM–12 PM)" | 6 hours gone |
| Ozone | "Early morning (about 6–9 AM)" | 9 hours gone |
| Traffic gases | "Midday (about 11 AM–3 PM)" | 3 hours gone |

It renders in the hero's anchored bar under the label **"IF YOU MUST GO OUT"**, so at
5pm the single most actionable element on the page is guaranteed wrong. This is the
one claim a reader can verify instantly against their own clock, which is exactly why
it costs more trust than a subtler error would.

**The required behaviour (owner's spec, 2026-08-10):**

1. **Always answer for today first.** A reader opening the app now wants the best time
   in the **remaining hours of today**, not a general daily pattern.
2. **Never leave them without a today answer.** If the genuinely better window is
   tomorrow, say so *and* still name the **least-risk remaining option today**.
3. **State the risk at the time you suggest.** If the least-risk remaining hour is
   still Poor, say that plainly alongside the lever (shorter, slower, N95) — do not
   present a least-bad hour as if it were a good one.
4. **Always name which day you mean.** Never print a bare clock time once today's
   window has passed.
5. **Preserve the honest branches.** The AQI > 300 "no safe window" and the no-reading
   branch must not regress into naming a friendly hour — but under rule 2 they should
   still offer the least-risk remaining option and its lever.

**Implementation notes**

- The diurnal shape per pollutant already encodes what is needed; the work is to
  **intersect that shape with "now → end of day"** and rank the remaining hours, rather
  than returning a fixed label. No hourly station feed is required.
- `best_window()` already accepts a `forecast` argument it does not use — that is the
  hook for the tomorrow case.
- Constraint (g) still binds: this stays a rule of thumb. The existing
  `window.general_note` ("a general pattern, not an hourly station forecast") must
  survive, and no modelled figure may be presented as measured.
- Both languages, per constraint (h).

**Testing — the gap this exposed, and the rule that comes out of it**

The suite has 1341 tests and 16 on this module, and none caught it. One of them,
`test_the_season_is_decided_in_india_not_on_the_server`, **freezes the clock at
2026-11-01 01:30 IST and asserts only that the month reached `_is_winter`** — it had
the clock in its hands and never asked what the window says at 01:30. The tests were
written from the implementation, so they inherited its assumption that the window is
time-independent.

**Standing rule from here on: time is an input dimension, like language and viewport.**

- Add a clock-freezing fixture and assert page coherence at **06:00, 12:00, 17:00 and
  23:00 IST**, in both languages.
- Bite-proof: with the fixture at 17:00, the pre-fix code must turn the test RED.
- Apply the same discipline to any future audit — the nine-lens audit of 2026-08-10
  varied language, theme and six viewport widths, but only ever rendered a single
  instant. That is why it missed this.

#### 1b. Copy: orientation, advice, and the one honest number (~1.5 days)

The current strings, verified in `saafsaans/services/i18n.py`:

- `band_advice.High` — "Don't exercise outside. Keep going out to a minimum…"
- `band_advice.Very High` — "Stay indoors if you can…"
- `band_advice.Extreme` — "Don't go outside."
- `window_none` — "There is no safe time to be outside today; stay indoors…"

Three of five advice bands lead with a prohibition, and the worst-case window leaves a
person with a school run holding nothing.

**Action items**

1. Rewrite `band_advice` (×5), `headline` (×5), and `window_none` — **in both
   languages** — so every one names *what to do*, not only what to avoid.
2. **Never render an empty-handed state.** When no window is safe, name the least-bad
   hour and what a mask and a slower pace change about it.
3. Lean on the levers the product already computes: **time of day**, **duration**,
   **intensity** (`risk.inhalation_ratio` is a real EPA Table 6-2 lookup, already
   wired into `dose_points`), and **filtration**.
4. Every sentence passes constraint (g)'s checklist before it ships.
5. Tests: assert each band's advice contains an actionable clause, in both languages,
   and that no band's advice is prohibition-only.

**First-visit orientation — DECIDED 2026-08-10.** Measured on the live first-visit
page, a new reader meets, in this order: the wordmark; `AQI 335 · Very Poor`;
`EXAMPLE — FOR AN ADULT WITH ASTHMA`; **"Don't go out unless you must — this air is
dangerous for you."**; `91/100 · Extreme` beside `healthy adult, same plans · 79`;
the window; and only *seventh*, "This page is showing an example… fill in your own
details."

- "What am I supposed to do" IS answered — the form is open, the example is labelled,
  the instruction is explicit. **Do not touch that onboarding work.**
- "What is this?" is answered **nowhere**. No sentence on the page states the product's
  purpose. "clean breath" is a translation, not a description.
- "How is it useful to me?" is absent. The differentiator — *every other app says how
  bad the air is; this says how bad it is for you* — lives only in PRODUCT.md.
- The first substantive sentence is an alarming verdict about a stranger.
- **The most important thing on the page is unlabelled:** `91` beside `79` IS the
  product — the personal delta — rendered as two bare numbers with no sentence saying
  what the gap means.

Action items:
6. Add **one line above the hero** stating what the app does and why it differs. Not a
   tour, not a modal (zero JS anyway).
7. Add a **short label to the 91-vs-79 comparison** naming what the gap is.
8. Consider moving the "this is an example" orientation **above** the alarming verdict.

**The one honest number — DECIDED 2026-08-10.** Ship the **activity** ratio, not the
timing one:

9. `risk.inhalation_ratio()` is a real EPA Table 6-2 lookup already live in the code:
   adult outdoor exercise **11.9x** sedentary, school run **6.19x**, commute **2.86x**.
   Comparing two activities is a ratio of two real table values — **no concentration,
   no forecast, no new data source**. Use it to give the reader a lever with a number:
   "running takes in about four times the air that walking does."
10. The **timing** number ("7pm saves you 84 ug") is deferred to Gate 4 — see the risk
    register. It cannot be computed honestly today.
11. Check that no caller passes a spaced activity string: `inhalation_ratio("child",
    "school run")` silently returns the sedentary fallback because the keys are
    underscored (`school_run`). A silent fallback would understate a child's intake.

#### 1c. The uneven cards (~2 hours)

**Measured** (Chrome 151 headless, persona applied): the row is full — no dead track
— `532px 532px` at 1120–1600px. The persona card is **309px** tall against the
reading card's **360px**: a **51px** ragged foot, narrowing to 13px at 900px. Cause is
`align-items: start` on `.grid` (`app.css:208`), which is deliberate and correct —
stretching would inflate a card with meaningless empty padding.

**Action items**

1. Fix the asymmetry **at the source, not by stretching**: the reading card is taller
   because it carries the CPCB scale bar *and* the WHO comparison line. Move one into
   the full-width caveat row that already sits below, so the two cards land within
   ~10px naturally.
2. Do **not** set `align-items: stretch`.
3. Repair the tests that pin card structure; add one that pins the new placement.

**Exit criteria**

- [ ] At 06:00, 12:00, 17:00 and 23:00 IST the named window is never in the past, always
      carries its day, and always offers a today option with its risk stated.
- [ ] The clock-freezing fixture exists and bites: the pre-fix code goes RED at 17:00.
- [ ] No `band_advice` or `headline` string is prohibition-only, in either language.
- [ ] `window_none` names a least-bad hour and a lever.
- [ ] Every new sentence checked against the evidence checklist; the check is recorded.
- [ ] Card height delta at 1120px is under ~15px, measured in a real browser.
- [ ] Full suite green on master; count recorded.

---

### Gate 2 — Correctness debt

**Goal:** close the three groups where the app is currently wrong or self-contradictory.

#### 2a. Devanagari Floor, enforced by measurement not by list — **highest**

Root cause: the floor is policed by hand-maintained selector lists, and every audit
finds another place a list missed. Seven findings share this one cause:

1. `.sim-note` renders Hindi at **12px**, under the 12.5px floor *(unfixed MUST-FIX;
   pre-existing on master — `.sim-note { font-size: 12px }` is byte-identical at `f7cd845`)*.
2. `h2.kicker` stays letter-spaced in Hindi (measured 1.5px = .12em at 12.5px).
3. The `lang="en"` escape hatch is inert — English text on Hindi pages still renders in
   Anek Devanagari at Hindi floors (`app.css:721-729` set the variables but nothing
   re-reads them per element).
4. The carve-out sweep reads only top-level rules, so an uppercase rule inside any
   `@media` block is invisible to it.
5. The sweep's `endswith` coverage clause passes rules that genuinely do uppercase
   Devanagari.
6. The tracking-specificity guard has an `!important` blind spot.
7. **A regression this round shipped:** `html *:lang(hi):lang(hi) { letter-spacing: normal }`
   (`app.css:793`, from `d2b5fe9`) outranks `.wordmark b`'s `-.01em` (`app.css:181`),
   so the Latin wordmark loses its display tracking on Hindi pages (0.21px per gap at 21px).

**The single fix:** render every Hindi page, compute styles for every element
containing Devanagari codepoints (U+0900–U+097F), and assert the floors — size,
tracking, case — against what the **browser resolved**. That one test replaces four
brittle selector-list guards and cannot be outflanked by specificity, `@media`, or
`!important`. The harness is proven: the triage agent drove headless Chrome over CDP
with `Emulation.setDeviceMetricsOverride` to reach genuine 320/360/414px viewports.

#### 2b. Honest zeros on System

`has_index` is threaded into some number-printing sites but not all, so the card can
contradict itself in a single render.

1. Three KPI tiles print unqualified zeros in the no-index state — including
   "0% stopped pre-model" beside the card's own "all blocked before the model".
2. "No locality data yet." is the one empty state left unbranched on `has_index`.
3. The refusal card claims the blocked prompt was "audited in security-events" when
   nothing was recorded (`today.html:426`).
4. A **measured** zero is indistinguishable from an unmeasured one — mutating
   `_kpi_stat`'s `if value is None` to `if not value` survives the entire suite.
5. `test_security_empty_state_says_how_to_produce_data` now asserts the opposite of
   its own name.
6. `assert "3" in body` is vacuous — "3" is present with zero rows.
7. `es.index_answers` ships three asserted safety properties with no test: the 2s
   timeout bound, the 60s failure TTL, and the cache itself.
8. The new `--` placeholder ships with no accompanying text or accessible name.

**The single fix:** thread `has_index` through every number-printing site, plus one
test that separates "measured zero" from "not measured".

#### 2c. Geometry step-class residue

`859d86c` correctly moved geometry from inline styles to step classes under CSP
(`style-src 'self'` was silently dropping `style="left:65.0%"`, parking a 325 caret at
0%). The conversion left edges:

1. **The chart reads backwards:** a nonzero day rounds to `p0` and draws 0.31px while
   a zero day draws the 2px `.b-nil` baseline.
2. `.b-nil` has no biting test — delete it and zero-days vanish, suite green.
3. The ▾ caret sits ~10.6px right of what it marks — 4.2% (≈21 AQI) at 320px, and past
   the end of the bar at AQI 500. *(Pre-existing: the whole string `"325 ▾"` is centred
   by `translateX(-50%)`, not the glyph. Same markup at `f7cd845`.)*
4. The per-day count is pinned to the top of the 74px band, up to 35.6px above its bar.
5. `style="max-width:640px"` was deleted rather than moved to a class — `.kpi` now
   measures 353px on Security against 172px elsewhere.
6. Two CSS comments describe inline margins the change removed.
7. The Guide's closing paragraph lost its 16px separation (now 8px).

**Exit criteria**

- [ ] The Devanagari sweep test exists, is browser-measured, and bites on each of the
      seven cases above.
- [ ] No System surface prints an unqualified zero when nothing was measured.
- [ ] A zero-count day can never draw taller than a nonzero day.
- [ ] Full suite green on master; count recorded.

---

### Gate 3 — Guards that bite

**Goal:** make the test suite trustworthy. (The counterfactual that used to live here is
deferred — see 3a.)

#### 3a. The timing counterfactual — **DEFERRED to Gate 4, decided 2026-08-10**

The intended feature was "her now vs her at the better hour". It cannot ship honestly
today: **there is no hourly data in this application.** The forecast block is
`forecast["daily"]["pm25"]` — `{day, avg, min, max}`, daily only. A per-hour ug figure
would be a modelled diurnal curve layered on a daily average — modelled on top of
modelled — and constraint (g) forbids presenting a modelled figure as measured (D4).

It is a **data problem, not a code problem**. Making it defensible needs a real hourly
concentration source (OpenAQ v3 serves raw ug/m3, live plus archive). That is a new
integration, an API key, caching and failure modes: roughly a week, and a change to the
data layer. Treat it as its own decision about the data layer, not a UI feature.

The honest number that ships instead is the **activity** ratio, in Gate 1b.

#### 3b. Guards that cannot bite (11 items)

1. `test_every_aria_current_state_is_also_a_visible_one` only proves a rule exists,
   not that it paints anything different; and it is an emptiness assertion with no
   partner — deleting `aria-current` from all four ask chips leaves the suite green.
2. The `.row` source-order guard has an at-rule hole (`tests/test_declutter.py:608`).
3. The `.scale` width guard ignores language-scoped and higher-specificity overrides.
4. `role="region"` is not asserted — deleting it from all four Guide wrappers leaves
   the suite green while destroying the accessible name the test claims to protect.
5. The WHO-AQG-2021 English-fallback guard can never fail: Jinja escapes the
   apostrophe to `&#39;`, so the raw substring can never appear.
6. The station-row test models only the `.no-bands` layout, so `.station .bd`'s 76px
   reserved column counts as 0.
7. `_budget` sums ancestor padding but never ancestor borders (260px granted vs 258px real).
8. `tests/test_held_reading.py:415` quotes a Hindi string that does not exist in the corpus.
9. The contrast test crashes with `AttributeError` on a literal colour value.
10. The uppercase carve-out guard's `endswith` fallback (also in Gate 2a).
11. The `SOURCE_GLOSS_HI` comment states a uniqueness rule two of its own rows break.

**Exit criteria**

- [ ] Each of the 11 guards demonstrably goes RED under a stated mutation.
- [ ] Full suite green on master; count recorded.

---

### Gate 4 — Decided by real usage, not in advance

Do **not** schedule these. Revisit once Gate 0.5's telemetry and any real traffic have
something to say.

- **The fold problem.** The "when" half of the answer falls below the fold on Hindi at
  360×640 and on a 375×553 English viewport — real against the five-second promise, but
  the remedy is a header/banner space redesign that needs a design decision from the
  owner, not an autonomous pass.
- **The school-run / second-persona surface (~1 week).** "Send a child outside" is a
  second persona checked by a first; today she must swap the whole persona and lose her
  own reading. Stress-test first: does she want a second reading, or just a yes/no for
  the child? If the latter, it is a copy change, not a feature.
- **The exposure-ledger thesis** (inhaled µg as the headline, with a falsifiable
  avoided-dose metric). A product-thesis change; decide it against usage.
- **Fonts and payload** (6 items, one change): limit the variable-font weight axis to
  what the CSS selects; preload IBM Plex Mono on English; gate `fonts.css` by language;
  content-hash the font URLs; skip gzip for woff2; fix `build_fonts.py`'s docstring,
  which now contradicts `requirements.txt`.
- **Design-system tidy** (8 items) and **a11y/copy one-offs** (11 items) — Appendix B.

---

## 5. Risk register

Ranked by expected damage, not by likelihood.

| # | Risk | Gate | Why it bites | Mitigation |
|---|---|---|---|---|
| R1 | An unsourced health claim ships in the new copy | 1b | The app gives health guidance to people with asthma, COPD and pregnancies. One promised outcome or invented percentage destroys the honesty position the whole product rests on | Constraint (g) checklist run against **every** new sentence, in both languages, and the check recorded in the PR |
| R2 | The window fix changes what the Q&A model is told | 1a | `best_window`'s output is injected into the LLM prompt under an instruction telling the model to trust it. Changing the window silently changes Q&A answers | Assert Q&A behaviour at the four frozen clock times before and after; treat any answer change as in-scope |
| R3 | The honest branches regress into naming a friendly hour | 1a | AQI > 300 and no-reading are currently the *only* correct branches. A refactor that ranks "remaining hours" could hand them a cheerful time | Pin both branches with tests **before** touching the ranking logic |
| R4 | Hindi ships wrong and nobody notices | 1a/1b | Devanagari is unicameral and no Hindi speaker has verified the draft; the suite cannot catch a fluent-but-wrong sentence | Every string reviewed in the rendered page, not the dictionary; the unverified-Hindi banner stays |
| R5 | Browser-measured tests make the suite slow or flaky | 2a | The Devanagari sweep needs headless Chrome over CDP. A flaky gate is worse than no gate | Keep it a separate marked suite; assert determinism by running it three times before merging |
| R6 | Gate 0.5 ships a device signal that quietly misleads | 0.5 | Zero JS means there is no viewport on the server. A user-agent proxy answers a different question than the one asked | State the method and its limits in the System view; never present the proxy as a viewport measurement |
| R7 | A usage limit kills a run mid-flight | any | Already happened once this project: a run died between build and merge, leaving ten branches unmerged | One gate per run; progress recorded in this file as it completes |
| R8 | Manual deploy drifts from master | 1d | There is no CI. Production sat months behind master until 2026-08-10 and nobody knew | Verify every deploy by asset-hash identity against local master, never by `/health` |
| R9 | The card fix breaks tests that pin card structure | 1c | Several tests assert the reading card's contents and order | Expected and cheap; repair them in the same commit |
| R10 | The timing counterfactual gets built anyway | 4 | It is the most attractive idea in the backlog and the least defensible without hourly data | It is written down as deferred, with the reason. Revisit only alongside a data-layer decision |

---

## Appendix A — What "done" means here

- Done = merged **and** verified running in production. Green on a branch is not done.
- Verify a release three ways: run it and check the output; search for absence (a flag
  never shown, a test in no workflow); confirm the live build matches what was merged.
- Never report from a tracker or a summary.
- Confirm a deploy by the deploy **job** completing and the running build's identity —
  never by an unchanged `/health` 200, which returns 200 either way.

## Appendix B — Non-blocking leftovers not yet scheduled

Recorded so nothing is silently dropped. None of these blocks a gate.

**Design system:** `.pat` paints Very Poor severity tokens (`--n5`/`--g5`) on a
non-severity security tag · `.caption` is a third quiet-qualification tier below
`.caveat` · `.fields .btn` is a second button geometry contradicting DESIGN.md's single
`.btn` spec · three dead padding declarations and a dead `.fields label` flex basis ·
`tabular-nums` not restored on `select`/`input`/`.btn` after the UA `font` shorthand
resets it · `--chart` is absent from DESIGN.md's frontmatter (it is now in the sidecar).

**Accessibility:** decorative `▸` inside the red-team button's accessible name · the
provenance chip's `●`/`◌` glyph is spoken as part of the freshness text · City Pulse's
21-station rail is a bare div, so list structure and worst-first rank are not
programmatically determinable · no `aria-controls` on the term disclosures.

**Responsive:** Hindi pill buttons drop to a 29px target outside both pointer media
queries (clears WCAG 2.1 AA's 24px; misses DESIGN.md's own stated rule).

**i18n:** two Hindi sentences end in a Latin full stop rather than a danda · missing
space before the separator after the PM2.5 unit, which compounds in Hindi.

**Typography:** System KPI labels are set in the body face on the page defined by its
mono register.

**Copy / states:** a whitespace-only question is accepted and answered with full health
instructions · an answer with no retrieved guidance shows no sources block and no
explanation · with no reading the hero still asserts "No safe outdoor window today"
under a caveat describing a data-driven pattern · the hero window is labelled "IF YOU
MUST GO OUT" even when the verdict says to go out · Guide table headers are
centre-aligned over left-aligned data · the ask chip's accent fill marks a *staged*
question and disappears once it is answered · the selected chip's focus ring is the
same colour as its own fill.

**Rejected, with reasons — do not resurrect without new evidence:** the
largest-text-is-a-number arithmetic (DESIGN.md prescribes both values) · stripping
26KB of design-rationale comments from `app.css` (needs a build pipeline) · the
systemic spacing-scale drift (pre-existing everywhere; acting on it is a redesign) ·
three performance claims their own authors measured and refuted.
