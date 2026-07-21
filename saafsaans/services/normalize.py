"""Pure helpers: persona normalization, AQI category, privacy utilities.

Everything here is side-effect free and cheap to unit-test. These functions
are the single source of truth for how UI labels map to advisory keywords and
how AQI values map to CPCB categories/colors, so the LLM prompt, the ES search,
and the UI badge all stay consistent.
"""
import hashlib
import re

# --- Persona label -> advisory keyword maps -------------------------------
# UI shows human labels; ES search + advisory docs use these keyword values.
CONDITION_MAP = {
    "Fit": "any",       # "Fit" = no relevant condition (reads better than "None")
    "None": "any",      # kept for backward compatibility
    "Asthma": "asthma",
    "Heart condition": "heart",
    "Pregnancy": "pregnancy",
    "COPD": "copd",
}
ACTIVITY_MAP = {
    "Outdoor exercise": "outdoor_exercise",
    "Commute": "commute",
    "School run": "school_run",
    "Stay home": "stay_home",
}
AGE_MAP = {
    "Child": "child",
    "Adult": "adult",
    "Senior": "senior",
}


def norm_condition(label: str) -> str:
    return CONDITION_MAP.get(label, "any")


def norm_activity(label: str) -> str:
    return ACTIVITY_MAP.get(label, "any")


def norm_age(label: str) -> str:
    return AGE_MAP.get(label, "any")


# --- AQI category / color -------------------------------------------------
# The six official CPCB National AQI bands. Earlier versions collapsed 0-100
# into a single "Good", which merged two distinct CPCB categories and made the
# six-segment scale in the UI unrepresentable. Hex values are the light-theme
# band inks from the approved design.
#
# (upper_bound, label, color_name, hex, slug). Ordered; first match wins.
AQI_BANDS = [
    (50,  "Good",         "blue",    "#2f6fb5", "g1"),
    (100, "Satisfactory", "teal",    "#3f7180", "g2"),
    (200, "Moderate",     "ochre",   "#8a5a0e", "g3"),
    (300, "Poor",         "orange",  "#9c4519", "g4"),
    (400, "Very Poor",    "red",     "#8a2a26", "g5"),
]
_SEVERE = ("Severe", "maroon", "#58150e", "g6")
_UNKNOWN = ("Unknown", "grey", "#9e9e9e", "gx")


def aqi_category(aqi):
    """Return ``(label, color_name, hex)`` for an AQI value.

    Defensive: ``None`` or a non-numeric value -> Unknown/grey. Negatives are
    clamped for the band decision; the caller still displays the raw value.
    """
    return band_for(aqi)[:3]


def band_for(aqi):
    """Return ``(label, color_name, hex, slug)`` -- as ``aqi_category`` plus the
    CSS token slug (``g1``-``g6``) the stylesheet uses for that band."""
    if aqi is None:
        return _UNKNOWN
    try:
        value = int(aqi)
    except (TypeError, ValueError):
        return _UNKNOWN
    value = max(value, 0)
    for upper, label, color_name, hex_, slug in AQI_BANDS:
        if value <= upper:
            return (label, color_name, hex_, slug)
    return _SEVERE


def band_slug(aqi) -> str:
    """CSS token slug for an AQI value: ``g1``-``g6``, or ``gx`` when unknown."""
    return band_for(aqi)[3]


# Plain-language meaning of each AQI category, for lay readers. Keyed by the
# label returned by aqi_category().
AQI_MEANING = {
    "Good": "Air is clean. Outdoor activity is fine for everyone.",
    "Satisfactory": "Fine for almost everyone. A few unusually sensitive people "
                    "may notice minor discomfort during heavy exertion.",
    "Moderate": "Acceptable for most. Sensitive groups (asthma, heart/lung "
                "conditions, kids, seniors) should take it easy on heavy exertion.",
    "Poor": "Unhealthy for sensitive groups. Everyone should cut back on long or "
            "intense outdoor activity; sensitive people should stay in.",
    "Very Poor": "Unhealthy for everyone. Avoid outdoor exertion; wear an N95 if "
                 "you must go out and run a purifier indoors.",
    "Severe": "Hazardous — a health emergency. Stay indoors, seal windows, run a "
              "purifier. Even healthy people can feel effects.",
    "Unknown": "Air-quality reading is unavailable right now. Treat conditions as "
               "unhealthy until you can confirm.",
}


