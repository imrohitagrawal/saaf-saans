# SaafSaans — Design Plan (v2)

Self-review note (pass 1 → pass 2): my first-pass layout was a hero card + KPI strip + chat panel — I would have drawn the same thing for a crypto dashboard. Changed: killed every card, killed the sidebar/tab shell, led with a *sentence* instead of a number, made severity an **ink-density axis** instead of a hue ramp, and split resident vs. system surfaces into two visual registers. What follows is pass 2.

---

## 1. Design rationale (concept)

**Haze is ink.** Polluted air is not a color — it is *density*: more particles per cubic metre, less light gets through. The interface encodes severity the same way breath experiences it: as accumulating density. On paper (light theme) severity is progressively darker ink; at night (dark theme) it is progressively brighter scatter — so severity **is** contrast, monotonically, in both themes, which is exactly what the CPCB rainbow fails at. The signature "specimen" renders a measured µg/m³ as literal dot density, so the number is felt, not just read.

The page itself is a **bulletin, not a dashboard**: one ruled column that opens with the answer in words — *"High risk — avoid outdoor exertion today"* — because the user's question ("is it safe for me?") is linguistic, not numeric. Every competitor leads with a colored circle and a number; leading with a verdict sentence is the one aesthetic risk here, and it is justified by the five-second test. The density language extends directly to v2's inhaled-dose metric: dose = dots accumulated over a day.

## 2. Three directions

**A — The Bulletin (recommended).** A single ruled reading column, verdict-first, like a public-health notice written by someone honest. No cards, no sidebar, no tabs. Persona rides in a sticky strip. System views live in a separate mono-typeset "proof" register at the foot.

```
375px
┌──────────────────────────┐
│ SaafSaans        ◐ theme │
│ FOR: adult · asthma ·    │  ← sticky persona strip
│ outdoor exercise · A.V.  │
├──────────────────────────┤
│ RIGHT NOW · 2:00 PM ·LIVE│
│ High risk — avoid        │  ← the answer, in words
│ outdoor exertion today.  │
│ Skip outdoor exercise…   │
│ IF YOU MUST GO —         │
│ Late morning, 9 AM–12 PM │  ← the "when", same viewport
├──────────────────────────┤
│ SAME AIR, DIFFERENT LUNGS│
│ 0───44────56────────100  │  ← ambient vs personal delta
├──────────────────────────┤
│ THE AIR · Anand Vihar    │
│ 191 Moderate  [specimen] │
│ scale ▲ · PM2.5 · PM10   │
├── outlook ── ask ────────┤
│ SYSTEM PROOF (mono)      │
└──────────────────────────┘
```

**B — The Split Ledger.** Two facing columns: THE AIR (ambient, instrument register) | YOUR LUNGS (personal, prose register), delta drawn between them.

```
┌───────────────┬───────────────┐
│ THE AIR       │ YOU           │
│ 191 Moderate  │ 56 High       │
│ PM2.5 · PM10  │ advice, when  │
└──────── delta bridge ─────────┘
```
Rejected: on 375px the columns stack and "when to go out" lands below the fold — fails the five-second test on the device most users hold.

**C — The Day Spine.** The page is a vertical 24-hour timeline; the now-marker, the best window, and the forecast hang off the spine.
```
6am ─┬─ …
9am ─┼─ ▓ BEST WINDOW
2pm ─┼─ ● NOW · AQI 191 · verdict
6pm ─┴─ …
```
Rejected: it renders the best-time window as if it were an hourly station forecast, which the product explicitly says it is not. The layout would be *lying about precision* — the honesty in §3.3's rationale is a design asset to preserve, not paint over.

**Winner: A**, borrowing C's hour-band only as text ("about 9 AM–12 PM"), never as a plotted curve.

## 3. Design tokens (all ratios measured, WCAG 2.x)

Canvas light `#F0F4F5` · canvas dark `#0F1519`.

