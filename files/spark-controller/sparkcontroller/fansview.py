"""Fans: pick a fan, pick a preset or draw a curve, apply. Applying asks for the password once
(polkit), because the service that writes the fan speeds runs as root."""

import copy
from typing import Any, Dict, List, Optional

import tkinter as tk

from . import config
from .app import save_fan_config
from .curve import PRESET_ORDER, PRESETS, fixed_curve
from .curveview import CurveEditor
from .overviewview import board_driver_missing, mode_text
from .text import t
from .ui import make_table
from .viewkit import View, duty_text, rpm_text, temp_text
from .widgets import T, Segmented, Toggle


class FansView(View):
    def __init__(self, app):
        super().__init__(app)
        self.px = app.px
        self.cfg: Dict[str, Any] = self._load()
        self.saved = copy.deepcopy(self.cfg)
        self.current: Optional[str] = None
        self.busy = False
        px = self.px
        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        left = tk.Frame(body, bg=T["bg"])
        left.pack(side="left", fill="y", padx=(0, px(12)))
        self.heading(left, t("fans.list")).pack(anchor="w", pady=(0, px(4)))
        frame, self.tree = make_table(left, ("name",), show="tree")
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("name", width=px(250), stretch=True)
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._picked)
        self.hint = self.note(left, "", px(250))
        self.hint.pack(anchor="w", pady=(px(8), 0))

        right = tk.Frame(body, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True)
        self.title = self.text(right, "", 11, True, T["text"])
        self.title.pack(anchor="w")
        self.live = self.text(right, "", 8, False, T["muted"])
        self.live.pack(anchor="w", pady=(0, px(8)))
        self.controls = tk.Frame(right, bg=T["bg"])
        self.controls.pack(fill="x")
        row = tk.Frame(self.controls, bg=T["bg"])
        row.pack(fill="x", pady=(0, px(8)))
        self.toggle = Toggle(row, t("fans.use_spark"), False, self._toggled, app.font(8))
        self.toggle.pack(side="left")
        self.preset = Segmented(row, [(t(f"preset.{p}").upper(), p) for p in PRESET_ORDER],
                                "balanced", self._preset, app.font(8))
        self.preset.pack(side="left", padx=(px(12), 0))
        row = tk.Frame(self.controls, bg=T["bg"])
        row.pack(fill="x", pady=(0, px(8)))
        self.text(row, t("fans.source").upper(), 7, True, T["muted"]).pack(side="left")
        self.source = Segmented(row, [(t(f"source.{s}").upper(), s) for s in config.SOURCES],
                                "max", self._source, app.font(8))
        self.source.pack(side="left", padx=(px(8), 0))
        self.fixed_row = tk.Frame(self.controls, bg=T["bg"])
        self.text(self.fixed_row, t("fans.fixed").upper(), 7, True, T["muted"]).pack(side="left")
        self.fixed = self._scale(self.fixed_row, self._fixed_moved)
        row = tk.Frame(self.controls, bg=T["bg"])
        row.pack(fill="x", pady=(0, px(8)))
        self.text(row, t("fans.minimum").upper(), 7, True, T["muted"]).pack(side="left")
        self.minimum = self._scale(row, self._minimum_moved)
        self.curve = CurveEditor(right, px(260), app.tkfont(7, False), self._curve_changed,
                                 self._curve_edit)
        self.curve.pack(fill="both", expand=True)
        self.curve_note = self.note(right, t("fans.curve_help"), px(700))
        self.curve_note.pack(anchor="w", pady=(px(4), px(8)))
        bar = tk.Frame(right, bg=T["bg"])
        bar.pack(fill="x")
        self.apply_button = self.button(bar, t("fans.apply"), self.apply, "primary")
        self.apply_button.pack(side="left")
        self.revert_button = self.button(bar, t("fans.revert"), self.revert)
        self.revert_button.pack(side="left", padx=(self.px(8), 0))
        self.release_button = self.button(bar, t("fans.hand_back"), self.hand_back, "danger")
        self.release_button.pack(side="right")
        self.result = self.note(right, "", px(700))
        self.result.pack(anchor="w", pady=(px(6), 0))
        self._set_enabled(False)

    # — helpers —
    def _scale(self, parent: tk.Misc, command) -> tk.Scale:
        scale = tk.Scale(parent, from_=0, to=100, orient="horizontal", showvalue=True,
                         length=self.px(240), command=command, bg=T["bg"], fg=T["text"],
                         troughcolor=T["panel2"], highlightthickness=0, bd=0,
                         activebackground=T["accent"], font=self.app.font(8), sliderrelief="flat")
        scale.pack(side="left", padx=(self.px(8), 0))
        return scale

    def _load(self) -> Dict[str, Any]:
        try:
            return config.load(config.config_path())
        except (config.ConfigError, OSError):
            return config.empty()

    def _entry(self, key: str) -> Dict[str, Any]:
        return self.cfg["fans"].setdefault(key, config.validate_fan({}))

    @property
    def dirty(self) -> bool:
        return self.cfg != self.saved

    def _fan(self, key: Optional[str]):
        for fan, _rpm, _duty in self.app.snap.fans:
            if fan.key == key:
                return fan
        return None

    def _set_enabled(self, on: bool) -> None:
        self.toggle.config(state="normal" if on else "disabled")

    # — events —
    def usb_ready(self) -> None:
        self.refresh()

    def _picked(self, _event=None) -> None:
        picked = self.tree.selection()
        if picked and picked[0] != self.current:
            self.current = picked[0]
            self._show_fan()

    def _show_fan(self) -> None:
        fan = self._fan(self.current)
        if fan is None:
            return
        entry = self._entry(fan.key)
        self.title.config(text=fan.label)
        can = fan.controllable
        self._set_enabled(can)
        self.toggle.set(bool(entry["enabled"]) and can)
        self.preset.set(entry["preset"])
        self.source.set(entry["source"])
        self.fixed.set(entry["fixed"])
        self.minimum.set(entry["min_duty"])
        self._layout(entry, can)
        self.hint.config(text="" if can else t("fans.read_only"))
        self._draw_curve()

    def _layout(self, entry: Dict[str, Any], can: bool) -> None:
        if entry["preset"] == "fixed":
            self.fixed_row.pack(fill="x", pady=(0, self.px(8)), before=self.curve)
        else:
            self.fixed_row.pack_forget()

    def _draw_curve(self) -> None:
        fan = self._fan(self.current)
        if fan is None:
            return
        entry = self._entry(fan.key)
        self.curve.set_points(config.curve_for(entry), entry["preset"] == "custom")

    def _toggled(self, value: bool) -> None:
        if self.current:
            self._entry(self.current)["enabled"] = value
            self._changed()

    def _preset(self, name: str) -> None:
        if not self.current:
            return
        entry = self._entry(self.current)
        entry["preset"] = name
        if name in PRESETS:
            entry["curve"] = [list(p) for p in PRESETS[name]]
        elif name == "fixed":
            entry["curve"] = [list(p) for p in fixed_curve(entry["fixed"])]
        self._layout(entry, True)
        self._draw_curve()
        self._changed()

    def _source(self, name: str) -> None:
        if self.current:
            self._entry(self.current)["source"] = name
            self._changed()

    def _fixed_moved(self, value: str) -> None:
        if not self.current:
            return
        entry = self._entry(self.current)
        if entry["preset"] != "fixed" or float(value) == entry["fixed"]:
            return
        entry["fixed"] = float(value)
        entry["curve"] = [list(p) for p in fixed_curve(entry["fixed"])]
        self._draw_curve()
        self._changed()

    def _minimum_moved(self, value: str) -> None:
        if not self.current:
            return
        entry = self._entry(self.current)
        if float(value) == entry["min_duty"]:
            return
        entry["min_duty"] = min(float(value), entry["max_duty"])
        self._changed()

    def _curve_edit(self) -> bool:
        """Touching a preset's curve turns it into a custom one."""
        if not self.current:
            return False
        entry = self._entry(self.current)
        if entry["preset"] == "fixed":
            return False
        entry["preset"] = "custom"
        self.preset.set("custom")            # none of the four is lit for a custom curve
        self.curve.editable = True
        return True

    def _curve_changed(self, points: List[List[float]]) -> None:
        if self.current:
            entry = self._entry(self.current)
            entry["curve"] = points
            entry["preset"] = "custom"
            self._changed()

    def _changed(self) -> None:
        text = t("fans.unsaved") if self.dirty else ""
        self.result.config(text=text, fg=T["gold"])

    # — saving —
    def _save(self, cfg: Dict[str, Any], done_text: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.app.set_status(t("status.saving"), T["gold"])

        def finished(_value, error) -> None:
            self.busy = False
            if error is None:
                self.saved = copy.deepcopy(self.cfg)
                self.result.config(text=done_text, fg=T["accent"])
                self.app.set_status(t("status.saved"), T["accent"], 4000)
                self.app.glitch.now(self.app.title)
            else:
                self.result.config(text=t("fans.failed", error=str(error)), fg=T["pink"])
                self.app.set_status(t("status.failed"), T["pink"], 6000)
                self.app.glitch.now(self.app.title, strong=True)
        self.app.worker.run(lambda: save_fan_config(cfg), finished)

    def apply(self) -> None:
        cfg = copy.deepcopy(self.cfg)
        # keep only entries that matter: enabled ones, or ones the service must give back
        cfg["fans"] = {k: v for k, v in cfg["fans"].items()
                       if v["enabled"] or k in self.saved["fans"]}
        n = sum(1 for e in cfg["fans"].values() if e["enabled"])
        self._save(cfg, t("fans.applied", n=n) if n else t("fans.applied_none"))

    def revert(self) -> None:
        self.cfg = copy.deepcopy(self.saved)
        self.result.config(text="")
        self._show_fan()

    def hand_back(self) -> None:
        for entry in self.cfg["fans"].values():
            entry["enabled"] = False
        self._show_fan()
        self._save(copy.deepcopy(self.cfg), t("fans.handed_back"))

    # — sampling —
    def refresh(self) -> None:
        snap = self.app.snap
        wanted = [f.key for f, _r, _d in snap.fans]
        if list(self.tree.get_children()) != wanted:
            selected = self.current
            self.tree.delete(*self.tree.get_children())
            for fan, _r, _d in snap.fans:
                self.tree.insert("", "end", iid=fan.key, values=(fan.label,))
            if selected in wanted:
                self.tree.selection_set(selected)
            elif wanted:
                self.tree.selection_set(wanted[0])
                self.current = None
                self._picked()
        if not wanted:
            self.hint.config(text=t("fans.none"))
        elif board_driver_missing(self.app):
            self.hint.config(text=t("hint.board_driver"), fg=T["gold"])
        fan = self._fan(self.current)
        if fan is None:
            return
        for f, rpm, duty in snap.fans:
            if f.key == fan.key:
                temp = snap.temps.get(self._entry(fan.key)["source"])
                self.live.config(text=t("fans.live", rpm=rpm_text(rpm), duty=duty_text(duty),
                                        mode=mode_text(fan, snap.daemon or {}),
                                        temp=temp_text(temp)))
                self.curve.set_live(temp, duty)
