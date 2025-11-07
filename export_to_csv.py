"""Interactive utility to export logger samples to CSV."""

from __future__ import annotations

import csv
import itertools
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_DB_PATH = os.environ.get("LAKESHORE_DB")


def _prompt(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _maybe_launch_file_dialog(initial: Optional[str] = None) -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.update()
        initialdir = None
        initialfile = None
        if initial:
            initial_path = Path(initial)
            if initial_path.exists():
                initialdir = str(initial_path.parent)
                initialfile = str(initial_path.name)
        path = filedialog.askopenfilename(
            title="Select Lake Shore logger database",
            initialdir=initialdir,
            initialfile=initialfile,
            filetypes=[
                ("SQLite databases", "*.sqlite3 *.db *.sqlite"),
                ("All files", "*.*"),
            ],
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if not path:
        return None
    return path


def _resolve_db_path() -> Path:
    print("Select the SQLite database to export from.")
    if DEFAULT_DB_PATH:
        print(f"Press Enter to use default: {DEFAULT_DB_PATH}")
    print("Type B to browse for a file using a dialog (if available).")

    auto_selected = _maybe_launch_file_dialog(DEFAULT_DB_PATH)
    if auto_selected:
        path = Path(auto_selected)
        if path.exists():
            print(f"Using selected database: {path}")
            return path
        print(f"Selected file does not exist: {auto_selected}")

    while True:
        resp = _prompt("> ").strip()
        if not resp:
            if DEFAULT_DB_PATH:
                path = Path(DEFAULT_DB_PATH)
                if path.exists():
                    return path
                print("Default database does not exist; please choose another path.")
            else:
                print("No default database configured; please enter a path.")
            continue

        if resp.lower() == "b":
            selected = _maybe_launch_file_dialog(DEFAULT_DB_PATH)
            if selected:
                path = Path(selected)
                if path.exists():
                    return path
                print(f"Selected file does not exist: {selected}")
            else:
                print("No file selected or file dialog unavailable.")
            continue

        path = Path(resp)
        if path.exists():
            return path
        print(f"File not found: {path}")


def _parse_date(value: str, *, is_start: bool, tzinfo) -> datetime:
    value = value.strip()
    if not value:
        raise ValueError("Empty date")

    # Try flexible ISO parsing first
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        formats = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            raise

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tzinfo)

    if value and len(value) == 10 and value[4] in "-/.":
        if is_start:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return dt


def _prompt_date_range() -> tuple[Optional[str], Optional[str]]:
    print("Enter the start and end of the date range to export.")
    print("Formats accepted: ISO 8601 (recommended), YYYY-MM-DD, or YYYY-MM-DD HH:MM[:SS].")
    print("Leave blank to export from the beginning or through the latest record.")

    local_tz = datetime.now().astimezone().tzinfo

    start_str = _prompt("Start date/time: ").strip()
    end_str = _prompt("End date/time:   ").strip()

    start_iso: Optional[str] = None
    end_iso: Optional[str] = None

    if start_str:
        try:
            start_dt = _parse_date(start_str, is_start=True, tzinfo=local_tz)
            start_iso = start_dt.isoformat()
        except Exception as exc:
            print(f"Could not parse start date: {exc}")
            return _prompt_date_range()

    if end_str:
        try:
            end_dt = _parse_date(end_str, is_start=False, tzinfo=local_tz)
            end_iso = end_dt.isoformat()
        except Exception as exc:
            print(f"Could not parse end date: {exc}")
            return _prompt_date_range()

    return start_iso, end_iso


def _query_rows(conn: sqlite3.Connection, start: Optional[str], end: Optional[str]) -> Iterable[tuple]:
    sql = "SELECT timestamp, source, channel, value, extra FROM samples"
    clauses = []
    params: list[object] = []

    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += " ORDER BY timestamp"
    return conn.execute(sql, params)


def _default_output_path(db_path: Path, start: Optional[str], end: Optional[str]) -> Path:
    stem = db_path.stem
    suffix = ""
    if start or end:
        def format_label(label: Optional[str], fallback: str) -> str:
            if not label:
                return fallback
            try:
                dt = datetime.fromisoformat(label)
                return dt.strftime("%Y%m%d")
            except Exception:
                return "any"

        start_label = format_label(start, "start")
        end_label = format_label(end, "end")
        suffix = f"_{start_label}-{end_label}"

    return db_path.with_name(f"{stem}{suffix}.csv")


def _write_csv(rows: Iterable[tuple], output_path: Path) -> int:
    count = 0
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "source", "channel", "value", "extra"])
        for row in rows:
            timestamp, source, channel, value, extra = row
            if value is None:
                value_str = ""
            elif isinstance(value, float):
                value_str = f"{value:.9g}"
            else:
                value_str = str(value)
            writer.writerow([timestamp, source, channel, value_str, extra or ""])
            count += 1
    return count


def main(argv: list[str]) -> int:
    print("Lake Shore logger CSV export utility")
    print("-----------------------------------")

    db_path = _resolve_db_path()
    print(f"Using database: {db_path}")

    start_iso, end_iso = _prompt_date_range()

    default_output = _default_output_path(db_path, start_iso, end_iso)
    print(f"Press Enter to use default output: {default_output}")
    output_resp = _prompt("Output CSV path: ").strip()
    output_path = Path(output_resp) if output_resp else default_output

    if output_path.exists():
        confirm = _prompt(f"{output_path} exists. Overwrite? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Aborting export.")
            return 1

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        print(f"Failed to open database: {exc}")
        return 1

    try:
        cursor = _query_rows(conn, start_iso, end_iso)
        iterator = iter(cursor)
        first_row = next(iterator, None)

        if first_row is None:
            print("No rows matched the specified range. Nothing exported.")
            return 0

        export_rows = itertools.chain([first_row], iterator)

        # Write CSV
        count = _write_csv(export_rows, output_path)
    except sqlite3.Error as exc:
        print(f"Database query failed: {exc}")
        return 1
    except OSError as exc:
        print(f"Failed to write CSV: {exc}")
        return 1
    finally:
        conn.close()

    print(f"Exported {count} rows to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
