from __future__ import annotations

from datetime import datetime

import init_connection
from logger import _poll_once


def run_monitor(interval_sec: float = 2.0):
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Header, Footer, DataTable, Static
        from textual.reactive import reactive
        from textual import work
    except Exception as exc:  # optional dependency
        raise RuntimeError(
            "The 'textual' package is required for the monitor UI.\n"
            "Install with: pip install textual"
        ) from exc

    class MonitorState:
        def __init__(self):
            self.inst = init_connection.logger()

        def close(self):
            try:
                self.inst.close()
            except Exception:
                pass

        def poll_latest(self):
            ts = datetime.utcnow().strftime("%H:%M:%S")
            results: dict[tuple[str, str], tuple[str, float | None]] = {}
            try:
                for (_ts, source, channel, value, _extra) in _poll_once(self.inst):
                    key = (source, channel)
                    results[key] = (ts, value)
            except Exception:
                results[("ERROR", "poll")] = (ts, None)
            return results

    class MonitorApp(App):
        CSS = ""
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh_now", "Refresh"),
        ]

        polling = reactive(True)

        def __init__(self, interval: float = 2.0):
            super().__init__()
            self.interval = max(0.2, float(interval))
            self.state = MonitorState()
            self.table: DataTable | None = None
            self.row_index: dict[tuple[str, str], int] = {}

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("Lake Shore Monitor (live)")
            self.table = DataTable(zebra_stripes=True)
            self.table.add_columns("Source", "Channel", "Value", "Time (UTC)")
            yield self.table
            yield Footer()

        def on_mount(self) -> None:
            metrics = [
                ("LS330BB", "setpoint[K]"),
                ("LS330BB", "temperature[K]"),
                ("LS330SP", "setpoint[K]"),
                ("LS330SP", "temperature[K]"),
                ("LS336", "A.setpoint[K]"),
                ("LS336", "A.temperature[K]"),
                ("LS336", "B.setpoint[K]"),
                ("LS336", "B.temperature[K]"),
            ]

            assert self.table is not None
            for m in metrics:
                row_id = self.table.add_row(m[0], m[1], "—", "—")
                self.row_index[m] = row_id

            self.set_interval(self.interval, self._tick, pause=not self.polling)

        def action_refresh_now(self) -> None:
            self._tick()

        @work(thread=True, exclusive=True)
        def _do_poll(self):
            return self.state.poll_latest()

        async def _tick(self) -> None:
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

        def on_unmount(self) -> None:
            self.state.close()

    app = MonitorApp(interval=interval_sec)
    app.run()
