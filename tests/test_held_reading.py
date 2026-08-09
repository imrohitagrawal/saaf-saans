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
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import aqi_scale, clock, i18n, normalize, risk, waqi
from saafsaans.web import presenters as pr
from saafsaans.web.main import app

# All FOUR persona fields: these tests assert the page a reader with an
# APPLIED persona sees, and persona_applied now requires the full set --
# without the locality the whole file would silently run in the first-visit
# example state, where the risk comparison is withheld for its own reason.
PERSONA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise", "theme": "light"}

# High enough to land in a severity band nobody could mistake for neutral: this
# is the reading that rendered band-g5 / VERY POOR / EXTREME on the shipped tip.
PM25, PM10 = 210.0, 300.0
AQI = aqi_scale.cpcb_aqi(PM25, PM10)[0]
# Relative to now, for the same reason as test_cpcb._recent_ist: a literal
# observation time ("2026-07-21T10:00:00+05:30") ages out of every freshness
# window the day after it is written. Nothing here asserts on the rendered time.
OBS = (clock.now_ist() - timedelta(hours=2)).isoformat()


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
    # Asserted as the SHAPE of the pill, not as the absence of band words in it.
    # `_named_bands(...) == set()` could not fail: deleting the pill's
    # {% if is_current %} guard makes it print the NEUTRALISED label, which is
    # "Unknown" / "पता नहीं" -- not a band word, so the word check stayed green
    # while the pill printed a claim the reading had not earned. This is the
    # same trap the band-chip assertion below already documents, and the same
    # fix: pin the element's content, not a vocabulary it happens to avoid.
    pill = re.search(r'<span class="hero-pill">(.*?)</span>', hero, re.S)
    assert pill, (lang, "the hero pill did not render")
    assert pill.group(1).strip() == f"AQI {AQI}", (lang, pill.group(1))
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


# --------------------------------------------- the surfaces carrying PROSE
#
# The first pass suppressed every LABEL on a held hero -- band word, colour,
# risk chip, go-out window, share title -- and left every surface carrying a
# SENTENCE. Those are the ones a reader acts on, and the suite could not see
# any of them: all four defects below were live with 1196 tests passing.


def _feed_values(monkeypatch, *, pm25, pm10, retained):
    """Serve one CPCB reading of the given concentrations for every locality."""
    def get_aqi(locality, es_client=None):
        return waqi._reading(pm25, pm10, station=locality, city="Delhi",
                             stale=False, forecast=None, obs_time=OBS,
                             retained=retained, source="cpcb"), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)


# A reading whose own meaning is REASSURING, deliberately -- the rest of this
# file uses a reading nobody could mistake for neutral, but the direction is
# what made this the worst of the held-reading defects. The page UNDER-warned.
# Delhi goes from 40 to 300 inside a morning inversion, so "Outdoor activity is
# fine for everyone" over a three-hour-old clean reading is the sentence that
# puts an asthmatic reader outside.
CLEAN_PM25, CLEAN_PM10 = 12.0, 30.0
CLEAN_AQI = aqi_scale.cpcb_aqi(CLEAN_PM25, CLEAN_PM10)[0]


