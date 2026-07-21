"""Backfill DEMO OPERATIONAL history so the System view has something to draw.

Writes ~40 app-telemetry docs spread over time and ~6 security-events, both of
which are records of how the APP behaved. Everything respects the fixed index
mappings and the field allowlists in :mod:`saafsaans.services.es` — no persona
or PII is ever written.

It does NOT write air readings, and must not. It used to seed ~42h of invented
AQI across five stations from a hardcoded base table — Anand Vihar 380, ITO 300,
RK Puram 260 — plus a random walk, straight into the aqi-readings index with
`@timestamp` running up to now and no field marking them as fabricated.

That index is now the app's honesty surface. `metrics.station_grid` reads it for
City Pulse, which prints the number with its age, and `main._last_real_reading`
reads it to print "We last recorded AQI n here on <date>" — a dated claim about
a measurement this app says it took. Nothing distinguished a seeded row from an
observed one, so running the documented backfill made the app publish invented
figures as its own observations. The run deleted `waqi.SAMPLES` for being exactly
that, and its stated reason applies here verbatim: a disconnected table is a
loaded gun left on the table.

The reason readings needed seeding is also gone. `main._live_grid` fetches and
indexes all 21 localities on every /city render, so the index fills from real
observations as soon as anyone loads the page.

Runnable:  python -m saafsaans.seed_demo_history
If ES is not configured (get_client returns None), it prints a notice and
exits 0 so it is safe to run in mock mode.
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from elasticsearch.helpers import bulk

from .services import es, waqi

EVENTS = ["chat_completed", "blocked"]
WAQI_STATUSES = ["ok", "fallback"]
LLM_STATUSES = ["ok", "llm_fallback"]
LOCALITIES = list(waqi.LOCALITIES)
PATTERNS = ["ignore_instructions", "system_prompt_leak", "roleplay_jailbreak",
            "reveal_secrets", "prompt_injection"]

# How far back the seeded operational events are spread.
SPAN_HOURS = 42
N_TELEMETRY = 40
N_SECURITY = 6


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _telemetry_docs(now: datetime):
    for i in range(N_TELEMETRY):
        ts = now - timedelta(minutes=random.randint(0, SPAN_HOURS * 60))
        event = random.choices(EVENTS, weights=[0.85, 0.15])[0]
        waqi_status = random.choices(WAQI_STATUSES, weights=[0.8, 0.2])[0]
        llm_status = random.choices(LLM_STATUSES, weights=[0.85, 0.15])[0]
        locality = random.choice(LOCALITIES)
        tokens = 0 if event == "blocked" else random.randint(180, 900)
        doc = {
            "_index": es.INDEX_TELEMETRY,
            "@timestamp": _iso(ts),
            "session_hash": f"{random.randrange(16**12):012x}",
            "event": event,
            "latency_ms": random.randint(200, 6000),
            "waqi_status": waqi_status,
            "llm_status": llm_status,
            "llm_tokens": tokens,
            "aqi_value": random.randint(80, 450),
            "locality": locality,
        }
        yield doc


def _security_docs(now: datetime):
    for i in range(N_SECURITY):
        ts = now - timedelta(minutes=random.randint(0, SPAN_HOURS * 60))
        yield {
            "_index": es.INDEX_SECURITY,
            "@timestamp": _iso(ts),
            "session_hash": f"{random.randrange(16**12):012x}",
            "event_type": "prompt_guard",
            "pattern_matched": random.choice(PATTERNS),
            "prompt_excerpt": "[demo] blocked prompt-injection attempt",
            "action_taken": "blocked",
        }


def main() -> int:
    client = es.get_client()
    if client is None:
        print("ES not configured (mock mode) — nothing to seed. Exiting 0.")
        return 0

    random.seed(42)
    now = datetime.now(timezone.utc)

    counts = {}
    for label, gen in (
        ("app-telemetry", _telemetry_docs(now)),
        ("security-events", _security_docs(now)),
    ):
        docs = list(gen)
        try:
            success, _ = bulk(client, docs, stats_only=True, raise_on_error=False)
        except Exception as exc:
            print(f"  {label}: bulk failed ({exc.__class__.__name__}); indexed 0")
            counts[label] = 0
            continue
        counts[label] = success
        print(f"  {label}: indexed {success} docs")

    print(f"Done. {sum(counts.values())} demo docs across "
          f"{len([c for c in counts.values() if c])} indices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
