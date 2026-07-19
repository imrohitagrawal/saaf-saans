"""The scale conversion, pinned against published breakpoints.

Every number in this file is an anchor from a source document, not a value
copied out of the implementation. If the tables are ever edited, these fail --
which is the point: the app renders these figures as measurements, and a
transcription slip would be invisible on screen and wrong in the same voice as
the truth.
"""
import pytest

from saafsaans.services import aqi_scale as s


# --- US EPA inversion ------------------------------------------------------
# Anchors from the EPA 2012 AQI fact sheet, which is the table WAQI's own
# calculator still uses. The 2024 revision moved the AQI-50 point for PM2.5
# from 12.0 to 9.0; inverting with the new table would misstate every reading,
# so the old boundary is asserted deliberately.
@pytest.mark.parametrize("index,expected", [
    (0, 0.0), (50, 12.0), (100, 35.4), (150, 55.4),
    (200, 150.4), (300, 250.4), (400, 350.4), (500, 500.4),
])
def test_epa_pm25_band_edges_inverve_to_published_concentrations(index, expected):
    assert s.concentration(index, "pm25") == expected


@pytest.mark.parametrize("index,expected", [
    (0, 0.0), (50, 54.0), (100, 154.0), (150, 254.0),
    (200, 354.0), (300, 424.0), (400, 504.0), (500, 604.0),
])
def test_epa_pm10_band_edges_invert_to_published_concentrations(index, expected):
    assert s.concentration(index, "pm10") == expected


def test_the_pre_2024_epa_table_is_the_one_in_use():
    """WAQI has not adopted EPA's May 2024 revision. Under the new table AQI 50
    would be 9.0 µg/m3, not 12.0. Using the wrong table would silently inflate
    every low reading by a third."""
    assert s.concentration(50, "pm25") == 12.0
    assert s.concentration(50, "pm25") != 9.0


def test_inversion_is_monotonic():
    previous = -1.0
    for index in range(0, 501, 7):
        value = s.concentration(index, "pm25")
        assert value >= previous
        previous = value


# --- CPCB forward ----------------------------------------------------------
# Anchors from the CPCB Expert Group report "National Air Quality Index",
# breakpoint tables in section 3.5.
@pytest.mark.parametrize("conc,expected", [
    (0, 0), (30, 50), (60, 100), (90, 200), (120, 300), (250, 400),
])
def test_cpcb_pm25_breakpoints_map_to_published_index_edges(conc, expected):
    assert s.cpcb_sub_index(conc, "pm25") == (expected, False)


@pytest.mark.parametrize("conc,expected", [
    (0, 0), (50, 50), (100, 100), (250, 200), (350, 300), (430, 400),
])
def test_cpcb_pm10_breakpoints_map_to_published_index_edges(conc, expected):
    assert s.cpcb_sub_index(conc, "pm10") == (expected, False)


def test_above_the_last_breakpoint_reports_a_floor_not_a_figure():
    """CPCB's top category is published open-ended ("above 250"), so there is
    no upper concentration to interpolate towards. Inventing one would put a
    fabricated precision on the most dangerous readings the app can show."""
    index, beyond = s.cpcb_sub_index(400, "pm25")
    assert beyond is True
    assert index == s.CPCB_SEVERE_INDEX == 401
    # ...and it does not keep climbing with a made-up slope.
    assert s.cpcb_sub_index(900, "pm25") == s.cpcb_sub_index(400, "pm25")


def test_cpcb_aqi_is_the_maximum_of_the_sub_indices():
    """CPCB defines the overall index as the max, not a mean."""
    # PM10 350 -> 300; PM2.5 60 -> 100. The worse one must win and be named.
    assert s.cpcb_aqi(60, 350) == (300, "pm10", False)
    assert s.cpcb_aqi(120, 60) == (300, "pm25", False)


def test_cpcb_aqi_survives_one_missing_pollutant():
    assert s.cpcb_aqi(60, None) == (100, "pm25", False)
    assert s.cpcb_aqi(None, 100) == (100, "pm10", False)
    assert s.cpcb_aqi(None, None) is None


# --- Defensiveness ---------------------------------------------------------
@pytest.mark.parametrize("junk", [None, "", "abc", float("nan"), -5, True, [], {}])
def test_unusable_input_returns_none_rather_than_a_number(junk):
    """A bad feed value must never become a zero. Zero reads as clean air."""
    assert s.concentration(junk, "pm25") is None
    assert s.cpcb_sub_index(junk, "pm25") is None


# --- The two scales really are different -----------------------------------
def test_the_us_and_indian_scales_disagree_enough_to_matter():
    """The defect this module exists to fix: the app showed a US EPA number
    under Indian band names. At Delhi concentrations they are far apart, so
    that was a health-relevant error, not a cosmetic one."""
    # 60 µg/m3 of PM2.5 is the top of CPCB "Satisfactory"...
    assert s.cpcb_sub_index(60, "pm25") == (100, False)
    # ...but sits well into the US scale's "Unhealthy" range.
    epa, _ = s._interpolate(60.0, s.EPA_PM25)
    assert epa > 150


def test_a_real_feed_reading_round_trips_into_something_physically_possible():
    """WAQI reported Anand Vihar as pm25 sub-index 165, pm10 sub-index 118 --
    which, read as concentrations, said there was more PM2.5 than PM10. PM10
    includes PM2.5, so that is impossible. After conversion the ordering is
    right, which is the cheapest available check that the tables are correct."""
    pm25 = s.concentration(165, "pm25")
    pm10 = s.concentration(118, "pm10")
    assert pm10 > pm25
    aqi, dominant, beyond = s.cpcb_aqi(pm25, pm10)
    assert 0 < aqi <= 500
    assert dominant in ("pm25", "pm10")
    assert beyond is False
