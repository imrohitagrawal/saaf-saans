# Adversarial verification for AI-assisted development

A domain-independent method, extracted from this project. Nothing here is specific to air
quality — it is about how to use AI assistance without inheriting its confidence.

## The problem it solves

An AI assistant produces fluent, plausible, well-formatted output at a rate no human can
review line by line. The failure mode is not obvious errors. It is **confident, specific,
well-argued claims that happen to be false** — and they arrive in the same voice as the
true ones.

Three real examples from this project, all of which reached documentation or code:

| What was asserted | What was true |
|---|---|
| "The persona is never written to any index" (in the README) | `locality` was written to the telemetry index on every request |
| "Severity always correlates with contrast against the background" (in the README) | The dark-mode ramp was non-monotonic; the claim was false for half the palette |
| "superdesign.dev is dead, skip it" | Two repos share the name; the live one had shipped code two days earlier |

The first two were written by an AI assistant. The third was an AI assistant relaying
another AI assistant's conclusion. **None was caught by reading carefully.** All three were
caught by mechanisms described below.

## The five rules

### 1. Separate the finder from the verifier

The agent that finds a defect must never be the agent that confirms it. A model asked to
check its own work defends it.

Implementation: fan out N agents to find issues, then for each finding spawn an
*independent* agent that has not seen the reasoning, only the claim.

### 2. Make the verifier default to rejection

The verifier's prompt must say, explicitly:

> *Default to `holds = false` unless you can prove it with the actual file contents /
> a source you fetched yourself.*

Without this, verifiers agree with almost everything. With it, they kill things.

**Measured on this project:**

| Study | Claims | Survived | Killed |
|---|---|---|---|
| Code review | — | 24 | not recorded |
| Evidence research | 14 | 7 | **7 (50%)** |
| Decision gaps | 30 | 26 | 4 |

A review process with a kill rate near zero is not verifying anything. **The kill rate is
the health metric of the method.**

### 3. Any claim in prose needs a test or a citation

Both documentation failures above were sentences written ahead of measurement. The fix is
mechanical: if a document asserts a property, either a test asserts it too, or a source is
cited beside it.

This project has three tests whose subject is a README sentence rather than a code path:

```python
def test_dark_severity_ramp_is_monotonic_in_luminance():
    """Parses the stylesheet, computes WCAG relative luminance, asserts that
    severity tracks contrast in BOTH themes -- which the README claims."""
```

These are cheap to write and they make documentation falsifiable. A claim nobody can fail
is not a claim.

### 4. Open the primary source yourself before acting on a summary

A subagent's report is **evidence, not a finding**. Relaying it in your own voice launders
an unverified claim into an assertion.

Rule: before recommending *against* any tool, library or data source, fetch its live page,
its actual repository, and its licence. When two similarly-named projects exist, confirm
which one the evidence describes.

Cost of skipping this on one occasion here: a wrong recommendation to abandon a working
tool, corrected only because the human said *"I can access it, try the URL."*

### 5. Research the premise before building it

The research that cancelled this project's phase 2 cost a fraction of building phase 1 and
could have run first. Test the assumption that justifies the work before doing the work.

Two scoping lessons, learned the expensive way:

- **Narrow beats broad.** A study with 8 sub-questions exhausted its search budget and
  returned nothing on half its scope. A study with 5 tight questions returned usable
  answers on all of them.
- **"Not researched" is not "disproven."** When budget runs out, say so explicitly.
  Silence in a report gets read as a negative finding.

## What this costs

| Study | Agents | Tokens |
|---|---|---|
| Code review (5 dimensions) | 45 | 1.17M |
| Competitive + adoption | 32 | 0.76M |
| Evidence research | 105 | 2.16M |
| Decision gaps | 35 | 0.84M |
| **Total** | **217** | **4.93M** |

This is not free. It is worth it when the alternative is building on a false premise, and
wasteful for routine work. Use it for: premise validation before a big build, pre-release
review, and any claim you intend to publish.

## Reusable implementation

`docs/review-workflow.js` in this repository is a parameterised version of the code-review
study. It takes a repo path and a list of review dimensions and runs find → refute → report.
It has no dependency on this project's domain.

The shape, in pseudocode:

```
findings = parallel(dimensions.map(d => agent(d.prompt, {schema: FINDINGS})))
verified = parallel(findings.map(f =>
    agent(`REFUTE this. Default to false unless proven.` + f, {schema: VERDICT})))
report(verified.filter(v => v.holds))
```

## What the method does not do

- **It does not find what nobody looked for.** Dimensions are chosen by a human. This
  project's review covered docs, dead code, accessibility, privacy and correctness — it
  would not have found a performance problem, because nobody asked.
- **It does not replace users.** Every finding here is about the artifact, not about
  whether anyone wants it. No amount of verification substitutes for one person using the
  thing.
- **It does not make the operator right.** It makes claims falsifiable. The human still
  chooses what to build and still decides what a survived finding means.