def _earned_meaning(lang, aqi_val):
    """The band meaning this reading would earn if it were current."""
    category = normalize.aqi_category(aqi_val)[0]
    return i18n.t(lang, "aqi_meaning", category,
                  normalize.aqi_meaning(category))


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_does_not_print_the_meaning_of_its_own_band(monkeypatch, lang):
    """`meaning` is keyed by CATEGORY, and neutralising the category did not
    neutralise the prose derived from it.

    This was broken in ENGLISH ONLY, which is why reading the Hindi corpus would
    never have found it: i18n.t returns its fallback for any lang != "hi", and
    that fallback was the meaning computed from the real aqi. Hindi happens to
    have an aqi_meaning["Unknown"] and so took the safe branch. The reviewed
    language was the unsafe one.
    """
    _feed_values(monkeypatch, pm25=CLEAN_PM25, pm10=CLEAN_PM10, retained=True)
    body = html.unescape(_today(lang))
    earned = _earned_meaning(lang, CLEAN_AQI)

    # Partner assertion: prove the paragraph still renders, so this cannot pass
    # by the meaning vanishing altogether -- a held reading that explains
    # nothing is a different defect, not a fix.
    printed = re.search(r'<p class="meaning">(.*?)</p>', body, re.S)
    assert printed and len(printed.group(1).strip()) > 20, (
        lang, "the meaning paragraph vanished instead of being replaced")
    assert earned not in body, (
        lang, "a held reading printed the meaning of the band it did not earn")


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_clean_reading_live_does_print_its_meaning(monkeypatch, lang):
    """The mirror. Without it, deleting the meaning entirely would pass."""
    _feed_values(monkeypatch, pm25=CLEAN_PM25, pm10=CLEAN_PM10, retained=False)
    body = html.unescape(_today(lang))
    assert _earned_meaning(lang, CLEAN_AQI) in body, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_forwarded_held_reading_carries_no_band_meaning(monkeypatch, lang):
    """og:description read data["meaning"], and the card is built after it is
    translated -- so the forwarded preview carried the same false reassurance.
    Forwards are how this app travels, so it is often the ONLY thing seen."""
    _feed_values(monkeypatch, pm25=CLEAN_PM25, pm10=CLEAN_PM10, retained=True)
    body = html.unescape(_today(lang))
    described = re.search(r'<meta property="og:description" content="([^"]*)"',
                          body)
    assert described, "the forwarded card has no description at all"
    assert _earned_meaning(lang, CLEAN_AQI) not in described.group(1), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_prints_no_risk_comparison(monkeypatch, lang):
    """The comparison names two figures ("would be at 79", "your 91") -- the
    risk score arriving by a second route, forty lines under a chip that says
    it cannot be scored. The block was already guarded for NO reading; a held
    reading has an aqi, so it walked straight through."""
    _feed_values(monkeypatch, pm25=PM25, pm10=PM10, retained=True)
    assert 'class="compare"' not in _today(lang), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_prints_its_risk_comparison(monkeypatch, lang):
    _feed_values(monkeypatch, pm25=PM25, pm10=PM10, retained=False)
    assert 'class="compare"' in _today(lang), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_lists_no_score_drivers(monkeypatch, lang):
    """The drivers explain a score, and their first chip is "AQI 369 (Very
    Poor)" -- the band word, printed forty lines under a hero saying no band is
    worked out from this reading. The caveat and the methodology link beside
    them describe the same withheld score.

    Asserted as the ABSENCE OF THE BLOCK as well as the absence of band words
    in it, for the reason the band-chip assertion above documents: a chip built
    from the neutralised category would print "Unknown", which is not a band
    word, so the word check alone would stay green over a claim the reading has
    not earned.
    """
    _feed_values(monkeypatch, pm25=PM25, pm10=PM10, retained=True)
    body = _today(lang)
    assert _named_bands(body, lang, "driver") == set(), lang
    assert 'class="drivers"' not in body, lang
    assert i18n.t(lang, "ui", "link_score",
                  "See how the score is worked out ›") not in body, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_lists_its_score_drivers(monkeypatch, lang):
    """The mirror: all three chips, the band word among them, and the link."""
    _feed_values(monkeypatch, pm25=PM25, pm10=PM10, retained=False)
    body = _today(lang)
    label = normalize.aqi_category(AQI)[0]
    assert _named_bands(body, lang, "driver") == {
        i18n.t(lang, "band_label", label, label).upper()}, lang
    assert len(re.findall(r'<span class="driver">', body)) == 3, lang
    assert i18n.t(lang, "ui", "link_score",
                  "See how the score is worked out ›") in body, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_page_with_no_reading_at_all_still_lists_its_drivers(monkeypatch, lang):
    """The third state's mirror, and the reason the guard is not `is_current`
    alone: with no reading the first chip names the ABSENCE ("No reading —
    treated as unhealthy") rather than a figure, so the block has always been
    honest there and must stay."""
    def get_aqi(locality, es_client=None):
        return waqi._fallback(locality), "fallback"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)
    body = _today(lang)
    assert 'class="drivers"' in body, lang
    # No band-word assertion here: the Hindi no-reading chip reads "कोई रीडिंग
    # नहीं — हवा ख़राब मानकर चलें", and ख़राब is character-for-character the band
    # label for Poor. It names a severity the app is CHOOSING to assume and
    # says so in the same breath -- test_severity_needs_a_measurement exempts
    # this exact sentence from its sweep for the same reason.
    assert i18n.t(lang, "driver", "no_reading",
                  "No reading — treated as unhealthy") in html.unescape(body), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_makes_no_who_comparison(monkeypatch, lang):
    """Every surviving branch of who_line is present tense about the air, and
    the PM10-only branch says a station "is not reporting them right now" --
    live claims over a measurement hours old. has_index does not gate it: it
    only reaches the PM10-only branch, so the comparison printed regardless."""
    _feed_values(monkeypatch, pm25=CLEAN_PM25, pm10=CLEAN_PM10, retained=True)
    sentence = pr.who_line(CLEAN_PM25, lang=lang, has_index=True)
    assert sentence, "the fixture produces no WHO line, so this proves nothing"
    assert sentence not in html.unescape(_today(lang)), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_live_makes_the_who_comparison(monkeypatch, lang):
    _feed_values(monkeypatch, pm25=CLEAN_PM25, pm10=CLEAN_PM10, retained=False)
    sentence = pr.who_line(CLEAN_PM25, lang=lang, has_index=True)
    assert sentence and sentence in html.unescape(_today(lang)), lang


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


