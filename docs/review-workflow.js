/**
 * Adversarial repo review — reusable across projects.
 *
 * Fans out one reviewer per dimension, then attacks every finding with an
 * independent refuter that defaults to "not a defect". Only survivors are
 * reported. See METHODOLOGY.md for why the default-to-reject stance matters:
 * without it verifiers agree with almost everything and the kill rate goes to
 * zero, which means the review is confirming rather than checking.
 *
 * Usage (Claude Code):
 *   Workflow({ scriptPath: "docs/review-workflow.js", args: {
 *     root: "/abs/path/to/repo",
 *     exclude: ".venv, node_modules, dist",
 *     dimensions: ["correctness", "docs-accuracy", "dead-code", "a11y", "security"]
 *   }})
 *
 * `dimensions` accepts the built-in keys below or {key, prompt} objects of your own.
 */
export const meta = {
  name: 'adversarial-repo-review',
  description: 'Review a repo across chosen dimensions; refute every finding before reporting it',
  phases: [
    { title: 'Review', detail: 'one independent reviewer per dimension' },
    { title: 'Verify', detail: 'refuters default to rejecting the finding' },
  ],
}

// Some harnesses hand `args` through as a JSON-ENCODED STRING. Left unparsed,
// every property read below returns undefined, `dimensions` silently falls back
// to the whole built-in list, and the run LOOKS like a clean success while
// reviewing something other than what was asked for. That happened once here
// and cost a full round of 61 agents. Parse, and fail loudly if it is neither.
let opts = args
if (typeof opts === 'string') {
  try {
    opts = JSON.parse(opts)
  } catch (e) {
    throw new Error(`args was a string but not valid JSON: ${e.message}`)
  }
}
if (opts != null && typeof opts !== 'object') {
  throw new Error(`args must be an object or a JSON string, got ${typeof opts}`)
}
const args_ = opts

const root = (args_ && args_.root) || '.'
const exclude = (args_ && args_.exclude) || '.venv, node_modules, dist, build, vendor'

// Each prompt asks for file:line and proof, and forbids style opinions. Findings
// without a reproduction are noise that survives refutation on vagueness alone.
const BUILT_IN = {
  'correctness': `Hunt for real bugs in ${root} (ignore: ${exclude}). Focus on crashes on missing/None data, division by zero, off-by-one, timezone handling, state machines, and boundary conditions. For each: file:line and a CONCRETE INPUT that triggers it. Do not report style opinions or hypotheticals.`,

  'docs-accuracy': `Read every README, doc and top-level docstring in ${root} and verify EVERY factual claim against the code. Check stated counts, file paths, described architecture, feature lists, and any behavioural promise. Report only claims that are FALSE or STALE. Quote the claim and state what is actually true. Run the test suite to check any stated test count.`,

  'dead-code': `Find dead code in ${root} (ignore: ${exclude}). Functions, constants, classes and CSS classes defined but never referenced; unused imports; comments and docstrings describing behaviour the code no longer has; leftover references to removed modules. Grep the whole tree before claiming something is unused, and show the grep result as proof.`,

  'a11y': `Audit accessibility of the templates and stylesheets in ${root}. Check heading order (no skipped levels), form labels, ARIA attribute validity FOR THE ELEMENT IT IS ON, visible focus states including whether any parent clips them, touch target sizes, colour never being the sole carrier of meaning, and accessible names on images and SVG. COMPUTE contrast ratios from the actual token values rather than estimating. Report concrete defects with file:line.`,

  'security': `Audit ${root} for security and privacy defects. Trace every write to a datastore or log and prove whether sensitive input can reach it. Check input validation, injection surfaces, secret handling, authentication and authorisation boundaries, and whether any documented privacy guarantee is actually enforced in code. Report violations with file:line.`,

  'performance': `Find performance problems in ${root} with a plausible impact: N+1 queries, unbounded result sets, work repeated per-request that could be cached, synchronous I/O on a hot path, unbounded in-memory growth. For each give file:line and the condition under which it bites.`,

  'tests': `Audit the test suite in ${root}. Find: tests that cannot fail (no meaningful assertion), tests coupled to implementation rather than behaviour, missing coverage of documented guarantees, side-effecting tests that touch shared state or real services, and slow tests. Report file:line.`,
}

const dimensions = ((args_ && args_.dimensions) || Object.keys(BUILT_IN)).map(d =>
  typeof d === 'string' ? { key: d, prompt: BUILT_IN[d] } : d
).filter(d => d.prompt)

if (!dimensions.length) throw new Error('No valid dimensions. Use built-ins or pass {key, prompt}.')

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          claim: { type: 'string' },
          evidence: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          fix: { type: 'string' },
        },
        required: ['file', 'claim', 'evidence', 'severity'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: {
    holds: { type: 'boolean' },
    reason: { type: 'string' },
    correction: { type: 'string' },
  },
  required: ['holds', 'reason'],
}

// Cap findings per dimension: one reviewer returning 40 items is usually padding,
// and verification cost is linear in findings.
const MAX_PER_DIMENSION = 8

const results = await pipeline(
  dimensions,
  d => agent(d.prompt, { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS })
        .then(r => ({ key: d.key, findings: ((r && r.findings) || []).slice(0, MAX_PER_DIMENSION) })),

  r => parallel(r.findings.map(f => () =>
        agent(
`Try to REFUTE this claimed defect in ${root}.

  File:     ${f.file}${f.line ? ':' + f.line : ''}
  Claim:    ${f.claim}
  Evidence: ${f.evidence}

Read the file yourself. Do not trust the evidence above.

DEFAULT TO holds=false. Only set holds=true if you can point at the actual file
contents and show the defect is real. If the code already handles the case, if the
claim is stale, if it is a style opinion, or if you cannot reproduce it, set
holds=false and say which.

If it is real, give the minimal fix in "correction".`,
          { label: `verify:${(f.file || '').split('/').pop()}`, phase: 'Verify', schema: VERDICT })
          .then(v => ({ ...f, dimension: r.key, verdict: v }))))
)

const all = results.flat().filter(Boolean)
const held = all.filter(f => f.verdict && f.verdict.holds)
const killed = all.length - held.length
const killRate = all.length ? Math.round((killed / all.length) * 100) : 0

// A kill rate near zero means the refuters are rubber-stamping; treat the run as
// suspect rather than as a clean bill of health. See METHODOLOGY.md rule 2.
// Say which dimensions actually ran. The returned findings carry a dimension
// each, but a dimension whose reviewer found NOTHING is invisible in that list,
// so the roster is reported separately -- otherwise "it ran" and "it found
// nothing" are indistinguishable in the result.
log(`dimensions run (${dimensions.length}): ${dimensions.map(d => d.key).join(', ')}`)
log(`${held.length} of ${all.length} findings survived (kill rate ${killRate}%)`)
if (all.length >= 8 && killRate < 10) {
  log(`WARNING: kill rate ${killRate}% is implausibly low - verifiers may be rubber-stamping.`)
}

const order = { high: 0, medium: 1, low: 2 }
return {
  dimensionsRun: dimensions.map(d => d.key),
  killRate,
  examined: all.length,
  confirmed: held
    .sort((a, b) => order[a.severity] - order[b.severity])
    .map(f => ({
      severity: f.severity, dimension: f.dimension,
      file: f.file, line: f.line, claim: f.claim,
      fix: f.verdict.correction || f.fix,
    })),
  rejected: all.filter(f => f.verdict && !f.verdict.holds)
    .map(f => ({ dimension: f.dimension, file: f.file, claim: f.claim, why: f.verdict.reason })),
}
