"""The viewport counter store: what it counts, and what it refuses to say.

The probe is a CSS media-query beacon and that half is unchanged. This file
covers the backing: a local SQLite file holding one running count per width
band, replacing an Elasticsearch index that held one document per page load.

The distinction these tests exist to protect is between a store that answered
and holds nothing (``[]``, "no page loads counted yet") and a store that could
not be read at all (``None``, "not being recorded"). Collapsing them prints a
measured zero over a probe that never ran.
"""
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from saafsaans.services import config, viewport


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the store at a fresh file that does not exist yet."""
    path = tmp_path / "counts.sqlite3"
    monkeypatch.setenv(config.VIEWPORT_DB_ENV, str(path))
    viewport.reset()
    yield path
    viewport.reset()


def _totals(rows):
    return {row["band"]: row["count"] for row in (rows or [])}


# --- the counter -----------------------------------------------------------
def test_a_recorded_load_becomes_a_count(store):
    viewport.record("narrow")
    viewport.record("narrow")
    viewport.record("wide")
    assert _totals(viewport.bands()) == {"narrow": 2, "wide": 1}


def test_the_store_holds_a_count_per_band_and_no_row_per_load(store):
    """The whole point of the swap. The Elasticsearch design wrote one document
    per page load, which grew for ever and carried a per-request timestamp that
    could be joined by time to a telemetry row holding a session hash. A
    counter has no per-load row to join and nothing to retain.

    Asserted on the physical table, not on the return value, because the return
    value would look identical if every load were still stored individually.
    """
    for _ in range(50):
        viewport.record("mid")

    rows = sqlite3.connect(store).execute(
        f"SELECT band, count FROM {viewport.TABLE_COUNTS}").fetchall()
    assert rows == [("mid", 50)], rows
    # The partner: 50 loads really were recorded, so the single row is a
    # counter and not a store that dropped 49 writes.
    assert _totals(viewport.bands()) == {"mid": 50}


def test_the_stored_columns_are_exactly_the_band_and_its_count(store):
    """Asserted for EQUALITY rather than screened for suspicious names. A rule
    like "no column whose name contains hash" waves through `referer`,
    `client_id` and `remote`; equality makes any addition a deliberate edit to
    this line, which a reviewer sees."""
    viewport.record("mid")
    columns = {row[1] for row in sqlite3.connect(store)
               .execute(f"PRAGMA table_info({viewport.TABLE_COUNTS})")}
    assert columns == {"band", "count"}, columns
    # No table anywhere in the file may carry a per-load row.
    tables = {row[0] for row in sqlite3.connect(store).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {viewport.TABLE_COUNTS, viewport.TABLE_META}, tables


def test_the_store_records_when_counting_began_and_not_when_a_load_arrived(store):
    """Appendix B's complaint about the old index was that the panel "cannot
    answer 'for how long'". One value answers it. It is written once, at
    creation, so it is a property of the STORE rather than of any page load --
    every reader shares it, so there is no per-load set to correlate with.
    """
    viewport.record("mid")
    first = viewport.counting_since()
    assert first, "the store never recorded when it started counting"

    meta = sqlite3.connect(store).execute(
        f"SELECT key, value FROM {viewport.TABLE_META}").fetchall()
    assert meta == [("counting_since", first)], meta

    # The partner: later loads do not move it, which is what makes it a start
    # date rather than a last-seen timestamp.
    time.sleep(0.01)
    viewport.record("wide")
    viewport.record("narrow")
    assert viewport.counting_since() == first
    assert sqlite3.connect(store).execute(
        f"SELECT COUNT(*) FROM {viewport.TABLE_META}").fetchone()[0] == 1


# --- an unreadable store is never a measured zero --------------------------
def test_a_store_that_was_never_created_is_not_a_measured_zero(store):
    """The distinction the whole module exists for.

    ``[]`` renders as "No page loads counted yet", which asserts a MEASURED
    zero. Before anything has written there is no measurement, and on this
    deployment the likeliest cause of an absent file is a volume that did not
    mount -- so a measured zero there would be a fabricated absence.
    """
    assert not store.exists()
    assert viewport.bands() is None
    assert viewport.counting_since() is None

    # The partner: once the writer has run, an emptied store answers [] rather
    # than None, so both branches are reachable and distinguishable.
    viewport.record("mid")
    assert viewport.bands() == [{"band": "mid", "count": 1}]
    # isolation_level=None, or sqlite3 opens a transaction this never commits
    # and the delete is rolled back when the connection is collected.
    sqlite3.connect(store, isolation_level=None).execute(
        f"DELETE FROM {viewport.TABLE_COUNTS}")
    assert viewport.bands() == []


def test_reading_never_creates_the_store_it_is_asking_about(store):
    """A read-write reader would create an empty database on the first /system
    view and then report a measured zero over a probe that never ran. Opening
    read-only is what keeps the absence signal true."""
    for _ in range(3):
        assert viewport.bands() is None
    assert not store.exists(), "the reader created the database"
    assert not list(store.parent.iterdir()), list(store.parent.iterdir())


# "never created" is deliberately absent: it is the one absent-store shape
# where the WRITE correctly succeeds and creates the file, and it is covered by
# test_a_store_that_was_never_created_is_not_a_measured_zero above.
@pytest.mark.parametrize("break_it, why", [
    (lambda p: p.write_bytes(b"this is not a database" * 40), "corrupt header"),
    (lambda p: p.parent.rmdir(), "parent directory missing"),
])
def test_every_unreadable_shape_reports_absence_and_never_raises(store, break_it,
                                                                 why):
    """Measured signatures, all mapped to the same honest answer.

    ``unable to open database file`` is returned for a missing file, a missing
    parent directory and an unreadable one alike, so the exception cannot tell
    them apart -- which is fine, because the page says the same true thing
    about all three: nothing is being recorded.
    """
    break_it(store)
    assert viewport.bands() is None, why
    assert viewport.counting_since() is None, why
    # The write path must swallow it too: a page renders whether or not the
    # counter can be written.
    viewport.record("mid")
    assert viewport.bands() is None, why


def test_a_read_only_filesystem_degrades_to_silence(store, tmp_path):
    """A WAL database cannot even be READ on a read-only filesystem, because
    SQLite must create the -shm sidecar. Measured: a pure SELECT raises
    ``attempt to write a readonly database``.

    This is the shape a Fly volume mounted root-owned against a uid-1000
    process takes, so it is the failure this deployment is most likely to meet.
    """
    viewport.record("mid")
    assert viewport.bands() == [{"band": "mid", "count": 1}]

    viewport.reset()
    store.parent.chmod(0o555)
    try:
        assert viewport.bands() is None
        viewport.record("wide")
        assert viewport.bands() is None
    finally:
        store.parent.chmod(0o755)
    # The partner: it comes back, so the None above was the filesystem and not
    # a store this test had already destroyed.
    viewport.reset()
    assert viewport.bands() == [{"band": "mid", "count": 1}]


def test_the_reader_is_not_fooled_by_rows_that_are_still_in_the_wal(store):
    """``immutable=1`` would also avoid creating the file and is deliberately
    not used. Measured against a database whose rows were still in the WAL it
    returned "no such table" instead of the true count -- an unreadable store
    turned into a silently wrong answer, which is the exact defect the
    None/[] distinction exists to prevent."""
    for _ in range(50):
        viewport.record("narrow")
    assert (store.parent / (store.name + "-wal")).exists(), "no WAL to be fooled by"
    assert viewport.bands() == [{"band": "narrow", "count": 50}]


# --- concurrency -----------------------------------------------------------
def test_concurrent_writers_lose_nothing(store):
    """The app runs under uvicorn and every route is a sync ``def``, so the
    probe executes in a worker thread and many of them write at once.

    This is the test that bites when ``busy_timeout`` is shortened or removed.
    Measured with none, 16 threads recorded 478 of 3200 -- the rest lost to
    ``database is locked``, which record() swallows, so no timing assertion can
    see the loss.

    Forty threads, not sixteen, and the difference decides the bound: at
    ``busy_timeout=250`` sixteen is lossless and forty drops 8 or 9. Forty is
    also the real figure, being the measured size of the single anyio
    threadpool every sync route in this app shares.
    """
    threads = [threading.Thread(target=lambda: [viewport.record("mid")
                                                for _ in range(250)])
               for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert _totals(viewport.bands()) == {"mid": 40 * 250}


def test_a_second_process_writing_at_the_same_time_loses_nothing(store):
    """Threads share one SQLite library; separate processes do not, and a
    volume outlives the process that made it. Proven across a real process
    boundary rather than assumed from the thread result."""
    import subprocess
    import sys

    root = str(Path(__file__).resolve().parents[1])
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import os,sys;sys.path.insert(0,sys.argv[1]);"
         "os.environ['SAAFSAANS_VIEWPORT_DB']=sys.argv[2];"
         "from saafsaans.services import viewport;"
         "[viewport.record('wide') for _ in range(500)]",
         root, str(store)])
    for _ in range(500):
        viewport.record("wide")
    assert child.wait(timeout=60) == 0

    assert _totals(viewport.bands()) == {"wide": 1000}


# --- the write is bounded, and the bound is real ---------------------------
def test_the_write_is_bounded_when_another_process_holds_the_lock(store):
    """The bound that replaces the Elasticsearch client's ``request_timeout``.

    The old test asserted only that a kwarg had been handed to
    elasticsearch-py, which a client that ignored it would also pass. This
    holds a real write lock and measures.

    The FLOOR is as load-bearing as the ceiling, and that is not obvious:
    setting ``busy_timeout=0`` makes the contended write fail INSTANTLY, which
    a ceiling-only assertion reads as a pass while every contended write is
    silently dropped. Measured, 250 ms blocks about 260 ms and 0 ms returns in
    0.0 ms, so the floor is what separates a bound from no bound at all.
    """
    viewport.record("mid")           # create the file so the blocker can lock it
    blocker = sqlite3.connect(store, timeout=0, isolation_level=None)
    blocker.execute("PRAGMA busy_timeout=0")
    blocker.execute("BEGIN IMMEDIATE")
    blocker.execute(f"INSERT INTO {viewport.TABLE_COUNTS} (band, count) "
                    "VALUES ('narrow', 99) ON CONFLICT(band) DO NOTHING")
    try:
        # Partner one: the lock really is held, so the timing below is contention
        # and not an idle machine.
        rival = sqlite3.connect(store, timeout=0, isolation_level=None)
        rival.execute("PRAGMA busy_timeout=0")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            rival.execute(f"INSERT INTO {viewport.TABLE_COUNTS} (band, count)"
                          " VALUES ('wide', 1)")
        rival.close()

        started = time.monotonic()
        viewport.record("mid")
        elapsed = time.monotonic() - started
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()

    # An ABSOLUTE floor, deliberately not derived from BUSY_TIMEOUT_MS.
    # Scaling it to the constant made this assertion collapse with the thing it
    # guards: setting BUSY_TIMEOUT_MS to 0 made the floor 0 too, so removing
    # the bound entirely left this test green while every contended write was
    # silently dropped. FLOOR pairs with the range asserted in
    # test_the_bound_is_the_pragma_the_module_declares, so the two together
    # cannot both be satisfied by a bound that does not wait.
    FLOOR = 0.5
    assert elapsed >= FLOOR, (
        f"the contended write returned in {elapsed:.3f}s, under the {FLOOR}s "
        "floor -- busy_timeout is not in force, so contended writes are being "
        "dropped instead of waited for")
    assert elapsed < 2.0, (
        f"the contended write held its thread for {elapsed:.3f}s; every route "
        "in this app is a sync def sharing one 40-slot threadpool")

    # Partner two: the contended write was dropped, and the writer still works
    # once the lock is gone -- so the bound above is not simply a broken writer.
    assert _totals(viewport.bands())["mid"] == 1
    viewport.record("mid")
    assert _totals(viewport.bands())["mid"] == 2


def test_the_bound_is_the_pragma_the_module_declares(store):
    """Catches the pragma being set on a connection other than the one used
    for writes, which no timing assertion can see."""
    viewport.record("mid")
    conn = viewport._writer()
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == viewport.BUSY_TIMEOUT_MS
    assert 500 <= viewport.BUSY_TIMEOUT_MS <= 1000, (
        "below 500ms writes are lost under the app's own threadpool width "
        "(measured: 250ms drops 8 or 9 of 20,000 at 40 threads); above 1000ms "
        "a contended write holds one of those 40 slots too long")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_an_uncontended_write_is_far_cheaper_than_the_bound(store):
    """The cost that matters in production. Measured median is about 10 us;
    the assertion is three orders above that so a loaded runner cannot reach
    it, and it still goes red if the write is put back on a network round trip
    or given an fsync per call."""
    viewport.record("mid")
    timings = []
    for _ in range(200):
        started = time.monotonic()
        viewport.record("mid")
        timings.append(time.monotonic() - started)

    timings.sort()
    median = timings[len(timings) // 2]
    assert median < 0.005, f"median write {median * 1000:.3f}ms"
    # The partner: all 201 writes were actually recorded.
    assert _totals(viewport.bands()) == {"mid": 201}


def test_the_store_files_a_count_only_under_a_band_it_knows(store):
    """Row growth is what bounds this file, and it is bounded by the closed
    set rather than by the rate limiter -- ratelimit's overflow path clears its
    whole table, so a distributed flood forgives itself.

    Checked here as well as at the route so the bound belongs to the store and
    not to one call site.
    """
    for rubbish in ("desktop", "", "narrow'; DROP TABLE viewport_counts;--",
                    "NARROW", None, 7):
        viewport.record(rubbish)
    assert viewport.bands() is None, "an unknown band created the store"

    viewport.record("narrow")
    for rubbish in ("desktop", "narrow'; DROP TABLE viewport_counts;--"):
        viewport.record(rubbish)
    assert viewport.bands() == [{"band": "narrow", "count": 1}]


def test_the_route_and_the_store_agree_on_the_bands():
    """Two copies of the same closed set. If they drift, the route accepts a
    band the store silently drops and the panel loses it with no error."""
    from saafsaans.web import main as web_main

    assert web_main.VIEWPORT_BANDS == viewport.BANDS
