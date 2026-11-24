"""Settings: which drive gets the copies, when it runs, and how many to keep. Saving goes
through the helper (one password), which checks everything again before writing."""

import json
from typing import Any, Dict, List

import tkinter as tk

from . import config
from .app import human
from .text import t
from .ui import make_table, scrollable
from .viewkit import View
from .widgets import T, Segmented

NONE_ROW = "none"


class SettingsView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))

        self.heading(pad, t("settings.drive")).pack(anchor="w", pady=(0, px(4)))
        frame, self.tree = make_table(pad, ("name", "type", "size", "free", "state"),
                                      show="headings")
        frame.pack(fill="x")
        for column, heading, width, anchor in (
                ("name", t("col.drive"), 300, "w"), ("type", t("col.type"), 110, "w"),
                ("size", t("col.size"), 90, "e"), ("free", t("col.free"), 90, "e"),
                ("state", t("col.state"), 230, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "name")
        self.tree.configure(height=5)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._picked())
        self.note(pad, t("settings.drive_note"), wrap=px(820)).pack(anchor="w", pady=(px(4), 0))
        self.drive_note = self.note(pad, "", wrap=px(820))
        self.drive_note.pack(anchor="w")

        self.heading(pad, t("settings.schedule")).pack(anchor="w", pady=(px(14), px(4)))
        row = tk.Frame(pad, bg=T["bg"])
        row.pack(anchor="w")
        self.every = Segmented(row, [(t("settings.daily").upper(), "daily"),
                                     (t("settings.weekly").upper(), "weekly")],
                               "daily", self._every_changed, app.font(8))
        self.every.pack(side="left")
        self.weekday = Segmented(row, [(t(f"day.{d}").upper(), d) for d in config.WEEKDAYS],
                                 "Sun", lambda _v: None, app.font(8))
        self.at = self.text(row, t("settings.at"), 9, False, T["muted"])
        self.at.pack(side="left", padx=(px(14), px(6)))
        self.time = tk.Entry(row, width=6, font=app.font(10), bg=T["panel"], fg=T["text"],
                             insertbackground=T["accent"], relief="flat", highlightthickness=1,
                             highlightbackground=T["line2"], highlightcolor=T["accent"])
        self.time.pack(side="left")

        self.heading(pad, t("settings.keep")).pack(anchor="w", pady=(px(14), px(4)))
        keep = tk.Frame(pad, bg=T["bg"])
        keep.pack(anchor="w")
        self.keep_local = self._spin(keep, t("settings.keep_here"))
        self.keep_target = self._spin(keep, t("settings.keep_drive"))
        self.note(pad, t("settings.keep_note"), wrap=px(820)).pack(anchor="w", pady=(px(4), 0))

        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(anchor="w", pady=(px(16), 0))
        self.save_button = self.button(bar, t("btn.save"), self.save, "primary")
        self.save_button.pack(side="left")
        self.off_button = self.button(bar, t("btn.turn_off"), self.turn_off)
        self.off_button.pack(side="left", padx=(px(8), 0))
        self.message = self.text(bar, "", 8, False, T["muted"])
        self.message.pack(side="left", padx=(px(14), 0))
        self.note(pad, t("settings.password_note"), wrap=px(820)).pack(anchor="w",
                                                                         pady=(px(6), 0))
        self._rows: List[Any] = []
        self._loaded = False
        self._drive_id = NONE_ROW

    def _spin(self, parent: tk.Misc, text: str) -> tk.Spinbox:
        px = self.app.px
        self.text(parent, text, 9, False, T["muted"]).pack(side="left", padx=(0, px(6)))
        box = tk.Spinbox(parent, from_=1, to=365, width=5, font=self.app.font(10),
                         bg=T["panel"], fg=T["text"], insertbackground=T["accent"],
                         buttonbackground=T["panel2"], relief="flat", highlightthickness=1,
                         highlightbackground=T["line2"], highlightcolor=T["accent"])
        box.pack(side="left", padx=(0, px(18)))
        return box

    # — the form —
    def _every_changed(self, value: str) -> None:
        if value == "weekly":
            self.weekday.pack(side="left", padx=(self.app.px(10), 0), before=self.at)
        else:
            self.weekday.pack_forget()

    def _load(self) -> None:
        cfg = self.app.model.cfg
        sched = cfg["schedule"]
        self.every.set(sched["every"])
        self._every_changed(sched["every"])
        self.weekday.set(sched["weekday"])
        self.time.delete(0, "end")
        self.time.insert(0, sched["time"])
        for box, key in ((self.keep_local, "keep_local"), (self.keep_target, "keep_target")):
            box.delete(0, "end")
            box.insert(0, str(cfg[key]))
        self._drive_id = cfg["target"]["uuid"] if cfg.get("target") else NONE_ROW
        self._loaded = True
        self._rows = []

    def refresh(self) -> None:
        m = self.app.model
        if not self._loaded:
            self._load()
        drives = list(m.drives)
        key = [(d.uuid, d.name, d.fstype, d.free, d.usable, d.mountpoint is not None)
               for d in drives] + [self._drive_id]
        if self._rows != key:
            self._rows = key
            self.tree.delete(*self.tree.get_children())
            self.tree.insert("", "end", iid=NONE_ROW,
                             values=(t("settings.no_drive"), "", "", "", ""))
            for d in drives:
                state = t("drive.ready") if d.usable else t(d.reason or "refuse.other")
                if d.usable and d.mountpoint is None:
                    state = t("drive.ready_unmounted")
                self.tree.insert("", "end", iid=d.uuid, tags=() if d.usable else ("off",),
                                 values=(d.name, d.fstype, human(d.size), human(d.free), state))
            saved = m.cfg.get("target") and m.cfg["target"]["uuid"]
            if saved and saved not in self.tree.get_children():
                self.tree.insert("", "end", iid=saved, tags=("off",), values=(
                    m.cfg["target"].get("label") or saved, m.cfg["target"].get("fstype", ""),
                    "", "", t("drive.unplugged")))
            wanted = self._drive_id if self._drive_id in self.tree.get_children() else NONE_ROW
            self.tree.selection_set(wanted)
        self.off_button.set_enabled(bool(m.cfg.get("enabled")))

    def _picked(self) -> None:
        sel = self.tree.selection()
        if sel:
            self._drive_id = sel[0]
            drive = next((d for d in self.app.model.drives if d.uuid == sel[0]), None)
            note = ""
            if drive is not None and drive.usable:
                note = (t("settings.method_btrfs", name=drive.name) if drive.method == "btrfs"
                        else t("settings.method_rsync", name=drive.name))
            elif drive is not None and drive.reason:
                note = t(drive.reason)
            self.drive_note.config(text=note)

    # — saving —
    def say(self, text: str, colour: str = "") -> None:
        self.message.config(text=text, fg=colour or T["muted"])

    def current_drive(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else self._drive_id

    def _read(self, enabled: bool) -> Dict[str, Any]:
        cfg = json.loads(json.dumps(self.app.model.cfg))
        cfg["enabled"] = enabled
        cfg["schedule"] = {"every": self.every.value, "weekday": self.weekday.value,
                           "time": self.time.get().strip()}
        for key, box in (("keep_local", self.keep_local), ("keep_target", self.keep_target)):
            try:
                cfg[key] = int(box.get().strip())
            except ValueError:
                raise config.ConfigError(t("settings.keep_number")) from None
        drive = next((d for d in self.app.model.drives if d.uuid == self.current_drive()), None)
        if drive is not None:
            cfg["target"] = {"uuid": drive.uuid, "label": drive.name, "fstype": drive.fstype}
        elif self.current_drive() == NONE_ROW:
            cfg["target"] = None
        return config.validate(cfg)

    def _send(self, enabled: bool) -> None:
        try:
            cfg = self._read(enabled)
        except (config.ConfigError, ValueError, KeyError) as exc:
            self.say(t("settings.invalid", error=str(exc)), T["pink"])
            return
        drive = next((d for d in self.app.model.drives if d.uuid == self.current_drive()), None)
        if drive is not None and not drive.usable:
            self.say(t("settings.cannot_use", drive=drive.name), T["pink"])
            return
        self.say(t("status.password"), T["gold"])

        def done(code: int, message: str) -> None:
            if code == 0:
                self.say(t("settings.saved") if enabled else t("settings.turned_off"), T["accent"])
                self._loaded = False
            else:
                self.say(t("settings.not_saved", error=message), T["pink"])
            self.refresh()

        self.app.helper(["save-config"], done, stdin=json.dumps(cfg))

    def save(self) -> None:
        self._send(True)

    def turn_off(self) -> None:
        self._send(False)
