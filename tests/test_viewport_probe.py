"""The viewport probe: what it counts, and what it must never write down.

The probe is a CSS media-query beacon. The stylesheet declares one background
image per width band; the browser fetches only the band whose query matches, so
the server learns the real viewport band with no JavaScript, no cookie and no
user-agent parsing. These tests pin the server half. The browser half -- that a
browser actually issues exactly one of the three requests -- is only observable
in a browser, and lives in tests/test_viewport_browser.py.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saafsaans.services import es, normalize, ratelimit
from saafsaans.web import main as web_main
from saafsaans.web.main import app

CSS_PATH = Path(web_main.__file__).parent / "static" / "app.css"


class Recorder:
    """An ES client that records what it was asked to index, and how."""

    def __init__(self):
        self.docs = []
        self.options_seen = []

    def options(self, **kwargs):
        self.options_seen.append(kwargs)
        return self

    def index(self, index, document):
        self.docs.append({"index": index, "doc": document})


@pytest.fixture
def recorder(monkeypatch):
    client = Recorder()
    monkeypatch.setattr(web_main, "get_client", lambda: client)
    return client


# --- what reaches storage --------------------------------------------------
def test_the_probe_records_the_band_and_nothing_else(recorder):
    with TestClient(app) as client:
        client.get("/probe/narrow.gif")

    assert len(recorder.docs) == 1, recorder.docs
    written = recorder.docs[0]
    assert written["index"] == es.INDEX_VIEWPORT
    assert set(written["doc"]) == {"@timestamp", "band"}
    assert written["doc"]["band"] == "narrow"


def test_the_probe_never_writes_an_identifier(recorder):
    """The privacy floor, asserted against a request that carries every
    identifier a browser can send.

    The allowlist is compared for EQUALITY rather than screened for suspicious
    names. A rule like "no field whose name contains hash" waves through
    `referer`, `client_id` and `remote`; equality makes any addition a
    deliberate edit to this line, which a reviewer sees.

    The absence half is worthless without the partner below it: the same
    detection is run against a document that DOES carry a session hash, so a
    detector that could never fire cannot pass this test.
    """
    sid = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    agent = "Mozilla/5.0 (probe-test-user-agent)"
    address = "203.0.113.7"
    with TestClient(app, cookies={"sid": sid}) as client:
        client.get("/probe/wide.gif",
                   headers={"User-Agent": agent, "X-Forwarded-For": address})

    doc = recorder.docs[0]["doc"]
    haystack = " ".join(str(value) for value in doc.values())
    hashed = normalize.session_hash(sid)
    for secret in (sid, agent, address, hashed):
        assert secret not in haystack, (secret, doc)

    assert es.VIEWPORT_FIELDS == {"@timestamp", "band"}
    assert set(doc) <= es.VIEWPORT_FIELDS
    # The partner: the band IS recorded, and the same detection fires on a
    # document this codebase really produces. Built from es.log_telemetry --
    # which does carry a session hash -- rather than from a dict literal
    # assembled here, which would only prove that `in` works.
    assert doc["band"] == "wide"

    telemetry = {}

    class _Telemetry:
        def index(self, index, document):
            telemetry.update(document)

    es.log_telemetry(_Telemetry(), {"@timestamp": "t", "session_hash": hashed,
                                    "event": "chat_completed"})
    assert hashed in " ".join(str(v) for v in telemetry.values()), (
        "the identifier detection cannot fire at all -- the absence above "
        "proves nothing")


def test_log_viewport_drops_any_stray_field():
    """The allowlist is the guarantee, so it is asserted at the write helper
    too -- not only at the one call site that exists today."""
    captured = {}

    class FakeClient:
        def options(self, **kwargs):
            return self

        def index(self, index, document):
            captured["doc"] = document

    es.log_viewport(FakeClient(), "mid")
    assert set(captured["doc"]) == {"@timestamp", "band"}

    captured.clear()
    es._safe_index(FakeClient(), es.INDEX_VIEWPORT,
                   {"@timestamp": "t", "band": "mid", "session_hash": "abc",
                    "user_agent": "x"}, es.VIEWPORT_FIELDS)
    assert set(captured["doc"]) == {"@timestamp", "band"}


def test_the_probe_write_cannot_hold_a_page_render(recorder):
    """es.py's own rule for the reachability ping: a hung endpoint must not
    hold a render for the client's full ten seconds. The probe fires on every
    page load, so it carries a tighter bound than the ping's own two."""
    with TestClient(app) as client:
        client.get("/probe/mid.gif")

    assert {"request_timeout": 1} in recorder.options_seen, recorder.options_seen
    # Partner: the bounded call still wrote the document.
    assert recorder.docs[0]["doc"]["band"] == "mid"


