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
from collections import OrderedDict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from saafsaans.attack_demo import ATTACKS
from saafsaans.services import (
    config, es, forecast, guard, i18n, llm, metrics, normalize, risk, waqi,
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

# The transcript store holds raw user questions, so leaving it unbounded is a
# privacy exposure as much as a memory leak: every question ever asked of this
# process stays in RAM until the process dies. Both dimensions are capped --
# how many sessions are held, and how many turns each session keeps.
MAX_SESSIONS = 500
MAX_TURNS_PER_SESSION = 20

# sid -> {"turns": deque, "next_id": int}, used as an LRU: reading or writing a
# session moves it to the end, so eviction always drops the session that has
# been idle longest.
_TRANSCRIPTS: "OrderedDict[str, dict]" = OrderedDict()
_client = None


def _session_store(sid: str) -> dict:
    """The transcript record for a session, created on first use.

    ``next_id`` is a monotonic per-session counter rather than ``len(turns)``,
    because the turn deque now drops its oldest entries: with a length-derived
    id, turn 0 would be evicted and the next turn would be numbered 0 again,
    and the provenance links -- which key off the id -- would open the wrong
    turn, or two turns at once.
    """
    store = _TRANSCRIPTS.get(sid)
    if store is None:
        store = {"turns": deque(maxlen=MAX_TURNS_PER_SESSION), "next_id": 0}
        _TRANSCRIPTS[sid] = store
        while len(_TRANSCRIPTS) > MAX_SESSIONS:
            _TRANSCRIPTS.popitem(last=False)
        return store
    _TRANSCRIPTS.move_to_end(sid)
    return store


def read_turns(sid: str) -> list:
    """Turns held for a session, oldest first; empty for an unknown session.

    Reading does not create a session -- otherwise every hit on Today from a
    forged or expired cookie would allocate a store entry, which is the growth
    this cap exists to stop.
    """
    store = _TRANSCRIPTS.get(sid)
    if store is None:
        return []
    _TRANSCRIPTS.move_to_end(sid)
    return list(store["turns"])


def add_turn(sid: str, turn: dict) -> dict:
    """Append a turn, stamping it with an id unique for the life of the session."""
    store = _session_store(sid)
    turn["id"] = str(store["next_id"])
    store["next_id"] += 1
    store["turns"].append(turn)
    return turn


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


def read_lang(request: Request) -> str:
    """The language for this request: ``?lang=`` first, then the cookie.

    Same shape as ``read_theme`` deliberately -- language is page state exactly
    as theme is, so it travels in the query string (every view stays
    shareable in the language it was read in) and is remembered in a cookie
    (so a reader who switched once does not switch again on every visit).
    ``i18n.normalise`` turns anything unrecognised into English rather than
    into a half-rendered page.
    """
    value = request.query_params.get("lang") or request.cookies.get("lang") or ""
    return i18n.normalise(value)


def _translator(lang: str):
    """``T(group, key, english)`` bound to this request's language.

    Handed to the templates so the copy stays where a reader of the template
    can see it: the English is written inline as the fallback argument, and the
    Hindi -- when there is one -- replaces it. A missing translation therefore
    renders the English that is right there in the markup.
    """
    def T(group: str, key: str, english: str) -> str:
        return i18n.t(lang, group, key, english)
    return T


def _option_labels(lang: str) -> dict:
    """Display text for every persona option, keyed by the value it submits.

    The keys stay English because they are the wire format: ``read_persona``
    validates against AGES / CONDITIONS / ACTIVITIES, the query string carries
    them, and ``normalize`` maps them to scoring keywords. Only what the reader
    sees is translated, so a Hindi page's persona editor still round-trips.

    Written out one literal key at a time rather than composed from the option
    name, because tests/test_i18n.py reads the requested keys back out of this
    file: a key built by concatenation is invisible to that parser, and an
    invisible key is one nobody notices is missing.
    """
    return {
        "Child": i18n.t(lang, "ui", "age_child", "Child"),
        "Adult": i18n.t(lang, "ui", "age_adult", "Adult"),
        "Senior": i18n.t(lang, "ui", "age_senior", "Senior"),
        "Fit": i18n.t(lang, "ui", "cond_fit", "Fit"),
        "Asthma": i18n.t(lang, "ui", "cond_asthma", "Asthma"),
        "Heart condition": i18n.t(lang, "ui", "cond_heart", "Heart condition"),
        "Pregnancy": i18n.t(lang, "ui", "cond_pregnancy", "Pregnancy"),
        "COPD": i18n.t(lang, "ui", "cond_copd", "COPD"),
        "Outdoor exercise": i18n.t(lang, "ui", "act_outdoor_exercise",
                                   "Outdoor exercise"),
        "Commute": i18n.t(lang, "ui", "act_commute", "Commute"),
        "School run": i18n.t(lang, "ui", "act_school_run", "School run"),
        "Stay home": i18n.t(lang, "ui", "act_stay_home", "Stay home"),
    }


def _advisory_translator(lang: str):
    """``advisory_text(doc)`` for a seeded advisory, translated when possible.

    The seeded advisories carry no id, so the key is composed from the five
    fields that together identify one: source, AQI band, and the persona triple.
    The persona fields are not optional. Source plus band alone collides --
    "WHO-AQG-2021:201-300" and "AHA-airpollution:201-300" each match two
    different seeded rows -- and a colliding key would serve one persona's
    health instruction under another persona's name, which is the worst
    available failure for this particular string. i18n.py documents the same
    rule and a test there fails the build if a future row collides.

    Any key with no translation falls back to the English on the document.
    """
    def advisory_text(doc: dict) -> str:
        key = (f"{doc.get('source')}:{doc.get('aqi_min')}-{doc.get('aqi_max')}"
               f":{doc.get('condition')}:{doc.get('activity')}:{doc.get('age_group')}")
        return i18n.t(lang, "advisory", key, doc.get("advice") or "")
    return advisory_text


def session_id(request: Request) -> str:
    """The chat-transcript key: the client's ``sid`` cookie when it is in the
    exact form this server issues, otherwise a fresh id.

    The cookie is deliberately NOT signed. Signing would mean owning a secret
    (generated, stored, rotated, and shared across processes) to protect a key
    that unlocks nothing but an in-memory chat transcript which is never
    persisted and is evicted within MAX_SESSIONS sessions. The cheaper check
    below removes the concrete defect -- an attacker choosing the key -- at no
    operational cost.

    What this DOES prevent: an arbitrary client-chosen key. The value must
    parse as a UUID, be version 4, and render back byte-for-byte in canonical
    lowercase form, so 'admin', a 10 MB string, and the brace/URN spellings of
    the same uuid are all rejected in favour of a new id. That bounds the key
    space to values the server could have issued and stops one client inflating
    the store with keys of its choosing.

    What this does NOT prevent: anyone who guesses or steals a real issued
    uuid4 still reads that session's transcript. Guessing is not a practical
    attack (122 random bits), but theft -- a shared device, a copied cookie --
    is not defended against here at all. Signing would not defend against theft
    either; only server-side authentication would.
    """
    raw = request.cookies.get("sid") or ""
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid4())
    if parsed.version != 4 or str(parsed) != raw:
        return str(uuid.uuid4())
    return raw


