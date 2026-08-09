"""The exception the offline guard raises, in a module both sides can name.

Not in ``conftest.py``, and the reason is a trap worth writing down: pytest
imports the rootdir conftest as ``conftest``, while a test doing
``from tests.conftest import X`` imports it as ``tests.conftest``. Those are two
module objects, so a CLASS defined there has two distinct identities and
``pytest.raises(...)`` fails to catch the one the fixture actually raised --
while the guard is working perfectly. ``BLANKED_CREDENTIALS`` next door survives
the same split only because a tuple of strings compares by value.

One plain module, imported by both, so there is one class.
"""


class NetworkUsedInTests(BaseException):
    """Raised when a test reaches for the network. Deliberately NOT ``Exception``.

    Every outbound call site in the service layer catches ``Exception`` so a dead
    upstream degrades instead of 500ing -- correct in production, and fatal to a
    guard here. An ``AssertionError`` was swallowed by exactly those handlers:
    the app took its offline path, the test passed, and the connection attempt
    still went out. Deriving from ``BaseException`` walks through them, so a leak
    fails the test that causes it, by name, instead of only showing up as a slow
    run.
    """
