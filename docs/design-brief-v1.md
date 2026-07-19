# Design brief — SaafSaans

Paste this entire document as your prompt. It is written to be self-contained.

---

You are the design lead at a studio known for giving every client a visual identity
that could not be mistaken for anyone else's. This client has been rejected once for
a design that looked templated, and their current build accidentally looks like a
different product they also own. They are paying for a distinctive, opinionated
point of view. Take one real aesthetic risk you can justify.

Work in two passes. First produce a written design plan. Review it against this
brief and ask yourself: *would I have produced this same layout for a project
management tool, a crypto dashboard, or a hospital admin panel?* If yes, it is a
default, not a decision — revise it and say what you changed. Only then write code.

---

## 1. The product

**SaafSaans** — a Delhi air-quality and public-health companion.

A person tells it who they are (locality, age group, health condition, planned
activity). It shows the live air quality where they are, scores their **personal**
risk, tells them the best window to go outside, and answers plain-language questions
with advice grounded in retrieved health guidance.

**The single job of the main screen — everything else is secondary:**

> *"Is it safe for **me** to go outside right now, and if not, when?"*

If a user cannot answer that in under five seconds without scrolling, the design has
failed regardless of how it looks.

### Audience

Delhi and NCR residents. A parent deciding whether the school run is safe. A
30-year-old with asthma deciding whether to run. A 70-year-old deciding whether to
leave the house at all. Mixed technical literacy, mixed English fluency. **Assume
mobile first** — most users are on a phone, often on a slow connection, often
outdoors in bright sunlight.

Many open this while anxious, during a genuine public-health emergency. Delhi
regularly exceeds AQI 400 for weeks.

### Emotional register

Credible and calm. Not alarming, not cheerful, not gamified, not corporate. Never
scold. Never panic. But never soften a severe reading — a person whose air is
genuinely dangerous must feel that, and act.

The user should feel: *this thing is being straight with me.*

---

## 2. What is wrong with the current design — read this carefully

The current build has a **left sidebar with persona dropdowns, a row of top tabs,
and a grid of uniform bordered cards.** This is the single most common web-app shell
in existence. The client's *other, unrelated product* uses the same shell, and when
they saw this build their reaction was that the two look like the same application.

**Do not deliver a left-sidebar-plus-top-tabs-plus-card-grid layout.** If you
genuinely believe it is right after considering alternatives, you must argue for it
explicitly and say what you rejected. The bar for that argument is high.

Other specific failures to fix:

1. **No hierarchy.** The AQI number, the risk score, and "AI tokens used" all render
   at roughly the same visual weight in identical bordered boxes. Nothing is
   primary. The eye has nowhere to land.
2. **The most decision-relevant fact is buried.** "Best time to go out" — the actual
   answer to the user's question — sits in a small tile below the fold, styled
   identically to the PM10 reading.
3. **Everything has equal navigational weight.** Four flat tabs imply a resident
   cares about p95 latency as much as whether their child can walk to school. The
   engineering views are *required* (see §3.7) — the failure is that nothing
   distinguishes a resident-facing destination from a system-facing one.
4. **Measured and estimated data look identical.** A live station reading, a cached
   sample from a dead feed, a rule-based fallback answer, and a model-generated
   answer are all styled the same. In a health tool this is a credibility problem,
   not a styling problem.
5. **The persona is invisible after it is set.** Nothing on screen continuously
   signals "this advice is specifically for a 70-year-old with COPD."
6. **Generic empty and degraded states.** No design for "the air-quality feed is
   down," which happens often.
7. **Definitions are stranded at the bottom of the page.** A "what these numbers
   mean" glossary sits below everything, decoupled from the numbers it explains.
   Nobody scrolls to it. A user who does not know what PM2.5 is meets that term at
   the top of the page and gets no help there.

---

## 3. What must be on screen — with real data

Use these real values. Do not invent placeholder content.

### 3.1 The air reading

```json
{ "aqi": 191, "pm25": 162.0, "pm10": 191.0,
  "dominant_pollutant": "pm10",
  "station": "Anand Vihar, Delhi", "city": "Delhi",
  "stale": false, "obs_time": "2026-07-19T14:00:00+05:30" }
```

`stale: true` means the live feed failed and this is a cached sample. **This
distinction must be visible.** Never disguise a fallback as live data.

CPCB category bands (India's scale, 0–500):
`Good 0–50` · `Satisfactory 51–100` · `Moderate 101–200` · `Poor 201–300` ·
`Very Poor 301–400` · `Severe 401–500`

Plain-language meaning for the current reading:
> *"Acceptable for most. Sensitive groups (asthma, heart/lung conditions, kids,
> seniors) should take it easy on heavy exertion."*

### 3.2 Personal risk

```json
{ "score": 56, "band": "High",
  "headline": "High risk — avoid outdoor exertion today",
  "advice": "Skip outdoor exercise. Keep trips short and wear an N95 outside.",
  "drivers": ["AQI 191 (Moderate)", "Outdoor exertion multiplies dose",
              "Asthma raises risk"] }
```

