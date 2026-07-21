"""Pure, deterministic persona risk scorer.

Turns an AQI reading plus a persona (condition/activity/age keywords) into a
0-100 risk score with a band, color, human-readable drivers, and a headline.

Side-effect free and cheap to unit-test -- this is the single source of truth
for how the Command Center "risk" tile is computed, so the UI never has to
invent its own math. All inputs are the normalize.py keyword vocab; unknown
keywords fall back to the neutral bucket so a bad label never crashes.

Scoring model
-------------
score = aqi_base + dose_pts + susceptibility_pts, clamped to [0, 100].

Two components, kept separate because their evidence is not the same strength
and the UI has to be able to say which is which:

* ``dose_pts`` -- GROUNDED. Derived from published inhalation rates: how much
  more air this age group moves at this activity level than a sedentary adult.
  Source is EPA's Exposure Factors Handbook (see ``SOURCE_EPA``). Exertion
  raises the inhaled dose of the same air; that much is measured, not assumed.

* ``susceptibility_pts`` -- NOT GROUNDED. Chronic condition, plus the extra
  vulnerability of children and older people beyond what their breathing rate
  explains. There is no citable single multiplier for "how much worse is this
  air for a person with COPD", so none is invented: the relative ordering is
  a stated clinical heuristic and is labelled as unvalidated wherever the
  score is explained, in the UI as well as the docs.

An earlier version of this module gave every persona factor an uncited point
value. Those numbers looked derived and were not. What could be grounded now
is; what cannot be is named as such rather than dressed up.

Bands: <20 Low, <40 Moderate, <60 High, <80 Very High, else Extreme.
"""
from math import log

from . import i18n
from .normalize import aqi_category

# --- Provenance -----------------------------------------------------------
SOURCE_EPA = (
    "U.S. EPA, Exposure Factors Handbook: 2011 Edition (EPA/600/R-09/052F), "
    "Chapter 6, Table 6-2 -- recommended short-term inhalation values, mean "
    "column, m3/min. EPA rates its own confidence in this recommendation "
    "Medium (Table 6-3)."
)
SOURCE_UNVALIDATED = (
    "Unvalidated clinical heuristic. Relative ordering only, chosen by the "
    "author from general public-health guidance; not derived from, or "
    "validated against, any published risk model."
)
SOURCE_CPCB_BANDS = (
    "Band boundaries follow the CPCB National AQI categories. The point "
    "values assigned to each band are a design choice, not a published scale."
)

# The sentence the UI shows next to the score. Kept here so the copy cannot
# drift away from what the weights actually are.
HEURISTIC_NOTICE = (
    "The exertion part of this score comes from published breathing rates "
    "(US EPA, confidence rated medium). The health-condition and age parts "
    "are our own judgement, not a validated medical model."
)

# --- Inhalation rates (grounded) ------------------------------------------
# m3/min, mean short-term values from EPA EFH 2011 Table 6-2. Only the three
# age bands the persona picker offers are carried; EPA's full table has 14.
EPA_AGE_BANDS = {
    "child": "6 to <11 years",
    "adult": "21 to <31 years",
    "senior": "61 to <71 years",
}
INHALATION_RATES = {
    "child":  {"sedentary": 4.8e-3, "light": 1.1e-2, "moderate": 2.2e-2, "high": 4.2e-2},
    "adult":  {"sedentary": 4.2e-3, "light": 1.2e-2, "moderate": 2.6e-2, "high": 5.0e-2},
    "senior": {"sedentary": 4.9e-3, "light": 1.2e-2, "moderate": 2.6e-2, "high": 4.7e-2},
}

# Which EPA activity level each persona activity is treated as. EPA does not
# publish this mapping -- it is our reading of what the activity involves, and
# is the one judgement inside the otherwise-grounded dose term.
ACTIVITY_INTENSITY = {
    "outdoor_exercise": "high",       # running, cycling, sport
    "school_run": "moderate",         # walking briskly, on foot both ways
    "commute": "light",               # standing, walking to and from transport
    "stay_home": "sedentary",         # indoors, at rest
    "any": "sedentary",               # unknown plans: assume the low end
}
# Least to most exertion. The one place this order is written down: the Guide
# renders INHALATION_RATES as a table and needs its columns in this order, and
# a second private copy next to that table would be free to disagree with the
# rates it is labelling.
INTENSITY_ORDER = ("sedentary", "light", "moderate", "high")

