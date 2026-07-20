"""Privacy invariants: no raw persona leaves the process into any index."""
import uuid

import pytest

from saafsaans.services import es, normalize


@pytest.fixture
def empty_store():
    from saafsaans.web import main as web_main
    web_main._TRANSCRIPTS.clear()
    yield web_main._TRANSCRIPTS
    web_main._TRANSCRIPTS.clear()


def test_session_hash_len_and_determinism():
    h1 = normalize.session_hash("abc-123")
    h2 = normalize.session_hash("abc-123")
    assert h1 == h2
    assert len(h1) == 12
    assert h1 != "abc-123"


def test_excerpt_cap():
    assert len(normalize.excerpt("x" * 500)) == 120
    assert normalize.excerpt("short") == "short"


def test_sanitize_error_redacts_token():
    err = Exception("GET https://api.waqi.info/feed/delhi/?token=SECRET123 failed")
    out = normalize.sanitize_error(err)
    assert "SECRET123" not in out
    assert "REDACTED" in out
    assert out.startswith("Exception")


def test_reading_index_drops_persona():
    """index_reading must only ever forward pollutant fields."""
    captured = {}

    class FakeClient:
        def index(self, index, document):
            captured["index"] = index
            captured["doc"] = document

    tainted = {"aqi": 250, "pm25": 180.0, "pm10": 300.0,
               "dominant_pollutant": "pm25", "station": "S", "city": "Delhi",
               "condition": "asthma", "age_group": "senior"}  # persona MUST be dropped
    es.index_reading(FakeClient(), tainted)
    assert set(captured["doc"].keys()) <= es.READING_FIELDS
    assert "condition" not in captured["doc"]
    assert "age_group" not in captured["doc"]


def test_telemetry_drops_stray_persona():
    captured = {}

    class FakeClient:
        def index(self, index, document):
            captured["doc"] = document

    es.log_telemetry(FakeClient(), {
        "@timestamp": "t", "session_hash": "abc", "event": "chat_completed",
        "locality": "ITO", "aqi_value": 250,
        "condition": "asthma", "age": "Senior",  # must be stripped
    })
    assert "condition" not in captured["doc"]
    assert "age" not in captured["doc"]
    assert set(captured["doc"].keys()) <= es.TELEMETRY_FIELDS


def test_security_excerpt_within_index_path():
    captured = {}

    class FakeClient:
        def index(self, index, document):
            captured["doc"] = document

    es.log_security(FakeClient(), {
        "@timestamp": "t", "session_hash": "abc", "event_type": "prompt_injection",
        "pattern_matched": "jailbreak", "prompt_excerpt": normalize.excerpt("j" * 400),
        "action_taken": "blocked",
    })
    assert len(captured["doc"]["prompt_excerpt"]) == 120
    assert set(captured["doc"].keys()) <= es.SECURITY_FIELDS


def test_no_page_repeats_the_false_never_logged_claim():
    """The README's version of this claim was the worst defect this project
    found in itself: it said the persona is never written to any index while
    locality was written on every request. The footer and the Guide were still
    saying it after the README was corrected. Any surface making a blanket
    "never logged" promise about the persona is making a false one."""
    from fastapi.testclient import TestClient
    from saafsaans.web.main import app
    with TestClient(app) as client:
        for path in ("/", "/guide", "/city", "/system"):
            flat = " ".join(client.get(path).text.replace("&#39;", "'").split())
            assert "Persona stays in session — never logged" not in flat, path
            assert "persona stays in the page address and your session — it is never" \
                not in flat.lower(), path


def test_the_transcript_store_forgets_the_oldest_questions(empty_store, monkeypatch):
    """The store holds raw user questions in process memory. Capping the turns
    per session bounds how long any one question is retained."""
    from fastapi.testclient import TestClient
    from saafsaans.web import main as web_main

    monkeypatch.setattr(web_main, "MAX_TURNS_PER_SESSION", 2)
    with TestClient(web_main.app) as client:
        for q in ("Question about my first child?", "Second?", "Third?"):
            client.post("/ask", data={"question": q})
    held = [t["question"] for store in empty_store.values() for t in store["turns"]]
    assert len(held) == 2
    assert "Question about my first child?" not in held


def test_the_transcript_store_forgets_the_least_recently_used_session(empty_store,
                                                                     monkeypatch):
    """Sessions are capped too, so questions do not accumulate for the life of
    the process one abandoned session at a time."""
    from saafsaans.web import main as web_main

    monkeypatch.setattr(web_main, "MAX_SESSIONS", 3)
    for n in range(4):
        web_main.add_turn(f"sid-{n}", {"question": f"q{n}"})
    assert len(empty_store) == 3
    assert "sid-0" not in empty_store          # least recently used, evicted


def test_reading_a_session_does_not_create_one(empty_store):
    """Otherwise any request with a stale or forged cookie grows the store."""
    from saafsaans.web import main as web_main
    assert web_main.read_turns("never-seen") == []
    assert len(empty_store) == 0


def test_a_client_chosen_session_key_is_never_used(empty_store):
    """`sid` is client-controlled. Anything that is not a canonical uuid4 --
    the only form this server issues -- is replaced, so a caller cannot pick
    the key its questions are filed under, nor read someone else's by naming
    it. This does NOT defend against a stolen or guessed real uuid4."""
    from fastapi.testclient import TestClient
    from saafsaans.web import main as web_main

    for forged in ("admin", "../etc", "x" * 5000, "{%s}" % uuid.uuid4(),
                   "urn:uuid:%s" % uuid.uuid4(), str(uuid.uuid4()).upper(),
                   str(uuid.uuid1())):
        with TestClient(web_main.app, cookies={"sid": forged}) as client:
            client.post("/ask", data={"question": "Is it safe outside?"})
        assert forged not in empty_store
    for key in empty_store:
        assert uuid.UUID(key).version == 4 and str(uuid.UUID(key)) == key


def test_a_real_session_id_still_carries_the_transcript(empty_store):
    """The uuid check must not break continuity for a legitimate cookie."""
    from fastapi.testclient import TestClient
    from saafsaans.web import main as web_main

    sid = str(uuid.uuid4())
    with TestClient(web_main.app, cookies={"sid": sid}) as client:
        client.post("/ask", data={"question": "Should I cycle today?"})
        assert "Should I cycle today?" in client.get("/").text
    assert sid in empty_store


def test_the_pages_name_locality_as_the_logged_exception():
    from fastapi.testclient import TestClient
    from saafsaans.web.main import app
    with TestClient(app) as client:
        footer = " ".join(client.get("/").text.replace("&#39;", "'").split())
        assert "hashed session id and the area you picked" in footer
        guide = " ".join(client.get("/guide").text.replace("&#39;", "'").split())
        assert "is the one exception and is stored deliberately" in guide
