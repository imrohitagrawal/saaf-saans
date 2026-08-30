"""Central environment / capability detection.

Loading ``.env`` and deciding which external services are available happens
here so every module and every test agrees on the same rules. This is the
foundation of the app's mock-first behaviour: with no keys set, every
capability check returns "unavailable" and callers fall back gracefully.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv is optional at runtime; env vars may already be set.
    pass


def _clean(name: str) -> str:
    """Return an env var stripped of whitespace, or '' if unset/blank."""
    return (os.environ.get(name) or "").strip()


def es_mode() -> str:
    """Return the Elasticsearch connection mode.

    Precedence:
      * ``cloud`` — ELASTIC_CLOUD_ID + ELASTIC_API_KEY both set
      * ``url``   — ELASTIC_URL + ELASTIC_API_KEY both set
      * ``none``  — anything else (in-process mock mode)

    A URL without an api key degrades to ``none`` — we never half-connect.
    """
    api_key = _clean("ELASTIC_API_KEY")
    if not api_key:
        return "none"
    if _clean("ELASTIC_CLOUD_ID"):
        return "cloud"
    if _clean("ELASTIC_URL"):
        return "url"
    return "none"


def es_available() -> bool:
    return es_mode() != "none"


def waqi_available() -> bool:
    return bool(_clean("WAQI_TOKEN"))


def llm_available() -> bool:
    return bool(_clean("OPENROUTER_API_KEY"))


def waqi_token() -> str:
    return _clean("WAQI_TOKEN")


def openrouter_key() -> str:
    return _clean("OPENROUTER_API_KEY")


def openrouter_model() -> str:
    return _clean("OPENROUTER_MODEL") or "google/gemini-2.5-flash"




def elastic_cloud_id() -> str:
    return _clean("ELASTIC_CLOUD_ID")


def elastic_url() -> str:
    return _clean("ELASTIC_URL")


def elastic_api_key() -> str:
    return _clean("ELASTIC_API_KEY")


def cpcb_key() -> str:
    return _clean("CPCB_API_KEY")


# Not a credential, so it is deliberately not in the _CLEAN credential shape
# tests/test_privacy.py screens for (_KEY|_TOKEN|_SECRET|_PASSWORD|_CLOUD_ID|
# _URL) and not in conftest's BLANKED_CREDENTIALS: blanking it would point the
# suite at the default path in the working directory, which is the opposite of
# what the harness wants.
VIEWPORT_DB_ENV = "SAAFSAANS_VIEWPORT_DB"


def viewport_db_path() -> str:
    """Where the viewport probe keeps its per-band counts.

    Defaults to a file in the working directory so tests and local runs need no
    volume. Production sets the variable to a path on a mounted Fly volume,
    because the container filesystem is replaced on every deploy.

    Read at call time rather than captured at import, so a test can repoint it.
    """
    return _clean(VIEWPORT_DB_ENV) or "viewport-counts.sqlite3"


def cpcb_available() -> bool:
    """Derived from ``cpcb_key`` rather than re-reading the environment.

    Two functions reading the same variable is how /health comes to report a
    capability the request path does not have: the fetch path asks for the
    key, so the availability answer has to be about the same call."""
    return bool(cpcb_key())
