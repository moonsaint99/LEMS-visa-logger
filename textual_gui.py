from __future__ import annotations

import sys
from datetime import datetime, timedelta

import init_connection
from logger import _poll_once, _connect_db, _insert_sample


def run_monitor(
    monitor_interval_sec: float = 10.0,
    log_interval_sec: float = 60.0,
    db_path: str = "C:\\Users\\qris\\py_automations\\data_log\\lakeshore.sqlite3",
):
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Header, Footer, DataTable, Static, TextLog, Checkbox, Button
        from textual.reactive import reactive
        from textual import work
    except Exception as exc:  # optional dependency
        raise RuntimeError(
            "The 'textual' package is required for the monitor UI.\n"
            "Install with: pip install textual"
        ) from exc

    class MonitorState:
        def __init__(self, open_330bb: bool, open_330sp: bool, open_336: bool, sources: set[str]):
            self.inst = init_connection.logger(
                open_330bb=open_330bb, open_330sp=open_330sp, open_336=open_336
            )
            self.sources = sources

        def close(self):
            try:
                self.inst.close()
            except Exception:
                pass

        def poll_latest(self):
            ts = datetime.utcnow().strftime("%H:%M:%S")
            results: dict[tuple[str, str], tuple[str, float | None]] = {}
            try:
                for (_ts, source, channel, value, _extra) in _poll_once(self.inst, sources=self.sources):
                    key = (source, channel)
                    results[key] = (ts, value)
            except Exception as e:
                results[("ERROR", "poll")] = (ts, None)
            return results

    class _StreamToTextLog:
        def __init__(self, app: "MonitorApp", log_widget: TextLog):
            self._app = app
            self._log = log_widget
            self._buffer = ""

        def write(self, s: str):
            self._buffer += s
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                ts = datetime.utcnow().strftime("%H:%M:%S")
                text = f"[{ts}] {line}"
                # Post the log line safely to the UI thread
                self._app.call_from_thread(self._log.write_line, text)

        def flush(self):
            if self._buffer:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                text = f"[{ts}] {self._buffer}"
                self._app.call_from_thread(self._log.write_line, text)
                self._buffer = ""

    class MonitorApp(App):
        CSS = ""
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh_now", "Refresh"),
        ]

        polling = reactive(True)

        def __init__(self, monitor_interval: float, log_interval: float, db_path: str):
            super().__init__()
            self.monitor_interval = max(0.2, float(monitor_interval))
            self.log_interval = max(1.0, float(log_interval))
            self.state: MonitorState | None = None
            self.table: DataTable | None = None
            self.row_index: dict[tuple[str, str], int] = {}
            self.status: Static | None = None
            self.log: TextLog | None = None
            self._last_poll: datetime | None = None
            self._last_log: datetime | None = None
            self._orig_stdout = None
            self._orig_stderr = None
            self._db_path = db_path
            self._db = None
            # Selection widgets
            self.sel_text: Static | None = None
            self.chk_330bb: Checkbox | None = None
            self.chk_330sp: Checkbox | None = None
            self.chk_336: Checkbox | None = None
            self.btn_start: Button | None = None
            self._started = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            # Selection panel
            self.sel_text = Static("Select instruments to monitor, then press Start:")
            yield self.sel_text
            self.chk_330bb = Checkbox("LS330BB", value=True, id="ls330bb")
            yield self.chk_330bb
            self.chk_330sp = Checkbox("LS330SP", value=True, id="ls330sp")
            yield self.chk_330sp
            self.chk_336 = Checkbox("LS336 (A & B)", value=True, id="ls336")
            yield self.chk_336
            self.btn_start = Button("Start", id="start")
            yield self.btn_start

            self.status = Static("Last poll: — | Last log: —")
            yield self.status
            self.table = DataTable(zebra_stripes=True)
            self.table.add_columns("Source", "Channel", "Value", "Time (UTC)")
            yield self.table
            self.log = TextLog(highlight=False, wrap=True)
            self.log.border_title = "Logs"
            yield self.log
            yield Footer()

        def on_mount(self) -> None:
            # Replace stdout/stderr with a stream that writes to the TextLog
            if self.log is not None:
                self._orig_stdout, self._orig_stderr = sys.stdout, sys.stderr
                redirect = _StreamToTextLog(self, self.log)
                sys.stdout = redirect  # type: ignore
                sys.stderr = redirect  # type: ignore

            # Only update status ticker before start
            self.set_interval(1.0, self._update_status)

        def _start(self):
            if self._started:
                return
            bbb = self.chk_330bb.value if self.chk_330bb else True
            bsp = self.chk_330sp.value if self.chk_330sp else True
            b36 = self.chk_336.value if self.chk_336 else True
            sources: set[str] = set()
            if bbb:
                sources.add("LS330BB")
            if bsp:
                sources.add("LS330SP")
            if b36:
                sources.add("LS336")

            self.state = MonitorState(bbb, bsp, b36, sources)

            # Seed metric rows based on selection
            metrics: list[tuple[str, str]] = []
            if bbb:
                metrics += [("LS330BB", "setpoint[K]"), ("LS330BB", "temperature[K]")]
            if bsp:
                metrics += [("LS330SP", "setpoint[K]"), ("LS330SP", "temperature[K]")]
            if b36:
                metrics += [
                    ("LS336", "A.setpoint[K]"),
                    ("LS336", "A.temperature[K]"),
                    ("LS336", "B.setpoint[K]"),
                    ("LS336", "B.temperature[K]"),
                ]

            assert self.table is not None
            for m in metrics:
                row_id = self.table.add_row(m[0], m[1], "—", "—")
                self.row_index[m] = row_id

            # Open DB for periodic logging
            try:
                self._db = _connect_db(self._db_path)
                print(f"SQLite logging to {self._db_path}")
            except Exception as e:
                print(f"Failed to open SQLite DB: {e}")

            # Start periodic polling (monitor) and logging
            self.set_interval(self.monitor_interval, self._tick, pause=not self.polling)
            self.set_interval(self.log_interval, self._log_tick)
            self._started = True

            # Hide selection controls
            for w in (self.sel_text, self.chk_330bb, self.chk_330sp, self.chk_336, self.btn_start):
                try:
                    if w is not None:
                        w.remove()
                except Exception:
                    pass

        def _update_status(self) -> None:
            if not self.status:
                return
            poll_str = "—"
            log_str = "—"
            if self._last_poll is not None:
                d = datetime.utcnow() - self._last_poll
                poll_str = f"{int(d.total_seconds())}s ago"
            if self._last_log is not None:
                d = datetime.utcnow() - self._last_log
                log_str = f"{int(d.total_seconds())}s ago"
            self.status.update(f"Last poll: {poll_str} | Last log: {log_str}")

        def action_refresh_now(self) -> None:
            # If not started yet, treat as start
            if not self._started:
                self._start()
            else:
                self._tick()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "start":
                self._start()

        @work(thread=True, exclusive=True)
        def _do_poll(self):
            return self.state.poll_latest()

        async def _tick(self) -> None:
            if not self.state:
                return
            try:
                result = await self._do_poll.wait()
            except Exception:
                return

            table = self.table
            if not table:
                return

            for key, (ts, val) in result.items():
                row = self.row_index.get(key)
                if row is None:
                    row = table.add_row(key[0], key[1], "—", "—")
                    self.row_index[key] = row
                value_str = (
                    f"{val:.6g}" if isinstance(val, (int, float)) and val is not None else ("—" if val is None else str(val))
                )
                table.update_cell(row, 2, value_str)
                table.update_cell(row, 3, ts)

            self._last_poll = datetime.utcnow()

        @work(thread=True, exclusive=True)
        def _do_log(self):
            if self._db is None or not self.state:
                return False
            try:
                with self._db:
                    for row in _poll_once(self.state.inst, sources=self.state.sources):
                        _insert_sample(self._db, *row)
                return True
            except Exception as e:
                print(f"SQLite log error: {e}")
                return False

        async def _log_tick(self) -> None:
            try:
                ok = await self._do_log.wait()
            except Exception:
                ok = False
            if ok:
                self._last_log = datetime.utcnow()

        def on_unmount(self) -> None:
            # Restore stdout/stderr
            if self._orig_stdout is not None:
                sys.stdout = self._orig_stdout  # type: ignore
            if self._orig_stderr is not None:
                sys.stderr = self._orig_stderr  # type: ignore
            self.state.close()
            try:
                if self._db is not None:
                    self._db.close()
            except Exception:
                pass

    app = MonitorApp(monitor_interval=monitor_interval_sec, log_interval=log_interval_sec, db_path=db_path)
    app.run()
