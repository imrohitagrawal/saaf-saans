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

PERSONA = {"age": "Senior", "condition": "COPD",
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
              i18n.t(lang, "driver", "no_reading", "No reading — treated as unhealthy"))

    with TestClient(app) as c:
        for loc in waqi.LOCALITIES:
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
            for key in ("og:title", "og:description", "twitter:title", "description"):
                m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % key, body)
                if not m:
                    continue
                content = m.group(1)
                for band in BANDS:
                    assert i18n.t(lang, "band_label", band, band) not in content \
                        or key.endswith("description"), (lang, loc, key, band)
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
