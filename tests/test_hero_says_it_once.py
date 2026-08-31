"""One instruction, one place on the hero.

The hero prints three sentences in a row and two of them were the same
instruction. `.hero-advice` is `risk.BAND_ADVICE`, keyed on the persona-adjusted
risk band; `.hero-window .lever` is `forecast.best_window()["note"]`, keyed on
the raw measured AQI. Measured on 2026-08-31 across AQI 0-500 x 60 personas:
11,400 of the 12,000 cells where both render gave the reader two different
instruction strengths, and the lever was never the stricter of the two -- always
equal or looser. The looser one is the one printed under "IF YOU MUST GO OUT",
which is the line a reader consults precisely when they have decided to go out.

Two examples, both rendered:

  AQI 250, senior + COPD + outdoor exercise:
    .hero-advice  Do not go outdoors. Seal windows, keep a purifier running...
    .lever        ...keep any outdoor activity short and wear an N95.

  AQI 0, child + COPD + school run  (CPCB band: Good):
    .meaning      Air is clean. Outdoor activity is fine for everyone.
    .hero-advice  Skip outdoor exercise. Keep trips short and wear an N95 outside.

The fix is not a reword. Each surface is given only the claim its own gating
variable knows: the advice speaks about the reader's day, because the band knows
the reader; the lever speaks about the outing, because the AQI knows the air.
So the mask, the trip length and the pace live in the lever and nowhere else,
and the placement of the day and the home's air live in the advice and nowhere
else.

This file checks that on the rendered page rather than in the dictionaries,
because the dictionaries are keyed on different things and only the page puts
the two strings next to each other.
"""
import html as htmllib
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, waqi
from saafsaans.web.main import app

# Two personas, because the advice slot is keyed on the risk band and the lever
# is keyed on the AQI, so one persona exercises only one diagonal of the grid.
# Between them these two reach Moderate, High, Very High and Extreme across the
# four readings below -- including the cell the defect actually lived in, a fit
# adult scoring band High at AQI 250 beside the Poor lever.
PERSONAS = {
    "asthma-commute": {"age": "Adult", "condition": "Asthma",
                       "activity": "Commute"},
    "fit-stay-home": {"age": "Adult", "condition": "Fit",
                      "activity": "Stay home"},
}
BASE = {"locality": "Rohini", "theme": "light"}

# The instruction tokens that must belong to exactly one of the two slots. Each
# is a whole instruction a reader can act on, not a stray word: the mask, the
# machine, the duration, the pace, and the two places. Written per language
# because "short" has no single Devanagari token -- the Hindi corpus says
# "कम समय का".
#
# Six, not the three this file shipped with. Three covered the duplication that
# existed, which is the weakest a marker list can be: it would have passed any
# reworded repeat. These six were swept over 17,760 (AQI x hour x persona x
# language) cells before being adopted, and no cell shares one.
#
# The bare "कम" is deliberately absent. It would catch more, and it would also
# catch "कमरे" -- the room the Very High advice names.
MARKERS = {
    "en": ("N95", "purifier", "short", "indoors", "windows", "slow"),
    "hi": ("N95", "प्यूरीफ़ायर", "कम समय", "अंदर", "खिड़कियाँ", "धीमा"),
}

# The band advice that shipped until 2026-08-31, quoted rather than imported:
# the strings are gone from the source, and reading the rule's own input off the
# shipped copy would make the partner test below circular.
_REPLACED_ADVICE = {
    "en": "Skip outdoor exercise. Keep trips short and wear an N95 outside.",
    "hi": "बाहर कसरत मत कीजिए। बाहर जाना कम रखिए और बाहर N95 मास्क पहनिए।",
}
_LEVER_AT_POOR = {
    "en": "Air is already Poor, so keep any outdoor activity short and wear an N95.",
    "hi": "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 पहनें।",
}

# A reading in each band the hero can be in, plus the state where there is none.
# 380 and the missing reading are here because they are the two that print a
# lever at all only since 2026-08-31.
READINGS = (("moderate", 120), ("poor", 250), ("severe", 380), ("none", None))


