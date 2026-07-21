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

from saafsaans.services import i18n
from saafsaans.web.main import app, _fmt_time

PERSONA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise"}


def _meta(body: str, key: str) -> str:
    import html
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(key), body)
    return html.unescape(m.group(1)) if m else ""


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_forwarded_card_says_a_sample_is_a_sample(lang):
    """The suite runs with no WAQI token, which is the shipped configuration,
    so this is the default state of every share card the app emits."""
    with TestClient(app) as client:
        body = client.get("/", params={**PERSONA, "lang": lang}).text
    title = _meta(body, "og:title")
    description = _meta(body, "og:description")
    assert title, "no share card rendered"

    # The title must be built from the sample key, not the live one. Built the
    # same way the code builds it and compared whole, rather than sliced apart:
    # a partial match would pass on a title assembled from the wrong template.
    def matches(key, english):
        """The title against a template, with {band} as a wildcard.

        The band's case is the template's business, not this test's -- the hero
        upper-cases it in CSS and the card does not -- so only the scaffolding
        and the place are pinned here.
        """
        pattern = re.escape(i18n.t(lang, "ui", key, english)
                            .replace("{place}", i18n.place(lang, PERSONA["locality"])))
        return re.fullmatch(pattern.replace(re.escape("{band}"), ".+"), title)

    assert matches("share_title_sample", "{place} air (sample): {band}"), (
        f"the card title is not the sample title: {title!r}")
    assert not matches("share_title", "{place} air right now: {band}"), (
        f"the card claims a live reading on a sample: {title!r}")

    note = i18n.t(lang, "ui", "share_sample_note",
                  "This is a typical figure for the place, not a live measurement.")
    assert note in description, (
        f"the forwarded card for a SAMPLE reading carries no hedge. "
        f"description={description!r}"
    )


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_card_and_the_page_agree_about_the_reading(lang):
    """Whatever the page says about the feed, the card must say too. This is
    the property; the wording is free to change."""
    with TestClient(app) as client:
        body = client.get("/", params={**PERSONA, "lang": lang}).text
    page_says_sample = i18n.t(lang, "prov", "sample", "◌ SAMPLE — not a reading") in body
    card_says_sample = i18n.t(
        lang, "ui", "share_sample_note",
        "This is a typical figure for the place, not a live measurement.") in _meta(body, "og:description")
    assert page_says_sample == card_says_sample, (
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
