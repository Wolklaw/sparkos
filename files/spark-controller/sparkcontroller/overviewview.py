"""Overview: temperatures, every fan with its live speed, and who is controlling them."""

from typing import Any, Dict, List, Tuple

import tkinter as tk

from . import config, sysinfo
from .text import t
from .ui import make_table
from .viewkit import View, duty_text, rpm_text, temp_text
from .widgets import T, GlitchPanel

_NCT = {"checked": False, "present": False}


def board_driver_missing(app) -> bool:
    """True when the kernel can read this board's fan chip but the module isn't loaded."""
    if any(c.name.lower().startswith(("nct", "it87", "it86")) for c in app.hwmon.chips()):
        return False
    if not _NCT["checked"]:
        _NCT["checked"] = True
        _NCT["present"] = sysinfo.kernel_has_module("nct6775")
    return _NCT["present"] and bool(app.hwmon.chips())


def enabled_fans() -> int:
    try:
        return sum(1 for e in config.load(config.config_path())["fans"].values() if e["enabled"])
    except (config.ConfigError, OSError, KeyError):
        return 0


def mode_text(fan, daemon: Dict[str, Any]) -> str:
    report = (daemon or {}).get("fans", {})
    if fan.key in report:
        return t("mode.spark")
    if (daemon or {}).get("errors", {}).get(fan.key):
        return t("mode.error")
    if fan.kind == "hwmon" and not fan.controllable:
        return t("mode.readonly")
    return t("mode.firmware")


class OverviewView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.banner = tk.Label(body, text="", font=app.font(8), fg=T["gold"], bg=T["panel"],
                               anchor="w", justify="left", wraplength=px(900), padx=px(10),
                               pady=px(6), highlightthickness=1, highlightbackground=T["line"])
        row = self.row = tk.Frame(body, bg=T["bg"])
        row.pack(fill="x", pady=(0, px(10)))
        self.tiles: Dict[str, tk.Label] = {}
        self.panels: List[GlitchPanel] = []
        for key in ("cpu", "gpu", "liquid", "profile"):
            panel = GlitchPanel(row, T["panel"])
            panel.pack(side="left", fill="x", expand=True, padx=(0, px(8)))
            self.panels.append(panel)
            self.text(panel.inner, t(f"tile.{key}").upper(), 7, True, T["muted"]).pack(
                anchor="w", padx=px(10), pady=(px(8), 0))
            value = self.text(panel.inner, "--", 15, True, T["accent"])
            value.pack(anchor="w", padx=px(10), pady=(0, px(8)))
            self.tiles[key] = value
        app.glitch.add(*self.panels)
        self.heading(body, t("overview.fans")).pack(anchor="w", pady=(0, px(4)))
        frame, self.tree = make_table(body, ("name", "rpm", "duty", "mode"), show="headings")
        frame.pack(fill="both", expand=True)
        for column, heading, width, anchor in (
                ("name", t("col.fan"), 380, "w"), ("rpm", t("col.speed"), 110, "e"),
                ("duty", t("col.duty"), 90, "e"), ("mode", t("col.control"), 200, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "name")
        self.empty = self.note(body, t("overview.none"))

    def refresh(self) -> None:
        snap = self.app.snap
        for key in ("cpu", "gpu"):
            self.tiles[key].config(text=temp_text(snap.temps.get(key)))
        liquid = snap.temps.get("liquid")
        self.tiles["liquid"].config(text=temp_text(liquid) if liquid is not None
                                    else t("tile.no_liquid"),
                                    fg=T["accent"] if liquid is not None else T["dim"])
        count = len((snap.daemon or {}).get("fans", {}))
        self.tiles["profile"].config(
            text=t("profile.spark", n=count) if snap.daemon and count else t("profile.firmware"),
            fg=T["accent"] if count else T["muted"])
        messages: List[Tuple[str, str]] = []
        if board_driver_missing(self.app):
            messages.append((t("hint.board_driver"), T["gold"]))
        if enabled_fans() and snap.daemon is None:
            messages.append((t("hint.service_off"), T["pink"]))
        if messages:
            self.banner.config(text="\n".join(m for m, _c in messages), fg=messages[0][1])
            self.banner.pack(fill="x", pady=(0, self.app.px(10)), before=self.row)
        else:
            self.banner.pack_forget()
        self._rows(snap)

    def _rows(self, snap) -> None:
        wanted = [f.key for f, _r, _d in snap.fans]
        if list(self.tree.get_children()) != wanted:
            self.tree.delete(*self.tree.get_children())
            for fan, _r, _d in snap.fans:
                self.tree.insert("", "end", iid=fan.key, values=("", "", "", ""))
        for fan, rpm, duty in snap.fans:
            name = f"{fan.label}  ·  {fan.chip}" if fan.chip not in fan.label else fan.label
            self.tree.item(fan.key, values=(name, rpm_text(rpm), duty_text(duty),
                                            mode_text(fan, snap.daemon or {})))
        if snap.fans:
            self.empty.pack_forget()
        else:
            self.empty.pack(anchor="w", pady=self.app.px(8))
