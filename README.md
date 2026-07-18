# SaafSaans — Delhi Air Quality & Public Health Companion

A 4-tab **Command Center**. Pick a persona (age, health condition, activity, Delhi locality), ask a question, and get concrete go/no-go air-quality advice grounded in a **live AQI reading** and **curated health advisories** — with a **personal risk score**, a **forecast-based best-time window**, live **Elastic Observability** and **Security** dashboards, and a prompt-injection guard.

**Tabs:** 🩺 Advisor (live AQI + risk gauge + structured advice card) · 🌆 City Pulse (all Delhi stations + 24h AQI trend from Elasticsearch) · 📊 Observability (telemetry KPIs: volume, p50/p95 latency, fallback rates, tokens) · 🛡️ Security (prompt-injection events + one-click red-team simulation).

## Setup (5 lines)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                     # optional: fill in keys; blank = mock mode
python saafsaans/setup_indices.py        # create 4 indices + seed 34 advisories
python -m saafsaans.seed_demo_history    # optional: backfill 24-48h so dashboards look alive
streamlit run saafsaans/app.py
```

The app runs with **zero keys** — every external call has a timeout and a deterministic fallback, so the demo never crashes. Add `WAQI_TOKEN`, `OPENROUTER_API_KEY`, and Elastic creds to `.env` to light up live data, the LLM, and dashboards.

## Architecture (6 lines)

1. **WAQI** (`services/waqi.py`) fetches live AQI for the locality; the reading is indexed into `aqi-readings`.
2. **Elasticsearch** (`services/es.py`) BM25-searches `health-advisories` by AQI band + persona boosts (auto-detects Cloud ID / URL / in-process mock mode).
3. **Guard** (`services/guard.py`) blocks prompt-injection *before* the LLM and logs to `security-events`.
4. **LLM** (`services/llm.py`) sends verified context + persona + advisories to Gemini via OpenRouter; falls back to rule-based advice on any failure.
5. **Streamlit** (`app.py`) orchestrates the flow and renders a color-coded CPCB AQI badge + a "what the app used" transparency panel.
6. **Telemetry** goes to `app-telemetry`; `attack_demo.py` populates the security dashboard on demand.

## Threat model

**What sensitive data does the design hold?**
Health condition + locality + planned activity form a sensitive persona. It lives **only in the Streamlit session** — it is never written to any index. Logs store a `session_hash` (sha256 of a per-session UUID, truncated to 12 chars) for correlation, and `prompt_excerpt` in `security-events` is capped at 120 chars. `aqi-readings` holds only station/pollutant data; `app-telemetry` holds only place + hashed id + status fields (its `error` field stores a sanitized, secret-redacted exception string — never the question or persona).

**Where can untrusted input reach something powerful?**
The only untrusted input is the user's chat text on its way to the LLM. Defence is layered: (1) `guard.check` blocks injection/extraction patterns and oversized input before any model call; (2) the system prompt is a fixed constant and the user question is framed as *data, not instructions*; (3) every attempt is audited in `security-events` with the matched pattern and `action_taken`.

**Which edges are exposed, and how are they secured?**
The Streamlit app, the Elastic endpoint, the OpenRouter key, and the WAQI feed. Secrets live only in `.env` (git-ignored); the Elastic API key should be least-privilege (write to the four app indices, read `health-advisories`). Every outbound call is timeout-bounded (WAQI 5s, LLM 30s, ES 10s) with a graceful fallback, so a slow or hostile edge degrades the demo instead of breaking it.

## Layout

```
saafsaans/
  app.py                # 4-tab Streamlit Command Center + orchestration
  services/
    config.py           # env / capability detection (mock-first)
    normalize.py        # persona maps, AQI category, privacy helpers
    guard.py            # prompt-injection detection (normalized + hardened)
    waqi.py             # live AQI fetch + per-locality fallback + forecast
    forecast.py         # WAQI forecast -> daily outlook + best-time window
    risk.py             # persona risk score (AQI x condition x activity x age)
    es.py               # ES client, dual-mode, BM25 search, logging
    metrics.py          # ES aggregations for the dashboards (read-only)
    llm.py              # Gemini via OpenRouter + structured advice + parser
    ui.py               # enterprise theme + HTML component toolkit
  data/advisories.py    # 34 seed advisories
  setup_indices.py      # create 4 indices + seed advisories
  seed_demo_history.py  # backfill demo readings/telemetry/security for dashboards
  attack_demo.py        # fire 3 malicious prompts at the guard
tests/                  # pytest (117): guard, privacy, search, normalize, waqi,
                        # es, llm, risk, forecast, metrics, ui
```