def test_a_missing_index_client_is_not_an_error(monkeypatch):
    """With no Elastic credentials `get_client()` is None all the way down, and
    the probe must still serve its image rather than raise."""
    monkeypatch.setattr(web_main, "get_client", lambda: None)
    with TestClient(app) as client:
        response = client.get("/probe/wide.gif")
    assert response.status_code == 200
    assert response.content.startswith(b"GIF8")


# --- the response itself ---------------------------------------------------
def test_the_probe_is_never_cached(recorder):
    """Without this the browser answers the second page load from its own
    cache and every returning reader stops reporting, so the counts silently
    under-read exactly the people who came back."""
    with TestClient(app) as client:
        response = client.get("/probe/narrow.gif")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("image/gif")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"GIF8") and len(response.content) > 20


def test_the_probe_sets_no_cookie(recorder):
    """Every rendered page attaches a session cookie. This response must not:
    it is a counter, and a counter that hands out an identifier is a tracker."""
    with TestClient(app) as client:
        response = client.get("/probe/wide.gif")
    # Asserted before the absence below: a 404 carries no cookie either, so
    # without this line the test passes while the probe does not exist at all.
    assert response.status_code == 200
    assert response.content.startswith(b"GIF8")
    assert "set-cookie" not in {k.lower() for k in response.headers}


def test_an_unknown_band_is_never_counted(recorder):
    """A path segment is caller-controlled, so it is checked against the closed
    set the stylesheet asks for -- otherwise any string a crawler invents ends
    up as a bucket on the System view."""
    with TestClient(app) as client:
        unknown = client.get("/probe/desktop.gif")
    assert unknown.status_code == 404
    # Not merely uncounted: it must not serve a valid image either, or
    # /probe/anything.gif becomes an open image endpoint.
    assert not unknown.content.startswith(b"GIF8")
    assert recorder.docs == []

    # The partner: a band the stylesheet does ask for is served and counted.
    with TestClient(app) as client:
        known = client.get("/probe/wide.gif")
    assert known.status_code == 200
    assert [d["doc"]["band"] for d in recorder.docs] == ["wide"]


def test_a_flood_stops_being_counted_but_never_stops_being_served(recorder,
                                                                  monkeypatch):
    """The counter is public and uncacheable, so a loop could otherwise write
    an unbounded number of documents and decide a layout argument.

    Throttling must never reach the page: over the limit the image is still
    served, exactly as before, and only the recording stops.
    """
    monkeypatch.setattr(ratelimit, "PROBE_LIMIT", 3)
    with TestClient(app) as client:
        responses = [client.get("/probe/mid.gif") for _ in range(6)]

    assert [r.status_code for r in responses] == [200] * 6
    assert all(r.content.startswith(b"GIF8") for r in responses)
    assert len(recorder.docs) == 3, [d["doc"] for d in recorder.docs]


# --- the stylesheet and the server must agree ------------------------------
def _probe_contexts():
    """{context: [band, ...]} for the top level and each width media block."""
    css = CSS_PATH.read_text()
    contexts, depth, current, buffer = {}, 0, "top", ""
    index = 0
    while index < len(css):
        found = re.compile(r"@media([^{]*)\{").match(css, index)
        if found and depth == 0:
            contexts.setdefault(current, "")
            contexts[current] += buffer
            buffer = ""
            query = " ".join(found.group(1).split())
            depth, end = 1, found.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(css[end], 0)
                end += 1
            contexts[query] = contexts.get(query, "") + css[found.end():end - 1]
            index = end
            continue
        buffer += css[index]
        index += 1
    contexts["top"] = contexts.get("top", "") + buffer
    return {name: re.findall(r"url\(\"/probe/([a-z]+)\.gif\"\)", body)
            for name, body in contexts.items()}


