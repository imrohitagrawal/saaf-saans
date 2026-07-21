"""Read-only Elasticsearch aggregations that feed the Command Center dashboards.

Every function is defensive by construction: it accepts an ES client that may be
``None`` and MUST return a valid, empty-but-correctly-shaped result on a None
client or on ANY exception. Dashboards must never crash because ES is down or a
mapping is missing — a blank chart is always preferable to a stack trace.

All queries are size=0 aggregations (es-py 9.x kwargs style: ``aggs=...``,
``query=...``, ``size=0``). Index names come from :mod:`saafsaans.services.es`.
"""
from .es import INDEX_READINGS, INDEX_TELEMETRY, INDEX_SECURITY


def _empty_kpis():
    return {
        "total": 0,
        "by_event": {},
        "latency_p50": 0.0,
        "latency_p95": 0.0,
        "waqi_fallback_rate": 0.0,
        "llm_fallback_rate": 0.0,
        "total_tokens": 0,
        "by_locality": [],
    }


def telemetry_kpis(client) -> dict:
    """Aggregate app-telemetry into headline KPIs for the ops dashboard.

    Returns totals, per-event counts, latency percentiles, WAQI/LLM fallback
    rates, token sum, and a per-locality breakdown. Empty shape on failure.
    """
    if client is None:
        return _empty_kpis()
    try:
        resp = client.search(
            index=INDEX_TELEMETRY,
            size=0,
            aggs={
                "by_event": {"terms": {"field": "event", "size": 20}},
                "by_locality": {"terms": {"field": "locality", "size": 20}},
                "latency": {"percentiles": {"field": "latency_ms", "percents": [50, 95]}},
                "total_tokens": {"sum": {"field": "llm_tokens"}},
                "by_waqi": {"terms": {"field": "waqi_status", "size": 10}},
                "by_llm": {"terms": {"field": "llm_status", "size": 10}},
            },
        )
        aggs = resp.get("aggregations", {})

        def _buckets(name):
            return aggs.get(name, {}).get("buckets", [])

        by_event = {b["key"]: b["doc_count"] for b in _buckets("by_event")}
        total = sum(by_event.values())

        waqi_counts = {b["key"]: b["doc_count"] for b in _buckets("by_waqi")}
        llm_counts = {b["key"]: b["doc_count"] for b in _buckets("by_llm")}
        waqi_total = sum(waqi_counts.values())
        # LLM fallback rate must only count turns that actually attempted an LLM
        # call: 'skipped' (blocked) and 'error' events never reached the model.
        llm_attempts = llm_counts.get("ok", 0) + llm_counts.get("llm_fallback", 0)
        waqi_fallback_rate = (
            round(waqi_counts.get("fallback", 0) / waqi_total, 4) if waqi_total else 0.0
        )
        llm_fallback_rate = (
            round(llm_counts.get("llm_fallback", 0) / llm_attempts, 4) if llm_attempts else 0.0
        )

        pcts = aggs.get("latency", {}).get("values", {}) or {}
        p50 = pcts.get("50.0")
        p95 = pcts.get("95.0")

        by_locality = [
            {"locality": b["key"], "count": b["doc_count"]}
            for b in _buckets("by_locality")
        ]

        return {
            "total": total,
            "by_event": by_event,
            "latency_p50": round(float(p50), 1) if p50 is not None else 0.0,
            "latency_p95": round(float(p95), 1) if p95 is not None else 0.0,
            "waqi_fallback_rate": waqi_fallback_rate,
            "llm_fallback_rate": llm_fallback_rate,
            "total_tokens": int(aggs.get("total_tokens", {}).get("value") or 0),
            "by_locality": by_locality,
        }
    except Exception:
        return _empty_kpis()


def _empty_security():
    return {"total_blocked": 0, "by_pattern": [], "block_rate": 0.0}


def security_stats(client) -> dict:
    """Aggregate security-events: total blocked, top patterns, block rate.

    ``block_rate`` is the share of events whose action_taken == 'blocked'.
    Empty shape on failure.

    It used to also return an hourly ``over_time`` histogram over the ENTIRE
    index, unbounded and growing with every event ever logged. Nothing
    rendered it: the Security chart is filled by ``security_daily``, which
    buckets by day over a fixed window, and said so in its own docstring. An
    unbounded aggregation computed on every view of a page that never shows it
    is a cost with no reader.
    """
    if client is None:
        return _empty_security()
    try:
        resp = client.search(
            index=INDEX_SECURITY,
            size=0,
            aggs={
                "by_pattern": {"terms": {"field": "pattern_matched", "size": 20}},
                "by_action": {"terms": {"field": "action_taken", "size": 10}},
            },
        )
        aggs = resp.get("aggregations", {})

        def _buckets(name):
            return aggs.get(name, {}).get("buckets", [])

        by_pattern = [
            {"pattern": b["key"], "count": b["doc_count"]}
            for b in _buckets("by_pattern")
        ]
        action_counts = {b["key"]: b["doc_count"] for b in _buckets("by_action")}
        action_total = sum(action_counts.values())
        blocked = action_counts.get("blocked", 0)
        # Total events = sum of pattern buckets (every event carries a pattern).
        total = sum(b["count"] for b in by_pattern) or action_total
        block_rate = round(blocked / action_total, 4) if action_total else 0.0

        return {
            "total_blocked": blocked if action_total else total,
            "by_pattern": by_pattern,
            "block_rate": block_rate,
        }
    except Exception:
        return _empty_security()


