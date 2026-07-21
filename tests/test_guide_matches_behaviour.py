"""The Guide must describe the app that exists, not the one that used to.

The Guide is the page whose whole job is to explain the data policy, so it is
the page that goes wrong most quietly: nothing on it is derived from a reading,
so no rendering test notices when the behaviour underneath it moves. It spent a
release telling readers, in both languages, that a place with no reading is
shown "a typical stand-in figure ... marked SAMPLE", after the stand-in figure
and the SAMPLE tag had both been deleted -- while the pages themselves printed
NO READING. Hard rule 5: a claim the code does not support is removed.

These are properties over the tag vocabulary rather than assertions about
sentences, so a reword of the Guide passes and a change of BEHAVIOUR fails.
"""
import html as htmllib

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import i18n
from saafsaans.web.main import app

# Every tag word the station grid can print, looked up from the corpus the
# template prints them from -- not typed out here, so a renamed tag moves this
# test with it instead of stranding it.
TAG_KEYS = (("tag_cached", "CACHED"), ("tag_no_reading", "NO READING"))

# The vocabulary of the deleted stand-in behaviour. These are spellings that
# must appear on NO page: the app cannot show a sample or a stand-in figure any
# more, so any page that names one is describing a different app.
# Matched case-insensitively, because the same claim was made in three
# registers: the Guide's "stand-in figure", the City Pulse tag "SAMPLE", and the
# provenance panel's "cached sample (feed missed)".
RETIRED = {"en": ("sample", "stand-in"), "hi": ("नमूना", "अंदाज़न")}


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_guide_describes_the_tags_the_app_actually_prints(lang):
    """A legend for a different page is worse than no legend: it sends the
    reader looking for a marker that will never appear."""
    with TestClient(app) as c:
        body = htmllib.unescape(c.get("/guide", params={"lang": lang}).text)
    for key, default in TAG_KEYS:
        word = i18n.t(lang, "ui", key, default)
        assert word in body, (lang, key, word)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("path", ["/guide", "/", "/city"])
def test_no_page_still_promises_a_stand_in_figure(lang, path):
    """Swept across the reader-facing pages, not just the Guide, because the
    claim was duplicated: the same vocabulary lived in the Guide answer, the
    City Pulse legend, the provenance panel and the answer body, and each was
    fixed on its own schedule.

    An ANSWER is asked for first and the provenance panel is opened, so the
    transcript is inside the swept body. A sweep of the empty page would miss
    the provenance count, the panel's detail line and the answer's own
    "(using cached sample data)" suffix -- which is exactly how all three
    survived the release that deleted the sample.
    """
    with TestClient(app) as c:
        c.post("/ask", params={"lang": lang},
               data={"question": "Can I go for a run this evening?"},
               follow_redirects=True)
        body = htmllib.unescape(c.get(path, params={"lang": lang, "prov": "0"}).text)
    low = body.lower()
    for word in RETIRED[lang]:
        assert word.lower() not in low, (lang, path, word)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_system_view_does_not_call_a_feed_miss_a_cache_hit(lang):
    """The KPI over `waqi_fallback_rate` was labelled "feed misses → cached".

    A feed miss routes to `waqi._fallback`, which returns a reading with every
    numeric field None. Nothing is cached and nothing is served, so an operator
    reading "42%" was told 42% of requests came from cache when in fact they
    were answered with no number at all. It also collided with City Pulse's
    CACHED, which means something else again -- a stored reading we do hold.
    Same word, two definitions, on the two pages that exist to explain the app.

    The property: the label for this KPI must not use the CACHED tag word.
    """
    from saafsaans.web import main as web_main
    real = web_main.get_client
    web_main.get_client = lambda: object()
    try:
        with TestClient(app) as c:
            body = htmllib.unescape(c.get("/system", params={"lang": lang}).text)
    finally:
        web_main.get_client = real
    label = i18n.t(lang, "ui", "sys_kpi_feed_fallback", "feed misses → no reading")
    assert label in body, (lang, label)
    cached = i18n.t(lang, "ui", "tag_cached", "CACHED")
    assert cached.lower() not in label.lower(), (lang, label, cached)