def test_the_stylesheet_asks_for_exactly_the_bands_the_server_counts():
    """The stylesheet is the only thing that ever names a band, and the server
    is the only thing that can count one. If they drift, the probe fetches a
    URL that 404s and the breakdown is silently empty for ever.

    Exactly one declaration per context is what makes "one request per page
    load" true: the cascade picks the last matching rule, so a second URL in
    one context would be dead and a missing one would leave a band unmeasured.
    """
    contexts = _probe_contexts()
    narrow_query = f"(max-width: {web_main.VIEWPORT_BREAKPOINTS[0]}px)"
    wide_query = f"(min-width: {web_main.VIEWPORT_BREAKPOINTS[1]}px)"

    for name in ("top", narrow_query, wide_query):
        assert len(contexts.get(name, [])) == 1, (name, contexts.get(name))

    declared = [contexts["top"][0], contexts[narrow_query][0], contexts[wide_query][0]]
    assert len(set(declared)) == 3, declared
    assert set(declared) == set(web_main.VIEWPORT_BANDS), declared
    # The narrow block must claim the narrow band and the wide block the wide
    # one; swapping them would invert every reading while staying "distinct".
    assert contexts[narrow_query][0] == "narrow"
    assert contexts[wide_query][0] == "wide"

    with TestClient(app) as client:
        for band in declared:
            assert client.get(f"/probe/{band}.gif").status_code == 200, band


def test_no_probe_url_in_the_stylesheet_is_absolute():
    """A probe pointing off-origin would send the reader's address to a third
    party on every page load -- the one thing this architecture does not do."""
    css = CSS_PATH.read_text()
    assert "url(\"/probe/" in css
    assert not re.search(r"url\(\"?https?://[^)]*probe", css)


# --- the System view -------------------------------------------------------
BANDS_STUB = [{"band": "narrow", "count": 12},
              {"band": "mid", "count": 0},
              {"band": "wide", "count": 4}]


def _system(monkeypatch, lang="en", rows=BANDS_STUB, answering=True):
    from saafsaans.services import es as es_module, metrics
    # `None` is a distinct answer from `[]` here and must survive the stub.
    monkeypatch.setattr(metrics, "viewport_bands",
                        lambda c: None if rows is None else list(rows))
    # Both branches are set explicitly. One test calls this twice, and
    # monkeypatch does not undo between calls inside a test, so leaving the
    # False case unpatched would silently inherit the True case's client.
    monkeypatch.setattr(web_main, "get_client",
                        (lambda: object()) if answering else (lambda: None))
    monkeypatch.setattr(es_module, "index_answers", lambda c: answering)
    with TestClient(app) as client:
        return client.get("/system", params={"lang": lang}).text


def _viewport_card(body):
    """Just the viewport section, so a count elsewhere cannot stand in for it."""
    from saafsaans.services import i18n
    for heading in (i18n.HI["ui"]["sys_h_viewport"], "Page loads by browser width"):
        start = body.find(heading)
        if start != -1:
            return body[start:body.find("</section>", start)]
    return ""


def test_the_system_view_shows_the_viewport_breakdown_in_both_languages(monkeypatch):
    from saafsaans.services import i18n

    english = _viewport_card(_system(monkeypatch, "en"))
    assert english, "no viewport card on the English System view"
    for label in ("0–560px", "561–899px", "900px+"):
        assert label in english, (label, english)
    assert english.count('class="sysbar"') == 3, english
    assert ">12<" in english and ">4<" in english

    hindi = _viewport_card(_system(monkeypatch, "hi"))
    assert hindi, "no viewport card on the Hindi System view"
    assert i18n.HI["ui"]["sys_h_viewport"] in hindi
    assert "Page loads by browser width" not in hindi
    # The width ranges are the measurement itself and stay in figures.
    for label in ("0–560px", "561–899px", "900px+"):
        assert label in hindi, (label, hindi)