def _share_card() -> dict:
    """Default Open Graph / Twitter card text, for views with no reading.

    City Pulse, System and the Guide show no single reading, so their card
    describes the site and claims nothing about the air. Today overrides this
    with text built from the reading it is rendering.
    """
    return {
        "title": "SaafSaans — Delhi air, explained for your body",
        "description": "See what the air in your area of Delhi means for you "
                       "today, in plain language.",
    }


def today_share_card(persona: dict, data: dict, verdict: str,
                     label: str = None) -> dict:
    """Card text for Today, built from the very values the page renders.

    ``data`` and ``verdict`` are the same objects passed to the template, so
    the forwarded card and the opened page cannot disagree -- which is the
    whole reason this is not composed from a second lookup.

    Plain language only: no index number, no micrograms. When the feed carries
    no particulate the reading is None; the card then says the reading is
    missing and repeats the page's own advice for that case, rather than
    naming a band it does not have.

    ``label`` and the verdict are passed in already in the reader's language,
    and ``data["meaning"]`` is translated by the caller, so a Hindi page's card
    cannot show a band name or a verdict the page itself does not display. The
    surrounding scaffolding is English in both cases: it is a link preview, and
    the persona sentence it quotes has no Hindi source.
    """
    label_en = data["category"][0]
    label = label or label_en
    place = persona["locality"]
    if data["reading"].get("aqi") is None or label_en == "Unknown":
        return {"title": f"{place}: no air reading right now",
                "description": data["meaning"]}
    return {
        "title": f"{place} air right now: {label}",
        # The place is already in the title, so the persona phrase drops it.
        "description": f"{verdict} This is for "
                       f"{pr.persona_sentence(persona, with_place=False)}.",
    }


