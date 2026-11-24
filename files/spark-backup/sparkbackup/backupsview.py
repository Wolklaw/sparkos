"""Backups: when the last one ran, when the next is due, and every snapshot with where it is."""

import datetime as dt
import os
from typing import Dict, List, Tuple

import tkinter as tk

from . import config
from .app import human, next_text
from .browse import label, snapshots
from .text import t
from .ui import make_table
from .viewkit import View
from .widgets import T, GlitchPanel

CONFIRM_MS = 4000


def last_text(last) -> Tuple[str, str]:
    """(text, colour) for the 'last backup' tile."""
    if not last:
        return t("tile.never"), T["muted"]
    try:
        when = dt.datetime.strptime(last["time"], "%Y-%m-%d %H:%M:%S")
        text = when.strftime("%Y-%m-%d %H:%M")
    except (KeyError, ValueError, TypeError):
        text = "--"
    return text, T["accent"] if last.get("ok") else T["pink"]


class BackupsView(View):
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
        for key in ("last", "next", "drive", "count"):
            panel = GlitchPanel(row, T["panel"])
            panel.pack(side="left", fill="x", expand=True, padx=(0, px(8)))
            self.panels.append(panel)
            self.text(panel.inner, t(f"tile.{key}").upper(), 7, True, T["muted"]).pack(
                anchor="w", padx=px(10), pady=(px(8), 0))
            value = self.text(panel.inner, "--", 12, True, T["accent"])
            value.pack(anchor="w", padx=px(10), pady=(0, px(8)))
            self.tiles[key] = value
        app.glitch.add(*self.panels)

        bar = tk.Frame(body, bg=T["bg"])
        bar.pack(fill="x", pady=(0, px(8)))
        self.now_button = self.button(bar, t("btn.backup_now"), self.backup_now, "primary")
        self.now_button.pack(side="left")
        self.remove_button = self.button(bar, t("btn.remove"), self.remove, "danger")
        self.remove_button.pack(side="left", padx=(px(8), 0))
        self.browse_button = self.button(bar, t("btn.browse"), self.browse)
        self.browse_button.pack(side="left", padx=(px(8), 0))
        self.message = self.text(bar, "", 8, False, T["muted"])
        self.message.pack(side="left", padx=(px(14), 0))

        frame, self.tree = make_table(body, ("date", "here", "drive"), show="headings")
        frame.pack(fill="both", expand=True)
        for column, heading, width, anchor in (
                ("date", t("col.date"), 320, "w"), ("here", t("col.here"), 160, "center"),
                ("drive", t("col.drive"), 160, "center")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "date")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._buttons())
        self.tree.bind("<Double-1>", lambda _e: self.browse())
        self.empty = self.note(body, t("backups.none"))
        self.confirming = ""
        self._confirm_id = None
        self._rows: List[str] = []
        self.snaps = []

    # — what is shown —
    def selected(self):
        sel = self.tree.selection()
        return next((s for s in self.snaps if sel and s.name == sel[0]), None)

    def refresh(self) -> None:
        m, app = self.app.model, self.app
        text, colour = last_text(m.last)
        self.tiles["last"].config(text=text, fg=colour)
        self.tiles["next"].config(text=next_text(m.cfg),
                                  fg=T["accent"] if m.cfg.get("enabled") else T["muted"])
        if m.cfg.get("target") is None:
            self.tiles["drive"].config(text=t("tile.no_drive"), fg=T["muted"])
        elif m.drive is None:
            self.tiles["drive"].config(text=t("tile.unplugged"), fg=T["gold"])
        else:
            self.tiles["drive"].config(text=m.drive.name, fg=T["accent"] if m.drive.usable
                                       else T["pink"])
        self.tiles["count"].config(text=str(len(m.local)), fg=T["accent"] if m.local
                                   else T["muted"])

        messages: List[Tuple[str, str]] = []
        if m.cfg_error:
            messages.append((t("banner.config", error=m.cfg_error), T["pink"]))
        if not m.layout:
            messages.append((t("banner.layout"), T["pink"]))
        if m.last and not m.last.get("ok") and m.last.get("error"):
            messages.append((t("banner.failed", error=m.last["error"]), T["pink"]))
        elif m.last and m.last.get("copy") == "unplugged":
            messages.append((t("banner.unplugged_last"), T["gold"]))
        if m.cfg.get("target") is not None and m.drive is not None and not m.drive.usable:
            messages.append((t("banner.refused", drive=m.drive.name, why=t(m.drive.reason)
                               if m.drive.reason else ""), T["pink"]))
        if not m.cfg.get("enabled") and not m.cfg_error:
            messages.append((t("banner.off"), T["gold"]))
        if messages:
            self.banner.config(text="\n".join(x for x, _c in messages), fg=messages[0][1])
            self.banner.pack(fill="x", pady=(0, app.px(10)), before=self.row)
        else:
            self.banner.pack_forget()

        self._table()
        self._buttons()

    def _table(self) -> None:
        m = self.app.model
        self.snaps = snapshots(m.local, m.copies)
        wanted = [s.name for s in self.snaps]
        selection = self.tree.selection()
        if self._rows != wanted:
            self.tree.delete(*self.tree.get_children())
            for snap in self.snaps:
                self.tree.insert("", "end", iid=snap.name, values=("", "", ""))
            self._rows = wanted
            if selection and selection[0] in wanted:
                self.tree.selection_set(selection[0])
        latest = wanted[0] if wanted else ""
        for snap in self.snaps:
            when = label(snap.when) + ("  ·  " + t("backups.newest") if snap.name == latest else "")
            here = "●" if snap.local else "·"
            if m.cfg.get("target") is None:
                there = "--"
            elif m.drive is None or not m.drive.mountpoint:
                there = "?" if not snap.copy else "●"
            else:
                there = "●" if snap.copy else "·"
            self.tree.item(snap.name, values=(when, here, there))
        if self.snaps:
            self.empty.pack_forget()
        else:
            self.empty.pack(anchor="w", pady=self.app.px(8))

    def _buttons(self) -> None:
        m = self.app.model
        busy = bool(m.progress)
        snap = self.selected()
        self.now_button.set_enabled(not busy)
        self.remove_button.set_enabled(not busy and snap is not None and snap.local)
        self.browse_button.set_enabled(snap is not None)
        if busy:
            detail = m.progress.get("detail") or ""
            self.message.config(text=t("backups.running", detail=detail).strip(), fg=T["gold"])
        elif self.message.cget("fg") == T["gold"]:
            self.message.config(text="")

    # — actions —
    def say(self, text: str, colour: str = "") -> None:
        self.message.config(text=text, fg=colour or T["muted"])

    def backup_now(self) -> None:
        if not os.path.exists(config.config_path()):
            self.say(t("msg.need_settings"), T["gold"])
            return
        self.say(t("msg.starting"), T["gold"])

        def done(code: int, message: str) -> None:
            self.say(t("msg.started") if code == 0 else t("msg.start_failed", error=message),
                     T["accent"] if code == 0 else T["pink"])
            self.refresh()

        self.app.helper(["start"], done)

    def remove(self) -> None:
        snap = self.selected()
        if snap is None or not snap.local:
            return
        if self.confirming != snap.name:
            self.confirming = snap.name
            self.remove_button.set_text(t("btn.remove_sure"))
            if self._confirm_id:
                self.after_cancel(self._confirm_id)
            self._confirm_id = self.after(CONFIRM_MS, self._unconfirm)
            return
        self._unconfirm()

        def done(code: int, message: str) -> None:
            self.say(t("msg.removed", name=label(snap.when)) if code == 0
                     else t("msg.remove_failed", error=message),
                     T["accent"] if code == 0 else T["pink"])
            self.refresh()

        self.app.helper(["remove-snapshot", snap.name], done)

    def _unconfirm(self) -> None:
        self.confirming = ""
        if self._confirm_id:
            self.after_cancel(self._confirm_id)
            self._confirm_id = None
        self.remove_button.set_text(t("btn.remove"))

    def browse(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        self.app.show("browse")
        self.app.views["browse"].open(snap.name)
