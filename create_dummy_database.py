"""Utility to generate a dummy Lake Shore logger SQLite database for testing."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Tuple

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    channel TEXT NOT NULL,
    value REAL,
    extra TEXT
);
"""

INSERT_SQL = """
INSERT INTO samples (timestamp, source, channel, value, extra)
VALUES (?, ?, ?, ?, ?)
"""

CHANNEL_PROFILES: Tuple[Tuple[str, str, float, float], ...] = (
    ("LS330BB", "setpoint[K]", 80.0, 0.05),
    ("LS330BB", "temperature[K]", 79.2, 0.04),
    ("LS330BB", "heater[%]", 42.0, -0.6),
    ("LS330SP", "setpoint[K]", 85.0, 0.03),
    ("LS330SP", "temperature[K]", 84.1, 0.05),
    ("LS330SP", "heater[%]", 48.0, -0.4),
    ("LS336", "A.setpoint[K]", 110.0, 0.02),
    ("LS336", "A.temperature[K]", 108.7, 0.03),
    ("LS336", "B.setpoint[K]", 112.5, -0.01),
    ("LS336", "B.temperature[K]", 111.9, -0.02),
)


def _generate_rows(
    start: datetime,
    count: int,
    interval: timedelta,
) -> Iterable[tuple[str, str, str, float, None]]:
    for idx in range(count):
        ts = (start + idx * interval).astimezone().isoformat()
        for source, channel, base, delta in CHANNEL_PROFILES:
            yield (ts, source, channel, base + idx * delta, None)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a dummy Lake Shore logger SQLite database with sample data.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="dummy-logger.sqlite3",
        help="Destination SQLite file (default: dummy-logger.sqlite3)",
    )
    parser.add_argument(
        "--start",
        metavar="ISO_TIMESTAMP",
        help="Start timestamp (default: now minus 2 days, in local time)",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=8,
        help="Number of sample timestamps to generate (default: 8)",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=6.0,
        help="Hours between each sample timestamp (default: 6)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser.parse_args()


def _resolve_start(start_arg: str | None) -> datetime:
    if not start_arg:
        return datetime.now().astimezone() - timedelta(days=2)

    try:
        parsed = datetime.fromisoformat(start_arg)
    except ValueError as exc:
        raise SystemExit(f"Could not parse --start value {start_arg!r}: {exc}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def main() -> None:
    args = _parse_args()

    db_path = Path(args.path).expanduser().resolve()
    if db_path.exists():
        if args.force:
            db_path.unlink()
        else:
            raise SystemExit(
                f"Refusing to overwrite existing file {db_path}. Use --force to replace it."
            )

    start_dt = _resolve_start(args.start)
    interval = timedelta(hours=args.interval_hours)

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
            rows = list(_generate_rows(start_dt, args.points, interval))
            conn.executemany(INSERT_SQL, rows)
    finally:
        conn.close()

    print(
        f"Created {db_path} with {args.points} timestamps and "
        f"{len(CHANNEL_PROFILES) * args.points} sample rows."
    )


if __name__ == "__main__":
    main()