def _qs(persona: dict, theme: str, lang: str, **extra) -> str:
    """Query string carrying persona + theme + language, plus disclosure state.

    ``lang`` is positional and required rather than defaulted, so a new link
    cannot silently omit it: a link without the language returns a Hindi reader
    to English the moment they click anything.

    Keys with a None value are dropped, which is how a disclosure link closes
    what is currently open.
    """
    params = {**persona, "theme": theme, "lang": lang}
    params.update(extra)
    return urlencode({k: v for k, v in params.items() if v is not None})


def base_context(request: Request, persona: dict, theme: str, lang: str,
                 active: str) -> dict:
    return {
        "request": request, "persona": persona, "theme": theme, "active": active,
        "lang": lang,
        "path": request.url.path,
        "ages": AGES, "conditions": CONDITIONS, "activities": ACTIVITIES,
        # value -> what the reader sees. The values above stay English because
        # they are what the form submits and what read_persona validates.
        "option_label": _option_labels(lang),
        "regions": waqi.REGIONS,
        "share": _share_card(),
        "q": _qs(persona, theme, lang),
        "q_light": _qs(persona, "light", lang),
        "q_dark": _qs(persona, "dark", lang),
        # The toggle keeps everything else about the page identical, so a
        # reader switching language does not also lose their persona or theme.
        "q_en": _qs(persona, theme, "en"),
        "q_hi": _qs(persona, theme, "hi"),
        # Shown on every Hindi page. Not a template literal: the wording of a
        # caveat about unreviewed health copy belongs beside the copy it is
        # about.
        "review_banner": i18n.REVIEW_BANNER,
        "review_banner_en": i18n.REVIEW_BANNER_EN,
        "T": _translator(lang),
        "advisory_text": _advisory_translator(lang),
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
def advisor_data(persona: dict, lang: str = "en") -> dict:
    """The reading and everything derived from it, in the reader's language.

    ``lang`` defaults to English so the signature stays compatible with every
    existing caller; the services it calls carry the same default, so a missing
    translation degrades to English one string at a time rather than raising.
    """
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
            normalize.norm_age(persona["age"]), lang=lang),
        # Same air, same plans, healthy adult body -- the gap is the whole point.
        # The baseline is a bare number, so it needs no language.
        "baseline": risk.compute_risk(
            aqi, "any", normalize.norm_activity(persona["activity"]), "adult")["score"],
        "window": forecast.best_window(
            # The feed's own dominant pollutant, which may be a gas the app's
            # particulate-only index does not model. The window advice differs
            # for ozone, so it must not be told "pm25" merely because PM drove
            # our number.
            aqi, dominant_pollutant=(reading.get("feed_dominant")
                                     or reading.get("dominant_pollutant")),
            forecast=reading.get("forecast"), lang=lang),
        "outlook": pr.outlook_rows(
            forecast.daily_outlook(reading.get("forecast"), lang=lang), lang=lang),
    }


