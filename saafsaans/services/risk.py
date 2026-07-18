"""Pure, deterministic persona risk scorer.

Turns an AQI reading plus a persona (condition/activity/age keywords) into a
0-100 risk score with a band, color, human-readable drivers, and a headline.

Side-effect free and cheap to unit-test -- this is the single source of truth
for how the Command Center "risk" tile is computed, so the UI never has to
invent its own math. All inputs are the normalize.py keyword vocab; unknown
keywords fall back to the neutral (+0) bucket so a bad label never crashes.

Scoring model (documented weights)
----------------------------------
score = aqi_base + condition_pts + activity_pts + age_pts, clamped to [0, 100].

* aqi_base maps the AQI to roughly 0-70. Exertion/health only *add* on top,
  so clean air keeps everyone low no matter the persona.
* condition_pts: chronic cardiopulmonary conditions dominate sensitivity.
* activity_pts: exertion multiplies the inhaled dose; staying home lowers it.
* age_pts: the very young and old have less physiological reserve.

Bands: <20 Low, <40 Moderate, <60 High, <80 Very High, else Extreme.
"""
from .normalize import aqi_category

# --- Weight tables --------------------------------------------------------
# AQI -> base points (~0-70). Buckets mirror the CPCB categories.
def _aqi_base(aqi: int) -> int:
    if aqi <= 50:
        return 5
    if aqi <= 100:
        return 15
    if aqi <= 200:
        return 30
    if aqi <= 300:
        return 50
    if aqi <= 400:
        return 65
    return 75


# Chronic-condition sensitivity: COPD/heart the most exposed, none neutral.
CONDITION_PTS = {
    "copd": 18,
    "heart": 16,
    "pregnancy": 14,
    "asthma": 12,
    "any": 0,
}

# Activity exposure: exertion multiplies dose; staying indoors reduces it.
ACTIVITY_PTS = {
    "outdoor_exercise": 14,
    "school_run": 9,
    "commute": 7,
    "stay_home": -6,
    "any": 0,
}

# Age vulnerability: children and seniors have less reserve.
AGE_PTS = {
    "senior": 10,
    "child": 8,
    "adult": 0,
    "any": 0,
}

# --- Bands ----------------------------------------------------------------
# (name, exclusive-upper-threshold, hex). Last band is the catch-all.
RISK_BANDS = ["Low", "Moderate", "High", "Very High", "Extreme"]
_BAND_TABLE = [
    ("Low", 20, "#2e7d32"),
    ("Moderate", 40, "#ef6c00"),
    ("High", 60, "#c62828"),
    ("Very High", 80, "#7f0000"),
    ("Extreme", 101, "#4a0000"),
]

_HEADLINE = {
    "Low": "Low risk -- normal activity is fine today",
    "Moderate": "Moderate risk -- sensitive groups take it easy",
    "High": "High risk -- avoid outdoor exertion today",
    "Very High": "Very high risk -- stay indoors and mask outside",
    "Extreme": "Extreme risk -- stay home, keep air purifiers on",
}

# Plain "what to do" line per band, so the score is actionable for lay readers.
BAND_ADVICE = {
    "Low": "Go ahead with your plans. No special precautions needed.",
    "Moderate": "You can go out, but keep intense activity short and carry a mask "
                "if you're in a sensitive group.",
    "High": "Skip outdoor exercise. Keep trips short and wear an N95 outside.",
    "Very High": "Stay indoors if you can. Wear an N95 for any essential trip and "
                 "run an air purifier at home.",
    "Extreme": "Do not go outdoors. Seal windows, keep a purifier running, and "
               "seek care if you feel unwell.",
}


def band_advice(band: str) -> str:
    """Plain 'what to do' guidance for a risk band."""
    return BAND_ADVICE.get(band, BAND_ADVICE["High"])


def _band_for(score: int):
    """Return ``(band_name, hex)`` for a clamped 0-100 score."""
    for name, upper, hex_ in _BAND_TABLE:
        if score < upper:
            return name, hex_
    return _BAND_TABLE[-1][0], _BAND_TABLE[-1][2]


def compute_risk(aqi, condition_kw: str, activity_kw: str, age_kw: str) -> dict:
    """Score persona risk from an AQI reading. Returns the RISK dict contract.

    Keys: ``score`` (int 0-100), ``band`` (RISK_BANDS), ``color`` (hex),
    ``drivers`` (list of short strings), ``headline`` (one line). Pure and
    defensive: a ``None``/invalid AQI is treated as 0, unknown persona
    keywords score +0.
    """
    try:
        aqi_val = max(int(aqi), 0)
    except (TypeError, ValueError):
        aqi_val = 0

    base = _aqi_base(aqi_val)
    cond_pts = CONDITION_PTS.get(condition_kw, 0)
    act_pts = ACTIVITY_PTS.get(activity_kw, 0)
    age_pts = AGE_PTS.get(age_kw, 0)

    score = base + cond_pts + act_pts + age_pts
    score = max(0, min(100, score))
    band, color = _band_for(score)

    # --- Drivers: rank the biggest contributors, AQI always shown first ---
    cat_label = aqi_category(aqi_val)[0]
    drivers = [f"AQI {aqi_val} ({cat_label})"]

    _COND_LABEL = {
        "copd": "COPD raises risk",
        "heart": "Heart condition raises risk",
        "pregnancy": "Pregnancy raises risk",
        "asthma": "Asthma raises risk",
    }
    _ACT_LABEL = {
        "outdoor_exercise": "Outdoor exertion multiplies dose",
        "school_run": "School run adds outdoor exposure",
        "commute": "Commute adds outdoor exposure",
        "stay_home": "Staying home lowers exposure",
    }
    _AGE_LABEL = {
        "child": "Child is more vulnerable",
        "senior": "Senior is more vulnerable",
    }

    # (weight, label) so we can surface the strongest persona factors.
    factors = []
    if condition_kw in _COND_LABEL:
        factors.append((cond_pts, _COND_LABEL[condition_kw]))
    if activity_kw in _ACT_LABEL:
        factors.append((act_pts, _ACT_LABEL[activity_kw]))
    if age_kw in _AGE_LABEL:
        factors.append((age_pts, _AGE_LABEL[age_kw]))
    # Sort by absolute weight so "stay home" (-6) can still surface as a driver.
    factors.sort(key=lambda f: abs(f[0]), reverse=True)
    drivers.extend(label for _, label in factors[:2])

    return {
        "score": score,
        "band": band,
        "color": color,
        "drivers": drivers,
        "headline": _HEADLINE[band],
        "advice": BAND_ADVICE[band],
    }
