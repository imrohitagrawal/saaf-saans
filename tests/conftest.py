"""Test isolation.

The app writes telemetry and blocked-prompt events to Elasticsearch. Without
this, running the suite pollutes the same indices the running app reads from --
every `pytest` run inflated the Security and Observability numbers with events
that came from tests, not from users.

The same argument applies to the outbound APIs, and it took longer to notice.
With WAQI_TOKEN and OPENROUTER_API_KEY set in .env, every run was making live
calls to both: the suite took three minutes instead of thirty seconds, its
results depended on Delhi's weather and on what a language model happened to
return, and a test asserting the shape of an answer could pass or fail for
reasons no commit caused. Clearing all five credentials makes the app take its
offline paths, which is what these tests are for.
"""
import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_live_external_calls():
    import os

    saved = {k: os.environ.pop(k, None)
             for k in ("ELASTIC_URL", "ELASTIC_CLOUD_ID", "ELASTIC_API_KEY",
                       "WAQI_TOKEN", "OPENROUTER_API_KEY")}
    from saafsaans.web import main
    main._client = None
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
    main._client = None


@pytest.fixture(autouse=True)
def _no_cached_readings_between_tests():
    """``waqi.get_aqi`` memoises per locality, so without this a test that
    stubs the feed leaves its reading visible to the next one and tests pass
    or fail depending on the order they ran in.

    The cache is process-global on purpose -- that is what makes it shared
    between visitors -- so isolating it belongs here rather than in each test.
    """
    from saafsaans.services import waqi
    waqi.cache_clear()
    yield
    waqi.cache_clear()


@pytest.fixture(autouse=True)
def _no_rate_limit_carryover_between_tests():
    """The limiter keys on client IP, and every test client presents the same
    one, so without this the suite shares a single bucket: a file that posts
    twenty questions throttles whatever runs after it, and the failure lands
    somewhere unrelated to the cause.
    """
    from saafsaans.services import ratelimit
    ratelimit.reset()
    yield
    ratelimit.reset()


# A live reading, for tests whose SUBJECT only exists when there is one.
#
# Until the fallback stopped manufacturing a figure, the default no-credentials
# render still produced a full reading -- a hardcoded winter concentration pair
# scored on the CPCB scale -- so tests about the WHO comparison, the scale
# marker, the provenance panel's measurement block and the answer's retrieved
# sources all got their subject for free. They were never testing the sample;
# they were testing a surface that is only drawn when a reading exists, and the
# sample was what happened to draw it. This fixture supplies the premise
# explicitly, so those tests keep asserting what they were written to assert.
LIVE_READING = {
    "aqi": 168, "aqi_beyond_scale": False, "pm25": 90.0, "pm10": 160.0,
    "dominant_pollutant": "pm25", "feed_aqi": 210, "feed_dominant": "pm25",
    "city": "Delhi", "stale": False, "forecast": None,
    "obs_time": "2026-07-21T10:00:00+05:30",
}


@pytest.fixture
def live_feed(monkeypatch):
    """Make ``waqi.get_aqi`` answer with a real-shaped live reading."""
    from saafsaans.services import waqi

    def _get(locality, es_client=None):
        return ({**LIVE_READING, "station": locality}, "ok")

    monkeypatch.setattr(waqi, "get_aqi", _get)
    return LIVE_READING
