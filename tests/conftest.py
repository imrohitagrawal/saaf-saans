"""Test isolation.

The app writes telemetry and blocked-prompt events to Elasticsearch. Without
this, running the suite pollutes the same indices the running app reads from --
every `pytest` run inflated the Security and Observability numbers with events
that came from tests, not from users.

Clearing the Elastic credentials for the session makes `es.get_client()` return
None, so the app exercises its in-process fallback path and writes nothing.
"""
import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_live_elasticsearch():
    import os

    saved = {k: os.environ.pop(k, None)
             for k in ("ELASTIC_URL", "ELASTIC_CLOUD_ID", "ELASTIC_API_KEY")}
    from saafsaans.web import main
    main._client = None
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
    main._client = None
