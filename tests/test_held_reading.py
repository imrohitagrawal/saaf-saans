"""A held reading earns a number and a time, and nothing else.

A HELD reading is real numbers we already fetched, re-served because the
upstream stopped answering (``cpcb`` retention). It is not the air now.

City Pulse has said so since the state was introduced -- ``main.city`` withholds
the band word and the severity slug unless the tile is live -- and the Guide
promises it in both languages. The Today page did not: it keyed every severity
claim off ``aqi is not None``, so the identical reading in the identical minute
rendered a full severity gradient, a band word, a 91/100 risk score and "Do not
go outdoors" beside a chip reading CACHED, while /city gave it a grey band-less
tile. Two pages of one app disagreeing about a measurement is the defect /city
was rewritten to remove.

Every test here has its MIRROR: the same reading unheld must keep everything a
live reading has earned, or "withhold the band" would be indistinguishable from
"the band is broken".
"""
import html
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import aqi_scale, i18n, normalize, waqi
from saafsaans.web import presenters as pr
from saafsaans.web.main import app

PERSONA = {"age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise", "theme": "light"}

# High enough to land in a severity band nobody could mistake for neutral: this
# is the reading that rendered band-g5 / VERY POOR / EXTREME on the shipped tip.
PM25, PM10 = 210.0, 300.0
AQI = aqi_scale.cpcb_aqi(PM25, PM10)[0]
OBS = "2026-07-21T10:00:00+05:30"


@pytest.fixture(autouse=True)
def _clean():
    waqi.cache_clear()
    yield
    waqi.cache_clear()


def _feed(monkeypatch, retained):
    """Serve one CPCB reading for every locality, held or not."""
    def get_aqi(locality, es_client=None):
        return waqi._reading(PM25, PM10, station=locality, city="Delhi",
                             stale=False, forecast=None, obs_time=OBS,
                             retained=retained, source="cpcb"), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)


def _today(lang):
    with TestClient(app) as client:
        return client.get("/", params={**PERSONA, "lang": lang}).text


def _hero(body):
    """The hero section only.

    Scoped deliberately. The severity slug also appears on the reading card and
    the band word appears in the glossary, so an assertion over the whole page
    would be answering about a different element than the one it names.
    """
    start = body.find('<section class="hero')
    assert start > 0, "the hero did not render"
    return body[start:body.find("</section>", start)]


def _band_words(lang):
    """Every band label in this language, as the page would print them."""
    return {i18n.t(lang, "band_label", label, label).upper()
            for _u, label, _c, _h, _s in normalize.AQI_BANDS} | {
        i18n.t(lang, "band_label", "Severe", "Severe").upper()}


def _named_bands(markup, lang, css_class):
    """The band words actually printed inside <span class="{css_class}"> tags.

    Scoped to the element rather than searched for across the page, and by
    exact tag content rather than a fixed-width slice. Hindi forces this: the
    band label for Poor is ख़राब, which is also the ordinary word for "bad"
    and occurs inside the held advice sentence ("the precautions you would
    take on a bad day"). A substring search over the whole hero could never
    pass in Hindi however correct the page was, and a test that cannot pass is
    as useless as one that cannot fail.
    """
    spans = re.findall(rf'<span class="{css_class}">(.*?)</span>', markup, re.S)
    words = _band_words(lang)
    found = set()
    for span in spans:
        matched = {word for word in words if word in span.upper()}
        # The band labels overlap each other: "POOR" is inside "VERY POOR",
        # and बहुत ख़राब contains ख़राब. Only the longest match in a span is
        # the word that span actually printed -- counting both would report a
        # band the page never named.
        found |= {word for word in matched
                  if not any(word != other and word in other
                             for other in matched)}
    return found


