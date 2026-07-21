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
    """The caller's identity for limiting: the LAST X-Forwarded-For hop.

    Fly terminates TLS at its proxy and APPENDS the connecting address to
    X-Forwarded-For. ``request.client.host`` is therefore the proxy for every
    visitor alike and would put the whole internet in one bucket -- so the
    header has to be read. But only its last entry is written by the proxy;
    everything before it was sent by the client and can say anything.

    The first draft of this read ``forwarded[0]``, which is the one value an
    attacker fully controls. A client sending `X-Forwarded-For: <random>` on
    each request arrives as "<random>, <real ip>", lands in a fresh bucket
    every time, and is never limited at all -- while also filling the bucket
    table, which is the memory leak the bound above exists for. The limiter
    would have been decorative.

    Taking the last entry inverts that: a forged prefix is ignored, because
    whatever the client prepends, the proxy's own append is what is read. If a
    second trusted proxy is ever put in front, this must index from the end by
    the known hop count -- not go back to [0].
    """
    forwarded = [hop.strip() for hop in
                 (request.headers.get("x-forwarded-for") or "").split(",")]
    forwarded = [hop for hop in forwarded if hop]
    if forwarded:
        return forwarded[-1]
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def reset():
    """Drop every bucket. For tests."""
    with _LOCK:
        _BUCKETS.clear()
