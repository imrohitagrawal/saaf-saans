"""The provenance panel must not call a stand-in a live reading.

Found by four independent persona walkthroughs of the running site, in both
languages. The collapsed label -- the one line most readers see without opening
anything -- said "1 live reading +" unconditionally, while the expanded line
fifteen lines lower in the same template branched correctly on the feed status.
So one panel contradicted itself, on a page that had already said SAMPLE in
three other places, and the Guide promises specifically that something cached or
estimated is never dressed up as live.

The identical block getting it right lower down is what makes this an oversight
rather than a decision, and it is why this test asserts the two halves agree
rather than merely asserting the string.
"""
import html

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n
from saafsaans.web.main import app

PERSONA = {"locality": "Anand Vihar", "age": "Adult", "condition": "Asthma",
           "activity": "Outdoor exercise"}


def _answered(client, lang):
    """Post a question, then read the page back with the provenance panel open."""
    client.post("/ask", params={**PERSONA, "lang": lang},
                data={"question": "Can I go out?"})
    body = client.get("/", params={**PERSONA, "lang": lang}).text
    turn = body[body.find('class="prov-bar"'):]
    return body, turn


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_missing_reading_is_never_counted_as_a_live_one(lang):
    """With no WAQI token there is no reading at all, which is the
    configuration the public deployment actually runs in -- so this is the
    default state of the page, not an edge case.

    This test used to assert `prov_count_before_sample` -- "1 sample reading +"
    -- was PRESENT, and so pinned the false claim in place after the sample was
    deleted: the panel counted one reading when the fallback carries none. The
    key is renamed and the assertion follows it. The count is the thing being
    checked, not the wording: it must not be one.
    """
    with TestClient(app) as client:
        body, turn = _answered(client, lang)
    live = i18n.t(lang, "ui", "prov_count_before", "1 live reading +")
    assert live not in turn, (
        f"the collapsed provenance label claims {live!r} on a page holding no "
        f"reading. The expanded line in the same panel says there is none."
    )
    none = i18n.t(lang, "ui", "prov_count_before_none", "no reading +")
    assert none in turn


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_panel_claims_no_measurement_when_none_was_taken(lang):
    """The expanded panel is the audit trail, so every claim inside it is load
    bearing -- including the kicker above the figures, which was unconditional
    and asserted "Measured at the time" over a row of dashes."""
    with TestClient(app) as client:
        client.post("/ask", params={**PERSONA, "lang": lang},
                    data={"question": "Can I go out?"})
        body = client.get("/", params={**PERSONA, "lang": lang}).text
        turn_id = body.split('id="turn-')[1].split('"')[0]
        opened = client.get("/", params={**PERSONA, "lang": lang,
                                         "prov": turn_id}).text
    panel = opened[opened.find('class="prov-body"'):]
    measured = i18n.t(lang, "ui", "prov_measured", "Measured at the time")
    assert measured not in panel, (lang, measured)
    assert i18n.t(lang, "ui", "prov_not_measured",
                  "Nothing was measured at the time") in panel, lang
    assert i18n.t(lang, "ui", "prov_none",
                  "no reading (the feed did not answer)") in panel, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_collapsed_label_and_the_expanded_line_agree(lang):
    """The property, rather than the string: whatever the panel says when shut
    must be what it says when open. This is what actually broke."""
    with TestClient(app) as client:
        client.post("/ask", params={**PERSONA, "lang": lang},
                    data={"question": "Can I go out?"})
        body = client.get("/", params={**PERSONA, "lang": lang}).text
        turn_id = body.split('id="turn-')[1].split('"')[0]
        opened = client.get("/", params={**PERSONA, "lang": lang,
                                         "prov": turn_id}).text
    panel = opened[opened.find('class="prov-bar"'):]
    # The two halves must be read separately. Scoping both to the whole panel
    # made this test unfailable: the collapsed label CONTAINS the expanded
    # line's phrase ("1 live reading +" contains "live reading"), so whenever
    # the collapsed half wrongly claimed live it dragged the expanded flag true
    # with it and the two agreed. That is the exact bug this test names, and it
    # sat green through it. The panel splits at prov-body: the label is above,
    # the detail lines below.
    split = panel.find('class="prov-body"')
    assert split > 0, "the expanded panel did not render; the split below is meaningless"
    collapsed, expanded = panel[:split], panel[split:]
    collapsed_says_live = i18n.t(lang, "ui", "prov_count_before",
                                 "1 live reading +") in collapsed
    expanded_says_live = i18n.t(lang, "ui", "prov_live", "live reading") in expanded
    assert collapsed_says_live == expanded_says_live, (
        f"the collapsed label and the expanded line disagree about whether this "
        f"reading is live: collapsed says live={collapsed_says_live}, "
        f"expanded says live={expanded_says_live}"
    )


# ------------------------------------------------------- the third state
#
# There are now three, not two: live, held (real numbers the source published
# earlier, re-served because it stopped answering) and none. Every surface in
# this panel branches on ``presenters.freshness`` for that reason -- four of
# them keyed off waqi_status alone, and a fix applied to the chip only would
# have left three of them calling a held reading live.
def _held_feed(monkeypatch, retained=True):
    from saafsaans.services import waqi

    def get_aqi(locality, es_client=None):
        return waqi._reading(90.0, 160.0, station=locality, city="Delhi",
                             stale=False, forecast=None,
                             obs_time="2026-07-21T10:00:00+05:30",
                             retained=retained), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)


