"""The Health tab: SMART for the picked drive. Looking is free and safe on every drive (D: and
the system disk included); "Read again" and "Short test" ask udisks, which asks polkit."""

import time
from typing import Dict, List, Optional

import tkinter as tk

from .lang import local_units
from .model import Node
from .smart import Health, summarise
from .text import t
from .ui import make_table
from .viewkit import View, error_text, size_text
from .widgets import T

VERDICT_COLOUR = {'good': T["accent"], 'warning': T["gold"], 'failing': T["pink"],
                  'unknown': T["dim"]}
BYTE_FACTS = ('smart.read', 'smart.written')
PERCENT_FACTS = ('smart.life_left', 'smart.spare')


class HealthView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.drives: Dict[str, Node] = {}
        self.health: Dict[str, Health] = {}
        self.busy = False
        pad = tk.Frame(self, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.heading(pad, t("health.heading")).pack(anchor="w")
        self.note(pad, t("health.note"), px(900)).pack(anchor="w", pady=(0, px(6)))
        frame, self.tree = make_table(pad, ("size", "verdict"), show="tree headings")
        self.tree.heading("#0", text=t("col.drive").upper(), anchor="w")
        self.tree.column("#0", width=px(420), anchor="w", stretch=True)
        self.tree.heading("size", text=t("col.size").upper(), anchor="e")
        self.tree.column("size", width=px(100), anchor="e", stretch=False)
        self.tree.heading("verdict", text=t("col.health").upper(), anchor="w")
        self.tree.column("verdict", width=px(140), anchor="w", stretch=False)
        self.tree.configure(height=5)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._picked())
        self.verdict = self.text(pad, "", 12, True, T["dim"])
        self.verdict.pack(anchor="w", pady=(px(12), 0))
        self.summary = self.note(pad, "", px(900))
        self.summary.pack(anchor="w")
        self.facts = tk.Frame(pad, bg=T["bg"])
        self.facts.pack(anchor="w", pady=(px(8), 0))
        self.problems = self.note(pad, "", px(900), T["gold"])
        self.problems.pack(anchor="w", pady=(px(6), 0))
        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(fill="x", pady=(px(10), 0))
        self.read_button = self.button(bar, t("btn.read_again"), self.read_again)
        self.read_button.pack(side="left")
        self.test_button = self.button(bar, t("btn.short_test"), self.short_test)
        self.test_button.pack(side="left", padx=(px(8), 0))
        self.disks_changed()

    def disks_changed(self) -> None:
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.drives = {}
        for disk in self.app.disks:
            if disk.kind != 'disk' or not disk.path:
                continue
            self.drives[disk.path] = disk
            name = disk.title or disk.path
            self.tree.insert("", "end", iid=disk.path, text=f"{name}  ({disk.path})",
                             values=(size_text(disk.size), self._word(disk.path)))
        for iid in keep:
            if iid in self.drives:
                self.tree.selection_set(iid)
        if not self.tree.selection() and self.drives:
            self.tree.selection_set(next(iter(self.drives)))
        self._picked()

    def _word(self, path: str) -> str:
        health = self.health.get(path)
        return t(f"verdict.{health.verdict}") if health else ''

    def refresh(self) -> None:
        self.disks_changed()

    def selected(self) -> Optional[Node]:
        picked = self.tree.selection()
        return self.drives.get(picked[0]) if picked else None

    def _picked(self) -> None:
        node = self.selected()
        self._buttons()
        if node is None:
            self._show(None)
        elif node.path in self.health:
            self._show(self.health[node.path])
        else:
            self._show(None, t("health.reading"))
            self._load(node)

    def _buttons(self) -> None:
        on = self.selected() is not None and not self.busy and not self.app.busy
        self.read_button.set_enabled(on)
        self.test_button.set_enabled(on)

    # — reading —
    def _load(self, node: Node, update: bool = False) -> None:
        path, ops = node.path, self.app.ops

        def job() -> Health:
            if update:
                ops.smart_update(path)
            return summarise(ops.smart(path))

        def done(value, error) -> None:
            self.busy = False
            self._buttons()
            current = self.selected()
            if error is not None:
                self.app.set_status(error_text(error), T["pink"], hold_ms=10000)
                self.app.glitch.now(self.app.title, strong=True)
                if current is not None and current.path == path:
                    self._show(None, t("health.failed"))
                return
            self.health[path] = value
            if self.tree.exists(path):
                self.tree.set(path, "verdict", self._word(path))
            if current is not None and current.path == path:
                self._show(value)
                if update:
                    self.app.glitch.now(self.app.title)
        self.busy = True
        self._buttons()
        self.app.worker.run(job, done)

    def read_again(self) -> None:
        node = self.selected()
        if node is not None and not self.busy:
            self.app.set_status(t("status.reading_smart"), T["gold"])
            self._load(node, update=True)

    def short_test(self) -> None:
        node = self.selected()
        if node is None or self.busy:
            return
        ops, path = self.app.ops, node.path
        self.busy = True
        self._buttons()
        self.app.set_status(t("status.testing"), T["gold"])

        def done(_value, error) -> None:
            self.busy = False
            self._buttons()
            if error is not None:
                self.app.set_status(error_text(error), T["pink"], hold_ms=10000)
                self.app.glitch.now(self.app.title, strong=True)
            else:
                self.app.set_status(t("done.test_started"), T["accent"], hold_ms=10000)
                self.app.glitch.now(self.app.title)
        self.app.worker.run(lambda: ops.smart_selftest(path), done)

    # — showing —
    def _fact_value(self, key: str, value: str) -> str:
        if key in BYTE_FACTS:
            return size_text(int(value))
        if key in PERCENT_FACTS:
            return local_units(f"{value} %")
        return value

    def _show(self, health: Optional[Health], message: str = "") -> None:
        for child in self.facts.winfo_children():
            child.destroy()
        self.problems.config(text="")
        if health is None:
            self.verdict.config(text=message or t("health.pick"), fg=T["dim"])
            self.summary.config(text="")
            return
        self.verdict.config(text="● " + t(f"verdict.{health.verdict}").upper(),
                            fg=VERDICT_COLOUR[health.verdict])
        if not health.supported:
            self.summary.config(text=t("health.unsupported"))
            return
        if health.facts and health.facts[0][0] == 'smart.not_read':
            self.summary.config(text=t("health.not_read"))
            return
        bits: List[str] = []
        if health.temperature_c is not None:
            bits.append(local_units(t("health.temperature", value=f"{health.temperature_c:.0f}")))
        if health.hours is not None:
            bits.append(t("health.hours", hours=f"{health.hours:,}".replace(",", " "),
                          days=f"{health.hours // 24:,}".replace(",", " ")))
        if health.updated:
            bits.append(t("health.read_at", when=time.strftime("%Y-%m-%d %H:%M",
                                                              time.localtime(health.updated))))
        self.summary.config(text="   ·   ".join(bits))
        for i, (key, value) in enumerate(health.facts):
            self.text(self.facts, t(key), 9, False, T["muted"]).grid(
                row=i, column=0, sticky="w", padx=(0, self.app.px(20)))
            self.text(self.facts, self._fact_value(key, value), 9, True).grid(
                row=i, column=1, sticky="w")
        if health.problems:
            seen: List[str] = []
            for key in health.problems:
                if key not in seen:
                    seen.append(key)
            self.problems.config(text="\n".join(t("problem." + k[len("smart."):]) for k in seen))
