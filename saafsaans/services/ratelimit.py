"""A fixed-window rate limiter for the two endpoints that do work on demand.

`POST /ask` and `POST /system/simulate` are unauthenticated by design -- there
are no accounts, and asking for one to read air-quality advice would defeat the
point. But both do real work per request: `/ask` writes telemetry, may write a
security event, and calls a language model when a key is configured; `/simulate`
writes a document per attack in the demo set. Unthrottled, one script can drive
unbounded Elasticsearch writes and unbounded third-party spend, on one 256MB
machine that scales to zero.

Deliberately in-process and deliberately simple:

  * There is ONE machine. A shared counter in Redis would be a second service
    to run, pay for and fail, guarding a single process that already has the
    numbers in memory. If this ever runs on two machines the limit becomes
    per-machine, which is a real limitation and is written down rather than
    designed around now.
  * The key is the client IP, taken from X-Forwarded-For because the container
    sits behind Fly's proxy. An IP is not a person -- a college or an office
    behind one NAT shares a bucket -- so the limits below are set well above
    what a person does and only bite on automation.
  * Nothing is persisted. A restart forgives everyone, which is the right
    failure direction for a limiter protecting a demo rather than a bank.

The window is fixed rather than sliding: a sliding window needs per-request
timestamps and this needs a counter and a clock.
"""
import threading
import time

# A reader asking questions does not exceed these. They are sized to stop a
# loop, not to ration a person.
ASK_LIMIT = 20          # questions per window, per IP
ASK_WINDOW = 300        # five minutes
SIMULATE_LIMIT = 5      # red-team demo firings per window, per IP
SIMULATE_WINDOW = 300

_BUCKETS = {}
_LOCK = threading.Lock()
# A bucket per IP would grow without bound under a spray of forged
# X-Forwarded-For headers -- a memory leak reachable from the internet, on a
# 256MB machine. Past this many, the expired entries are dropped; if that is
# not enough, the whole table is, which forgives everyone and is a better
# failure than being killed by the OOM reaper.
_MAX_BUCKETS = 10_000


def _now():
    return time.monotonic()


def check(key: str, limit: int, window: int):
    """Record a hit for ``key`` and return ``(allowed, retry_after_seconds)``.

    ``retry_after`` is 0 when allowed, and otherwise the whole seconds until
    the current window ends.
    """
    now = _now()
    with _LOCK:
        if len(_BUCKETS) >= _MAX_BUCKETS:
            for stale in [k for k, (start, _) in _BUCKETS.items()
                          if now - start >= window]:
                del _BUCKETS[stale]
            if len(_BUCKETS) >= _MAX_BUCKETS:
                _BUCKETS.clear()

        start, count = _BUCKETS.get(key, (now, 0))
        if now - start >= window:
            start, count = now, 0
        count += 1
        _BUCKETS[key] = (start, count)

    if count > limit:
        return False, max(1, int(window - (now - start)))
    return True, 0


def client_key(request) -> str:
    """The caller's identity for limiting: the first X-Forwarded-For hop.

    Fly terminates TLS at its proxy and appends the real client to
    X-Forwarded-For, so ``request.client.host`` is the proxy for every visitor
    and would put the whole internet in one bucket. The FIRST entry is the
    originating client; later ones are proxies. It is attacker-controlled, so
    it is a courtesy key and not an identity -- which is why the table above is
    bounded.
    """
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")
    first = forwarded[0].strip()
    if first:
        return first
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def reset():
    """Drop every bucket. For tests."""
    with _LOCK:
        _BUCKETS.clear()
