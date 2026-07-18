"""Elasticsearch client, index setup, advisory search, and logging.

Dual-mode + mock-first:
  * ``cloud`` — Elasticsearch(cloud_id=..., api_key=...)
  * ``url``   — Elasticsearch(hosts=[url], api_key=...)
  * ``none``  — no client; searches run in-process over the seed advisories,
                and every index/log call is a silent no-op.

Every write helper swallows exceptions: logging and indexing must never crash
a chat turn. Search always returns at least one advisory when any seed matches
the AQI band, and degrades to in-process filtering on any ES error.
"""
from datetime import datetime, timezone

from . import config
from ..data.advisories import ADVISORIES

INDEX_ADVISORIES = "health-advisories"
INDEX_READINGS = "aqi-readings"
INDEX_TELEMETRY = "app-telemetry"
INDEX_SECURITY = "security-events"

# Field sets a document is allowed to contain. Used as a privacy backstop so a
# stray persona value can never be written to an index.
READING_FIELDS = {"@timestamp", "station", "city", "aqi", "pm25", "pm10", "dominant_pollutant"}
# ``user_hash`` is the OPTIONAL salted hash of a signed-in identity — never the
# raw email/phone. It is the only identity value permitted into an index.
TELEMETRY_FIELDS = {"@timestamp", "session_hash", "event", "latency_ms", "waqi_status",
                    "llm_status", "llm_tokens", "error", "aqi_value", "locality",
                    "user_hash"}
SECURITY_FIELDS = {"@timestamp", "session_hash", "event_type", "pattern_matched",
                   "prompt_excerpt", "action_taken", "user_hash"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_client():
    """Build an Elasticsearch client for the detected mode, or None.

    Returns None in ``none`` mode or if the client cannot be constructed, so
    callers transparently fall back to mock behaviour.
    """
    mode = config.es_mode()
    if mode == "none":
        return None
    try:
        from elasticsearch import Elasticsearch
        if mode == "cloud":
            return Elasticsearch(cloud_id=config.elastic_cloud_id(),
                                 api_key=config.elastic_api_key(),
                                 request_timeout=10)
        return Elasticsearch(hosts=[config.elastic_url()],
                             api_key=config.elastic_api_key(),
                             request_timeout=10)
    except Exception:
        return None


# --- Indexing / logging (fire-and-forget) ---------------------------------
def _safe_index(client, index: str, doc: dict, allowed: set):
    """Index ``doc`` keeping only allowed fields. Never raises."""
    if client is None:
        return
    try:
        clean = {k: v for k, v in doc.items() if k in allowed}
        client.index(index=index, document=clean)
    except Exception:
        # Logging/indexing must never break the app.
        pass


def index_reading(client, reading: dict) -> None:
    doc = {
        "@timestamp": now_iso(),
        "station": reading.get("station"),
        "city": reading.get("city"),
        "aqi": reading.get("aqi"),
        "pm25": reading.get("pm25"),
        "pm10": reading.get("pm10"),
        "dominant_pollutant": reading.get("dominant_pollutant"),
    }
    _safe_index(client, INDEX_READINGS, doc, READING_FIELDS)


def log_telemetry(client, doc: dict) -> None:
    _safe_index(client, INDEX_TELEMETRY, doc, TELEMETRY_FIELDS)


def log_security(client, doc: dict) -> None:
    _safe_index(client, INDEX_SECURITY, doc, SECURITY_FIELDS)


# --- Advisory search ------------------------------------------------------
def build_query(aqi: int, condition: str, activity: str, age_group: str, k: int, with_should: bool):
    """Build the bool query. ``with_should=False`` is the filter-only retry."""
    query = {
        "bool": {
            "filter": [
                {"range": {"aqi_min": {"lte": aqi}}},
                {"range": {"aqi_max": {"gte": aqi}}},
            ]
        }
    }
    if with_should:
        # Only boost on specific persona values; "any" would over-boost generic
        # advisories and diverge from the in-process scoring.
        should = []
        if condition != "any":
            should.append({"term": {"condition": condition}})
        if activity != "any":
            should.append({"term": {"activity": activity}})
        if age_group != "any":
            should.append({"term": {"age_group": age_group}})
        if should:
            query["bool"]["should"] = should
            query["bool"]["minimum_should_match"] = 0
    return {"query": query, "size": k}


def _in_process_search(aqi, condition, activity, age_group, k):
    """Filter + score the seed advisories in pure Python (no ES).

    Score = number of persona keyword matches (condition/activity/age).
    Guarantees a non-empty result: if nothing sits in the AQI band, returns the
    advisories whose band is nearest to ``aqi``.
    """
    def score(a):
        s = 0
        if condition != "any" and a["condition"] == condition:
            s += 1
        if activity != "any" and a["activity"] == activity:
            s += 1
        if age_group != "any" and a["age_group"] == age_group:
            s += 1
        return s

    in_band = [a for a in ADVISORIES if a["aqi_min"] <= aqi <= a["aqi_max"]]
    if in_band:
        in_band.sort(key=score, reverse=True)
        return in_band[:k]

    # Nearest-band fallback so the UI always has content.
    def distance(a):
        if aqi < a["aqi_min"]:
            return a["aqi_min"] - aqi
        if aqi > a["aqi_max"]:
            return aqi - a["aqi_max"]
        return 0

    nearest = sorted(ADVISORIES, key=distance)
    return nearest[:k]


def _hits_to_docs(resp):
    return [h["_source"] for h in resp.get("hits", {}).get("hits", [])]


def search_advisories(aqi: int, condition: str, activity: str, age_group: str, k: int = 4,
                      client="__auto__"):
    """Return up to ``k`` advisories most relevant to persona + AQI.

    Always returns a non-empty list when any advisory can apply. Uses ES when a
    client is available, else (or on any ES error) an in-process search.
    """
    if client == "__auto__":
        client = get_client()
    if client is None:
        return _in_process_search(aqi, condition, activity, age_group, k)
    try:
        resp = client.search(index=INDEX_ADVISORIES,
                             **build_query(aqi, condition, activity, age_group, k, with_should=True))
        docs = _hits_to_docs(resp)
        if not docs:
            resp = client.search(index=INDEX_ADVISORIES,
                                 **build_query(aqi, condition, activity, age_group, k, with_should=False))
            docs = _hits_to_docs(resp)
        if not docs:
            return _in_process_search(aqi, condition, activity, age_group, k)
        return docs
    except Exception:
        return _in_process_search(aqi, condition, activity, age_group, k)
