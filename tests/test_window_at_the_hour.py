"""The go-out window has to be true at the hour it is read.

Measured on 2026-08-10 at 17:52 IST, every driver returned a window already in
the past: PM2.5 "Late morning (about 9 AM-12 PM)" six hours gone, ozone "Early
morning (about 6-9 AM)" nine hours gone, traffic gases "Midday (about 11 AM-3
PM)" three hours gone. `best_window` read `clock.today_ist().month` for the
season and never read the hour at all. It renders under "IF YOU MUST GO OUT",
so at five in the afternoon the most actionable line on the page was guaranteed
wrong -- and it is the one claim a reader can check against their own clock.

Sixteen tests already covered this module and none of them caught it, because
they were written from the implementation and inherited its assumption that the
answer does not depend on the time. So every test here freezes the clock: time
is an input dimension, like language and viewport.

The first two blocks pin the branches that were already CORRECT before this
change -- severe air and no reading -- because a refactor that ranks "the hours
left today" is exactly the kind that hands them a cheerful hour.
"""
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import forecast, i18n
from saafsaans.web import presenters
from saafsaans.web.main import app

# The four the plan names, plus the two that bracket the last block of the day.
HOURS = (6, 12, 17, 23)

PERSONA = {"age": "adult", "condition": "asthma", "activity": "commute",
           "locality": "Rohini"}

# A clock time written for a reader, in either language: "9 AM", "12 PM", or
# Devanagari's "9 बजे". If one of these reaches the window slot, the window is
# naming an hour.
CLOCK_TIME = re.compile(r"\d\s*(?:AM|PM|बजे)")


# --- The honest branches, pinned before the ranking logic is touched --------
# R3 in the risk register: severe air and a missing reading are the only two
# branches that were already right. Both must keep refusing to name an hour, at
# every hour, in both languages.

@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
@pytest.mark.parametrize("dominant", ("pm25", "o3", "no2"))
def test_severe_air_names_no_hour_whatever_the_time(at_ist, hour, lang, dominant):
    at_ist(hour)
    win = forecast.best_window(380, dominant_pollutant=dominant, lang=lang)
    whole = f"{win['window']} {win.get('note', '')}"
    assert not CLOCK_TIME.search(whole), (hour, lang, dominant, whole)
    assert win["window"] == i18n.t(lang, "window", "none",
                                   "No safe outdoor window today")


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_a_missing_reading_names_no_hour_whatever_the_time(at_ist, hour, lang):
    at_ist(hour)
    win = forecast.best_window(None, dominant_pollutant="pm25", lang=lang)
    whole = f"{win['window']} {win.get('note', '')}"
    assert not CLOCK_TIME.search(whole), (hour, lang, whole)
    assert win["window"] == i18n.t(lang, "window", "none",
                                   "No safe outdoor window today")