def test_the_prompt_never_calls_a_held_reading_live():
    """The same line that carries HELD READING, NOT CURRENT also opened with
    "Live AQI", so the label contradicted the correction beside it."""
    from saafsaans.services import llm

    held = waqi._reading(PM25, PM10, station="ITO", city="Delhi", stale=False,
                         forecast=None, obs_time=OBS, retained=True,
                         source="cpcb")
    prompt = llm.build_user_message(held, PERSONA, [], "Can I go out?",
                                    "ITO", "2:00 PM")
    assert "HELD READING" in prompt, "the marker itself went missing"
    assert "Live AQI" not in prompt
    # Partner assertion: the number is still labelled, so this cannot pass by
    # the whole line disappearing.
    assert f"AQI (ITO, 2:00 PM): {int(AQI)}" in prompt


def _band_passed_to_the_model(monkeypatch, *, retained):
    """The risk_band kwarg main.ask hands to llm.answer for this freshness."""
    captured = {}
    _feed_values(monkeypatch, pm25=PM25, pm10=PM10, retained=retained)
    from saafsaans.web import main as web_main

    def fake_answer(*args, **kwargs):
        captured.update(kwargs)
        return "### Verdict\nGo ahead\n", 0, "ok"

    monkeypatch.setattr(web_main.llm, "answer", fake_answer)
    with TestClient(app) as client:
        client.post("/ask", params={**PERSONA, "lang": "en"},
                    data={"question": "Can I go for a run this evening?"})
    assert captured, "llm.answer was never reached, so this proves nothing"
    return captured.get("risk_band")


def test_a_held_reading_does_not_republish_its_suppressed_band_to_the_model(monkeypatch):
    """The hero withholds the band; ask() passed it anyway, into the answer card
    AND the system prompt, under the line "This is what the page already tells
    them above your answer, so do not be more permissive than it" -- which was
    false. The aqi-only test let it through because a held reading HAS an aqi.

    This matters on the shipped path specifically: OPENROUTER_API_KEY is unset in
    production, so llm._rule_based runs, and it states the band in prose with no
    freshness awareness of its own.
    """
    assert _band_passed_to_the_model(monkeypatch, retained=True) is None


def test_the_same_reading_live_does_pass_its_band_to_the_model(monkeypatch):
    """The mirror. Passing None always would make the assertion above vacuous
    and would also lose the constraint that stops the card being more permissive
    than the verdict printed above it."""
    band = _band_passed_to_the_model(monkeypatch, retained=False)
    assert band and band in risk.BAND_ADVICE, band


