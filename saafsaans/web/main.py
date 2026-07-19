"""FastAPI + Jinja2 front end for SaafSaans.

Recreates the approved design in design_handoff_saafsaans/ (v4). The service
layer (waqi / es / llm / guard / risk / forecast / metrics / normalize) is
framework-independent and untouched; this module orchestrates it, and
``presenters`` turns the results into copy and geometry.

Everything is server-rendered and every control is a link or a form, so the
whole app works with JavaScript disabled. Disclosure state (persona editor,
term definitions, provenance panel) rides in the query string rather than in
client state -- which also gives the design's "opening one term closes another"
behaviour for free.

Persona travels in the query string too, so any view is shareable. Only the
chat transcript needs continuity; it is held per session id in memory and never
persisted, because the persona is sensitive and must not reach an index.
"""
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from saafsaans.attack_demo import ATTACKS
from saafsaans.services import (
    config, es, forecast, guard, llm, metrics, normalize, risk, waqi,
)
from saafsaans.web import presenters as pr

BASE = Path(__file__).parent
app = FastAPI(title="SaafSaans")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

AGES = ["Child", "Adult", "Senior"]
CONDITIONS = ["Fit", "Asthma", "Heart condition", "Pregnancy", "COPD"]
ACTIVITIES = ["Outdoor exercise", "Commute", "School run", "Stay home"]
TERMS = ["AQI", "PM2.5", "PM10"]
IST = timezone(timedelta(hours=5, minutes=30))

_TRANSCRIPTS: dict[str, list] = {}
_client = None


def get_client():
    """One Elasticsearch client per process (or None in mock mode)."""
    global _client
    if _client is None:
        _client = es.get_client()
    return _client


# --- request state ---------------------------------------------------------
def read_persona(request: Request) -> dict:
    q = request.query_params

    def pick(key, options, default):
        value = q.get(key)
        return value if value in options else default

    return {
        "locality": pick("locality", waqi.LOCALITIES, "Anand Vihar"),
        "age": pick("age", AGES, "Adult"),
        "condition": pick("condition", CONDITIONS, "Asthma"),
        "activity": pick("activity", ACTIVITIES, "Outdoor exercise"),
    }


def read_theme(request: Request) -> str:
    value = request.query_params.get("theme") or request.cookies.get("theme")
    return "dark" if value == "dark" else "light"


def session_id(request: Request) -> str:
    return request.cookies.get("sid") or str(uuid.uuid4())


def _qs(persona: dict, theme: str, **extra) -> str:
    """Query string carrying persona + theme, plus any disclosure state.

    Keys with a None value are dropped, which is how a disclosure link closes
    what is currently open.
    """
    params = {**persona, "theme": theme}
    params.update(extra)
    return urlencode({k: v for k, v in params.items() if v is not None})


def base_context(request: Request, persona: dict, theme: str, active: str) -> dict:
    return {
        "request": request, "persona": persona, "theme": theme, "active": active,
        "path": request.url.path,
        "ages": AGES, "conditions": CONDITIONS, "activities": ACTIVITIES,
        "regions": waqi.REGIONS,
        "q": _qs(persona, theme),
        "q_light": _qs(persona, "light"),
        "q_dark": _qs(persona, "dark"),
        "pct": pr.pct,
    }


def _fmt_time(iso: str = None) -> str:
    """'2:00 PM' in IST. Falls back to now when the feed gave no timestamp."""
    dt = None
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            dt = None
    dt = (dt or datetime.now(timezone.utc)).astimezone(IST)
    return dt.strftime("%-I:%M %p")


