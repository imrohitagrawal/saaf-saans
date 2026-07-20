"""Honest, heuristic outlook helpers built on the WAQI forecast block.

Two pure functions, neither of which does any I/O:

- ``daily_outlook`` parses the optional ``forecast["daily"]["pm25"]`` block
  that WAQI returns alongside a live reading into simple per-day rows.
- ``best_window`` gives a general Delhi diurnal "when to go out" heuristic.

Both degrade gracefully: no forecast -> empty outlook, and ``best_window``
still returns a diurnal window from the current AQI alone. We are careful to
label the window a *general seasonal pattern*, never a station forecast, and we
treat forecast PM2.5 as a µg/m3 concentration (NOT an AQI value) mapped with a
documented CPCB-style scale.
"""
import datetime

from . import aqi_scale, i18n

# CPCB 24h PM2.5 concentration (µg/m3) -> label. Applied to a real
# concentration, which is what daily_outlook now produces.
#
# It did not used to. The comment here previously asserted that "WAQI forecast
# values are raw concentrations"; they are AQI sub-indices, exactly like the
# live feed's, so these concentration breakpoints were being applied to index
# points. The band was wrong whenever the two scales disagreed, which is most
# of the time. See services/aqi_scale.py.
_PM25_BANDS = [
    (30, "Good"),
    (60, "Satisfactory"),
    (90, "Moderate"),
    (120, "Poor"),
    (250, "Very Poor"),
]
_PM25_SEVERE = "Severe"


def _pm25_category(value) -> str:
    """Map a PM2.5 concentration (µg/m3) to an app band label."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    for ceiling, label in _PM25_BANDS:
        if v <= ceiling:
            return label
    return _PM25_SEVERE


def daily_outlook(forecast, lang: str = "en") -> list:
    """Parse a WAQI forecast dict into per-day PM2.5 rows.

    Expects ``forecast["daily"]["pm25"]`` to be a list of
    ``{"day": "YYYY-MM-DD", "avg": int, "min": int, "max": int}``.
    Returns ``[{date, pm25_avg:int, pm25_max:int, category:str}]`` for every
    parseable day, sorted by date. Returns ``[]`` for missing/empty/malformed
    input so the UI can simply hide the section.

    ``category`` is a display label, so ``lang`` translates it -- through the
    existing ``band_label`` group, which already carries these exact seven
    words for the live reading, rather than a second copy under a forecast key.
    The row's date and its "Today" label are NOT this function's: they are
    formatted in ``presenters.outlook_rows``, which is also the only caller and
    which currently drops ``category`` before the template sees it.
    """
    if not isinstance(forecast, dict):
        return []
    daily = forecast.get("daily")
    if not isinstance(daily, dict):
        return []
    rows_raw = daily.get("pm25")
    if not isinstance(rows_raw, list):
        return []

    out = []
    for row in rows_raw:
        if not isinstance(row, dict):
            continue
        date = row.get("day")
        if not date:
            continue
        # WAQI's forecast carries the same AQI sub-indices as the live feed,
        # not concentrations -- the docstring here used to say "µg/m3" of a
        # number that was nothing of the kind. Invert before banding, or the
        # CPCB concentration breakpoints below are applied to the wrong scale.
        avg = aqi_scale.concentration(row.get("avg"), "pm25")
        mx = aqi_scale.concentration(row.get("max"), "pm25")
        if avg is None or mx is None:
            continue
        avg = int(round(avg))
        mx = int(round(mx))
        label = _pm25_category(avg)
        out.append({
            "date": date,
            "pm25_avg": avg,
            "pm25_max": mx,
            "category": i18n.t(lang, "band_label", label, label),
        })

    out.sort(key=lambda r: r["date"])
    return out


def _is_winter(month: int) -> bool:
    """Delhi's inversion/stubble season, when mornings are worst."""
    return month in (11, 12, 1, 2)


