"""Privacy invariants: no raw persona leaves the process into any index."""
from saafsaans.services import es, normalize


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
