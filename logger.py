"""
Core polling and SQLite logging utilities for Lake Shore instruments.

This module exposes:
- _connect_db: ensure SQLite schema and return a connection
- _insert_sample: insert a single sample row
- _poll_once: poll selected instruments and yield rows
- poll_and_log_sqlite: simple headless logger loop

logger.py also serves as the entry point when run directly; it launches a
minimal interactive CLI (no TUI).
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
BOLD = "\033[1m"
RESET = "\033[0m"
TEMP_LINE_STYLE = "\033[1;33m"
SPINNER_FRAMES = "|/-\\"


def _handle_sigint(signum, frame):
    global STOP
    STOP = True
    print("Stopping after current poll...")


def _connect_db(db_path: str) -> sqlite3.Connection:
    # Ensure parent directory exists
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Longer timeout helps when another writer holds the lock briefly
    # Use IMMEDIATE to acquire the write lock up front on write transactions
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level="IMMEDIATE")
    # Enable WAL mode and set reasonable defaults for durability/perf
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        # Reduce fsyncs while keeping durability acceptable under WAL
        conn.execute("PRAGMA synchronous=NORMAL")
        # Back off a bit on lock contention to play nice with readers
        conn.execute("PRAGMA busy_timeout=15000")  # ms
        if mode and mode[0].lower() != "wal":
            print(f"Warning: requested WAL mode, got {mode[0]!r}")
    except Exception as e:
        print(f"Warning: failed to enable WAL mode: {e}")
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


def _poll_once(
    inst: init_connection.logger,
    sources: set[str] | None = None,
    warnings: list[str] | None = None,
):
    # Use local timezone-aware ISO timestamp (e.g., 2025-09-09T05:12:34-07:00)
    ts = datetime.now().astimezone().isoformat()

    if sources is None or "LS330BB" in sources:
        bb_sp, bb_temp, bb_heat = inst.poll_330BB()
        yield (ts, "LS330BB", "setpoint[K]", bb_sp, None)
        yield (ts, "LS330BB", "temperature[K]", bb_temp, None)
        yield (ts, "LS330BB", "heater[%]", bb_heat, None)

    if sources is None or "LS330SP" in sources:
        sp_sp, sp_temp, sp_heat = inst.poll_330SP()
        yield (ts, "LS330SP", "setpoint[K]", sp_sp, None)
        yield (ts, "LS330SP", "temperature[K]", sp_temp, None)
        yield (ts, "LS330SP", "heater[%]", sp_heat, None)

    if sources is None or "LS336" in sources:
        try:
            res_a, res_b = inst.poll_336()
        except Exception as e:
            if warnings is not None:
                warnings.append(f"Error polling LS336: {e}")
            else:
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


def _format_value(channel: str, value) -> str:
    if isinstance(value, (int, float)):
        try:
            v_str = f"{value:.6g}"
        except Exception:
            v_str = str(value)
    else:
        v_str = "NA"

    return v_str


def _print_poll_block(
    poll_index: int,
    rows: list[tuple[str, str, str, object, str | None]],
    warnings: list[str] | None = None,
):
    header_line = "=" * 60
    print("\n" + header_line)

    poll_ts = rows[0][0] if rows else datetime.now().astimezone().isoformat()
    try:
        dt = datetime.fromisoformat(poll_ts)
        poll_label = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        poll_label = poll_ts

    title = f" Poll #{poll_index} — {poll_label} "
    print(title.center(len(header_line), "="))
    print(header_line)

    if warnings:
        for warning in warnings:
            print(f"{BOLD}! {warning}{RESET}")
        print("-" * len(header_line))

    if not rows:
        print("(No readings returned this cycle)")
        return

    for ts, source, channel, value, _extra in rows:
        try:
            dt = datetime.fromisoformat(ts)
            human_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            human_ts = ts
        value_str = _format_value(channel, value)
        line = f"{human_ts}  {source:<7}  {channel:<18} = {value_str}"
        if "temperature" in channel.lower():
            line = f"{TEMP_LINE_STYLE}{line}{RESET}"
        print(line)


def _countdown(seconds: float):
    if seconds <= 0:
        return

    end_time = time.monotonic() + seconds
    frame_index = 0
    max_width = 0

    while not STOP:
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            break
        spinner = SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]
        frame_index += 1
        msg = f"Next poll in {remaining:4.1f}s {spinner}"
        max_width = max(max_width, len(msg))
        print("\r" + msg.ljust(max_width), end="", flush=True)
        time.sleep(0.2)

    print("\r" + " " * max_width + "\r", end="", flush=True)
    print(flush=True)


def poll_and_log_sqlite(
    interval_sec: int = 10,
    db_path: str = DEFAULT_DB_PATH,
    sources: set[str] | None = None,
):
    """Headless polling loop that writes to SQLite.

    - interval_sec: seconds between polls
    - db_path: SQLite file path
    - sources: optional set of sources to poll (e.g., {"LS330BB", "LS336"})
    """
    signal.signal(signal.SIGINT, _handle_sigint)

    print("Starting logger")
    print(f"- interval: {interval_sec}s")
    print(f"- db: {db_path}")
    if sources:
        print(f"- sources: {', '.join(sorted(sources))}")

    # Open only requested instruments to avoid conflicts with other software
    open_330bb = (sources is None) or ("LS330BB" in sources)
    open_330sp = (sources is None) or ("LS330SP" in sources)
    open_336 = (sources is None) or ("LS336" in sources)

    inst = init_connection.logger(open_330bb=open_330bb, open_330sp=open_330sp, open_336=open_336)
    db = _connect_db(db_path)

    poll_index = 0

    try:
        while not STOP:
            cycle_start = time.monotonic()
            poll_index += 1
            warnings: list[str] = []
            rows = list(_poll_once(inst, sources=sources, warnings=warnings))
            # Write to DB with retry to handle concurrent writer
            max_retries = 5
            backoff = 0.2
            for attempt in range(max_retries):
                try:
                    # Transaction per polling cycle; IMMEDIATE lock requested by connection
                    with db:
                        for row in rows:
                            _insert_sample(db, *row)
                    break
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if ("locked" in msg) or ("busy" in msg):
                        if attempt == max_retries - 1:
                            warnings.append("DB busy/locked after retries; skipping this cycle.")
                            break
                        sleep_s = backoff * (2 ** attempt)
                        warnings.append(f"DB locked; retrying in {sleep_s:.2f}s...")
                        time.sleep(sleep_s)
                        continue
                    else:
                        raise
            _print_poll_block(poll_index, rows, warnings=warnings)

            elapsed = time.monotonic() - cycle_start
            remaining = max(0.0, float(interval_sec) - elapsed)
            if not STOP:
                _countdown(remaining)
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


def _prompt_sources() -> set[str]:
    print("Select instruments to monitor (comma-separated):")
    print("  1) LS330BB")
    print("  2) LS330SP")
    print("  3) LS336")
    raw = input("Choice [blank for all]: ").strip()
    if not raw:
        return {"LS330BB", "LS330SP", "LS336"}
    picks = {s.strip() for s in raw.split(",") if s.strip()}
    mapping = {"1": "LS330BB", "2": "LS330SP", "3": "LS336",
               "LS330BB": "LS330BB", "LS330SP": "LS330SP", "LS336": "LS336"}
    out: set[str] = set()
    for p in picks:
        name = mapping.get(p)
        if name:
            out.add(name)
    if not out:
        print("No valid selection detected; defaulting to all.")
        out = {"LS330BB", "LS330SP", "LS336"}
    return out


def run_cli():
    try:
        iv_raw = os.environ.get("LAKESHORE_INTERVAL", "")
        interval = int(iv_raw) if iv_raw.isdigit() else 10
    except Exception:
        interval = 10
    db_path = DEFAULT_DB_PATH

    print("Lake Shore logger (CLI)")
    print("Press Ctrl+C to stop.")
    sources = _prompt_sources()
    poll_and_log_sqlite(interval_sec=interval, db_path=db_path, sources=sources)


if __name__ == "__main__":
    run_cli()
