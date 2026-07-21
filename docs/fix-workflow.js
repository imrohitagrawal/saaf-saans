/**
 * Parallel fix-and-verify for an adversarial review's confirmed findings.
 *
 * Each group owns a DISJOINT set of files and runs in its own git worktree, so
 * no two writers can see each other's half-finished edits. A previous run put
 * five writers in one tree: every one of them reported failures that were
 * another agent's in-flight edit, and one left an uncommitted mutation that
 * silently reverted a committed fix.
 *
 * Each group commits in its worktree and returns the SHA; the caller
 * cherry-picks. Disjoint file sets are what make that conflict-free.
 */
export const meta = {
  name: 'fix-confirmed-findings',
  description: 'Fix reviewed findings in isolated worktrees, then verify each independently',
  phases: [
    { title: 'Fix', detail: 'one writer per disjoint file group, each in its own worktree' },
    { title: 'Verify', detail: 'independent checker re-reads the diff and re-runs the suite' },
  ],
}

// The harness may hand `args` through as a JSON-encoded string; unparsed, every
// property read below is undefined and the run silently does the wrong thing.
let opts = args
if (typeof opts === 'string') {
  try {
    opts = JSON.parse(opts)
  } catch (e) {
    throw new Error(`args was a string but not valid JSON: ${e.message}`)
  }
}
const args_ = opts

const ROOT = '/Users/rohitagrawal/Projects/saaf-saans'

// Shared preamble. Identical text in every prompt so no two agents invent
// different conventions for the same repo rule.
const RULES = `
You are working in the SaafSaans repository, on a git worktree of branch hindi-2.
Run commands from the worktree root you were started in, NOT from ${ROOT}.

HARD RULES (violating any of these fails the task):
- Run the suite with: .venv/bin/python -m pytest -q
  The .venv lives at ${ROOT}/.venv -- use that absolute path if your worktree has none.
- NEVER WEAKEN A TEST TO MAKE IT PASS. If a test blocks you, either the code is
  wrong or the test is wrong; prove which in the commit message. Never edit an
  allowlist to go green.
- Add a test for behaviour you change, and CHECK THAT IT CAN FAIL: break the code
  it covers, watch it go red, restore, watch it go green. A test that cannot fail
  is worse than none. This run has already found two.
- NEVER CLAIM WHAT THE CODE DOES NOT DO. Any factual claim in prose needs a test
  or a citation beside it. An unsupportable claim is REMOVED, not softened.
- ZERO JAVASCRIPT. No <script> tag, ever. The app is server-rendered Jinja2.
- NO EMOJI as icons. Comments explain non-obvious DECISIONS only; docstrings
  state contracts. No co-author trailers.
- Any local server MUST neutralise credentials by setting them EMPTY, not unset
  (services/config calls load_dotenv() at import, which refills an UNSET name):
    env OPENROUTER_API_KEY= WAQI_TOKEN= ELASTIC_URL= ELASTIC_API_KEY= ELASTIC_CLOUD_ID= <cmd>
  Confirm /health reports {"es":"none","waqi":false,"llm":false} before trusting it.
- DO NOT push, do not merge, do not touch any branch but the one you are on.

WHEN DONE: commit your work in the worktree with a multi-line message explaining
WHY, run the FULL suite one last time, and return the commit SHA plus the test
count. If you conclude a finding is NOT a real defect, do not fix it -- say so
and give the evidence. Reporting a finding as bogus is a perfectly good outcome.
`