def test_the_viewport_caveat_says_page_loads_not_people(monkeypatch):
    """The one thing this figure must never be read as is a headcount. There
    is no cookie and no identifier, so it cannot be one."""
    import html as _html
    from saafsaans.services import i18n

    english = _viewport_card(_system(monkeypatch, "en"))
    assert 'class="caveat"' in english, english
    assert "Page loads, not people" in _html.unescape(english)
    assert "not the kind of device" in _html.unescape(english)

    hindi = _html.unescape(_viewport_card(_system(monkeypatch, "hi")))
    assert i18n.HI["ui"]["sys_viewport_caveat"] in hindi
    assert "Page loads, not people" not in hindi


def test_the_viewport_block_tells_an_unrecorded_zero_from_a_measured_one(monkeypatch):
    """Three states that all read as a zero, and are three different facts.

    The dangerous one is the middle case: the CLUSTER is answering and other
    panels have rows, while this index is missing, mis-mapped or unauthorised.
    Keying the empty state off the page-wide has_index printed "no page loads
    counted yet" there -- a measured zero over traffic that was counted and is
    merely unreadable.
    """
    import html as _html
    from saafsaans.services import i18n

    # 1. Counted. The measured zero IS printed, beside its non-zero neighbours.
    counted = _viewport_card(_system(monkeypatch, "en"))
    assert counted.count('class="sysbar"') == 3
    assert ">0<" in counted

    # 2. The index answered and holds nothing yet.
    empty = _viewport_card(_system(monkeypatch, "en", rows=[]))
    assert 'class="sysbar"' not in empty, empty
    assert "No page loads counted yet" in empty
    assert "Not a measured zero" not in empty

    # 3. This index could not be read -- WITH the rest of the cluster healthy.
    unread = _viewport_card(_system(monkeypatch, "en", rows=None, answering=True))
    assert 'class="sysbar"' not in unread, unread
    assert "Not a measured zero" in unread
    assert "No page loads counted yet" not in unread

    # The same state, rendered in Hindi rather than merely present in the dict.
    hindi = _html.unescape(_viewport_card(_system(monkeypatch, "hi", rows=None,
                                                  answering=True)))
    assert i18n.HI["ui"]["sys_empty_viewport_no_index"] in hindi
    assert "Not a measured zero" not in hindi


def test_counted_bands_prove_the_index_answered(monkeypatch):
    """Rows on the page are proof the index answered, whatever the ping said --
    the rule every other panel on this view already follows. Dropping vp_rows
    from the has_index expression would print "none is answering" above three
    bars drawn from that very index."""
    body = _system(monkeypatch, "en", rows=BANDS_STUB, answering=False)
    card = _viewport_card(body)
    assert card.count('class="sysbar"') == 3, card
    assert "nothing is being recorded" not in body


def test_the_bars_carry_their_geometry_as_a_step_class(monkeypatch):
    """Geometry cannot ride a style attribute under style-src 'self', so the
    width arrives as a pN class. Dropping {{ pos(r.w) }} renders three
    zero-width bars and every other assertion here still passes."""
    card = _viewport_card(_system(monkeypatch, "en"))
    # 12 and 4 of a 12 max, and a measured zero.
    assert re.findall(r'class="fill (p\d+)"', card) == ["p100", "p0", "p33"], card


def test_a_band_the_route_cannot_write_is_not_rendered(monkeypatch):
    """The route validates against VIEWPORT_BANDS, so a stray key can only be
    residue from another writer. It must not become a row."""
    assert web_main._viewport_rows([{"band": "desktop", "count": 5}]) == []
    # Partner: the same call with a real band does produce a row.
    rows = web_main._viewport_rows([{"band": "wide", "count": 5}])
    assert [r["v"] for r in rows] == [0, 0, 5]


def test_the_viewport_rows_are_ordered_by_width_not_by_count(monkeypatch):
    """The list is a scale, so it reads narrow to wide. Sorting by count would
    reorder the axis every time traffic changed."""
    card = _viewport_card(_system(monkeypatch, "en"))
    assert re.findall(r"(0–560px|561–899px|900px\+)", card) == [
        "0–560px", "561–899px", "900px+"]


