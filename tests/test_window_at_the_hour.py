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

from saafsaans.services import clock, forecast, i18n, normalize
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


# The frozen hours at which a normal reading still gets a clock time. This was
# HOURS itself when the test was written, before any ranking existed. It lost
# 12, 17 and 23 to the first draft of the floor, which named a time only inside
# a cited-calm run; 12 and 17 came back once a span could also be named by the
# stretch beside it. 23 does not: with no cited stretch anywhere in the hours
# that are left, there is nothing to point at, and the answer is that the hours
# are alike. `test_a_normal_reading_is_never_told_what_severe_air_is_told`
# below is the partner at that hour.
HOURS_WITH_SOMETHING_TO_NAME = (6, 12, 17)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS_WITH_SOMETHING_TO_NAME)
def test_the_same_hour_with_a_normal_reading_does_name_one(at_ist, hour, lang):
    """The partner the two tests above need. Both of them assert an ABSENCE, and
    an absence is satisfied by a function that returns nothing at all: delete
    the whole heuristic and they stay green. This proves that at the very same
    instant, air the app can be honest about DOES get a named hour -- so the
    absence above is a decision, not an empty implementation."""
    at_ist(hour)
    win = forecast.best_window(168, dominant_pollutant="pm25", lang=lang)
    assert CLOCK_TIME.search(win["window"]), (hour, lang, win["window"])


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
    # Each of the three gets its OWN lever, and no two of them share one. This
    # line read `severe["note"] == "" and missing["note"] == ""` until
    # 2026-08-31. The property it was protecting is that severe air and a
    # missing reading are never told there is a good hour -- and that property
    # is asserted by hour, not by emptiness, in the two tests at the top of
    # this file, which run CLOCK_TIME over `window + note` for exactly these
    # two branches. Emptiness protected it only by accident, at the cost of
    # handing the reader in the worst air the least help on the page.
    assert severe["note"] and missing["note"], (hour, lang)
    assert len({normal["note"], severe["note"], missing["note"]}) == 3, (hour, lang)


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
    # Not merely "no digits leaked": at 17:00 the ranking names no hour either,
    # so an hour-free string cannot tell the two apart. Severe air has to get
    # the severe line, not the one saying the pattern picks nothing out.
    assert slot.group(1).strip() == i18n.t(
        lang, "window", "none", "No safe outdoor window today"), (
            lang, slot.group(1))


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
    ("no2", 1, (11, 12, 13, 14, 15, 16, 17), "the midday lull between them"),
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
    shipped = {(d, t, frozenset(h), c) for d, h, t, c in forecast._TIER_CITATIONS}
    expected = {(d, t, frozenset(h), c) for d, t, h, c in EXPECTED_CITATIONS}
    assert shipped == expected, \
        "the shipped tier table no longer matches the one read off the sentences"

    for driver, dominant, winter in DRIVERS:
        rationale = _rationale_for(dominant, winter, at_ist)
        cited = {}
        # Read the clause off the SHIPPED table, not off the copy above. An
        # earlier version of this test took it from EXPECTED_CITATIONS, so
        # every shipped clause could be blanked with the suite green -- the
        # grounding claim was checked only against the test's own private copy.
        for row_driver, hours, tier, clause in forecast._TIER_CITATIONS:
            if row_driver != driver:
                continue
            assert clause and clause in rationale, (driver, clause, rationale)
            for hour in hours:
                cited[hour] = tier
        tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
        for hour in range(24):
            # 2, not forecast._TIER_UNSAID: an expectation imported from the
            # implementation follows it silently when it changes.
            assert tiers[hour] == cited.get(hour, 2), (driver, hour, tiers[hour])


