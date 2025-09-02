import os
import signal
import sqlite3
import time
from datetime import datetime

import init_connection


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


def _insert_sample(db: sqlite3.Connection, ts: str, source: str, channel: str, value, extra: str | None = None):
    db.execute(
        "INSERT INTO samples (timestamp, source, channel, value, extra) VALUES (?, ?, ?, ?, ?)",
        (ts, source, channel, value, extra),
    )


def _poll_once(inst: init_connection.logger):
    ts = datetime.utcnow().isoformat()

    # Lake Shore 330 BB
    bb_sp, bb_temp = inst.poll_330BB()
    yield (ts, "LS330BB", "setpoint[K]", bb_sp, None)
    yield (ts, "LS330BB", "temperature[K]", bb_temp, None)

    # Lake Shore 330 SP
    sp_sp, sp_temp = inst.poll_330SP()
    yield (ts, "LS330SP", "setpoint[K]", sp_sp, None)
    yield (ts, "LS330SP", "temperature[K]", sp_temp, None)

    # Lake Shore 336 (channels A and B)
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


def poll_and_log_sqlite(interval_sec: int = 15, db_path: str = "C:\\Users\\qris\\py_automations\\data_log\\lakeshore.sqlite3"):
    signal.signal(signal.SIGINT, _handle_sigint)

    print("Welcome!")
    print(f"Starting SQLite logger every {interval_sec}s → {db_path}")

    inst = init_connection.logger()
    db = _connect_db(db_path)

    try:
        while not STOP:
            with db:  # Transaction per polling cycle
                for row in _poll_once(inst):
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
    poll_and_log_sqlite()


# Textual UI wrapper delegated to textual_gui.py for separation of concerns.
def run_monitor(interval_sec: float = 2.0):
    from textual_gui import run_monitor as _run
    _run(interval_sec=interval_sec)
