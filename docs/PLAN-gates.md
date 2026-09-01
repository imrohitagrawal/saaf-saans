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
Gate 0.5  viewport telemetry                             DONE 2026-08-10
Gate 0.9  CI, and a merge gate that binds                DONE 2026-08-31
Gate 1a   the window must be true at the hour it is read DONE 2026-08-31
C1        fonts and payload (was Appendix B)             DONE 2026-08-31
B1        page-load counts leave Elasticsearch           DONE 2026-08-31
P1        /health says which commit is running           DONE 2026-08-31
Gate 1b   copy: orientation + advice + activity ratio    DONE 2026-08-31
Gate 1c   card alignment                                 DONE 2026-08-31 (ragged foot open, see below)
Gate 1d   deploy + verify the whole batch                DONE (folded into 2026-08-31 deploys)
          >>> PROMOTED — the app has been running master at saafsaans.stackclimb.com <<<
--- AFTER PROMOTION --------------------------------------------------
Scorer honesty  AQI-0/unmeasured severity (found during Gate 2, fixed first)  DONE 2026-09-01
Gate 2    correctness debt (3 groups)                    DONE 2026-09-01
Gate 3    test guards that bite                          DONE 2026-09-01
Gate 4    decided by real usage, not in advance          unscheduled  <- next, if ever
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

### Merging, mechanically — learned the hard way on 2026-08-31

The protocol above says "merge into master". Four things about doing that are not obvious,
and three of them nearly shipped a mistake.

**A sub-orchestrator never merges.** It hands back at a green PR; one coordinator holds a
serialized queue. Not a style preference: with several lanes green at once, each was tested
against the master it branched from, so merging in parallel lands at least one commit that
nothing tested against what the others just merged.

**`gh pr checks --watch` will hand you the previous commit's green run.** Called soon after a
push, before GitHub has created a check run on the new head, it reports the *old* run and
exits 0. This happened: a Hindi fix was pushed, `--watch` returned green for the commit
before it, and the merge was one command away. Wait for a check run to *exist* on the actual
head SHA:

```bash
HEAD_OID=$(gh pr view "$PR" --json headRefOid --jq .headRefOid)
gh api "repos/<owner>/<repo>/commits/$HEAD_OID/check-runs" --jq '.check_runs[].name'
```

**Merge pinned to the commit that was tested**, so anything pushed in between refuses rather
than merging untested:

```bash
gh pr merge "$PR" --squash --delete-branch --match-head-commit "$HEAD_OID"
```

**`--delete-branch` abandons the remote deletion if the local delete fails**, and the local
delete fails whenever a worktree still holds the branch. The remote branch is then silently
left behind — `git ls-remote --heads origin` is the check, not the absence of an error. And
after a squash merge `git branch -d` always refuses, because the branch tip is not an
ancestor of master; confirm the content landed before forcing:

```bash
git diff --stat master <branch>   # empty output = every line is in master
git worktree remove <path>        # worktree FIRST -- a branch in use cannot be deleted
git branch -D <branch>
```

`branch_protection` on this repo carries `enforce_admins: true`, so there is no bypass and
`--admin` fails for everyone including the owner. That is deliberate: with it false, a direct
push to master succeeded while GitHub printed `Required status check "suite" is expected`.

---

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

**Owner checkpoints (the only places a run stops for a human):**

1. ~~Gate 0.5 method~~ — **decided 2026-08-10: Option A.** No stop here.
2. ~~Gate 1b, before the copy merges~~ — **removed 2026-08-31 by the owner**, who chose
   to run the remaining gates with no human stops. Read this before assuming otherwise:
   a sub-orchestrator has already deferred to this checkpoint after it stopped existing,
   and correctly said so rather than guessing.

   The claim it made was true when written: new sentences advise people with asthma,
   COPD and pregnancies, in two languages, one of which nobody has verified; R1 is the
   highest-damage risk in this plan; and a human reading the strings is the only
   mitigation a *test* cannot provide. Removing the reader without replacing anything
   would have left R1 with no mitigation at all.

   What replaces it: **`tests/test_health_claims.py`**, which encodes the eight-item
   copy-review checklist from `docs/research/2026-07-exposure-evidence.md` as an
   executable sweep over the whole string corpus — `i18n.HI`, `risk.BAND_ADVICE` and
   `risk._HEADLINE`, walked recursively rather than by a list of keys, so a new key
   cannot slip past it. Every rule ships with two partners: one proving it fires on a
   violation, one proving it does not block the honest sentence it must allow. A further
   test proves the sweep reached the strings at all, because eight absence-checks over
   an empty corpus would pass in silence for ever.

   **It is a smaller thing than the reader it replaces, and that gap is accepted, not
   closed.** It catches eight specific claim shapes. It cannot catch a sentence that is
   fluent, sourced and simply wrong, and it cannot read Hindi for sense — R4 stands
   untouched. The unverified-Hindi banner stays up until a Hindi speaker has read the
   strings.
3. **Promotion.** A gate may deploy; it never promotes. That is the owner's action.

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
  untracked and absent from worktrees. The skill is installed under the user's home
  directory, not inside this project:
  `/Users/rohitagrawal/.claude/skills/impeccable/reference/craft-floor.md`
  plus the command doc that matches the work (`polish.md`, `harden.md`, `clarify.md`,
  `audit.md`, `critique.md`). Confirm the file opens before relying on it. The path
  written here until 2026-08-31 pointed inside the project, where nothing has ever been
  installed, so every subagent that followed this instruction read nothing and said so
  to no one.
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

### Gate 0.5 — Viewport telemetry (the "deeper fix") — **DONE 2026-08-10**

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

**THE OWNER DECISION AT THIS GATE — DECIDED 2026-08-10: Option A.**
The owner chose the CSS media-query probe. Do not re-open this; build Option A. The
alternatives and the reasoning are kept below because a later reader will ask why.

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

**Recommendation — accepted by the owner on 2026-08-10**

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

1. Record a **coarse viewport bucket** per request via the **CSS media-query probe**:
   the stylesheet declares a background image per width band, the browser fetches only
   the band whose media query matches, and the server counts the request. Pick the
   bands from the breakpoints the layout already uses, so the data answers questions
   the stylesheet actually asks.
2. Serve the probe with `Cache-Control: no-store`, or repeat visits stop reporting and
   the counts silently under-read returning readers. A test must pin this header.
3. The probe must never become a tracker: no cookie, no identifier, no IP, no raw
   user-agent. A counter per band, nothing else — and a test that bites if any of them
   reach storage.
4. The System view states plainly that these are **page loads, not people**, and that
   the figure is a viewport band rather than a device.
3. **Privacy floor, non-negotiable:** no raw user-agent string stored, no IP, no
   fingerprinting, no per-user identifier. A counter per bucket, nothing more.
4. Surface the breakdown on the **System** view, in the proof register (mono, flat),
   with a caveat naming the method's limits.
5. Tests: the bucket function, the privacy property (assert the raw UA never reaches
   storage), and the System rendering in both languages.

**Exit criteria**

- [x] Full suite green on master, count recorded — **1372** (from 1341), including
      the browser guard, which runs only where Chrome exists.
