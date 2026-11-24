"""Spark RGB: one colour and one effect per device. Saved, and applied again at login."""

from typing import Dict, List, Optional

import tkinter as tk
from tkinter import colorchooser

from . import rgb
from .rgb import EFFECTS, SPEEDS, RgbDevice
from .text import t
from .ui import make_table
from .viewkit import View
from .widgets import T, Segmented

SWATCHES = ("#3de8c8", "#ff2e88", "#22d8ff", "#f4c95d", "#b9a6ff", "#ff4d4d", "#4dff88",
            "#ffffff")


class RgbView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.devices: List[RgbDevice] = []
        self.saved: Dict[str, Dict[str, str]] = rgb.load_saved()
        self.current: Optional[RgbDevice] = None
        self.setting = rgb.clean_setting(None)
        self.scanning = False
        self.scanned = False
        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        left = tk.Frame(body, bg=T["bg"])
        left.pack(side="left", fill="y", padx=(0, px(12)))
        self.heading(left, t("rgb.devices")).pack(anchor="w", pady=(0, px(4)))
        # Packed before the list, from the bottom: a short window shrinks the list (it
        # scrolls) instead of pushing Rescan and the problems off screen.
        self.problems = self.note(left, "", px(270), T["gold"])
        self.problems.pack(side="bottom", anchor="w", pady=(px(6), 0))
        self.rescan_button = self.button(left, t("rgb.rescan"), self.scan)
        self.rescan_button.pack(side="bottom", anchor="w", pady=(px(8), 0))
        frame, self.tree = make_table(left, ("name",), show="tree")
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("name", width=px(270), stretch=True)
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._picked)

        right = tk.Frame(body, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True)
        self.title = self.text(right, t("rgb.scanning"), 11, True)
        self.title.pack(anchor="w")
        self.kind = self.text(right, "", 8, False, T["muted"])
        self.kind.pack(anchor="w", pady=(0, px(10)))
        self.controls = tk.Frame(right, bg=T["bg"])
        self.controls.pack(fill="x")
        self.heading(self.controls, t("rgb.effect")).pack(anchor="w")
        self.effect = Segmented(self.controls, [(t(f"effect.{e}").upper(), e) for e in EFFECTS],
                                "static", self._effect, app.font(8))
        self.effect.pack(anchor="w", pady=(px(4), px(10)))
        self.heading(self.controls, t("rgb.colour")).pack(anchor="w")
        row = tk.Frame(self.controls, bg=T["bg"])
        row.pack(anchor="w", pady=(px(4), px(10)))
        self.swatch = tk.Label(row, text="", width=6, bg=T["accent"], highlightthickness=1,
                               highlightbackground=T["line2"])
        self.swatch.pack(side="left", ipady=px(6))
        self.hex = self.text(row, "#3DE8C8", 9, True)
        self.hex.pack(side="left", padx=px(8))
        for colour in SWATCHES:
            chip = tk.Label(row, text="", width=2, bg=colour, cursor="hand2",
                            highlightthickness=1, highlightbackground=T["line2"])
            chip.pack(side="left", padx=(px(3), 0), ipady=px(4))
            chip.bind("<ButtonRelease-1>", lambda _e, c=colour: self._colour(c))
        self.button(row, t("rgb.pick"), self._pick_colour).pack(side="left", padx=(px(10), 0))
        self.heading(self.controls, t("rgb.speed")).pack(anchor="w")
        self.speed = Segmented(self.controls, [(t(f"speed.{s}").upper(), s) for s in SPEEDS],
                               "normal", self._speed, app.font(8))
        self.speed.pack(anchor="w", pady=(px(4), px(12)))
        bar = tk.Frame(right, bg=T["bg"])
        bar.pack(fill="x")
        self.apply_button = self.button(bar, t("rgb.apply"), self.apply, "primary")
        self.apply_button.pack(side="left")
        self.all_button = self.button(bar, t("rgb.apply_all"), self.apply_all)
        self.all_button.pack(side="left", padx=(px(8), 0))
        self.off_button = self.button(bar, t("rgb.off"), self.lights_off, "danger")
        self.off_button.pack(side="left", padx=(px(8), 0))
        self.result = self.note(right, "", px(700))
        self.result.pack(anchor="w", pady=(px(8), 0))
        self.note(right, t("rgb.note"), px(700)).pack(anchor="w", pady=(px(14), 0))

    # — finding devices —
    def usb_ready(self) -> None:
        if self.winfo_ismapped() and not self.scanned:
            self.scan()

    def refresh(self) -> None:
        if not self.scanned and not self.scanning and self.app.rgb is not None:
            self.scan()

    def scan(self) -> None:
        manager = self.app.rgb
        if manager is None or self.scanning:
            return
        self.scanning = True
        self.title.config(text=t("rgb.scanning"))
        self.kind.config(text="")
        self.app.set_status(t("status.scanning"), T["gold"])

        def found(devices, error) -> None:
            self.scanning, self.scanned = False, True
            self.app.set_status(t("status.watching"), T["accent"])
            self.devices = []
            self.problems.config(text="\n".join(manager.errors) if error is None
                                 else str(error))
            self.tree.delete(*self.tree.get_children())
            for device in devices or []:
                if self.tree.exists(device.key):    # one bad row must not stop the list
                    continue
                self.tree.insert("", "end", iid=device.key, values=(device.name,))
                self.devices.append(device)
            if self.devices:
                self.tree.selection_set(self.devices[0].key)
                self._picked()
            else:
                self.current = None
                self.title.config(text=t("rgb.none"))
                self.kind.config(text="")
        self.app.worker.run(manager.discover, found)

    def _picked(self, _event=None) -> None:
        picked = self.tree.selection()
        device = next((d for d in self.devices if picked and d.key == picked[0]), None)
        if device is None:
            return
        self.current = device
        self.title.config(text=device.name)
        self.kind.config(text=f"{device.kind}  ·  {device.backend}")
        self.setting = rgb.clean_setting(self.saved.get(device.key))
        self._show()

    def _show(self) -> None:
        self.effect.set(self.setting["effect"])
        self.speed.set(self.setting["speed"])
        self.swatch.config(bg=self.setting["color"])
        self.hex.config(text=self.setting["color"].upper())

    # — editing —
    def _effect(self, value: str) -> None:
        self.setting["effect"] = value

    def _speed(self, value: str) -> None:
        self.setting["speed"] = value

    def _colour(self, value: str) -> None:
        self.setting["color"] = value
        if self.setting["effect"] in ("off", "spectrum"):
            self.setting["effect"] = "static"
            self.effect.set("static")
        self._show()

    def _pick_colour(self) -> None:
        chosen = colorchooser.askcolor(color=self.setting["color"], parent=self.winfo_toplevel())
        if chosen and chosen[1]:
            self._colour(chosen[1].lower())

    # — applying —
    def _run(self, jobs, message_ok: str) -> None:
        manager = self.app.rgb
        if manager is None or not jobs:
            return
        self.app.set_status(t("status.applying"), T["gold"])

        def done(results, error) -> None:
            if error is not None:
                results = {d.key: str(error) for d, _s in jobs}
            failed = [(d, results.get(d.key)) for d, _s in jobs if results.get(d.key)]
            for device, setting in jobs:
                if not results.get(device.key):
                    self.saved[device.key] = dict(rgb.clean_setting(setting))
            rgb.save_saved(self.saved)
            if failed:
                names = "; ".join(f"{d.name}: {m}" for d, m in failed)
                self.result.config(text=t("rgb.failed", errors=names), fg=T["pink"])
                self.app.set_status(t("status.failed"), T["pink"], 6000)
                self.app.glitch.now(self.app.title, strong=True)
            else:
                self.result.config(text=message_ok, fg=T["accent"])
                self.app.set_status(t("status.saved"), T["accent"], 4000)
                self.app.glitch.now(self.app.title)
        self.app.worker.run(lambda: manager.apply_many(jobs), done)

    def apply(self) -> None:
        if self.current is not None:
            self._run([(self.current, dict(self.setting))], t("rgb.applied", n=1))

    def apply_all(self) -> None:
        self._run([(d, dict(self.setting)) for d in self.devices],
                  t("rgb.applied", n=len(self.devices)))

    def lights_off(self) -> None:
        off = dict(self.setting, effect="off")
        self.setting["effect"] = "off"
        self.effect.set("off")
        self._run([(d, dict(off)) for d in self.devices], t("rgb.is_off"))
