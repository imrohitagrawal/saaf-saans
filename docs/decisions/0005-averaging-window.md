# 0005 — The averaging window: CPCB, WAQI and OpenAQ do not publish the same quantity

**Status: RESOLVED 2026-07-21**, by measurement, for the window question. One residual
question — a systematic PM2.5 magnitude gap between CPCB and OpenAQ — is **UNRESOLVED**
and recorded as such below.

The finding, in one line each:

* **CPCB `avg_value` on data.gov.in is a rolling 24-hour mean**, republished hourly.
* **WAQI's `iaqi` values are US EPA sub-indices of the latest hourly concentration** —
  a roughly instantaneous quantity, not a daily mean.
* **OpenAQ's measurements are 15-minute instantaneous concentrations.**

They are **three different quantities**. The app's index scale is India's CPCB AQI, which
is defined on 24-hour averages. So the CPCB path feeds the scale the quantity it was
designed for, and the WAQI fallback path does not.

## Assumptions going in

1. That the divergence measured before this work (CPCB pm25 vs OpenAQ pm25 — RK Puram
   39/9, Anand Vihar 90/33, Dwarka 112/36.7, ITO 51/22, DTU 45/23) was a *window*
   difference. **Partly wrong.** Most of it is a window difference. A residual factor of
   about 1.7 on PM2.5 is not, and is still unexplained.
2. That `min_value` / `max_value` would be uninformative. **Wrong, and they turned out to
   be the decisive evidence.** They fingerprint the window.
3. That the documentary record would settle it. **Wrong in practice** — see
   "What could not be done".

## Analysis

### The method

A window cannot be read off a single number. It can be fingerprinted: if `avg_value` is
the mean of a source's own sub-hourly series over the last 24 hours, then `min_value` and
`max_value` must equal the **minimum and maximum of that same series over that same
window** — and a min/max pair is far harder to match by coincidence than a mean is.

OpenAQ publishes the raw 15-minute series for the same CPCB/DPCC stations. So: pull
OpenAQ's raw measurements for the trailing 25 hours, reduce them to mean/min/max, and
compare against CPCB's published triple for the same station in the same minute.

### Data point 1 — PM10 fingerprints the window exactly, 5 stations of 5

Delhi, 21 July 2026, CPCB `last_update` 21:00:00 IST. CPCB `(avg, min, max)` against
OpenAQ raw 15-minute `(mean, min, max)` over the trailing 24 hours:

| Station | pollutant | CPCB avg/min/max | OpenAQ 15-min mean/min/max |
|---|---|---|---|
| R K Puram | PM10 | 69 / 27 / 114 | 68.7 / **27.0** / 121 |
| ITO | PM10 | 62 / 11 / 110 | 61.4 / **10.0** / 117 |
| NSIT Dwarka | PM10 | 83 / 52 / 107 | 80.9 / **52.3** / 111 |
| DTU | PM10 | 49 / 11 / 109 | 49.9 / **11.0** / 116 |
| Anand Vihar | PM10 | 93 / 39 / 154 | 97.0 / **39.0** / 173 |

The means agree to within 4%. The **minima agree to the unit at four stations of five**
(27, 52, 11, 39) and to 1 µg/m³ at the fifth. A 24-hour window is the only window that
produces that. The maxima run 5–12% below CPCB's, in the direction and magnitude expected
from OpenAQ's series being ingested at 15-minute resolution with occasional gaps — a
missed spike lowers a maximum but barely moves a mean or a minimum.

Reducing the same OpenAQ data to *hourly* means instead of raw 15-minute values pushes
the maxima further down (RK Puram PM10 121 → 121, Anand Vihar 173 → 161) and leaves the
means unchanged, which is the expected behaviour of smoothing and is why the raw series
is the one quoted above.

**Conclusion: `avg_value` is a 24-hour mean.** It is rolling and republished hourly, not
fixed to a calendar day: `last_update` advanced hour by hour during this work, and the
values moved with it (RK Puram PM2.5 39 → 37, NSIT Dwarka 112 → 108 across the session).

### Data point 2 — WAQI is the latest hour, not the day

For each station where the WAQI feed's own name matches the OpenAQ station name *and*
WAQI's timestamp is the current hour, WAQI's `iaqi` inverted through the EPA table
(`aqi_scale.concentration`, the inversion the app already performs) against OpenAQ:

| Station | pollutant | WAQI iaqi → µg/m³ | OpenAQ latest hour | OpenAQ 24h mean |
|---|---|---|---|---|
| R K Puram | PM2.5 | 36 → **8.6** | **9.0** | 20.4 |
| R K Puram | PM10 | 37 → **40.0** | **38.0** | 68.9 |
| Mandir Marg | PM2.5 | 5 → **1.2** | **1.0** | 15.6 |
| Mandir Marg | PM10 | 59 → **72.0** | **70.0** | 65.5 |
| Patparganj (Mother Dairy) | PM2.5 | 38 → **9.1** | **9.0** | 21.8 |
| Patparganj (Mother Dairy) | PM10 | 40 → **43.2** | **44.0** | 54.9 |

Six comparisons of six land on the latest hourly value, within 1–2 µg/m³. Mandir Marg
PM2.5 is the decisive one: WAQI says 1.2, the latest hour is 1.0, and the 24-hour mean is
15.6 — thirteen times apart. WAQI cannot be publishing a daily mean.

This also confirms, independently, the inversion `aqi_scale` performs. If `iaqi` were a
concentration rather than an EPA sub-index, RK Puram PM2.5 would read 36 µg/m³ against an
observed 9.0. Inverted, it reads 8.6. The module's existing claim is now measured, not
only cited.

### Data point 3 — OpenAQ's own metadata

Sensor 12234787 (R K Puram PM2.5) reports `expectedInterval: "01:00:00"` with observations
at :00/:15/:30/:45 and `latest` stamped `2026-07-21T19:45:00+05:30` — a point value at an
instant, with no averaging field of any kind. `datetimeFirst` is 2025-02-18. Nothing in
the sensor record describes an averaging period for the measurement itself.

### What this means for the app's own number

The app's index is CPCB-scale. India's National AQI defines its PM sub-indices on 24-hour
averages. Therefore:

* A **CPCB-sourced** reading feeds the scale a 24-hour mean. Correct by construction.
* A **WAQI-sourced** reading feeds the scale a single hour. **The scale is being given a
  quantity it is not defined on.** An hourly value put through a 24-hour breakpoint table
  yields a number that is not an AQI on any published method — it swings with the traffic
  peak in a way a daily index cannot.

This is not hypothetical: WAQI is the fallback, and on this day it was the live source
for Wazirpur.

## What changed our mind

Three things.

1. **`min_value`, not `avg_value`, settled it.** The whole question had been framed around
   comparing averages, and averages are weak evidence — many windows produce a similar
   mean on a flat day. The minimum of a 24-hour window is a specific number that a
   1-hour or 8-hour window will almost never reproduce. Four exact matches ended the
   argument in one query.
2. **The prior reading of the evidence was wrong about direction.** The pre-existing
   measurements compared CPCB against OpenAQ's *latest* value and read the gap as
   "CPCB is inflated". Against the correct comparand — OpenAQ's 24-hour mean — CPCB PM10
   is not inflated at all; it matches. The gap was mostly the window.
3. **WAQI turned out to be the misfit, not CPCB.** The concern in the brief was that CPCB
   might be the odd one out. It is the opposite: CPCB is the source whose window matches
   the scale the app publishes on, and WAQI is the one that does not.

## What we kept

* **CPCB stays the primary source.** This work strengthens rather than weakens that
  choice: its window is the one the CPCB scale is defined on.
* **WAQI stays as the fallback**, and the EPA→concentration inversion stays exactly as it
  is — Data point 2 confirms it empirically.
* **No number is grafted from one source into another.** The two sources publish
  different quantities; averaging or substituting across them would manufacture a figure
  that no instrument measured.

## The residual, unresolved: PM2.5 magnitude

PM10 matches. **PM2.5 does not**, at all five stations, in the same query:

| Station | CPCB avg / min / max | OpenAQ 15-min mean / min / max | ratio of means |
|---|---|---|---|
| R K Puram | 37 / 3 / 92 | 21.6 / 2.0 / 55.0 | 1.71 |
| ITO | 51 / 16 / 89 | 30.1 / 9.0 / 59.0 | 1.69 |
| NSIT Dwarka | 108 / 46 / 172 | 55.6 / 27.7 / 81.5 | 1.94 |
| DTU | 44 / 15 / 92 | 26.7 / 9.0 / 62.0 | 1.65 |
| Anand Vihar | 88 / 53 / 161 | 49.0 / 32.0 / 76.0 | 1.80 |

**This is not a window difference, and the min/max columns are why.** A longer window
lowers a minimum and raises a maximum; it does not scale all three of min, mean and max by
the same factor. Here the minima scale by 1.50–1.78 and the means by 1.65–1.94 — the whole
distribution is multiplied, which is the signature of a calibration, correction-factor or
instrument-channel difference between the two sources' PM2.5 series, not of a different
averaging period.