# --------------------------------------------------------------- the hero
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_gets_no_severity_colour(monkeypatch, lang):
    _feed(monkeypatch, retained=True)
    hero = _hero(_today(lang))
    neutral = normalize.band_slug(None)
    assert f"band-{neutral}" in hero, hero[:200]
    assert f'data-band="{neutral}"' in hero


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_gets_its_severity_colour(monkeypatch, lang):
    """The mirror. Without it, a template that lost `band` entirely would pass
    the test above."""
    _feed(monkeypatch, retained=False)
    hero = _hero(_today(lang))
    expected = normalize.band_slug(AQI)
    assert expected != normalize.band_slug(None)
    assert f"band-{expected}" in hero
    assert f'data-band="{expected}"' in hero


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_earns_no_band_word_but_keeps_its_number(monkeypatch, lang):
    """Both halves matter. Dropping the number too would be the blank city that
    retention exists to remove; keeping the band word is the claim it must not
    make."""
    _feed(monkeypatch, retained=True)
    body = _today(lang)
    hero = _hero(body)
    assert f"AQI {AQI}" in hero, "the held number was suppressed as well"
    assert _named_bands(hero, lang, "hero-pill") == set()
    # The reading card carries the second one, and it is a separate element
    # with its own branch, so a fix applied to the hero alone would leave it.
    # Asserted as the ABSENCE OF THE ELEMENT, not the absence of band words in
    # it: the neutralised category renders the chip as "Unknown", which is not
    # a band word, so a chip that always rendered passed the word check while
    # printing a band claim ("Unknown") the reading had not earned either.
    assert 'class="band-chip"' not in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_earns_its_band_word(monkeypatch, lang):
    _feed(monkeypatch, retained=False)
    body = _today(lang)
    label = normalize.aqi_category(AQI)[0]
    earned = {i18n.t(lang, "band_label", label, label).upper()}
    assert 'class="band-chip"' in body
    assert _named_bands(_hero(body), lang, "hero-pill") == earned
    assert _named_bands(body, lang, "band-chip") == earned


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_is_not_scored(monkeypatch, lang):
    _feed(monkeypatch, retained=True)
    hero = _hero(_today(lang))
    assert i18n.t(lang, "ui", "risk_held",
                  "HELD READING — WE CANNOT SCORE YOUR RISK") in hero
    # The SHAPE of the claim, not one spelling of it. Deliberately not the
    # absence of the "YOUR RISK" label: that string is a substring of the
    # held chip's own text, so asserting it is absent could never pass.
    assert not re.search(r"\d+/100", hero), "a risk score was printed anyway"
    assert i18n.t(lang, "ui", "baseline_chip",
                  "healthy adult, same plans") not in hero


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_is_scored(monkeypatch, lang):
    _feed(monkeypatch, retained=False)
    hero = _hero(_today(lang))
    assert i18n.t(lang, "ui", "risk_held",
                  "HELD READING — WE CANNOT SCORE YOUR RISK") not in hero
    assert re.search(r"\d+/100", hero)
    assert i18n.t(lang, "ui", "baseline_chip", "healthy adult, same plans") in hero


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_gets_no_band_advice(monkeypatch, lang):
    """The band advice is the largest health directive on the page and it is
    keyed on a band the held reading has not earned."""
    from saafsaans.services import risk

    _feed(monkeypatch, retained=True)
    hero = _hero(_today(lang))
    for band, advice in risk.BAND_ADVICE.items():
        assert i18n.t(lang, "band_advice", band, advice) not in hero, band
    # And the headline it is replaced by is the HELD one, not the no-reading
    # one -- "we have no air reading" printed above a number would be the same
    # self-contradiction seen from the other side.
    locality = PERSONA.get("locality", "Anand Vihar")
    assert pr.held_verdict(locality, lang) in hero
    assert pr.no_reading_verdict(locality, lang) not in hero


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_gets_its_band_advice(monkeypatch, lang):
    from saafsaans.services import risk

    _feed(monkeypatch, retained=False)
    hero = _hero(_today(lang))
    printed = [b for b, advice in risk.BAND_ADVICE.items()
               if i18n.t(lang, "band_advice", b, advice) in hero]
    assert len(printed) == 1, printed


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_names_no_go_out_window(monkeypatch, lang):
    """best_window is keyed off the severity as well as the hour -- above 300 it
    returns "No safe outdoor window today" -- so it is worked out from the
    reading and goes with the rest of it.

    Dropped rather than replaced by the no-reading rationale, which states "AQI
    reading is unavailable": false here, because there IS a reading.
    """
    _feed(monkeypatch, retained=True)
    body = _today(lang)
    assert 'class="hero-window"' not in body
    assert i18n.t(lang, "answer", "why_unknown",
                  "AQI reading is unavailable; treat {activity} as unsafe "
                  "until confirmed.").split("{")[0] not in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_names_its_window(monkeypatch, lang):
    _feed(monkeypatch, retained=False)
    assert 'class="hero-window"' in _today(lang)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_page_with_no_reading_at_all_still_names_a_window(monkeypatch, lang):
    """The third state's mirror. Suppressing the window for a held reading must
    not suppress it for the no-reading page, which has always carried it."""
    def get_aqi(locality, es_client=None):
        return waqi._fallback(locality), "fallback"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)
    assert 'class="hero-window"' in _today(lang)