# --- Today -----------------------------------------------------------------
def advisor_data(persona: dict) -> dict:
    reading, waqi_status = waqi.get_aqi(persona["locality"], es_client=get_client())
    aqi = reading.get("aqi")
    return {
        "reading": reading, "waqi_status": waqi_status,
        "category": normalize.aqi_category(aqi),
        "band": normalize.band_slug(aqi),
        "meaning": normalize.aqi_meaning(normalize.aqi_category(aqi)[0]),
        "risk": risk.compute_risk(
            aqi, normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"])),
        # Same air, same plans, healthy adult body -- the gap is the whole point.
        "baseline": risk.compute_risk(
            aqi, "any", normalize.norm_activity(persona["activity"]), "adult")["score"],
        "window": forecast.best_window(
            aqi, dominant_pollutant=reading.get("dominant_pollutant"),
            forecast=reading.get("forecast")),
        "outlook": pr.outlook_rows(forecast.daily_outlook(reading.get("forecast"))),
    }


@app.get("/")
def today(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    sid = session_id(request)
    q = request.query_params

    ctx = base_context(request, persona, theme, "today")
    data = advisor_data(persona)
    ctx.update(data)

    term = q.get("term") if q.get("term") in TERMS else None
    persona_open = q.get("edit") == "1"
    obs_time = _fmt_time(data["reading"].get("obs_time"))

    # Newest first, and the whole history: a user tracking a decision needs to
    # re-read what they already asked, not have it replaced by the next answer.
    turns = list(reversed(_TRANSCRIPTS.get(sid, [])))
    open_prov = q.get("prov")

    ctx.update({
        "verdict": pr.verdict_for(data["risk"]["band"]),
        "kicker": pr.persona_kicker(persona),
        "persona_line": pr.persona_line(persona),
        "compare": pr.comparison_line(data["risk"]["score"], data["baseline"], persona),
        "scale_pos": pr.scale_position(data["reading"].get("aqi")),
        "prov_chip": pr.provenance_chip(data["waqi_status"], obs_time),
        "obs_time": obs_time,
        "glossary": normalize.GLOSSARY,
        "term": term, "persona_open": persona_open,
        "transcript": turns, "open_prov": open_prov,
        "condition_help": normalize.condition_help(persona["condition"]),
        "conditions_help": normalize.CONDITION_HELP,
        # Each link toggles its own disclosure and clears the others.
        "q_persona_toggle": _qs(persona, theme, edit=None if persona_open else "1"),
        # Provenance opens per turn, so history stays independently inspectable.
        "q_prov": lambda tid: _qs(persona, theme,
                                  prov=None if open_prov == tid else tid),
        "q_term_aqi": _qs(persona, theme, term=None if term == "AQI" else "AQI"),
        "q_term_pm25": _qs(persona, theme, term=None if term == "PM2.5" else "PM2.5"),
        "q_term_pm10": _qs(persona, theme, term=None if term == "PM10" else "PM10"),
    })
    return _render(request, "today.html", ctx, sid, theme)


@app.post("/ask")
def ask(request: Request, question: str = Form(...)):
    """Guard -> retrieve -> answer, then redirect so a refresh cannot resubmit."""
    persona = read_persona(request)
    theme = read_theme(request)
    sid = session_id(request)
    client = get_client()
    turns = _TRANSCRIPTS.setdefault(sid, [])

    hashed = normalize.session_hash(sid)
    data = advisor_data(persona)
    reading, waqi_status = data["reading"], data["waqi_status"]
    start = time.time()

    ok, pattern = guard.check(question)
    if not ok:
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(question), "action_taken": "blocked"})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "blocked",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "skipped", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"], "error": ""})
        turns.append({"kind": "refusal", "id": str(len(turns)), "question": question,
                      "pattern": pattern, "persona_line": pr.persona_line(persona)})
        return _back(request, sid, theme)

    try:
        advisories = es.search_advisories(
            reading.get("aqi") or 0,
            normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]), client=client)
        text, tokens, llm_status = llm.answer(
            reading,
            {"age_group": persona["age"], "condition": persona["condition"],
             "activity": persona["activity"]},
            advisories, question, locality=persona["locality"],
            timestamp=es.now_iso(), best_window=data["window"])
        parsed = llm.parse_advice(text)
        turns.append({
            "kind": "answer", "id": str(len(turns)), "question": question,
            "persona_line": pr.persona_line(persona),
            "blocks": pr.answer_sections(parsed),
            "disclaimer": parsed.get("disclaimer"),
            "sources": advisories,
            "reading": reading, "waqi_status": waqi_status})
        degraded = [n for n, bad in (("waqi_fallback", waqi_status == "fallback"),
                                     ("llm_fallback", llm_status == "llm_fallback")) if bad]
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "chat_completed",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": llm_status, "llm_tokens": tokens,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": "; ".join(degraded)})
    except Exception as exc:  # pragma: no cover - top-level safety net
        turns.append({
            "kind": "answer", "id": str(len(turns)), "question": question,
            "persona_line": pr.persona_line(persona),
            "blocks": [{"heading": "Verdict", "lead": True,
                        "text": "Something went wrong preparing your advice. When in "
                                "doubt, minimise outdoor exposure and wear an N95 outside."}],
            "disclaimer": None, "sources": [],
            "reading": reading, "waqi_status": waqi_status})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "error",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "error", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": normalize.sanitize_error(exc)})
    return _back(request, sid, theme)