**We do not know which figure is right, and we are not guessing.** WAQI agrees with
OpenAQ on instantaneous PM2.5 (Data point 2), but WAQI and OpenAQ both mirror the same
real-time upstream, so their agreement is one opinion and not two. Resolving this needs a
source independent of that stream.

Note what this does *not* undermine: the window finding rests on PM10, where the two
sources agree in magnitude, and PM2.5's minima scale in lockstep with its means, which is
itself evidence that both series cover the same 24 hours.

## What could not be done

The documentary half of this investigation failed and is reported as failed. In this
session:

* `airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf` — self-signed certificate in the
  chain; fetch refused.
* `app.cpcbccr.com/ccr_docs/FINAL-REPORT_AQI_.pdf` and
  `data.gov.in/resource/real-time-air-quality-index-various-locations` — HTTP 403.
* `aqicn.org/json-api/doc/` — served a client-rendered shell with no content.
* The web-search budget for the session was exhausted before any of this began.

So **every claim above rests on measurement, not on documentation.** The CPCB 2014 Expert
Group report and the WAQI field documentation are cited in
`saafsaans/services/aqi_scale.py` from earlier work and were not re-verified here. The
one documentary line that was fetched successfully is aqicn.org's India FAQ, which says
only *"For information about the 24 hours averaging used or Ozone and Particulate Matter
(PM2.5), please refer to those two articles"* — it points at 24-hour averaging without
stating what the live feed publishes, and the linked articles were not reachable. It is
not load-bearing here.

## Risks accepted

1. **One day, one city, one season.** Every measurement is Delhi, 21 July 2026, monsoon.
   Concentrations were low (PM2.5 means 20–60 µg/m³). The window fingerprint is a
   structural property and should not be seasonal, but it has not been observed in winter.
2. **A one-session time series.** "Rolling, republished hourly" rests on values moving
   across a few hours of one evening, not on a logged day.
3. **Five stations.** All Delhi, all in the CPCB/DPCC network. NCR stations were not
   fingerprinted.
4. **The PM2.5 gap is carried, not closed.** We ship knowing that CPCB and OpenAQ disagree
   by ~1.7x on PM2.5 magnitude and that we cannot say who is right.

## What would falsify this

Stated so the next person can attack it cheaply:

* **The window claim dies if** CPCB's `min_value` stops tracking the 24-hour minimum of
  the station's own sub-hourly series. Re-run the Data point 1 comparison on a day with a
  sharp overnight trough: if CPCB's minimum sits well above the trough, the window is
  shorter than 24 hours; if well below, longer. Four exact matches would have to become
  four misses.
* **It also dies if** `avg_value` is found to jump discontinuously at 00:00 IST, which
  would make it a calendar-day mean rather than a rolling one. Logging one station's
  `avg_value` hourly across a midnight boundary settles it. This was not done.
* **The WAQI claim dies if** a matched station shows `iaqi`, inverted, tracking the 24-hour
  mean rather than the latest hour on a day with a wide diurnal swing. The Mandir Marg
  PM2.5 pair (1.2 vs 1.0 vs 15.6) is the shape to look for; one clear counter-example in
  the opposite direction overturns it.
* **The "different quantities" conclusion dies if** OpenAQ turns out to be republishing a
  smoothed or rolling figure rather than an instantaneous one — in which case the whole
  comparand is wrong and Data points 1 and 2 both need re-doing against station-level raw
  data.
* **The PM2.5 residual is closed** — in either direction — by any PM2.5 series for these
  stations that does not derive from the CPCB real-time stream.

## Consequence for the pages — a claim the app makes that is false

This is the reason the question gated shipping.

`saafsaans/web/presenters.py:who_line` reasons in its docstring that *"The app holds a
single near-instantaneous station reading"*, and therefore phrases the WHO sentence to
keep a mismatch visible — *"Right now the air here holds about {word} of this pollution as
the World Health Organization's safe level **for a whole day**."* The Guide,
`guide.html:who_1_after`, tells the reader the same thing outright:

> The line on the Today page compares the air right now against the 24-hour figure, and
> says so in those words, because the two are not the same thing: **a single reading is
> not a daily average.**

For a CPCB-sourced reading — the primary source, most readings, most of the time — **that
is false**. The reading *is* a daily average. WHO's 15 µg/m³ figure is a 24-hour mean, and
the app is comparing a 24-hour mean against it while telling the reader it is not doing
so. The sentence is served unchanged for WAQI-sourced readings, where it *is* true. One
sentence, in both languages, describing two different quantities and getting one of them
wrong.

Both surfaces are in scope for correction. Neither is corrected by this document; this
document establishes the fact that requires it.