@app.get("/")
def today(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    sid = session_id(request)
    q = request.query_params

    ctx = base_context(request, persona, theme, lang, "today")
    data = advisor_data(persona, lang)
    ctx.update(data)

    term = q.get("term") if q.get("term") in TERMS else None
    persona_open = q.get("edit") == "1"
    obs_time = _fmt_time(data["reading"].get("obs_time"))

    # Newest first, and the whole history: a user tracking a decision needs to
    # re-read what they already asked, not have it replaced by the next answer.
    turns = list(reversed(read_turns(sid)))
    open_prov = q.get("prov")
    band = data["risk"]["band"]
    verdict = i18n.t(lang, "verdict", band, pr.verdict_for(band))
    # The band label and the meaning are translated here rather than in the
    # template because the share card is built from them too, and the card must
    # not name a band in a language the page does not use.
    band_label = i18n.t(lang, "band_label", data["category"][0], data["category"][0])
    data["meaning"] = i18n.t(lang, "aqi_meaning", data["category"][0], data["meaning"])
    ctx["meaning"] = data["meaning"]

    ctx.update({
        "verdict": verdict,
        "band_label": band_label,
        # Built from `data` and `verdict` themselves, so a forwarded link's
        # preview cannot say something the page does not.
        "share": today_share_card(persona, data, verdict, band_label),
        "kicker": pr.persona_kicker(persona, lang=lang),
        "persona_line": pr.persona_line(persona, lang=lang),
        "compare": pr.comparison_line(data["risk"]["score"], data["baseline"],
                                      persona, lang=lang),
        "scale_pos": pr.scale_position(data["reading"].get("aqi")),
        "prov_chip": pr.provenance_chip(data["waqi_status"], obs_time, lang=lang),
        "obs_time": obs_time,
        "glossary": normalize.GLOSSARY,
        "term": term, "persona_open": persona_open,
        "transcript": turns, "open_prov": open_prov,
        "condition_help": normalize.condition_help(persona["condition"]),
        "conditions_help": normalize.CONDITION_HELP,
        # The score is half published figure and half the author's judgement.
        # Saying so next to the number is the point; saying it only in the
        # README would repeat the mistake this project exists to record.
        "risk_notice": i18n.t(lang, "ui", "risk_notice", risk.HEURISTIC_NOTICE),
        "who_line": pr.who_line(data["reading"].get("pm25"), lang=lang),
        # Each link toggles its own disclosure and clears the others.
        "q_persona_toggle": _qs(persona, theme, lang,
                                edit=None if persona_open else "1"),
        # Provenance opens per turn, so history stays independently inspectable.
        "q_prov": lambda tid: _qs(persona, theme, lang,
                                  prov=None if open_prov == tid else tid),
        "q_term_aqi": _qs(persona, theme, lang, term=None if term == "AQI" else "AQI"),
        "q_term_pm25": _qs(persona, theme, lang, term=None if term == "PM2.5" else "PM2.5"),
        "q_term_pm10": _qs(persona, theme, lang, term=None if term == "PM10" else "PM10"),
    })
    return _render(request, "today.html", ctx, sid, theme, lang)


@app.post("/ask")
def ask(request: Request, question: str = Form(...)):
    """Guard -> retrieve -> answer, then redirect so a refresh cannot resubmit."""
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    sid = session_id(request)
    client = get_client()

    hashed = normalize.session_hash(sid)
    data = advisor_data(persona, lang)
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
        # The excerpt, not the raw string: guard.check rejects oversized input,
        # and storing what it rejected would let a client pin an arbitrarily
        # large question in server memory -- through the one path that exists
        # precisely to refuse it. It is also raw user text, which the transcript
        # cap is meant to bound rather than accumulate.
        add_turn(sid, {"kind": "refusal", "question": normalize.excerpt(question),
                       "pattern": pattern,
                       "persona_line": pr.persona_line(persona, lang=lang)})
        return _back(request, sid, theme, lang)

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
            timestamp=es.now_iso(), best_window=data["window"], lang=lang)
        parsed = llm.parse_advice(text)
        add_turn(sid, {
            "kind": "answer", "question": question,
            "persona_line": pr.persona_line(persona, lang=lang),
            "blocks": pr.answer_sections(parsed, lang=lang),
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
        add_turn(sid, {
            "kind": "answer", "question": question,
            "persona_line": pr.persona_line(persona, lang=lang),
            "blocks": [{"heading": i18n.t(lang, "ui", "heading_verdict", "Verdict"),
                        "lead": True,
                        "text": i18n.t(
                            lang, "ui", "answer_error",
                            "Something went wrong preparing your advice. When in "
                            "doubt, minimise outdoor exposure and wear an N95 "
                            "outside.")}],
            "disclaimer": None, "sources": [],
            "reading": reading, "waqi_status": waqi_status})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": hashed, "event": "error",
            "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "error", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": persona["locality"],
            "error": normalize.sanitize_error(exc)})
    return _back(request, sid, theme, lang)