def _shape_at(dominant, winter, hour):
    """What the ranking has to work with at this hour: a cited-calm run, a run
    with a cited bad stretch beside it, or neither."""
    tiers = forecast._hour_tiers(forecast._pollutant_key(dominant), winter)
    first = min(max(hour, 6), 23)
    rem = range(first, 24)
    start, end, tier = forecast._best_run(tiers, first)
    if tier == forecast._TIER_CALM:
        return "calm"
    if any(tiers[h] == forecast._TIER_BAD for h in rem if h >= end):
        return "before"
    if any(tiers[h] == forecast._TIER_BAD for h in rem if h < start):
        return "after"
    return "alike"


def test_a_time_is_named_only_when_a_sentence_puts_something_beside_it(at_ist):
    """The rule the whole feature rests on, in one assertion.

    A tier-1 run is named because a sentence calls those hours calm. A tier-2
    run may be named only when a tier-3 stretch is still in the remaining hours
    to give it an edge -- then the claim is about that stretch ("the afternoon
    peak is past by then"), which a sentence does state. With no tier-3 left
    there is nothing to cite, and no time may be named at all.

    Turns red when: a tier-2 span is named with no bad stretch beside it, which
    is ranking hours no sentence ranks; or a cited edge stops being named,
    which is the silence this replaced."""
    for _driver, dominant, winter in DRIVERS:
        for hour in range(24):
            at_ist(hour, month=12 if winter else 8)
            win = forecast.best_window(168, dominant_pollutant=dominant)
            shape = _shape_at(dominant, winter, hour)
            named = bool(CLOCK_TIME.search(win["window"]))
            assert named == (shape != "alike"), (dominant, hour, shape, win["window"])
            # And a named tier-2 span always states the fact that earns it.
            if shape in ("before", "after"):
                assert win["note"] and win["note"] != "", (dominant, hour)


def test_every_edge_the_table_can_reach_has_a_sentence_to_state(at_ist):
    """The partner for the rule above. `_edge_sentence` returns "" for a driver
    it has no clause for, and the caller then falls back to saying the hours
    are alike -- correct, but silent. If a change to the tier table makes a new
    (driver, edge) pair reachable, this fails rather than quietly losing the
    answer for those hours.

    Turns red when: a citation moves so a driver reaches an edge nobody wrote
    a sentence for."""
    missing = []
    for _driver, dominant, winter in DRIVERS:
        for hour in range(24):
            shape = _shape_at(dominant, winter, hour)
            if shape in ("before", "after") and not forecast._edge_sentence(
                    forecast._pollutant_key(dominant), winter, shape, "en"):
                missing.append((dominant, winter, hour, shape))
    assert not missing, f"reachable edges with no sentence: {sorted(set(missing))}"


# Superlatives rank hours against each other. The sentences this module ships
# rank one stretch as bad and say nothing about the rest, so a superlative in
# the window or the note is a claim nothing backs -- and in Hindi "सबसे कम
# ख़राब" would reuse ख़राब, the reserved CPCB word for the Poor band, on hours
# no reading has banded.
SUPERLATIVES = ("calmest", "cleanest", "best time", "least bad", "safest",
                "सबसे शांत", "सबसे साफ़", "सबसे कम ख़राब", "सबसे अच्छा", "सबसे बेहतर")


# 380 and None joined this list on 2026-08-31, when those two branches stopped
# returning an empty note. A guard over `window + note` reads nothing from a
# note that is "", so until they carried copy they were being swept vacuously.
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("aqi", (45, 168, 250, 380, None))
def test_no_window_ranks_the_hours_it_cannot_rank(at_ist, lang, aqi):
    """Turns red when: any window or note string starts calling a named span
    the calmest, cleanest or least bad of what is left, in either language."""
    for _driver, dominant, winter in DRIVERS:
        for hour in range(24):
            at_ist(hour, month=12 if winter else 8)
            win = forecast.best_window(aqi, dominant_pollutant=dominant, lang=lang)
            whole = f"{win['window']} {win['note']}".lower()
            for word in SUPERLATIVES:
                assert word.lower() not in whole, (dominant, hour, lang, word, whole)