const GROUPS = [
  {
    key: 'template-marker',
    files: 'saafsaans/web/templates/today.html and its tests',
    prompt: `Two confirmed review findings, both on the AQI scale marker at
saafsaans/web/templates/today.html:139.

(a) [high, correctness] When the reading has no usable particulate, the marker
    prints the literal string "None ▾" -- the word None, from Python -- while the
    headline number two lines above correctly renders "--". Reproduce it first:
    the deployed configuration has no WAQI token, so a locality with no stored
    sample takes this path. Use fastapi TestClient.
(b) [medium, a11y] The same marker leaks its decorative ▾ glyph to assistive
    technology, while the two lines around it handle that correctly.

Decide the honest fix. Note that printing "--" still parks the marker at the
Good end of the scale, which asserts a position the reading does not have, so
hiding the marker entirely when there is no AQI is likely more truthful than
printing a placeholder -- but verify how the surrounding markup and the
aria-hidden decoration behave before choosing.`,
  },
  {
    key: 'css-a11y',
    files: 'saafsaans/web/static/app.css and tests/test_a11y.py',
    prompt: `Four confirmed a11y/dead-code findings in saafsaans/web/static/app.css.
You also own tests/test_a11y.py. Verify EVERY claim against the actual file
before changing anything; compute the arithmetic yourself and show it.

(a) [high, app.css:544] Every pill/button target on coarse pointers is said to
    fall below the 44px floor the stylesheet claims to enforce, because
    line-height:1.2 at :539-544 overrides the body's 1.55 that the coarse-pointer
    padding at :462-471 was sized against. tests/test_a11y.py computes the height
    with a hardcoded BODY_LINE_HEIGHT and so never sees it. If this is real, fix
    BOTH: make the test read the declared line-height instead of assuming, and
    raise the padding to clear 44px. Check that every @media (pointer:fine)
    counterpart stays strictly shorter so the existing
    test_pointer_fine_only_ever_reduces_a_target still passes.
(b) [high, app.css:639] The persona toggle on the HINDI page at a coarse pointer
    is ~39px, because a Devanagari optical correction subtracts padding from the
    floor. Keep the optical shift, preserve the total.
(c) [high, app.css:116 and :372] Inline links inside .caveat and .hint are
    distinguished from surrounding text by colour alone, at roughly 1.21:1
    (light) and 1.71:1 (dark) against the body text -- far under the 3:1 that
    colour-only link identification requires. Both rules strip the underline the
    base 'a' rule already supplies with a tuned offset. Recompute the ratios
    from the real token values before accepting this.
(d) [medium, app.css:124] The sticky header hides whatever keyboard focus and
    in-page anchors land on; there is no scroll-padding anywhere.
(e) [low/medium, dead CSS] .ask-cols, .ask-main and .ask-side (:249) styled a
    two-column Ask layout deleted from today.html; .muted (:93) is unreferenced
    since the Streamlit-era templates. Grep the WHOLE tree (templates, python,
    docs) before deleting, and paste the grep as proof.

NOTE ON SCOPE: a real viewport and a coarse pointer are NOT available here and
anything needing them is unverifiable -- but these findings are static
arithmetic over declared CSS values, which IS verifiable. Do the arithmetic; do
not claim to have observed a rendered page.`,
  },
  {
    key: 'stale-comments',
    files: 'saafsaans/services/i18n.py (comments only) and tests/test_hindi_completeness.py (comments only)',
    prompt: `Four confirmed dead-code findings, all of them COMMENTS that describe
behaviour the code no longer has. The repository's rule is that an unsupportable
claim is removed, not softened. Change comments and docstrings only -- do NOT
change any translation string, any key, or any assertion.

(a) [i18n.py:290] An orphaned comment block explains the stale_before/stale_after
    translation keys, which were deleted in commit bdb9722. It now sits above a
    blank line describing keys that do not exist.
(b) [i18n.py:211] A comment points readers at a test named
    test_ui_and_guide_carry_the_keys_the_templates_request which does not exist.
    Find what the test is ACTUALLY called now (grep tests/) and cite that, or
    drop the citation if nothing covers it -- do not invent a name.
(c) [tests/test_hindi_completeness.py:99] The ALLOWED-list comment says "action
    plan" is left untranslated in the Hindi asthma advisory. That gap was closed;
    the Hindi now reads "डॉक्टर की लिखी हुई हिदायतें". Verify, then correct the
    comment. If the ALLOWED entry itself is now protecting a string that is never
    emitted, REMOVE the entry -- a previous run found eleven such entries.
(d) [tests/test_hindi_completeness.py:92] Every line-number citation in the
    ALLOWED-list comments is stale; the referenced lines hold unrelated text.
    Either re-pin them to the correct lines or replace line numbers with
    something that does not rot (a quoted fragment, a key name). Prefer the
    latter -- you are fixing this class of bug, not renewing it.`,
  },
  {
    key: 'verdict-and-llm-tests',
    files: 'saafsaans/services/llm.py and tests/test_llm.py',
    prompt: `Three confirmed findings.

(a) [medium, correctness, llm.py:336] _verdict returns early for an unknown AQI
    without consulting the persona risk band, so the answer card can be MORE
    PERMISSIVE than the hero above it -- the exact invariant the function's own
    docstring says it maintains. Reproduce with a concrete persona and an unknown
    AQI, show the two strings disagreeing, then fix so the docstring is true.
    This is an honesty bug: the app must never tell a COPD patient the air is
    fine in one panel and unsafe in another.
(b) [high, tests/test_llm.py:110] test_system_prompt_fixed_and_user_text_not_in_it
    CANNOT FAIL on the property its name promises. This is the highest-value item
    in your group. PROVE it toothless first -- mutate the code so the user's text
    DOES leak into the system prompt and show the test still passing, and paste
    that output. Then rewrite it so the same mutation turns it red, and show
    that. Do not delete the test.
(c) [medium, tests/test_llm.py:134] The documented LLM 30s timeout is enforced by
    no test, because the stub swallows kwargs. Make the stub assert the timeout
    it was called with.`,
  },
  {
    key: 'time-zones',
    files: 'saafsaans/services/forecast.py and saafsaans/seed_demo_history.py',
    prompt: `Two confirmed findings, both the same root cause: server-local time
standing in for India Standard Time. The shipped container runs UTC; the readers
are all in Delhi.

(a) [medium, forecast.py:173] best_window decides Delhi's winter season from
    datetime.date.today() instead of IST, so the season flips 5.5 hours late at
    every month boundary.
(b) [low, seed_demo_history.py:60] The demo diurnal curve is computed from the
    UTC hour, so the seeded "worse at night / early morning" peak lands at
    11:30 AM IST -- the time of day the docstring says is cleanest.

Check whether the repo ALREADY has an IST helper before writing another one
(grep for tzinfo, timezone, IST, Asia/Kolkata, +05:30). If it does, use it; two
independent notions of "now" is how this class of bug spreads. Add a test that
pins the boundary rather than one that passes whenever it happens to be run --
freeze the clock.`,
  },
  {
    key: 'fallbacks-and-labels',
    files: 'saafsaans/web/main.py, saafsaans/web/presenters.py, saafsaans/services/risk.py',
    prompt: `Three confirmed findings in three different files.

(a) [low, correctness, main.py:630] City Pulse falls back to the labelled sample
    only when there is NO stored row, not when the stored row's aqi is None, so a
    locality renders "--"/Unknown even though a sample figure exists. Reproduce
    with a stored row carrying aqi=None.
(b) [medium, a11y, presenters.py:376] The one accessible name on the site that
    carries data is hardcoded English and is neither translated nor marked
    lang="en", so on the Hindi City Pulse page a screen reader announces English
    words with Devanagari phonetics. Decide between translating it (preferred --
    the repo is bilingual and i18n.py is the one corpus) and marking it lang="en".
    If you translate, put the string in i18n.py with BOTH languages, and check
    whether tests/test_hindi_completeness.py needs to know about it.
(c) [medium, dead-code, risk.py:69] EPA_AGE_BANDS is dead production data --
    nothing renders it, and the Guide table showing EPA age brackets carries its
    own independent copy of the three strings. Grep the whole tree before
    deleting and paste the grep as proof. If it IS dead, deleting it leaves the
    Guide's copy as the single source; confirm that is so rather than assuming.`,
  },
]

