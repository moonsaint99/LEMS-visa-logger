from __future__ import annotations

import asyncio
import threading
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Tuple

import init_connection
from logger import _poll_once, _connect_db, _insert_sample


def run_tui(monitor_interval_sec: float = 10.0, log_interval_sec: float = 60.0, db_path: str = \
            "C:\\Users\\qris\\py_automations\\data_log\\lakeshore.sqlite3"):
    try:
        from textual.app import App
        from textual.widgets import Header, Footer, Static, DataTable, Checkbox, Button
    except Exception as exc:
        raise RuntimeError("Textual is required: pip install textual") from exc

    class State:
        def __init__(self, open_330bb: bool, open_330sp: bool, open_336: bool, sources: set[str]):
            self.inst = init_connection.logger(open_330bb=open_330bb, open_330sp=open_330sp, open_336=open_336)
            self.sources = sources
            self.lock = threading.Lock()
            self.series: Dict[Tuple[str, str], Deque[float | None]] = {}

        def close(self):
            try:
                self.inst.close()
            except Exception:
                pass

        def poll(self) -> List[Tuple[str, str, float | None, str]]:
            with self.lock:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                out: List[Tuple[str, str, float | None, str]] = []
                for (_ts, source, channel, value, _extra) in _poll_once(self.inst, self.sources):
                    out.append((source, channel, value, ts))
                    key = (source, channel)
                    dq = self.series.setdefault(key, deque(maxlen=120))
                    dq.append(value if isinstance(value, (int, float)) else None)
                return out

        def log_once(self, db_path: str) -> int:
            with self.lock:
                rows = list(_poll_once(self.inst, self.sources))
            db = _connect_db(db_path)
            inserted = 0
            try:
                with db:
                    for row in rows:
                        _insert_sample(db, *row)
                        inserted += 1
            finally:
                try:
                    db.close()
                except Exception:
                    pass
            return inserted

    def sparkline(vals: Deque[float | None], width: int = 40) -> str:
        if not vals:
            return "".ljust(width)
        # Take last width values
        data = [v for v in list(vals)[-width:]]
        nums = [v for v in data if isinstance(v, (int, float)) and v is not None]
        if not nums:
            return ("·" * min(width, len(data))).ljust(width)
        lo, hi = min(nums), max(nums)
        if hi == lo:
            return ("▆" * min(width, len(data))).ljust(width)
        blocks = "▁▂▃▄▅▆▇█"
        out = []
        for v in data:
            if v is None:
                out.append("·")
            else:
                idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
                out.append(blocks[idx])
        return ("".join(out)).ljust(width)

    class AppUI(App):
        CSS = ""

        def __init__(self, mon_iv: float, log_iv: float, db_path: str):
            super().__init__()
            self.mon_iv = max(1.0, float(mon_iv))
            self.log_iv = max(5.0, float(log_iv))
            self.db_path = db_path
            self.state: State | None = None
            self.spinner = "|/-\\"
            self.spin_idx = 0
            # widgets
            self.sel_text: Static | None = None
            self.chk_330bb: Checkbox | None = None
            self.chk_330sp: Checkbox | None = None
            self.chk_336: Checkbox | None = None
            self.btn_start: Button | None = None
            self.status: Static | None = None
            self.table: DataTable | None = None
            self._last_poll: datetime | None = None
            self._last_log: datetime | None = None

        def compose(self):
            yield Header(show_clock=True)
            self.sel_text = Static("Select instruments, then press Start:")
            yield self.sel_text
            self.chk_330bb = Checkbox("LS330BB", value=True)
            yield self.chk_330bb
            self.chk_330sp = Checkbox("LS330SP", value=True)
            yield self.chk_330sp
            self.chk_336 = Checkbox("LS336 (A & B)", value=True)
            yield self.chk_336
            self.btn_start = Button("Start", id="start")
            yield self.btn_start
            self.status = Static("⏳ Waiting to start…")
            yield self.status
            self.table = DataTable(zebra_stripes=True)
            self.table.add_columns("Metric", "Value", "Sparkline", "Time (UTC)")
            yield self.table
            yield Footer()

        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "start":
                self._start()

        def _start(self):
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
            self.state = State(bbb, bsp, b36, sources)

            # Hide selection widgets
            for w in (self.sel_text, self.chk_330bb, self.chk_330sp, self.chk_336, self.btn_start):
                try:
                    if w is not None:
                        w.remove()
                except Exception:
                    pass

            # Seed rows
            assert self.table is not None
            self.table.clear()
            self.table.add_columns("Metric", "Value", "Sparkline", "Time (UTC)")
            metrics: List[Tuple[str, str]] = []
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
            self._rows: Dict[Tuple[str, str], int] = {}
            for src, ch in metrics:
                rid = self.table.add_row(f"{src}.{ch}", "—", "", "—")
                self._rows[(src, ch)] = rid

            # Intervals
            self.set_interval(1.0, self._tick_status)
            self.set_interval(self.mon_iv, self._schedule_poll)
            self.set_interval(self.log_iv, self._schedule_log)
            # Kick an immediate poll
            self._schedule_poll()

        def _tick_status(self):
            if not self.status:
                return
            spin = self.spinner[self.spin_idx % len(self.spinner)]
            self.spin_idx += 1
            poll_str = "—" if not self._last_poll else f"{(datetime.utcnow()-self._last_poll).seconds}s ago"
            log_str = "—" if not self._last_log else f"{(datetime.utcnow()-self._last_log).seconds}s ago"
            self.status.update(f"{spin} Poll: {poll_str} | Log: {log_str}")

        def _schedule_poll(self):
            if not self.state:
                return
            async def runner():
                try:
                    rows = await asyncio.to_thread(self.state.poll)
                except Exception:
                    rows = []
                self._apply_poll(rows)
            asyncio.create_task(runner())

        def _apply_poll(self, rows: List[Tuple[str, str, float | None, str]]):
            tbl = self.table
            if not tbl:
                return
            for src, ch, val, ts in rows:
                key = (src, ch)
                row = self._rows.get(key)
                if row is None:
                    row = tbl.add_row(f"{src}.{ch}", "—", "", "—")
                    self._rows[key] = row
                # Update value
                val_str = f"{val:.6g}" if isinstance(val, (int, float)) and val is not None else "—"
                tbl.update_cell(row, 1, val_str)
                # Update sparkline
                s = sparkline(self.state.series.get(key, deque()), width=40) if self.state else ""
                tbl.update_cell(row, 2, s)
                # Update time
                tbl.update_cell(row, 3, ts)
            self._last_poll = datetime.utcnow()

        def _schedule_log(self):
            if not self.state:
                return
            async def runner():
                try:
                    inserted = await asyncio.to_thread(self.state.log_once, self.db_path)
                except Exception:
                    inserted = -1
                if inserted >= 0:
                    self._last_log = datetime.utcnow()
            asyncio.create_task(runner())

        def on_unmount(self) -> None:
            try:
                if self.state:
                    self.state.close()
            except Exception:
                pass

    app = AppUI(monitor_interval_sec, log_interval_sec, db_path)
    app.run()

