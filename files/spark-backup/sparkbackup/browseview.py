"""Browse: look inside a snapshot and copy a file or folder back. Never overwrites."""

import datetime as dt
import os
from typing import List, Optional

import tkinter as tk

from . import browse as engine
from .app import human, pick_folder
from .text import t
from .ui import make_table
from .viewkit import View
from .widgets import T


class BrowseView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        left = tk.Frame(body, bg=T["bg"], width=px(230))
        left.pack(side="left", fill="y", padx=(0, px(12)))
        left.pack_propagate(False)
        self.heading(left, t("browse.snapshots")).pack(anchor="w", pady=(0, px(4)))
        frame, self.snaps_tree = make_table(left, ("when",), show="headings")
        frame.pack(fill="both", expand=True)
        self.snaps_tree.heading("when", text=t("col.date").upper(), anchor="w")
        self.snaps_tree.column("when", width=px(200), anchor="w")
        self.snaps_tree.bind("<<TreeviewSelect>>", self._pick_snapshot)

        right = tk.Frame(body, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True)
        bar = tk.Frame(right, bg=T["bg"])
        bar.pack(fill="x", pady=(0, px(6)))
        self.up_button = self.button(bar, t("btn.up"), self.up)
        self.up_button.pack(side="left")
        self.path = self.text(bar, "", 9, True, T["accent"])
        self.path.pack(side="left", padx=(px(10), 0))
        frame, self.tree = make_table(right, ("name", "size", "modified"), show="headings")
        frame.pack(fill="both", expand=True)
        for column, heading, width, anchor in (
                ("name", t("col.name"), 340, "w"), ("size", t("col.size"), 100, "e"),
                ("modified", t("col.modified"), 150, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "name")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._buttons())
        self.tree.bind("<Double-1>", self._enter)
        actions = tk.Frame(right, bg=T["bg"])
        actions.pack(fill="x", pady=(px(8), 0))
        self.here_button = self.button(actions, t("btn.restore_here"), self.restore_here, "primary")
        self.here_button.pack(side="left")
        self.to_button = self.button(actions, t("btn.restore_to"), self.restore_to)
        self.to_button.pack(side="left", padx=(px(8), 0))
        self.message = self.note(right, t("browse.help"), wrap=px(640))
        self.message.pack(anchor="w", pady=(px(8), 0))

        self.snap: Optional[engine.Snap] = None
        self.rel = ""
        self.items: List[engine.Entry] = []
        self._rows: List[str] = []
        self._shown = ("", "")
        self.busy = False

    # — the snapshot list and the folder shown —
    def snap_root(self, snap: engine.Snap) -> Optional[str]:
        m = self.app.model
        if snap.local:
            return os.path.join(m.snap_dir, snap.name)
        if snap.copy and m.copy_root:
            return os.path.join(m.copy_root, snap.name)
        return None

    def open(self, name: str) -> None:
        self.rel = ""
        if name in self.snaps_tree.get_children():
            self.snaps_tree.selection_set(name)

    def refresh(self) -> None:
        m = self.app.model
        snaps = engine.snapshots(m.local, m.copies)
        names = [s.name for s in snaps]
        if self._rows != names:
            selection = self.snaps_tree.selection()
            self.snaps_tree.delete(*self.snaps_tree.get_children())
            for s in snaps:
                self.snaps_tree.insert("", "end", iid=s.name,
                                       values=(engine.label(s.when),))
            self._rows = names
            if selection and selection[0] in names:
                self.snaps_tree.selection_set(selection[0])
        sel = self.snaps_tree.selection()
        self.snap = next((s for s in snaps if sel and s.name == sel[0]), None)
        self._list()
        self._buttons()

    def _pick_snapshot(self, _event=None) -> None:
        self.rel = ""
        self.refresh()

    def _list(self) -> None:
        key = (self.snap.name if self.snap else "", self.rel)
        if key == self._shown and self.items:
            return
        self._shown = key
        self.tree.delete(*self.tree.get_children())
        self.items = []
        root = self.snap_root(self.snap) if self.snap else None
        self.path.config(text="/" + self.rel if self.snap else "")
        if self.snap is None:
            self.say(t("browse.help"))
            return
        if root is None:
            self.say(t("browse.not_here"), T["gold"])
            return
        try:
            self.items = engine.entries(root, self.rel)
        except engine.BrowseError as exc:
            self.say(t("browse.cannot_read", error=str(exc)), T["pink"])
            return
        for i, item in enumerate(self.items):
            mark = "▸ " if item.is_dir else ("↪ " if item.is_link else "  ")
            when = dt.datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=str(i), values=(
                mark + item.name, "" if item.is_dir else human(item.size), when))
        if not self.items:
            self.say(t("browse.empty"))

    def selected_rel(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        return "/".join(p for p in (self.rel, self.items[int(sel[0])].name) if p)

    def _enter(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel and self.items[int(sel[0])].is_dir:
            self.rel = self.selected_rel() or ""
            self._list()
            self._buttons()

    def up(self) -> None:
        self.rel = "/".join(self.rel.split("/")[:-1])
        self._list()
        self._buttons()

    def _buttons(self) -> None:
        picked = self.tree.selection() != () and self.snap is not None and not self.busy
        self.here_button.set_enabled(picked)
        self.to_button.set_enabled(picked)
        self.up_button.set_enabled(bool(self.rel))

    # — getting it back —
    def say(self, text: str, colour: str = "") -> None:
        self.message.config(text=text, fg=colour or T["muted"])

    def restore_here(self) -> None:
        rel = self.selected_rel()
        if rel:
            self._restore(rel, engine.original_parent(rel, self.home()), True)

    def home(self) -> str:
        return self.app.source or "/home"

    def restore_to(self) -> None:
        rel = self.selected_rel()
        if not rel:
            return
        folder = pick_folder(self, os.path.expanduser("~"))
        if folder:
            self._restore(rel, folder, False)

    def _restore(self, rel: str, dest: str, beside: bool) -> None:
        root = self.snap_root(self.snap) if self.snap else None
        if root is None or self.snap is None:
            return
        when = self.snap.when
        self.busy = True
        self._buttons()
        self.say(t("browse.copying"), T["gold"])

        def work():
            return engine.restore(root, rel, dest, when, beside)

        def done(value, error) -> None:
            self.busy = False
            if error is not None:
                self.say(t("browse.restore_failed", error=str(error)), T["pink"])
            elif value.errors:
                self.say(t("browse.restored_some", path=value.path, n=len(value.errors)),
                         T["gold"])
            else:
                self.say(t("browse.restored", path=value.path), T["accent"])
            self._buttons()

        self.app.worker.run(work, done)
