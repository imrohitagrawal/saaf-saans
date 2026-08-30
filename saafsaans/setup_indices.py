"""One-shot: create the four indices (if missing) and seed advisories.

Run: ``python setup_indices.py`` (or ``python saafsaans/setup_indices.py``).
Idempotent — existing indices are left in place. Requires Elastic credentials;
without them it prints guidance and exits cleanly (the app itself still runs
in mock mode).

Idempotent is not the same as authoritative. Advisory ids are derived from the
advisory itself, so re-running overwrites a changed row and adds a new one, but
nothing here deletes a row that has LEFT the corpus. A connected deployment
therefore keeps serving advisories this repository no longer contains until the
``health-advisories`` index is dropped and re-seeded. Every guarantee the tests
make about which advisories a persona can be served holds in-process; it holds
against Elasticsearch only after that re-seed.
"""
import os
import hashlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saafsaans.services import config, es  # noqa: E402
from saafsaans.data.advisories import ADVISORIES  # noqa: E402

MAPPINGS = {
    es.INDEX_ADVISORIES: {"mappings": {"properties": {
        "aqi_min": {"type": "integer"}, "aqi_max": {"type": "integer"},
        "condition": {"type": "keyword"}, "activity": {"type": "keyword"},
        "age_group": {"type": "keyword"},
        "advice": {"type": "text"}, "source": {"type": "keyword"}}}},
    es.INDEX_READINGS: {"mappings": {"properties": {
        "@timestamp": {"type": "date"}, "station": {"type": "keyword"},
        "city": {"type": "keyword"}, "aqi": {"type": "integer"},
        "pm25": {"type": "float"}, "pm10": {"type": "float"},
        "dominant_pollutant": {"type": "keyword"}}}},
    es.INDEX_TELEMETRY: {"mappings": {"properties": {
        "@timestamp": {"type": "date"}, "session_hash": {"type": "keyword"},
        "event": {"type": "keyword"}, "latency_ms": {"type": "integer"},
        "waqi_status": {"type": "keyword"}, "llm_status": {"type": "keyword"},
        "llm_tokens": {"type": "integer"}, "error": {"type": "text"},
        "aqi_value": {"type": "integer"}, "locality": {"type": "keyword"},
        "user_hash": {"type": "keyword"}}}},
    es.INDEX_SECURITY: {"mappings": {"properties": {
        "@timestamp": {"type": "date"}, "session_hash": {"type": "keyword"},
        "event_type": {"type": "keyword"}, "pattern_matched": {"type": "keyword"},
        "prompt_excerpt": {"type": "text"}, "action_taken": {"type": "keyword"},
        "user_hash": {"type": "keyword"}}}},
}


def advisory_id(advisory: dict) -> str:
    """Stable id for a seed advisory, so re-seeding is idempotent.

    Derived from the fields that identify the row rather than from its position
    in the list, so reordering data/advisories.py does not orphan documents.
    """
    key = "|".join(str(advisory.get(f, "")) for f in
                   ("aqi_min", "aqi_max", "condition", "activity", "age_group", "source"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def main():
    if not config.es_available():
        print("No Elastic credentials found (ELASTIC_CLOUD_ID/ELASTIC_URL + "
              "ELASTIC_API_KEY). Nothing to set up — the app still runs in "
              "mock mode. Set credentials in .env to enable Elastic.")
        return 1

    client = es.get_client()
    if client is None:
        print("Could not build an Elasticsearch client. Check credentials.")
        return 1

    ready = 0
    for index, body in MAPPINGS.items():
        if client.indices.exists(index=index):
            print(f"  = {index} already exists")
        else:
            # elasticsearch-py 9.x removed the `body=` param; pass mappings directly.
            client.indices.create(index=index, mappings=body["mappings"])
            print(f"  + {index} created")
        ready += 1

    from elasticsearch.helpers import bulk

    # Deterministic ids derived from the advisory itself, so re-running this
    # script overwrites rather than appends. Without them every run added
    # another full copy of the 34 advisories, and retrieval then returned the
    # same guidance several times in one answer -- visible to the user as
    # duplicate sources in the "what this answer is based on" panel.
    actions = [
        {"_index": es.INDEX_ADVISORIES, "_id": advisory_id(a), "_source": a}
        for a in ADVISORIES
    ]
    bulk(client, actions)
    client.indices.refresh(index=es.INDEX_ADVISORIES)
    total = client.count(index=es.INDEX_ADVISORIES)["count"]

    print(f"\n{ready} indices ready + {len(ADVISORIES)} advisories indexed "
          f"({total} in the index).")
    if total != len(ADVISORIES):
        print(f"  ! expected {len(ADVISORIES)}; delete the index and re-run to clear "
              "duplicates left by an older version of this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
