"""The demo seeder must not fabricate air readings.

This file used to test the shape of a synthetic diurnal AQI curve: that the
seeded "worst air" landed in the early morning, which is what Delhi actually
looks like. Those tests were correct about the curve and beside the point about
the product. The curve wrote invented AQI figures into the aqi-readings index --
the index City Pulse prints numbers from and `main._last_real_reading` prints
"We last recorded AQI n here on <date>" from -- with nothing marking them as
fabricated. A well-shaped lie is still a lie, and the app was publishing it as
its own observation.

So the property under test changed with the code. What is guarded now is the
boundary: the seeder may write records of how the APP behaved (telemetry,
security events) and may not write records of what the AIR was.
"""
from datetime import datetime, timezone

import pytest

from saafsaans import seed_demo_history as seed
from saafsaans.services import es, waqi

NOW = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)


def _all_docs():
    return list(seed._telemetry_docs(NOW)) + list(seed._security_docs(NOW))


def test_the_seeder_writes_no_air_readings():
    """The one that matters. Asserted over the index every generator targets,
    not over the names of the generators, so a new writer is covered the day it
    is added rather than the day someone remembers this file."""
    docs = _all_docs()
    assert docs, "the seeder produced no documents; this would prove nothing"
    for doc in docs:
        assert doc["_index"] != es.INDEX_READINGS, doc


def test_the_seeder_has_no_air_reading_writer_left():
    """The generator, the station base table and the curve are gone -- not
    merely disconnected. A disconnected fabricated-number writer pointed at an
    honesty surface is a loaded gun left on the table, which is the reasoning
    that deleted `waqi.SAMPLES`."""
    for name in ("_reading_docs", "STATIONS", "_diurnal_factor"):
        assert not hasattr(seed, name), name


def test_no_seeded_document_carries_an_aqi_field_into_the_readings_index():
    """Belt and braces on the field, not just the index. `aqi_value` on a
    telemetry row is a record of what the app was serving when it answered, and
    it lives in app-telemetry where nothing reads it as the air; `aqi` is the
    readings-index field the reader-facing surfaces print."""
    for doc in _all_docs():
        assert "aqi" not in doc, doc


@pytest.mark.parametrize("doc", _all_docs())
def test_every_seeded_document_names_a_real_index(doc):
    assert doc["_index"] in (es.INDEX_TELEMETRY, es.INDEX_SECURITY), doc


def test_seeded_telemetry_names_only_real_localities():
    """The locality list used to be the keys of the deleted station table, which
    included "Delhi (city)" -- not one of the app's 21 localities. A System view
    filtered by locality would have shown a place the app does not serve."""
    for doc in seed._telemetry_docs(NOW):
        assert doc["locality"] in waqi.LOCALITIES, doc