# (hour, driver) pairs where a stretch of hours a shipped sentence calls calm
# is still ahead: ozone's morning at 8, particulates' late morning at 6, the
# traffic-gas midday lull at 12. After about 3 PM no driver has one, which is
# the ranking's floor working rather than a gap in the table.
STILL_A_CALM_STRETCH_LEFT = ((6, "pm25"), (8, "o3"), (12, "no2"))


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour,dominant", STILL_A_CALM_STRETCH_LEFT)
def test_the_same_hour_with_a_normal_reading_does_name_one(
        at_ist, hour, dominant, lang):
    """The partner the two tests above need. Both of them assert an ABSENCE, and
    an absence is satisfied by a function that returns nothing at all: delete
    the whole heuristic and they stay green. This proves that at the very same
    instant, air the app can be honest about DOES get a named hour -- so the
    absence above is a decision, not an empty implementation."""
    at_ist(hour)
    win = forecast.best_window(168, dominant_pollutant=dominant, lang=lang)
    assert CLOCK_TIME.search(win["window"]), (hour, dominant, lang, win["window"])


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_a_normal_reading_is_never_told_what_severe_air_is_told(at_ist, hour, lang):
    """The partner for the hours where the answer is that no calm hour is left.

    This test replaces four parametrisations of the one above, and the reason
    is worth writing down. That test froze 06/12/17/23 before any ranking
    existed and asserted a normal reading always names a clock time. It cannot
    hold now, and it should not: after about 3 PM no shipped sentence describes
    any remaining hour as calm, so naming one would be the invention this
    package's whole floor exists to prevent.

    The partner's job survives intact -- prove the absence tests are not
    satisfied by an empty implementation. It just proves it the other way at
    those hours: air the app can be honest about gets its OWN answer, not the
    one severe air and a missing reading get, and it gets the lever with it."""
    at_ist(hour)
    normal = forecast.best_window(250, dominant_pollutant="pm25", lang=lang)
    severe = forecast.best_window(380, dominant_pollutant="pm25", lang=lang)
    missing = forecast.best_window(None, dominant_pollutant="pm25", lang=lang)
    assert normal["window"] != severe["window"], (hour, lang, normal["window"])
    assert normal["window"] != missing["window"], (hour, lang, normal["window"])
    assert "N95" in normal["note"], (hour, lang, normal["note"])
    assert severe["note"] == "" and missing["note"] == ""


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_page_keeps_the_honest_branch_at_five_in_the_afternoon(
        at_ist, monkeypatch, lang):
    """The branch, rendered. R4 says review the string in the page, not in the
    dictionary."""
    from saafsaans.services import waqi

    at_ist(17)
    monkeypatch.setattr(waqi, "get_aqi", lambda locality, es_client=None: (
        {"aqi": 380, "aqi_beyond_scale": False, "pm25": 380.0, "pm10": 420.0,
         "dominant_pollutant": "pm25", "feed_aqi": 380, "feed_dominant": "pm25",
         "city": "Delhi", "stale": False, "retained": False, "source": "waqi",
         "forecast": None, "obs_time": "2026-08-10T16:00:00+05:30",
         "station": locality}, "ok"))
    with TestClient(app) as c:
        body = c.get("/", params={**PERSONA, "lang": lang}).text
    slot = re.search(r'class="val">([^<]*)<', body)
    assert slot, "no window slot rendered at all"
    assert not CLOCK_TIME.search(slot.group(1)), (lang, slot.group(1))


# --- The ranking ------------------------------------------------------------
# Everything above pins branches that name no hour. An absence is satisfied by
# an implementation that does nothing, so the tests below have to prove the
# ranking exists and is grounded. The first one is the important one: it goes
# red on the defect class both drafts of this change actually had, which was an
# hour given a tier because it seemed right rather than because a sentence said
# so. A golden table cannot see that -- it would happily pin the invention.

DRIVERS = (("pm-winter", "pm25", True), ("pm-other", "pm25", False),
           ("o3", "o3", False), ("no2", "no2", False))


def _rationale_for(dominant, winter, at_ist):
    at_ist(6, month=12 if winter else 8)
    return forecast.best_window(168, dominant_pollutant=dominant)["rationale"]


# Read off the four rationale sentences by hand, and kept here rather than
# imported, on purpose: a test that builds its expectation from the same table
# the code builds its behaviour from cannot fail. This is the second,
# independent statement of the claim, so changing the curve means changing it
# here too, in front of whoever reviews the diff.
#   (driver, tier, hours, the words in that driver's rationale that say so)
EXPECTED_CITATIONS = (
    ("pm-winter", 3, (6, 7, 8, 9, 10), "~6-10 AM is "),
    ("pm-winter", 1, (13, 14, 15), "eases by early afternoon"),
    ("pm-other", 3, (12, 13, 14, 15, 16, 17), "before the afternoon peak"),
    ("pm-other", 1, (9, 10, 11), "late morning tends to be the calmer window"),
    ("o3", 3, (12, 13, 14, 15, 16, 17), "afternoons are worst"),
    ("o3", 1, (6, 7, 8), "the early morning is the cleaner window"),
    ("no2", 3, (8, 9, 10, 18, 19, 20, 21), "morning and evening rush hours"),
    ("no2", 1, (11, 12, 13, 14), "the midday lull between them"),
)


