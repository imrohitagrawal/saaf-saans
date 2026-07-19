# Design brief — SaafSaans v1 (Delhi Air Quality & Public Health Companion)

Paste this whole document as your prompt. It is written to be self-contained.

---

You are the design lead at a studio known for giving every client a visual identity
that could not be mistaken for anyone else's. This client has already been rejected
once for a design that looked templated. Give them a distinctive, opinionated point
of view — and take one real aesthetic risk you can justify.

## 1. What the product is

**SaafSaans** — a Delhi air-quality and public-health companion. A person picks a
persona (locality, age group, health condition, planned activity), sees the live air
quality for their area, gets a personal risk read, and can ask questions in plain
language and get grounded advice.

**Audience.** Delhi and NCR residents. Wide range: a parent deciding whether the
school run is safe, an asthmatic deciding whether to run today, a senior deciding
whether to go out at all. Mixed technical literacy. Mobile and desktop. Many will
open it during a pollution emergency, worried, wanting one clear answer fast.

**The single job of the main screen:** answer "is it safe for *me* to go outside
right now, and if not, when?"

**Emotional register.** This is a health tool during a genuine public-health crisis.
It must feel credible and calm — not alarming, not cheerful, not gamified. Nobody
should feel scolded or panicked. But it must not soften a severe reading either.

## 2. Screens and their real content

Four sections. Use real values below — do not invent placeholder lorem.

### A. Advisor (primary — 80% of usage)
- **Live AQI**: `191`, category `Moderate`, station `Anand Vihar, Delhi`
- Position on the CPCB 0–500 scale (bands: Good 0–50, Satisfactory 51–100,
  Moderate 101–200, Poor 201–300, Very Poor 301–400, Severe 401–500)
- Plain-language meaning: *"Acceptable for most. Sensitive groups (asthma,
  heart/lung conditions, kids, seniors) should take it easy on heavy exertion."*
- **Pollutants**: PM2.5 `162`, PM10 `191`, dominant `pm10`
- **Personal risk**: `44 / 100`, band `High`, headline *"High risk — avoid outdoor
  exertion today"*, action *"Skip outdoor exercise. Keep trips short and wear an N95
  outside."*, drivers: `AQI 191 (Moderate)`, `Outdoor exertion multiplies dose`
- **Best time to go out**: *"Late morning (about 9 AM–12 PM)"* — rationale: *"Fine
  particles are the main driver. Outside winter, afternoon sun can lift ozone."*
- **Data status**: `LIVE` from WAQI/CPCB (or `CACHED` when the feed is down — this
  distinction must be visible and honest, never hidden)
- **Multi-day PM2.5 outlook**: a small forecast table
- **Chat**: question input + answer thread. Answers are structured cards with
  sections (verdict / what to do / why / when to seek help), each with an
  expandable "what the app used" panel listing the sources behind the answer

### B. City Pulse
- Grid of ~21 monitoring stations, grouped Delhi / NCR, each showing name + AQI +
  category. Some marked `STALE` when live data is unavailable.
- A 24-hour AQI trend line for a selected station

### C. Observability
- KPI row: questions answered, median response, p95 latency, live-data miss rate,
  AI fallback rate, tokens used
- Two bar charts: events by type, requests by locality

### D. Security
- KPI row: attacks blocked, block rate, attack types seen
- Two charts: blocked by pattern, attacks over time
- A button that runs a red-team simulation

## 3. Hard constraints — read carefully

**The implementation target is server-rendered HTML + CSS** (FastAPI + Jinja2
templates). You are free to design real layouts — CSS Grid, Flexbox, custom
components, any structure you want. There is no component-library lock-in and no
framework whose widgets you must design around.

- Hand-written semantic HTML and CSS. No React, no Tailwind, no component library.
- Vanilla JavaScript is available and welcome for interaction, but the page must be
  useful and readable before any JS runs. Progressive enhancement, not SPA.
- Charts are rendered as inline SVG from server-side data — so you may specify chart
  form precisely rather than accepting a library's defaults.
- No build step. Ship CSS that a browser reads directly (custom properties are fine
  and encouraged).
