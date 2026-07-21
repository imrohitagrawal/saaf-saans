# Plan — closing `hindi-2`

The single reconciled plan for the unattended run of 21 July 2026. Four planners were fanned
out over the advisory-relevance fix, the declutter, the Hindi prompt-excerpt decision and the
merge sequence; each plan was then attacked by an independent critic instructed to default to
rejection and to cite `file:line` it had personally read.

**33 objections were raised against the four plans** — 5 of them fatal. Two plans came back
`needs-rework` and two `sound-with-fixes`. Nothing was implemented in that phase. This document
is what survived, with each overturned item recorded rather than quietly dropped.

Baseline pinned at `1207f1f`: **474 tests passing**, `.venv/bin/python -m pytest -q`, ~1s, no network.

---

## 0. What the critics overturned

Recorded because a plan that was corrected before it was built is the only cheap kind of
correction, and because the next reader should be able to see that the review rejected things.

| # | Plan | Objection | Ruling |
|---|---|---|---|
| 1 | merge | The proposed merge commit message says master "already had" a Dockerfile. `git ls-tree master` shows it does not — the Dockerfile arrives *with* this merge. | **Upheld, fatal.** A false claim written into permanent history is precisely the defect class this repository exists to record. Message rewritten from the actual diff. |
| 2 | merge | The message credits the licence and the methodology write-up to "24 commits of closure work". Both are already ancestors of master. | **Upheld.** Message rewritten. |
| 3 | merge | A proposed guard test asserts `app.css` has exactly two `@media` blocks. It has four. | **Upheld.** Test dropped; the real gap it pointed at — `(pointer: coarse)` is invisible to every a11y assertion — is recorded as an open item, not silently fixed. |
| 4 | declutter | `.disclaimer` does not render at 11.5px. `.answer p` (0-1-1) outranks it (0-1-0), so it already renders at 13.5px. The plan's inventory was wrong about the page as it stands. | **Upheld, fatal.** See §2. |
| 5 | declutter | `.caveat` as specified (0-1-0) would lose to `.answer p` and `.refusal p`, shipping a class named caveat that is not styled as one. | **Upheld, fatal.** Fixed by exclusion, not by a specificity war — see §2. |
| 6 | excerpt | The proposed caption "shown exactly as it arrived" is false: `normalize.excerpt` truncates at 120 characters, and the page's own red-team button fires a 1,250-character attack. | **Upheld.** Caption reworded to something true, and a >120-character fixture added so the claim stays checkable. |
| 7 | excerpt | The draft case-study paragraph explains the eleven dead allowlist entries by a mechanism the code does not have. | **Upheld.** The record is written last, from the final diff. |
| 8 | advisory | The contract gives two mutually exclusive answers for what happens when ranking finds nothing applicable. | **Upheld.** Resolved in §1; this is the `nav.today`/`nav_today` failure mode and is settled before any agent is dispatched. |
| 9 | advisory | Nothing re-seeds Elasticsearch, so the "every persona has an applicable advisory" guarantee holds in-process and nowhere else. | **Upheld.** `setup_indices.py` is not idempotent across a corpus change; recorded as a documented deployment step, not silently assumed. |
| 10 | advisory | The proposed CPCB 101–200 row opens "acceptable for most people", which is US EPA's *Moderate* framing, not CPCB's. | **Upheld.** Rewritten to CPCB's own descriptor. Attributing EPA wording to CPCB is the same defect as publishing a US index under Indian band names, which this project already fixed once. |

Overturned in the other direction — objections the critics raised that are **not** being acted on:

- *"The merge lands three tracked `.DS_Store` blobs and `.gitignore` has no entry."* Correct, and
  being fixed — but as its own commit, not folded into a merge.
- *"`README.md:143` says 363 tests."* Correct and being fixed, but it is not an advisory-plan
  concern; it lands in the record pass (§5).
- *"`inhaler` appears in the Hindi corpus in Latin and is not on the completeness allowlist."*
  Correct, and worse than reported: the scan passes only because `inhaler` happens to occur in
  `REVIEW_BANNER_EN`, whose words are folded into `ALLOWED` wholesale. The exemption is real but
  accidental — a reword of the banner would fail an unrelated test. See §1(e).

---

## 1. Advisory relevance

**The bug, reproduced.** `es._in_process_search` filters on the AQI band alone and scores only
positive persona matches, so a contradicting row is returned with score 0 rather than excluded
(`saafsaans/services/es.py:139-146`). Verified independently of the planner:

```
es.search_advisories(450, 'asthma', 'school_run', 'child', client=None)
  -> CPCB any/any/any · WHO-AQG-2021 any/any/senior · EPA stay_home · AHA heart/senior
```

Not one row applies to a child with asthma. A sweep over the whole reachable persona space
(5 conditions × 4 activities × 3 ages × AQI 0–999) finds **10 (persona, band) regions with no
applicable advisory at all**, and above AQI 400 there is no asthma, COPD, pregnancy or child row
in the corpus.

`today.html:202` and `:211` claim answers are "written for your persona". That claim is false
today. It becomes true here, or it goes.

### (a) The contract — settled before dispatch

New in `saafsaans/services/es.py`:

```python
RELEVANCE_PERSONA = "persona"
RELEVANCE_GENERAL = "general"
FETCH_K = 25

def applies_to(advisory: dict, condition: str, activity: str, age_group: str) -> bool: ...
def specificity(advisory: dict, condition: str, activity: str, age_group: str) -> int: ...
def rank_advisories(docs: list, aqi: int, condition: str, activity: str,
                    age_group: str, k: int) -> list: ...
```

- `applies_to` — a field matches when the advisory's value is `"any"` or equals the persona's.
  A persona value of `"any"` matches only advisories whose field is `"any"`: an unstated
  condition does not entitle the reader to asthma advice. Missing keys default to `"any"`,
  because ES documents are external data.
- `specificity` — 0–3, how many of the advisory's non-`"any"` fields name this persona.
- `rank_advisories` — filter by `applies_to`; **if that leaves nothing, return `docs` unchanged**;
  then prefer in-band rows, else the nearest band; sort by specificity descending, stable, take
  `k`; return new dicts via `dict(d, relevance=...)`, never mutating the input.

**The ambiguity the critic caught, resolved: `rank_advisories` never returns empty for a
non-empty input.** `search_advisories` therefore needs no post-rank empty branch; its only
empty case remains ES returning zero hits, which already falls through to the filter-only retry
and then to the in-process path. One rule, stated once.

New key on a *returned* row only: `"relevance": "persona" | "general"`. It is not stored in
`data/advisories.py`, not indexed, and not part of the five-field i18n key.

`build_query` is unchanged.

### (b) The data gap — 9 new rows

Nine rows close all 10 empty regions and give every condition a row at every band above AQI 100.
Sources are bodies already cited in the corpus; text follows what those bodies publish.
The `CPCB-AQI-scale:101-200` row is written in **CPCB's** register — "breathing discomfort to
people with lung disease such as asthma, and discomfort to people with heart disease, children
and older adults" — not EPA's "acceptable for most people".

```
CPCB-AQI-scale   101-200  any/any/any
CPCB-AQI-scale   201-300  any/any/any
GINA-guidance    301-999  asthma/any/any
GOLD-guidance    401-999  copd/any/any
ACOG-airquality  401-999  pregnancy/any/any
AHA-airpollution 301-999  heart/any/any
WHO-children-air 401-999  any/any/child
AHA-airpollution 101-200  heart/any/any
ACOG-airquality  151-200  pregnancy/any/any
```

Corpus goes 34 → 43. Every present-tense "34" in `README.md` and `docs/CASE-STUDY.md` is
updated; the two *historical* mentions of the 34×3=102 duplicate-seeding incident
(`CASE-STUDY.md:85`, `setup_indices.py:80`) are narrative about a past bug and must **not** be
renumbered.

### (c) Hindi for all nine

Key rule, unchanged and exact (`i18n.py:868-884`):

```
f"{a['source']}:{a['aqi_min']}-{a['aqi_max']}:{a['condition']}:{a['activity']}:{a['age_group']}"
```

Written by **one** agent, not two, because the register has to match the existing 34 and health
instructions must carry identical force in both languages — neither softened nor strengthened.

### (d) Where relevance becomes visible

- `llm.build_user_message` — two labelled groups instead of one flat list.
- Provenance panel — two headings, each rendered only when non-empty.
- `ask_sub` / `ask_hint` — rewritten to claims the new tests prove.

Turns already in the in-RAM transcript store carry no `relevance` key and fall into the general
group. The store does not survive a restart, so this is a display detail for one process
lifetime; noted rather than engineered around.

### (e) `inhaler`

