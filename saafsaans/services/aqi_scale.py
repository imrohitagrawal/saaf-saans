"""Turn WAQI's US-EPA AQI sub-indices into concentrations, and concentrations
into India's CPCB National AQI.

Why this module exists
----------------------
The app consumed ``data.iaqi.pm25.v`` from the WAQI feed and rendered it with
the literal unit label ``µg/m³``. It is not a concentration. WAQI's own field
documentation says so outright -- "Individual AQI for the PM2.5"
(https://aqicn.org/json-api/doc/) -- and the feed proves it: across a sample of
237 stations worldwide, the sub-index of the dominant pollutant equalled
``data.aqi`` in every single case, and 91% of stations reported a PM2.5 figure
*higher* than their PM10 figure, which is impossible for mass concentrations
because PM10 includes PM2.5 by definition.

The scale was wrong too. The app labelled the number "CPCB" and bucketed it
with CPCB band boundaries. WAQI publishes on the US EPA scale worldwide, and
says so specifically for India: "On Januray 8th 2016, the AQI scale used on the
World Air Quality Index project for all stations in India has been updated to
better align with the US EPA Standard", and "if you notice any difference
between the values published on India's new National Air Quality Index System
and the World Air Quality Index project, this is very likely the reason"
(https://aqicn.org/faq/2015-05-15/india-national-air-quality-index/).

The two scales are not interchangeable. 60 µg/m³ of PM2.5 is CPCB 100
"Satisfactory" and US EPA ~154 "Unhealthy". The CPCB scale has no "Unhealthy
for Sensitive Groups"; the EPA scale has no "Satisfactory" or "Severe".

So the feed value is inverted back to a concentration through the EPA table
WAQI actually uses, and the concentration is then put through the CPCB table.
Delhi residents see CPCB numbers everywhere else; giving them a US number under
Indian band names was the worst of both.

What this module does NOT claim
-------------------------------
``cpcb_aqi`` is computed from PM2.5 and PM10 only. CPCB's own method uses up to
eight pollutants and requires at least three, one of which must be a
particulate. This is therefore a *particulate-only* CPCB-scale index, and every
surface that shows it says so. In Delhi particulates dominate almost always, so
it is close in practice -- but "close in practice" is a reason to disclose, not
a reason to round up to "the CPCB AQI".

Sources
-------
CPCB: Central Pollution Control Board, Expert Group final report "National Air
Quality Index" (2014), sections 2.2.1 (pp. 9-10) and 3.5 (p. 44).
https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf

US EPA (2012 breakpoints, superseded in 2024 but still what WAQI's own
calculator uses): https://www.epa.gov/sites/default/files/2016-04/documents/2012_aqi_factsheet.pdf
"""

# --- Breakpoint tables ----------------------------------------------------
# Rows are (conc_low, conc_high, index_low, index_high).
#
# The published tables are written discretely -- EPA's PM2.5 "Moderate" row
# starts at 12.1 where "Good" ends at 12.0 -- which leaves a hairline gap that
# makes interpolation ambiguous. Every row below closes that gap by starting at
# the previous row's upper bound. The resulting index differs from the official
# discrete convention by less than one point, and the alternative is a function
# with holes in its domain.

# US EPA PM2.5, 24-hour, µg/m3. The 2012 table, NOT the May 2024 revision:
# WAQI's public calculator still uses the old breakpoints (AQI 50 at 12.0, not
# at 9.0), so inverting with the new table would misstate every reading.
EPA_PM25 = [
    (0.0, 12.0, 0, 50),
    (12.0, 35.4, 50, 100),
    (35.4, 55.4, 100, 150),
    (55.4, 150.4, 150, 200),
    (150.4, 250.4, 200, 300),
    (250.4, 350.4, 300, 400),
    (350.4, 500.4, 400, 500),
]

# US EPA PM10, 24-hour, µg/m3.
EPA_PM10 = [
    (0, 54, 0, 50),
    (54, 154, 50, 100),
    (154, 254, 100, 150),
    (254, 354, 150, 200),
    (354, 424, 200, 300),
    (424, 504, 300, 400),
    (504, 604, 400, 500),
]

