"""The two endpoints that do work on demand are unauthenticated by design.

`POST /ask` writes telemetry, may write a security event, and calls a paid
model when a key is configured. `POST /system/simulate` writes a document per
attack in the demo set. Neither asks who you are -- requiring registration
before someone may ask whether the air is safe would defeat the app -- so a
limit is the only thing between one loop and unbounded writes on a single
256 MB machine.
"""
import pytest
from fastapi.testclient import TestClient

from saafsaans.services import ratelimit
from saafsaans.web.main import app

PERSONA = {"locality": "Anand Vihar", "age": "Adult",
           "condition": "Asthma", "activity": "Outdoor exercise"}


def test_a_reader_asking_normally_is_never_throttled():
    """The limit exists to stop a loop, not to ration a person. Ten questions
    in a sitting is a curious reader, not an attack."""
    with TestClient(app) as client:
        for i in range(10):
            client.post("/ask", params=PERSONA, data={"question": f"Is it safe? {i}"})
        body = client.get("/", params=PERSONA).text
    assert "Too many questions" not in body


def test_a_loop_is_stopped_and_told_when_to_come_back():
    with TestClient(app) as client:
        for i in range(ratelimit.ASK_LIMIT + 3):
            client.post("/ask", params=PERSONA, data={"question": f"q{i}"})
        body = client.get("/", params=PERSONA).text
    assert "Too many questions" in body
    assert "try again in about" in body


def test_the_throttle_is_explained_in_hindi_too():
    with TestClient(app) as client:
        for i in range(ratelimit.ASK_LIMIT + 3):
            client.post("/ask", params={**PERSONA, "lang": "hi"},
                        data={"question": f"q{i}"})
        body = client.get("/", params={**PERSONA, "lang": "hi"}).text
    assert "अभी बहुत सारे सवाल आ गए।" in body
    assert "Too many questions" not in body


def test_a_throttled_question_reaches_neither_the_model_nor_any_index(monkeypatch):
    """The whole point: the work must not happen. A limiter that refuses AFTER
    calling the model has spent the money it exists to save."""
    from saafsaans.web import main as web_main

    calls = {"telemetry": 0, "security": 0}
    monkeypatch.setattr(web_main.es, "log_telemetry",
                        lambda c, d: calls.__setitem__("telemetry", calls["telemetry"] + 1))
    monkeypatch.setattr(web_main.es, "log_security",
                        lambda c, d: calls.__setitem__("security", calls["security"] + 1))

    with TestClient(app) as client:
        for i in range(ratelimit.ASK_LIMIT):
            client.post("/ask", params=PERSONA, data={"question": f"q{i}"})
        before = calls["telemetry"]
        for i in range(5):
            client.post("/ask", params=PERSONA, data={"question": f"over{i}"})

    assert calls["telemetry"] == before, (
        "a throttled question still wrote telemetry, so the limiter is not "
        "saving the work it exists to save")


def test_a_rate_limit_trip_is_not_logged_as_a_security_event(monkeypatch):
    """Writing one security event per blocked request hands the flooder the
    very index the limit protects, and a rate-limit trip is not an attack."""
    from saafsaans.web import main as web_main
    events = []
    monkeypatch.setattr(web_main.es, "log_security", lambda c, d: events.append(d))

    with TestClient(app) as client:
        for i in range(ratelimit.ASK_LIMIT + 5):
            client.post("/ask", params=PERSONA, data={"question": f"q{i}"})

    assert not [e for e in events if "rate" in str(e).lower()], events


def test_the_simulate_endpoint_is_limited_harder_than_ask():
    """Nobody needs the red-team demo twenty times in five minutes, and it
    writes a document per attack every time it runs.

    Asserted on the redirect TARGET, not the status code: both branches return
    303, so a status assertion here held whether or not the limiter existed.
    Only the allowed path carries sim=1, which is what tells the Security view
    a run just happened.
    """
    assert ratelimit.SIMULATE_LIMIT < ratelimit.ASK_LIMIT
    with TestClient(app) as client:
        targets = [client.post("/system/simulate", params=PERSONA,
                               follow_redirects=False).headers["location"]
                   for _ in range(ratelimit.SIMULATE_LIMIT + 2)]

    ran = [t for t in targets if "sim=1" in t]
    refused = [t for t in targets if "sim=1" not in t]
    assert len(ran) == ratelimit.SIMULATE_LIMIT, (
        f"{len(ran)} runs allowed, limit is {ratelimit.SIMULATE_LIMIT}")
    assert len(refused) == 2, targets


