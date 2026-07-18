"""ES mode detection, none-mode no-ops, connected search + retry/fallback."""
import pytest

from saafsaans.services import es, config


def test_mode_detection(monkeypatch):
    monkeypatch.setattr(config, "_clean", lambda name: {
        "ELASTIC_API_KEY": "k", "ELASTIC_CLOUD_ID": "cid"}.get(name, ""))
    assert config.es_mode() == "cloud"

    monkeypatch.setattr(config, "_clean", lambda name: {
        "ELASTIC_API_KEY": "k", "ELASTIC_URL": "https://x"}.get(name, ""))
    assert config.es_mode() == "url"

    # URL without api key -> none (no half-connect)
    monkeypatch.setattr(config, "_clean", lambda name: {
        "ELASTIC_URL": "https://x"}.get(name, ""))
    assert config.es_mode() == "none"

    monkeypatch.setattr(config, "_clean", lambda name: "")
    assert config.es_mode() == "none"


def test_none_mode_logging_is_noop():
    # No client -> these must simply return without raising.
    es.index_reading(None, {"aqi": 1})
    es.log_telemetry(None, {"event": "x"})
    es.log_security(None, {"event_type": "y"})


class FakeESClient:
    def __init__(self, responses):
        # responses: list of dicts returned by successive .search calls
        self._responses = list(responses)
        self.search_calls = []
        self.indexed = []

    def search(self, index, **body):
        self.search_calls.append(body)
        return self._responses.pop(0)

    def index(self, index, document):
        self.indexed.append((index, document))


def _hits(sources):
    return {"hits": {"hits": [{"_source": s} for s in sources]}}


def test_connected_search_returns_hits():
    client = FakeESClient([_hits([{"advice": "a", "condition": "asthma",
                                   "aqi_min": 201, "aqi_max": 300}])])
    docs = es.search_advisories(250, "asthma", "any", "any", client=client)
    assert docs[0]["advice"] == "a"
    assert len(client.search_calls) == 1


def test_zero_hits_triggers_filter_only_retry():
    client = FakeESClient([_hits([]), _hits([{"advice": "b"}])])
    docs = es.search_advisories(250, "asthma", "any", "any", client=client)
    assert docs[0]["advice"] == "b"
    assert len(client.search_calls) == 2
    assert "should" not in client.search_calls[1]["query"]["bool"]


def test_double_zero_falls_back_in_process():
    client = FakeESClient([_hits([]), _hits([])])
    docs = es.search_advisories(250, "asthma", "any", "any", client=client)
    assert len(docs) >= 1  # in-process seed fallback


def test_search_exception_falls_back():
    class Boom:
        def search(self, *a, **k):
            raise RuntimeError("es down")

    docs = es.search_advisories(250, "asthma", "any", "any", client=Boom())
    assert len(docs) >= 1  # never propagates, always returns content


def test_log_swallows_client_exception():
    class Boom:
        def index(self, *a, **k):
            raise RuntimeError("es down")

    # Must not raise.
    es.log_telemetry(Boom(), {"event": "x", "session_hash": "h"})
    es.log_security(Boom(), {"event_type": "y", "session_hash": "h"})