- Self-hosted or Google Fonts, your choice.

Design the layout you actually think is right. If you want a full-bleed hero, an
asymmetric grid, a sticky rail, a split view, or a single-column reading experience,
propose it — all of that is now buildable.

**Also required:**
- Light and dark, designed as a pair. Neither is an afterthought.
- Body text ≥ 4.5:1 contrast; large text ≥ 3:1. Verify, don't estimate.
- Never convey meaning by colour alone — always pair with text or shape.
- No emoji as icons.
- Tabular figures for all numbers so digits don't shift between refreshes.
- Readable at 375px width.

## 4. The colour problem — the most important design decision here

The obvious move is the official CPCB AQI ramp: green → yellow → orange → red →
dark red → maroon. **Do not simply adopt it.** Three verified problems:

1. **It is non-monotonic in lightness.** CPCB "Good" `#00E400` is *darker* than
   "Moderate" `#FFFF00`. That breaks it as a sequential scale mathematically, not
   just aesthetically.
2. `#FFFF00` on white is about **1.07:1** — effectively invisible.
3. **In dark mode it inverts catastrophically.** Yellow becomes a glare bomb while
   maroon `#7E0023` drops to roughly 1.4:1 — making the *most severe* category the
   *least visible*. (This bug was live in the current build.)
4. Green→red collapses under deuteranopia (~8% of males).

The US EPA publishes its own accessible alternate, **"ColorVision Assist"**, in its
Technical Assistance Document, stating the standard scale "can be difficult to
discern… especially red and green." That is precedent for deviating.

**Required principle:** severity must correlate with *contrast against the
background* in both themes. Severe should be the darkest step on a light canvas and
the brightest on a dark one. Propose a ramp that satisfies this. You may keep
official hues in one small labelled reference badge if you want the familiarity.

## 5. Where the current design fails

Be ruthless. The current build:
- Puts everything in uniform bordered cards, so nothing has priority — the AQI
  number, the risk score, and "AI tokens used" all read at the same weight
- Gives two of four tabs to internal infrastructure metrics that no resident cares
  about, at equal navigational weight to the actual advice
- Buries the most decision-relevant fact (the best time to go outside) in a small
  tile below the fold
- Wraps the chat, the risk gauge, and the AQI reading in the same container styling,
  so the page has no focal point
- Has no visual distinction between "this is measured" and "this is our estimate"

## 6. What to avoid

AI-generated design currently clusters around three looks. All are defaults, not
choices — do not deliver any of them:
1. Warm cream background (~`#F4F1EA`) + high-contrast serif display + terracotta accent
2. Near-black background + a single acid-green or vermilion accent
3. Broadsheet layout with hairline rules, zero radius, dense newspaper columns

Also avoid: the generic SaaS-dashboard look (blue + amber, uniform rounded cards,
drop shadows, a KPI strip across the top); gauge dials; gradient hero numbers;
decorative motion.

## 7. Deliverables

1. **Design rationale** — 150 words. What is the concept, and why does it suit *this*
   subject rather than any health dashboard?
2. **Design tokens** — 4–6 named colours with hex values for light *and* dark, plus
   the severity ramp with contrast ratios stated against each canvas.
3. **Typography** — display, body, and numeric faces with a full type scale
   (sizes, weights, line-heights). Justify the pairing. Do not default to Inter.
4. **Layout** — ASCII wireframes for the Advisor screen at desktop and 375px mobile,
   plus one for City Pulse. Show the information hierarchy explicitly.
5. **Component specs** — the AQI reading, risk indicator, best-time module, station
   tile, chat answer card, and data-status indicator. Anatomy, spacing, states.
6. **Navigation** — should this stay four equal tabs? If not, what? Note that
   Observability and Security are developer-facing; consider demoting them.
7. **One signature element** — the single thing this interface is remembered by.
   Justify it. It must encode something true about air quality or exposure, not
   decorate.
8. **A working static HTML + CSS mockup** of the Advisor screen, light and dark,
   self-contained in one file, using the real values above.

State your assumptions. Where you deviate from this brief, say so and why.
