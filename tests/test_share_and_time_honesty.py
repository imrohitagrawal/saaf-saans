"""The forwarded card and the reading clock must not promise a measurement.

Both defects were found by persona walkthroughs of the running site, and both
had the same shape: a surface that looked like evidence while the page beside
it said the figure was a stand-in.

  * The share card stated the band as fact -- "Anand Vihar air right now:
    Severe" -- whether the figure was measured or sampled. On the shipped
    configuration there is no WAQI token, so EVERY forwarded link was in that
    state, and the word SAMPLE existed only after the recipient clicked.
    Forwarding is how this site is meant to travel, which makes the preview
    the surface most readers will ever see.
  * `_fmt_time` fell back to `datetime.now()`, printing the page-load clock in
    the slot where a reading's own observation time goes. The fallback reading
    has no observation time by definition, so a stand-in looked like a
    measurement taken this minute -- and the time changed on every refresh.
"""
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, normalize
from saafsaans.web.main import app, _fmt_time

PERSONA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise"}


def _meta(body: str, key: str) -> str:
    import html
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(key), body)
    return html.unescape(m.group(1)) if m else ""


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_forwarded_card_names_no_band_when_there_is_no_reading(lang):
    """The suite runs with no WAQI token, which is the shipped configuration,
    so this is the default state of every share card the app emits.

    This replaces `test_the_forwarded_card_says_a_sample_is_a_sample`, which
    asserted the card hedged a band word with "(sample)". Its premise was the
    defect: the card had a band to hedge only because a hardcoded winter
    concentration had been scored on the CPCB scale. The card must now carry no
    band at all, which is a strictly stronger claim -- a hedge can be missed,
    a word that is not on the card cannot be.
    """
    with TestClient(app) as client:
        body = client.get("/", params={**PERSONA, "lang": lang}).text
    title = _meta(body, "og:title")
    description = _meta(body, "og:description")
    assert title, "no share card rendered"

    expected = i18n.t(lang, "ui", "share_no_reading",
                      "{place}: no air reading right now").replace(
                          "{place}", i18n.place(lang, PERSONA["locality"]))
    assert title == expected, f"the card is not the no-reading card: {title!r}"

    # PROPERTY: the title states no CPCB band, in either language. Scoped to
    # the title on purpose. The band word is a CLAIM only where the card
    # asserts it as this place's air, and that is the title -- the description
    # is the app's Unknown meaning, whose Hindi legitimately contains "ख़राब"
    # in the sentence telling the reader to ASSUME bad air until they know.
    # Asserting over the description too would forbid the honest advice.
    for band in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"):
        assert i18n.t(lang, "band_label", band, band) not in title, (band, title)
        assert band not in title, (band, title)
    # And the description is exactly the app's own no-reading meaning, so the
    # card cannot say something the page does not.
    assert description == i18n.t(lang, "aqi_meaning", "Unknown",
                                 normalize.AQI_MEANING["Unknown"])


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_card_and_the_page_agree_about_the_reading(lang):
    """Whatever the page says about the feed, the card must say too. This is
    the property; the wording is free to change.

    Rewritten from "do both say SAMPLE" to "do both say there is no reading",
    because there is no sample any more. Still a two-sided agreement check, so
    it fails if either surface starts claiming a reading the other does not.
    """
    with TestClient(app) as client:
        body = client.get("/", params={**PERSONA, "lang": lang}).text
    page_has_no_reading = i18n.t(lang, "prov", "no_reading", "\u25cc NO READING") in body
    card_has_no_reading = _meta(body, "og:title") == i18n.t(
        lang, "ui", "share_no_reading", "{place}: no air reading right now").replace(
            "{place}", i18n.place(lang, PERSONA["locality"]))
    assert page_has_no_reading == card_has_no_reading, (
        "the forwarded card and the page disagree about whether this reading "
        "was measured"
    )


def test_a_reading_with_no_time_does_not_borrow_the_clock():
    """The regression that matters: two calls a moment apart must not produce
    two different times for a reading that has none."""
    assert _fmt_time(None) == _fmt_time(None)
    assert not re.search(r"\d{1,2}:\d\d", _fmt_time(None)), (
        f"_fmt_time(None) printed a clock time: {_fmt_time(None)!r}"
    )
    # A real timestamp still formats normally.
    assert _fmt_time("2026-07-21T10:00:00+05:30") == "10:00 AM"


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_reading_card_says_there_is_no_reading_time(lang):
    with TestClient(app) as client:
        body = client.get("/", params={**PERSONA, "lang": lang}).text
    assert i18n.t(lang, "ui", "no_obs_time", "no reading time") in body
