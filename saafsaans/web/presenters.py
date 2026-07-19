"""Presentation logic for the web views.

Pure functions that turn service-layer dicts into the strings and geometry the
templates render. Kept out of Jinja so the copy and the arithmetic are
unit-testable, and out of ``services/`` so the API-level contracts stay free of
presentation concerns.

The voice here is deliberate: human and direct, never softening a severe
reading and never dramatising a mild one. See design_handoff_saafsaans/README.md.
"""
from markupsafe import Markup

# --- Verdict ---------------------------------------------------------------
# One headline per risk band. risk.py has its own drier `headline` for the API
# contract; this is the editorial voice the hero speaks in.
_VERDICTS = {
    "Low": "A good day to breathe — enjoy it outside.",
    "Moderate": "Manageable for you today — just pace yourself.",
    "High": "Today isn't kind to your lungs — keep it indoors.",
    "Very High": "Your lungs need you indoors today.",
    "Extreme": "Don't go out unless you must — this air is dangerous for you.",
}


def verdict_for(band: str) -> str:
    """The hero headline for a risk band. Unknown bands get the cautious one."""
    return _VERDICTS.get(band, _VERDICTS["High"])


# --- Persona ---------------------------------------------------------------
# The persona appears in three places and must read as a sentence in all of
# them. Joining the raw values with dots ("Senior · copd · school run · Noida")
# reads as a database row, not as a description of a person.
_AGE_PHRASE = {"Child": "a child", "Adult": "an adult", "Senior": "a senior"}
_CONDITION_PHRASE = {
    "Fit": "in good health",
    "None": "in good health",
    "Asthma": "with asthma",
    "Heart condition": "with a heart condition",
    "Pregnancy": "who is pregnant",
    "COPD": "with COPD",
}
_ACTIVITY_PHRASE = {
    "Outdoor exercise": "planning outdoor exercise",
    "Commute": "planning a commute",
    "School run": "planning a school run",
    "Stay home": "planning to stay home",
}
_NEUTRAL_CONDITIONS = {"Fit", "None", None, ""}


def persona_sentence(persona: dict, with_place: bool = True) -> str:
    """e.g. 'a senior with COPD, planning a school run in Noida'.

    Reads as prose so it can be dropped into a sentence anywhere it is needed.
    """
    persona = persona or {}
    who = _AGE_PHRASE.get(persona.get("age"), "an adult")
    condition = _CONDITION_PHRASE.get(persona.get("condition"), "in good health")
    activity = _ACTIVITY_PHRASE.get(persona.get("activity"))
    parts = f"{who} {condition}"
    if activity:
        parts += f", {activity}"
    place = persona.get("locality")
    if with_place and place:
        parts += f" in {place}"
    return parts


def persona_kicker(persona: dict) -> str:
    """The hero's small-caps line. Place is omitted -- the hero already shows it."""
    return "FOR " + persona_sentence(persona, with_place=False).upper()


def persona_line(persona: dict) -> str:
    """The persona as a readable phrase, for the card and the transcript."""
    return persona_sentence(persona)


def _reasons(persona: dict) -> str:
    """The persona factors that moved the score, phrased for prose."""
    bits = []
    condition = persona.get("condition")
    if condition not in _NEUTRAL_CONDITIONS:
        bits.append(f"your {condition.lower()}")
    activity = persona.get("activity")
    if activity and activity != "Stay home":
        bits.append(str(activity).lower())
    return " + ".join(bits)


def comparison_line(score: int, baseline: int, persona: dict) -> str:
    """Explain the gap between this persona's risk and a healthy adult's.

    The gap *is* the product's reason to exist -- the same air scores
    differently for different bodies -- so it is spelled out rather than left
    for the reader to infer from two numbers.
    """
    if score > baseline:
        reasons = _reasons(persona)
        tail = (f" comes from {reasons} — the gap is your body and plans, not the air."
                if reasons else " is higher than theirs.")
        return f"A healthy adult in this air would be at {baseline}. Your {score}{tail}"
    if score == baseline:
        return f"A healthy adult in this air would be at {baseline} too — that's you today."
    return (f"Staying in brings you to {score} — below the healthy-adult {baseline}. "
            "Good call.")


# --- Scale geometry --------------------------------------------------------
# CPCB bands are unequal in width but drawn as fixed segments (10/10/20/20/20/20%)
# so the low bands stay legible. The marker must use the same mapping or it
# would point at the wrong segment.
_SEGMENTS = [(0, 50, 0, 10), (50, 100, 10, 20), (100, 200, 20, 40),
             (200, 300, 40, 60), (300, 400, 60, 80), (400, 500, 80, 100)]


def scale_position(aqi) -> float:
    """Marker position as a percentage across the six-segment scale bar."""
    try:
        value = max(0, min(int(aqi), 500))
    except (TypeError, ValueError):
        return 0.0
    for lo, hi, start, end in _SEGMENTS:
        if value <= hi:
            span = hi - lo
            return round(start + (value - lo) / span * (end - start), 1)
    return 100.0