# --- City Pulse ------------------------------------------------------------
@app.get("/city")
def city(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    client = get_client()
    selected = request.query_params.get("station")
    if selected not in waqi.LOCALITIES:
        selected = persona["locality"]

    grid = {r.get("station"): r for r in metrics.station_grid(client, waqi.LOCALITIES)}
    stations = []
    for loc in waqi.LOCALITIES:
        row = grid.get(loc)
        # A stored reading is only "live" if it is recent. Treating a week-old
        # document as current would present stale air as the air outside now --
        # the one thing this product promises never to do.
        stale = row is None or not _is_fresh(row.get("ts"), hours=3)
        # No stored reading: fall back to the labelled per-locality sample rather
        # than showing a dead row. It is marked CACHED, never passed off as live,
        # and costs no HTTP -- 21 live fetches would make this page crawl.
        aqi = row.get("aqi") if row else (waqi.SAMPLES.get(loc) or {}).get("aqi")
        label, _c, _h, slug = normalize.band_for(aqi)
        stations.append({"name": loc, "aqi": aqi, "band": label, "slug": slug,
                         "stale": stale, "selected": loc == selected})

    def group(region):
        rows = [s for s in stations if s["name"] in waqi.REGIONS[region]]
        # Worst first: the station in trouble is the one you scan for.
        return sorted(rows, key=lambda s: (s["aqi"] is None, -(s["aqi"] or 0)))

    trend = metrics.aqi_trend(client, locality=selected, hours=24)
    ctx = base_context(request, persona, theme, "city")
    ctx.update({
        "delhi": group("Delhi"), "ncr": group("NCR"),
        "count": sum(1 for s in stations if s["aqi"] is not None),
        "median": pr.median_aqi(stations),
        "now": _fmt_time(),
        "selected": selected,
        "selected_aqi": next((s["aqi"] for s in stations if s["name"] == selected), None),
        "spark": pr.sparkline_svg(trend.get("points")),
        "q_station": lambda name: _qs(persona, theme, station=name),
    })
    return _render(request, "city.html", ctx, session_id(request), theme)


# --- System ----------------------------------------------------------------
@app.get("/system")
def system(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    client = get_client()
    view = "security" if request.query_params.get("view") == "security" else "observability"

    ctx = base_context(request, persona, theme, "system")
    ctx.update({
        "view": view,
        "q_obs": _qs(persona, theme, view="observability"),
        "q_sec": _qs(persona, theme, view="security"),
        "simulated": request.query_params.get("sim") == "1",
        "attack_count": len(ATTACKS),
    })

    if view == "observability":
        k = metrics.telemetry_kpis(client)
        by_event = k.get("by_event") or {}
        ev_max = max(by_event.values()) if by_event else 0
        loc_rows = k.get("by_locality") or []
        loc_max = max((r["count"] for r in loc_rows), default=0)
        # `total` counts every logged event, including blocked prompts and
        # errors. Only completed answers belong under "questions answered".
        answered = (by_event or {}).get("chat_completed", 0)
        ctx.update({
            "kpis": [
                {"v": answered, "l": "questions answered"},
                {"v": k.get("total", 0), "l": "events logged"},
                {"v": f'{k.get("latency_p50", 0) / 1000:.1f} s', "l": "median response"},
                {"v": f'{k.get("latency_p95", 0) / 1000:.1f} s', "l": "p95 response"},
                {"v": f'{k.get("waqi_fallback_rate", 0) * 100:.1f}%', "l": "feed misses → cached"},
                {"v": f'{k.get("llm_fallback_rate", 0) * 100:.1f}%', "l": "rule-based fallbacks"},
                {"v": f'{k.get("total_tokens", 0) / 1000:.1f}k', "l": "tokens spent"},
            ],
            "ev_rows": [{"l": n, "v": c, "w": pr.pct(c, ev_max)}
                        for n, c in sorted(by_event.items(), key=lambda x: -x[1])],
            "loc_rows": [{"l": r["locality"], "v": r["count"], "w": pr.pct(r["count"], loc_max)}
                         for r in loc_rows[:6]],
        })
    else:
        stats = metrics.security_stats(client)
        daily = metrics.security_daily(client, days=7)
        day_max = max((d["count"] for d in daily), default=0)
        # security_stats aggregates the whole index, so the KPI has to come from
        # the same seven-day buckets the chart uses or the label is a lie.
        last_7 = sum(d["count"] for d in daily)
        ctx.update({
            "sec_kpis": [
                {"v": last_7, "l": "blocked, last 7 days"},
                {"v": f'{stats.get("block_rate", 0) * 100:.0f}%', "l": "stopped pre-model"},
                {"v": len(stats.get("by_pattern") or []), "l": "distinct patterns"},
            ],
            "days": [{"n": d["count"], "d": _day_label(d["date"]),
                      "h": pr.pct(d["count"], day_max)} for d in daily],
            "attempts": pr.group_attempts(
                [{**a, "when": _fmt_time(a["ts"])}
                 for a in metrics.recent_security_events(client, limit=40)])[:6],
        })
    return _render(request, "system.html", ctx, session_id(request), theme)


@app.post("/system/simulate")
def simulate(request: Request):
    """Fire the known attack prompts at the live guard and audit every block."""
    persona = read_persona(request)
    theme = read_theme(request)
    client = get_client()
    hashed = normalize.session_hash("red-team-demo")
    for _name, prompt in ATTACKS:
        ok, pattern = guard.check(prompt)
        if ok:
            continue
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(prompt), "action_taken": "blocked"})
    try:
        if client is not None:
            client.indices.refresh(index=es.INDEX_SECURITY)
    except Exception:
        pass
    url = "/system?" + _qs(persona, theme, view="security", sim="1")
    return RedirectResponse(url, status_code=303)