def test_the_tier_table_cites_a_sentence_for_every_claim(at_ist):
    """No hour may be called calm or bad unless a rationale sentence this
    module ships says so, in those words, and every hour nobody wrote about is
    tier 2.

    Turns red when: an hour is added to or removed from a cited span, a tier is
    assigned with no clause behind it, or a clause stops appearing in the
    sentence it quotes. That is the defect this package twice had in draft --
    ozone nights scored calm, then Delhi winter evenings scored bad, neither
    supported by any sentence in the file."""
    assert {(d, t, h) for d, h, t, _c in forecast._TIER_CITATIONS} == \
        {(d, t, h) for d, t, h, _c in EXPECTED_CITATIONS}, \
        "the shipped tier table no longer matches the one read off the sentences"

    for driver, dominant, winter in DRIVERS:
        rationale = _rationale_for(dominant, winter, at_ist)
        cited = {}
        for row_driver, tier, hours, clause in EXPECTED_CITATIONS:
            if row_driver != driver:
                continue
            assert clause in rationale, (driver, clause, rationale)
            for hour in hours:
                cited[hour] = tier
        tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
        for hour in range(24):
            expected = cited.get(hour, forecast._TIER_UNSAID)
            assert tiers[hour] == expected, (driver, hour, tiers[hour], expected)


def test_an_hour_is_named_only_when_a_sentence_calls_those_hours_calm(at_ist):
    """The floor. Ranking the hours nothing describes above the hours a
    sentence calls bad would turn an absence of evidence into a recommendation,
    which is worse than the bug this package was opened for: today's window is
    wrong, but it is at least a stated pattern.

    Turns red when: the tier check around the named window is removed, so a
    tier-2 or tier-3 run gets a clock time."""
    for driver, dominant, winter in DRIVERS:
        for hour in range(24):
            at_ist(hour, month=12 if winter else 8)
            win = forecast.best_window(168, dominant_pollutant=dominant)
            tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
            _s, _e, tier = forecast._best_run(tiers, forecast._first_useful_hour(
                __import__("datetime").datetime(2026, 1, 1, hour)))
            named = bool(CLOCK_TIME.search(win["window"]))
            assert named == (tier == forecast._TIER_CALM), (driver, hour, win["window"])


def test_no_hour_is_ever_named_before_the_hour_it_is_read(at_ist):
    """The defect itself, measured at 17:52 IST on 2026-08-10, when every
    driver named a window already gone.

    Turns red when: `_best_run` stops clamping its first hour up to now."""
    for driver, dominant, winter in DRIVERS:
        for hour in range(24):
            tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
            start, end, _tier = forecast._best_run(tiers, hour)
            assert start >= min(max(hour, 6), 23), (driver, hour, start)
            assert start < end <= 24, (driver, hour, start, end)


def test_the_four_windows_this_module_shipped_before_it_read_the_clock(at_ist):
    """The curve is a re-encoding of copy that already passed review, not a new
    claim: with no hour of the day gone, every driver still returns the window
    it returned when the answer did not depend on the time at all.

    Turns red when: a cited hour span moves, or the run cap changes."""
    expected = {"pm-winter": "1-4 PM", "pm-other": "9 AM-12 PM",
                "o3": "6-9 AM", "no2": "11 AM-3 PM"}
    for driver, dominant, winter in DRIVERS:
        tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
        start, end, tier = forecast._best_run(tiers, 0)
        assert i18n.clock_range("en", start, end) == expected[driver], driver
        assert tier == forecast._TIER_CALM, (driver, tier)


# A regression guard, not a bite-proof: it pins the output of the rule above
# rather than the rule, so it cannot see an uncited tier. It is here to make
# any change to the shipped answer visible in a diff a person can read.
GOLDEN_WINDOWS = """
00 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
01 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
02 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
03 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
04 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
05 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
06 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
07 1-4 PM 9 AM-12 PM 7-9 AM 11 AM-3 PM
08 1-4 PM 9 AM-12 PM 8-9 AM 11 AM-3 PM
09 1-4 PM 9 AM-12 PM none 11 AM-3 PM
10 1-4 PM 10 AM-12 PM none 11 AM-3 PM
11 1-4 PM 11 AM-12 PM none 11 AM-3 PM
12 1-4 PM none none 12-3 PM
13 1-4 PM none none 1-3 PM
14 2-4 PM none none 2-3 PM
15 3-4 PM none none none
16 none none none none
17 none none none none
18 none none none none
19 none none none none
20 none none none none
21 none none none none
22 none none none none
23 none none none none
"""


