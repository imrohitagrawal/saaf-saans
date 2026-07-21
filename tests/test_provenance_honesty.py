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
def test_a_sample_reading_is_never_counted_as_a_live_one(lang):
    """With no WAQI token the reading is a labelled sample, which is the
    configuration the public deployment actually runs in -- so this is the
    default state of the page, not an edge case."""
    with TestClient(app) as client:
        body, turn = _answered(client, lang)
    live = i18n.t(lang, "ui", "prov_count_before", "1 live reading +")
    assert live not in turn, (
        f"the collapsed provenance label claims {live!r} on a page serving a "
        f"sample. The expanded line in the same panel says it is a sample."
    )
    sample = i18n.t(lang, "ui", "prov_count_before_sample", "1 sample reading +")
    assert sample in turn


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
    collapsed_says_live = i18n.t(lang, "ui", "prov_count_before",
                                 "1 live reading +") in panel
    expanded_says_live = i18n.t(lang, "ui", "prov_live", "live reading") in panel
    assert collapsed_says_live == expanded_says_live, (
        "the collapsed label and the expanded line disagree about whether this "
        "reading is live"
    )