Bands: `Low` `Moderate` `High` `Very High` `Extreme`.

**Design consideration:** the same air is 44/100 for a healthy adult and 56/100 for
an asthmatic doing outdoor exercise. The *difference between the ambient reading and
the personal one* is the product's entire reason to exist. Make that legible.

### 3.3 Best time to go out

```json
{ "window": "Late morning (about 9 AM–12 PM)",
  "rationale": "Fine particles are the main driver. Outside winter, afternoon sun
                can lift ozone too, so late morning tends to be the calmer window
                before the afternoon peak. This is a general pattern, not an hourly
                station forecast." }
```

Note the honesty in that last sentence. Preserve that tone.

### 3.4 Multi-day PM2.5 outlook

A short table: date, average, min, max. Roughly 5 rows.

### 3.4b Definitions, in place

Terms like *AQI*, *PM2.5*, *PM10*, *dominant pollutant*, and *personal risk* are
unfamiliar to a large share of users, and they appear at the very top of the screen.
Definitions must be available **at the point of need**, not stranded in a glossary
at the bottom.

Example content: *"PM2.5 = fine particles under 2.5 micrometres that reach deep into
the lungs. Delhi's main health concern."*

Design an inline disclosure affordance for this. Hard requirements:
- It must be a real focusable control with `aria-expanded` — **never hover-only**.
  Most users are on phones, where hover does not exist.
- It must not add visual noise next to every number. Solve the density problem.
- Longer-form explanation may live on a separate page; the one-line definition must
  be reachable without leaving the screen.

### 3.5 The conversation

Question in, structured answer out. Answers arrive as an ordered dict of section
headings to content — headings vary but are typically along the lines of *verdict*,
*what to do*, *why*, *when to seek help*. Content is either a paragraph or a bullet
list.

Every answer carries a **"what the app used"** disclosure: the AQI reading it was
grounded in, whether that reading was live or cached, and the retrieved health
advisories with their sources (`CPCB-AQI-scale`, `GINA-guidance`, `AHA-airpollution`,
`WHO-AQG-2021`, `ACOG-airquality`, `GOLD-guidance`, `EPA-indoor-air`).

```json
{ "source": "GINA-guidance",
  "advice": "AQI 101-200 with asthma: carry your reliever inhaler, prefer indoor
             exercise, and avoid high-traffic roads where NO2 spikes." }
```

This provenance is a core feature, not a footnote. It is the difference between this
and a chatbot guessing. **But it must not clutter the primary answer** — design the
relationship between claim and source.

Also design the **refusal state**: questions that try to manipulate the assistant are
blocked before reaching the model, and the user sees an explanation. It should feel
matter-of-fact, not accusatory.

### 3.6 City-wide view

~21 monitoring stations across Delhi and NCR, each with a name, an AQI, a category,
and a possible `stale` flag. Plus a 24-hour trend for one selected station.

Delhi stations: Anand Vihar, ITO, Rohini, RK Puram, Punjabi Bagh, Mandir Marg,
Dwarka, Najafgarh, Wazirpur, Jahangirpuri, Okhla, Ashok Vihar, Nehru Nagar,
Patparganj, DTU. NCR: Noida, Greater Noida, Gurugram, Ghaziabad, Faridabad.

### 3.7 Observability and Security — required, not optional

These are part of what this product **is**, and they must remain visible
destinations. Do not remove or hide them.

**Observability.** Every question the app answers is logged. Shows: questions
answered, median and p95 response time, how often the live air-data feed was missed
and a cached sample used instead, how often the AI fell back to rule-based advice,
total token spend, events by type, requests by locality.

**Security.** Prompt-injection attempts are blocked *before* reaching the model and
audited. Shows: attacks blocked, block rate, distinct attack patterns seen, blocked
attempts over time, and a button that fires a red-team simulation live.

**Why they matter here.** This product's core claim is that its advice is grounded,
auditable, and safe. These two views are that claim being *demonstrated* rather than
asserted — a visitor can watch an injection attempt get blocked, and can see that
the app admits when it degraded to cached data. Treat them as proof surfaces.

**The design problem is weight, not existence.** A Delhi resident opening this during
an emergency needs the health advice; an evaluator wants the engineering evidence.
Both audiences are real. Decide how to serve both without letting the second crowd
out the first: peer-level destinations, a grouped "system" section, a distinct visual
register, a different entry point? Argue your choice.

Note also: the honesty already present in the product — telemetry records when the
app fell back rather than hiding it — is a design asset. Surface it.

---

## 4. The colour problem — the most consequential decision here

The obvious move is India's official CPCB AQI ramp: green → yellow → orange → red →
dark red → maroon. **Do not simply adopt it.** Four verified problems:

1. **It is non-monotonic in lightness.** CPCB "Good" `#00E400` is *darker* than
   "Moderate" `#FFFF00`. That breaks it as a sequential scale mathematically, not
   merely aesthetically.
2. `#FFFF00` on white measures roughly **1.07:1** — effectively invisible.
3. **It inverts catastrophically in dark mode.** Yellow becomes a glare bomb while
   maroon `#7E0023` falls to about **1.4:1** — making the *most severe* category the
   *least visible thing on screen*. This bug was live in the current build.
