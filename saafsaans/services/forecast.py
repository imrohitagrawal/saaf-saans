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

from . import aqi_scale, clock, i18n

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


# The diurnal shape, as an hourly tier per driver.
#
# One rule decides every hour of the table, and it is the whole reason the
# table can be trusted: tier 1 where a rationale sentence below names those
# hours calm, tier 3 where one names them bad, tier 2 everywhere else. Tier 2
# is not a claim that an hour is average, it is the ABSENCE of a claim -- which
# is why no hour inside it outranks another, and why the ranking still prefers
# it to tier 3: avoiding an hour a sentence calls bad is the only preference
# those sentences license.
#
# The tiers are not written out; they are built from the citations below, and
# every row carries the clause it rests on. What that does and does not buy is
# worth being exact about, because the honesty of the feature rests on it.
#
# Only one clause names clock hours: winter's "~6-10 AM". The other seven name
# a DAYPART -- "early morning", "late morning", "the midday lull", "the
# afternoon peak", "the morning and evening rush hours" -- and turning a
# daypart into hour boundaries is a reading, not a derivation. Those boundaries
# are the author's, and a reviewer who disagrees with one should move it. What
# the citations do buy is that no hour is ranked without a sentence to point
# at, and that the sentence still contains the clause quoted beside it.
#
# Two spans were argued over. Delhi winter evenings are tier 2, not tier 3: the
# winter sentence names a mechanism ("overnight temperature inversions trap
# smog near the ground") but never says when overnight begins, and an earlier
# draft scored 7 PM to midnight as bad on it. The no2 lull runs to 17 rather
# than 14 because its clause defines it as the lull BETWEEN the rushes, and
# this table puts those at 8-10 and 18-21; stopping it at 14 made the table
# disagree with itself, and cost the traffic-gas reader the three hours it
# disagreed about.
#
# Applied this way, with no hour of the day gone, the four drivers return the
# same four windows this function returned when it did not read the clock at
# all: 6-9 AM, 9 AM-12 PM, 11 AM-3 PM, 1-4 PM.
_TIER_CALM, _TIER_UNSAID, _TIER_BAD = 1, 2, 3

# (driver, hours, tier, the clause in that driver's rationale that grounds it)
_TIER_CITATIONS = (
    ("pm-winter", (6, 7, 8, 9, 10), _TIER_BAD, "~6-10 AM is "),
    ("pm-winter", (13, 14, 15), _TIER_CALM, "eases by early afternoon"),
    ("pm-other", (12, 13, 14, 15, 16, 17), _TIER_BAD, "before the afternoon peak"),
    ("pm-other", (9, 10, 11), _TIER_CALM, "late morning tends to be the calmer window"),
    ("o3", (12, 13, 14, 15, 16, 17), _TIER_BAD, "afternoons are worst"),
    ("o3", (6, 7, 8), _TIER_CALM, "the early morning is the cleaner window"),
    ("no2", (8, 9, 10, 18, 19, 20, 21), _TIER_BAD, "morning and evening rush hours"),
    ("no2", (11, 12, 13, 14, 15, 16, 17), _TIER_CALM,
     "the midday lull between them"),
)

# The heuristic never sends anybody outside at 3 AM, so the ranking starts at
# 6 and the last hour it can offer is the one the day ends in.
_DAY_FIRST_HOUR = 6
_DAY_LAST_HOUR = 23
# The four windows this function shipped spanned three and four hours. Longer
# than four reads as a claim about a whole evening that no sentence supports.
_MAX_RUN_HOURS = 4


def _driver_key(pollutant: str, winter: bool) -> str:
    if pollutant == "pm":
        return "pm-winter" if winter else "pm-other"
    return pollutant


def _hour_tiers(pollutant: str, winter: bool) -> tuple:
    """The 24 hourly tiers for one driver, built from the citations."""
    tiers = [_TIER_UNSAID] * 24
    key = _driver_key(pollutant, winter)
    for driver, hours, tier, _clause in _TIER_CITATIONS:
        if driver == key:
            for hour in hours:
                tiers[hour] = tier
    return tuple(tiers)