# --------------------------------------------------- which source it reads first
#
# The Guide said readings are "read through the WAQI feed" and described
# converting WAQI's US EPA index back into concentrations -- neither of which
# happens on a CPCB reading, and CPCB is the source the code tries FIRST.
# Nothing anywhere named data.gov.in. Rule 5, shipped, in two languages.
@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_guide_names_the_source_the_code_actually_reads_first(lang):
    """The host token is derived from the module, not typed here, so changing
    the endpoint moves this test with it.

    The SOURCE_NAME half ("CPCB") was already satisfied before this run; the
    host is the half that bites.
    """
    from urllib.parse import urlparse

    from saafsaans.services import cpcb

    hostname = urlparse(cpcb.ENDPOINT).hostname
    assert hostname.endswith(cpcb.SOURCE_HOST), (
        "SOURCE_HOST no longer describes the endpoint this module calls")

    with TestClient(app) as c:
        body = htmllib.unescape(c.get("/guide", params={"lang": lang}).text)
    assert cpcb.SOURCE_NAME in body, lang
    assert cpcb.SOURCE_HOST in body, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_guide_still_names_the_fallback(lang):
    """The rewrite must not delete the fallback's existence: WAQI really is
    consulted when CPCB has nothing, and Wazirpur is the case where it wins."""
    with TestClient(app) as c:
        body = htmllib.unescape(c.get("/guide", params={"lang": lang}).text)
    assert "WAQI" in body, lang


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_the_conversion_claim_is_scoped_to_the_feed_it_applies_to(lang):
    """A paragraph-level property, not a spelling.

    The US-EPA inversion happens only to a reading that came through WAQI --
    tests/test_cpcb.py::test_a_cpcb_concentration_is_not_put_through_the_waqi_
    inversion forbids it on the other path. So the paragraph making that claim
    must name WAQI, and the sentence naming CPCB as the source read first must
    not make it.
    """
    import re

    from saafsaans.services import cpcb

    with TestClient(app) as c:
        body = htmllib.unescape(c.get("/guide", params={"lang": lang}).text)
    # Scoped to the section that explains the scale. "US EPA" also appears in
    # the risk-score provenance, where it cites published breathing rates and
    # has nothing to do with any conversion.
    section = body[body.find('id="numbers"'):]
    section = section[:section.find("</section>")]
    assert len(section) > 200, (lang, "the scale section did not render")
    paragraphs = [re.sub(r"<[^>]+>", " ", p)
                  for p in re.findall(r"<p[^>]*>(.*?)</p>", section, re.S)]
    epa = [p for p in paragraphs if "EPA" in p]
    assert epa, (lang, "no paragraph mentions the EPA scale at all")
    for para in epa:
        assert "WAQI" in para, (lang, para)

    # The answer that names the primary source must not be the one claiming a
    # conversion: that answer is about a path where no conversion happens.
    answers = [re.sub(r"<[^>]+>", " ", a)
               for a in re.findall(r"<dd[^>]*>(.*?)</dd>", body, re.S)]
    primary = [a for a in answers if cpcb.SOURCE_HOST in a]
    assert primary, (lang, "no answer names the primary source")
    for para in primary:
        assert "EPA" not in para, (lang, para)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
@pytest.mark.parametrize("path", ["/", "/guide", "/city"])
def test_every_page_footer_names_the_primary_source(lang, path):
    """The only source list on EVERY page. It said "Data: WAQI/CPCB" --
    fallback first, primary second, and no host at all."""
    from saafsaans.services import cpcb

    with TestClient(app) as c:
        body = htmllib.unescape(c.get(path, params={"lang": lang}).text)
    footer = body[body.find('class="foot"'):]
    footer = footer[:footer.find("</footer>")]
    assert len(footer) > 50, (lang, path, "no footer rendered")
    assert cpcb.SOURCE_NAME in footer, (lang, path)
    assert cpcb.SOURCE_HOST in footer, (lang, path)
    assert footer.index(cpcb.SOURCE_NAME) < footer.index("WAQI"), (
        lang, path, "the fallback is named before the primary source")
