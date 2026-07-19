"""SaafSaans Command Center — Streamlit UI + orchestration.

Four tabs over one shared persona/state:
  Advisor       — live AQI + personal risk + forecast window + grounded chat
  City Pulse    — all Delhi stations live + 24h AQI trend (Elasticsearch)
  Observability — telemetry KPIs from app-telemetry (Elastic Observability)
  Security      — prompt-injection events from security-events + red-team demo

Every external call is timeout-bounded with a graceful fallback, so the demo
never crashes regardless of which credentials are present. Dashboard queries are
cached so switching tabs stays snappy.
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402  (bundled with streamlit)
import streamlit as st  # noqa: E402

from saafsaans.services import (  # noqa: E402
    auth, config, es, forecast, guard, llm, metrics, normalize, risk, ui, waqi,
)
from saafsaans.attack_demo import ATTACKS  # noqa: E402

LOCALITIES = waqi.LOCALITIES
REGION_OF = {loc: region for region, locs in waqi.REGIONS.items() for loc in locs}
AGES = ["Child", "Adult", "Senior"]
CONDITIONS = ["Fit", "Asthma", "Heart condition", "Pregnancy", "COPD"]
ACTIVITIES = ["Outdoor exercise", "Commute", "School run", "Stay home"]


def _loc_label(loc: str) -> str:
    """Group the flat selectbox by region: 'Delhi · Anand Vihar'."""
    return f"{REGION_OF.get(loc, 'Delhi')} · {loc}"


# --- shared resources / caching -------------------------------------------
@st.cache_resource(show_spinner=False)
def get_client():
    """One Elasticsearch client per process (or None in mock mode)."""
    return es.get_client()


@st.cache_data(ttl=120, show_spinner=False)
def cached_reading(locality: str):
    """Live AQI for one locality, cached 2 min. Indexes on each cache miss."""
    reading, status = waqi.get_aqi(locality, es_client=get_client())
    return reading, status


@st.cache_data(ttl=300, show_spinner=False)
def live_station_readings():
    """Display-only live AQI per station (no indexing — Advisor handles that).

    Fallback for the City Pulse grid only when Elasticsearch has no readings.
    Passing es_client=None avoids double-indexing the same localities.
    """
    out = {}
    for loc in LOCALITIES:
        reading, _status = waqi.get_aqi(loc, es_client=None)
        out[loc] = reading
    return out


@st.cache_data(ttl=30, show_spinner=False)
def cached_telemetry_kpis():
    return metrics.telemetry_kpis(get_client())


@st.cache_data(ttl=30, show_spinner=False)
def cached_security_stats():
    return metrics.security_stats(get_client())


@st.cache_data(ttl=60, show_spinner=False)
def cached_trend(locality: str):
    return metrics.aqi_trend(get_client(), locality=locality, hours=24)


def get_identity():
    """Return ``(session_hash, user_hash)``.

    ``user_hash`` is the salted hash of a signed-in identity (or None). When
    signed in, telemetry correlates to that hash across sessions; otherwise a
    random per-session hash is used. Raw email/phone is never involved here.
    """
    if "sid" not in st.session_state:
        st.session_state["sid"] = str(uuid.uuid4())
    user_hash = st.session_state.get("user_id")  # salted hash or None
    session_hash = user_hash or normalize.session_hash(st.session_state["sid"])
    return session_hash, user_hash


# --- app -------------------------------------------------------------------
def main():
    st.set_page_config(page_title="SaafSaans Command Center", page_icon="◐",
                       layout="wide")
    ui.inject_theme()

    st.markdown("## SaafSaans — Command Center")
    st.caption("Delhi Air Quality & Public Health Companion · "
               "live AQI · grounded advice · full observability & security")

    persona = sidebar()
    client = get_client()

    tab_advisor, tab_city, tab_obs, tab_sec = st.tabs(
        ["Advisor", "City Pulse", "Observability", "Security"]
    )
    with tab_advisor:
        advisor_tab(persona, client)
    with tab_city:
        city_pulse_tab()
    with tab_obs:
        observability_tab()
    with tab_sec:
        security_tab(client)

    st.divider()
    st.caption("Data: WAQI/CPCB stations · Search & monitoring: Elastic · "
               "Model: Gemini via OpenRouter")


def sidebar():
    with st.sidebar:
        st.header("Your persona")
        locality = st.selectbox("Locality", LOCALITIES, format_func=_loc_label)
        age = st.selectbox("Age group", AGES, index=1)
        condition = st.selectbox("Health condition", CONDITIONS,
                                 help="Choose 'Fit' if none of these apply.")
        activity = st.selectbox("Planned activity", ACTIVITIES)

        _login_box()

        st.divider()
        st.markdown(
            ui.service_status_html(config.es_mode(), config.waqi_available(),
                                   config.llm_available()),
            unsafe_allow_html=True,
        )
        with st.expander("How SaafSaans uses Elastic"):
            st.markdown(
                "- **Search** — health advisories are retrieved from Elasticsearch "
                "(`health-advisories`, BM25) to ground every answer.\n"
                "- **Observability** — each request is logged to `app-telemetry`; "
                "the Observability tab reads it live.\n"
                "- **Security** — blocked prompt-injection attempts are audited in "
                "`security-events`; the Security tab reads it live.\n\n"
                "No personal data is stored — only a hashed id, place, and status."
            )
        st.caption("Your persona stays in this session only — never written to "
                   "any index. Logs store just a hashed id.")
    return {"locality": locality, "age": age, "condition": condition,
            "activity": activity}


def _login_box():
    """Optional sign-in. Stores only a salted hash — never the raw email/phone."""
    with st.expander("Sign in (optional)"):
        if st.session_state.get("user_id"):
            st.caption(f"Signed in as **{st.session_state.get('user_masked', 'you')}** "
                       f"· id `{st.session_state['user_id'][:8]}…`")
            if st.button("Sign out"):
                st.session_state.pop("user_id", None)
                st.session_state.pop("user_masked", None)
                st.rerun()
            return
        st.caption("Optional — lets your activity carry across sessions. We store "
                   "only a one-way hash, never your email or phone.")
        with st.form("login_form", clear_on_submit=True):
            identity = st.text_input("Email or phone")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            if auth.is_valid(identity):
                # Hash immediately; the raw value is never stored anywhere.
                st.session_state["user_id"] = auth.hash_identity(
                    identity, config.login_salt())
                st.session_state["user_masked"] = auth.mask(identity)
                st.rerun()
            else:
                st.warning("Enter a valid email or phone number.")


# --- Tab 1: Advisor --------------------------------------------------------
def advisor_tab(persona, client):
    locality = persona["locality"]
    reading, waqi_status = cached_reading(locality)
    category = normalize.aqi_category(reading.get("aqi"))

    meaning = normalize.aqi_meaning(category[0])
    left, right = st.columns([3, 2])
    with left:
        st.markdown(ui.aqi_hero_html(reading, category, meaning=meaning),
                    unsafe_allow_html=True)
    with right:
        risk_doc = risk.compute_risk(
            reading.get("aqi"),
            normalize.norm_condition(persona["condition"]),
            normalize.norm_activity(persona["activity"]),
            normalize.norm_age(persona["age"]),
        )
        st.markdown(ui.risk_gauge_html(risk_doc), unsafe_allow_html=True)

    window = forecast.best_window(
        reading.get("aqi"),
        dominant_pollutant=reading.get("dominant_pollutant"),
        forecast=reading.get("forecast"),
    )
    st.markdown(
        ui.kpi_row_html([
            {"label": "Best time to go out", "value": window["window"],
             "sub": window["rationale"][:80]},
            {"label": "Dominant pollutant", "value": reading.get("dominant_pollutant"),
             "sub": "live station reading" if not reading.get("stale") else "cached sample"},
            {"label": "Data status", "value": ("LIVE" if waqi_status == "ok" else "CACHED"),
             "sub": "from WAQI/CPCB" if waqi_status == "ok" else "sample (no live feed)"},
        ]),
        unsafe_allow_html=True,
    )

    outlook = forecast.daily_outlook(reading.get("forecast"))
    if outlook:
        with st.expander("PM2.5 multi-day outlook (WAQI forecast)"):
            st.dataframe(pd.DataFrame(outlook), hide_index=True)

    with st.expander("What these numbers mean"):
        for term, definition in normalize.GLOSSARY.items():
            st.markdown(f"- **{term}** — {definition}")

    st.divider()
    cond_display = "Fit" if persona["condition"] in ("Fit", "None") else persona["condition"]
    st.markdown(
        f"**Ask SaafSaans** — next answer for  ·  **Age:** {persona['age']}  ·  "
        f"**Health:** {cond_display}  ·  **Activity:** {persona['activity']}  ·  "
        f"**Location:** {locality}"
    )

    if "history" not in st.session_state:
        st.session_state["history"] = []
    for msg in st.session_state["history"]:
        with st.chat_message(msg["role"]):
            if msg.get("html"):
                st.markdown(msg["html"], unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])
            if msg.get("used"):
                with st.expander("What the app used"):
                    st.markdown(msg["used"])

    prompt = st.chat_input("Ask about going out, masks, timing, symptoms…")
    if prompt:
        handle_message(prompt, persona, reading, waqi_status, client)


def handle_message(prompt, persona, reading, waqi_status, client):
    session_hash, user_hash = get_identity()
    uh = {"user_hash": user_hash} if user_hash else {}  # only the hash, ever
    locality = persona["locality"]
    st.session_state["history"].append({"role": "user", "content": prompt})

    start = time.time()

    # 1) Guard: block injection before the LLM is ever called.
    ok, pattern = guard.check(prompt)
    if not ok:
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": session_hash,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(prompt), "action_taken": "blocked",
            **uh,
        })
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": session_hash,
            "event": "blocked", "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "skipped", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": locality, "error": "", **uh,
        })
        refusal = ui.refusal_html(pattern)
        st.session_state["history"].append({"role": "assistant", "html": refusal})
        _bust_dashboards()
        st.rerun()

    try:
        with st.spinner("Checking the air and preparing your advice…"):
            # 2) Retrieve advisories (ES BM25, in-process fallback).
            advisories = es.search_advisories(
                reading.get("aqi") or 0,
                normalize.norm_condition(persona["condition"]),
                normalize.norm_activity(persona["activity"]),
                normalize.norm_age(persona["age"]),
                client=client,
            )
            # 3) LLM (or rule-based fallback), then parse into advice-card sections.
            persona_labels = {"age_group": persona["age"], "condition": persona["condition"],
                              "activity": persona["activity"]}
            best_window = forecast.best_window(
                reading.get("aqi"),
                dominant_pollutant=reading.get("dominant_pollutant"),
                forecast=reading.get("forecast"),
            )
            text, tokens, llm_status = llm.answer(
                reading, persona_labels, advisories, prompt,
                locality=locality, timestamp=es.now_iso(), best_window=best_window,
            )
            sections = llm.parse_advice(text)
            card = ui.advice_card_html(sections)
            used = _format_used(reading, waqi_status, advisories)
        st.session_state["history"].append({"role": "assistant", "html": card, "used": used})

        degraded = []
        if waqi_status == "fallback":
            degraded.append("waqi_fallback")
        if llm_status == "llm_fallback":
            degraded.append("llm_fallback")
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": session_hash,
            "event": "chat_completed", "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": llm_status, "llm_tokens": tokens,
            "aqi_value": reading.get("aqi"), "locality": locality,
            "error": "; ".join(degraded), **uh,
        })
    except Exception as exc:  # pragma: no cover - top-level safety net
        fallback = ("Sorry — something went wrong preparing your advice. When in "
                    "doubt, minimise outdoor exposure and wear an N95 outside.")
        st.session_state["history"].append({"role": "assistant", "content": fallback})
        es.log_telemetry(client, {
            "@timestamp": es.now_iso(), "session_hash": session_hash,
            "event": "error", "latency_ms": int((time.time() - start) * 1000),
            "waqi_status": waqi_status, "llm_status": "error", "llm_tokens": 0,
            "aqi_value": reading.get("aqi"), "locality": locality,
            "error": normalize.sanitize_error(exc), **uh,
        })
    _bust_dashboards()
    # Re-run so the history loop repaints every message above the pinned chat
    # input; rendering inline here would place new turns below the input box.
    st.rerun()


def _format_used(reading, waqi_status, advisories):
    lines = [
        f"**AQI reading** ({waqi_status}): {reading.get('aqi')} · "
        f"PM2.5 {reading.get('pm25')} · dominant {reading.get('dominant_pollutant')}"
        + (" · **STALE / cached sample**" if reading.get("stale") else ""),
        "", "**Advisory sources (BM25 from Elasticsearch):**",
    ]
    for a in advisories:
        lines.append(f"- _{a.get('source', 'n/a')}_ — {a.get('advice', '')}")
    return "\n".join(lines)


def _bust_dashboards():
    """Refresh cached dashboard data after a new event is logged."""
    cached_telemetry_kpis.clear()
    cached_security_stats.clear()


# --- Tab 2: City Pulse -----------------------------------------------------
def city_pulse_tab():
    st.markdown("#### Delhi-NCR station grid")
    st.caption("Live air quality across the region — the latest reading per "
               "station, read from Elasticsearch (`aqi-readings`).")
    # Primary source: latest reading per station from Elasticsearch (fast, no
    # HTTP on this eager-rendered tab). Only fetch live if ES has no readings.
    grid = metrics.station_grid(get_client(), LOCALITIES)
    by_station = {r.get("station"): r for r in grid}
    missing = [loc for loc in LOCALITIES if loc not in by_station]
    live = live_station_readings() if missing else {}

    any_stale = False

    def _card(loc):
        nonlocal any_stale
        if loc in by_station:
            aqi, stale = by_station[loc].get("aqi"), False
        else:
            r = live.get(loc, {})
            aqi, stale = r.get("aqi"), bool(r.get("stale"))
            any_stale = any_stale or stale
        return {"name": loc, "aqi": aqi,
                "category": normalize.aqi_category(aqi), "stale": stale}

    for region, locs in waqi.REGIONS.items():
        st.markdown(f"**{region}**")
        st.markdown(ui.station_grid_html([_card(loc) for loc in locs]),
                    unsafe_allow_html=True)
    if any_stale:
        st.caption("STALE = cached sample (no live WAQI token for that station).")

    st.markdown("#### 24-hour AQI trend")
    col1, col2 = st.columns([1, 3])
    with col1:
        loc = st.selectbox("Station", LOCALITIES, key="trend_loc",
                           format_func=_loc_label)
    trend = cached_trend(loc)
    points = trend.get("points") or []
    if points:
        df = pd.DataFrame(points)
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.dropna(subset=["ts"]).set_index("ts")
        st.line_chart(df["aqi"], height=260)
    else:
        st.info("No trend data yet. Run `python -m saafsaans.seed_demo_history` "
                "to backfill 24-48h of readings, or keep using the app to "
                "accumulate live readings.")


# --- Tab 3: Observability --------------------------------------------------
def observability_tab():
    st.markdown("#### How the app is performing")
    st.caption("Read **live from Elasticsearch** (`app-telemetry`) each time this "
               "loads. Every question the app answers is logged here — how fast it "
               "responded, whether it used live data or a fallback, and how much AI "
               "it cost. No personal data is stored — only a hashed id, place, and "
               "status.")
    kpis = cached_telemetry_kpis()
    st.markdown(ui.kpi_row_html([
        {"label": "Questions answered", "value": kpis.get("total", 0),
         "sub": "total logged events"},
        {"label": "Typical response", "value": f'{kpis.get("latency_p50", 0):.0f} ms',
         "sub": "median (p50)"},
        {"label": "Slowest 5%", "value": f'{kpis.get("latency_p95", 0):.0f} ms',
         "sub": "p95 latency"},
        {"label": "Live air-data misses", "value": f'{kpis.get("waqi_fallback_rate", 0)*100:.0f}%',
         "sub": "used cached sample (WAQI fallback)"},
        {"label": "AI fallback used", "value": f'{kpis.get("llm_fallback_rate", 0)*100:.0f}%',
         "sub": "rule-based instead of Gemini"},
        {"label": "AI tokens used", "value": kpis.get("total_tokens", 0),
         "sub": "total Gemini tokens"},
    ]), unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Events by type**")
        by_event = kpis.get("by_event") or {}
        if by_event:
            st.bar_chart(pd.Series(by_event, name="count"), height=240)
        else:
            st.info("No telemetry yet — use the Advisor tab or seed demo history.")
    with c2:
        st.markdown("**Requests by locality**")
        by_loc = kpis.get("by_locality") or []
        if by_loc:
            df = pd.DataFrame(by_loc).set_index("locality")
            st.bar_chart(df["count"], height=240)
        else:
            st.info("No locality data yet.")


# --- Tab 4: Security -------------------------------------------------------
def security_tab(client):
    st.markdown("#### Protecting the assistant from misuse")
    st.caption("SaafSaans blocks prompt-injection attempts (people trying to trick "
               "the AI into ignoring its rules) **before** they reach the model. "
               "Every attempt is audited **live in Elasticsearch** (`security-events`). "
               "Only a 120-character snippet is kept — never full personal data.")
    stats = cached_security_stats()
    st.markdown(ui.kpi_row_html([
        {"label": "Attacks blocked", "value": stats.get("total_blocked", 0),
         "sub": "stopped before the AI"},
        {"label": "Block rate", "value": f'{stats.get("block_rate", 0)*100:.0f}%',
         "sub": "of flagged attempts"},
        {"label": "Attack types seen", "value": len(stats.get("by_pattern") or []),
         "sub": "distinct patterns"},
    ]), unsafe_allow_html=True)

    if st.button("Run red-team attack simulation", type="primary"):
        _run_attacks(client)
        cached_security_stats.clear()
        st.success(f"Fired {len(ATTACKS)} malicious prompts — all blocked before "
                   "the LLM and logged to security-events.")
        # No st.rerun(): the charts below render after this handler in the same
        # run, and the cache was cleared, so they reflect the new events while
        # this confirmation stays visible.

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Blocked by pattern**")
        by_pat = stats.get("by_pattern") or []
        if by_pat:
            df = pd.DataFrame(by_pat).set_index("pattern")
            st.bar_chart(df["count"], height=240)
        else:
            st.info("No attacks logged yet — click the red-team button above.")
    with c2:
        st.markdown("**Attacks over time**")
        over_time = stats.get("over_time") or []
        if over_time:
            df = pd.DataFrame(over_time)
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
            df = df.dropna(subset=["ts"]).set_index("ts")
            st.bar_chart(df["count"], height=240)
        else:
            st.info("No time-series data yet.")


def _run_attacks(client):
    session_hash = normalize.session_hash("red-team-demo")
    for _name, prompt in ATTACKS:
        ok, pattern = guard.check(prompt)
        if ok:
            continue
        es.log_security(client, {
            "@timestamp": es.now_iso(), "session_hash": session_hash,
            "event_type": "prompt_injection", "pattern_matched": pattern,
            "prompt_excerpt": normalize.excerpt(prompt), "action_taken": "blocked",
        })
    # Make the just-logged events immediately queryable for the refreshed charts.
    try:
        if client is not None:
            client.indices.refresh(index=es.INDEX_SECURITY)
    except Exception:
        pass


main()