def _first_useful_hour(now) -> int:
    """The earliest hour still worth offering: the one the reader is in.

    An earlier draft rounded up once half the hour had gone, so that 17:52 was
    not offered a window with eight minutes of life in it. It was removed: at
    11:30 it denied that any calmer hour was left while thirty minutes of a
    cited-calm hour were still ahead, which is the same untrue statement this
    function exists to stop. The run it names ends at the end of the calm
    stretch rather than the end of the hour, so those eight minutes were never
    the whole offer anyway.
    """
    return min(max(now.hour, _DAY_FIRST_HOUR), _DAY_LAST_HOUR)


def _best_run(tiers, first_hour: int):
    """``(start, end, tier)`` for the calmest run of hours still ahead.

    ``end`` is exclusive. Ties go to the soonest run: when two stretches are
    ranked the same, the sooner one is the more useful answer and the less
    speculative one. Capped at ``_MAX_RUN_HOURS``.
    """
    first = min(max(first_hour, _DAY_FIRST_HOUR), _DAY_LAST_HOUR)
    remaining = range(first, _DAY_LAST_HOUR + 1)
    best = min(tiers[h] for h in remaining)
    start = next(h for h in remaining if tiers[h] == best)
    end = start
    while end + 1 <= _DAY_LAST_HOUR and tiers[end + 1] == best:
        end += 1
    return start, min(end + 1, start + _MAX_RUN_HOURS), best


def _edge_sentence(pollutant: str, winter: bool, shape: str, lang: str) -> str:
    """The fact a shipped sentence licenses about the stretch beside this span.

    A tier-2 hour is one nothing describes, so nothing can be said about the
    hour itself -- "the calmest left" would rank hours the sentences do not
    rank. What the sentences DO license is a statement about the tier-3 stretch
    next to it: that it is over, or that it starts. That is a cited exclusion,
    not a recommendation, and it is the only claim made here.

    Empty when the driver has no sentence for that edge. The caller then says
    the remaining hours are alike rather than inventing a reason.
    """
    if pollutant == "o3" and shape == "before":
        return i18n.t(lang, "window", "o3_edge_before",
                      "The afternoon build-up starts after that.")
    if pollutant == "o3" and shape == "after":
        return i18n.t(lang, "window", "o3_edge_after",
                      "The afternoon build-up is past by then.")
    if pollutant == "no2" and shape == "after":
        return i18n.t(lang, "window", "no2_edge_after",
                      "The evening rush is past by then.")
    if pollutant == "pm" and not winter and shape == "after":
        return i18n.t(lang, "window", "pm_edge_after",
                      "The afternoon peak is past by then.")
    return ""