def _reading(aqi):
    return {"aqi": aqi, "aqi_beyond_scale": False, "pm25": aqi * 0.6,
            "pm10": aqi * 1.05, "dominant_pollutant": "pm25", "feed_aqi": aqi,
            "feed_dominant": "pm25", "city": "Delhi", "stale": False,
            "retained": False, "source": "waqi", "forecast": None,
            "obs_time": "2026-08-10T11:00:00+05:30", "station": "Rohini"}


def _slots(monkeypatch, aqi, lang, persona="asthma-commute"):
    """The two hero sentences as a reader sees them, unescaped."""
    if aqi is None:
        monkeypatch.setattr(waqi, "get_aqi",
                            lambda loc, es_client=None: (waqi._fallback(loc),
                                                         "fallback"))
    else:
        monkeypatch.setattr(waqi, "get_aqi",
                            lambda loc, es_client=None: (_reading(aqi), "ok"))
    with TestClient(app) as client:
        body = htmllib.unescape(
            client.get("/", params={**BASE, **PERSONAS[persona],
                                    "lang": lang}).text)
    advice = re.search(r'class="hero-advice">(.*?)</p>', body, re.S)
    lever = re.search(r'class="lever">(.*?)</span>', body, re.S)
    return (advice.group(1).strip() if advice else "",
            lever.group(1).strip() if lever else "")


def _shared(advice, lever, lang):
    return [m for m in MARKERS[lang] if m in advice and m in lever]


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("persona", sorted(PERSONAS))
@pytest.mark.parametrize("state,aqi", READINGS, ids=[s for s, _ in READINGS])
def test_the_hero_never_gives_the_same_instruction_twice(
        monkeypatch, at_ist, state, aqi, persona, lang):
    """Turns red when: the mask, the trip length, the pace, the purifier, the
    windows or the word indoors is printed in both `.hero-advice` and `.lever`
    on one page -- which is what shipped until 2026-08-31 at every reading
    above AQI 200."""
    at_ist(12)
    advice, lever = _slots(monkeypatch, aqi, lang, persona)
    assert advice, (state, persona, lang, "the hero printed no advice line")
    assert not _shared(advice, lever, lang), (
        state, persona, lang, _shared(advice, lever, lang), advice, lever)


def test_the_duplication_rule_would_have_caught_what_shipped():
    """The partner. The rule above asserts an ABSENCE, and an absence is
    satisfied by a marker list that matches nothing, by a regex that finds no
    slot, and by a page that renders neither sentence.

    So: the marker list is run against the pair that actually shipped -- the
    High band advice and the Poor lever, which a reader met together on every
    page between AQI 201 and 300 -- and must find the duplication in both
    languages.

    The mask was printed twice in both. English printed the trip length twice as
    well; the Hindi pair said it two different ways ("बाहर जाना कम रखिए" against
    "कम समय का"), which is why the Hindi expectation is the mask alone. The
    obvious fix -- adding the bare "कम" as a marker -- is wrong: "कमरे" (room)
    contains it, and the Very High advice names a room."""
    for lang in i18n.LANGUAGES:
        caught = _shared(_REPLACED_ADVICE[lang], _LEVER_AT_POOR[lang], lang)
        assert "N95" in caught, (lang, caught)
    en = _shared(_REPLACED_ADVICE["en"], _LEVER_AT_POOR["en"], "en")
    assert "short" in en, en


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_both_hero_slots_are_actually_being_read(monkeypatch, at_ist, lang):
    """The other partner. `_slots` returns "" for a slot it cannot find, and two
    empty strings share no marker, so a template rename would turn the rule
    above into a check on nothing.

    At AQI 250 both slots are present and both carry a marker, so the rule is
    reading two real sentences."""
    at_ist(12)
    advice, lever = _slots(monkeypatch, 250, lang)
    assert advice and lever, (lang, advice, lever)
    assert any(m in advice for m in MARKERS[lang]), (lang, advice)
    assert any(m in lever for m in MARKERS[lang]), (lang, lever)