def _open_panel(client, lang):
    client.post("/ask", params={**PERSONA, "lang": lang},
                data={"question": "Can I go out?"})
    body = client.get("/", params={**PERSONA, "lang": lang}).text
    turn_id = body.split('id="turn-')[1].split('"')[0]
    opened = client.get("/", params={**PERSONA, "lang": lang, "prov": turn_id}).text
    panel = opened[opened.find('class="prov-bar"'):]
    split = panel.find('class="prov-body"')
    assert split > 0, "the expanded panel did not render; the split is meaningless"
    return panel[:split], panel[split:]


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_held_reading_is_never_described_as_live(monkeypatch, lang):
    _held_feed(monkeypatch)
    with TestClient(app) as client:
        collapsed, expanded = _open_panel(client, lang)

    assert i18n.t(lang, "ui", "prov_count_before", "1 live reading +") not in collapsed
    assert i18n.t(lang, "ui", "prov_count_before_held", "1 held reading +") in collapsed
    assert i18n.t(lang, "ui", "prov_measured", "Measured at the time") not in expanded
    assert i18n.t(lang, "ui", "prov_measured_held",
                  "Measured earlier, not at the time") in expanded
    assert i18n.t(lang, "ui", "prov_live", "live reading") not in expanded
    assert i18n.t(lang, "ui", "prov_held",
                  "held reading (the source did not answer, so we kept the "
                  "last one)") in expanded


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_same_reading_unheld_is_described_as_live(monkeypatch, lang):
    """The mirror: the held wording must not swallow the live one."""
    _held_feed(monkeypatch, retained=False)
    with TestClient(app) as client:
        collapsed, expanded = _open_panel(client, lang)

    assert i18n.t(lang, "ui", "prov_count_before", "1 live reading +") in collapsed
    assert i18n.t(lang, "ui", "prov_count_before_held", "1 held reading +") not in collapsed
    assert i18n.t(lang, "ui", "prov_measured", "Measured at the time") in expanded
    assert i18n.t(lang, "ui", "prov_live", "live reading") in expanded


# ------------------------------------------------ the panel names its source
#
# Nothing else in the reading identifies which upstream answered: feed_aqi is
# None on a CPCB reading AND on a WAQI station whose own headline figure was
# "-". So the panel reads reading["source"], and each of the three values gets
# its own assertion -- a two-way branch would label the no-reading page, the
# state the public deployment runs in, as CPCB-sourced.
def _sourced_feed(monkeypatch, source):
    from saafsaans.services import waqi

    def get_aqi(locality, es_client=None):
        return waqi._reading(90.0, 160.0, station=locality, city="Delhi",
                             stale=False, forecast=None,
                             obs_time="2026-07-21T10:00:00+05:30",
                             feed_aqi=210 if source == "waqi" else None,
                             source=source), "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_cpcb_reading_names_cpcb_and_not_the_waqi_figure(monkeypatch, lang):
    from saafsaans.services import cpcb
    _sourced_feed(monkeypatch, "cpcb")
    with TestClient(app) as client:
        _collapsed, expanded = _open_panel(client, lang)
    # Jinja escapes the apostrophe in "WAQI's": Don&#39;t vs Don't has cost
    # this suite a green test before.
    expanded = html.unescape(expanded)
    assert cpcb.SOURCE_HOST in expanded
    assert i18n.t(lang, "ui", "prov_source_cpcb_before",
                  "read from CPCB itself, published on") in expanded
    assert i18n.t(lang, "ui", "prov_feed_figure", "WAQI's own figure") not in expanded


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_waqi_reading_names_the_feed_and_not_cpcbs_publication(monkeypatch, lang):
    from saafsaans.services import cpcb
    _sourced_feed(monkeypatch, "waqi")
    with TestClient(app) as client:
        _collapsed, expanded = _open_panel(client, lang)
    # Jinja escapes the apostrophe in "WAQI's": Don&#39;t vs Don't has cost
    # this suite a green test before.
    expanded = html.unescape(expanded)
    assert i18n.t(lang, "ui", "prov_feed_figure", "WAQI's own figure") in expanded
    assert cpcb.SOURCE_HOST not in expanded


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_turn_stored_before_the_source_field_existed_still_renders(monkeypatch, lang):
    """A reading rebuilt from Elasticsearch has no ``source`` key at all --
    it is deliberately not indexed. The panel must claim neither source rather
    than defaulting into one of them."""
    from saafsaans.services import cpcb, waqi

    def get_aqi(locality, es_client=None):
        reading = waqi._reading(90.0, 160.0, station=locality, city="Delhi",
                                stale=False, forecast=None,
                                obs_time="2026-07-21T10:00:00+05:30")
        reading.pop("source")
        return reading, "ok"

    monkeypatch.setattr(waqi, "get_aqi", get_aqi)
    with TestClient(app) as client:
        _collapsed, expanded = _open_panel(client, lang)
    # Jinja escapes the apostrophe in "WAQI's": Don&#39;t vs Don't has cost
    # this suite a green test before.
    expanded = html.unescape(expanded)
    assert cpcb.SOURCE_HOST not in expanded
    assert i18n.t(lang, "ui", "prov_feed_figure", "WAQI's own figure") not in expanded
    # And the panel still rendered its own figures.
    assert "AQI " in expanded
