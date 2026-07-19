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