# Everything is expressed relative to a sedentary adult, so the dose term
# reads as "you are breathing N times as much air as a resting adult".
BASELINE_RATE = INHALATION_RATES["adult"]["sedentary"]

# The published ratios span 1.0x to 11.9x. That range is mapped onto 0..14
# points -- 14 being the value the previous heuristic already used for the
# heaviest activity, so grounding the shape of the curve does not silently
# rescale the bands. The mapping is logarithmic because risk is not believed
# to rise linearly with dose; that choice is a design decision, not a finding.
DOSE_MAX_PTS = 14
_MAX_RATIO = max(r for by_age in INHALATION_RATES.values() for r in by_age.values()) / BASELINE_RATE
_DOSE_SCALE = DOSE_MAX_PTS / log(_MAX_RATIO)


def inhalation_ratio(age_kw: str, activity_kw: str) -> float:
    """How much more air this persona moves than a sedentary adult.

    Pure lookup of EPA Table 6-2 mean rates. Unknown age or activity keywords
    fall back to adult / sedentary, which is the least alarming assumption --
    an unknown persona must never be scored as if it were exercising.
    """
    rates = INHALATION_RATES.get(age_kw) or INHALATION_RATES["adult"]
    intensity = ACTIVITY_INTENSITY.get(activity_kw, "sedentary")
    return rates[intensity] / BASELINE_RATE


def dose_points(age_kw: str, activity_kw: str) -> int:
    """Points for inhaled dose: 0 for a resting adult, 14 at the EPA maximum."""
    return round(_DOSE_SCALE * log(inhalation_ratio(age_kw, activity_kw)))


# --- Susceptibility (not grounded) ----------------------------------------
# Chronic-condition sensitivity. Ordering is asserted, magnitude is not
# measured. See SOURCE_UNVALIDATED.
CONDITION_PTS = {
    "copd": 18,
    "heart": 16,
    "pregnancy": 14,
    "asthma": 12,
    "any": 0,
}

# Extra vulnerability of the very young and the old *beyond* their breathing
# rate. This term exists because EPA's absolute rates do not support the
# intuition: a 6-11 year old moves rather less air per minute than an adult,
# so grounding age in inhalation alone would score a child as safer than an
# adult. The physiological reasons children and seniors are more affected --
# developing lungs, more air per kilogram of body weight, less reserve -- are
# real but not reducible to a citable number, so they sit here, labelled.
AGE_SUSCEPTIBILITY_PTS = {
    "senior": 10,
    "child": 8,
    "adult": 0,
    "any": 0,
}


# --- AQI base -------------------------------------------------------------
# AQI -> base points (~0-75). Buckets mirror the CPCB categories.
AQI_BASE_PTS = [(50, 5), (100, 15), (200, 30), (300, 50), (400, 65)]
AQI_BASE_MAX = 75

# No usable reading is NOT clean air. Treating a missing AQI as 0 scored it as
# the safest possible day and produced "A good day to breathe -- enjoy it
# outside" on a page that simultaneously said UNKNOWN and "treat conditions as
# unhealthy until you can confirm". Absence of evidence was being rendered as
# evidence of absence, in the one direction that can get somebody hurt. An
# unknown reading now scores as the Poor band does, which matches what
# normalize.AQI_MEANING["Unknown"] already told the reader to do.
AQI_BASE_UNKNOWN = 50


def _aqi_base(aqi: int) -> int:
    for upper, points in AQI_BASE_PTS:
        if aqi <= upper:
            return points
    return AQI_BASE_MAX


