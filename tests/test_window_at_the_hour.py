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


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("hour", HOURS)
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
