---
name: SaafSaans
description: Delhi air-quality companion — the sky is the interface
colors:
  paper: "#F2F1EE"
  surface: "#FBFAF8"
  surface-recessed: "#E9E7E2"
  border: "#DCD9D2"
  border-strong: "#8F8B80"
  ink: "#211E19"
  ink-2: "#57524A"
  ink-3: "#6B665D"
  clear-day-blue: "#2F5D8A"
  accent-tint: "#DCE7F1"
  on-accent: "#FFFFFF"
  g1: "#2F6FB5"
  g2: "#3F7180"
  g3: "#8A5A0E"
  g4: "#9C4519"
  g5: "#8A2A26"
  g6: "#58150E"
  n1: "#DCE9F6"
  n2: "#DAEAEE"
  n3: "#F3E4C4"
  n4: "#F6DFD2"
  n5: "#F4D9D7"
  n6: "#EFD7D2"
typography:
  display:
    fontFamily: "Anek Latin, Segoe UI, sans-serif"
    fontSize: "clamp(28px, 5vw, 42px)"
    fontWeight: 800
    lineHeight: 1.08
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Anek Latin, Segoe UI, sans-serif"
    fontSize: "26px"
    fontWeight: 700
  title:
    fontFamily: "Anek Latin, Segoe UI, sans-serif"
    fontSize: "20px"
    fontWeight: 600
  body:
    fontFamily: "IBM Plex Sans, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "IBM Plex Mono, ui-monospace, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.12em"
  data:
    fontFamily: "IBM Plex Mono, ui-monospace, Menlo, monospace"
    fontSize: "46px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.02em"
rounded:
  track: "4px"
  input: "8px"
  button: "10px"
  panel: "12px"
  kpi: "14px"
  card: "16px"
  hero: "20px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.clear-day-blue}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.button}"
    padding: "11px 20px"
  button-pill:
    backgroundColor: "transparent"
    textColor: "{colors.clear-day-blue}"
    rounded: "{rounded.pill}"
    padding: "6px 14px"
  band-chip:
    backgroundColor: "{colors.n3}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.input}"
    padding: "8px 10px"
---

# Design System: SaafSaans

## Overview

**Creative North Star: "The Sky Is the Interface"**

The hero renders the air you are being told about, so severity is felt before it
is read. The sky gradient, the blurred sun, and the haze layer all track the CPCB
band of the current reading; the one variable doing the real work is haze
opacity, which climbs monotonically with severity. The rest of the page is a warm
paper bulletin beneath that sky: the app is a companion first and an instrument
second, and it reassures by being plainly honest — verdicts in warm display type,
qualifications visibly quieter, numbers steady in a mono register that never
shifts on refresh.

Two registers share the system. The resident register (Today, City Pulse, Guide)
is proportional prose on warm paper, verdict-first. The proof register (System)
is deliberately mono-heavy and flat, because telemetry must not sound like
advice. Both are flat-on-paper: depth comes from surface steps and hairline
borders, with the sky hero as the single atmospheric exception.

The rejected shell is documented history: no dashboard cards-with-gauges, no
sidebar, no CPCB rainbow. Severity is never carried by colour alone.

**Key Characteristics:**
- Sky-reactive hero: gradient, sun, and haze density driven by the live band
- Warm paper surfaces with a single restrained blue accent
- The Delhi Sky severity ramp: real sky colours, luminance monotone with severity
- Two typographic registers: warm prose for people, flat mono for the machine
- Bilingual by construction: Devanagari is a first-class script, not a fallback

## Colors

A warm paper neutral family, one restrained blue accent, and a six-band severity
ramp drawn from the real colours of a Delhi sky.