4. **Green→red collapses under deuteranopia** (~8% of males).

The US EPA publishes its own accessible alternate — **"ColorVision Assist"**, in its
Technical Assistance Document for reporting daily air quality — stating that the
standard scale "can be difficult to discern… especially red and green." That is
formal precedent for deviating from the official ramp.

**Required principle:** severity must correlate with **contrast against the
background** in *both* themes. Severe should be the darkest step on a light canvas
and the brightest on a dark one. Propose a ramp satisfying this and state measured
contrast ratios. You may retain official hues in one small labelled reference badge
if you want the familiarity — but they must not be the page's colour system.

Also note: every other air-quality product on the market (IQAir, AQI.in, SAFAR,
Google Maps) uses a big coloured circle with a number on a map, in that ramp.
**Looking like them is a commercial failure, not a neutral choice.**

---

## 5. Technical constraints

**Target: server-rendered HTML + CSS** (FastAPI + Jinja2 templates, Python).

- Hand-written semantic HTML and CSS. No React, no Tailwind, no component library,
  no build step. CSS custom properties are encouraged.
- Vanilla JavaScript is available and welcome, **but the page must be fully useful
  and readable before any JS runs.** Progressive enhancement, not an SPA.
- Charts are inline SVG generated server-side, so you can specify chart form exactly
  rather than accepting a library's defaults.
- Fonts: Google Fonts or self-hosted, your choice. Do not default to Inter.

**Non-negotiable quality floor:**

- Light and dark designed as a pair, neither an afterthought.
- Body text ≥ 4.5:1 contrast, large text ≥ 3:1. State measured values, do not estimate.
- Never convey meaning by colour alone — always pair with text, shape, or position.
- No emoji as icons.
- Tabular figures on all numerals so digits do not shift between refreshes.
- Fully usable at 375px width. Design mobile first, then scale up.
- Visible keyboard focus. `prefers-reduced-motion` respected.
- Readable in bright outdoor sunlight — this is used outside, on phones.

---

## 6. Anti-patterns — do not deliver any of these

AI-generated design currently clusters around three looks. All are defaults, not
choices:

1. Warm cream background (~`#F4F1EA`), high-contrast serif display, terracotta accent.
2. Near-black background with a single acid-green or vermilion accent.
3. Broadsheet layout, hairline rules, zero border-radius, dense newspaper columns.

Also avoid:

- The generic SaaS dashboard: blue and amber, uniform rounded cards with drop
  shadows, a KPI strip across the top, a left nav rail.
- **The left-sidebar + top-tabs + card-grid shell** (see §2).
- Gauge dials and speedometers.
- Gradient hero numbers.
- Decorative motion that encodes nothing.
- Numbered eyebrows (01 / 02 / 03) on content that is not actually a sequence.

---

## 7. Where this is going — design so v1 is not a dead end

A successor product is being built on the same service layer. Its headline metric is
**inhaled dose** — *"you inhaled 312 µg of PM2.5 today"* — accumulating over days,
broken down by segment of the user's day, with counterfactual suggestions (*"shift
your run to 6pm: −84 µg"*).

You are **not** designing that. But if your visual system can extend to it, say how.
A design language that dies at v1 is worth less than one that carries forward.

---

## 8. Deliverables

1. **Design rationale** — 150–200 words. What is the concept, and why does it suit
   *air quality and human breath specifically*, rather than any health dashboard?

2. **Three distinct directions**, described in a short paragraph plus an ASCII
   wireframe each. Make them genuinely different in structure — not three colourways
   of one layout. Then **recommend one and justify it.** Develop only the winner
   through the remaining deliverables.

3. **Design tokens** — 4–6 named colours with hex values for light *and* dark, plus
   the severity ramp with measured contrast ratios against each canvas.

4. **Typography** — display, body, and numeric faces with a complete type scale
   (sizes, weights, line-heights, letter-spacing). Justify the pairing against this
   subject. Not Inter.

5. **Layout** — ASCII wireframes of the main screen at 375px and at desktop, plus
   the city-wide view. Annotate the information hierarchy: what is first, second,
   third, and what you cut.

6. **Component specs** — anatomy, spacing, and all states for: the air reading, the
   personal-risk indicator, the best-time module, the station tile, an answer with
   its sources, the data-provenance indicator (live vs cached vs estimated), and the
   refusal state.

7. **Information architecture** — how many top-level destinations, what they are,
   and what navigation pattern. All four areas (advice, city-wide, observability,
   security) must be reachable; decide their relative weight and grouping, and
   whether resident-facing and system-facing views should read in different visual
   registers. Justify.

8. **One signature element** — the single thing this interface is remembered by. It
   must encode something true about air, breath, or exposure. Not decoration.
   Explain why it earns its place.

9. **A working self-contained HTML + CSS mockup** of the main screen, light and
   dark, in one file, using the real data above.

State your assumptions. Where you deviate from this brief, say so and why — a
justified deviation is more valuable than compliance.
