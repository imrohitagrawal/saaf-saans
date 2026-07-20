"""Presentation logic for the web views.

Pure functions that turn service-layer dicts into the strings and geometry the
templates render. Kept out of Jinja so the copy and the arithmetic are
unit-testable, and out of ``services/`` so the API-level contracts stay free of
presentation concerns.

The voice here is deliberate: human and direct, never softening a severe
reading and never dramatising a mild one. See design_handoff_saafsaans/README.md.
"""
import math

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
# The same conditions again, as the possessive form a sentence needs ("your
# COPD"). Written out rather than lower-cased off _CONDITION_PHRASE because
# lower-casing turns the acronym COPD into "copd" mid-sentence. A test pins
# these keys to _CONDITION_PHRASE so the two cannot drift apart.
_CONDITION_REASON = {
    "Asthma": "your asthma",
    "Heart condition": "your heart condition",
    "Pregnancy": "your pregnancy",
    "COPD": "your COPD",
}
_AGE_REASON = {"Child": "being a child", "Senior": "being a senior"}


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
    """The persona factors that actually open the gap, phrased for prose.

    The baseline (main.advisor_data) holds the reader's own activity fixed and
    varies only the body: ``compute_risk(aqi, "any", their activity, "adult")``.
    The activity therefore very nearly cancels out of the subtraction, so
    naming it would credit a cause the arithmetic has almost entirely removed.
    Only health condition and age are listed.

    Almost, not exactly: ``risk.dose_points`` is a function of age *and*
    activity, because EPA publishes a breathing rate per age band per exertion
    level. A child at rest differs from an adult at rest by a little more than
    a child running differs from an adult running, so up to one point of the
    gap moves when the plans change. That residue is still an age difference,
    which is why the sentence attributes the gap to the body -- but it is why
    the sentence must not go on to deny the plans outright.
    """
    bits = []
    condition = persona.get("condition")
    if condition not in _NEUTRAL_CONDITIONS:
        bits.append(_CONDITION_REASON.get(condition, "your health condition"))
    age = _AGE_REASON.get(persona.get("age"))
    if age:
        bits.append(age)
    return " + ".join(bits)


def comparison_line(score: int, baseline: int, persona: dict) -> str:
    """Explain the gap between this persona's risk and a healthy adult's.

    The gap *is* the product's reason to exist -- the same air scores
    differently for different bodies -- so it is spelled out rather than left
    for the reader to infer from two numbers.

    The comparison person has the reader's own plans, not an invented set of
    them, so the label says so: the baseline number moves when the reader edits
    their activity, and a sentence that denied that would forfeit their trust.

    The sentence says the gap is the body. It does not go on to say "not your
    plans", because that would be very slightly false -- see ``_reasons``.

    There is no branch for a score *below* the baseline. Every term that can
    differ is non-negative except a dose residue worth at most one point, which
    age susceptibility always outweighs, so the case cannot occur; a message
    congratulating the reader on it would be copy for a situation the model
    cannot produce. Equal-or-lower collapses into the same honest sentence.
    """
    opener = f"A healthy adult with the same plans as you would be at {baseline}"
    if score > baseline:
        reasons = _reasons(persona)
        tail = (f" comes from {reasons} — the gap is your body, not the air."
                if reasons else " is higher than theirs.")
        return f"{opener}. Your {score}{tail}"
    return f"{opener} too — that's you today."


# --- The WHO comparison ----------------------------------------------------
# WHO 2021 Global Air Quality Guidelines, PM2.5: 24-hour AQG level 15 µg/m3
# (annual 5). Citation in the Guide.
WHO_PM25_24H = 15

# Spelled out, because "about six times as much" is read by everyone and
# "about 6x" is read by people who already read charts. One significant figure
# never produces a number outside this set below a thousand.
#
# "as much as", not "more than": ten times MORE than 15 is literally 165, and
# the figure meant is 150. The looser phrasing is what most writing uses and
# what the brief for this line suggested, but it overstates by one multiple
# every time, and overstating is the one thing this project does not do.
_MULTIPLE_WORDS = {
    2: "twice as much", 3: "three times as much", 4: "four times as much", 5: "five times as much",
    6: "six times as much", 7: "seven times as much", 8: "eight times as much", 9: "nine times as much",
    10: "ten times as much", 20: "twenty times as much", 30: "thirty times as much",
    40: "forty times as much", 50: "fifty times as much", 60: "sixty times as much",
    70: "seventy times as much", 80: "eighty times as much", 90: "ninety times as much",
    100: "a hundred times as much", 200: "two hundred times as much", 300: "three hundred times as much",
    400: "four hundred times as much", 500: "five hundred times as much",
}


def who_multiple(pm25):
    """How many times the WHO 24-hour PM2.5 guideline this reading is.

    Rounded to one significant figure, because the underlying value came from
    inverting an integer index and cannot support more. ``None`` when there is
    no usable reading -- the caller renders nothing, which is the only correct
    output when the alternative is a wrong number.
    """
    try:
        value = float(pm25)
    except (TypeError, ValueError):
        return None
    if value != value or value <= 0:
        return None
    ratio = value / WHO_PM25_24H
    magnitude = math.floor(math.log10(ratio))
    return round(ratio, -int(magnitude))


def who_line(pm25) -> str:
    """The WHO comparison as one plain sentence, or "" when it cannot be made.

    Deliberately phrased about the air *right now*, not about what the reader
    has breathed today. WHO's 15 µg/m3 figure is a 24-hour mean, and is itself
    defined as the 99th percentile of the annual distribution of those means --
    not a ceiling for any one day. The app holds a single near-instantaneous
    station reading. Saying "today you breathed in ten times more than is safe
    in a day" would assert both a daily average the app does not have and an
    inhaled dose it has no basis to compute. The mismatch is kept visible in
    the sentence -- "right now" against "for a whole day" -- and explained in
    full in the Guide.

    No microgram figure appears here: this sentence sits on the reading card
    where a lay reader meets it, and the unit belongs in the Guide.
    """
    multiple = who_multiple(pm25)
    if multiple is None:
        return ""
    if multiple < 2:
        if multiple < 1:
            return ("Right now the air here is cleaner than the World Health "
                    "Organization's safe level for a whole day.")
        return ("Right now the air here is about at the World Health "
                "Organization's safe level for a whole day.")
    word = _MULTIPLE_WORDS.get(int(multiple))
    if word is None:
        return ("Right now the air here holds far more of this pollution than the "
                "World Health Organization's safe level for a whole day allows.")
    return (f"Right now the air here holds about {word} of this pollution as the "
            "World Health Organization's safe level for a whole day.")


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
    from datetime import date, datetime, timedelta, timezone
    # The audience is in India; a UTC-configured server would otherwise label
    # the wrong row "Today" for five and a half hours of every day.
    today = today or datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    rows = []
    for row in outlook or []:
        try:
            day = date.fromisoformat(str(row.get("date"))[:10])
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
