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
