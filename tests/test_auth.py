"""Optional login: salted one-way hashing, never exposing raw PII."""
from saafsaans.services import auth

SALT = "test-salt"
EMAIL = "Rohit@Gmail.com"
PHONE = "+91 98123-45678"


def test_email_validation():
    assert auth.valid_email("a@b.co")
    assert not auth.valid_email("not-an-email")
    assert not auth.valid_email("a@b")
    assert not auth.valid_email("")


def test_phone_validation():
    assert auth.valid_phone("+91 98123-45678")
    assert auth.valid_phone("9812345678")
    assert not auth.valid_phone("12")
    assert not auth.valid_phone("abcdefg")


def test_hash_deterministic_and_salted():
    h1 = auth.hash_identity(EMAIL, SALT)
    h2 = auth.hash_identity(EMAIL, SALT)
    assert h1 == h2                     # deterministic
    assert h1 != auth.hash_identity(EMAIL, "other-salt")  # salt matters
    assert len(h1) == 16


def test_hash_is_case_and_whitespace_canonical():
    assert auth.hash_identity("Rohit@Gmail.com", SALT) == \
        auth.hash_identity("  rohit@gmail.com ", SALT)
    assert auth.hash_identity("+91 9812345678", SALT) == \
        auth.hash_identity("+919812345678", SALT)


def test_hash_never_contains_raw_pii():
    h = auth.hash_identity(EMAIL, SALT)
    assert "rohit" not in h.lower()
    assert "@" not in h
    assert "gmail" not in h.lower()
    ph = auth.hash_identity(PHONE, SALT)
    assert "9812345678" not in ph


def test_mask_hides_identity():
    assert auth.mask("rohit@gmail.com") == "r***@gmail.com"
    assert "rohit" not in auth.mask("rohit@gmail.com")
    masked_phone = auth.mask("+919812345678")
    assert masked_phone.endswith("78")
    assert "9812345" not in masked_phone


def test_is_valid_accepts_either():
    assert auth.is_valid("a@b.co")
    assert auth.is_valid("9812345678")
    assert not auth.is_valid("nonsense")
