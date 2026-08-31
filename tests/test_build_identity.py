"""`/health` says which commit is running.

Before this, the only thing a running instance disclosed about its own code was
the ``?v=<sha256[:12]>`` content hash on ``app.css``. That is a hash of one
stylesheet, so a release that changed Python, a template, a font or a
dependency reported byte-identical to the release before it.

That is not hypothetical. On 2026-08-31 the asset-hash check reported "parity
OK" against a production instance that was nine files behind master, including
`saafsaans/web/main.py` and every subsetted font -- because the fonts package
happened not to touch `app.css`. The check was doing exactly what it was built
to do and still returned a green answer to the wrong question.

`build` answers the right one: an exact commit, comparable to `git rev-parse`.
"""
import os
import re

import pytest
from fastapi.testclient import TestClient

from saafsaans.web.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_a_build(client):
    """Turns red when: `build` is dropped from the /health payload.

    An absence check on its own would be satisfied by an endpoint that returns
    nothing, so the partner below pins a real value through.
    """
    body = client.get("/health").json()
    assert "build" in body, f"/health has no build field: {sorted(body)}"


def test_the_build_field_carries_the_environment_through(client, monkeypatch):
    """The partner. Proves `build` reads the environment rather than printing a
    constant -- a hardcoded "unknown" would satisfy the test above for ever, and
    would report the same string on every deploy that ever runs.
    """
    monkeypatch.setenv("GIT_SHA", "0123456789abcdef0123456789abcdef01234567")
    body = client.get("/health").json()
    assert body["build"] == "0123456789abcdef0123456789abcdef01234567"


def test_an_image_built_without_a_commit_says_unknown(client, monkeypatch):
    """Absence is stated, never fabricated -- constraint (i).

    An image built with no `--build-arg GIT_SHA` must not invent a plausible
    commit or report empty. It says "unknown", and the deploy verification
    treats "unknown" as a failed check rather than a pass.
    """
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert client.get("/health").json()["build"] == "unknown"


def test_the_dockerfile_declares_the_build_arg():
    """Turns red when: the ARG/ENV pair is dropped from the Dockerfile.

    The endpoint reading `GIT_SHA` is only half of it. If the image never
    receives the value, every deploy reports "unknown" and the whole check
    degrades to a constant -- green, uninformative, and indistinguishable from
    working. Both halves have to exist for either to mean anything.
    """
    from pathlib import Path

    dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text()
    assert re.search(r"^ARG\s+GIT_SHA=", dockerfile, re.M), "Dockerfile has no ARG GIT_SHA"
    assert re.search(r"^ENV\s+GIT_SHA=\$\{GIT_SHA\}", dockerfile, re.M), \
        "Dockerfile does not promote GIT_SHA into the image environment"


def test_health_still_reports_every_backend_it_did_before(client):
    """The field set is a contract; `build` is added to it, not swapped in.

    `tests/test_web.py` asserts the primary source is listed before the
    fallback. This guards the rest of the payload against a future edit that
    trims it while adding to it.
    """
    body = client.get("/health").json()
    for key in ("ok", "es", "cpcb", "waqi", "llm", "build"):
        assert key in body, f"/health lost {key}: {sorted(body)}"
