"""Severity language requires a measurement behind it.

The rule this file exists to make mechanical: a sample or a stale reading must
never drive a severity word or a health instruction. The app used to break it
completely -- ITO, in July, with no credentials, rendered

    AQI 400 - VERY POOR
    Don't go out unless you must - this air is dangerous for you.

off a hardcoded winter concentration pair. The page did carry a "SAMPLE" chip;
every derived claim ignored it, which is why the fix was to remove the number
rather than to add a seventh marker.

Everything here is a PROPERTY over the reachable space -- every locality, both
languages, both states (a reading and no reading) -- because the project's own
recurring defect is a narrowing applied to one side and not its mirror. The
tests are two-sided on purpose: each also asserts that the severity language
DOES appear when there is a real reading, so a change that simply deleted the
verdict everywhere would fail rather than pass.
"""
import html as htmllib
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n, normalize, risk, waqi
from saafsaans.web import presenters as pr
from saafsaans.web.main import app

# All four fields: persona_applied requires the full set, and these pages are
# meant to be the ones an applied-persona reader sees, not the first-visit
# example state.
PERSONA = {"locality": "Anand Vihar", "age": "Senior", "condition": "COPD",
           "activity": "Outdoor exercise", "theme": "light"}

BANDS = ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe")

# Kept in step with today.html by test_the_no_reading_advice_is_the_one_the_page_renders
# below, so this literal cannot drift away from the template that prints it.
_ADVICE_NO_READING = ("Until we can tell you what the air is doing, take the "
                      "precautions you would take on a bad day: keep hard exercise "
                      "indoors, and carry your inhaler if you use one.")


def _severity_strings(lang):
    """Every sentence and word on the site that asserts how bad the air is.

    Collected from the sources the page renders from, not typed out here, so a
    new band verdict or a reworded advice line is covered the day it is added
    rather than the day someone remembers to update this list.
    """
    out = []
    for band in risk.RISK_BANDS:
        out.append(i18n.t(lang, "verdict", band, pr.verdict_for(band)))
        out.append(i18n.t(lang, "band_advice", band, risk.BAND_ADVICE[band]))
    for band in BANDS:
        out.append(i18n.t(lang, "band_label", band, band))
        out.append(i18n.t(lang, "aqi_meaning", band, normalize.AQI_MEANING[band]))
    return [s for s in out if s and s.strip()]


def _no_feed(monkeypatch):
    monkeypatch.setattr(waqi, "get_aqi",
                        lambda loc, es_client=None: (waqi._fallback(loc), "fallback"))