- [ ] Deployed, and the System view shows a non-zero bucket count from real traffic.
      **DEFERRED to Gate 1d**, by lines 47–50 above: this telemetry ships with the Gate 1
      batch, so there is nothing to deploy on its own. Nothing else in Gate 0.5 depends on
      it. This deferral was directed by the main orchestrator; it is recorded here rather
      than decided here, and Gate 1d must not close without it.
- [x] A test proves no raw user-agent or IP is persisted — and it bites when mutated.
      `tests/test_viewport_probe.py::test_the_probe_never_writes_an_identifier` sends a
      user-agent, an `X-Forwarded-For` and a `sid` cookie and asserts none of them, nor the
      session hash derived from the cookie, reaches the document. It freezes
      `es.VIEWPORT_FIELDS == {"@timestamp", "band"}`, so any added field is a visible edit.
      Verified RED by widening that set.

**Done 2026-08-10.** Built, reviewed and merged. Not deployed — see the deferral above.

What shipped, and what it costs:

- Bands are `app.css`'s own breakpoints: `0–560px`, `561–899px`, `900px+`.
- Measured in Chrome 151 over CDP before any code was written, and pinned by
  `tests/test_viewport_browser.py`: exactly one probe per page load at every width
  including both boundaries, and `no-store` does make a repeat navigation report again.
- **Known under-counting, measured:** a back/forward navigation reports nothing — the
  back-forward cache restores the document and no request is made. `no-store` fixes
  repeat *navigations*, not *back* navigations.
- **Known over-counting, measured:** resizing across a boundary counts twice.
- Automated traffic (crawlers, link unfurlers, prerender) is counted the same as people
  and cannot be separated without reading the user-agent, which action item 3 forbids.
  The System view says so. **The first numbers must not be read as human traffic** — R6.
- The count is a floor, not a total: past 1200 loads in five minutes from one address the
  page is served normally and the load is not counted.

---

### Gate 0.9 — CI, and a merge gate that binds — **DONE 2026-08-31**

**Goal:** make "merged" mean a machine agreed, not that whoever ran the suite said so.

Until this gate there was no `.github/` directory and no branch protection. The plan's own
step 9 ("rerun the full suite on master, then push") was policed by nothing.

- [x] `.github/workflows/ci.yml`: one `suite` job, no path filters, on every PR and every
      push to master. `python -m pytest` — **bare `pytest` dies at collection** here, because
      `saafsaans` is not installed into the venv and `tests/` has no `__init__.py`, so only
      `-m` puts the working directory on `sys.path`.
- [x] `SAAFSAANS_REQUIRE_BROWSER=1` at job level, so the headless-Chrome test fails instead
      of skipping. Verified on the runner: Google Chrome 151.0.7922.173, and the test spent
      42.26s of a 51s suite actually driving it.
- [x] A tripwire step pinning the browser test's node id, because the env var turns a *skip*
      into a failure but cannot see a test *renamed away*.
- [x] Branch protection: `suite` required and pinned to the GitHub Actions app id,
      `strict: true`, `required_pull_request_reviews: null` (so an agent can still merge),
      `required_linear_history`, no force pushes, no deletions.
