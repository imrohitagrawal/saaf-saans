# 0002 — A sample must never drive severity

**Status: DECIDED 2026-07-21. Implementation pending.**

When the app has no live reading, it must show **the station's last real reading with its
age** — "ITO last reported 23 June" — and never an invented number. A stand-in figure must
never drive a severity word, a band, a risk score or a health instruction.

## Assumptions

The behaviour being replaced rested on three assumptions, all now rejected:

1. That a labelled stand-in is honest enough — that if the page says `SAMPLE`, a reader
   will discount everything downstream of it.
2. That a "typical figure for the place" is a useful default, better than a gap.
3. That the severity stack (band, verdict, advice, risk score) is a neutral rendering
   layer that can be pointed at any number.

## Analysis

**The defect, reproduced.** With the mandated empty-credential environment:

```
env OPENROUTER_API_KEY= WAQI_TOKEN= ELASTIC_URL= ELASTIC_API_KEY= ELASTIC_CLOUD_ID= \
  .venv/bin/python -c "..."   # TestClient GET /?locality=ITO, senior, asthma, exercise
```

renders:

- `<span class="prov">◌ SAMPLE — not a reading</span>`
- `<span class="hero-pill">AQI 400 · VERY POOR</span>`
- `<h1 class="verdict">Don't go out unless you must — this air is dangerous for you.</h1>`

The 400 is derived: `aqi_scale.cpcb_aqi(250.0, 410.0) == (400, 'pm25', False)`, from
`waqi.SAMPLES["ITO"] = {"pm25": 250.0, "pm10": 410.0, "dom": "no2"}`
(`saafsaans/services/waqi.py:165`). Those are winter concentrations, served in July.

**Be exact about what is wrong.** The number is *labelled*. `◌ SAMPLE — not a reading`
renders immediately before the pill. This is not an unlabelled fabrication. The defect is
that **the label is ignored by every consumer of the number**:

| Surface | Sample-driven? | Marked? |
| --- | --- | --- |
| Provenance chip (`today.html:20`) | — | **yes** |
| Stale-note paragraph (`today.html:41-44`) | — | **yes** |
| `og:title` parenthetical (`base.html:21`) | — | **yes** ("(sample)") — but still names a CPCB band |
| AQI pill + band word | yes | no |
| Editorial verdict `<h1>` | yes | no |
| Band advice line | yes | no |
| Risk score, band and driver chips (which quote "AQI 400" verbatim) | yes | no |
| WHO comparison ("Right now the air here holds about twenty times…") | yes | no |
| Band meaning paragraph | yes | no |
| "If you must go out" window | yes | no |
| `/ask` retrieval key and the "Published guidance used" rows | yes | no |
| `/city` band, colour, sort order, `count`, `median` | yes | row-level tag only, not the summary |

Three markers; eleven unmarked derived claims. **Adding a twelfth marker cannot fix this.**
The markers already exist and are already ignored.

**Two independent code paths, not one.** `waqi._fallback()` serves the Today and `/ask`
path. `/city` never calls it — `saafsaans/web/main.py:607-625` `_sample_aqi()` reads
`waqi.SAMPLES` directly. Neither is a cache, timeout or freshness bug. `/city` also never
calls `waqi.get_aqi` at all; its only data source is the Elasticsearch `aqi-readings`
index via `metrics.station_grid` (`main.py:638`), which returns `[]` on a `None` client or
any exception (`metrics.py:271-272, 304-305`). So a station can be LIVE on `/` and SAMPLE
on `/city` at the same moment.

**Why the sample gets served for ITO at all.** `MAX_OBS_AGE = timedelta(hours=12)`
(`waqi.py:129`). An observation older than that routes through `_obs_too_old` →
`_fetch_feed` returns `None` (`waqi.py:313`) → `_fallback()`. The app *correctly* refuses
to call a month-old observation live, and then substitutes something worse than nothing.

**Two localities are permanently sample-driven.** `FEED_MAP` maps Ashok Vihar and Nehru
Nagar to `None` — no WAQI station exists. No outage is required for them to fabricate.

## Data points

- `waqi.SAMPLES` — 21 hardcoded winter concentration pairs, no observation time, no source
  citation (`waqi.py:163-186`). Anand Vihar `pm25 380.0 / pm10 520.0`; ITO `250.0 / 410.0`.
- `_fallback()` is returned on four distinct paths — no token, no feed slug, fetch
  failed/too stale, station-name mismatch — and always sets `stale=True`, `obs_time=None`
  (`waqi.py:355, 359, 371, 381`).
- Real CPCB values for the same stations on 2026-07-21 17:00 IST, from
  `api.data.gov.in` resource `3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69`: **ITO PM2.5 = 54**
  (app serves 250), **Anand Vihar PM2.5 = 91** (app serves 380). See
  [`research/`](../research/) and the source note in [INDEX](../INDEX.md).
- Production `/city` printed `median AQI 358` across 21/21 `SAMPLE` rows while `/` printed
  `Rohini · LIVE · AQI 86 · SATISFACTORY` in the same minute.
- A sample is **never** written to Elasticsearch: the only `es.index_reading` call site is
  `waqi.py:389`, after both the fetch-succeeded and `_corroborates` checks. Good — the
  index is uncontaminated, so a stored "last real reading" is genuinely real.

## What changed our mind