Kept in Latin, consistent with the shipped corpus and with the allowlist's own stated principle
("technical terms a Delhi reader says out loud in English"). It is added to `ALLOWED`
**explicitly**, with that reason, because it is currently exempt only by accident — it occurs in
`REVIEW_BANNER_EN`, and every word of that banner is folded into the allowlist wholesale. This
is not editing an allowlist to go green: the suite is already green. It is replacing an
accidental exemption with a stated one, so a future reword of the banner cannot break an
unrelated test.

### (f) Elasticsearch

`setup_indices.py` writes deterministic ids but does not delete rows that have left the corpus.
Adding 9 rows means a connected deployment serves the old 34 until it is re-run. The app ships
with no Elasticsearch, so this affects no current environment — but the guarantee is
in-process-only until re-seeded, and the docstring will say so instead of implying otherwise.

---

## 2. Declutter

The named defect: the WHO line uses `.meaning`, the same weight as the band meaning it sits
under. Every honesty fix added text and none of it was ranked.

**DEMOTION, NOT DELETION.** Nothing leaves the site. Nothing moves to the Guide — every caveat
is demoted in place, and the WHO caveat gains a link to the Guide section that already explains
it, so a demoted line still has a route to its explanation.

### The one quiet style

```css
.caveat { margin: 8px 0 0; font-size: 12.5px; line-height: 1.5; font-weight: 400;
          color: var(--text-3); text-wrap: pretty; }
.caveat a { color: var(--accent); text-decoration: none; }
.caveat.on-tint { color: var(--text-2); }
.hero-window .caveat { font-size: 12px; color: #F5F4F0; opacity: .65; }
```

Collapsing into it on `/`: `.hint` (5 sites), `.caption` (1), `.disclaimer` (1),
`.answered-for` (1), `.refusal .audit` (1, as `.on-tint`), `.hero-window .note` (1), and the WHO
half of `.meaning`. `.hint` and `.caption` survive as classes — they are body prose in
`guide.html`, `city.html` and `system.html`, not caveat styles there.

`.meaning` is left with exactly one job and **promoted**:

```css
.meaning { margin: 14px 0 0; font-size: 14.5px; font-weight: 500; color: var(--text); }
```

### The cascade trap, and the fix

`.caveat` is a single class (0-1-0). `.answer p` (`app.css:224`) and `.refusal p` (`:242`) are
0-1-1 and would beat it on size, colour and margin — shipping a class named caveat that renders
at body weight. The same cascade already means `.disclaimer` never rendered at its declared
11.5px, which is why the original inventory was wrong about the page as it stands.

**Fixed by exclusion, not by escalation:**

```css
.answer  p:not(.caveat) { ... }
.refusal p:not(.caveat) { ... }
```

The competing rule stops applying to the element instead of the two rules fighting. No `!important`,
no compounded selector, no dependence on source order — and the next person to add a caveat inside
a card does not have to know this history.

A test must assert the *resolved* style for every element carrying `.caveat`, not the flat
selector map the existing helpers read. Without it this class of bug recurs.

### Contrast, computed

`--text-3` on `--surface`: **5.47:1** light, **4.61:1** dark. On `--bg`: 5.05 / 5.10.
On `--surface-2` dark it is **4.12:1 — below 4.5** — which is why `.caveat` sets no background
and why `.on-tint` exists (`--text-2`: 6.27 light / 6.14 dark).
`.caveat a` on `--surface`: 6.59 / 7.90. Promoted `.meaning`: 15.92 / 13.22.
Hero caveat composited over all seven skies in both themes: worst case 6.41:1.

### Hindi

`.caveat` joins the existing Devanagari prose floor at 13.5px / 1.65 (`app.css:530-533`) —
12.5px chosen against Latin sits below where matras resolve — plus a hero floor the old `.note`
never had. Face, tracking and case need nothing: `*:lang(hi)` already redirects `--body` and
normalises letter-spacing, and `.caveat` sets no `text-transform`.

### What stays distinct

`.stale-note` is not a qualification of a correct answer — it says the figures on the page are
not a measurement at all. It renders only when the feed failed and must be **noticed**, not
absorbed. Demoting it would be the one demotion that changes what the page claims.

---

## 3. Prompt excerpts in Hindi — the decision

The excerpt on `/system?view=security` is verbatim visitor text of genuinely unknown language.
Today it inherits `lang="hi"` from `<html lang="{{ lang }}">` — an active false claim about text
the app did not write.

**Decision: mark it honestly unknown rather than English.**

```html
<span class="excerpt">"<bdi lang="" translate="no">{{ v.excerpt }}</bdi>"</span>
```