# --- Provenance registry --------------------------------------------------
def weight_table() -> list:
    """Every weight in the scoring model, with where it came from.

    Exists so the provenance is checkable rather than asserted: a test walks
    this and fails if any weight has no source, and the Guide renders it. The
    ``grounded`` flag is the honest divider -- True means a published figure,
    False means the author's ordering.
    """
    rows = []
    for age, by_intensity in INHALATION_RATES.items():
        for intensity, rate in by_intensity.items():
            rows.append({
                "table": "inhalation_rates",
                "key": f"{age} / {intensity}",
                "value": rate,
                "unit": "m3/min",
                "grounded": True,
                "source": SOURCE_EPA,
            })
    for cond, pts in CONDITION_PTS.items():
        rows.append({"table": "condition_pts", "key": cond, "value": pts,
                     "unit": "points", "grounded": False, "source": SOURCE_UNVALIDATED})
    for age, pts in AGE_SUSCEPTIBILITY_PTS.items():
        rows.append({"table": "age_susceptibility_pts", "key": age, "value": pts,
                     "unit": "points", "grounded": False, "source": SOURCE_UNVALIDATED})
    for upper, pts in AQI_BASE_PTS:
        rows.append({"table": "aqi_base_pts", "key": f"AQI <= {upper}", "value": pts,
                     "unit": "points", "grounded": False, "source": SOURCE_CPCB_BANDS})
    rows.append({"table": "aqi_base_pts", "key": "AQI > 400", "value": AQI_BASE_MAX,
                 "unit": "points", "grounded": False, "source": SOURCE_CPCB_BANDS})
    return rows


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


# --- Driver chip labels ----------------------------------------------------
# The short phrases under the score that say WHY it is what it is. Module-level
# so the i18n keys they map to are readable next to the English, and so a test
# can walk them without calling the scorer.
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
}
_AGE_LABEL = {
    "child": "Child is more vulnerable",
    "senior": "Senior is more vulnerable",
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


def compute_risk(aqi, condition_kw: str, activity_kw: str, age_kw: str,
                 lang: str = "en") -> dict:
    """Score persona risk from an AQI reading. Returns the RISK dict contract.

    Keys: ``score`` (int 0-100), ``band`` (RISK_BANDS), ``color`` (hex),
    ``drivers`` (list of short strings), ``headline`` (one line), ``advice``.
    Pure and defensive: a ``None``/invalid AQI is treated as 0, unknown persona
    keywords score the neutral bucket.

    ``lang`` translates ``drivers`` only. ``headline`` and ``advice`` are
    already translated where they are rendered -- today.html asks for
    ``T('band_advice', risk.band, risk.advice)``, keyed on the band this
    function returns -- so translating them here would hand that lookup a Hindi
    key and lose the translation, not add one. ``band`` and ``color`` stay
    English/hex because they are keys and CSS, not copy.
    """
    try:
        aqi_val = max(int(aqi), 0)
        known = True
    except (TypeError, ValueError):
        aqi_val, known = 0, False

    base = _aqi_base(aqi_val) if known else AQI_BASE_UNKNOWN
    cond_pts = CONDITION_PTS.get(condition_kw, 0)
    dose_pts = dose_points(age_kw, activity_kw)
    age_pts = AGE_SUSCEPTIBILITY_PTS.get(age_kw, 0)

    score = max(0, min(100, base + cond_pts + dose_pts + age_pts))
    band, color = _band_for(score)

    # --- Drivers: rank the biggest contributors, AQI always shown first ---
    if known:
        # The band word comes from the shared band_label group, the same one
        # the reading card uses, so the chip and the card cannot disagree about
        # what today's air is called. The whole chip is one template because
        # Hindi does not put the parenthetical where English does.
        label = aqi_category(aqi_val)[0]
        drivers = [i18n.t(lang, "driver", "aqi", "AQI {aqi} ({band})")
                   .replace("{aqi}", str(aqi_val))
                   .replace("{band}", i18n.t(lang, "band_label", label, label))]
    else:
        drivers = [i18n.t(lang, "driver", "no_reading",
                          "No reading — treated as unhealthy")]

    # (weight, label) so we can surface the strongest persona factors. An
    # activity only appears when it actually moved the score: "stay home" no
    # longer subtracts points, so listing it would claim a discount that is
    # not in the arithmetic.
    factors = []
    if condition_kw in _COND_LABEL:
        factors.append((cond_pts, i18n.t(lang, "driver", f"cond_{condition_kw}",
                                         _COND_LABEL[condition_kw])))
    if activity_kw in _ACT_LABEL and dose_pts > 0:
        factors.append((dose_pts, i18n.t(lang, "driver", f"act_{activity_kw}",
                                         _ACT_LABEL[activity_kw])))
    if age_kw in _AGE_LABEL:
        factors.append((age_pts, i18n.t(lang, "driver", f"age_{age_kw}",
                                        _AGE_LABEL[age_kw])))
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