def test_the_shipped_window_table_is_what_a_reader_gets():
    rows = []
    for hour in range(24):
        cells = []
        for _driver, dominant, winter in DRIVERS:
            tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
            start, end, tier = forecast._best_run(tiers, hour)
            cells.append(i18n.clock_range("en", start, end)
                         if tier == forecast._TIER_CALM else "none")
        rows.append(f"{hour:02d} " + " ".join(cells))
    assert "\n".join(rows) == GOLDEN_WINDOWS.strip()


# --- What the change does to the answer (R2) --------------------------------
# The window is injected into the prompt under a system instruction telling the
# model to trust it ("only say no window applies if the heuristic itself says
# there is no safe window"), so moving the window moves the answer. Production
# runs with no model key by design, which makes the deterministic fallback the
# path live readers are actually on.

def _window_line(win, lang="en"):
    from saafsaans.services import llm
    reading = {"aqi": 250, "pm25": 150.0, "pm10": 260.0, "dominant_pollutant": "pm25",
               "city": "Delhi", "stale": False, "source": "waqi", "obs_time": "t"}
    return llm.build_user_message(
        reading, {"age_group": "adult", "condition": "asthma", "activity": "commute"},
        [], "Can I run?", "Rohini", "t", win, "High")


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_the_model_is_told_the_hour_and_the_lever_the_page_shows(at_ist, hour, lang):
    """Turns red when: `note` stops being appended to the prompt's heuristic
    line, so the model can answer with a friendlier window than the bar shows."""
    at_ist(hour)
    win = forecast.best_window(250, dominant_pollutant="pm25", lang=lang)
    prompt = _window_line(win, lang)
    assert win["window"] in prompt, (hour, lang)
    assert win["note"] and win["note"] in prompt, (hour, lang, win["note"])


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_the_deterministic_fallback_says_what_the_bar_says(at_ist, hour, lang):
    """The path live readers are on: the public instance ships no model key, so
    every answer comes from here.

    Turns red when: `_rule_based` stops carrying the note, so the answer and the
    hero bar disagree about the same reading."""
    from saafsaans.services import llm
    at_ist(hour)
    win = forecast.best_window(250, dominant_pollutant="pm25", lang=lang)
    reading = {"aqi": 250, "pm25": 150.0, "pm10": 260.0, "dominant_pollutant": "pm25",
               "city": "Delhi", "stale": False, "source": "waqi", "obs_time": "t"}
    body = llm._rule_based(reading, [], win, "Can I run?", lang, "High")
    assert win["window"] in body and win["note"] in body, (hour, lang)


