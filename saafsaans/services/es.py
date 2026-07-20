"""Elasticsearch client, index setup, advisory search, and logging.

Dual-mode + mock-first:
  * ``cloud`` — Elasticsearch(cloud_id=..., api_key=...)
  * ``url``   — Elasticsearch(hosts=[url], api_key=...)
  * ``none``  — no client; searches run in-process over the seed advisories,
                and every index/log call is a silent no-op.

Every write helper swallows exceptions: logging and indexing must never crash
a chat turn. Search never returns empty while the corpus is non-empty, and
degrades to in-process ranking on any ES error.

Retrieval is ranked, not merely filtered by AQI band: an advisory written for a
different persona is excluded rather than returned with a score of zero. See
``rank_advisories``.
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
# Tag on a *returned* advisory saying why it was chosen. Never stored in
# data/advisories.py, never indexed, and not part of the five-field i18n key.
RELEVANCE_PERSONA = "persona"
RELEVANCE_GENERAL = "general"
# ES is asked for more rows than the caller wants because the persona filter
# runs after retrieval: a page of 4 band-matching hits can contain 0 that apply.
FETCH_K = 25


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


def applies_to(advisory: dict, condition: str, activity: str, age_group: str) -> bool:
    """True when every persona field of ``advisory`` fits this reader.

    A field matches when the advisory's value is ``"any"`` or equals the
    reader's. A reader value of ``"any"`` therefore matches only advisories
    whose field is ``"any"``: an unstated condition does not entitle the reader
    to asthma advice, and scoring a mismatch zero is not the same as excluding
    it. Missing keys default to ``"any"`` because ES documents are external
    data and may be shaped by whatever last seeded the index.
    """
    return all(advisory.get(field, "any") in ("any", value)
               for field, value in (("condition", condition),
                                    ("activity", activity),
                                    ("age_group", age_group)))


def specificity(advisory: dict, condition: str, activity: str, age_group: str) -> int:
    """0-3: how many of the advisory's non-``"any"`` fields name this persona."""
    return sum(1 for field, value in (("condition", condition),
                                      ("activity", activity),
                                      ("age_group", age_group))
               if advisory.get(field, "any") == value != "any")


def _band_distance(advisory: dict, aqi: int) -> int:
    low = advisory.get("aqi_min", 0)
    high = advisory.get("aqi_max", 999)
    if aqi < low:
        return low - aqi
    if aqi > high:
        return aqi - high
    return 0


def rank_advisories(docs: list, aqi: int, condition: str, activity: str,
                    age_group: str, k: int) -> list:
    """Up to ``k`` of ``docs``, applicable to this persona and tagged.

    Never returns empty for a non-empty input: if nothing applies to the
    persona the input is used unchanged, and if nothing sits in the AQI band the
    nearest band is used. That is the only empty-fallback rule in this module,
    so callers need no second one.

    Returns new dicts carrying ``relevance``. The input is never mutated:
    ``ADVISORIES`` is a module constant and a stray key on it would be indexed.
    """
    candidates = [d for d in docs if applies_to(d, condition, activity, age_group)]
    if not candidates:
        candidates = docs

    nearest = min((_band_distance(d, aqi) for d in candidates), default=0)
    in_band = [d for d in candidates if _band_distance(d, aqi) == nearest]

    ranked = sorted(in_band,
                    key=lambda d: specificity(d, condition, activity, age_group),
                    reverse=True)[:k]
    return [dict(d, relevance=(RELEVANCE_PERSONA
                               if specificity(d, condition, activity, age_group)
                               else RELEVANCE_GENERAL))
            for d in ranked]


def _in_process_search(aqi, condition, activity, age_group, k):
    """Rank the seed advisories in pure Python (no ES)."""
    return rank_advisories(ADVISORIES, aqi, condition, activity, age_group, k)


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
                             **build_query(aqi, condition, activity, age_group,
                                           FETCH_K, with_should=True))
        docs = _hits_to_docs(resp)
        if not docs:
            resp = client.search(index=INDEX_ADVISORIES,
                                 **build_query(aqi, condition, activity, age_group,
                                               FETCH_K, with_should=False))
            docs = _hits_to_docs(resp)
        if not docs:
            return _in_process_search(aqi, condition, activity, age_group, k)
        # rank_advisories never returns empty for a non-empty input, so zero
        # hits above is the only empty case and it is already handled.
        return rank_advisories(docs, aqi, condition, activity, age_group, k)
    except Exception:
        return _in_process_search(aqi, condition, activity, age_group, k)
