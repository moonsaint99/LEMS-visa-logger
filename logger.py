"""
Core polling and SQLite logging utilities for Lake Shore instruments.

This module exposes:
- _connect_db: ensure SQLite schema and return a connection
- _insert_sample: insert a single sample row
- _poll_once: poll selected instruments and yield rows
- poll_and_log_sqlite: simple headless logger loop

logger.py also serves as the entry point when run directly; it launches the
Textual TUI defined in tui.py.
"""

import os
import signal
import sqlite3
import time
from datetime import datetime

import init_connection


# Default database path (override with LAKESHORE_DB env var if desired)
DEFAULT_DB_PATH = os.environ.get(
    "LAKESHORE_DB", "C:\\Users\\qris\\py_automations\\data_log\\lakeshore.sqlite3"
)


STOP = False


def _handle_sigint(signum, frame):
    global STOP
    STOP = True
    print("Stopping after current poll...")


def _connect_db(db_path: str) -> sqlite3.Connection:
    # Ensure parent directory exists
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            channel TEXT NOT NULL,
            value REAL,
            extra TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_timestamp ON samples(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_source ON samples(source)")
    conn.commit()
    return conn


def _insert_sample(
    db: sqlite3.Connection,
    ts: str,
    source: str,
    channel: str,
    value,
    extra: str | None = None,
):
    db.execute(
        "INSERT INTO samples (timestamp, source, channel, value, extra) VALUES (?, ?, ?, ?, ?)",
        (ts, source, channel, value, extra),
    )


def _poll_once(inst: init_connection.logger, sources: set[str] | None = None):
    ts = datetime.utcnow().isoformat()

    if sources is None or "LS330BB" in sources:
        bb_sp, bb_temp = inst.poll_330BB()
        yield (ts, "LS330BB", "setpoint[K]", bb_sp, None)
        yield (ts, "LS330BB", "temperature[K]", bb_temp, None)

    if sources is None or "LS330SP" in sources:
        sp_sp, sp_temp = inst.poll_330SP()
        yield (ts, "LS330SP", "setpoint[K]", sp_sp, None)
        yield (ts, "LS330SP", "temperature[K]", sp_temp, None)

    if sources is None or "LS336" in sources:
        try:
            res_a, res_b = inst.poll_336()
        except Exception as e:
            print(f"Error polling LS336: {e}")
            res_a = res_b = None

        a_sp = a_temp = b_sp = b_temp = None
        if res_a:
            a_sp, a_temp = res_a
        if res_b:
            b_sp, b_temp = res_b

        yield (ts, "LS336", "A.setpoint[K]", a_sp, None)
        yield (ts, "LS336", "A.temperature[K]", a_temp, None)
        yield (ts, "LS336", "B.setpoint[K]", b_sp, None)
        yield (ts, "LS336", "B.temperature[K]", b_temp, None)


def poll_and_log_sqlite(
    interval_sec: int = 15,
    db_path: str = DEFAULT_DB_PATH,
    sources: set[str] | None = None,
):
    """Headless polling loop that writes to SQLite.

    - interval_sec: seconds between polls
    - db_path: SQLite file path
    - sources: optional set of sources to poll (e.g., {"LS330BB", "LS336"})
    """
    signal.signal(signal.SIGINT, _handle_sigint)

    print("Starting SQLite logger")
    print(f"  interval: {interval_sec}s")
    print(f"  db: {db_path}")
    if sources:
        print(f"  sources: {', '.join(sorted(sources))}")

    # Open only requested instruments to avoid conflicts with other software
    open_330bb = (sources is None) or ("LS330BB" in sources)
    open_330sp = (sources is None) or ("LS330SP" in sources)
    open_336 = (sources is None) or ("LS336" in sources)

    inst = init_connection.logger(open_330bb=open_330bb, open_330sp=open_330sp, open_336=open_336)
    db = _connect_db(db_path)

    try:
        while not STOP:
            with db:  # Transaction per polling cycle
                for row in _poll_once(inst, sources=sources):
                    _insert_sample(db, *row)
            time.sleep(interval_sec)
    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            inst.close()
        except Exception:
            pass
        print("Logger stopped. Resources closed.")


if __name__ == "__main__":
    # Launch the new minimal TUI by default
    from tui import run_tui
    run_tui(monitor_interval_sec=10.0, log_interval_sec=60.0, db_path=DEFAULT_DB_PATH)