# ------------------------------------------------- a section that vanishes
#
# Not about held readings, but about the same standard: an element that
# disappears between renders has to account for itself. The five-day outlook
# comes from the WAQI forecast, and a CPCB reading carries forecast=None -- so
# with a CPCB key set the section is absent for almost every reader and returns
# on the same locality whenever the fallback fires, with nothing said.
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_missing_outlook_explains_itself(monkeypatch, lang):
    _feed(monkeypatch, retained=False)          # a CPCB reading: forecast None
    body = _today(lang)
    assert 'aria-label="' + i18n.t(lang, "ui", "sec_outlook",
                                   "Five-day outlook") + '"' not in body
    assert i18n.t(lang, "ui", "outlook_absent",
                  "The five-day outlook comes from the WAQI feed. This reading "
                  "did not arrive with one, so there is none to show — a "
                  "reading read from CPCB directly never carries a forecast."
                  ) in html.unescape(body)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_reading_that_has_an_outlook_does_not_explain_its_absence(monkeypatch, lang):
    """The mirror. The explanation must not print above a rendered outlook."""
    # Today and tomorrow in IST, not literals: presenters.outlook_rows drops any
    # day before clock.today_ist(), so fixed past dates render no outlook at all
    # and this test would assert the absence of the thing it exists to require.
    today = clock.today_ist()
    forecast = {"daily": {"pm25": [
        {"day": today.isoformat(), "avg": 80, "min": 60, "max": 100},
        {"day": (today + timedelta(days=1)).isoformat(),
         "avg": 90, "min": 70, "max": 110}]}}

    def get_aqi(locality, es_client=None):
        return waqi._reading(PM25, PM10, station=locality, city="Delhi",
                             stale=False, forecast=forecast, obs_time=OBS,
                             retained=False, source="waqi"), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)

    body = html.unescape(_today(lang))
    assert 'aria-label="' + i18n.t(lang, "ui", "sec_outlook",
                                   "Five-day outlook") + '"' in body
    assert i18n.t(lang, "ui", "outlook_absent",
                  "The five-day outlook comes from the WAQI feed. This reading "
                  "did not arrive with one, so there is none to show — a "
                  "reading read from CPCB directly never carries a forecast."
                  ) not in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_page_with_no_reading_does_not_explain_a_missing_outlook(monkeypatch, lang):
    """The third state. The page has already said it has no number; a second
    explanation of a missing forecast is noise, not honesty."""
    def get_aqi(locality, es_client=None):
        return waqi._fallback(locality), "fallback"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main, "waqi", waqi)

    assert i18n.t(lang, "ui", "outlook_absent",
                  "The five-day outlook comes from the WAQI feed. This reading "
                  "did not arrive with one, so there is none to show — a "
                  "reading read from CPCB directly never carries a forecast."
                  ) not in html.unescape(_today(lang))


# ------------------------------------------------- dating a held reading
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_readings_chip_says_how_old_it_is_not_what_time_it_was(monkeypatch, lang):
    """The chip printed `_fmt_time` alone, so a measurement three weeks old
    rendered "CACHED · 5:26 PM" -- at 5:26 PM -- and read as minutes old. The one
    surface whose whole job is to date the number was the one that did not.

    Asserted as "the age is present AND the bare clock time is not", because
    either half alone passes for the wrong reason: adding the age while keeping
    the clock time leaves the misreading available, and dropping the clock time
    without adding the age leaves the reading undated.

    Same vocabulary City Pulse already teaches for this state ("CACHED · 13 H
    OLD"), and both `_age_label` and `ui.tag_old` were already translated, so no
    new copy was needed in either language.
    """
    from saafsaans.web import main as web_main

    old = (clock.now_ist() - timedelta(days=21)).isoformat()

    def feed(locality, es_client=None):
        return waqi._reading(PM25, PM10, station=locality, city="Delhi",
                             stale=False, forecast=None, obs_time=old,
                             retained=True, source="cpcb"), "ok"

    monkeypatch.setattr(waqi, "get_aqi", feed)
    monkeypatch.setattr(web_main, "waqi", waqi)

    chip = re.search(r'<span class="prov[^"]*">(.*?)</span>',
                     html.unescape(_today(lang)), re.S)
    assert chip, (lang, "the provenance chip did not render")
    text = re.sub(r"<[^>]+>", "", chip.group(1)).strip()

    age = web_main._age_label(old, lang)
    assert age, "the fixture produced no age, so this proves nothing"
    assert age in text, (lang, text, "the chip does not say how old the reading is")
    assert web_main._fmt_time(old, lang) not in text, (
        lang, text, "the chip still prints the bare clock time")


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_live_reading_is_still_dated_by_its_clock_time(monkeypatch, lang):
    """The mirror. An age on a live reading would be noise -- "0 MIN OLD" beside
    a reading that just arrived -- and the clock time is what a reader checks it
    against."""
    from saafsaans.web import main as web_main

    _feed(monkeypatch, retained=False)
    chip = re.search(r'<span class="prov[^"]*">(.*?)</span>',
                     html.unescape(_today(lang)), re.S)
    assert chip, (lang, "the provenance chip did not render")
    text = re.sub(r"<[^>]+>", "", chip.group(1)).strip()
    assert web_main._fmt_time(OBS, lang) in text, (lang, text)