def aqi_meaning(label: str) -> str:
    """Plain-language sentence for an AQI category label."""
    return AQI_MEANING.get(label, AQI_MEANING["Unknown"])


# One-sentence, lay-reader definitions of the technical terms shown in the UI.
# Used for tooltips and the "What these numbers mean" glossary.
GLOSSARY = {
    "AQI": "Air Quality Index — a 0-500+ score combining several pollutants. "
           "Higher is worse; India uses the CPCB scale (Good to Severe).",
    "PM2.5": "Fine particles under 2.5 micrometres — small enough to reach deep "
             "into the lungs and bloodstream. The main health concern in Delhi.",
    "PM10": "Coarser dust particles under 10 micrometres — irritate the airways "
            "and eyes; includes road and construction dust.",
    "CPCB": "Central Pollution Control Board — the Indian government body that "
            "monitors pollution across the country. Its name appears beside a "
            "reading to say which monitoring network that reading is credited to.",
    # Describes the unit only. What the site's own figures are measured in is a
    # separate question, so this deliberately makes no claim about them.
    "µg/m³": "Micrograms per cubic metre — a way of saying how much of something "
             "is floating in a given amount of air. A microgram is a millionth of "
             "a gram, and a bigger number means more of it in the same air.",
    # Says what an N95 is, not what it does: the strongest available evidence on
    # mask benefit is rated very low certainty, so no effectiveness claim is made.
    "N95": "A close-fitting disposable face mask made from a filter material "
           "graded to a United States standard. The European grade of the same "
           "kind of mask is called FFP2.",
    "Dominant pollutant": "The pollutant driving today's AQI (e.g. pm25 = fine "
                          "particles, pm10 = dust, o3 = ozone, no2 = traffic gas).",
    "Risk score": "A 0-100 estimate of today's risk FOR YOU, combining the air "
                  "quality with your age, health condition, and planned activity.",
}


# --- Privacy helpers ------------------------------------------------------
EXCERPT_MAX = 120


def session_hash(session_id: str) -> str:
    """12-char sha256 of a session id. Raw id is never stored anywhere."""
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:12]


def excerpt(text: str, limit: int = EXCERPT_MAX) -> str:
    """Cap untrusted prompt text before it is logged to security-events."""
    return (text or "")[:limit]


_TOKEN_RE = re.compile(r"(token|api[_-]?key)=([^&\s]+)", re.IGNORECASE)


def sanitize_error(exc) -> str:
    """Turn an exception into a short, secret-free string for telemetry.

    Stores the exception class plus a truncated message with any
    ``token=``/``api_key=`` query values redacted, so secrets and raw user
    text never reach the ``app-telemetry`` index.
    """
    if exc is None:
        return ""
    name = type(exc).__name__
    msg = _TOKEN_RE.sub(r"\1=REDACTED", str(exc))
    msg = msg[:200]
    return f"{name}: {msg}" if msg else name


# Plain-language explanation of each persona health condition. The picker offers
# clinical labels ("COPD") that a lay reader will not recognise, so every option
# is explained wherever it is offered and in the Guide.
CONDITION_HELP = {
    "Fit": "No condition that makes polluted air riskier for you than for an average adult.",
    "Asthma": "A long-term condition where the airways tighten and inflame. Fine particles "
              "and traffic gases are common triggers.",
    "Heart condition": "Any diagnosed heart or circulatory condition. Fine particles raise "
                       "the short-term risk of angina and irregular heartbeats.",
    "Pregnancy": "Raises sensitivity to fine particles, which are linked to lower "
                 "birth weight and preterm birth.",
    "COPD": "Chronic Obstructive Pulmonary Disease — long-term lung damage, usually from "
            "smoking or long exposure to smoke and dust, that narrows the airways and makes "
            "breathing harder. Polluted air can trigger a flare-up.",
}


def condition_help(label: str) -> str:
    """One-line explanation of a persona health condition."""
    return CONDITION_HELP.get(label, "")
