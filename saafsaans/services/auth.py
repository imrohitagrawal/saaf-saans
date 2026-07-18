"""Optional, privacy-preserving identity for continuity across sessions.

The design keeps SaafSaans's zero-PII promise: a user may *optionally* sign in
with an email or phone number, but the raw value is **never** returned, stored
in session state, or written to Elasticsearch. We derive a one-way ``user_id``
and keep only that. ``mask`` produces a display string that hides the identity
while confirming to the user what they typed.

We use **scrypt** (a memory-hard KDF), not a bare SHA-256, because identities
like phone numbers have low entropy and would otherwise be brute-forceable if
someone obtained the hashes. scrypt makes each guess expensive. For real
anonymity the deployment must also set a secret ``SAAFSAANS_LOGIN_SALT`` (a
pepper) — the built-in demo salt is public, so treat the demo as illustrative,
not hardened.
"""
import hashlib
import re

# scrypt work factors. 128*N*r*p ~= 16 MB of memory per hash — cheap for a
# single interactive login, expensive to brute-force at scale.
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Digits only, 7-15 (E.164-ish) after stripping spaces / dashes / parens / +.
_PHONE_CLEAN_RE = re.compile(r"[\s\-()]+")
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def valid_email(identity: str) -> bool:
    return bool(_EMAIL_RE.match((identity or "").strip()))


def valid_phone(identity: str) -> bool:
    cleaned = _PHONE_CLEAN_RE.sub("", (identity or "").strip())
    return bool(_PHONE_RE.match(cleaned))


def is_valid(identity: str) -> bool:
    return valid_email(identity) or valid_phone(identity)


def _canonical(identity: str) -> str:
    """Normalise so 'A@X.com ' and 'a@x.com' hash identically."""
    s = (identity or "").strip().lower()
    if "@" not in s:  # phone: keep leading +, drop separators
        return _PHONE_CLEAN_RE.sub("", s)
    return s


def hash_identity(identity: str, salt: str, length: int = 16) -> str:
    """Return a salted, memory-hard one-way ``user_id``.

    Deterministic for the same (identity, salt) so a returning user correlates
    to the same id, but expensive to reverse: scrypt makes each brute-force
    guess costly, which matters for low-entropy identities like phone numbers.
    The raw identity is never stored.
    """
    canonical = _canonical(identity)
    derived = hashlib.scrypt(
        canonical.encode("utf-8"), salt=str(salt).encode("utf-8"),
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32, maxmem=_SCRYPT_MAXMEM,
    )
    return derived.hex()[:length]


def mask(identity: str) -> str:
    """Display string that confirms the identity without revealing it.

    ``rohit@gmail.com`` -> ``r***@gmail.com``; ``+919812345678`` -> ``+91****78``.
    """
    s = (identity or "").strip()
    if "@" in s:
        local, _, domain = s.partition("@")
        head = local[0] if local else ""
        return f"{head}***@{domain}"
    cleaned = _PHONE_CLEAN_RE.sub("", s)
    if len(cleaned) >= 4:
        return f"{cleaned[:3]}****{cleaned[-2:]}"
    return "****"
