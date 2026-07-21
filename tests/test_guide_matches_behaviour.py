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
RETIRED = {"en": ("SAMPLE", "stand-in"), "hi": ("नमूना", "अंदाज़न")}


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
    City Pulse legend and the provenance panel, and each was fixed on its own
    schedule."""
    with TestClient(app) as c:
        body = htmllib.unescape(c.get(path, params={"lang": lang}).text)
    for word in RETIRED[lang]:
        assert word not in body, (lang, path, word)
