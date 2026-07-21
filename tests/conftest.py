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