# CPCB PM2.5 and PM10, 24-hour, µg/m3. CPCB's formula reduces the lower index
# bound by one wherever it exceeds 50 (report s2.2.1), which is exactly what
# closing the gaps below does.
CPCB_PM25 = [
    (0, 30, 0, 50),
    (30, 60, 50, 100),
    (60, 90, 100, 200),
    (90, 120, 200, 300),
    (120, 250, 300, 400),
]
CPCB_PM10 = [
    (0, 50, 0, 50),
    (50, 100, 50, 100),
    (100, 250, 100, 200),
    (250, 350, 200, 300),
    (350, 430, 300, 400),
]

# CPCB's top category is written open-ended ("PM2.5 above 250", "PM10 above
# 430") mapping to 401-500, so the report gives no upper concentration to
# interpolate towards. Rather than invent one, anything above the last
# breakpoint is reported as the bottom of Severe with a flag, and the UI says
# "Severe" instead of pretending to a precision the source does not support.
CPCB_SEVERE_INDEX = 401


def _interpolate(value, table):
    """Segmented linear interpolation of ``value`` through a breakpoint table.

    Returns ``(index, beyond)`` where ``beyond`` is True when the value sits
    above the last published breakpoint and the index is therefore a floor
    rather than a figure.
    """
    for lo, hi, i_lo, i_hi in table:
        if value <= hi:
            span = hi - lo
            if span <= 0:
                return i_lo, False
            return i_lo + (max(value, lo) - lo) * (i_hi - i_lo) / span, False
    return table[-1][3], True


def _invert(index, table):
    """Segmented linear inverse: an index back to the concentration that made it."""
    for lo, hi, i_lo, i_hi in table:
        if index <= i_hi:
            span = i_hi - i_lo
            if span <= 0:
                return float(lo)
            return lo + (max(index, i_lo) - i_lo) * (hi - lo) / span
    return float(table[-1][1])


def _as_number(value):
    """Coerce to float, or None. A bad feed value must not become a zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:  # NaN or negative
        return None
    return number


def concentration(sub_index, pollutant: str):
    """Concentration in µg/m3 behind a WAQI sub-index, or None if unusable.

    ``pollutant`` is ``"pm25"`` or ``"pm10"``. Rounded to one decimal because
    the inversion cannot be more precise than the index it started from -- an
    index is an integer, so a whole band of concentrations maps to each value.
    """
    value = _as_number(sub_index)
    if value is None:
        return None
    table = EPA_PM25 if pollutant == "pm25" else EPA_PM10
    return round(_invert(value, table), 1)


def cpcb_sub_index(conc, pollutant: str):
    """CPCB National AQI sub-index for a concentration, or None if unusable.

    Returns ``(index, beyond_scale)``. ``beyond_scale`` True means the
    concentration is above CPCB's last published breakpoint, so the index is
    the floor of Severe rather than a computed position within it.
    """
    value = _as_number(conc)
    if value is None:
        return None
    table = CPCB_PM25 if pollutant == "pm25" else CPCB_PM10
    index, beyond = _interpolate(value, table)
    if beyond:
        return CPCB_SEVERE_INDEX, True
    return int(round(index)), False


def cpcb_aqi(pm25_conc, pm10_conc):
    """India-scale AQI from particulate concentrations. ``None`` if neither.

    CPCB takes the maximum of the pollutant sub-indices, so that is what this
    does -- but over two pollutants where CPCB uses up to eight and requires at
    least three. Callers must present the result as particulate-only; it is not
    the figure CPCB's own portal would publish for the same station.

    Returns ``(aqi, dominant, beyond_scale)`` -- ``dominant`` being whichever
    particulate drove the number, which is what the reader needs to know.
    """
    parts = []
    for conc, name in ((pm25_conc, "pm25"), (pm10_conc, "pm10")):
        result = cpcb_sub_index(conc, name)
        if result is not None:
            parts.append((result[0], name, result[1]))
    if not parts:
        return None
    parts.sort(key=lambda p: -p[0])
    return parts[0]