const groups = GROUPS.filter(g => !(args_ && args_.only) || args_.only.includes(g.key))

const RESULT = {
  type: 'object',
  properties: {
    sha: { type: 'string', description: 'commit SHA in the worktree, or empty if nothing was changed' },
    worktree: { type: 'string', description: 'absolute path of the worktree you worked in' },
    tests: { type: 'number', description: 'passing test count after your change' },
    fixed: { type: 'array', items: { type: 'string' }, description: 'findings you fixed, one line each' },
    rejected: { type: 'array', items: { type: 'string' }, description: 'findings you judged NOT real, with evidence' },
    notes: { type: 'string' },
  },
  required: ['sha', 'worktree', 'tests', 'fixed', 'rejected'],
}

const CHECK = {
  type: 'object',
  properties: {
    sound: { type: 'boolean' },
    problems: { type: 'array', items: { type: 'string' } },
    toothlessTests: { type: 'array', items: { type: 'string' } },
  },
  required: ['sound', 'problems'],
}

const results = await pipeline(
  groups,

  g => agent(RULES + '\n' + g.prompt, {
    label: `fix:${g.key}`, phase: 'Fix', isolation: 'worktree', schema: RESULT,
  }).then(r => ({ ...(r || {}), key: g.key, files: g.files })),

  (r, g) => {
    if (!r || !r.sha) return { ...r, key: g.key, check: { sound: true, problems: ['nothing committed'] } }
    return agent(
`An agent was asked to fix reviewed defects in the SaafSaans repo, touching only:
  ${g.files}

It worked in the git worktree at: ${r.worktree}
and committed ${r.sha}. It reports ${r.tests} tests passing.
It says it fixed: ${JSON.stringify(r.fixed)}
It says it rejected: ${JSON.stringify(r.rejected)}

Check its work ADVERSARIALLY. cd to that worktree and:
  1. Run: git show --stat ${r.sha} and git show ${r.sha}. Read the whole diff.
  2. Confirm it touched ONLY the files it was scoped to. Any other file is a problem.
  3. Run the full suite yourself: .venv/bin/python -m pytest -q
     (use ${ROOT}/.venv/bin/python if the worktree has no .venv). Confirm the count.
  4. Confirm 'git status --short' is CLEAN. An uncommitted mutation left behind is
     the specific failure that silently reverted a committed fix in an earlier run.
  5. For every NEW OR CHANGED test in the diff, verify it CAN FAIL: break the code
     it covers, run it, confirm red, then restore and confirm green. Paste the
     evidence. List any test that stays green under mutation in toothlessTests.
  6. Check the commit message describes what the diff ACTUALLY does. An earlier
     draft in this repo claimed something the tree contradicted.
  7. Check no factual claim was added to a comment or docstring that the code
     does not support.

Restore the worktree to exactly ${r.sha} when you are done (git checkout . && git status).
DEFAULT TO SKEPTICISM. Report problems plainly; sound=true only if you checked
all seven points and they hold.`,
      { label: `check:${g.key}`, phase: 'Verify', schema: CHECK })
      .then(c => ({ ...r, key: g.key, check: c }))
  }
)

const done = results.filter(Boolean)
for (const r of done) {
  log(`${r.key}: ${r.sha ? r.sha.slice(0, 8) : 'NO COMMIT'} — ${(r.fixed || []).length} fixed, ` +
      `${(r.rejected || []).length} rejected, sound=${r.check && r.check.sound}`)
}

return {
  groups: done.map(r => ({
    key: r.key, sha: r.sha, worktree: r.worktree, tests: r.tests,
    fixed: r.fixed, rejected: r.rejected, notes: r.notes,
    sound: r.check && r.check.sound,
    problems: (r.check && r.check.problems) || [],
    toothlessTests: (r.check && r.check.toothlessTests) || [],
  })),
}
