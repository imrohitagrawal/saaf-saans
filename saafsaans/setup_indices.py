"""One-shot: create the four indices (if missing) and seed advisories.

Run: ``python setup_indices.py`` (or ``python saafsaans/setup_indices.py``).
Idempotent — existing indices are left in place. Requires Elastic credentials;
without them it prints guidance and exits cleanly (the app itself still runs
in mock mode).
"""
import os
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
    actions = [{"_index": es.INDEX_ADVISORIES, "_source": a} for a in ADVISORIES]
    bulk(client, actions)
    client.indices.refresh(index=es.INDEX_ADVISORIES)

    print(f"\n{ready} indices ready + {len(ADVISORIES)} advisories indexed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