def test_the_rendered_band_labels_match_the_stylesheets_breakpoints(monkeypatch):
    """Gate 1c and Gate 2 both touch app.css. Moving a breakpoint without
    moving the constant would leave the System view stating a number the
    layout no longer uses, in two languages, with the suite green."""
    css = CSS_PATH.read_text()
    widths = [int(n) for n in re.findall(r"@media \((?:max|min)-width: (\d+)px\)", css)]
    assert sorted(widths) == sorted(web_main.VIEWPORT_BREAKPOINTS), widths

    card = _viewport_card(_system(monkeypatch, "en"))
    labels = re.findall(r"<span class=\"l\">([^<]+)</span>", card)
    narrow, wide = web_main.VIEWPORT_BREAKPOINTS
    assert labels == [f"0–{narrow}px", f"{narrow + 1}–{wide - 1}px", f"{wide}px+"], labels


# --- what the site says it records -----------------------------------------
def test_the_site_names_the_width_band_among_what_it_records(monkeypatch):
    """The footer and the Guide are this site's account of what is written
    down. A new stored value that appears in neither makes both incomplete on
    every page, which is the defect this project already caught itself in once
    with the persona claim.

    Appended, never rephrased: tests/test_privacy.py pins a substring of each
    of these two sentences.
    """
    import html as _html
    from saafsaans.services import i18n

    with TestClient(app) as client:
        english = _html.unescape(client.get("/", params={"lang": "en"}).text)
        english_guide = _html.unescape(client.get("/guide", params={"lang": "en"}).text)
        hindi = _html.unescape(client.get("/", params={"lang": "hi"}).text)
        hindi_guide = _html.unescape(client.get("/guide", params={"lang": "hi"}).text)

    assert "width band your browser reports" in english
    assert "width band your browser reports" in english_guide
    assert i18n.HI["ui"]["footer"] in hindi
    assert i18n.HI["guide"]["a_privacy"] in hindi_guide
    for hindi_text in (i18n.HI["ui"]["footer"], i18n.HI["guide"]["a_privacy"]):
        assert "चौड़ाई" in hindi_text, hindi_text

    # The partner: the sentences the privacy suite pins are still there, so
    # this test cannot pass by having replaced them.
    assert "hashed session id and the area you picked" in english
    assert "the one part of your persona that is stored deliberately" in english_guide


def test_every_character_in_a_band_label_exists_in_the_shipped_faces():
    """The proof register is defined by its mono face, so a character the
    subsetted woff2 does not carry is drawn by whatever the operating system
    substitutes -- different metrics, different weight, in the one place on the
    site that is meant to read as an instrument.

    This caught a real defect: the labels were first written with ≤ and ≥,
    which are in NONE of the six shipped faces and outside the unicode-range
    fonts.css declares.
    """
    from fontTools.ttLib import TTFont

    faces = sorted((Path(web_main.__file__).parent / "static" / "fonts").glob("*.woff2"))
    assert faces, "no shipped faces found -- this test would prove nothing"
    latin = [f for f in faces if "devanagari.woff2" not in f.name]
    assert latin, "no Latin-carrying face found"

    labels = "".join(_band_label_all())
    wanted = {ord(ch) for ch in labels if not ch.isspace()}
    assert wanted, "no characters to check"
    for face in latin:
        cmap = TTFont(face).getBestCmap()
        missing = sorted(f"U+{cp:04X} {chr(cp)}" for cp in wanted if cp not in cmap)
        assert not missing, (face.name, missing)


def _band_label_all():
    return [web_main._band_label(band) for band in web_main.VIEWPORT_BANDS]


