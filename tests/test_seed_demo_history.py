"""The seeded demo history must describe Delhi's day, not the server's.

The generator shapes a diurnal curve so the seeded "worst air" lands in the
early morning, which is what Delhi actually looks like. It read the hour off a
UTC timestamp, so the whole curve sat five and a half hours out of phase and
the peak landed at 11:30 IST -- late morning, heading down towards the
afternoon trough the module's own docstring describes. Nothing crashed and no
test noticed; the demo simply told a plausible lie about the city.
"""
from datetime import datetime, timezone

from saafsaans import seed_demo_history as seed
from saafsaans.services import clock


def _factor_at_ist(hour):
    """The curve's value at a given IST hour, reached through a UTC instant."""
    ist = datetime(2026, 1, 15, hour, 0, tzinfo=clock.IST)
    return seed._diurnal_factor(clock.to_ist(ist.astimezone(timezone.utc)).hour)


def test_the_dirty_peak_is_early_morning_in_delhi():
    """06:00 IST is the maximum, and it beats every other hour of the day."""
    peak = _factor_at_ist(6)
    for hour in range(24):
        if hour != 6:
            assert _factor_at_ist(hour) <= peak, f"{hour}:00 IST beat 06:00 IST"


def test_the_clean_trough_is_the_opposite_phase_in_delhi():
    """18:00 IST is the minimum -- the far side of the same cosine."""
    trough = _factor_at_ist(18)
    for hour in range(24):
        if hour != 18:
            assert _factor_at_ist(hour) >= trough, f"{hour}:00 IST undercut 18:00 IST"


def test_reading_docs_convert_to_ist_before_shaping_the_curve(monkeypatch):
    """The bug was at the call site, so the guard belongs there.

    _reading_docs walks backwards in fixed steps from ``now``, so the hours it
    asks the curve about are fully determined; only the noise added afterwards
    is random. Recording what the curve is ASKED lets this assert the fix
    without touching that randomness.

    A UTC timestamp of 06:00 is 11:30 in Delhi, and must not be shaped as the
    dawn peak. Reading the hour straight off ``ts`` did exactly that.
    """
    asked = []
    monkeypatch.setattr(seed, "_diurnal_factor",
                        lambda hour: asked.append(hour) or 1.0)

    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    assert clock.to_ist(now).hour == 11
    list(seed._reading_docs(now))

    assert asked, "_reading_docs asked the curve nothing"
    assert asked[0] == 11, (
        f"the curve was asked about hour {asked[0]}; 06:00 UTC is 11:30 in "
        f"Delhi, so it must be asked about 11")
    assert set(asked) <= set(range(24))