def best_window(aqi: int, dominant_pollutant=None, forecast=None, lang: str = "en") -> dict:
    """Return ``{window, rationale, note}`` for the hours a reader has left.

    The window is answered for TODAY, from the current hour to the end of the
    day: the diurnal shape per driver is intersected with the hours that remain
    and the calmest run of those is named, with the day it belongs to. It used
    to read ``clock.today_ist().month`` for the season and nothing else, so it
    returned one of four fixed labels all day. Measured on 2026-08-10 at 17:52
    IST, every driver named a window already in the past -- under "IF YOU MUST
    GO OUT", the one claim a reader can check against their own clock.

    ``window`` never names an hour that has gone, and never names one at all
    unless a shipped rationale sentence calls those hours calm: once the cited
    calm hours are behind us it says so instead of ranking the hours nothing
    describes. ``note`` carries the lever: what to do about the outing rather
    than when to take it. On the normal branch it opens with the cited edge
    sentence that earned the span its boundary, which IS about when -- that
    sentence is the window's own grounding and is placed here because no
    template renders ``rationale``. Everything after it is the lever proper.
    From AQI 101 up that names the mask; ``note`` is empty only on air the CPCB
    scale calls Good or Satisfactory, and only at the hours where no cited
    stretch gives the span an edge to state.

    The window on the two refusing branches is unchanged. When AQI > 300 there
    is no safe outdoor window regardless of time, and when the AQI is missing
    no window is named either: an unknown reading must never produce a
    friendlier answer than a known bad one, and it used to produce the
    friendliest available, because the unparseable value was read as 0.

    Their ``note`` did change, on 2026-08-31. Both returned "" until then, so
    the reader in the worst air on the page got the least help on it: the hero
    printed "IF YOU MUST GO OUT" over "No safe outdoor window today" and
    stopped, under a label that promises something to exactly the reader who
    must go out anyway. Both now carry a lever, and a lever is not a window --
    it names no hour, so the refusal above it survives intact. The two levers
    are separate strings because only one of them may name a band: 380 is in
    the Very Poor to Severe range and this module's own rationale has always
    said so, while a missing reading is a missing reading.

    ``forecast`` is still accepted and still unused. It was to have carried a
    "the calmer hours fall here tomorrow" line, which was cut: the daily
    outlook is absent on the retained, CPCB and fallback paths, so the line
    would have shipped from a static table alone on every one of them.

    ``lang`` translates every returned string. The rationale is assembled from
    separately translated whole sentences rather than built word by word.
    """
    try:
        aqi_val = int(aqi)
    except (TypeError, ValueError):
        # No reading. Not zero -- zero is the cleanest air there is, and it
        # took the branch with no severity caveat at all, so the hero rendered
        # "IF YOU MUST GO OUT: Late morning" underneath "AQI -- - UNKNOWN" and
        # "Do not go outdoors". The heuristic is also injected into the prompt
        # under a system instruction telling the model to trust it, so a
        # friendly window here becomes a friendly answer as well.
        #
        # Both strings are existing keys, reused rather than reworded: the
        # window is the same "no window" line severe air gets, because we
        # cannot name a safe hour without a reading either; the reason is the
        # answer card's own "reading is unavailable" sentence, which is true
        # here and does not assert a band, unlike window/none_rationale.
        return {
            "window": i18n.t(lang, "window", "none", "No safe outdoor window today"),
            "rationale": i18n.t(
                lang, "answer", "why_unknown",
                "AQI reading is unavailable; treat {activity} as unsafe until "
                "confirmed.").replace(
                    "{activity}",
                    i18n.t(lang, "answer", "activity_generic", "outdoor activity")),
            # A lever, not a window: it says what to do and never when, so the
            # refusal above survives it intact. It asserts no band either --
            # with no reading nobody knows the air, which is why this is its own
            # key and not the severe one reused.
            "note": i18n.t(
                lang, "window", "note_no_reading",
                "Keep any trip outside short and wear an N95 until there is a "
                "reading to go on."),
        }

    # The season is Delhi's, so the month must be Delhi's. date.today() is the
    # server's, and the container ships UTC: for the five and a half hours
    # after midnight UTC it still reports the previous month, so the winter
    # rationale arrived late at every month boundary -- including the one into
    # November, when Delhi's air turns and the advice matters most.
    today = clock.today_ist()
    winter = _is_winter(today.month)
    pollutant = _pollutant_key(dominant_pollutant)

    if aqi_val > 300:
        return {
            "window": i18n.t(lang, "window", "none", "No safe outdoor window today"),
            "rationale": i18n.t(
                lang, "window", "none_rationale",
                "Current AQI is in the Very Poor/Severe range, so pollution "
                "stays hazardous across the whole day. Keep windows shut, run "
                "a purifier if you have one, and keep any unavoidable trip "
                "short. This is a rule of thumb, not an hourly station "
                "forecast."),
            # The band phrase is the one this branch's own rationale has always
            # used, so the lever asserts nothing new: above 300 the reading
            # spans CPCB Very Poor and Severe, which is why it is not "Severe"
            # alone. Duration and pace, not an hour -- the refusal above stands.
            "note": i18n.t(
                lang, "window", "note_severe",
                "Air is in the Very Poor to Severe range, so keep any trip "
                "outside short and slow, and wear an N95."),
        }

    if pollutant == "o3":
        rationale = i18n.t(
            lang, "window", "o3_rationale",
            "Today's air is driven by ozone, which builds up under afternoon "
            "sunlight — so the early morning is the cleaner window and "
            "afternoons are worst.")
    elif pollutant == "no2":
        rationale = i18n.t(
            lang, "window", "no2_rationale",
            "Today's air is driven by traffic gases (like NO2), which spike "
            "during the morning and evening rush hours — so the midday lull "
            "between them is the calmer window.")
    elif winter:
        rationale = i18n.t(
            lang, "window", "winter_rationale",
            "Fine particles are the main driver. In Delhi winter, overnight "
            "temperature inversions trap smog near the ground, so ~6-10 AM is "
            "usually worst and the air eases by early afternoon once the "
            "mixing layer lifts.")
    else:
        rationale = i18n.t(
            lang, "window", "default_rationale",
            "Fine particles are the main driver. Outside winter, afternoon sun "
            "can lift ozone too, so late morning tends to be the calmer window "
            "before the afternoon peak.")

    tiers = _hour_tiers(pollutant, winter)
    first = _first_useful_hour(clock.now_ist())
    start, end, tier = _best_run(tiers, first)
    remaining = range(first, _DAY_LAST_HOUR + 1)
    edge = ""
    if tier == _TIER_CALM:
        window = i18n.t(
            lang, "window", "today_window", "Today, about {range}").replace(
                "{range}", i18n.clock_range(lang, start, end))
    else:
        # A tier-3 run still ahead gives this span a cited edge: the span sits
        # either before that stretch starts or after it has passed, and either
        # is a fact a shipped sentence states. Prefer the earlier edge, which
        # is the sooner answer. With no tier-3 left there is nothing to cite,
        # and the honest reply is that the hours are alike.
        bad_ahead = any(tiers[h] == _TIER_BAD for h in remaining if h >= end)
        bad_behind = any(tiers[h] == _TIER_BAD for h in remaining if h < start)
        shape = "before" if bad_ahead else ("after" if bad_behind else "")
        edge = _edge_sentence(pollutant, winter, shape, lang) if shape else ""
        if edge and shape == "before":
            window = i18n.t(
                lang, "window", "today_before", "Today, before about {time}").replace(
                    "{time}", i18n.clock_hour(lang, end))
        elif edge:
            window = i18n.t(
                lang, "window", "today_after", "Today, after about {time}").replace(
                    "{time}", i18n.clock_hour(lang, start))
        else:
            window = i18n.t(
                lang, "window", "hours_alike",
                "The hours left today look much alike — waiting will not buy "
                "cleaner air.")

    parts = [edge] if edge else []
    # The band is the one that was measured, stated in the present. A band for
    # the hour being suggested would be a modelled figure wearing a
    # measurement's clothes, which the evidence checklist forbids (D4). Both
    # sentences already existed and are moved, not written: they were assembled
    # into `rationale`, which no template renders, so the lever has been
    # reaching the model and never the reader.
    if aqi_val > 200:
        parts.append(i18n.t(
            lang, "window", "note_poor",
            "Air is already Poor, so keep any outdoor activity short and wear an N95."))
    elif aqi_val > 100:
        # The mask is named from 101, not from 201. This lever is the only
        # surface that speaks about the outing, and its threshold now matches
        # the app's own advisory corpus rather than sitting a band above it:
        # data/advisories.py carries "AQI 101-200 with COPD: ... Consider an N95
        # for essential trips" (GOLD-guidance), and an N95 row for pregnancy on
        # a commute in the same range. Until 2026-08-31 the hero delivered that
        # instruction off the persona band instead, which is how it also reached
        # a reader at AQI 0 -- and, at AQI 150 with a Very High persona, how it
        # went missing from the hero entirely once the band stopped carrying it.
        parts.append(i18n.t(
            lang, "window", "note_moderate",
            "Air is Moderate, so ease off intense exertion and consider an N95 "
            "for essential trips."))

    rationale = " ".join([rationale, i18n.t(
        lang, "window", "general_note",
        "This is a general pattern, not an hourly station forecast.")])
    return {"window": window, "rationale": rationale, "note": " ".join(parts)}
