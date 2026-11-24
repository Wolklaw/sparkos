"""The System tab: what this PC is, for support requests. Built when the tab is first opened.
The part that needs programs (rpm-ostree, vulkaninfo, udevadm, kscreen-doctor) is read once on
a thread and fills in when it is ready; the rest is on screen at once."""

import queue
import threading
from datetime import datetime
from typing import Dict, List, Optional

import tkinter as tk

from . import sysinfo
from .core import log
from .host import Host
from .sysinfo import Section
from .text import t
from .ui import scrollable
from .widgets import T, Toggle, WolkButton


class SystemView(tk.Frame):
    def __init__(self, app, host: Optional[Host] = None):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.host = host or Host(app.src)
        px = app.px
        self.cmds: Dict[str, Optional[str]] = {}
        self.sections: List[Section] = []
        self.serials = False
        self.ready = False
        self._done: "queue.Queue[Dict[str, Optional[str]]]" = queue.Queue()
        self.uptime_label: Optional[tk.Label] = None

        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(10), px(6)))
        self.copy_button = WolkButton(bar, t('sys.copy_all'), self.copy_all, app.font(9),
                                      variant="primary")
        self.copy_button.pack(side="left")
        self.serial_toggle = Toggle(bar, t('sys.include_serials'), False, self.set_serials,
                                    app.font(8))
        self.serial_toggle.pack(side="left", padx=(px(10), 0))
        self.note = tk.Label(bar, text="", bg=T["bg"], fg=T["muted"], font=app.font(8),
                             anchor="e")
        self.note.pack(side="right")
        outer, self.inner = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True, padx=(px(14), px(6)), pady=(0, px(10)))
        self.columns = [tk.Frame(self.inner, bg=T["bg"]), tk.Frame(self.inner, bg=T["bg"])]
        self.inner.grid_columnconfigure(0, weight=1, uniform="c")
        self.inner.grid_columnconfigure(1, weight=1, uniform="c")
        self.columns[0].grid(row=0, column=0, sticky="new", padx=(0, px(8)))
        self.columns[1].grid(row=0, column=1, sticky="new", padx=(px(8), px(8)))

        self.build()                                 # the quick part, now
        self.note.config(text=t('sys.reading'))
        threading.Thread(target=self._fetch, daemon=True).start()
        self.after(200, self._wait)

    def _fetch(self) -> None:
        try:
            self._done.put(sysinfo.fetch(self.host))
        except Exception as exc:    # noqa: BLE001 - the tab still shows what /sys gave
            log.warning("system: programs failed: %s", exc)
            self._done.put({})

    def _wait(self) -> None:
        try:
            self.cmds = self._done.get_nowait()
        except queue.Empty:
            self.after(200, self._wait)
            return
        self.ready = True
        self.note.config(text="")
        self.build()
        self.app.glitch.now(self.app.title)

    def build(self) -> None:
        self.sections = sysinfo.build(self.app.src, self.app.system, self.cmds)
        self.render()

    def render(self) -> None:
        app, px = self.app, self.app.px
        for col in self.columns:
            for child in col.winfo_children():
                child.destroy()
        self.uptime_label = None
        loads = [0, 0]
        for section in self.sections:
            rows = [r for r in section.rows if self.serials or not r.secret]
            side = 0 if loads[0] <= loads[1] else 1
            loads[side] += len(rows) + 2
            panel = tk.Frame(self.columns[side], bg=T["line"], padx=1, pady=1)
            panel.pack(fill="x", pady=(0, px(10)))
            body = tk.Frame(panel, bg=T["panel"])
            body.pack(fill="x")
            tk.Label(body, text=section.title.upper(), bg=T["panel"], fg=T["accent"],
                     font=app.font(9), anchor="w").grid(row=0, column=0, columnspan=2,
                                                        sticky="w", padx=px(10),
                                                        pady=(px(8), px(4)))
            body.grid_columnconfigure(1, weight=1)
            for i, row in enumerate(rows, start=1):
                tk.Label(body, text=row.label.upper(), bg=T["panel"], fg=T["muted"],
                         font=app.font(7), anchor="nw", justify="left").grid(
                    row=i, column=0, sticky="nw", padx=(px(10), px(8)), pady=px(2))
                value = tk.Label(body, text=row.value, bg=T["panel"],
                                 fg=T["gold"] if row.secret else T["text"],
                                 font=app.font(9, False), anchor="w", justify="left",
                                 wraplength=px(330))
                value.grid(row=i, column=1, sticky="w", padx=(0, px(10)), pady=px(2))
                if section.key == 'uptime':
                    self.uptime_label = value
            tk.Frame(body, height=px(6), bg=T["panel"]).grid(row=len(rows) + 1, column=0)
        if not self.serials:
            self.note_hidden = tk.Label(self.columns[1], text=t('sys.serials_hidden'),
                                        bg=T["bg"], fg=T["muted"], font=app.font(7),
                                        anchor="w", justify="left", wraplength=px(330))
            self.note_hidden.pack(fill="x")

    def set_serials(self, on: bool) -> None:
        self.serials = on
        self.render()
        self.app.glitch.now(self.app.title)

    def refresh(self) -> None:
        if self.uptime_label is not None:
            text = sysinfo.uptime_text(sysinfo.read_uptime(self.app.src))
            if self.uptime_label.cget('text') != text:
                self.uptime_label.config(text=text)

    def reload(self) -> None:
        threading.Thread(target=self._fetch, daemon=True).start()
        self.after(200, self._wait)

    def report(self) -> str:
        stamp = datetime.now().astimezone()
        when = stamp.strftime('%Y-%m-%d %H:%M ') + (stamp.tzname() or '')
        for section in self.sections:
            if section.key == 'uptime':
                section.rows[0].value = sysinfo.uptime_text(sysinfo.read_uptime(self.app.src))
        return sysinfo.report(self.sections, self.serials, when)

    def copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.report())
        self.app.set_status(t('sys.copied_serials' if self.serials else 'sys.copied'))
        self.app.glitch.now(self.app.title)