def recent_security_events(client, limit: int = 6) -> list:
    """Most recent blocked attempts, newest first.

    ``security_stats`` only aggregates; the Security view also lists individual
    attempts, so this returns the documents themselves. Only the fields already
    stored are read -- ``prompt_excerpt`` is capped at 120 chars at write time
    (see ``normalize.excerpt``).

    ``session_hash`` is projected so the caller can decide whose text it is
    willing to display. It has to: the excerpt is a verbatim fragment of
    something a visitor typed, and /system is a public page with no
    authentication.
    """
    if client is None:
        return []
    try:
        resp = client.search(
            index=INDEX_SECURITY,
            size=max(1, int(limit)),
            sort=[{"@timestamp": {"order": "desc"}}],
            query={"match_all": {}},
        )
        hits = (resp.get("hits") or {}).get("hits") or []
        return [
            {
                "pattern": src.get("pattern_matched") or "unknown",
                "excerpt": src.get("prompt_excerpt") or "",
                "ts": src.get("@timestamp") or "",
                "session_hash": src.get("session_hash") or "",
            }
            for src in (h.get("_source") or {} for h in hits)
        ]
    except Exception:
        return []


def security_daily(client, days: int = 7) -> list:
    """Blocked-attempt counts bucketed by calendar day, oldest first.

    ``security_stats.over_time`` buckets hourly, which cannot fill a seven-day
    column chart. Days with no events are returned with a zero count so the
    chart keeps a stable number of columns.
    """
    days = max(1, int(days))
    if client is None:
        return []
    try:
        resp = client.search(
            index=INDEX_SECURITY,
            size=0,
            query={"bool": {"filter": [
                {"range": {"@timestamp": {"gte": f"now-{days}d/d"}}}
            ]}},
            aggs={"per_day": {"date_histogram": {
                "field": "@timestamp",
                "calendar_interval": "1d",
                "min_doc_count": 0,
                "format": "yyyy-MM-dd",
                # min_doc_count alone only fills gaps *between* existing
                # buckets, so a quiet start or end of the week would silently
                # shorten the chart. extended_bounds pins all N columns.
                "extended_bounds": {"min": f"now-{days - 1}d/d", "max": "now/d"},
            }}},
        )
        buckets = resp.get("aggregations", {}).get("per_day", {}).get("buckets", [])
        return [
            {"date": b.get("key_as_string") or b.get("key"), "count": b["doc_count"]}
            for b in buckets
        ][-days:]
    except Exception:
        return []


def aqi_trend(client, locality: str = None, hours: int = 24) -> dict:
    """Average-AQI timeline (30-minute buckets) for the trend chart.

    When ``locality`` is given, filters to readings whose station OR city equals
    it (readings store station names, but the city feed writes 'Delhi').
    Empty shape on failure.
    """
    empty = {"locality": locality, "points": []}
    if client is None:
        return empty
    try:
        query = {
            "bool": {"filter": [{"range": {"@timestamp": {"gte": f"now-{int(hours)}h"}}}]}
        }
        if locality:
            query["bool"]["must"] = [
                {"bool": {"should": [
                    {"term": {"station": locality}},
                    {"term": {"city": locality}},
                ], "minimum_should_match": 1}}
            ]
        resp = client.search(
            index=INDEX_READINGS,
            size=0,
            query=query,
            aggs={
                "trend": {
                    "date_histogram": {"field": "@timestamp", "fixed_interval": "30m"},
                    "aggs": {"avg_aqi": {"avg": {"field": "aqi"}}},
                }
            },
        )
        buckets = resp.get("aggregations", {}).get("trend", {}).get("buckets", [])
        points = []
        for b in buckets:
            avg = b.get("avg_aqi", {}).get("value")
            if avg is None:
                continue
            points.append({
                "ts": b.get("key_as_string") or b.get("key"),
                "aqi": round(float(avg)),
            })
        return {"locality": locality, "points": points}
    except Exception:
        return empty


def station_grid(client, localities: list) -> list:
    """Latest reading per station, one row per station with a live reading.

    Uses a terms agg over station with a size-1 top_hits sorted by newest
    @timestamp. Returns ``[]`` on a None client, no data, or any error.
    """
    if client is None:
        return []
    try:
        resp = client.search(
            index=INDEX_READINGS,
            size=0,
            aggs={
                "stations": {
                    "terms": {"field": "station", "size": max(len(localities or []), 5) + 5},
                    "aggs": {
                        "latest": {
                            "top_hits": {
                                "size": 1,
                                "sort": [{"@timestamp": {"order": "desc"}}],
                            }
                        }
                    },
                }
            },
        )
        buckets = resp.get("aggregations", {}).get("stations", {}).get("buckets", [])
        rows = []
        for b in buckets:
            hits = b.get("latest", {}).get("hits", {}).get("hits", [])
            if not hits:
                continue
            src = hits[0].get("_source", {})
            rows.append({
                "station": b["key"],
                "aqi": src.get("aqi"),
                "ts": src.get("@timestamp"),
            })
        return rows
    except Exception:
        return []
