# Documentation index

The map. Start here. Every document below has one line saying **when to read it** — not
what it contains, but the situation in which you should open it.

Written 2026-07-21. If you are a future session with no context, read in this order:
`README.md` → this file → the decision that covers what you are about to change.

## Reading order by situation

| You are about to… | Read |
| --- | --- |
| change anything at all | `README.md`, then this file |
| understand why the project is shaped this way | [`CASE-STUDY.md`](CASE-STUDY.md) |
| change a rule that feels arbitrary | the matching file in [`decisions/`](decisions/) — it is probably logged, possibly as open |
| make a claim about air, dose or behaviour in user-facing copy | [`research/2026-07-exposure-evidence.md`](research/2026-07-exposure-evidence.md), especially its refutations |
| deploy | [`DEPLOY.md`](DEPLOY.md) |
| put the app in front of a person | [`USER-TEST.md`](USER-TEST.md) + [`user-test-sheet.md`](user-test-sheet.md) |

## Decisions

One file per decision. Each carries: assumptions, analysis, data points, what changed our
mind, what we kept, what we are modifying, risks accepted, and what would falsify it.

| # | Decision | Status | Read it when |
| --- | --- | --- | --- |
| [0001](decisions/0001-zero-javascript.md) | Zero JavaScript | **OPEN — NOT DECIDED** | You want to add a script, or you are wondering why the app has none and cannot find a reason. Records that the rule has *no evidence behind it*, states the real benefits too, and names what would settle it. |
| [0002](decisions/0002-sample-data-honesty.md) | A sample must never drive severity | Decided; implementation pending | You are touching `waqi.SAMPLES`, `_fallback`, `/city`, or anything that turns a number into a band, verdict or health instruction. |
| [0003](decisions/0003-notifications-and-the-pull-ritual.md) | Notifications, and the pull ritual instead | Decided | Someone proposes push notifications or alerts. Explains why push is both evidence-weak *and* architecturally blocked, and what replaces it. |
| [0004](decisions/0004-value-proposition.md) | The same air is not the same dose for you | Decided | You are deciding what goes at the top of a page, or arguing about what this app is for. |

## Research

Evidence, with sources and verification status. Nothing marked *search-layer only* may
appear in user-facing prose.

| Document | Read it when |
| --- | --- |
| [`2026-07-exposure-evidence.md`](research/2026-07-exposure-evidence.md) | Before writing any factual claim about purifiers, masks, commuting, indoor air or behaviour change. **Read Part 1 (refuted) first** — 9 of 25 claims died, and four of them were headed into the product. |

## Narrative

The story of how the decisions were reached. Not normative — do not cite these as rules.

| Document | Read it when |
| --- | --- |
| [`CASE-STUDY.md`](CASE-STUDY.md) | You want the full record: what was built, what the evidence said, why Phase 2 was cancelled, and the method lessons from three review runs. Long. §6 ("what this demonstrates — and what it does not") is the most honest part. |
| [`../RETROSPECTIVE.md`](../RETROSPECTIVE.md) | You want to know why the previous version lost. |
| [`METHODOLOGY.md`](METHODOLOGY.md) | You want the review method itself, independent of this app — kill rates, agent fan-out, what a finding is. |

## Instruments

Things you run, not things you read for information.

| Document | Read it when |
| --- | --- |
| [`USER-TEST.md`](USER-TEST.md) | You are facilitating a session. Includes the wording to use and the leading wording to avoid. |
| [`user-test-sheet.md`](user-test-sheet.md) | You need the per-participant recording sheet. |
| [`DEPLOY.md`](DEPLOY.md) | You are deploying, or need the platform runbook. |

## History and archive

| Document | Read it when |
| --- | --- |
| [`design-brief-v1.md`](design-brief-v1.md) | You want the original brief. **Superseded — kept as a record.** Its §5:275 is the primary source for decision 0001. |
| [`PLAN-hindi2-closure.md`](PLAN-hindi2-closure.md) | You are working on Hindi, advisory relevance, or the caveat cascade. |
| [`phase-2/`](phase-2/) | You are wondering about the cancelled exposure ledger. It stays cancelled. |
| [`archive/`](archive/) | You need the Hugging Face Space branch patch. |
| [`screenshots/`](screenshots/) | You need images. |

## Standing constraints (recorded elsewhere, listed here so they are findable)

- **Zero `<script>` tags.** Pinned by `tests/test_web.py:48`. See [0001](decisions/0001-zero-javascript.md) — logged as an *open question*, not a settled rule.
- **The Hindi review banner stays.** Not removable.
- **Cancelled, do not re-add:** the exposure ledger, push notifications, a forecast "best hours" feature, mask health-benefit claims, WhatsApp. Push is reasoned in [0003](decisions/0003-notifications-and-the-pull-ritual.md); the ledger in [`CASE-STUDY.md`](CASE-STUDY.md) §5.
- **Every factual claim in prose needs a citation or a test beside it.** An unsupportable claim is removed, not softened.

## Test baseline

882 passing, ~2.3s, no network, at commit `3bac090`. Run with:

```
cd /Users/rohitagrawal/Projects/saaf-saans && env OPENROUTER_API_KEY= WAQI_TOKEN= \
  ELASTIC_URL= ELASTIC_API_KEY= ELASTIC_CLOUD_ID= .venv/bin/python -m pytest -q
```

The trailing-equals form is **required**. `env -u NAME` does not work: `services/config`
calls `load_dotenv()` at import, which refills an unset name from `.env` and produces a
live-credential run. `load_dotenv` does not overwrite a name that is present but empty.

> Note: `README.md:174` and `RETROSPECTIVE.md:52` both state 773 tests / 25 files. The
> measured figure is 882 / 26. Those are stale, unpinned, present-tense claims and should
> be corrected by measurement. (`CASE-STUDY.md:32`'s 831 is *pinned to commit `b26256d`*
> and is therefore a correct historical statement, not a stale one.)
