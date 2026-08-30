"""Page-load counts by browser width band, in a local SQLite file.

The probe is a CSS media-query beacon: app.css declares one background image
per width band, the browser fetches only the band whose query matches, and
``main.viewport_probe`` counts the request. This module is where the count
lives.

It stores COUNTERS, not events, and that is the whole design. The previous
backing wrote one Elasticsearch document per page load, which grew without
bound, needed a retention policy nobody had written, and carried a per-request
``@timestamp`` that could in principle be joined by time to a telemetry
document holding a session hash. Four rows replace all of that: three counts
and one date saying when counting began.

A per-day key was considered and rejected. It bounds growth just as well, but
it leaves same-day k-anonymity with k = that day's load count, and on a
scaled-to-zero deployment k is routinely 1 -- a day whose single load was
narrow tells you the one session that day was narrow. That REDUCES the join
rather than closing it. ``counting_since`` answers the only question the day
column was wanted for ("for how long"), as one value every reader shares, with
no per-day set to correlate against.

Row growth is structurally impossible: ``band`` is checked against the closed
set of three before it reaches SQL. That, not the rate limiter, is what bounds
this file -- ratelimit's overflow path clears its whole table, so a distributed
flood forgives itself.

Reading and writing are deliberately asymmetric. The WRITER opens read-write
and creates the file; the READER opens ``mode=ro`` and creates nothing. That is
what lets ``bands()`` return None for "no measurement was ever taken" instead
of [] for "measured, and it was zero" -- a reader that opened read-write would
create an empty database on the first /system view and report a measured zero
over a probe that had never run.
"""
import sqlite3
import threading

from . import clock, config

# The closed set a count may be filed under. web.main validates the path
# segment against its own copy before calling here, and a test pins the two
# equal; this second check is what makes "the table can never exceed three
# rows" a property of the STORE rather than of one call site. That bound, not
# the rate limiter, is what caps this file: ratelimit's overflow path clears
# its whole table, so a distributed flood forgives itself.
BANDS = ("narrow", "mid", "wide")

TABLE_COUNTS = "viewport_counts"
TABLE_META = "viewport_meta"
_SINCE_KEY = "counting_since"

# How long a write waits for another writer's lock before giving up. Not a
# tuning knob: without enough of it writes are LOST, and lost silently, because
# record() swallows. Measured with the schema already created, threads x writes
# each, counting what reached the table:
#
#   busy_timeout   16 threads x 200      40 threads x 500      worst wait
#          100ms   3197-3198 / 3200      19964-19966 / 20000       119ms
#          250ms   3200 / 3200            19991-19992 / 20000       287ms
#         1000ms   3200 / 3200            20000 / 20000             879ms
#
# 40 is the number that decides it: every route in main.py is a sync `def`, so
# they share one anyio threadpool whose measured size is 40, and that is the
# concurrency this file can actually meet. 250ms is lossless at 16 and drops
# writes at 40.
#
# The waits are long because a WAL checkpoint stalls a writer for 120-200ms at
# p99.9, so a bound near that figure sits inside the noise. The cost of the
# larger bound is threadpool occupancy, but reaching it needs ANOTHER PROCESS
# holding a write lock -- on a Fly volume attached to one machine, an operator
# with a shell.
BUSY_TIMEOUT_MS = 1000

_SCHEMA = (
    # WITHOUT ROWID on both: the key covers the row, so a rowid table would
    # carry a second B-tree. Measured at 757 rows it halved the file (28,672
    # against 53,248 bytes) at identical latency.
    f"CREATE TABLE IF NOT EXISTS {TABLE_COUNTS} ("
    " band TEXT PRIMARY KEY, count INTEGER NOT NULL) WITHOUT ROWID",
    f"CREATE TABLE IF NOT EXISTS {TABLE_META} ("
    " key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID",
)
_UPSERT = (f"INSERT INTO {TABLE_COUNTS} (band, count) VALUES (?, 1) "
           "ON CONFLICT(band) DO UPDATE SET count = count + 1")
_TOTALS = f"SELECT band, count FROM {TABLE_COUNTS} ORDER BY band"
# OR IGNORE, so the date is written once and every later load leaves it alone.
# A row that moved on each write would be a last-seen timestamp, which is the
# per-load time this design exists not to keep.
_SINCE_INIT = f"INSERT OR IGNORE INTO {TABLE_META} (key, value) VALUES (?, ?)"
_SINCE_READ = f"SELECT value FROM {TABLE_META} WHERE key = ?"

# One connection per thread, and NO process-wide mutex. Every route in main.py
# is a sync `def`, so they all share one anyio threadpool (measured: 40
# tokens). A single connection behind one lock serialises that pool: measured
# with an external write lock held, 16 queued probes took 16.84s wall against
# 1.06s thread-local, because threading.Lock is not FIFO-fair and a thread
# starves behind the convoy. SQLite's own locking already serialises the write;
# adding a Python lock only widens what waits.
_LOCAL = threading.local()
# Bumped by reset(). A thread compares it before reusing its connection, which
# is how a reset reaches connections this thread does not own.
_GENERATION = 0
_GENERATION_LOCK = threading.Lock()
_INIT_LOCK = threading.Lock()
_INITIALISED = None  # (path, generation) whose schema this process has created


def _generation() -> int:
    with _GENERATION_LOCK:
        return _GENERATION