### Primary
- **Clear-Day Blue** (#2F5D8A): links, actions, the primary button, selection
  marks (nav underline, station rail), and the live-provenance dot. The colour of
  the sky on the day you can go outside. Dark theme lightens it to #8FB8DC with
  **Accent Tint** (#DCE7F1 light / #1C2938 dark) as its wash.

### Neutral
- **Paper** (#F2F1EE): the page canvas. Dark theme: #12151C.
- **Surface** (#FBFAF8): cards and raised panels. Dark: #1B1F28.
- **Surface Recessed** (#E9E7E2): definition slots, refusals, driver chips — one
  step back into the paper. Dark: #232834.
- **Border** (#DCD9D2) and **Border Strong** (#8F8B80): hairlines and control
  outlines; Border Strong is measured at 3.26:1 on Surface (3.41:1 dark), the
  SC 1.4.11 floor for control boundaries. Dark: #2B303B / #6B7280.
- **Ink** (#211E19), **Ink 2** (#57524A), **Ink 3** (#6B665D): the three text
  weights — full voice, supporting prose, quiet metadata. Dark: #E8E6E1 /
  #ABA79E / #8B877E.

### Severity: The Delhi Sky ramp
Six band inks (g1–g6) with paired tints (n1–n6), Good → Severe: clear-sky blues
(#2F6FB5, #3F7180), dust ochres (#8A5A0E, #9C4519), smog maroons (#8A2A26,
#58150E). Light theme darkens with severity; the dark-theme ramp (#5A8CBA →
#FFC3B2) brightens with it — in both, luminance is monotone, so severity tracks
contrast-against-background and survives every colour-vision deficiency. The
unknown band (gx/nx) is Ink 3 on Surface Recessed: no reading, no colour claim.
Each band also owns a sky pair (--sky1/--sky2), a sun tint, and a haze opacity
for the hero, in both themes.

### Named Rules
**The Never-Colour-Alone Rule.** Every band colour is paired with the band word
and a position on the labelled scale. Colour is reinforcement, never the message.

**The Monotone Severity Rule.** Any new severity colour must keep luminance
monotone with severity in both themes, measured against the surface it sits on.
The dark ramp was re-valued once because g2 sat brighter than g3–g5; that defect
class is banned.

## Typography

**Display Font:** Anek Latin (with Segoe UI fallback) — weights 600–800
**Body Font:** IBM Plex Sans (with Segoe UI fallback) — weights 400–700
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, Menlo fallback) — 400 and 600
**Hindi:** Anek Devanagari replaces all three when the computed language is
Hindi (it is one superfamily with Anek Latin, loaded only on Hindi pages).

All faces are self-hosted as subsetted woff2 under `/static/fonts` — no request
leaves the origin for type. `scripts/build_fonts.py` regenerates the files and
the metric-matched fallback faces (Arial / Courier New with measured
size-adjust and ascent/descent overrides), so fallback text holds the same
lines while a face loads and nothing jumps on swap.

**Character:** A condensed, high-x-height display face that reads in sunlight,
over a bookish humanist body; every number, timestamp, and label sits in an
instrument-grade mono. Warm where it speaks, exact where it measures.

### Hierarchy
- **Display / verdict** (800, clamp(28–42px), 1.08, -0.015em): the answer in
  words, on the sky. The largest text on any page is a sentence, not a number.
- **Headline / page-h1** (700, 26px): page titles.
- **Title / ask-h2** (600, 20px): section heads like the Q&A lead.
- **Body** (400, 15px, 1.55): all prose; `tabular-nums` set globally.
- **Label / kicker** (mono, 11px, 0.12em, uppercase): kickers, field labels,
  answer section heads. Rendered as h2.kicker when it carries the outline.
  11px is also the Latin floor: no font-size in the stylesheet sits below it
  (the audience includes seniors; the instrument register earns its density
  from the mono face and tracking, not from sub-11px sizes).
- **Data** (mono 600, 46px AQI numeral; 16–22px for pollutant values and KPIs):
  every measurement on the site is mono.

### Named Rules
**The Steady Digits Rule.** `font-variant-numeric: tabular-nums` is global;
digits must not shift on refresh.

**The Devanagari Floor Rule.** Hindi text is never letter-spaced, never
uppercased, never below 12px (12.5px floor on labels), and each display-face
heading moves up one weight step — Devanagari at a given weight reads lighter
than Latin. Pill controls take measured optical padding shifts (ink sits 2px
lower) because Anek Devanagari reserves below-baseline space most strings never
ink.

**The Quiet Caveat Rule.** Exactly one style — `.caveat` (12.5px, Ink 3) — for
every qualification. Full weight belongs to the verdict, the advice, and what to
do; everything that hedges them shares this one quiet voice.

## Layout

A centered shell, max-width 1120px, with 18–20px gutters (14–16px under 560px).
Content flows in an auto-fit card grid (`minmax(min(330px, 100%), 1fr)`, 16px
gap) with full-width rows opting in via a `wide` class; the Today page leads
with the full-width sky hero. Nothing in the layout forces a horizontal
scrollbar at the 320px reflow width — track minimums yield to the container,
and the a11y suite sums every fixed minimum against the space available at 320.
The header carries wordmark, nav, and the theme/language pill toggles; it is
sticky (with `scroll-padding-top: 76px` so focus moves and the skip link clear
it) only from 900px up, where it provably holds one row — narrower, it wraps
taller than any fixed clearance, so it scrolls away instead of covering what
an anchor jump lands on. Density is calm: cards pad 16px, related items sit
8–12px apart. Touch targets hold a 44px floor via measured padding, relaxed to
the designed density only under `@media (pointer: fine)`; the a11y test suite
recomputes every target from the stylesheet.

## Elevation & Depth

Flat on paper, with one atmospheric exception. There are no box-shadows in the
system: depth is carried by surface steps (Paper → Surface → Surface Recessed),
hairline borders, and the single inset selection rail (`inset 3px 0 0` in
Clear-Day Blue) on the chosen station row. The exception is the sky hero, which
builds real atmosphere from a layered stack — band-driven gradient, blurred sun
disc, haze gradient whose opacity climbs with severity, and a fixed legibility
scrim under the text. That stack is weather, not elevation; nothing else on the
page may borrow it.

### Named Rules
**The Flat-On-Paper Rule.** No component ships a drop shadow. If a surface needs
distinction, step it (Surface Recessed), border it, or rail it.

## Shapes

Pill geometry (999px) marks everything small and interactive or categorical:
toggles, chips, ghost buttons, band chips. Rounded rectangles scale their radius
with prominence: 4px meter tracks, 8px inputs and definition slots, 10px
buttons, 12px answer panels, 14px KPI tiles, 16px cards, 20px the hero. Meaning
rides on border style: solid hairlines structure, a **dashed** border marks
stale/cached data, a **dotted** underline marks a tappable defined term, and the
notice block carries a 4px accent left bar — a caveat's shape, deliberately not
an error's red.

## Components

### Buttons
- **Primary (`.btn`):** Clear-Day Blue fill, white text, 10px radius, 11px 20px
  padding (14px 20px on touch), body-font 600. Used for Ask and persona Apply.
- **Pill button (`.pill-btn`):** ghost pill — transparent, Border Strong
  outline, Clear-Day Blue mono 11px label. The `.strong` variant takes the
  accent border, 600 weight, a 12.5px label (the same step the Devanagari
  floor gives it in Hindi) and an Accent Tint fill — a visible control, not a
  ghost, because it is the way into the persona editor. Plain `.pill-btn`
  stays the register for quiet actions.
- **Focus:** global 2px Clear-Day Blue outline, 2px offset; drawn inside
  (-3px, currentColor) within clipped pills and rounded lists.

### Chips
- **Band chip:** band tint background, Ink text, 1px band-ink border, pill,
  mono 11.5px 600. Always carries the band word.
- **Hero chips (`.chip-risk`, `.chip-base`):** translucent paper-white pills on
  the sky, mono 12px; risk is the firmer of the two.
- **Driver chips:** Surface Recessed pills, mono 11px, Ink 2 — the "why" behind
  a score.

### Cards / Containers
- **Corner Style:** 16px; hero 20px; answer panels 12px; KPI tiles 14px.
- **Background:** Surface on Paper; recessed elements use Surface Recessed.
- **Shadow Strategy:** none — see The Flat-On-Paper Rule.
- **Border:** 1px Border hairline on every card.
- **Internal Padding:** 16px (12px 14px on KPI tiles).

### Inputs / Fields
- **Style:** Surface background, Border Strong 1px outline, 8px radius, 13.5px
  body face; labels are mono 10px kickers above.
- **Focus:** the global focus ring.
- **Stale/empty:** dashed-border `.stale-note` with the last real measurement on
  its own mono line.

### Navigation
- **Style:** text links, Ink 3, 14px; the current page takes Ink at 600 with a
  2px Clear-Day Blue underline via `aria-current`. Theme and language are
  segmented pill controls; the active segment fills with the accent. All of it
  works without JavaScript.

### The Sky Hero (signature)
Full-width, 20px radius, min-height 330px. Layered: band gradient
(--sky1→--sky2), blurred sun disc, severity haze, legibility scrim, then the
content column — mono meta line (place, provenance pill), kicker, the verdict
sentence in Display 800, advice, risk chips. Anchored to its foot, a near-black
**hero-window** bar states the best time to go out: mono label, Anek 600 value,
its caveat on the same baseline. This is the one component allowed atmosphere;
its band variables come from `data-band` on the hero element.

### The Proof Register (System view)
KPI tiles, labelled meter bars, hour columns, and attempt logs — all mono,
flat, hairline-ruled, sized 9.5–11.5px. Deliberately reads as an instrument
panel so telemetry can never be mistaken for health advice.

## Do's and Don'ts

### Do:
- **Do** pair every severity colour with its band word and a position on the
  labelled scale (The Never-Colour-Alone Rule).
- **Do** keep new severity values luminance-monotone with severity in both
  themes, and measure contrast against the actual surface (4.5:1 for text,
  3:1 for non-text marks — the ratios live as comments next to the tokens).
- **Do** put every qualification in `.caveat` (`.on-tint` when it sits on a
  tint), and write competing descendant rules as `p:not(.caveat)`.
- **Do** set every measurement, timestamp, and label in the mono register, and
  keep `tabular-nums` global.
- **Do** give Hindi its floors: Anek Devanagari faces, ≥12.5px labels, normal
  tracking, no uppercasing, one weight step up on display headings.
- **Do** keep the 44px touch floor measured (font-size × line-height + padding
  + border), relaxing density only under `@media (pointer: fine)`.

### Don't:
- **Don't** add a box-shadow anywhere; step, border, or rail the surface
  instead.
- **Don't** use the CPCB rainbow or any green/red opposition as the page's
  colour system; the official hues may appear only in a small labelled
  reference row.
- **Don't** style honesty notices as errors — no red, no icon scolding; a
  caveat's shape (accent bar, Surface Recessed) is the register for trust
  statements.
- **Don't** write inline `style` font sizes in templates; sizes live in
  classes so the `:lang(hi)` floors can reach them.
- **Don't** letter-space or uppercase Devanagari, ever.
- **Don't** render the wordmark gloss as a tagline: "clean breath" is a
  translation, one visual step below the Devanagari it translates, English
  pages only — never "Breathe clean".