`lang=""` is the HTML spec's *explicitly unknown*, which is what this is — the attacker may have
typed Hindi. `lang="en"` would be a guess stated as a fact, on an audit page whose entire purpose
is showing what is actually in the index. `<bdi>` carries `dir="auto"` and bidi isolation, so an
Arabic or Urdu injection cannot reorder the quote marks around it. `translate="no"` stops an
in-browser translator rewriting evidence. Quote marks stay outside the `<bdi>`; `lang=""` never
goes on `.excerpt` itself, which would break `:lang(hi) .excerpt`.

Hiding it was rejected: an audit view that hides its evidence from one language's readers is not
an audit view. Accepting the mixed page unmarked was rejected because the mixture is not the
problem — the false `lang` is.

**Two findings alongside, both recorded, neither papered over:**

1. The completeness scan has never once seen an excerpt. With no ES client
   `metrics.recent_security_events` returns `[]` and the empty state renders, so the whole
   `attempts` branch — and the excerpt with it — is unreachable in the entire suite. Eleven
   allowlist entries (`blocked`, `jailbreak`, `pretend`, `roleplay`, `password`, …) exist to
   protect strings **that are never emitted on any page**. Verified by rendering all five pages
   × three personas, plus a fired simulation, and diffing against `ALLOWED`. They are removed,
   and the genuinely load-bearing insight in that comment — that `LATIN_RUN` has no underscore
   in its character class, so an entry like `chat_completed` can never be emitted and reads as
   protection while giving none — is **kept**, because that is why the next entry will not be
   written wrongly.
2. The caption must not say the excerpt is shown "exactly as it arrived". `normalize.excerpt`
   truncates at 120 characters and the page's own red-team button fires a 1,250-character
   attack. A fixture longer than 120 characters is added so the wording stays checkable.

Tests to add must be named for what they prove. A test that strips `lang=""` before scanning
proves the wrapper is present, not that the excerpt was read — so it is named for the former, and
a separate test asserts the excerpt renders verbatim (to the cap) in both languages, and a third
bounds the escape: only `<bdi>` may ever carry `lang=""`.

---

## 4. Merge

History is strictly linear — `master ⊂ v1-closure ⊂ hindi-2`, zero divergence either side, both
merges conflict-impossible. `--no-ff` is a history-shaping choice, not a necessity.

Two worktrees hold the branch names hostage: `saaf-saans-stable` holds `master`,
`/private/tmp/saafsaans-v1closure` holds `v1-closure`. A branch checked out elsewhere can be
neither checked out here nor deleted, so both names are freed first.

`space` (`cc541ae`) is built on `v1-closure`, not master, and its one unique commit adds 15 lines
of Hugging Face YAML front matter to `README.md` and nothing else. It is unmerged, so deletion
needs `-D`; it is archived to a patch first. `ui-revamp` is byte-identical to master and tracks a
real `origin/ui-revamp`; deleting it locally is safe and touches nothing remote.

Order: free the names → merge `hindi-2` into `v1-closure` → full suite → merge `v1-closure` into
`master` → full suite → delete `hindi-2`, `v1-closure`, `space`, `ui-revamp`. **Never merge a red
branch. Nothing is pushed.**

Landing on master with the merge and therefore handled first, as their own commits:

- Three tracked `.DS_Store` blobs, with no `.gitignore` entry, which will keep coming back.
- `docs/screenshots/review-hindi2/`, whose own README says it should be deleted at merge time.

Merge messages are written from the actual diff. The overturned draft claimed master already had
a Dockerfile (it does not — the Dockerfile arrives with the merge) and credited master's own tip
commit to the branch being merged.

---

## 5. Record

`docs/CASE-STUDY.md` gains this run: what was done, every kill rate, every judgement call taken
on the owner's behalf, and what remains open. Every figure in §2 is re-verified by re-running the
commands and pinned to a named commit, because the counts move as the work lands.
`README.md` gains the true test count — it currently says 363 against a suite of 474 — and the
corpus count, and its limitations are re-read against what the code now does.

Written **last, from the final diff**, not from planning notes. Two of the draft record's
sentences were already false when the critic read them.

---

## 6. Out of scope, deliberately

The user test with real people (`docs/USER-TEST.md` is written and waiting), Hindi sign-off by a
Hindi speaker, pushing to `origin/master`, and peer review by another developer. The Hindi review
banner stays on every `?lang=hi` page until a fluent speaker has signed the translation off.

Four things this run cannot verify and will not claim: 375px rendering in a real viewport, the
browser tab strip, coarse-pointer touch targets, and anything that requires a person's reaction.
