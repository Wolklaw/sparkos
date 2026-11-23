"""Drivers and firmware. Device firmware (fwupd, LVFS) can be updated here. The kernel, Mesa and
the GPU firmware ship inside the system image, so they are shown, not changed."""

from typing import List

import tkinter as tk

from . import sysinfo
from .fwupd import Fwupd, FwDevice
from .text import t
from .ui import make_table, scrollable
from .viewkit import View
from .widgets import T


class DriversView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.fwupd = Fwupd()
        self.devices: List[FwDevice] = []
        self.updates: List[FwDevice] = []
        self.loaded = False
        self.busy = False
        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))

        self.heading(pad, t("drivers.firmware")).pack(anchor="w")
        self.note(pad, t("drivers.firmware_note"), px(860)).pack(anchor="w", pady=(0, px(6)))
        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(fill="x", pady=(0, px(6)))
        self.check_button = self.button(bar, t("drivers.check"), self.check)
        self.check_button.pack(side="left")
        self.install_button = self.button(bar, t("drivers.install"), self.install, "primary")
        self.install_button.pack(side="left", padx=(px(8), 0))
        self.status = self.note(bar, "", px(520))
        self.status.pack(side="left", padx=(px(12), 0))
        frame, self.tree = make_table(pad, ("name", "version", "state"), show="headings")
        for column, heading, width, anchor in (
                ("name", t("col.device"), 360, "w"), ("version", t("col.version"), 160, "w"),
                ("state", t("col.state"), 260, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "name")
        self.tree.configure(height=9)
        frame.pack(fill="x")
        self.detail = self.note(pad, "", px(860))
        self.detail.pack(anchor="w", pady=(px(6), 0))
        self.tree.bind("<<TreeviewSelect>>", self._picked)

        self.heading(pad, t("drivers.system")).pack(anchor="w", pady=(px(16), 0))
        self.note(pad, t("drivers.system_note"), px(860)).pack(anchor="w", pady=(0, px(6)))
        self.system = tk.Frame(pad, bg=T["bg"])
        self.system.pack(fill="x")
        self.heading(pad, t("drivers.bios")).pack(anchor="w", pady=(px(16), px(4)))
        self.bios = tk.Frame(pad, bg=T["bg"])
        self.bios.pack(fill="x")
        self.note(pad, t("drivers.bios_note"), px(860)).pack(anchor="w", pady=(px(6), 0))
        self._versions()
        self._set_buttons()

    def _rows(self, frame: tk.Frame, rows) -> None:
        for child in frame.winfo_children():
            child.destroy()
        for i, (name, value) in enumerate(rows):
            self.text(frame, name, 9, False, T["muted"]).grid(row=i, column=0, sticky="w",
                                                              padx=(0, self.app.px(20)))
            self.text(frame, value or t("drivers.unknown"), 9, True,
                      T["text"] if value else T["dim"]).grid(row=i, column=1, sticky="w")

    def _versions(self) -> None:
        rows = [(t(f"drivers.{key}"), value) for key, value in sysinfo.system_versions()]
        self._rows(self.system, rows)
        info = sysinfo.bios()
        self._rows(self.bios, [(t("drivers.board"), info["board"]),
                               (t("drivers.bios_version"), info["version"]),
                               (t("drivers.bios_date"), info["date"]),
                               (t("drivers.bios_vendor"), info["vendor"])])

    def _set_buttons(self) -> None:
        ok = self.fwupd.available and not self.busy
        self.check_button.set_enabled(ok)
        self.install_button.set_enabled(ok and bool(self.updates))

    # — firmware —
    def refresh(self) -> None:
        if not self.loaded and not self.busy:
            self.loaded = True
            self.load()

    def _say(self, text: str, colour: str = "") -> None:
        self.status.config(text=text, fg=colour or T["muted"])

    def load(self) -> None:
        if not self.fwupd.available:
            self._say(t("drivers.no_fwupd"), T["gold"])
            return
        self.busy = True
        self._set_buttons()
        self._say(t("drivers.reading"))

        def job():
            return self.fwupd.devices(), self.fwupd.updates()

        def done(value, error) -> None:
            self.busy = False
            if error is not None:
                self._say(t("drivers.failed", error=str(error)), T["pink"])
            else:
                self.devices, self.updates = value
                self._fill()
            self._set_buttons()
        self.app.worker.run(job, done)

    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        pending = {d.id: d.releases[0].version for d in self.updates if d.releases}
        for i, device in enumerate(self.devices):
            if device.id in pending:
                state, tag = t("drivers.update_to", version=pending[device.id]), ("busy",)
            elif device.updatable:
                state, tag = t("drivers.up_to_date"), ()
            else:
                state, tag = t("drivers.not_updatable"), ("off",)
            self.tree.insert("", "end", iid=str(i), values=(device.title, device.version, state),
                             tags=tag)
        if self.updates:
            self._say(t("drivers.n_updates", n=len(self.updates)), T["gold"])
        else:
            self._say(t("drivers.none_pending"), T["accent"])

    def _picked(self, _event=None) -> None:
        picked = self.tree.selection()
        if not picked:
            return
        device = self.devices[int(picked[0])]
        release = next((d.releases[0] for d in self.updates if d.id == device.id and d.releases),
                       None)
        lines = [device.summary] if device.summary else []
        if release:
            lines.append(t("drivers.release", version=release.version))
            if release.description:
                lines.append(release.description)
        if device.needs_reboot:
            lines.append(t("drivers.reboot"))
        self.detail.config(text="\n".join(lines))

    def check(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_buttons()
        self._say(t("drivers.checking"))
        self.app.set_status(t("status.checking"), T["gold"])

        def job():
            self.fwupd.refresh()
            return self.fwupd.devices(), self.fwupd.updates()

        def done(value, error) -> None:
            self.busy = False
            self.app.set_status(t("status.watching"), T["accent"])
            if error is not None:
                self._say(t("drivers.failed", error=str(error)), T["pink"])
                self.app.glitch.now(self.app.title, strong=True)
            else:
                self.devices, self.updates = value
                self._fill()
            self._set_buttons()
        self.app.worker.run(job, done)

    def install(self) -> None:
        if self.busy or not self.updates:
            return
        self.busy = True
        self._set_buttons()
        self._say(t("drivers.installing"), T["gold"])
        self.app.set_status(t("status.updating"), T["gold"])

        def done(value, error) -> None:
            self.busy = False
            self.app.set_status(t("status.watching"), T["accent"])
            if error is not None:
                self._say(t("drivers.failed", error=str(error)), T["pink"])
                self.app.glitch.now(self.app.title, strong=True)
            else:
                self._say(t("drivers.installed", detail=value or ""), T["accent"])
                self.app.glitch.now(self.app.title)
                self.loaded = False
            self._set_buttons()
            if error is None:
                self.refresh()
        self.app.worker.run(self.fwupd.update, done)