def _feed(monkeypatch, pm25=90.0):
    def get_aqi(loc, es_client=None):
        return (waqi._reading(pm25, pm25 * 1.6, station=loc, city="Delhi",
                              stale=False, forecast=None,
                              obs_time="2026-07-21T10:00:00+05:30"), "ok")
    monkeypatch.setattr(waqi, "get_aqi", get_aqi)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_no_reading_means_no_severity_language_anywhere_on_today(monkeypatch, lang):
    """The whole page, every locality, both languages.

    Swept over the rendered body rather than over one element, because the
    defect was distributed: the verdict, the band advice, the band meaning, the
    risk chip and the share card each reached the same fabricated number by a
    different route.
    """
    _no_feed(monkeypatch)
    forbidden = _severity_strings(lang)
    assert forbidden, "collected no severity strings; the sweep would prove nothing"

    # Two sentences the page prints whatever the reading is, and which contain
    # a band WORD without making a band CLAIM:
    #   * the Unknown meaning, which tells the reader to ASSUME bad air -- its
    #     Hindi contains "ख़राब" (Poor);
    #   * the risk-score notice, whose Hindi describes EPA's confidence as
    #     "मध्यम" (medium), the same word as the Moderate band.
    # Both are removed from the BODY by whole-string identity before the sweep,
    # not excluded from the forbidden list. A severity claim would have to be
    # character-for-character one of these two sentences to hide behind them,
    # and they are looked up from the corpus so a reword cannot strand this.
    # The other two are the no-reading copy itself, which says "take the
    # precautions you would take on a BAD day" and "no reading - air treated as
    # unhealthy". Both name a severity the app is choosing to ASSUME and both
    # say so in the same breath; neither claims a measurement.
    exempt = (i18n.t(lang, "aqi_meaning", "Unknown", normalize.AQI_MEANING["Unknown"]),
              i18n.t(lang, "ui", "risk_notice", risk.HEURISTIC_NOTICE),
              i18n.t(lang, "ui", "advice_no_reading", _ADVICE_NO_READING),
              i18n.t(lang, "driver", "no_reading", "No reading — treated as unhealthy"),
              # The mask precaution in the answer card. Its Hindi opens
              # "बाहर अच्छी तरह फ़िट होने वाला N95" -- "a WELL-fitting N95" --
              # and "अच्छी" is character-for-character the Hindi band label for
              # Good. It is an adjective about a mask, not a claim about the
              # air, and it is printed identically whatever the reading is.
              # Removed by whole-sentence identity from the corpus, like the
              # others above, rather than by dropping "अच्छी" from the
              # forbidden list -- which would have blinded the sweep to the
              # Good band everywhere on the page.
              i18n.t(lang, "answer", "precaution_mask_high",
                     "Wear a well-fitted N95/FFP2 mask outdoors and run an air "
                     "purifier indoors."))

    with TestClient(app) as c:
        for loc in waqi.LOCALITIES:
            # An ANSWER is asked for first, so the transcript block is part of
            # the body this sweeps. Without this POST the sweep saw only the
            # empty-thread page, and the one surface that renders a generated
            # verdict -- the answer card -- was outside it. The band advice for
            # the assumed-AQI band was being emitted there, in both languages,
            # while this test passed.
            c.post("/ask", params={**PERSONA, "locality": loc, "lang": lang},
                   data={"question": "Can I go for a run this evening?"},
                   follow_redirects=True)
            # Unescaped: Jinja writes "Don&#39;t go out unless you must" for
            # the Extreme verdict, so a raw substring sweep silently misses the
            # single most severe sentence on the site -- exactly the string
            # this file exists to forbid. Found by breaking the code and
            # watching only the Hindi half go red.
            body = htmllib.unescape(
                c.get("/", params={**PERSONA, "locality": loc, "lang": lang}).text)
            for sentence in exempt:
                assert sentence in body, (lang, loc, "exempt sentence not rendered; "
                                          "this exemption is stale and hides nothing")
                body = body.replace(sentence, "")
            for s in forbidden:
                assert s not in body, (lang, loc, s)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_real_reading_still_gets_its_severity_language(monkeypatch, lang):
    """The mirror. Without this, deleting the verdict outright would pass the
    test above, and a page that never speaks is not the goal."""
    _feed(monkeypatch, pm25=250.0)
    with TestClient(app) as c:
        body = htmllib.unescape(c.get("/", params={**PERSONA, "locality": "ITO",
                                                   "lang": lang}).text)
    aqi = waqi._reading(250.0, 400.0, station="ITO", city="Delhi", stale=False,
                        forecast=None, obs_time=None)["aqi"]
    band = normalize.aqi_category(aqi)[0]
    assert i18n.t(lang, "band_label", band, band) in body, (lang, band)
    assert re.search(r'class="hero-pill">AQI %d' % aqi, body), lang
    risk_band = risk.compute_risk(aqi, "copd", "outdoor_exercise", "senior")["band"]
    assert i18n.t(lang, "verdict", risk_band, pr.verdict_for(risk_band)) in body


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_no_reading_means_no_number_on_today(monkeypatch, lang):
    """No AQI figure, and no risk score either. The score was built on an
    ASSUMED AQI (risk.AQI_BASE_UNKNOWN), so printing it as "76/100 VERY HIGH"
    was an invented severity wearing a measurement's clothes."""
    _no_feed(monkeypatch)
    with TestClient(app) as c:
        for loc in waqi.LOCALITIES:
            body = htmllib.unescape(
                c.get("/", params={**PERSONA, "locality": loc, "lang": lang}).text)
            assert "hero-pill" not in body, (lang, loc)
            assert not re.search(r"\d+/100", body), (lang, loc)
            # The comparison sentence quotes two more scores off the same
            # assumed AQI ("A healthy adult ... would be at 79. Your 91 ...").
            # Suppressing the chip alone left that second route open.
            assert 'class="compare"' not in body, (lang, loc)
            assert 'class="scale-mark"' not in body, (lang, loc)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_share_card_never_carries_severity_without_a_reading(monkeypatch, lang):
    """The forwarded preview is the surface most readers ever see, so it is the
    one place the honesty has to hold hardest -- and it is in <head>, where the
    page's own markers cannot reach it."""
    _no_feed(monkeypatch)
    with TestClient(app) as c:
        for loc in waqi.LOCALITIES:
            body = htmllib.unescape(
                c.get("/", params={**PERSONA, "locality": loc, "lang": lang}).text)
            # The description fields used to be exempted from the band
            # assertion by a trailing `or key.endswith("description")`, which
            # made that assertion unconditionally TRUE for two of the four keys
            # -- the test written to protect the share card did not protect the
            # share card. Proved by mutation: appending " Severe" to the
            # no-reading description passed here and was caught only
            # incidentally by the whole-body sweep above.
            #
            # The exemption existed for one real reason: the Hindi Unknown
            # meaning legitimately contains "ख़राब" (Poor) in the sentence
            # telling the reader to ASSUME bad air. The sibling test in
            # test_share_and_time_honesty.py handles that honestly, by pinning
            # the description to the Unknown meaning with EXACT EQUALITY -- which
            # permits the honest sentence and forbids anything appended to it.
            # Same approach here, so both keys are actually checked.
            unknown = i18n.t(lang, "aqi_meaning", "Unknown",
                             normalize.AQI_MEANING["Unknown"])
            for key in ("og:title", "og:description", "twitter:title", "description"):
                m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % key, body)
                if not m:
                    continue
                content = htmllib.unescape(m.group(1))
                if key.endswith("description"):
                    assert content == unknown, (lang, loc, key, content)
                    continue
                for band in BANDS:
                    assert i18n.t(lang, "band_label", band, band) not in content, (
                        lang, loc, key, band)
                for rb in risk.RISK_BANDS:
                    verdict = i18n.t(lang, "verdict", rb, pr.verdict_for(rb))
                    assert verdict not in content, (lang, loc, key, rb)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_no_reading_means_no_go_outside_hour(monkeypatch, lang):
    """The least defensible line in the old inventory: the "if you must go out"
    window named a concrete hour chosen by a dominant pollutant that was itself
    a hardcoded key in the sample dict. Gurugram's fabricated "o3" produced
    "Early morning (about 6-9 AM)" -- a specific instruction about a specific
    hour, invented end to end."""
    _no_feed(monkeypatch)
    with TestClient(app) as c:
        for loc in waqi.LOCALITIES:
            body = c.get("/", params={**PERSONA, "locality": loc, "lang": lang}).text
            window = re.search(r'class="val">([^<]*)<', body)
            assert window, (lang, loc, "no window slot rendered at all")
            assert not re.search(r"\d\s*(AM|PM|बजे)", window.group(1)), (
                lang, loc, window.group(1))