def _pollutant_key(dominant) -> str:
    """Normalise a WAQI dominant-pollutant code to a family we reason about."""
    p = str(dominant or "").strip().lower()
    if p in ("o3", "ozone"):
        return "o3"
    if p in ("no2", "so2", "co"):
        return "no2"
    if p in ("pm25", "pm2.5", "pm10", "dust"):
        return "pm"
    return "pm"  # PM is the default driver in Delhi


def best_window(aqi: int, dominant_pollutant=None, forecast=None, lang: str = "en") -> dict:
    """Return ``{window, rationale}`` — a Delhi diurnal heuristic.

    The window now varies by three things, so it is not constant within a
    season: the **dominant pollutant**, the **current AQI severity**, and the
    **season**. It stays an honest rule of thumb, never claiming to be an
    hourly station forecast:

      * Ozone (o3): builds up under afternoon sun, so mornings are cleaner.
      * Traffic gases (no2/so2/co): peak at morning and evening rush, so the
        midday lull is calmer.
      * Particulates (pm2.5/pm10): in winter, overnight inversions trap smog so
        ~6-10 AM is worst and early afternoon is better; other seasons, late
        morning is the calm window before the afternoon photochemical peak.

    When AQI > 300 there is no safe outdoor window regardless of time.
    ``forecast`` is accepted for future refinement; the window works without it.

    ``lang`` translates both returned strings. The rationale is assembled from
    two or three separately translated sentences rather than one, because the
    severity tail is chosen independently of the pollutant clause; each piece
    is a whole sentence, so no clause has to be built word by word.
    """
    try:
        aqi_val = int(aqi)
    except (TypeError, ValueError):
        aqi_val = 0

    winter = _is_winter(datetime.date.today().month)
    pollutant = _pollutant_key(dominant_pollutant)

    if aqi_val > 300:
        return {
            "window": i18n.t(lang, "window", "none", "No safe outdoor window today"),
            "rationale": i18n.t(
                lang, "window", "none_rationale",
                "Current AQI is in the Very Poor/Severe range, so pollution "
                "stays hazardous across the whole day. It is best to stay "
                "indoors and keep windows shut. This is a rule of thumb, not "
                "an hourly station forecast."),
        }

    if pollutant == "o3":
        window = i18n.t(lang, "window", "o3", "Early morning (about 6-9 AM)")
        rationale = i18n.t(
            lang, "window", "o3_rationale",
            "Today's air is driven by ozone, which builds up under afternoon "
            "sunlight — so the early morning is the cleaner window and "
            "afternoons are worst.")
    elif pollutant == "no2":
        window = i18n.t(lang, "window", "no2", "Midday (about 11 AM-3 PM)")
        rationale = i18n.t(
            lang, "window", "no2_rationale",
            "Today's air is driven by traffic gases (like NO2), which spike "
            "during the morning and evening rush hours — so the midday lull "
            "between them is the calmer window.")
    elif winter:
        window = i18n.t(lang, "window", "winter", "Early afternoon (about 1-4 PM)")
        rationale = i18n.t(
            lang, "window", "winter_rationale",
            "Fine particles are the main driver. In Delhi winter, overnight "
            "temperature inversions trap smog near the ground, so ~6-10 AM is "
            "usually worst and the air eases by early afternoon once the "
            "mixing layer lifts.")
    else:
        window = i18n.t(lang, "window", "default", "Late morning (about 9 AM-12 PM)")
        rationale = i18n.t(
            lang, "window", "default_rationale",
            "Fine particles are the main driver. Outside winter, afternoon sun "
            "can lift ozone too, so late morning tends to be the calmer window "
            "before the afternoon peak.")

    parts = [rationale, i18n.t(
        lang, "window", "general_note",
        "This is a general pattern, not an hourly station forecast.")]
    if aqi_val > 200:
        parts.append(i18n.t(
            lang, "window", "note_poor",
            "Air is already Poor, so keep any outdoor activity short and wear an N95."))
    elif aqi_val > 100:
        parts.append(i18n.t(
            lang, "window", "note_moderate",
            "Air is Moderate, so ease off intense exertion."))

    return {"window": window, "rationale": " ".join(parts)}
