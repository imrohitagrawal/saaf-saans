# Handoff: SaafSaans — Delhi Air-Quality & Public-Health Companion (UI v4)

## Overview
SaafSaans answers one question in under five seconds: **"Is it safe for *me* to go outside right now, and if not, when?"** A user sets a persona (age, health condition, planned activity, locality); the app shows the live AQI, a personal 0–100 risk score, the best time-window to go out, and answers plain-language questions grounded in retrieved health advisories — with full provenance. Two "proof" surfaces (Observability, Security) demonstrate that the advice is grounded, degraded-honest, and guarded.

This bundle documents the final approved UI (v4): **the sky is the interface** — a rendered sky hero whose haze matches the reading, editorial verdict typography, human voice copy.

## About the Design Files
The files in this bundle are **design references created in HTML** — interactive prototypes showing intended look and behavior, **not production code to copy directly**. The task is to recreate these designs in the target codebase: **FastAPI + Jinja2 templates, hand-written semantic HTML + CSS (custom properties), vanilla JS as progressive enhancement — no React, no Tailwind, no build step.** The page must be fully readable before any JS runs; JS only adds tab switching without reload, disclosure toggles, and the red-team simulation. Server-side render everything; charts are inline SVG generated server-side.

- `SaafSaans v4.dc.html` — the approved design (all three views, light + dark). Open in a browser to inspect (needs `support.js` beside it).
- `Hero Options.dc.html` — the three explored moods (1a atmospheric / 1b editorial / 1c warm); final = blend.
- `Design Plan.md` — earlier design rationale/background (an earlier "bulletin" direction; superseded by this README where they differ).

## Fidelity
**High-fidelity.** Colors, type, spacing, radii, copy, and states are final. Recreate pixel-perfectly with the codebase's Jinja2/CSS patterns. All numeric data shown is real sample data from the product's data model (WAQI reading, risk.py-style scoring, ES telemetry).

## Design Tokens (CSS custom properties)

### Light (default) / Dark
| token | light | dark | use |
|---|---|---|---|
| --bg | #F2F1EE | #12151C | page canvas |
| --surface | #FBFAF8 | #1B1F28 | cards |
| --surface-2 | #E9E7E2 | #232834 | insets, bar tracks, refusal block |
| --border | #DCD9D2 | #2B303B | card borders, row rules |
| --border-s | #C2BEB4 | #3D4350 | control borders |
| --text | #211E19 | #E8E6E1 | primary text |
| --text-2 | #57524A | #ABA79E | secondary text |
| --text-3 | #6B665D | #8B877E | captions, kickers |
| --accent | #2F5D8A | #8FB8DC | links, active nav, buttons, sparkline |
| --accent-tint | #DCE7F1 | #1C2938 | selected row bg, sim notice |
| --on-accent | #FFFFFF | #12151C | text on accent |

### Severity ramp (CPCB bands = the real colours of a Delhi sky: clear blue → dust ochre → smog maroon)
Never convey severity by colour alone — always paired with the band word and/or position on the labeled scale.

| band | ink light | ink dark | tint light | tint dark |
|---|---|---|---|---|
| Good (0–50) | #2F6FB5 | #7FB2E8 | #DCE9F6 | #1C2938 |
| Satisfactory (51–100) | #3F7180 | #7FBFCB | #DAEAEE | #1B2C31 |
| Moderate (101–200) | #8A5A0E | #E0A94F | #F3E4C4 | #322815 |
| Poor (201–300) | #9C4519 | #E88650 | #F6DFD2 | #362216 |
| Very Poor (301–400) | #8A2A26 | #EE7B70 | #F4D9D7 | #351D1B |
| Severe (401–500) | #58150E | #F3B7A5 | #EFD7D2 | #3A1F18 |

### Sky (hero) tokens
- Light/day: gradient 180deg #7D93A6 → #C4AD8B; sun disc #FFE9C4; haze overlay rgba(120,105,85,0.35)
- Dark/night: gradient #232C44 → #4A3B33; disc #D8DCE8; haze rgba(30,26,22,0.35)
- These values are for the current Moderate reading; conceptually the sky pair should shift with the band (clearer/bluer for Good, browner/denser haze for Severe). v1 may ship the Moderate pair only.