def _initialise(conn) -> None:
    """Create the schema once per process, not once per thread.

    ``CREATE TABLE`` and the ``counting_since`` row are WRITES, and
    ``PRAGMA journal_mode=WAL`` takes a brief exclusive lock. Running them on
    every thread's first write made sixteen threads contend during setup, and
    a raise there cost that thread its increment: measured 3199 of 3200
    recorded, consistently, with the loss hidden by record()'s own except.

    Guarded rather than left to CREATE TABLE IF NOT EXISTS being idempotent,
    because idempotent is not the same as contention-free.
    """
    global _INITIALISED
    key = (config.viewport_db_path(), _generation())
    with _INIT_LOCK:
        if _INITIALISED == key:
            return
        # WAL is persistent in the file header, so this is the one connection
        # that needs to set it.
        conn.execute("PRAGMA journal_mode=WAL")
        for statement in _SCHEMA:
            conn.execute(statement)
        conn.execute(_SINCE_INIT, (_SINCE_KEY, clock.today_ist().isoformat()))
        _INITIALISED = key


def _writer():
    """This thread's write connection, opening it if the path or generation moved."""
    path = config.viewport_db_path()
    generation = _generation()
    held = getattr(_LOCAL, "conn", None)
    if held is not None:
        if _LOCAL.key == (path, generation):
            return held
        _close(held)
        _LOCAL.conn = None
    # timeout=0 because busy_timeout below is the one bound. sqlite3's own
    # `timeout` sets the same pragma, and two names for one number drift.
    conn = sqlite3.connect(path, timeout=0, isolation_level=None,
                           check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    # NORMAL, not FULL. Measured: SIGKILL of a writer mid-flood lost 0 of
    # 133,600 acknowledged ticks and integrity_check returned ok, because in
    # WAL mode a NORMAL commit is already on disk -- only host power loss can
    # take it. FULL costs an fsync per page load and measured 2.3x less
    # throughput for a counter the System view already calls a floor.
    conn.execute("PRAGMA synchronous=NORMAL")
    _initialise(conn)
    _LOCAL.conn = conn
    _LOCAL.key = (path, generation)
    return conn


def _close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def record(band: str) -> None:
    """Count one page load in ``band``. Never raises.

    A page must render whether or not the counter can be written. Every way the
    store can be unavailable -- no volume mounted, a read-only filesystem, a
    corrupt file -- arrives here as an exception and is swallowed, and
    ``bands()`` then reports the absence rather than a zero.

    The parent directory is never created. A production container whose volume
    failed to mount would otherwise create the mount point on the ephemeral
    root, count into it, lose the counts on the next deploy, and show a
    measured figure the whole time. Refusing to create it makes a missing
    volume read as "not being recorded", which is true.
    """
    if band not in BANDS:
        return
    try:
        _writer().execute(_UPSERT, (band,))
    except Exception:
        pass


def _read(query, args=()):
    """Run ``query`` against a read-only connection, or return None.

    Read-only so that reading can never create the file it is asking about, and
    opened per call so no reader pins a WAL snapshot -- a held read stops the
    checkpoint and lets the -wal grow without bound.

    ``immutable=1`` would also avoid creating anything and is deliberately not
    used: measured against a database whose rows were still in the WAL it
    returned "no such table" instead of the true count, turning an unreadable
    store into a silently wrong answer.
    """
    try:
        conn = sqlite3.connect(f"file:{config.viewport_db_path()}?mode=ro",
                               uri=True, timeout=0, isolation_level=None)
    except Exception:
        return None
    try:
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        return conn.execute(query, args).fetchall()
    except Exception:
        return None
    finally:
        _close(conn)


def bands():
    """Counts per band as ``[{"band": ..., "count": ...}]``, or None.

    ``[]`` and ``None`` are different facts and the caller must be able to tell
    them apart. ``[]`` is a store that answered and holds no rows. ``None`` is
    a store that could not be read at all -- never created, absent, corrupt,
    unreadable, or on a filesystem that will not take a WAL.

    Collapsing them is not theoretical: ``[]`` renders as "No page loads
    counted yet", which asserts a MEASURED zero. Before the writer has run
    there is no measurement, so that sentence would be a fabricated absence --
    the defect class this project returns None rather than 0.0 for everywhere
    else.

    A read never blocks on a writer: measured under a held BEGIN IMMEDIATE the
    aggregate returned the last committed state in 0.03ms. So there is no
    "too slow to read" state, and no timeout branch below.
    """
    rows = _read(_TOTALS)
    if rows is None:
        return None
    return [{"band": band, "count": count} for band, count in rows]


def counting_since():
    """The date this store began counting, or None if it could not be read.

    One value, shared by every reader, written once when the store is created.
    It answers "for how long" -- which PLAN-gates Appendix B records the old
    index could not -- without keeping a time against any page load.
    """
    rows = _read(_SINCE_READ, (_SINCE_KEY,))
    return rows[0][0] if rows else None


def reset() -> None:
    """Drop this thread's connection and invalidate every other thread's.

    For tests: the store is process-global, so without this the file a test
    points at is decided by whichever test opened one first.
    """
    global _GENERATION, _INITIALISED
    with _GENERATION_LOCK:
        _GENERATION += 1
    with _INIT_LOCK:
        _INITIALISED = None
    held = getattr(_LOCAL, "conn", None)
    if held is not None:
        _close(held)
        _LOCAL.conn = None