# --- City ------------------------------------------------------------------
def median_aqi(stations) -> int:
    """Median AQI across stations, ignoring those with no reading."""
    values = sorted(s["aqi"] for s in (stations or []) if s.get("aqi") is not None)
    if not values:
        return 0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return round((values[mid - 1] + values[mid]) / 2)


def sparkline_svg(points, width: int = 560, height: int = 90) -> Markup:
    """Inline SVG sparkline: area fill, line, and a dot on the newest reading.

    Rendered server-side so the chart is present before any JavaScript runs.
    Returns an empty string when there is nothing to draw, letting the caller
    show an empty state instead of an axis with no data.
    """
    values = [p.get("aqi") for p in (points or []) if p.get("aqi") is not None]
    if len(values) < 2:
        return Markup("")
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = width / (len(values) - 1)
    coords = [(i * step, height - 6 - (v - lo) / span * (height - 16))
              for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"M0,{height} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords) + f" L{width},{height} Z"
    nx, ny = coords[-1]
    return Markup(
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="AQI over the last 24 hours, from {lo} to {hi}">'
        f'<path d="{area}" fill="currentColor" opacity="0.12"/>'
        f'<polyline points="{line}" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="3.5" fill="currentColor"/></svg>'
    )


# --- Provenance ------------------------------------------------------------
def provenance_chip(waqi_status: str, when: str) -> str:
    """'● LIVE · 2:00 PM' or '◌ CACHED · 2:00 PM'. Never disguise a fallback."""
    return f"● LIVE · {when}" if waqi_status == "ok" else f"◌ CACHED · {when}"


def grounding_note(waqi_status: str, when: str) -> str:
    """The trailing clause of the 'what the app used' grounding line."""
    return (f"live reading · {when} IST" if waqi_status == "ok"
            else f"cached sample (feed missed) · {when} IST")


def pct(value, total) -> str:
    """Width for a bar, as a CSS percentage string. Guards divide-by-zero."""
    try:
        if not total:
            return "0%"
        return f"{max(0.0, min(float(value) / float(total), 1.0)) * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "0%"


def outlook_rows(outlook, today=None) -> list:
    """Format the five-day PM2.5 outlook for display.

    WAQI's forecast includes days already past; those are dropped so the first
    row is always today. Dates become 'Sat 19', and today is flagged so the
    template can weight it.
    """
    from datetime import date as _date
    today = today or _date.today()
    rows = []
    for row in outlook or []:
        try:
            day = _date.fromisoformat(str(row.get("date"))[:10])
        except (TypeError, ValueError):
            continue
        if day < today:
            continue
        rows.append({
            "label": "Today" if day == today else day.strftime("%a %-d"),
            "avg": row.get("pm25_avg"),
            "is_today": day == today,
        })
    return rows[:5]


def answer_sections(sections: dict) -> list:
    """Map llm.parse_advice's contract onto the design's three labelled blocks.

    parse_advice returns a fixed-key dict that includes ``raw`` -- the entire
    model response -- and a disclaimer the card renders separately. Iterating
    the dict blindly puts both on screen, so the mapping is explicit here.

    ``window`` is deliberately dropped: the best-time window already has its own
    bar on the hero, and repeating it inside every answer is noise.
    """
    s = sections or {}
    blocks = []
    detail = (s.get("verdict_detail") or "").strip()
    if detail:
        blocks.append({"heading": "Verdict", "text": detail, "lead": True})
    precautions = [p for p in (s.get("precautions") or []) if p]
    if precautions:
        blocks.append({"heading": "What to do", "bullets": precautions})
    symptoms = [x for x in (s.get("symptoms") or []) if x]
    if symptoms:
        blocks.append({"heading": "When to seek help", "bullets": symptoms})
    return blocks


def group_attempts(attempts) -> list:
    """Group blocked attempts by detection pattern, then by distinct prompt.

    One pattern legitimately catches many different prompts -- that is the guard
    working, not a duplicate. But a flat list repeats the pattern chip on every
    row, so the eye reads a stutter and the thing that actually differs (the
    prompt) trails. Grouping puts the pattern once and the variants under it.

    Nothing is discarded: every event stays in the index, and the counts here
    add up to the number of events seen.
    """
    groups: dict = {}
    for a in attempts or []:
        pattern = a.get("pattern") or "unknown"
        g = groups.setdefault(pattern, {"pattern": pattern, "total": 0, "variants": {}})
        g["total"] += 1
        excerpt = a.get("excerpt") or ""
        v = g["variants"].get(excerpt)
        if v:
            v["count"] += 1
        else:
            g["variants"][excerpt] = {"excerpt": excerpt, "count": 1,
                                      "when": a.get("when"), "ts": a.get("ts")}
    out = []
    for g in groups.values():
        variants = sorted(g["variants"].values(), key=lambda v: -v["count"])
        out.append({"pattern": g["pattern"], "total": g["total"], "variants": variants})
    return sorted(out, key=lambda g: -g["total"])