# ------------------------------------------------------- the forwarded card
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_forwarded_held_reading_names_no_band(monkeypatch, lang):
    """The card lives in <head> and is the first thing most readers ever see.
    It used to preview a held reading as "{place} air right now: Very Poor",
    with no CACHED anywhere in it."""
    _feed(monkeypatch, retained=True)
    body = _today(lang)
    head = body[:body.find("</head>")]
    title = re.search(r'<meta property="og:title" content="([^"]*)"', head)
    assert title, head[-400:]
    printed = html.unescape(title.group(1))

    place = i18n.place(lang, PERSONA.get("locality", "Anand Vihar"))
    # It must say we are HOLDING a reading. Asserting only that no band word
    # appears was unfailable: deleting the held branch entirely falls through
    # to the no-reading card, whose title names no band either -- so the test
    # passed while the card claimed "no air reading right now" about a page
    # printing a number. Both the true card and the false one are pinned.
    assert printed == i18n.t(lang, "ui", "share_held",
                             "{place}: we are holding an earlier air reading"
                             ).replace("{place}", place)
    assert printed != i18n.t(lang, "ui", "share_no_reading",
                             "{place}: no air reading right now"
                             ).replace("{place}", place)
    assert _band_words(lang).isdisjoint({printed.upper()})


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_forwarded_live_reading_still_names_its_band(monkeypatch, lang):
    _feed(monkeypatch, retained=False)
    body = _today(lang)
    head = body[:body.find("</head>")]
    title = re.search(r'<meta property="og:title" content="([^"]*)"', head)
    label = normalize.aqi_category(AQI)[0]
    assert i18n.t(lang, "band_label", label, label).upper() in title.group(1).upper()


# --------------------------------------------- the two pages must not differ
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_today_and_city_pulse_agree_about_a_held_reading(monkeypatch, lang):
    """The property the whole surface exists for, asserted across the two pages
    rather than inside either: whichever band words City Pulse withholds from a
    held tile, Today must withhold from the same reading."""
    _feed(monkeypatch, retained=True)
    with TestClient(app) as client:
        city = client.get("/city", params={**PERSONA, "lang": lang}).text
        today = _hero(client.get("/", params={**PERSONA, "lang": lang}).text)

    grid = city[city.find('class="station'):]
    on_city = _named_bands(grid, lang, "bd")
    on_today = _named_bands(today, lang, "hero-pill")
    assert on_city == on_today, (lang, on_city, on_today)
    # And it is the EMPTY set they agree on. Without this the equality above is
    # satisfied just as well by both pages naming a band.
    assert on_city == set(), (lang, on_city)


# ------------------------------------------------------------- the prompt
def test_a_held_reading_reaches_the_prompt_marked_held():
    """freshness() was threaded through five presentation surfaces and zero
    generation surfaces, so the model was handed a held reading described
    exactly as a live one and answered in the present tense about air measured
    up to three hours ago."""
    from saafsaans.services import llm

    held = waqi._reading(PM25, PM10, station="ITO", city="Delhi", stale=False,
                         forecast=None, obs_time=OBS, retained=True,
                         source="cpcb")
    prompt = llm.build_user_message(held, PERSONA, [], "Can I go out?",
                                    "ITO", "2:00 PM")
    assert "HELD" in prompt
    # NOT the stale marker: stale means no numbers at all, and llm appends "we
    # have no reading for this area" to it -- beside a printed number.
    assert "STALE DATA" not in prompt


def test_a_live_reading_reaches_the_prompt_unmarked():
    from saafsaans.services import llm

    live = waqi._reading(PM25, PM10, station="ITO", city="Delhi", stale=False,
                         forecast=None, obs_time=OBS, retained=False,
                         source="cpcb")
    prompt = llm.build_user_message(live, PERSONA, [], "Can I go out?",
                                    "ITO", "2:00 PM")
    assert "HELD" not in prompt
    assert "STALE DATA" not in prompt