# What the bar must say, spelled out rather than recomputed. The first draft of
# this test compared the rendered value against best_window() called from the
# test, so both sides moved together and it stayed green with the clock ignored
# entirely -- the very defect it was written for.
#   (hour, lang) -> the value in the bar, and the note beside it
BAR_AT_250 = {
    (6, "en"): ("Today, about 9 AM-12 PM",
                "Air is already Poor, so keep any outdoor activity short and wear an N95."),
    (6, "hi"): ("आज, क़रीब सुबह 9 से दोपहर 12 बजे तक",
                "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
    (12, "en"): ("No hour left today is a calmer one.",
                 "Air is already Poor, so keep any outdoor activity short and wear an N95."),
    (12, "hi"): ("आज बचे घंटों में कोई ज़्यादा शांत नहीं है।",
                 "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
    (17, "en"): ("No hour left today is a calmer one.",
                 "Air is already Poor, so keep any outdoor activity short and wear an N95."),
    (17, "hi"): ("आज बचे घंटों में कोई ज़्यादा शांत नहीं है।",
                 "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
    (23, "en"): ("No hour left today is a calmer one.",
                 "Air is already Poor, so keep any outdoor activity short and wear an N95."),
    (23, "hi"): ("आज बचे घंटों में कोई ज़्यादा शांत नहीं है।",
                 "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
}


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_the_hero_bar_says_what_it_should_at_each_hour(at_ist, monkeypatch, hour, lang):
    """End to end, in the rendered page, against a written-down expectation.

    Turns red when: the clock stops being read, the floor is removed, the note
    is not rendered, or the day word is dropped -- each of which changes one of
    these eight strings. The bar is where a reader checks the claim against
    their own clock, so it is the one place worth pinning literally."""
    from saafsaans.services import waqi

    at_ist(hour)
    monkeypatch.setattr(waqi, "get_aqi", lambda locality, es_client=None: (
        {"aqi": 250, "aqi_beyond_scale": False, "pm25": 150.0, "pm10": 260.0,
         "dominant_pollutant": "pm25", "feed_aqi": 250, "feed_dominant": "pm25",
         "city": "Delhi", "stale": False, "retained": False, "source": "waqi",
         "forecast": None, "obs_time": "2026-08-10T05:00:00+05:30",
         "station": locality}, "ok"))
    expected_value, expected_note = BAR_AT_250[(hour, lang)]
    with TestClient(app) as c:
        body = c.get("/", params={**PERSONA, "lang": lang}).text
    slot = re.search(r'class="val">([^<]*)<', body)
    assert slot and slot.group(1).strip() == expected_value, (
        hour, lang, slot.group(1) if slot else None)
    assert expected_note in body, (hour, lang)


def test_the_answer_card_has_never_carried_the_window():
    """A REGRESSION GUARD, not a bite-proof, and labelled so on purpose.

    presenters.answer_sections drops the window unconditionally and says why:
    the window has its own bar on the hero, so repeating it in every answer is
    noise. That means this assertion is true before this change, after it, and
    with the feature deleted -- it cannot go red for anything this package
    does. It is here to catch a future change that starts routing the window
    into the card, which would put an hour in front of a reader without the
    caveat the bar carries."""
    from saafsaans.services import llm
    sections = llm.parse_advice(
        "### Verdict\nv — d\n### Best time window\nTodayish, about 9 AM-12 PM\n"
        "### Warning symptoms\n- s\n### Disclaimer\nd\n")
    rendered = " ".join(
        f"{b.get('heading', '')} {b.get('text', '')} {b.get('items', '')}"
        for b in presenters.answer_sections(sections))
    assert "Todayish" not in rendered


# --- Owner's rule 4, and the partner for the lever --------------------------

@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", range(24))
@pytest.mark.parametrize("dominant", ("pm25", "o3", "no2"))
def test_a_named_hour_always_says_which_day_it_belongs_to(
        at_ist, hour, lang, dominant):
    """Owner's rule 4. A bare clock time is ambiguous the moment today's window
    has passed, and "9 AM-12 PM" read at 5pm is the defect this package exists
    to fix wearing a different hat.

    Turns red when: the day word is dropped from window/today_window, at any
    hour, in either language."""
    at_ist(hour)
    win = forecast.best_window(168, dominant_pollutant=dominant, lang=lang)
    if CLOCK_TIME.search(win["window"]):
        today = "आज" if lang == "hi" else "Today"
        assert today in win["window"], (hour, lang, dominant, win["window"])


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_clean_air_is_not_handed_a_lever_it_does_not_need(at_ist, lang):
    """The partner for the lever assertions: an implementation that appends the
    N95 sentence unconditionally passes those and is wrong here, on air the
    CPCB scale calls Satisfactory.

    Indexes `note` rather than `.get("note", "")` on purpose -- with `.get` a
    function that never sets the key at all would satisfy this.

    Turns red when: the severity sentence stops being conditional on the
    reading."""
    at_ist(6)
    win = forecast.best_window(60, dominant_pollutant="pm25", lang=lang)
    assert win["note"] == "", (lang, win["note"])
    poor = forecast.best_window(250, dominant_pollutant="pm25", lang=lang)
    assert poor["note"] != "", lang