- [x] **`enforce_admins: true`.** Proven necessary the hard way: with it false, a direct push
      to master succeeded while GitHub printed `Required status check "suite" is expected`.
      Reverted through a PR (#5). With it true the identical push is `[remote rejected]
      (protected branch hook declined)`.
- [x] **The gate observed failing.** PR #4 appended `body::after { background-image: none }`
      to `app.css` — invisible to all 26 string tests in `test_viewport_probe.py`, caught by
      the browser test. CI went red; `gh pr merge --squash` was refused with "the base branch
      policy prohibits the merge". Closed, never merged; branch and worktree deleted.

`strict: true` is why there is no merge queue: it refuses any PR not up to date with master,
which is the guarantee a queue exists to give. GitHub's native merge queue is unavailable
here anyway — it requires an organization-owned repository, and this one is user-owned.

---

### Gate 0.5 addendum — the telemetry finally measured something, 2026-08-31

Gate 0.5 was recorded DONE on 2026-08-10. **It had recorded nothing at all between then
and 2026-08-31**, and the reason was not in the code: production carried no Elastic
credentials, so `es.get_client()` returned `None` and `_safe_index` returned on its first
line. The System view said so honestly the whole time — *"this index is not answering"* —
and nobody read it. The Elastic project in the local `.env` had also stopped resolving.

Two consequences worth carrying forward:

- **"Deployed" was not "collecting".** The gate's exit criterion (a non-zero band count)
  was recorded as deferred rather than failed, and a deferred criterion nobody returns to
  is indistinguishable from one that was met.
- **The fix removed the dependency rather than restoring it.** Page loads are now counted
  in SQLite on a 1 GB Fly volume (`vol_vwnx0xwo2keg9e9v`, `sin`), as `band -> count`
  integers — not one document per load. A `(day, band)` schema was designed and rejected:
  on a day whose loads all fall in one band, which is the ordinary case at this traffic,
  that row discloses the band for every session hash of that day. Four rows, no timestamp,
  nothing to join.

  This **replaces** the planned ILM/retention work rather than adding to it, and it
  retires three Appendix B items: the unbounded index, the missing retention policy, and
  the timestamp joinable to `app-telemetry`.

**Verified on 2026-08-31, in production, by running it:** `/data` is owned by uid 1000,
not root; six probes produced `0–560px 3 · 561–899px 2 · 900px+ 1`; the counts survived a
machine restart; an unknown band and a path-traversal attempt both return 404.

**Still unverified:** whether Fly honours `auto_stop_machines = "suspend"` with a volume
attached. If it does not, the fallback is `stop` — a slower cold start, no data loss,
because the volume is durable either way. It needs an idle period to observe.

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

#### 1a — **DONE 2026-08-31.** What shipped, and what it costs

Deployed and verified: release **v15**, `/health` reports `build`
`3e1db68b1366cff6f6d103ec88108b3f0440a248`, equal to the merged commit. Suite **1513**.

`best_window` now reads the hour. Each driver's diurnal sentence is transcribed into an
hourly tier table where **every row carries the clause it rests on**: tier 1 where a
sentence calls those hours calm, tier 3 where one calls them bad, tier 2 everywhere else.
Tier 2 is the *absence* of a claim, so no hour inside it outranks another.

**The design decision worth remembering, because it was got wrong twice first.** Two plan
revisions were rejected for inventing a ranking — v1 scored evening hours as calm, v2
scored winter evenings as bad — each time moving the invention rather than removing it.
The rule that settled it: **name an hour only when a sentence can be pointed at, and say
what that sentence actually says.** The difference between honest and invented turned out
to live entirely in the copy, not the selection:

- *"6 PM is the calmest hour left"* — ranks hours nothing ranks. Forbidden.
- *"After about 6 PM the afternoon peak is past"* — the shipped clause, read as an
  exclusion. Allowed.

A first ruling suppressed tier-2 spans outright, which was honest and cost too much: the
app named no hour for 15 of 24 ozone hours and 12 of 24 default-driver hours, always
running to midnight, while `PRODUCT.md` promises "and if not, **when**?". Correcting the
copy instead of suppressing the span recovered most of it:

| driver | named before | named after | first silent hour |
|---|---|---|---|
| traffic gases | 18/24 | **22/24** | 22:00 |
| particulates, other seasons | 12/24 | **18/24** | 18:00 |
| ozone | 9/24 | **18/24** | 18:00 |
| winter particulates | 16/24 | 16/24 | 16:00 |

**Residual: 22 of 96 driver-hours (23%) name no time** — late evening on three drivers,
and from 16:00 in winter, where no cited stretch remains to define an edge. Those hours
say the remaining time is alike and give the lever. That is the honest floor, not a gap
to be closed by ranking.

A guard refuses "calmest", "cleanest", "best time", "least bad", "safest" and
`सबसे शांत` / `सबसे साफ़` / `सबसे कम ख़राब` / `सबसे अच्छा` / `सबसे बेहतर` in either
language, with a partner proving it fires. The whole feature's honesty rests on wording,
so the wording is tested.

**R2 discharged in part, and the gap named.** `best_window`'s output reaches the model at
`llm.py` and the rule-based fallback. Moving the severity tail out of `rationale` would
have silently stripped "wear an N95" from both — 128 occurrences in the captured baseline
— because `rationale` had become its only carrier. Both sites now append `note`. The
paid-model path stays untestable: `presenters.answer_sections` drops the window section
deliberately, so no rendered surface reflects it.

**One pre-registered test changed and it should be read as a cost.**
`test_the_same_hour_with_a_normal_reading_does_name_one` froze 06/12/17/23 before any
ranking existed. 12 and 17 name a clock time again; **23 does not** and cannot, so a
partner covers that hour by proving normal air still gets a different answer from severe
air and from a missing reading, with the lever, where those get none. The absence tests
still cannot be satisfied by an empty implementation.

---

#### 1b. Copy: orientation, advice, and the one honest number (~1.5 days)

The current strings, verified in `saafsaans/services/i18n.py`:

- `band_advice.High` — "Don't exercise outside. Keep going out to a minimum…"
- `band_advice.Very High` — "Stay indoors if you can…"
- `band_advice.Extreme` — "Don't go outside."
- `window_none` — "There is no safe time to be outside today; stay indoors…"

Three of five advice bands lead with a prohibition, and the worst-case window leaves a
person with a school run holding nothing.

**Correction, 2026-08-31 — two of these targets are the wrong objects.**

`risk._HEADLINE` is rendered **nowhere**. No template references it; it exists only in
`compute_risk()`'s return contract. The headline a reader meets is a third five-string set,
`presenters._VERDICTS` (`presenters.py:39-45`), which carries *"Don't go out unless you must
— this air is dangerous for you."* If the goal is that no prohibition-leading sentence
reaches a reader, `_VERDICTS` is the set that matters, and it is in neither item 1 nor the
`test_health_claims.py` corpus.

The `window_none` quoted below is `llm.py:476-479`, reachable only when `best_window` is
falsy — and `forecast.best_window()` always returns a non-empty `window`, so that branch is
**dead on the live path** and no test covers it. The live string is `forecast`'s
`window/none` (`i18n.py:1067`).

Item 1 must also be authored together with Gate 1a's `window.note`: `.hero-advice` and
`.hero-window .lever` already say "keep it short" and "wear an N95" in the same hero, gated
on different variables, so rewriting one alone produces a third phrasing of the same advice.

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
11. **Checked 2026-08-31: latent, not live.** `inhalation_ratio` does fall back to sedentary
    for any unrecognised key, and the understatement is large — `("child", "outdoor exercise")`
    returns 1.14 where `("child", "outdoor_exercise")` returns 10.0. But no caller passes a
    spaced string: `main.py` routes every activity through `normalize.norm_activity()`, which
    maps the UI's `"School run"` to `"school_run"` before it reaches `risk.py`. There is one
    production path in and it is pre-normalised.

    So this is not a defect to repair; it is a hazard for the code **item 9 is about to
    write**. A new call site with a hardcoded `"school run"` is exactly how it becomes live.
    Make the fallback loud at that boundary, and keep `tests/test_risk.py:218`, which
    exercises the fallback deliberately and asserts it returns 1.0.

#### 1d note carried from Gate 0.5

**Superseded by b1-telemetry-sqlite.** There is no `viewport-bands` index any more, so
`setup_indices.py` has nothing to add for the probe. What that deploy must do instead:
create the Fly volume BEFORE deploying (`flyctl volumes create saafsaans_data --app
saafsaans --region sin --size 1`), then confirm `/data` is owned by uid 1000 and that the
System view shows a non-zero band count. That count is still Gate 0.5's deferred exit
criterion, and it is now the first time this telemetry will have recorded anything at all.

#### 1c. The uneven cards (~2 hours)

**Measured** (Chrome 151 headless, persona applied): the row is full — no dead track
— `532px 532px` at 1120–1600px. The persona card is **309px** tall against the
reading card's **360px**: a **51px** ragged foot, narrowing to 13px at 900px.

**Re-measured after 1b-surface landed, 2026-08-31: unchanged.** 309 vs 360 at 1120
and 366 vs 401 at 900, in both languages — identical to the figures above. 1b added
a line to the persona card, but inside the `persona_open` branch, so the card in the
state this item measures does not move. The two figures below it still hold. Cause is
`align-items: start` on `.grid` (`app.css:208`), which is deliberate and correct —
stretching would inflate a card with meaningless empty padding.

~~**Note from Gate 0.5:** the System observability grid now holds three cards~~ —
**wrong when written, corrected 2026-08-31.** The viewport card is `class="card wide"`
(`system.html:96`), made wide in `6416b42` — the same commit that introduced it, the same day
this note was written, with a comment measuring exactly the three-track problem the note
predicts. The Observability grid lays **two** narrow tracks, not three. Card-alignment work
inherits a two-card match, the same shape as Today's.

**Action items**

1. Fix the asymmetry **at the source, not by stretching**: the reading card is taller
   because it carries the CPCB scale bar *and* the WHO comparison line. Move one below the
   pair, so the two cards land within ~10px naturally.
2. Do **not** set `align-items: stretch` (`app.css:216` — this line was recorded as 208 and
   has moved). Put the reason in the CSS while you are there: the argument for `start` over
   `stretch` exists only in this document, and anyone reading the stylesheet cold has none.
3. Repair the tests that pin card structure; add one that pins the new placement.

**Correction, 2026-08-31 — the row this fix moves into does not exist.** Item 1 said "the
full-width caveat row that already sits below". The only `.caveat.wide` on the page is
`today.html:342`, gated `{% if not outlook and has_reading %}` — it renders only when the
five-day outlook is **absent**, and disappears the moment the outlook is present, which is
the state the 51px measurement was taken in. The `.caveat.wide` *convention* exists and works;
the row does not. Whoever implements this creates one, or makes that conditional row
unconditional. Only one test is genuinely fragile: `tests/test_declutter.py:379-380` pins the
literal `'<p class="caveat">{{ who_line }}'`, so changing that class attribute breaks it. The
`.scale`, `.scale-mark` and remaining `who_line` tests search the whole body and survive a
relocation — but if `.scale-mark` leaves the `aria-hidden` `.scale-wrap`, its own
`aria-hidden` must travel with it.

**And nothing here measures a rendered height yet.** `tests/test_viewport_browser.py` has the
plumbing — real uvicorn server, real headless Chrome, a CDP session,
`Emulation.setDeviceMetricsOverride` — but no code in this repo calls `Runtime.evaluate` or
reads `getBoundingClientRect()`. The exit criterion below cannot be met without adding that.

---

**BUILT AND MEASURED, 2026-08-31 — and the remedy above is refuted. Read this before
acting on anything above it.**

The height measurement now exists (`_Devtools.call`/`evaluate` and two guards in
`tests/test_viewport_browser.py`). The first thing it did was contradict the item that
asked for it. Every figure below is Chrome 151, persona applied, live reading, no
five-day outlook — `grid-duo`, the state a CPCB reading produces and so almost every
reader's. Signed **reading minus persona**, so the sign says which card ends lower.

Keyed by TRACK width, not by viewport: two viewports that lay the same track render the
same cards. Thirteen distinct tracks, sampled at fifteen viewports; the band lays more
between them, and the sweep does not claim to have seen every one.

| track | viewport | persona en | reading en | en | persona hi | reading hi | hi |
|---|---|---|---|---|---|---|---|
| 332px | 720 | 455.8 | 440.7 | **−15.2** | 513.2 | 397.8 | **−115.5** |
| 352px | 760 | 455.8 | 418.2 | −37.6 | 468.7 | 397.8 | −70.9 |
| 372px | 800 | 455.8 | 418.2 | −37.6 | 468.7 | 397.8 | −70.9 |
| 392px | 840 | 418.3 | 418.2 | −0.1 | 435.3 | 397.8 | −37.6 |
| 412px | 880 | 387.3 | 401.2 | +13.9 | 397.9 | 375.3 | −22.6 |
| 422px | 900 | 366.4 | 401.2 | +34.8 | 375.4 | 375.3 | **−0.1** |
| 442px | 940 | 349.8 | 382.4 | +32.6 | 375.4 | 375.3 | −0.1 |
| 452px | 960 | 349.8 | 359.9 | +10.1 | 353.1 | 375.3 | +22.1 |
| 462px | 980 | 327.4 | 359.9 | +32.6 | 353.1 | 375.3 | +22.1 |
| 472px | 1000 | 308.6 | 359.9 | +51.3 | 353.1 | 342.9 | **−10.2** |
| 482px | 1020 | 308.6 | 359.9 | +51.3 | 330.9 | 342.9 | +12.1 |
| 502px | 1060 | 308.6 | 359.9 | +51.3 | 330.9 | 342.9 | +12.1 |
| 532px | 1120–1600 | 308.6 | 359.9 | **+51.3** | 297.5 | 342.9 | **+45.4** |

The foot does not cross once and settle. English crosses between 392px and 412px; Hindi
crosses between 442px and 452px, crosses BACK to −10.2 at 472px, and returns positive at
482px. Any claim about this curve from two samples is a guess.

**Three claims above are wrong.**

1. **"narrowing to 13px at 900px" is refuted.** Measured +34.8 (en) and −0.1 (hi) at
   900px, in four states and both languages. This section already contradicted itself four
   lines later with "366 vs 401 at 900" — that figure (34.8) is the true one. A ~13px foot
   does exist, at 880px in English (+13.9); it is not at 900px and not in Hindi.
2. **"in both languages — identical" is false.** 309/360 English against 297/343 Hindi at
   1120; at 900 the two languages differ by 35px of foot.
3. **"the row this fix moves into does not exist" is backwards.** `532px 532px` is
   `grid-duo`, which the template emits only at `narrow_cards == 2`. That is reachable two
   ways: persona closed with no outlook, and persona editor OPEN with an outlook present —
   but in the second the persona card is itself `wide` (rendered and checked), so it cannot
   be the 309-vs-360 narrow pair. The measured state is therefore the first, and
   `{% if not outlook and has_reading %}` renders there. The wide row exists precisely
   where the fix was said to have nowhere to go. (The literal `tests/test_declutter.py`
   pins, and a second at `:393` matching `class="caveat">` on the rendered body, are real.)

**The remedy itself does not survive measurement.** Action item 1 reads the 1120px end
alone, concludes the reading card is the taller one, and prescribes moving a block out of
it. Across the band the persona card sheds 147px (en) and 216px (hi) between 332px and
532px tracks while the reading card sheds 81px and 55px, so **the two heights cross** —
near 840px in English, 940px in Hindi — and the foot changes sign. A block moved out of
the reading card is a constant subtraction that shifts the whole curve down: it fixes the
1120px end and drives everything below it further apart. Measured both ways, by removing
the WHO comparison line from the live DOM at every layout in the band:

| | distinct tracks improved | mean foot | worst foot |
|---|---|---|---|
| English | 7 of 13 | 32.3px → 39.4px | 51.3px → **101.9px** |
| Hindi | **1 of 13** | 34.0px → **69.0px** | 115.5px → **168.0px** |

Moving the CPCB scale bar instead has the same shape and a worse landing. It is a
constant 58.05px (en) / 60.38px (hi) at every one of the thirteen tracks — it never
rewraps — so it is the same constant subtraction, and at 1120px it overshoots to −15.0px
in Hindi, outside the ~10px this item asks for and outside the ~15px its exit criterion
asked for.

**One claim made in the first draft of this section is withdrawn.** It said the moved
scale bar puts 1px of horizontal document overflow on the page at 320/360/375/414px, an
SC 1.4.10 failure. That came from one reviewing lens and was written down without being
re-measured. A second lens then tried six constructions — a real template patch and four
live-DOM moves, two languages, two AQIs, four widths, 112 cells — and read
`scrollWidth - clientWidth == 0` every time. **Treat it as unsupported.** The refusal does
not rest on it; the constant-subtraction argument above stands on its own.

**So no content move was made.** Constraint (h) settles it on its own: Hindi improves in
one layout of twelve and its worst foot rises by 52px. There is no single block whose
height rises with track width, which is what a correction to this curve would have to be,
so this is not a matter of choosing a different block.

**What shipped instead**

1. The measurement, as two guards rather than a one-off number.
   `test_no_card_in_the_today_grid_is_padded_out_to_its_neighbour` forces `align-self:
   start` on each card and compares — it refuses a card sized by its neighbour, and turns
   red on `align-items: stretch` at five of its eight cells, naming the 115.47px of empty
   surface that would buy. Not all eight: at 900px in Hindi the two cards already agree to
   0.11px, so stretch has nothing to add there. It also refuses `min-height` on the cards,
   which levels the feet by the same means and went undetected until a reviewer mutated
   it in. `test_the_ragged_foot_..._is_no_worse_than_measured` is a
   ratchet, not a pin: it holds each measured foot plus 26px of headroom (one wrapped
   `.caveat` line is 18.75px English, 22.27px Devanagari), so it refuses a change that
   spreads the pair and stays green for one that closes them. Pinning the foot instead
   would be a check that goes red when the defect is fixed.
2. The reason for `start` over `stretch`, in `app.css`, with the measurement in it.

**Hosted parity cost two things the local run could not have told us**, both found by the
guards failing loudly on the first CI run rather than by reasoning:

- **The runner lays a different page at the same width.** macOS draws overlay scrollbars;
  Ubuntu draws a classic one 15px wide inside the layout viewport, and
  `Emulation.setDeviceMetricsOverride` does not sit above it. A 720px window is 680px of
  content here and 665px there — and at 665px `.grid-duo`'s 330px floor beats `50% - 8px`,
  so the row falls to a single 665px column. The same stylesheet, a different layout, and a
  card height that means something different on each machine. `--hide-scrollbars` makes the
  two agree. Any future browser-measured test in this repo needs that flag.
- **Two `@font-face` rules are expected to fail on Linux.** `fonts.css` gives each
  metric-matched fallback `src: local("Arial")` or `local("Courier New")`, so the runner
  reported `['IBM Plex Sans Fallback', 'IBM Plex Mono Fallback']` in `error` while every
  self-hosted woff2 had loaded. Whether a machine has Arial is not a fact about this
  deploy, so the face check exempts them by name.

**What is still open.** The ragged foot is real and is NOT fixed. Within the two-card row
this item is about, it is worst at **115px, at 720px, in Hindi** — more than double the
51px this item was written about, in the direction nobody looked. Scope that to
`grid-duo`: with the outlook present the row holds three cards and the spread across it is
**220px (en) / 223px (hi)** at 1120px, set by the persona card against the outlook card,
and nothing here addresses it. It cannot be closed by moving one block; closing it means the two
cards carrying comparable amounts of content, which is a copy and information-architecture
change to the persona card, not a layout tweak. That is Gate 2/4 work and it needs the
owner's call on whether an uneven foot is worth spending copy on at all.

**Exit criteria**

- [ ] At 06:00, 12:00, 17:00 and 23:00 IST the named window is never in the past, always
      carries its day, and always offers a today option with its risk stated.
- [ ] The clock-freezing fixture exists and bites: the pre-fix code goes RED at 17:00.
- [x] No `band_advice` or `headline` string is prohibition-only, in either language. Gate 1b widened this to `presenters._VERDICTS` as well — the set a reader actually meets — and made it executable: `tests/test_i18n.py::test_no_band_keyed_sentence_opens_with_a_prohibition`, over all fifteen band-keyed sentences in both languages, with a partner that proves the rule fires on the four it replaced.
- [x] `window_none` names a lever, and deliberately names **no** hour. Amended by Gate 1b, 2026-08-31. "A least-bad hour" cannot be delivered: Gate 1a's floor forbids naming an hour on the severe and no-reading branches at all, and "least bad" is itself one of the ten superlatives `tests/test_window_at_the_hour.py` bans, in both languages. The reader's actual problem — a refusal and nothing else — is fixed by the lever. `window/none` ("No safe outdoor window today") is left as it stands: it is accurate, and with a lever beside it it is no longer empty-handed.
- [x] Every new sentence checked against the evidence checklist; the check is recorded in the Gate 1b pull request, per sentence, per language, with the D-item that licenses it. `tests/test_health_claims.py` sweeps all of it mechanically (corpus 640 strings).
- [x] **A real browser measures a rendered card height, and two guards keep it honest.**
      *(Written by this gate for itself, replacing the criterion below. A gate that can add
      a criterion and tick it in the same commit is weaker than one that cannot; it is
      named here rather than left to be noticed.)*
      `tests/test_viewport_browser.py` now calls `Runtime.evaluate` and reads
      `getBoundingClientRect()` at 720, 900 and 1120px in both languages. Each guard was
      driven RED by a stated mutation: `align-items: stretch` for the padding guard,
      `.meaning`'s top margin for the ratchet, and the refuted remedy itself for the
      premise that the reading card still carries the WHO comparison.
- [ ] ~~Card height delta at 1120px is under ~15px~~ — **NOT MET, and withdrawn as
      written.** It is satisfiable only by a change that measures as a regression: it
      names the one width where the foot is at its worst, so meeting it doubles the worst
      foot across the rest of the band and takes Hindi from 35px mean to 70px. The
      measurement above replaces it. A criterion that survives the evidence would bound
      the foot across the two-column band in both languages, and nothing in this gate's
      scope can meet that one either. Carried to Gate 2/4 with the reason.
- [ ] Full suite green on master; count recorded.

---

### Gate 2 — Correctness debt — **DONE 2026-09-01**

**Goal:** close the three groups where the app is currently wrong or self-contradictory.

**Found during this gate's execution and fixed first, ahead of 2a/2b/2c — scorer
honesty.** Not in the original scope above: at AQI 0 ("Good" air), 10 of 60 persona
combinations scored band "High" (susceptibility points rode on a base that never scaled
down as AQI approached 0), and `compute_risk()` could return `Extreme 89/100` for an
unmeasured reading, with nothing in `risk.py` itself guarding it (decision 0002 — a
sample must never drive severity). Both share one root cause and one fix, in
`saafsaans/services/risk.py`: susceptibility points are now scaled by
`base/AQI_BASE_MAX`, so at AQI 0 the scale is ~0.067 and at unmeasured
(`AQI_BASE_UNKNOWN=50`) it is ~0.667 — same as a known AQI 250, never Extreme. Verified:
AQI-0 max across all 60 personas is now 8 (Low, was up to 47/High); unmeasured max across
the full table is 78 (Very High, never Extreme, was 92). Merged as PR #19
(`5aa616f`), suite 1613 → 1616.

#### 2a. Devanagari Floor, enforced by measurement not by list — **highest** — DONE

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

**Shipped 2026-09-01, PR #21 (`c69d9a0`), suite 1626 → 1632.** All 7 findings verified
live and fixed. `tests/test_devanagari_floor.py` (7 tests, real headless Chrome) replaced
the four hand-maintained selector-list guards; each was re-applied as a mutation and
confirmed the new test catches it. Item 7 (the Latin wordmark losing display tracking on
Hindi pages) was resolved as accepted collateral of the broader reset, with the new test
also protecting the Latin tracking case.

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

**Shipped 2026-09-01, PR #20 (`8c925b8`), suite 1616 → 1626.** Item 1: the one specific
example quoted ("0% stopped pre-model") was already fixed by an earlier gate; two sibling
raw-count tiles were still real and are now fixed. Item 6 (`assert "3" in body`) was
investigated and found not reproducible — the "3" was grounded in real injected data, not
vacuous. All other items (2, 3, 4, 5, 7, 8) verified real and fixed, each with a bite-proof
test. `today.html`'s refusal card no longer claims "audited in security-events" when
`es=none` (production's actual configuration) — the claim is now conditional on
`es.index_answers(client)` actually succeeding.

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

**Shipped 2026-09-01, PR #22 (`7ce1c7b`), suite 1632 → 1641.** All 7 findings verified
real and fixed. Item 1 (the backwards chart): `.col .b:not(.b-nil){min-height:3px}`
guarantees a nonzero bar is never shorter than the 2px `.b-nil` baseline — advisory debt
below. Item 3 (the caret): required two attempts — the first fix caused a new vertical
overlap between the caret and its label, caught by the domain reviewer and by CI running
on Linux Chrome (macOS Chrome had more headroom and didn't show it); reworked to need no
extra height, re-verified clean at AQI 25/168/325/500.

**Exit criteria**

- [x] The Devanagari sweep test exists, is browser-measured, and bites on each of the
      seven cases above. `tests/test_devanagari_floor.py`, PR #21.
- [x] No System surface prints an unqualified zero when nothing was measured. PR #20.
- [x] A zero-count day can never draw taller than a nonzero day. PR #22 —
      `.col .b:not(.b-nil){min-height:3px}`, with a real-Chrome pixel-height test.
- [x] Full suite green on master; count recorded. **1641**, verified independently by
      the main orchestrator by running the suite itself (not from a subagent report).

---

### Gate 3 — Guards that bite — **DONE 2026-09-01**

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

**Shipped 2026-09-01, PR #23 (`df907c1`), suite 1641 → 1641** (guards strengthened in
place; no new tests added). Items 1 and 6 were found already fixed by Gate 2a/2b's work
and verified as such rather than re-fixed. Items 8 and 11 were comment-only defects,
corrected. The remaining 7 (2, 3, 4, 5, 7, 9, 10) were real and fixed. An adversarial
review round found real holes in the first-pass fixes for items 3 (missed a child-
combinator `.scale > span` form), 7 (assumed a border shorthand's first token is always
the width, breaking on `border: solid 1px red`), and 10 (a token-set comparison fooled by
a descendant selector sharing class tokens with a compound selector) — all three closed
in the one allowed fix round and re-verified against the reviewer's exact counterexamples.
Spot-checked independently by the main orchestrator: reintroducing an uppercasing rule
with no `:lang(hi)` reset, and stripping `role="region"` from the Guide's scroll ports,
both correctly failed the strengthened guards.

**Exit criteria**

- [x] Each of the 11 guards demonstrably goes RED under a stated mutation. Confirmed for
      all 11 (2 already-fixed, 2 comment-only, 7 fixed this gate) — see above.
- [x] Full suite green on master; count recorded. **1641**, verified independently.

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
| R8 | Manual deploy drifts from master | 1d | There is no CI. Production sat months behind master until 2026-08-10 and nobody knew | **Superseded 2026-08-31.** `/health` now reports the commit the image was built from, so a deploy is verified by comparing that against `origin/master`. The asset-hash check this row recommended is the *weaker* one: it hashes `app.css` alone, and on 2026-08-31 it reported "parity OK" against an instance nine files behind master, because the release that day changed fonts, `main.py` and a template and touched no CSS. Keep it as a second signal; never as the only one |
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

**From Gate 2c (2026-09-01), advisory, not blocking.** `.col .b:not(.b-nil){min-height:3px}`
fixes the backwards-reading chart (a nonzero day can no longer draw shorter than the zero
baseline) but flattens every very-small nonzero count to the same 3px height — no longer
backwards, but not proportionally distinct either. Accepted as a legibility floor, the same
idea as `.b-nil` itself already was.

**From Gate 3b (2026-09-01), advisory, not blocking.** The new `_resolve_color`/`_border`
helpers (contrast and layout-budget guards) handle hex colours and simple border shorthands
but not `rgb()`/named-color literals or a `border-width`-without-`border-style` form.
Confirmed to fail loud (`ValueError`) on those forms rather than silently passing, so there
is no false-pass risk — just forms not present in the current corpus and therefore untested.

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

**From Gate 1c (2026-08-31), found by measurement and left unfixed.**

· **Two thirds of the scale bar's `aria-hidden` is unguarded.**
`tests/test_web.py::test_the_scale_marker_is_hidden_from_assistive_technology` reads the
`.scale-mark` tag alone. Dropping `aria-hidden` from `.scale` and `.scale-ends` was
mutated in and the whole suite stayed green — a screen reader would then announce a
six-segment severity ramp and the words "0 good … severe 500" as if they described this
reading. Pre-existing; 1c moved nothing, so it neither created nor touched it.
· **The scale block's `{% if is_current %}` guard is protected by a translation
collision, not by a test.** Removing it was caught only by
`test_no_reading_means_no_severity_language_anywhere_on_today[hi]`, tripping on `0 अच्छी`. English passed:
`scale_low` renders lowercase "0 good" while the forbidden list holds the capitalised band
label "Good".
· **"What do these numbers mean? ›" renders twice, 41px apart**, once at the foot of the
reading card and once in the outlook-absent wide row below it, whenever a reading has no
forecast — which is every CPCB reading, so almost every page. Measured at 1120px.
Declutter debt, not an alignment question.

**Responsive:** Hindi pill buttons drop to a 29px target outside both pointer media
queries (clears WCAG 2.1 AA's 24px; misses DESIGN.md's own stated rule).

**i18n:** two Hindi sentences end in a Latin full stop rather than a danda · missing
space before the separator after the PM2.5 unit, which compounds in Hindi.

**Typography:** System KPI labels are set in the body face on the page defined by its
mono register.

**From Gate 1b-surface (2026-08-31), the orientation line, the chip label and the
activity ratio.** Measured in Chrome 151 unless stated.

· **The Gate 4 fold item is now larger on a Hindi first visit, by this much.**
Verdict foot against a 640px fold, first visit: English 414 → 490 at 320 and
375 → 432 at 360, both still above it. Hindi 652 → 709 at 320, which was already
12px past it before the orientation line existed, and 604 → 661 at 360, which
was not. Every persona-applied state is byte-identical to before the change at
320, 360, 900 and 1120 in both languages — that is what the `not persona_applied`
gate buys. The remedy is still the header/banner redesign this document defers
to an owner decision. · **No test sweeps the contrast of small text sitting
directly on the sky.** `test_the_hero_small_text_is_readable_over_every_sky_in_both_themes`
is parametrised on two selectors, both inside `.hero-window`'s 85%-opaque panel.
`.hero-kicker`, `.hero-advice` and now `.hero-gap` sit on the gradient under a
translucent scrim and are measured by nobody. Sampled by hand off the rendered
pixels, worst band (g1, light): `.hero-gap` 8.74:1, `.hero-kicker` 7.39:1,
`.hero-advice` 7.25:1 — all above the 4.5:1 floor. Extending the existing test
naively fails: pairing every sky hex with the scrim's lightest stop reports
`.hero-advice` at 4.20:1, a combination that cannot occur because that hex is the
foot of a 180deg gradient where the scrim is 0.82. The test that would close this
has to interpolate both ramps by vertical position. · **`.hero-gap`'s rule is
reachable but not pinned.** Deleting `.hero-gap { … }` leaves the class in the
markup and the suite green; the line would render at the inherited size.
`test_no_class_in_the_stylesheet_is_unreachable` catches the opposite direction
only. · **Two multiples of one activity render on one Hindi page, on undeclared
baselines.** The driver chip says `कई गुना` (several times, against a sedentary
adult — the table gives 11.9x) and the effort line says `लगभग चार गुना` (about
four times, against a commute). They sit about 1,200px apart in the same card and
neither names its comparand. English is clean: its driver chip carries no figure.
· **The activity ratio is only visible while the editor is open.** After the first
Apply it is gone until the reader reopens "Change details" — which is the moment
the number is about, and is why it sits there, but it does mean the package's one
honest number is not on the resident page. · **`presenters.EFFORT_MULTIPLE` has no
production consumer.** The copy spells the multiple as a word, because only a
literal fourth argument to `i18n.t` reaches the D1–D8 sweep. Its two `rate_for`
calls are what keep `test_no_call_site_hands_either_lookup_a_key_the_tables_lack`
non-vacuous, so removing them reds that test for a cleanup reason rather than for
the hazard it guards. · **That sweep cannot see a key built from a variable, or a
call from a template.** Both limits are stated in its docstring; neither is
reachable today. · **`.hero-gap` takes no `:lang(hi)` line-height** (20.15px, 1.55)
where the Hindi block's pattern is 1.6. Consistent with `.hero-advice`, its
neighbour on the same surface, which also has none. · **The orientation line is the
one sentence a heading-navigator never reaches** — it is the only `page-sub` on the
site placed above its heading rather than below, because Today's only `h1` is the
verdict inside the hero. No SC requires otherwise; the three other views do not
have the problem. · **Hindi reading order above the hero.** base.html renders
`.persona-path` — "set your own age, health and area ›" — 2px above the line that
says why a reader would, and 16px separates that pair from the hero, so the two
read as one block. today.html cannot reorder a base.html block. ·
**`risk.HEURISTIC_NOTICE` under-hedges what the effort line hedges.** It attributes
the exertion term wholly to published EPA rates, while `ACTIVITY_INTENSITY`'s own
comment calls the activity-to-effort mapping "the one judgement inside the
otherwise-grounded dose term". Pre-existing; the new sentence makes it legible by
saying the truer thing two cards above it.

**From the fonts-and-payload change (2026-08-31):** nothing in the suite pins the
metric-matched fallback overrides to the face they were measured from.
`test_fallback_text_is_metric_matched_not_just_a_system_stack` only checks the family
names are present, so a typo in any of the six `size-adjust`/`ascent-override`/
`descent-override` numbers would ship green — and this change moved three of them
(Anek Latin 95.98/93.77/20.84 → 98.18/91.67/20.37, because clipping the weight axis moves
the default instance the measurement is taken at). The check that would settle it is
asserting `build_fonts.fallback_face(family, shipped_file)` reproduces the block in
fonts.css; it is not written because that reads local Arial and Courier New from
`/System/Library/Fonts/Supplemental/`, which CI's `ubuntu-24.04` image does not have, so
it would skip in CI — and a skipped guard proves nothing. Settling it properly needs a
committed metrics fixture for the two fallback faces, or a Linux-available equivalent.
· **`*:lang(en)` in app.css is effectively dead.** Its `--body`/`--mono` redefinitions are
consumed by exactly one element on any Hindi page, `.pat` on the System view, because
every other `lang="en"` element inherits an already-resolved `font-family` rather than
re-resolving the variable. (The `English` toggle does re-resolve it, via `.seg a`, and is
saved only by `:lang(hi) .seg a` hardcoding the Devanagari stack at higher specificity.)
Not a defect today, but it is why gating `fonts.css` by language was rejected: any future
fix that made the rule actually bite would silently strip the Latin faces from every
English island on a Hindi page. · **The size of that prize, stated correctly.** `fonts.css`
is 501 gzipped bytes and is `?v=`-hashed under `max-age=31536000, immutable`, so gating it
saves ~500 bytes **once per reader**, not 843 per page load, and no font bytes at all.
· **`.pat` does not render on production as deployed** — `attempts` comes only from
`metrics.recent_security_events`, which returns `[]` with no Elasticsearch client, and
production has no `ELASTIC_*` secret. The skip still falls the right way: the case is one
`fly secrets set` away and `/system/simulate` exists to populate it, and the local suite
structurally cannot reach the state, so the regression would ship green.

**From Gate 0.5:** the System view now shows a `.caveat` (the Quiet Caveat Rule's one
qualification style) in the viewport card, while two sibling cards on the same page still
use `.caption`. The new card follows DESIGN.md; the two older ones were left alone rather
than restyled inside a telemetry gate. Converting them is a two-line change and closes the
`.caption` item above.

**From Gate 0.5, CLOSED by the SQLite counter swap (b1-telemetry-sqlite).** Three
leftovers were recorded here and all three had the same root cause — one document per page
load in a `viewport-bands` index. Counters removed the cause rather than mitigating it:

- *"No retention policy on any index. `viewport-bands` grows by one document per page load
  for ever."* Closed for this store only. It now holds three counter rows and one date, for
  ever, so there is nothing to expire and no ILM policy to write. **The other four indices
  still have no ILM policy and that item stands.**
- *"A `viewport-bands` document carries a timestamp, so it could in principle be joined by
  time to an `app-telemetry` document that carries a session hash."* Closed. No per-load row
  of any kind survives, so there is nothing to join. A `(day, band)` key was designed,
  reviewed and rejected precisely because it would have left this *reduced* rather than
  closed: on a day whose loads all land in one band — the common case on a scaled-to-zero
  demo — the row still discloses that band for every session hash of that day.
- *"The probe's write is synchronous on the request path (bounded at 1s); moving it to a
  background task would stop a degraded Elasticsearch occupying a threadpool slot per page
  load."* Closed by removing the network call. The write is a local upsert, measured at a
  ~10 µs median, and the 1 s bound is now a SQLite `busy_timeout` reachable only when
  another process holds the write lock.

**New, from the same change (advisory, none blocking):**

- The counter store is not created until the first page load, so a healthy deployment that
  nobody has visited is indistinguishable from a broken one: both read "not being recorded".
  Creating the schema at startup instead would make an absent file mean exactly one thing —
  the store could not be created — and let a genuine measured zero say so. Not done here
  because it changes what the default render says on every page of the suite.
- `PRAGMA wal_checkpoint(TRUNCATE)` at shutdown would leave a suspended machine a clean
  file (measured: 4.12 MB of write-ahead log to 0). It needs FastAPI's `lifespan` API —
  `@app.on_event` is deprecated and adds a warning — and that edit sits in a region of
  `main.py` another lane owns. SQLite's own auto-checkpoint already bounds the log at
  ~4 MB, so this is tidiness, not a leak.
- `ui/sys_empty_no_index` was narrowed in English from "This view reads from a database
  index" to "These panels…", because the viewport card on the same view is no longer one of
  them. The Hindi mirror already says "यह हिस्सा" (this section), which is correctly
  scoped; only its second clause is looser than the English now.

**Copy / states:** a whitespace-only question is accepted and answered with full health
instructions · an answer with no retrieved guidance shows no sources block and no
explanation · with no reading the hero still asserts "No safe outdoor window today"
under a caveat describing a data-driven pattern · the hero window is labelled "IF YOU
MUST GO OUT" even when the verdict says to go out · Guide table headers are
centre-aligned over left-aligned data · the ask chip's accent fill marks a *staged*
question and disappears once it is answered · the selected chip's focus ring is the
same colour as its own fill.

**From Gate 1a (the window at the hour it is read):** an hour is named when a sentence
this module ships calls those hours calm, and a span is also named when a stretch a
sentence calls BAD sits beside it — then the claim is about that stretch ("the afternoon
peak is past by then"), which is a cited exclusion rather than a ranking of hours nobody
ranked. Only where no bad stretch is left in the day is no time named; the reply there is
that the hours are alike and waiting buys nothing, plus the lever.

Driver-hours naming a time, before and after that distinction was drawn:

| driver | first draft | shipped | first silent hour |
|---|---|---|---|
| traffic gases (no2) | 18/24 | **22/24** | 22:00 |
| winter particulates | 16/24 | 16/24 | 16:00 |
| particulates, other seasons | 12/24 | **18/24** | 18:00 |
| ozone | 9/24 | **18/24** | 18:00 |

The residual — a span with no cited stretch beside it, where no time can honestly be named
— is **22 of 96 driver-hours**. An earlier draft of this entry reported the silence as
"three distinct answers at 00–11, two at 12–14, one at 15–23"; that counted distinct
strings across four driver columns, which no reader experiences, and was wrong as that
too. Per driver is the honest form. · **None of the eight `window` rationale strings traces
to `docs/research/2026-07-exposure-evidence.md`** — the file is silent on the diurnal cycle
in both directions. Pre-existing and inherited; the tier table is where a diurnal claim
would land if the evidence file ever gains one. Seven of its eight citations name a daypart
rather than clock hours, so the hour boundaries are a reading of imprecise prose, and the
module comment says so. · `window.rationale` is rendered by no template, so
`window/general_note` survives only in the prompt; the one hedge a reader sees is
`ui/window_note`, and it now captions a value carrying the word "Today" — consider whether
that caption should retract the day as well as the hour. · `_edge_sentence` has copy for
the four (driver, edge) pairs the tier table can currently reach;
`test_every_edge_the_table_can_reach_has_a_sentence_to_state` fails if a citation change
makes a fifth reachable. · Owner's rule 5's second clause is Gate 1b's `window_none` item,
and 1b will have to change `test_severe_air_names_no_hour_whatever_the_time`. · `at_ist`
freezes the clock only in the tests that call `best_window` directly; suite-wide is the
follow-up. · `tests/test_hindi_completeness.py` never freezes the clock and its `LATIN_RUN`
needs three characters, so a bare `AM`/`PM` leaking into Hindi would not match; the literal
hero-bar pins cover that today. · `forecast.py` carries an unused `import datetime` that
predates this change.

**From Gate 1b — the advice copy (2026-08-31).** Six lenses ran; nothing below reproduced
as a blocker, and each is recorded rather than fixed because the fix belongs to another
package or another kind of change.

· **Band `High` is reachable at AQI 0.** `compute_risk(0, "copd", "school_run", "child")`
returns `High`, so the persona-keyed advice line says "Move exercise indoors today, and run
a purifier at home if you have one" on a page whose own band meaning reads "Air is clean.
Outdoor activity is fine for everyone." This package moved the *mask* out of that line for
exactly this reason and keyed it to the measurement instead; the purifier and the
relocation are still keyed to the score. The remaining disagreement is the SCORER's floor
(`AQI_BASE_PTS` plus the condition and activity weights), not the copy's, and changing
weights is Gate 2/4 work.
· **The state of maximum uncertainty is now the strictest surface.** With no reading every
reader is told to wear an N95; at a measured AQI 120 they are told to *consider* one. That
is deliberate — an unknown reading must never be friendlier than a known bad one — but it
is the one place where more data buys weaker protection.
· **`llm.py`'s `answer/window_none` branch is dead on the live path and was left.**
`forecast.best_window()` returns a non-empty `window` on every branch (3,400,704 calls
swept: zero falsy), and `main.py:879` is the only production caller. The `elif` is
unreachable there. It is NOT unreferenced: `tests/test_llm.py` calls `_rule_based` with the
`best_window=None` default and takes that arm, and `test_i18n.py`'s corpus test requires the
Hindi key while the call site stands. Deleting it means deleting a guard on a public helper
plus three test cases plus `i18n.py`'s key, in one commit, for no change in behaviour.
· **Above AQI 300 the answer card's raw markdown states the band twice.**
`llm.py:468-475` concatenates `window + rationale + note`, and `window/none_rationale` and
`window/note_severe` both name the Very Poor-to-Severe range and both say to keep a trip
short. `presenters.answer_sections` drops the whole window block, so no reader sees it; it
reaches the model prompt. The fix is to stop assembling `rationale` into that section, which
is a change to the answer path, not to copy.
· **`BAND_ADVICE` is reused verbatim as the answer card's Verdict sentence** (`llm.py:387`)
whenever the persona band beats the AQI ladder, so a school-run question can be answered
with "Move exercise indoors today". `llm.py`'s own comment rejects giving the card a third
sentence of its own ("a third verdict to keep in sync"); resolving it needs a decision about
that surface, not a reword.
· **The prohibition rule is "opens with", by design.** A prohibition moved into the second
sentence is not caught, and the test says so in its name and its docstring. Widening it to
whole sentences needs a way to tell "do not exercise outdoors" from "keep any trip short"
that a word list does not have.
· **The no-reading lever is guarded against severity by two word lists**, the six CPCB band
labels and six severity adjectives read off shipped copy. A sentence that invents a new way
to assert severity is not caught. Stated in the test.
· **Hindi, unverified.** No Hindi speaker has read any of the eighteen new strings; the
banner stays. Three items a reviewer flagged and this package did not resolve:
`headline/Moderate`'s "आराम बरतें" (बरतना collocates with सावधानी, not आराम) is a
pre-existing house phrase that also ships in `aqi_meaning/Moderate`, so fixing it here alone
would make one page disagree with itself — it needs a corpus-wide pass;
`band_advice/Moderate`'s "उतनी ही आसानी से" has no stated comparand; and the Hindi is
slightly stricter than the English at `band_advice/Moderate` and `window/note_severe`
(stricter, never looser — checked in every cell).
· **Layout, measured in Chrome 151 and left to Gate 1c.** The copy is longer, so the hero
grew: at 1120px the window block goes from one row to two wherever a lever appeared
(`.hero-window` +30 to +34px), and at 390px Hindi the hero grows +85px. Nothing overflows and
nothing scrolls horizontally at 320/360/390/768/1120. Two inherited items surfaced with it:
`h1.verdict` has `line-height: 1.08` and no `:lang(hi)` override, so Devanagari lines have no
zero-ink row between them (the Hindi verdict now sets to three lines where it set to two, so
one collision seam becomes two); and `.hero-advice` runs the full 676px column, a ~90ch
measure against the craft floor's 65-75ch. Both are container properties this change did not
touch.

· **`llm._rule_based` still emits the mask off the composite band.** At AQI 0 with a
COPD child on a school run the hero is now clean, but the answer card — which a reader
sees only after asking a question — still prints "Wear a well-fitted N95/FFP2 mask
outdoors" because `precaution_mask_high` is gated on the VERDICT token, and the band
ladder raises that to NO-GO off the same composite score this package moved the mask away
from. Pre-existing and unchanged here; the fix is to gate that precaution on the AQI the
way the lever now is, which is a change to the answer path.
· **Three guards this package hardened are still lexical, and say so.** The lever's
time check is a word list (clock forms, hour ranges, dayparts); the no-reading lever's
severity check is a word list; the hero's duplication check is a six-token marker list per
language. Each is proven to fire on the phrasings that defeated its predecessor and each
names its own limit in its docstring. A synonym nobody listed still gets through. Making
any of them semantic is not a copy change.
· **The prohibition rule is clause-level, not sentence-level.** It asks whether any
clause OPENS with a prohibition. A prohibition buried mid-clause ("Head out but skip the
run") is not caught. Widening it needs a way to tell "do not exercise outdoors" from
"keep any trip short" that a word list does not have.

**Rejected, with reasons — do not resurrect without new evidence:** the
largest-text-is-a-number arithmetic (DESIGN.md prescribes both values) · stripping
26KB of design-rationale comments from `app.css` (needs a build pipeline) · the
systemic spacing-scale drift (pre-existing everywhere; acting on it is a redesign) ·
three performance claims their own authors measured and refuted.
