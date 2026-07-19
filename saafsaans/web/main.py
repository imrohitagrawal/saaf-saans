"""FastAPI + Jinja2 front end for SaafSaans.

Replaces the Streamlit UI. The service layer (waqi / es / llm / guard / risk /
forecast / metrics / normalize) is untouched and framework-independent -- this
module only orchestrates it and hands plain dicts to templates.

Design rationale for the swap: Streamlit's widget set dictated the layout, so a
design could only ever be approximated. Server-rendered HTML means a design
lands as a template with no translation loss, and the same service layer will
back the v2 exposure ledger.

Persona lives in the query string so a view is shareable and the server stays
stateless. Only the chat transcript needs continuity, and that is held per
session id in memory -- deliberately not persisted, because the persona is
sensitive and must never reach an index (see the threat model in README).
"""
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from saafsaans.services import (
    config, es, forecast, guard, llm, metrics, normalize, risk, waqi,
)

BASE = Path(__file__).parent
app = FastAPI(title="SaafSaans")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

AGES = ["Child", "Adult", "Senior"]
CONDITIONS = ["Fit", "Asthma", "Heart condition", "Pregnancy", "COPD"]
ACTIVITIES = ["Outdoor exercise", "Commute", "School run", "Stay home"]
REGION_OF = {loc: r for r, locs in waqi.REGIONS.items() for loc in locs}

# session id -> list of chat turns. In memory only, cleared on restart.
_TRANSCRIPTS: dict[str, list] = {}
_client = None


def get_client():
    """One Elasticsearch client per process (or None in mock mode)."""
    global _client
    if _client is None:
        _client = es.get_client()
    return _client


def read_persona(request: Request) -> dict:
    """Persona from the query string, falling back to sane defaults."""
    q = request.query_params

    def pick(key, options, default):
        value = q.get(key)
        return value if value in options else default

    return {
        "locality": pick("locality", waqi.LOCALITIES, "Delhi (city)"),
        "age": pick("age", AGES, "Adult"),
        "condition": pick("condition", CONDITIONS, "Fit"),
        "activity": pick("activity", ACTIVITIES, "Commute"),
    }


def session_id(request: Request) -> str:
    return request.cookies.get("sid") or str(uuid.uuid4())


def base_context(request: Request, persona: dict, active: str) -> dict:
    """Everything every page needs: nav state, persona form, service status."""
    return {
        "request": request,
        "persona": persona,
        "active": active,
        "localities": waqi.LOCALITIES,
        "regions": waqi.REGIONS,
        "region_of": REGION_OF,
        "ages": AGES,
        "conditions": CONDITIONS,
        "activities": ACTIVITIES,
        "status": {
            "es": config.es_mode(),
            "waqi": config.waqi_available(),
            "llm": config.llm_available(),
        },
    }


def advisor_data(persona: dict) -> dict:
    """The Advisor screen's payload. Pure reads -- safe to call on every render."""
    reading, waqi_status = waqi.get_aqi(persona["locality"], es_client=get_client())
    aqi = reading.get("aqi")
    category = normalize.aqi_category(aqi)
    return {
        "reading": reading,
        "waqi_status": waqi_status,
        "category": category,
        "meaning": normalize.aqi_meaning(category[0]),
        "risk": risk.compute_risk(
            aqi,
            normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]),
        ),
        "window": forecast.best_window(
            aqi,
            dominant_pollutant=reading.get("dominant_pollutant"),
            forecast=reading.get("forecast"),
        ),
        "outlook": forecast.daily_outlook(reading.get("forecast")) or [],
        "glossary": normalize.GLOSSARY,
    }


@app.get("/")
def advisor(request: Request):
    persona = read_persona(request)
    sid = session_id(request)
    ctx = base_context(request, persona, "advisor")
    ctx.update(advisor_data(persona))
    ctx["transcript"] = _TRANSCRIPTS.get(sid, [])
    response = templates.TemplateResponse(request, "advisor.html", ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.post("/ask")
def ask(request: Request, question: str = Form(...)):
    """Guard -> retrieve -> answer. Mirrors the Streamlit flow exactly."""
    persona = read_persona(request)
    sid = session_id(request)
    client = get_client()
    turns = _TRANSCRIPTS.setdefault(sid, [])
    turns.append({"role": "user", "text": question})

    hashed = normalize.session_hash(sid)
    data = advisor_data(persona)
    reading, waqi_status = data["reading"], data["waqi_status"]
    start = time.time()

    ok, pattern = guard.check(question)
    if not ok:
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(question), "action_taken": "blocked",
        })
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "blocked",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "skipped", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"], "error": "",
        })
        turns.append({"role": "assistant", "refused": True, "pattern": pattern})
        return _back(request, sid)

    try:
        advisories = es.search_advisories(
            reading.get("aqi") or 0,
            normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]),
            client=client,
        )
        text, tokens, llm_status = llm.answer(
            reading,
            {"age_group": persona["age"], "condition": persona["condition"],
             "activity": persona["activity"]},
            advisories, question,
            locality=persona["locality"], timestamp=es.now_iso(),
            best_window=data["window"],
        )
        turns.append({
            "role": "assistant",
            "sections": llm.parse_advice(text),
            "sources": advisories,
            "reading": reading,
            "waqi_status": waqi_status,
        })
        degraded = [n for n, bad in (("waqi_fallback", waqi_status == "fallback"),
                                     ("llm_fallback", llm_status == "llm_fallback")) if bad]
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "chat_completed",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": llm_status, "llm_tokens": tokens,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": "; ".join(degraded),
        })
    except Exception as exc:  # pragma: no cover - top-level safety net
        turns.append({"role": "assistant", "error": True})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "error",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "error", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": normalize.sanitize_error(exc),
        })
    return _back(request, sid)


def _back(request: Request, sid: str):
    """POST/redirect/GET so a refresh never re-sends the question."""
    query = request.url.query
    response = RedirectResponse(f"/?{query}" if query else "/", status_code=303)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.get("/city")
def city_pulse(request: Request):
    persona = read_persona(request)
    client = get_client()
    grid = {r.get("station"): r for r in metrics.station_grid(client, waqi.LOCALITIES)}
    stations = []
    for loc in waqi.LOCALITIES:
        row = grid.get(loc)
        aqi = row.get("aqi") if row else None
        stations.append({"name": loc, "aqi": aqi, "stale": row is None,
                         "category": normalize.aqi_category(aqi)})
    ctx = base_context(request, persona, "city")
    ctx["stations"] = stations
    ctx["trend"] = metrics.aqi_trend(client, locality=persona["locality"], hours=24)
    return templates.TemplateResponse(request, "city.html", ctx)


@app.get("/health")
def health():
    """Liveness probe that also reports which integrations are live."""
    return {"ok": True, "es": config.es_mode(),
            "waqi": config.waqi_available(), "llm": config.llm_available()}