The severity audit. We went in believing this was a labelling problem and came out with a
table showing eleven derived claims that never consult the label. The decisive item is the
**"if you must go out" window**: `SAMPLES["Gurugram"]` carries `"dom": "o3"`, which
`_fallback` passes to `forecast.best_window`, which prints "Early morning (about 6-9 AM)".
A *hardcoded fabricated dominant pollutant* selects a concrete hour at which to send a
person with COPD outdoors. That is indefensible under any amount of labelling.

## What we kept

- The `SAMPLES` dict itself. `tests/test_waqi.py:64`
  `test_all_localities_have_feed_and_sample` correctly requires every locality to have one.
  Deleting the dict is a larger change than removing its **authority over severity**, and
  the two should not be mixed.
- Every provenance-honesty test. `tests/test_provenance_honesty.py` in full;
  `tests/test_web.py:177, :309, :961, :1047`; `tests/test_share_and_time_honesty.py:89, :101`.
  These pin *label/branch agreement*, not numbers, and were empirically proven to survive
  the fix.
- `tests/test_unknown_aqi.py` entirely — it is the **specification the new behaviour must
  satisfy**. It already asserts that a missing AQI retrieves no advisories (`:45, :55`),
  does not quote the clean band (`:75`), and gets no friendlier window (`:120`).

## What we are modifying

In dependency order:

1. `waqi._fallback()` stops manufacturing an index. It returns a reading whose `aqi` is
   `None`, plus a `last_real` block (value + observation time) when one is stored. The
   existing **Unknown** path — already correct, already tested — then takes over
   automatically for verdict, advice, risk, window and `og:`.
2. Delete the `"dom"` keys from `SAMPLES`. A fabricated dominant pollutant must not select
   a go-outside hour.
3. `presenters.who_line` returns `""` when the reading is not live. "Right now" is a
   measurement claim.
4. **Separate commit:** `/city`. Delete `main._sample_aqi` and its call site. A locality
   with no number shows its last stored reading with age, or nothing; sorts last; is
   excluded from `count` and `median`; receives no band label.
5. `today.html:287` renders the kicker "Measured at the time" unconditionally. It must
   branch on `waqi_status`, as `:282` already does.
6. `main.py:729-730` labels the fallback rate "feed misses → cached" while `city.html:31`
   defines CACHED as "we hold a reading for that place". Same word, opposite definitions on
   two pages. Reconcile.
7. `saafsaans/seed_demo_history.py` writes fabricated readings with timestamps up to `now`,
   which `/city`'s `<=3h` freshness check renders with **no tag at all**. Meanwhile
   `guide.html:59` asserts "Nothing old or stood-in is ever presented as live." Either the
   seed script stamps a marker field that `/city` renders, or that Guide sentence is
   **removed** — Hard Rule 5: an unsupportable claim is removed, not softened.

**Measured blast radius** (mutating a throwaway copy of the tree, full suite each time):

| Change | Result |
| --- | --- |
| Baseline | 882 passed |
| `_fallback` yields no index | **16 failed, 866 passed** |
| …plus `_sample_aqi` neutered | **19 failed, 863 passed** |

Every load-bearing honesty test stayed green under both. None of the 19 needs weakening —
each asserted a *consequence of the bug*, and each is a fixture/premise correction. The two
highest-value ones, `tests/test_share_and_time_honesty.py:37` and `:74`, must be
**rewritten to assert the new honest state**, never deleted.

## Risks accepted

- **Gaps become visible.** With no ES row and no live feed, a locality shows nothing. That
  is the intended outcome, and it will look broken to someone expecting a number. It is
  correct: the app's degraded state stops being papered over.
- **`/city` may render mostly empty in production** until the ES-connection question is
  answered (production `station_grid` returns zero rows; whether the Fly machine has
  `ELASTIC_*` secrets is *inferred, not proven*). This is a feature of the fix — it
  surfaces a real outage that the sample was hiding.
- **A "last real reading" can itself be misleading if old.** Mitigated by always printing
  the age beside it, never the value alone.
- **We are not fixing the source in this run.** WAQI stays. The CPCB feed (which covers 45
  Delhi stations including Ashok Vihar and Nehru Nagar, and answers today for ITO) needs an
  owner-registered `data.gov.in` API key, which an agent must not create.

## What would falsify it

- **A user test showing readers correctly discount a labelled sample** — i.e. that people
  shown "◌ SAMPLE" and "AQI 400 · VERY POOR" do not act on the 400. That would move this
  from a correctness defect to a copy problem. `docs/USER-TEST.md` is the instrument.
- **Evidence that an empty tile causes worse behaviour than a stand-in** — e.g. readers
  treat "no data" as "no problem" and go outside on a genuinely bad day. This is a real
  possibility and the strongest counter-argument available. It would not restore the
  fabricated number, but it would demand different copy for the empty state.
- Evidence that the `SAMPLES` values are in fact defensible annual medians rather than
  winter peaks — would still not license them driving severity, but would change how the
  dict is described.

**The bite-proof for the fix is a property, not a string:** for every locality, in **both**
languages, assert that a tile whose status is not `ok` carries no AQI integer, no CPCB band
word outside a sample-marked element, and contributes to neither `count` nor `median`.
Prove it bites by reinstating `_sample_aqi` / `_fallback`'s index and watching it go red.