| token | light | ctr | dark | ctr |
|---|---|---|---|---|
| text | `#1A2024` | 14.86 | `#E2E9EB` | 14.97 |
| text-2 | `#4E575D` | 6.67 | `#A4ACB1` | 7.98 |
| text-3 | `#646D74` | 4.76 | `#7F888C` | 5.08 |
| accent (links/actions) | `#0D5A79` | 6.88 | `#7DC3DE` | 9.40 |
| surface | `#F8FBFB` | — | `#171E22` | — |
| border | `#D5DCDE` | — | `#2A3137` | — |

**Severity ramp** — six CPCB bands on one perceptual axis: lightness monotone (darker = worse on paper, brighter = worse at night), hue drifting clear-sky blue → violet → oxblood. No green/red opposition; order survives deuteranopia because *contrast alone* carries it. Ratios vs. each canvas:

| band | light | ctr | dark | ctr |
|---|---|---|---|---|
| Good | `#588FA9` | 3.21 | `#1D6E8E` | 3.22 |
| Satisfactory | `#536EA0` | 4.62 | `#5E7FBB` | 4.58 |
| Moderate | `#625292` | 6.04 | `#9A88D3` | 5.99 |
| Poor | `#6C356E` | 7.99 | `#CA93CB` | 7.49 |
| Very Poor | `#63203C` | 10.52 | `#E6AABD` | 9.50 |
| Severe | `#4D1111` | 13.51 | `#F2C7C2` | 12.02 |

Good (3.2:1) is used only for large text and marks, never body copy. Each band also has a tint for chips (e.g. light Moderate ink on tint: 5.40; Severe on tint: 12.10 — all ≥4.5 except Good, which is chip-marked with a label, never text-on-tint). Severity is always paired with the band word and a position on the labeled scale — never color alone. Personal-risk bands map Low→1, Moderate→2, High→4, Very High→5, Extreme→6.

The official CPCB hues may appear in one small labelled reference swatch row for familiarity; they are not the page's color system (EPA's ColorVision Assist is the precedent for deviating).

## 4. Typography

- **Display — Anek Latin** (Ek Type, Mumbai). Designed as one superfamily with Anek Devanagari: when Hindi UI ships, headlines keep identical weight and rhythm. Condensed-ish, high x-height — reads in sunlight. Weights 600–700.
- **Body — IBM Plex Sans**, 400/600, `font-feature-settings: "tnum"` globally so inline figures never shift.
- **Numeric & system register — IBM Plex Mono**, 400–600. All data numerals, timestamps, provenance, and the entire Observability/Security register. Inherently tabular.

Scale (mobile → desktop): verdict 30→42/1.12/-0.01em Anek 700 · section head 20→24/1.2 Anek 600 · AQI numeral 56→68 Mono 600 · body 15→16/1.55 Plex 400 · secondary 13.5/1.5 · kicker 11/0.08em caps Mono 500 · data cell 14 Mono. Not Inter, per brief; the pairing is justified by script coverage (Anek↔Devanagari) and instrument-grade numerals (Mono), not by fashion.

## 5. Layout & hierarchy

Hierarchy: **1)** verdict sentence + personal band, **2)** best window, **3)** ambient↔personal delta, **4)** the reading (AQI, pollutants, specimen, scale), **5)** outlook, **6)** ask, **7)** city strip, **8)** proof register. **Cut:** token spend, latency, station map, gauge of any kind — from the resident surface entirely (they live in the proof register / Observability).

375px: see §2A. Desktop (≥900px): the same single column, 700px measure, centered; the reading section alone widens into a two-column row (numbers | specimen). A bulletin does not become a dashboard on a bigger desk.

City view (separate destination):
```
┌ CITY · 21 stations · 3 PM ────────────┐
│ sorted worst-first, one row each:     │
│ Wazirpur      204 ▪ Poor              │
│ Anand Vihar   191 ▪ Moderate ← you    │
│ Okhla         176 ▪ Moderate · CACHED │
│ …                                     │
│ [24h trend, selected station: sparkline
│   inline SVG, ink = band of each hour]│
└───────────────────────────────────────┘
```
Rows, not tiles: ranking is the information. Density strip per row optional at ≥900px.

