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

from tests._netguard import NetworkUsedInTests

# Every credential the app reads to reach an external service. A name missing
# here is not a small oversight: the suite silently starts making live calls,
# which is how a run once took three minutes instead of thirty seconds and
# depended on Delhi's weather. Named as a module constant rather than inlined
# below so test_privacy can assert this list against what config.py actually
# reads -- the next credential to be added is caught by that test, not by
# somebody remembering this file exists.
BLANKED_CREDENTIALS = (
    "ELASTIC_URL", "ELASTIC_CLOUD_ID", "ELASTIC_API_KEY",
    "WAQI_TOKEN", "OPENROUTER_API_KEY", "CPCB_API_KEY",
)


@pytest.fixture(autouse=True, scope="session")
def _no_live_external_calls():
    import os

    saved = {k: os.environ.pop(k, None) for k in BLANKED_CREDENTIALS}
    from saafsaans.web import main
    main._client = None
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
    main._client = None


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "allow_network: this test genuinely needs outbound transport")


@pytest.fixture(autouse=True)
def _no_outbound_sockets(request):
    """Make the offline paths ENFORCED rather than merely intended.

    Blanking the credentials states the intent and does not secure it. A test
    stubbed ``config.cpcb_available()`` to True without stubbing
    ``config.cpcb_key()``, so ``cpcb.available()`` was true while the key was
    "" and ``cpcb._fetch_city`` issued a real HTTPS request to api.data.gov.in
    -- with ``api-key=`` in the query string -- on six parametrisations of every
    run. Around twelve outbound calls per run, and the reason the suite's
    runtime ranged from 5.6s to 19.4s: the tail was ``_CITY_FETCH_BUDGET``
    expiring on a stalled TLS handshake, so a green run and a slow one differed
    by Delhi's network rather than by anything in the tree.

    An assertion about hermeticity written as a comment is a wish. This is the
    same argument the module docstring already makes, enforced.

    Loopback stays open -- TestClient speaks ASGI in-process, so nothing here
    needs it, but a future fixture binding a local port should not have to
    fight this. A test that truly needs transport marks itself ``allow_network``,
    which is greppable; a silent leak is not.
    """
    if request.node.get_closest_marker("allow_network"):
        yield
        return

    import socket

    real_connect = socket.socket.connect

    def blocked(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else address
        if host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address, *args, **kwargs)
        raise NetworkUsedInTests(
            f"the suite tried to reach {host!r}. These tests run offline: stub "
            "the call, or mark the test `allow_network` if it really needs a "
            "network.")

    socket.socket.connect = blocked
    try:
        yield
    finally:
        socket.socket.connect = real_connect


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
def _no_index_reachability_carryover_between_tests():
    """Whether the index answered is cached per process, for the same reason
    the readings are: it is one fact about one endpoint, shared by every
    request. Held across tests it would make a test that stubs a reachable
    client decide what the next one sees.
    """
    from saafsaans.services import es
    es.answer_cache_clear()
    yield
    es.answer_cache_clear()


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
    "city": "Delhi", "stale": False, "retained": False, "source": "waqi",
    "forecast": None,
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


@pytest.fixture(autouse=True, scope="session")
def _viewport_counts_never_touch_a_real_store(tmp_path_factory):
    """The probe's counter file, pointed at a temporary directory.

    Not tidiness. Several test files issue real probe requests, and
    tests/test_viewport_browser.py runs a real uvicorn in this process across
    seven widths -- against the developer's real .env, because config calls
    load_dotenv() at import and find_dotenv() walks up out of a worktree. With
    no override the suite writes page-load counts into whatever store the
    machine is configured for: the pollution this module's docstring already
    describes for Elasticsearch, arriving in a second place.

    Set rather than unset, for the reason
    test_privacy.py::test_clearing_credentials_needs_them_empty_not_unset
    pins: load_dotenv() does not overwrite a name already in the environment,
    but it does fill in one that has been UNSET.
    """
    import os

    from saafsaans.services import config, viewport

    path = tmp_path_factory.mktemp("viewport") / "counts.sqlite3"
    saved = os.environ.get(config.VIEWPORT_DB_ENV)
    os.environ[config.VIEWPORT_DB_ENV] = str(path)
    viewport.reset()
    yield
    viewport.reset()
    if saved is None:
        os.environ.pop(config.VIEWPORT_DB_ENV, None)
    else:
        os.environ[config.VIEWPORT_DB_ENV] = saved


@pytest.fixture(autouse=True)
def _no_viewport_counts_carryover_between_tests():
    """Counters are cumulative by design, so without this the bands a test
    asserts depend on how many probe requests every earlier test happened to
    make -- the argument the rate-limit fixture above makes about buckets.

    The FILE is removed, not emptied, and the difference is the whole point.
    An emptied store answers as a MEASURED zero ("no page loads counted yet");
    a store that was never created answers as no measurement at all. Emptying
    would silently move every test after the first probe request onto the other
    branch, and which branch renders is what several other files assert.

    The -wal and -shm sidecars go too: a WAL left behind holds committed rows
    the main file does not, so removing only the database would let one test
    read the previous test's counts.

    Deleting the store lives here rather than in the module under test. A
    production module that can erase its own database is a footgun the app has
    no use for.
    """
    import pathlib

    from saafsaans.services import config, viewport

    def clear():
        base = pathlib.Path(config.viewport_db_path())
        if not base.exists():
            # Most tests never touch the store. Reopening and unlinking nothing
            # 1400 times over is measurable, and skipping it is free: with no
            # file there is no connection to drop either.
            return
        viewport.reset()
        for path in (base, base.with_name(base.name + "-wal"),
                     base.with_name(base.name + "-shm")):
            path.unlink(missing_ok=True)

    clear()
    yield
    clear()