@app.get("/guide")
def guide(request: Request):
    """Plain-language explanation of every number and term the site shows.

    Lives at its own URL rather than as a collapsed block on Today, so it can be
    linked to directly from the term that confused someone.
    """
    persona = read_persona(request)
    theme = read_theme(request)
    ctx = base_context(request, persona, theme, "guide")
    ranges = ["0-50", "51-100", "101-200", "201-300", "301-400", "401-500"]
    labels = [b[1] for b in normalize.AQI_BANDS] + ["Severe"]
    slugs = [b[4] for b in normalize.AQI_BANDS] + ["g6"]
    ctx.update({
        "glossary": normalize.GLOSSARY,
        "conditions_help": normalize.CONDITION_HELP,
        "bands": [{"label": l, "range": r, "slug": g,
                   "meaning": normalize.aqi_meaning(l)}
                  for l, r, g in zip(labels, ranges, slugs)],
    })
    return _render(request, "guide.html", ctx, session_id(request), theme)


@app.get("/health")
def health():
    return {"ok": True, "es": config.es_mode(),
            "waqi": config.waqi_available(), "llm": config.llm_available()}


# --- helpers ---------------------------------------------------------------
def _is_fresh(ts, hours: int = 3) -> bool:
    """True when a stored reading is recent enough to call live."""
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) <= timedelta(hours=hours)


def _day_label(date_str: str) -> str:
    try:
        return datetime.fromisoformat(str(date_str)[:10]).strftime("%a")
    except ValueError:
        return str(date_str)[:3]


def _render(request, template, ctx, sid, theme):
    response = templates.TemplateResponse(request, template, ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    response.set_cookie("theme", theme, samesite="lax")
    return response


def _back(request: Request, sid: str, theme: str):
    persona = read_persona(request)
    response = RedirectResponse("/?" + _qs(persona, theme) + "#ask", status_code=303)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response
