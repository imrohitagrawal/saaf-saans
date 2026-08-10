# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Delhi/NCR residents deciding whether to go outside — primarily people with a health
condition (or someone to protect: a child, an elderly parent) and a concrete plan for
the next few hours. They check on a phone, quickly, before leaving. Evaluators
(judges, recruiters, peers) do view the deployed site, but design decisions optimize
for genuine resident use first.

## Product Purpose

Answer one question in under five seconds, without scrolling: **"Is it safe for *me*
to go outside right now, and if not, when?"** The user sets a persona (age, health
condition, planned activity, locality); the app shows the live reading, scores their
personal risk, names the best window to go out, and answers plain-language questions
grounded in retrieved health guidance with sources shown.

## Positioning

The personal delta (decision 0004): every other Delhi air product answers "how bad is
the air?" — one answer for eight million people. SaafSaans answers "how bad is it
**for you**, today, given what you are planning?" The core artifact is the comparison
against a healthy-adult baseline with the same plans: "the gap is your body, not the
air."

## Operating Context

- A pull ritual, not push notifications (decision 0003): the user comes to the app at
  decision moments; push is both evidence-weak and architecturally blocked.
- Runs with zero API keys: every external call is timeout-bounded with a deterministic
  fallback. Live data (WAQI), the model (OpenRouter), and dashboards (Elastic) light
  up only when credentials exist.
- Deployed at https://saafsaans.stackclimb.com on one 256 MB Fly.io machine in Mumbai,
  scaled to zero when idle — first request after a quiet spell is slow. The public
  instance has WAQI live but deliberately no model key, so Q&A answers come from the
  rule-based fallback.

## Capabilities and Constraints

- Four views: Today (personal risk, best-time window, CPCB position, WHO comparison,
  five-day outlook, grounded Q&A), City Pulse (21 stations worst-first, 24 h trend),
  System (observability and security self-audit), Guide (glossary of every number,
  band, and condition).
- A sample must never drive severity (decision 0002, implemented): fallback or seeded
  data may render, but never produces a band, verdict, or health instruction.
- Averaging window rules are logged in decision 0005.
- Informational, non-clinical guidance only — not medical advice or an emergency
  service. Every Q&A answer shows its sources.
- Zero JavaScript is **OPEN, not decided** (decision 0001): the rule currently holds
  but has no evidence behind it; the decision file names what would settle it.

## Brand Commitments

- Wordmark: **SaafSaans** paired with Devanagari साफ़ साँस. On English pages the gloss
  is the translation "clean breath" — a translation, not a tagline. Never render it as
  a slogan such as "Breathe clean"; "clean breath" stays true at AQI 40.
- Voice: plain language, sources shown, honest about what is sample data and what the
  app cannot know.

## Evidence on Hand

- `docs/research/2026-07-exposure-evidence.md` — evidence base (with refutations) for
  every user-facing claim about air, dose, or behaviour. Consult it before adding a
  claim.
- `docs/decisions/0001–0005` — the decision log with assumptions and falsifiers.
- `docs/USER-TEST.md` and `docs/user-test-sheet.md` — the user-testing protocol.
- `docs/screenshots/` — current-state captures of all four views, light/dark/Hindi.
- Absences future work must not fabricate: no testimonials, no clinical validation, no
  named users, no verified Hindi review yet.

## Product Principles

1. The personal delta is the product; a city-wide number is commodity.
2. Honesty over polish: sample data never drives severity, absences are stated, every
   health claim traces to the evidence file.
3. Non-clinical by design: inform the decision, never prescribe treatment.
4. Degrade deterministically: zero keys must still produce a truthful, useful page.
5. Meet the user at the decision moment (pull), not in their notification tray (push).

## Accessibility & Inclusion

- WCAG 2.1 AA is the target for contrast, keyboard use, and screen readers.
- Hindi parity is a goal: the Hindi draft ships gated behind a banner stating no Hindi
  speaker has verified it, and new surfaces must not make parity harder to reach.