def test_a_flood_of_page_loads_cannot_forgive_the_ask_limiter(recorder, monkeypatch):
    """The limiter's overflow path clears its whole table, and that table used
    to be shared. `/ask` inserts a bucket only when somebody posts a question,
    so reaching the cap was unreachable; the probe inserts one per address per
    page load, so a crawl can now fill it. If the two shared a table, the reset
    would drop the `ask:` counters that guard model spend, mid-window."""
    monkeypatch.setattr(ratelimit, "_MAX_BUCKETS", 4)
    ratelimit.reset()
    ratelimit.check("ask:1.2.3.4", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    assert "ask:1.2.3.4" in ratelimit._BUCKETS

    with TestClient(app) as client:
        for n in range(30):
            client.get("/probe/mid.gif", headers={"X-Forwarded-For": f"10.0.0.{n}"})

    # The probe table absorbed its own flood and was reset; the ask counter did
    # not move. The partner: the flood really did happen.
    assert len(ratelimit._PROBE_BUCKETS) < 30
    assert "ask:1.2.3.4" in ratelimit._BUCKETS, "a page-load flood wiped the ask limiter"


def test_the_probe_does_not_spend_the_readers_question_budget(recorder):
    """Same address, both endpoints: the buckets are namespaced, so page loads
    cannot throttle a reader off the Q&A."""
    ratelimit.reset()
    with TestClient(app) as client:
        for _ in range(5):
            client.get("/probe/wide.gif", headers={"X-Forwarded-For": "9.9.9.9"})
    assert not any(k.startswith("ask:") for k in ratelimit._PROBE_BUCKETS), \
        ratelimit._PROBE_BUCKETS
    assert ratelimit._BUCKETS == {}, ratelimit._BUCKETS


def test_the_caveat_calls_the_number_a_floor(monkeypatch):
    """Two source files argue that a silent under-count is acceptable BECAUSE
    the page discloses it. That argument is only sound while the page does."""
    import html as _html
    from saafsaans.services import i18n

    english = _html.unescape(_viewport_card(_system(monkeypatch, "en")))
    assert "a floor, never a total" in english, english
    # The mechanism only counts a client that fetches the stylesheet's image,
    # so most automated visitors are MISSING, not over-represented. An earlier
    # draft said the opposite.
    assert "automated visitors are missing" in english
    assert "back button" in english

    hindi = _html.unescape(_viewport_card(_system(monkeypatch, "hi")))
    assert i18n.HI["ui"]["sys_viewport_caveat"] in hindi
    assert "कम से कम की गिनती" in hindi


def test_the_base_probe_rule_sits_above_the_width_blocks():
    """All three rules are `body::after`, so they have identical specificity and
    SOURCE ORDER alone decides which wins. Move the base rule below the 560px
    block and every phone reports `mid` instead of `narrow` -- the counts
    silently invert, the stylesheet still declares three distinct bands in three
    distinct contexts, and every other test in this file stays green.

    app.css says "This one must stay ABOVE the 560px block" and, until this
    test, nothing that runs without a browser enforced it.
    """
    css = CSS_PATH.read_text()
    base = css.index('url("/probe/mid.gif")')
    narrow_block = css.index(f"@media (max-width: {web_main.VIEWPORT_BREAKPOINTS[0]}px)")
    wide_block = css.index(f"@media (min-width: {web_main.VIEWPORT_BREAKPOINTS[1]}px)")

    assert base < narrow_block, (
        "the base body::after rule is declared after the narrow media block, so "
        "it overrides it and every narrow viewport reports the middle band")
    assert base < wide_block, (
        "the base body::after rule is declared after the wide media block")
    # Partner: the two blocks really are where this test thinks they are, and
    # each really does re-point the probe.
    assert css.index('url("/probe/narrow.gif")') > narrow_block
    assert css.index('url("/probe/wide.gif")') > wide_block


def test_the_viewport_index_is_created_with_a_keyword_mapping():
    """metrics.viewport_bands retries on band.keyword so a deployment nobody
    re-seeded still reads, but the shape that is MEANT is a keyword field. If
    the mapping is dropped, the retry papers over it and nothing else notices."""
    from saafsaans.setup_indices import MAPPINGS

    assert es.INDEX_VIEWPORT in MAPPINGS, "the probe's index is never created"
    properties = MAPPINGS[es.INDEX_VIEWPORT]["mappings"]["properties"]
    assert properties["band"]["type"] == "keyword", properties
    assert set(properties) == es.VIEWPORT_FIELDS, (
        "the mapping and the write allowlist disagree about the document")