def test_the_superlative_guard_would_notice_one(at_ist):
    """The partner. A guard that only ever asserts an absence passes against a
    function that returns nothing, and this one runs over strings that are
    mostly short -- so prove it fires on the phrasing it exists to stop, and
    that it permits the cited-fact phrasing that ships."""
    at_ist(12)
    shipped = forecast.best_window(250, dominant_pollutant="pm25")
    whole = f"{shipped['window']} {shipped['note']}".lower()
    assert not any(w.lower() in whole for w in SUPERLATIVES), whole
    assert "past by then" in whole, "the cited-fact phrasing must be permitted"
    for banned in ("Today, the calmest hours left", "आज सबसे कम ख़राब समय"):
        assert any(w.lower() in banned.lower() for w in SUPERLATIVES), banned


def test_no_hour_is_ever_named_before_the_hour_it_is_read(at_ist):
    """The defect itself, measured at 17:52 IST on 2026-08-10, when every
    driver named a window already gone.

    Goes through best_window rather than _best_run, and at :52 as well as :00,
    because the property belongs to what a reader is handed. An earlier version
    asserted _best_run's own clamp line back to it, which stayed green under an
    implementation that ignored the minutes entirely.

    Turns red when: _first_useful_hour stops clamping up to the current hour."""
    for driver, dominant, winter in DRIVERS:
        for hour in range(24):
            for minute in (0, 29, 30, 52):
                at_ist(hour, minute, month=12 if winter else 8)
                win = forecast.best_window(168, dominant_pollutant=dominant)
                for start, meridiem in re.findall(r"(\d+)(?:-\d+)? ?(AM|PM)",
                                                  win["window"]):
                    named = int(start) % 12 + (12 if meridiem == "PM" else 0)
                    assert named >= hour or hour < 6, (
                        driver, hour, minute, win["window"])


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
## columns: pm-winter  pm-other  o3  no2
00 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
01 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
02 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
03 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
04 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
05 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
06 1-4 PM 9 AM-12 PM 6-9 AM 11 AM-3 PM
07 1-4 PM 9 AM-12 PM 7-9 AM 11 AM-3 PM
08 1-4 PM 9 AM-12 PM 8-9 AM 11 AM-3 PM
09 1-4 PM 9 AM-12 PM before 12 PM 11 AM-3 PM
10 1-4 PM 10 AM-12 PM before 12 PM 11 AM-3 PM
11 1-4 PM 11 AM-12 PM before 12 PM 11 AM-3 PM
12 1-4 PM after 6 PM after 6 PM 12-4 PM
13 1-4 PM after 6 PM after 6 PM 1-5 PM
14 2-4 PM after 6 PM after 6 PM 2-6 PM
15 3-4 PM after 6 PM after 6 PM 3-6 PM
16 alike after 6 PM after 6 PM 4-6 PM
17 alike after 6 PM after 6 PM 5-6 PM
18 alike alike alike after 10 PM
19 alike alike alike after 10 PM
20 alike alike alike after 10 PM
21 alike alike alike after 10 PM
22 alike alike alike alike
23 alike alike alike alike
"""


def test_the_shipped_window_table_is_what_a_reader_gets(at_ist):
    """A REGRESSION GUARD over the shipped answer, hour by hour and driver by
    driver. It pins the output of the rule, not the rule, so it cannot see an
    uncited tier -- that is the citation test's job. It is here so any change
    to what a reader is told shows up as a diff a person can read.

    It calls best_window, not the helpers: an earlier version reimplemented the
    naming rule in the test body and so stayed green when the floor was removed
    and when the day word was dropped."""
    rows = []
    for hour in range(24):
        cells = []
        for _driver, dominant, winter in DRIVERS:
            at_ist(hour, month=12 if winter else 8)
            window = forecast.best_window(168, dominant_pollutant=dominant)["window"]
            for prefix, short in (("Today, about ", ""),
                                  ("Today, after about ", "after "),
                                  ("Today, before about ", "before ")):
                if window.startswith(prefix):
                    cells.append(short + window[len(prefix):])
                    break
            else:
                cells.append("alike")
        rows.append(f"{hour:02d} " + " ".join(cells))
    wanted = "\n".join(l for l in GOLDEN_WINDOWS.strip().splitlines()
                        if not l.startswith("##"))
    assert "\n".join(rows) == wanted, (
        "the shipped window changed; columns are "
        + ", ".join(d for d, _dom, _w in DRIVERS))

# Every range the ranking can put in front of a reader, in both languages, plus
# the midnight form clock_range supports but no driver currently reaches.
# GOLDEN_WINDOWS' sibling: without it, "always repeat the daypart" passes, and
# so does labelling 8 PM as सुबह -- the exact ambiguity the Hindi clock exists
# to avoid.
GOLDEN_CLOCK = """
06 09 | 6-9 AM | सुबह 6 से 9 बजे
07 09 | 7-9 AM | सुबह 7 से 9 बजे
08 09 | 8-9 AM | सुबह 8 से 9 बजे
09 12 | 9 AM-12 PM | सुबह 9 से दोपहर 12 बजे
10 12 | 10 AM-12 PM | सुबह 10 से दोपहर 12 बजे
11 12 | 11 AM-12 PM | सुबह 11 से दोपहर 12 बजे
11 15 | 11 AM-3 PM | सुबह 11 से दोपहर 3 बजे
12 16 | 12-4 PM | दोपहर 12 से शाम 4 बजे
13 16 | 1-4 PM | दोपहर 1 से शाम 4 बजे
13 17 | 1-5 PM | दोपहर 1 से शाम 5 बजे
14 16 | 2-4 PM | दोपहर 2 से शाम 4 बजे
14 18 | 2-6 PM | दोपहर 2 से शाम 6 बजे
15 16 | 3-4 PM | दोपहर 3 से शाम 4 बजे
15 18 | 3-6 PM | दोपहर 3 से शाम 6 बजे
16 18 | 4-6 PM | शाम 4 से 6 बजे
17 18 | 5-6 PM | शाम 5 से 6 बजे
20 24 | 8 PM-midnight | रात 8 से 12 बजे
"""


def test_the_clock_reads_as_a_clock_in_both_languages():
    """Turns red when: the meridiem is printed on the wrong end, midnight stops
    being a word, a Devanagari daypart is dropped or mislabelled, or the second
    daypart stops appearing only when the range crosses one."""
    rows = []
    for line in GOLDEN_CLOCK.strip().splitlines():
        start, end = (int(x) for x in line.split("|")[0].split())
        rows.append(f"{start:02d} {end:02d} | {i18n.clock_range('en', start, end)}"
                    f" | {i18n.clock_range('hi', start, end)}")
    assert "\n".join(rows) == GOLDEN_CLOCK.strip()


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
    (12, "en"): ("Today, after about 6 PM",
                 "The afternoon peak is past by then. Air is already Poor, so keep "
                 "any outdoor activity short and wear an N95."),
    (12, "hi"): ("आज, क़रीब शाम 6 बजे के बाद",
                 "दोपहर का चढ़ाव तब तक बीत चुका होता है। हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
    (17, "en"): ("Today, after about 6 PM",
                 "The afternoon peak is past by then. Air is already Poor, so keep "
                 "any outdoor activity short and wear an N95."),
    (17, "hi"): ("आज, क़रीब शाम 6 बजे के बाद",
                 "दोपहर का चढ़ाव तब तक बीत चुका होता है। हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।"),
    (23, "en"): ("The hours left today look much alike — waiting will not buy "
                 "cleaner air.",
                 "Air is already Poor, so keep any outdoor activity short and wear an N95."),
    (23, "hi"): ("आज बचे घंटे लगभग एक जैसे हैं — इंतज़ार करने से हवा साफ़ नहीं होगी।",
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
def test_a_named_hour_always_says_which_day_it_belongs_to(at_ist, lang):
    """Owner's rule 4. A bare clock time is ambiguous the moment today's window
    has passed, and "9 AM-12 PM" read at 5pm is the defect this package exists
    to fix wearing a different hat. Every hour and every driver, so the two
    span shapes that name a boundary rather than a range are covered too.

    Turns red when: the day word is dropped from any of the three window
    templates, at any hour, in either language."""
    today = "आज" if lang == "hi" else "Today"
    seen = 0
    for _driver, dominant, winter in DRIVERS:
        for hour in range(24):
            at_ist(hour, month=12 if winter else 8)
            win = forecast.best_window(168, dominant_pollutant=dominant, lang=lang)
            if CLOCK_TIME.search(win["window"]):
                seen += 1
                assert today in win["window"], (hour, lang, dominant, win["window"])
    # The partner for a loop whose body is conditional: an implementation that
    # never names an hour would satisfy every assertion above by running none.
    assert seen >= 60, f"only {seen} of 96 driver-hours named a time"


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


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
def test_the_two_branches_that_name_no_hour_still_hand_over_a_lever(
        at_ist, hour, lang):
    """Severe air and a missing reading refuse to name an hour, and still say
    something a reader can act on.

    Both branches returned `note: ""` until 2026-08-31, so `.hero-window`
    rendered "IF YOU MUST GO OUT" over "No safe outdoor window today" and
    stopped -- a label promising help to the reader who must go out anyway,
    above nothing at all. The reader in the worst air on the page was getting
    the least help on the page.

    A lever is not a window: it says what to do, never when. So both halves are
    asserted together here -- the lever exists, and it still names no hour and
    ranks no hours.

    Turns red when: either branch stops carrying a lever, or a lever starts
    naming a time or ranking the hours."""
    at_ist(hour)
    for aqi in (380, None):
        note = forecast.best_window(aqi, dominant_pollutant="pm25",
                                    lang=lang)["note"]
        assert note.strip(), (hour, lang, aqi)
        assert not CLOCK_TIME.search(note), (hour, lang, aqi, note)
        for word in SUPERLATIVES:
            assert word.lower() not in note.lower(), (hour, lang, aqi, word)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_only_the_branch_with_a_reading_names_the_band_in_its_lever(at_ist, lang):
    """The two levers above are not interchangeable, and the difference is the
    whole reason the missing-reading branch needs its own string.

    Severe air may name the band it measured: 380 IS in the Very Poor to Severe
    range, and this branch's own rationale has said so since before the lever
    existed. A missing reading may not, because nobody knows the air -- that is
    the same rule `answer/why_unknown` follows one panel down, and the whole-
    page sweep in test_severity_needs_a_measurement enforces it on the rendered
    output.

    The two assertions are partners: the absence below would be satisfied by a
    lever that said nothing at all, so the presence above proves a band word in
    a lever is reachable and is being looked for in the right place.

    Turns red when: the missing-reading lever starts asserting a band, or the
    severe lever stops naming the one it measured."""
    at_ist(12)
    bands = ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe")
    labels = [i18n.t(lang, "band_label", b, b) for b in bands]

    # The two the branch is entitled to, not any of the six. "Air is already
    # Poor" satisfies "some band label is present" at AQI 380 and names the
    # wrong band; above 300 the reading is in Very Poor or Severe and the
    # rationale has always said so.
    licensed = [i18n.t(lang, "band_label", b, b) for b in ("Very Poor", "Severe")]
    severe = forecast.best_window(380, dominant_pollutant="pm25", lang=lang)["note"]
    for label in licensed:
        assert label in severe, (lang, label, severe)

    missing = forecast.best_window(None, dominant_pollutant="pm25", lang=lang)["note"]
    named = [label for label in labels if label in missing]
    assert not named, (lang, named, missing)
    # A band label is a word list, and a word list is not a semantic check: it
    # does not stop "The air is probably hazardous" / "हवा शायद जानलेवा है",
    # which asserts a severity in prose with no label in it. So the severity
    # adjectives this app actually uses are refused here too. What this still
    # cannot catch is a sentence that invents a new way to say it -- stated
    # rather than papered over, and the reason the no-reading branch keeps its
    # own key instead of reusing the severe one.
    for word in SEVERITY_WORDS[lang]:
        assert word not in missing.lower(), (lang, word, missing)


# Severity asserted without a band label. Read off the strings the app already
# ships: aqi_meaning, the answer card's precautions, and the verdicts.
SEVERITY_WORDS = {
    "en": ("hazardous", "unhealthy", "dangerous", "harmful", "toxic", "emergency"),
    "hi": ("ख़तरनाक", "जानलेवा", "हानिकारक", "ज़हरीली", "आपातकाल"),
}


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_severity_word_list_would_notice_one(lang):
    """The partner for the loop above. A word list that matches nothing passes
    against every sentence there is.

    The words are checked against copy this app already ships, so the list is
    grounded in the vocabulary the app actually uses rather than invented for
    the test."""
    shipped = " ".join([
        i18n.t(lang, "aqi_meaning", "Severe", normalize.AQI_MEANING["Severe"]),
        i18n.t(lang, "verdict", "Extreme", presenters.verdict_for("Extreme")),
    ]).lower()
    assert any(w in shipped for w in SEVERITY_WORDS[lang]), (lang, shipped)


# --- The presence -----------------------------------------------------------
# Everything above asserts an absence -- no hour, no superlative, no repeated
# instruction. A page that said nothing at all to anybody would satisfy every
# one of them. This is the other side.

@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("aqi", (101, 150, 200, 250, 380, None))
def test_a_reader_who_must_go_out_is_told_what_to_wear(at_ist, lang, aqi):
    """From CPCB Moderate upwards the lever names the mask, and it is the only
    surface that does.

    The threshold is the advisory corpus's own: data/advisories.py carries
    "AQI 101-200 with COPD: ... Consider an N95 for essential trips"
    (GOLD-guidance) and an N95 row for a pregnancy commute in the same range.
    Until 2026-08-31 the hero delivered that instruction from `BAND_ADVICE`,
    keyed on the persona-adjusted band, which put it in front of a reader at
    AQI 0 and -- once the band stopped carrying it -- took it away from a COPD
    senior at AQI 150 whose own risk chip read 64/100, Very High.

    Turns red when: any lever from 101 up, or the missing-reading lever, stops
    naming the mask."""
    at_ist(12)
    note = forecast.best_window(aqi, dominant_pollutant="pm25", lang=lang)["note"]
    assert "N95" in note, (aqi, lang, note)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", (6, 12))
def test_air_the_scale_calls_clean_is_told_no_such_thing(at_ist, hour, lang):
    """The partner. An implementation that appends the mask to every lever
    passes the test above and is wrong here, on air the CPCB scale calls Good
    or Satisfactory -- which is the defect being repaired, in the other
    direction: `BAND_ADVICE["High"]` said "wear an N95 outside" at AQI 0, over
    a band meaning reading "Air is clean. Outdoor activity is fine for
    everyone."

    Both hours matter. At 6 the lever is empty; at 12 it carries the edge
    sentence, so this also proves the check is reading a lever that exists
    rather than passing on an empty string.

    Turns red when: the mask stops being conditional on the reading."""
    at_ist(hour)
    for aqi in (0, 60, 100):
        note = forecast.best_window(aqi, dominant_pollutant="pm25",
                                    lang=lang)["note"]
        assert "N95" not in note, (aqi, hour, lang, note)
    at_ist(12)
    assert forecast.best_window(60, dominant_pollutant="pm25",
                                lang=lang)["note"].strip(), (
        lang, "the empty-string case would satisfy the loop above by itself")
