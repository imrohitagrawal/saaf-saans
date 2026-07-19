# Retrospective

SaafSaans was built for a hackathon and did not reach the top 15. This is what went wrong and
what changed.

## What the first version was

A four-tab Streamlit "Command Center": pick a persona from four dropdowns, see a live AQI number,
chat about it. Two of the four tabs were engineering telemetry. ~4,300 lines, 142 tests, graceful
degradation on every external call, a written threat model.

The engineering was fine. That was not the problem.

## Why it lost

1. **The core loop was undifferentiated.** Pick dropdowns → see an AQI number → chat. IQAir,
   AQI.in, SAFAR and Google Maps already do this. A judge files it under "another AQI app" in ten
   seconds, and nothing in the build argued otherwise.

2. **The demo pointed at the plumbing.** Two of four tabs showcased *our infrastructure* at equal
   navigational weight to the health advice. That reads as sponsor-checklist compliance rather
   than as solving a problem. (These views are back in the rebuild — but as *proof surfaces* for
   a portfolio audience, not as half the product.)

3. **It informed without creating agency.** "Wear an N95, stay indoors" is what every Delhi
   resident already knows and largely cannot act on. The build never made the personal number
   feel different from the ambient one.

4. **Retrieval theatre.** `data/advisories.py` held 34 hardcoded rows behind an Elasticsearch
   query that returned results identical to a dict lookup. A reviewer who greps the repo finds
   zero `match`, `multi_match`, `query_string`, or `fuzzy` queries — the "search" was range
   filters and keyword boosts. The retrieval *pattern* was right; the storage engine was chosen
   for how it sounded.

5. **Invented numbers.** `services/risk.py` produced the headline figure and its weights cited
   nothing. The docstring said "documented weights"; the documentation was us.

6. **No evidence.** No user validated it. No number quantified its impact. Nothing a judge could
   repeat to another judge.

## What changed

| Then | Now |
|---|---|
| Generic dropdown-and-cards shell | Sky hero whose gradient and haze track the reading |
| Ambient AQI as the headline | *Your* risk against a healthy-adult baseline, with the gap explained in words |
| 577 lines of HTML strings injected into Streamlit | FastAPI + Jinja2, hand-written semantic markup |
| Colour ramp copied from CPCB | Severity correlates with contrast in both themes; the official ramp is quarantined to one labelled badge |
| Glossary stranded at page bottom | Definitions open in place, next to the term |
| Cached and live data styled identically | `◌ CACHED`, a dead-feed notice, and fallbacks logged as fallbacks |
| Emoji as icons | None |
| 142 tests | 186, including end-to-end tests that assert no page ships JavaScript |

Bugs the rebuild surfaced, all of which had been live:

- **`normalize.aqi_category` collapsed 0–100 into "Good"**, merging two distinct official CPCB
  categories. Satisfactory (51–100) simply did not exist in the app.
- **The dark-mode severity ramp was backwards.** Severe rendered at roughly 1.4:1 against the
  background — the most dangerous band was the least visible thing on screen.
- **Seeding was not idempotent.** `setup_indices.py` used auto-generated document ids, so each
  run appended another copy of the 34 advisories; retrieval then cited the same guidance twice
  in one answer.
- **The chat replaced its own history**, so a user tracking a decision lost what they had asked.
- **`aria-pressed` on links**, no `<main>` landmark, no skip link, and section titles that were
  styled `div`s rather than headings — the page had one heading and nothing else to navigate by.
- **A false claim in this repository's own README**: it stated the persona is never written to
  any index, while locality was being indexed deliberately to power a dashboard. The claim is
  now precise about what is stored and why.

## The honest lesson

Adding tests, a threat model, and more feature tabs to a weak wedge produces a *well-built* weak
wedge. Execution quality cannot rescue a premise nobody challenged.

The second mistake was subtler: the first two rebuild attempts *also* failed, because both kept a
left-sidebar-plus-top-tabs-plus-card-grid shell — the default layout of every web app, and
coincidentally the same shell as an unrelated project in the same portfolio. Changing the
palette and calling it a redesign is the same error wearing better colours. The fix only came
from a real design brief, a real design, and being willing to throw away a working UI.

## What this repo is now

A finished, documented baseline. It is not being extended — the successor takes the same service
layer in a different direction, with **inhaled dose in micrograms** as the headline metric rather
than ambient AQI, accumulating over time and grounded in published inhalation rates rather than
invented weights.

The two repositories together are the point: what was built, why it was weak, and what was done
about it.