def test_the_no_reading_advice_is_the_one_the_page_renders():
    """The exemption above is only safe if it names the string the template
    actually prints. A drifted literal would silently exempt nothing and, worse,
    would make the sweep look like it had checked something it had not."""
    from pathlib import Path
    template = (Path(__file__).resolve().parents[1]
                / "saafsaans/web/templates/today.html").read_text()
    flat = " ".join(template.split())
    assert " ".join(_ADVICE_NO_READING.split()) in flat


# --- The last real reading, with its age -----------------------------------
def _stored(monkeypatch, rows):
    from saafsaans.web import main as web_main
    monkeypatch.setattr(web_main.metrics, "station_grid", lambda client, locs: rows)
    monkeypatch.setattr(web_main, "get_client", lambda: object())


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_with_no_live_feed_today_names_the_last_real_reading_and_its_date(
        monkeypatch, lang):
    """Owner decision C. The number is a measurement and the date is its
    warrant, so they are printed together or not at all -- and with no band
    word beside them, because a reading from a month ago describes a month ago.
    """
    _no_feed(monkeypatch)
    _stored(monkeypatch, [{"station": "ITO", "aqi": 149,
                           "ts": "2026-06-23T11:00:00+05:30"}])
    with TestClient(app) as c:
        body = htmllib.unescape(
            c.get("/", params={**PERSONA, "locality": "ITO", "lang": lang}).text)
    line = re.search(r'class="last-real">(.*?)</span>', body, re.S)
    assert line, (lang, "no last-real line rendered")
    text = " ".join(line.group(1).split())
    assert "149" in text, text
    assert "23" in text, text
    from saafsaans.web.main import _month_abbr
    assert _month_abbr(lang, 6) in text, (lang, text)
    # The date is the OBSERVATION's, not ours -- and it carries no severity.
    for band in BANDS:
        assert i18n.t(lang, "band_label", band, band) not in text, (lang, band)
    # ...and it is still not a reading: the page must not have grown a hero
    # pill or a risk score off the back of it.
    assert "hero-pill" not in body, lang
    assert not re.search(r"\d+/100", body), lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_last_real_date_is_read_in_ist_not_utc(monkeypatch, lang):
    """The IST conversion in _fmt_date had no test that could see it.

    The only coverage used ts='2026-06-23T11:00:00+05:30', where
    `astimezone(IST)` is a no-op, so deleting the line left the suite green.
    This uses a UTC 'Z' stamp on the far side of midnight IST -- which is
    exactly the shape of a row dated by `@timestamp`, the compatibility path
    metrics.station_grid falls back to. 2026-07-19T20:00:00Z is 20 July,
    01:30 IST: the app must name the day the AIR was measured in Delhi.
    """
    from saafsaans.web.main import _month_abbr
    _no_feed(monkeypatch)
    _stored(monkeypatch, [{"station": "ITO", "aqi": 149,
                           "ts": "2026-07-19T20:00:00Z"}])
    with TestClient(app) as c:
        body = htmllib.unescape(
            c.get("/", params={**PERSONA, "locality": "ITO", "lang": lang}).text)
    text = " ".join(re.search(r'class="last-real">(.*?)</span>',
                              body, re.S).group(1).split())
    assert "20 %s" % _month_abbr(lang, 7) in text, (lang, text)
    assert "19 %s" % _month_abbr(lang, 7) not in text, (lang, text)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_last_real_date_from_another_year_says_which_year(monkeypatch, lang):
    """The date is the entire warrant for the number beside it, and day-plus-
    month made 23 June 2025 indistinguishable from 23 June 2026 -- a
    thirteen-month-old measurement reading as four weeks old. The seed and
    backfill paths make multi-year rows reachable.

    The mirror is asserted in the same test: a date inside the current year
    must NOT grow a year, or the fix is just noise on every line.
    """
    from saafsaans.web.main import _fmt_date
    from datetime import datetime
    from saafsaans.services.clock import IST
    this_year = datetime.now(IST).year
    old = _fmt_date("%d-06-23T11:00:00+05:30" % (this_year - 1), lang)
    assert str(this_year - 1) in old, (lang, old)
    current = _fmt_date("%d-06-23T11:00:00+05:30" % this_year, lang)
    assert str(this_year) not in current, (lang, current)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_with_nothing_stored_today_invents_no_last_reading(monkeypatch, lang):
    """The honest empty state, which is what the SHIPPED configuration renders:
    with no Elasticsearch credentials there is no client, so no last reading can
    be looked up and none is claimed."""
    _no_feed(monkeypatch)
    _stored(monkeypatch, [])
    with TestClient(app) as c:
        body = c.get("/", params={**PERSONA, "locality": "ITO", "lang": lang}).text
    assert 'class="last-real"' not in body, lang
    # The page still explains itself rather than going silent.
    assert i18n.t(lang, "prov", "no_reading", "◌ NO READING") in body, lang


def test_a_row_with_no_usable_date_is_not_shown_at_all(monkeypatch):
    """The date is the entire warrant for the number. A row we cannot date is a
    number with nothing behind it -- which is what this whole change removes."""
    _no_feed(monkeypatch)
    _stored(monkeypatch, [{"station": "ITO", "aqi": 149, "ts": "not-a-date"}])
    with TestClient(app) as c:
        body = c.get("/", params={**PERSONA, "locality": "ITO"}).text
    assert 'class="last-real"' not in body
    assert "149" not in body