# --- City Pulse ------------------------------------------------------------
@app.get("/city")
def city(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
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
        fresh = row is not None and _is_fresh(row.get("ts"), hours=3)
        # No stored reading: fall back to the labelled per-locality sample rather
        # than showing a dead row. It costs no HTTP -- 21 live fetches would make
        # this page crawl -- but it is a stand-in figure, not a reading we hold,
        # so it must not carry the same tag as a genuine stored-but-old reading.
        aqi = row.get("aqi") if row else (waqi.SAMPLES.get(loc) or {}).get("aqi")
        label, _c, _h, slug = normalize.band_for(aqi)
        stations.append({"name": loc, "aqi": aqi,
                         "band": i18n.t(lang, "band_label", label, label),
                         "slug": slug,
                         "source": "live" if fresh else ("cached" if row else "sample"),
                         "age": None if fresh or row is None else _age_label(row.get("ts"), lang),
                         "selected": loc == selected})

    def group(region):
        rows = [s for s in stations if s["name"] in waqi.REGIONS[region]]
        # Worst first: the station in trouble is the one you scan for.
        return sorted(rows, key=lambda s: (s["aqi"] is None, -(s["aqi"] or 0)))

    trend = metrics.aqi_trend(client, locality=selected, hours=24)
    ctx = base_context(request, persona, theme, lang, "city")
    ctx.update({
        "delhi": group("Delhi"), "ncr": group("NCR"),
        "count": sum(1 for s in stations if s["aqi"] is not None),
        "median": pr.median_aqi(stations),
        "now": _fmt_stamp(lang),
        "selected": selected,
        "selected_aqi": next((s["aqi"] for s in stations if s["name"] == selected), None),
        "spark": pr.sparkline_svg(trend.get("points")),
        "q_station": lambda name: _qs(persona, theme, lang, station=name),
    })
    return _render(request, "city.html", ctx, session_id(request), theme, lang)


# --- System ----------------------------------------------------------------
@app.get("/system")
def system(request: Request):
    persona = read_persona(request)
    theme = read_theme(request)
    # The System views are developer-facing and stay English by design, but the
    # shared header still has to keep the reader's language on every link out.
    lang = read_lang(request)
    client = get_client()
    view = "security" if request.query_params.get("view") == "security" else "observability"

    ctx = base_context(request, persona, theme, lang, "system")
    ctx.update({
        # Developer-facing and mono by design; it is not translated, so the
        # document must not claim to be in a language it is not written in.
        "doc_lang": "en",
        "view": view,
        "q_obs": _qs(persona, theme, lang, view="observability"),
        "q_sec": _qs(persona, theme, lang, view="security"),
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
            # Whose blocked prompt may be shown. /system is public and
            # unauthenticated, and the excerpt is a verbatim fragment of what
            # somebody typed -- publishing a stranger's is not made acceptable
            # by the fact that the guard stopped it. The red-team demo's own
            # attempts are ours to display, and a visitor may see their own.
            "attempts": pr.group_attempts(
                [{**a, "when": _fmt_time(a["ts"])}
                 for a in metrics.recent_security_events(client, limit=40)
                 if a.get("session_hash") in _displayable_sessions(request)])[:6],
        })
    return _render(request, "system.html", ctx, session_id(request), theme, lang)


@app.post("/system/simulate")
def simulate(request: Request):
    """Fire the known attack prompts at the live guard and audit every block."""
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
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
    url = "/system?" + _qs(persona, theme, lang, view="security", sim="1")
    return RedirectResponse(url, status_code=303)


# The Guide renders three of risk.py's tables, whose keys are scoring keywords
# ("copd", "outdoor_exercise", "sedentary") rather than copy. Capitalising a
# keyword in the template produced "Copd" in English and left it in English on
# a Hindi page; these builders name each row instead. The persona words reuse
# the picker's own labels, so a condition cannot be called one thing in the
# editor and another in the Guide.
_EPA_AGE_ORDER = ("child", "adult", "senior")
_INTENSITY_ORDER = ("sedentary", "light", "moderate", "high")
# risk.py's scoring keyword -> the persona option it stands for.
_FACTOR_OPTION = {
    "copd": "COPD", "heart": "Heart condition", "pregnancy": "Pregnancy",
    "asthma": "Asthma", "senior": "Senior", "child": "Child",
}


def _intensity_labels(lang: str) -> dict:
    return {
        "sedentary": i18n.t(lang, "guide", "level_sedentary", "sedentary"),
        "light": i18n.t(lang, "guide", "level_light", "light"),
        "moderate": i18n.t(lang, "guide", "level_moderate", "moderate"),
        "high": i18n.t(lang, "guide", "level_high", "high"),
    }


def _epa_rows(lang: str) -> list:
    """EPA's inhalation table, one row per age group this site offers.

    The age band ("6 to <11 years") is EPA's own bracket, restated rather than
    quoted, so it is translated -- unlike the citation under the table.
    """
    labels = _option_labels(lang)
    bands = {
        "child": i18n.t(lang, "guide", "age_band_child", "6 to <11 years"),
        "adult": i18n.t(lang, "guide", "age_band_adult", "21 to <31 years"),
        "senior": i18n.t(lang, "guide", "age_band_senior", "61 to <71 years"),
    }
    return [{"label": labels[age.capitalize()], "band": bands[age],
             "rates": [risk.INHALATION_RATES[age][level]
                       for level in _INTENSITY_ORDER]}
            for age in _EPA_AGE_ORDER]


def _intensity_rows(lang: str) -> list:
    """Which planned activity this site treats as which EPA effort level.

    "any" is the unknown-plans fallback and is never a thing a reader picked,
    so it is not shown.
    """
    labels, levels = _option_labels(lang), _intensity_labels(lang)
    activity_option = {"outdoor_exercise": "Outdoor exercise",
                       "school_run": "School run", "commute": "Commute",
                       "stay_home": "Stay home"}
    return [{"activity": labels[activity_option[keyword]], "level": levels[level]}
            for keyword, level in risk.ACTIVITY_INTENSITY.items()
            if keyword in activity_option]


def _factor_rows(lang: str) -> list:
    """The ungrounded weights: condition and age, named as the picker names them."""
    labels = _option_labels(lang)
    return [{"label": labels[_FACTOR_OPTION[w["key"]]], "value": w["value"]}
            for w in risk.weight_table()
            if w["table"] in ("condition_pts", "age_susceptibility_pts")
            and w["value"] and w["key"] in _FACTOR_OPTION]


@app.get("/guide")
def guide(request: Request):
    """Plain-language explanation of every number and term the site shows.

    Lives at its own URL rather than as a collapsed block on Today, so it can be
    linked to directly from the term that confused someone.
    """
    persona = read_persona(request)
    theme = read_theme(request)
    lang = read_lang(request)
    ctx = base_context(request, persona, theme, lang, "guide")
    ranges = ["0-50", "51-100", "101-200", "201-300", "301-400", "401-500"]
    labels = [b[1] for b in normalize.AQI_BANDS] + ["Severe"]
    slugs = [b[4] for b in normalize.AQI_BANDS] + ["g6"]
    ctx.update({
        "glossary": normalize.GLOSSARY,
        "conditions_help": normalize.CONDITION_HELP,
        "bands": [{"label": i18n.t(lang, "band_label", l, l), "range": r, "slug": g,
                   "meaning": i18n.t(lang, "aqi_meaning", l, normalize.aqi_meaning(l))}
                  for l, r, g in zip(labels, ranges, slugs)],
        # Only the two glossary terms that are ordinary English. AQI, PM2.5,
        # PM10, CPCB, N95 and µg/m³ are how a Delhi reader says them out loud,
        # so the template falls back to the term itself for those.
        "glossary_terms": {
            "Dominant pollutant": i18n.t(lang, "guide", "term_dominant",
                                         "Dominant pollutant"),
            "Risk score": i18n.t(lang, "guide", "term_risk_score", "Risk score"),
        },
        # A reader told "44/100 · HIGH" cannot check that without the cut-offs.
        "risk_bands": [{"label": n, "upper": u} for n, u, _c in risk._BAND_TABLE],
        "risk_notice": i18n.t(lang, "ui", "risk_notice", risk.HEURISTIC_NOTICE),
        # Citations, not copy: an identifier a reader is meant to look up. Left
        # in Latin on purpose -- translating it would make the source harder to
        # find, which is the opposite of why it is printed.
        "source_epa": risk.SOURCE_EPA,
        "who_guideline": pr.WHO_PM25_24H,
        # Not a citation. It is this site's own statement about its own numbers,
        # and a reader must be able to read it in the language they chose.
        "source_unvalidated": i18n.t(lang, "guide", "source_unvalidated",
                                     risk.SOURCE_UNVALIDATED),
        "epa_rows": _epa_rows(lang),
        "intensity_rows": _intensity_rows(lang),
        "factor_rows": _factor_rows(lang),
    })
    return _render(request, "guide.html", ctx, session_id(request), theme, lang)


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


def _displayable_sessions(request: Request) -> set:
    """Session hashes whose blocked-prompt text this page may print."""
    return {normalize.session_hash("red-team-demo"),
            normalize.session_hash(session_id(request))}


def _day_label(date_str: str) -> str:
    try:
        return datetime.fromisoformat(str(date_str)[:10]).strftime("%a")
    except ValueError:
        return str(date_str)[:3]


def _set_cookies(response, request: Request, sid: str, theme: str = None,
                 lang: str = None):
    """Attach the session and theme cookies.

    ``secure`` follows the scheme actually in use rather than being hardcoded
    True: over https the browser must never send these back in clear, and over
    the plain-http development server a Secure cookie would simply be dropped,
    silently breaking the transcript and the theme toggle.

    That is only as good as the scheme this process can see. Behind a proxy
    that terminates TLS -- which is every deployment target in docs/DEPLOY.md
    -- ``request.url.scheme`` reads "http" unless uvicorn is told to trust the
    forwarded header, because ``--forwarded-allow-ips`` defaults to 127.0.0.1
    and the proxy is not on the loopback. The Dockerfile passes that flag for
    exactly this reason. Run this app behind a proxy without it and the cookies
    will NOT be marked Secure, which is worth knowing rather than assuming.
    """
    secure = request.url.scheme == "https"
    response.set_cookie("sid", sid, httponly=True, samesite="lax", secure=secure)
    if theme is not None:
        response.set_cookie("theme", theme, samesite="lax", secure=secure)
    if lang is not None:
        response.set_cookie("lang", lang, samesite="lax", secure=secure)
    return response


def _render(request, template, ctx, sid, theme, lang):
    return _set_cookies(templates.TemplateResponse(request, template, ctx),
                        request, sid, theme, lang)


def _month_abbr(lang: str, month: int) -> str:
    """The month, short. ``strftime('%b')`` would hand a Hindi page 'Jul'.

    Twelve literal keys rather than a formatted one, so tests/test_i18n.py can
    read them back out of this file and fail when one is missing.
    """
    return (
        i18n.t(lang, "ui", "month_1", "Jan"), i18n.t(lang, "ui", "month_2", "Feb"),
        i18n.t(lang, "ui", "month_3", "Mar"), i18n.t(lang, "ui", "month_4", "Apr"),
        i18n.t(lang, "ui", "month_5", "May"), i18n.t(lang, "ui", "month_6", "Jun"),
        i18n.t(lang, "ui", "month_7", "Jul"), i18n.t(lang, "ui", "month_8", "Aug"),
        i18n.t(lang, "ui", "month_9", "Sep"), i18n.t(lang, "ui", "month_10", "Oct"),
        i18n.t(lang, "ui", "month_11", "Nov"), i18n.t(lang, "ui", "month_12", "Dec"),
    )[month - 1]


def _fmt_stamp(lang: str = "en") -> str:
    """Now, as '3:05 AM IST, 20 Jul' -- placeable on a calendar.

    Comparing two pages is impossible without the date and the zone, so both
    are always spelled out. Takes no timestamp on purpose: this stamps the
    moment the page was rendered, and accepting one would invite it to be used
    for an observation time, which is what ``_fmt_time`` is for.

    The month is looked up rather than left to ``%b``, which is either English
    or at the mercy of the server's locale -- neither of which is the language
    the reader asked for.
    """
    now = datetime.now(timezone.utc).astimezone(IST)
    return f"{now.strftime('%-I:%M %p IST')}, {now.day} {_month_abbr(lang, now.month)}"


def _age_label(ts, lang: str = "en") -> str:
    """How old a stored reading is, terse enough for a tag: '40 MIN', '5 H', '3 D'.

    Empty when the timestamp is missing or unparseable -- an invented age would
    be worse than none.
    """
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if minutes < 0:
        return ""
    if minutes < 60:
        return f"{minutes} " + i18n.t(lang, "ui", "age_unit_min", "MIN")
    if minutes < 60 * 48:
        return f"{minutes // 60} " + i18n.t(lang, "ui", "age_unit_hours", "H")
    return f"{minutes // (60 * 24)} " + i18n.t(lang, "ui", "age_unit_days", "D")


def _back(request: Request, sid: str, theme: str, lang: str):
    persona = read_persona(request)
    response = RedirectResponse("/?" + _qs(persona, theme, lang) + "#ask",
                                status_code=303)
    return _set_cookies(response, request, sid)