# --- the limiter itself ----------------------------------------------------
def test_each_caller_gets_their_own_budget():
    """Keyed per client. One heavy user must not lock everyone else out --
    which, on a shared limit, is a denial of service anyone can perform."""
    for _ in range(ratelimit.ASK_LIMIT + 1):
        ratelimit.check("ask:1.1.1.1", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    blocked, _ = ratelimit.check("ask:1.1.1.1", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    allowed, _ = ratelimit.check("ask:2.2.2.2", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    assert blocked is False
    assert allowed is True


def test_the_window_reopens():
    """A limiter that never forgets is a ban."""
    for _ in range(ratelimit.ASK_LIMIT + 1):
        ratelimit.check("ask:3.3.3.3", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    assert ratelimit.check("ask:3.3.3.3", ratelimit.ASK_LIMIT,
                           ratelimit.ASK_WINDOW)[0] is False
    with ratelimit._LOCK:
        start, count = ratelimit._BUCKETS["ask:3.3.3.3"]
        ratelimit._BUCKETS["ask:3.3.3.3"] = (start - ratelimit.ASK_WINDOW - 1, count)
    assert ratelimit.check("ask:3.3.3.3", ratelimit.ASK_LIMIT,
                           ratelimit.ASK_WINDOW)[0] is True


def test_the_bucket_table_cannot_grow_without_bound():
    """X-Forwarded-For is attacker-controlled, so a bucket per distinct value
    is a memory leak reachable from the internet, on a 256 MB machine."""
    for i in range(ratelimit._MAX_BUCKETS + 500):
        ratelimit.check(f"ask:10.0.{i // 256}.{i % 256}", 100, 300)
    assert len(ratelimit._BUCKETS) <= ratelimit._MAX_BUCKETS


@pytest.mark.parametrize("headers,expected", [
    ({"x-forwarded-for": "203.0.113.7"}, "203.0.113.7"),
    # A forged prefix must be ignored: Fly APPENDS the connecting address, so
    # only the last entry is the proxy's own and everything before it is
    # whatever the client chose to send.
    ({"x-forwarded-for": "1.2.3.4, 203.0.113.7"}, "203.0.113.7"),
    ({"x-forwarded-for": "evil, 10.0.0.1, 203.0.113.7"}, "203.0.113.7"),
    ({"x-forwarded-for": "  203.0.113.7  "}, "203.0.113.7"),
])
def test_the_key_is_the_hop_the_proxy_wrote_not_the_one_the_client_sent(headers, expected):
    """Fly terminates TLS at its proxy, so request.client.host is that proxy
    for every visitor alike and keying on it would throttle the whole internet
    as one. The header must be read -- but only its LAST entry is written by
    the proxy.

    The first draft read entry [0], the one value an attacker fully controls.
    See the next test for what that cost."""
    class _Req:
        def __init__(self, h):
            self.headers = h
            self.client = type("C", (), {"host": "127.0.0.1"})()

    assert ratelimit.client_key(_Req(headers)) == expected


def test_a_forged_forwarded_header_cannot_buy_a_fresh_bucket():
    """The bypass this limiter shipped with for one commit. A client sending a
    different X-Forwarded-For each time arrives at the proxy as
    "<whatever they sent>, <their real ip>"; keying on the first entry put them
    in a new bucket every request, so they were never limited -- while filling
    the bucket table, which is the leak the bound exists for. The limiter was
    decorative against precisely the caller it is for."""
    class _Req:
        def __init__(self, forged):
            self.headers = {"x-forwarded-for": f"{forged}, 203.0.113.99"}
            self.client = type("C", (), {"host": "127.0.0.1"})()

    keys = {ratelimit.client_key(_Req(f"10.9.9.{i}")) for i in range(50)}
    assert keys == {"203.0.113.99"}, (
        f"a rotating forged header produced {len(keys)} distinct buckets")

    allowed_after_limit = None
    for i in range(ratelimit.ASK_LIMIT + 5):
        key = ratelimit.client_key(_Req(f"172.16.0.{i}"))
        allowed_after_limit, _ = ratelimit.check(
            f"ask:{key}", ratelimit.ASK_LIMIT, ratelimit.ASK_WINDOW)
    assert allowed_after_limit is False, (
        "a caller rotating X-Forwarded-For evaded the limit entirely")


def test_a_caller_with_no_forwarded_header_still_gets_a_key():
    class _Req:
        headers = {}
        client = type("C", (), {"host": "198.51.100.4"})()

    assert ratelimit.client_key(_Req()) == "198.51.100.4"