### Spacing / radius / misc
- Spacing: 4, 8, 10, 12, 14, 16, 20, 22px paddings as used inline; card gap 16px; KPI gap 10px.
- Radius: cards 16px; hero 20px; KPI tiles 14px; inputs/buttons 8–10px; chips/pills 999px; scale bar & bar tracks 4px.
- Shell: max-width 1120px, side padding 20px. Content grid: `grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px` (KPIs: minmax(150px,1fr)).
- `font-variant-numeric: tabular-nums` on the root — digits must not shift between refreshes.
- Focus: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }`. Respect `prefers-reduced-motion` (design uses no decorative motion).

## Typography
Google Fonts, three families:
- **Anek Latin** (display; 600/700/800) — headlines, section titles, the verdict, "Late morning" window. Chosen because it ships as a superfamily with Anek Devanagari for future Hindi support.
- **IBM Plex Sans** (body; 400/500/600/700) — all body copy, nav, buttons.
- **IBM Plex Mono** (400/500/600) — every data numeral, timestamp, kicker/eyebrow, provenance line, chip label, and the entire System register.

Scale: verdict h1 clamp(28px, 5vw, 42px)/1.08, weight 800, letter-spacing −0.015em · page h1 26px/700 (Anek) · section h2 20px/600 (Anek) · AQI numeral 46px/600 mono, −0.02em · KPI value 22px/600 mono · body 15px/1.55 · secondary 13.5px · captions 11.5–12px · kickers 10–11px mono, uppercase, letter-spacing 0.08–0.14em.

Wordmark: "SaafSaans" Anek 800 21px + "साफ़ साँस" 13px in --text-3 (header only; rest of UI is English).

## Screens / Views

### Navigation shell (all screens)
Sticky top header (bg --bg, 1px bottom border): wordmark left; nav right: Today / City Pulse / System as text buttons (14px; active = weight 600, --text, 2px --accent underline; inactive = --text-3); Day/Night segmented pill (mono 11px; active side filled --accent). Wraps gracefully at 375px. Footer on every view (11px, --text-3): "Persona stays in session — never logged; telemetry keeps a hashed id only. Data: WAQI/CPCB · advisories: CPCB, WHO, GINA, GOLD, AHA, ACOG, EPA."

### 1 · Today (default)
Grid; hero and Ask span full width (`grid-column: 1 / -1`); persona, reading, outlook cards flow 1-col mobile → 2-col desktop.

**Sky hero** (radius 20, min-height 330, gradient sky): blurred sun disc top-right (68px circle, blur 10px, opacity .55); haze overlay; bottom scrim `linear-gradient(180deg, rgba(10,12,16,0) 24%, rgba(10,12,16,0.7) 84%)`; text #F7F3EC, max-width 720px. Content bottom-aligned:
1. Meta row (mono 11px, ls .08em): `ANAND VIHAR` · provenance chip `● LIVE · 2:00 PM` (opacity .75) · pill `AQI 191 · MODERATE` (bg rgba(247,243,236,.16), 1px border rgba(247,243,236,.35)).
2. Persona kicker (mono 11px, ls .14em, opacity .85): `FOR AN ADULT WITH ASTHMA, PLANNING OUTDOOR EXERCISE` — regenerated from persona.
3. Verdict h1 (voice is human, facts unsoftened) — per band: LOW "A good day to breathe — enjoy it outside." · MODERATE "Manageable for you today — just pace yourself." · HIGH "Today isn't kind to your lungs — keep it indoors." · VERY HIGH "Your lungs need you indoors today." · EXTREME "Don't go out unless you must — this air is dangerous for you."
4. Advice line 15px, opacity .92 (e.g. HIGH: "Skip outdoor exercise. Keep trips short and wear an N95 outside.").
5. Chips (mono 12px): `YOUR RISK · 56/100 · HIGH` (filled rgba(247,243,236,.18) + border) · `healthy adult · 44` (bg rgba .12).

**"If you must go" bar** — anchored to hero base, full hero width: bg rgba(12,13,15,.85), text #F5F4F0, padding 12px 22px: kicker `IF YOU MUST GO OUT` (mono 10px ls .12em, opacity .7) + `Late morning · 9 AM–12 PM` (Anek 600 17px) + "a general pattern, not an hourly forecast" (12px, opacity .65). Severe episodes: window text becomes "None today — recheck tomorrow morning."

**Stale state** (feed down): provenance chips swap to `◌ CACHED · 2:00 PM`; a dashed-border notice card appears under the hero: "Live feed is down — this sky and advice use the last good reading, from 2:00 PM, and will refresh when the feed returns." Never disguise cached as live.

**Persona card**: kicker `CARING FOR` + "Adult · asthma · outdoor exercise · Anand Vihar" + `Change` pill button (aria-expanded) revealing 3 selects (Age: Child/Adult/Senior · Health: None/Asthma/Heart condition/Pregnancy/COPD · Plan: Outdoor exercise/Commute/School run/Stay home) + privacy note "Stays in this session only — never logged." Below: comparison line — gap>0: "A healthy adult in this air would be at 44. Your 56 comes from your asthma + outdoor exercise — the gap is your body and plans, not the air."; gap 0: "…that's you today."; negative: "Staying in brings you to 38 — below the healthy-adult 44. Good call." Then driver chips (mono 11px, bg --surface-2): "AQI 191 · Moderate", "Outdoor exercise multiplies dose", "Asthma raises risk", etc.

**Reading card**: `191` (46px mono) + `MODERATE` chip (tint bg, band ink) + `AQI · CPCB · 2:00 PM` (AQI is a dotted-underline term button). Position scale: 6 segments (widths 10/10/20/20/20/20% for 0-50-100-200-300-400-500) in band inks, `191 ▾` marker at 38.2%, endpoint labels "0 good / 200 / severe 500". Pollutants: PM2.5 162 µg/m³, PM10 191 µg/m³ + "· DOMINANT" (both term buttons). Meaning line: "Acceptable for most. Sensitive groups (asthma, heart/lung conditions, kids, seniors) should take it easy on heavy exertion."
**Term definitions**: term words are real `<button aria-expanded>` with 1px dotted underline; toggling shows a one-line definition in a shared inset slot (bg --surface-2, radius 8) inside the card; opening one closes another. Definitions: AQI "one 0–500 number summarising all pollutants on India's CPCB scale. Higher is worse." · PM2.5 "fine particles under 2.5 micrometres that reach deep into the lungs. Delhi's main health concern." · PM10 "coarser dust under 10 micrometres; irritates the airways. Today's biggest share."

**Outlook card**: kicker `PM2.5 · NEXT FIVE DAYS`; 5 rows (grid 96px/36px/1fr): day (today bold), avg (mono 600), horizontal bar (track --surface-2, fill --g3 Moderate ink, width = avg/220). Data: Sun 19 · today 158 / Mon 20 142 / Tue 21 165 / Wed 22 171 / Thu 23 149. Caption: "Daily averages, µg/m³ · WAQI forecast — a coarse outlook, not an hourly promise."

**Ask card** (full width): title + "grounded in the reading above · written for your persona". Desktop: answered Q left (flex 3), refusal right (flex 2); mobile stacks. Q line: mono `Q ·` prefix + bold question. Answer block (1px border, radius 12): sections with mono kickers VERDICT / WHAT TO DO / WHEN TO SEEK HELP (paragraphs or bullet lists, 13.5px --text-2), footnote "General guidance, not medical advice." Footer bar: `▸ WHAT THE APP USED` button (aria-expanded) opening the provenance panel: grounding line "AQI 191 · PM2.5 162 · dominant PM10 · live reading · 2:00 PM IST" (says "cached sample (feed missed)" when stale) + advisory rows: bordered source tag (mono 10.5px, radius 4) + one-line content — GINA-guidance, WHO-AQG-2021 (sources: CPCB-AQI-scale, GINA-guidance, AHA-airpollution, WHO-AQG-2021, ACOG-airquality, GOLD-guidance, EPA-indoor-air).
**Refusal state** (blocked injection): flat --surface-2 block, no red, no icon: bold "Not processed." + "That looked like an attempt to change how the assistant works, so it was stopped before reaching the model. Air, precautions, masks, timing — all fair game." + mono footer "blocked pre-model · audited in security-events".
Input row: text input (placeholder "Ask about going out, masks, timing, symptoms…") + filled `Ask` button (--accent).

### 2 · City Pulse
H1 + "20 stations · 3:00 PM · median AQI 173 · worst first". Grid auto-fit: trend card + DELHI list + NCR list.
**Trend card**: selected station name + `LAST 24 H · AQI` + current value; inline SVG sparkline (stroke --accent 2px, area fill currentColor at .12 opacity, dot on the "now" hour); x-labels 12 AM / 6 AM / 12 PM / 6 PM / NOW; caption "Delhi pattern: overnight build-up, mid-day relief. Tap a station to see its curve."
**Station rows** (each a full-width button, min-height 46px, top-ruled): band dot (9px circle, band ink) · name · optional `CACHED` tag (mono 10px) · AQI (mono 600) · band word right-aligned in band ink. Selected row: bg --accent-tint, name weight 600. Sorted worst-first. Delhi: Wazirpur 204 Poor, Jahangirpuri 198, Anand Vihar 191, Nehru Nagar 187, Ashok Vihar 181, Okhla 176 (CACHED), Punjabi Bagh 173, ITO 168, Patparganj 164, DTU 156, Rohini 152, RK Puram 147, Dwarka 143, Mandir Marg 138, Najafgarh 121. NCR: Ghaziabad 210 Poor, Greater Noida 189, Noida 172, Faridabad 166, Gurugram 158.

### 3 · System (Observability | Security)
H1 + "The app audits itself — grounded, degraded-honest, and guarded. Watch it here." Segmented pill control (max-width 420px) switches the two registers. This register is deliberately mono-heavy and flat — visibly *not* the health-advice voice.
**Observability**: KPI tiles (auto-fit minmax 150px): 142 questions answered · 0.9 s median response · 2.1 s p95 response · 4 (2.8%) feed misses → cached · 6 rule-based fallbacks · 48.2k tokens spent. Two bar cards (grid 118px/1fr/34px rows; track --surface-2, radius 4): EVENTS BY TYPE (advice_served 142 in --accent, feed_fallback 4, llm_fallback 6, injection_blocked 3) with caption "Fallbacks are logged, never hidden — 4 cached readings and 6 rule-based answers were shown as such today."; REQUESTS BY LOCALITY (fills --g3): Anand Vihar 48, Rohini 26, RK Puram 21, ITO 17, Dwarka 13, other 17.
**Security**: KPI tiles: 3 blocked today · 100% stopped pre-model · 9 distinct patterns. BLOCKED · LAST 7 DAYS: column mini-bars (fill --g5, radius 4 top) Mon 4 Tue 7 Wed 2 Thu 9 Fri 6 Sat 8 Sun 3, value above, day below. RECENT BLOCKED ATTEMPTS: rows = pattern chip (bg --n5, ink --g5, radius 4: prompt-extract / ignore-previous / role-override) + italic quoted excerpt + "2:04 PM · blocked pre-model". Header has `▸ Run red-team simulation` outline pill: on click, POST to the guard demo endpoint (attack_demo), then show notice "Simulation fired 3 known attack prompts at the guard — all blocked before the model, logged below.", prepend 3 rows ("just now"), bump today/Sun counters.

## Interactions & Behavior
- Tabs and the System segment switch without reload where JS is available; each view must also be server-renderable at its own URL (progressive enhancement).
- All disclosures (Change persona, term definitions, WHAT THE APP USED) are `<button aria-expanded>`; never hover-only.
- Changing persona recomputes score/band/verdict/kicker/drivers/comparison instantly (see State).
- City station row click selects it and re-renders the sparkline (server-side: link + re-render).
- No decorative animation. Transitions if added: opacity/transform ≤200ms, disabled under prefers-reduced-motion.
- Fully usable at 375px; hit targets ≥44px.

## State Management
- `persona {age, condition, activity, locality}` — session-only, never logged (telemetry stores hashed session id only).
- `theme` light|dark (default light; persist preference), `tab`, `systemSegment`, `selectedStation`, open/closed flags for the three disclosure types, `simFired`.
- **Risk model (UI contract; real source is services/risk.py):** score = base(AQI for healthy adult; 44 at AQI 191) + condition {None 0, Asthma +8, Heart +10, Pregnancy +6, COPD +14} + activity {Outdoor exercise +4, Commute +1, School run +2, Stay home −6} + age {Child +4, Adult 0, Senior +6}. Bands: <30 LOW, <45 MODERATE, <60 HIGH, <75 VERY HIGH, else EXTREME.
- Data fetches: current reading (WAQI, `stale` flag must drive the CACHED treatment), forecast outlook, station list + 24h series (ES), telemetry & security aggregations (ES metrics).

## Assets
No image assets. Sky, sun disc, haze = pure CSS gradients + a blurred circle div. Charts = inline SVG. Fonts from Google Fonts (Anek Latin, IBM Plex Sans, IBM Plex Mono).

## Files
- `SaafSaans v4.dc.html` + `support.js` — approved interactive design (open v4 in a browser)
- `Hero Options.dc.html` — explored directions (context)
- `Design Plan.md` — earlier rationale document (background)