## 6. Component specs

**Air reading.** Kicker (station + provenance chip) / AQI numeral (Mono 600) + band chip (tint bg, ink text, band word) / observed time / meaning sentence / labeled position scale (six segments, proportional widths 10-10-20-20-20-20%, ▲ marker with mono value; thresholds 0·50·100·200·300·400·500 beneath) / pollutant row (PM2.5, PM10 + DOMINANT tag). States: live · stale (chip swaps to dashed CACHED + notice line) · feed-down (no reading: scale unmarked, verdict computed from last cached sample, dated loudly).

**Personal risk.** Band chip (word + score /100, tint+ink) + headline (the page's H1) + advice + drivers list ("what's driving your 56"). Never a gauge. States per band; Extreme swaps chip to solid ink with canvas-colored text.

**Best-time module.** Mono kicker "IF YOU MUST GO OUT" / window in Anek 600 / rationale in text-3 *including the honesty sentence verbatim*. State: no-window ("None today — recheck tomorrow morning") in Severe episodes.

**Station tile (row).** Name · Mono AQI · band square + band word · optional CACHED tag. 44px min height. Selected row: 2px ink inset.

**Answer.** "Q ·" mono prefix + question in 600 / sections as small-caps mono headings (verdict, what to do, why, when to seek help) with paragraph or bullets / footnote "general guidance, not medical advice" / provenance disclosure (below).

**Provenance indicator.** One grammar everywhere: `● LIVE · 2:00 PM` (solid dot, accent), `◌ CACHED · 2:00 PM` (dashed chip, Satisfactory ink), `≈ ESTIMATED / RULE-BASED` (tilde prefix). The answer's "What the app used" is a real `<button aria-expanded>` opening a mono panel: grounding reading + its status, then each retrieved advisory as source-tag + one-line content.

**Refusal.** Flat surface-2 block, no red, no icon-scolding: "Not processed." + one plain sentence of why + what *is* answerable; mono footer "blocked before the model · audited (security-events)". Matter-of-fact.

**Definitions (3.4b).** Terms (AQI, PM2.5, PM10, dominant pollutant, personal risk) are dotted-underline `<button aria-expanded>` on the term text itself — no extra glyph per number. Opening one fills a single shared definition slot directly beneath that section (one slot per section = no noise multiplication). Long-form lives on a separate page; the one-liner never leaves the screen.

## 7. Information architecture

Four destinations, two registers:
- **Resident register (proportional type, prose):** *Today* (default, everything above) and *City* (21 stations + trend).
- **Proof register (mono, flat, hairline-ruled):** *Observability* and *Security*, entered from a persistent "SYSTEM PROOF" strip at the foot of every resident page. The strip is not a link farm — it *states the day's honesty first* ("live feed missed 4×, cached samples shown and marked · 3 injection attempts blocked before the model") and then links. So the proof surfaces are peer destinations, discoverable and demonstrable to an evaluator, but typeset in an instrument register that visibly is-not the health advice — weight solved by register, not by hiding. No tabs, no sidebar.

## 8. Signature element

**The specimen** — a bordered square of "air" whose dot count is the measured PM2.5 (1 dot = 2 µg/m³), always shown against a WHO-guideline square (15 µg/m³, 8 dots) at the same scale. Today: 8 dots vs 81. It encodes a true physical quantity (particle mass per volume), works in both themes (ink on paper / scatter at night), survives every color-vision deficiency (density, not hue), reappears at row scale in the outlook table, and is the exact visual grammar v2 needs: **inhaled dose = the dots you collected today**, segmented by activity. It is the one thing a user will describe to someone else: "the app shows you the air."

## Assumptions & deviations
- Outlook rows (§3.4) aren't specified numerically in the brief; mockup uses plausible values consistent with today's 162 µg/m³, marked as forecast.
- Mockup includes a city *strip* (worst stations + link), not the full city view — brief asks for the main screen only.
- Interactive mockup adds minimal JS (theme, disclosures); page reads fully without it, per the progressive-enhancement constraint.
