"""Backfill DEMO history so the Command Center dashboards look alive.

Writes ~24-48h of aqi-readings across the 5 Delhi stations following a
realistic diurnal curve (worse at night / early morning, cleaner mid-afternoon),
~40 app-telemetry docs spread over time, and ~6 security-events. Everything
respects the fixed index mappings and the field allowlists in
:mod:`saafsaans.services.es` — no persona or PII is ever written.

Runnable:  python -m saafsaans.seed_demo_history
If ES is not configured (get_client returns None), it prints a notice and
exits 0 so it is safe to run in mock mode.
"""
import math
import random
import sys
from datetime import datetime, timedelta, timezone

from elasticsearch.helpers import bulk

from .services import clock, es

# Per-station baseline AQI and its rough amplitude for the diurnal swing.
STATIONS = {
    "Anand Vihar": 380,
    "ITO": 300,
    "Rohini": 190,
    "RK Puram": 260,
    "Delhi (city)": 285,
}
POLLUTANTS = ["pm25", "pm10"]

EVENTS = ["chat_completed", "blocked"]
WAQI_STATUSES = ["ok", "fallback"]
LLM_STATUSES = ["ok", "llm_fallback"]
LOCALITIES = list(STATIONS.keys())
PATTERNS = ["ignore_instructions", "system_prompt_leak", "roleplay_jailbreak",
            "reveal_secrets", "prompt_injection"]

READING_HOURS = 42          # span of backfilled readings
READING_INTERVAL_MIN = 30   # one reading per station every 30 minutes
N_TELEMETRY = 40
N_SECURITY = 6


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _diurnal_factor(hour: int) -> float:
    """Multiplier in ~[0.7, 1.3]: peaks around 06:00 IST, dips mid-afternoon.

    ``hour`` must be an IST hour. It used to be read straight off a UTC
    timestamp, which shifted the whole curve by five and a half hours and put
    the seeded "worst air" peak at 11:30 IST -- late morning, on the way down
    towards the afternoon trough this same docstring describes.
    """
    # Shift so the cosine peak lands near early morning (hour 6).
    return 1.0 + 0.3 * math.cos((hour - 6) / 24.0 * 2 * math.pi)


def _reading_docs(now: datetime):
    steps = int(READING_HOURS * 60 / READING_INTERVAL_MIN)
    for station, base in STATIONS.items():
        for i in range(steps):
            ts = now - timedelta(minutes=i * READING_INTERVAL_MIN)
            factor = _diurnal_factor(clock.to_ist(ts).hour)
            aqi = int(max(20, base * factor + random.uniform(-25, 25)))
            pm25 = round(aqi * random.uniform(0.7, 0.9), 1)
            pm10 = round(aqi * random.uniform(1.1, 1.5), 1)
            yield {
                "_index": es.INDEX_READINGS,
                "@timestamp": _iso(ts),
                "station": station,       # real station name
                "city": "Delhi",          # schema-valid demo marker
                "aqi": aqi,
                "pm25": pm25,
                "pm10": pm10,
                "dominant_pollutant": random.choice(POLLUTANTS),
            }


def _telemetry_docs(now: datetime):
    for i in range(N_TELEMETRY):
        ts = now - timedelta(minutes=random.randint(0, READING_HOURS * 60))
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
        ts = now - timedelta(minutes=random.randint(0, READING_HOURS * 60))
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
        ("aqi-readings", _reading_docs(now)),
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
