"""The Startup tab: what starts when you log in, with a switch for each."""

import os
import queue
import threading
from typing import Dict, List, Optional

import tkinter as tk

from . import startup
from .core import config_dir, log
from .startup import AUTOSTART, StartupItem
from .text import t
from .ui import make_table
from .widgets import T, WolkButton

COLUMNS = ('status', 'origin', 'kind', 'about')


class StartupView(tk.Frame):
    def __init__(self, app, runner: startup.Runner = startup.run):
        super().__init__(app.body, bg=T["bg"])
        self.app, self.runner = app, runner
        px = app.px
        frame, self.tree = make_table(self, COLUMNS)
        frame.pack(fill="both", expand=True, padx=px(14), pady=(px(10), 0))
        tree = self.tree
        tree.heading('#0', text=t('col.name').upper(), anchor="w")
        tree.column('#0', width=px(250), minwidth=px(140), stretch=False)
        for col, key, width in (('status', 'col.status', 70), ('origin', 'col.origin', 80),
                                ('kind', 'perf.type', 80), ('about', 'col.about', 360)):
            tree.heading(col, text=t(key).upper(), anchor="w")
            tree.column(col, width=px(width), minwidth=px(50), anchor="w",
                        stretch=col == 'about')
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=px(10))
        self.note = tk.Label(bar, text="", bg=T["bg"], fg=T["muted"], font=app.font(8, False),
                             anchor="w", justify="left")
        self.note.pack(side="left", fill="x", expand=True)
        self.button = WolkButton(bar, t('startup.turn_off'), self.toggle, app.font(9))
        self.button.pack(side="right")
        self.button.set_enabled(False)
        self.items: Dict[str, StartupItem] = {}
        self.busy = False
        self.results: "queue.Queue" = queue.Queue()
        self.memory_file = os.path.join(config_dir(), 'startup.json')
        tree.bind("<<TreeviewSelect>>", lambda _e: self.selection_changed())
        tree.bind("<Double-1>", lambda _e: self.toggle())
        tree.bind("<space>", lambda _e: self.toggle())
        self.reload()

    def reload(self) -> None:
        src = self.app.src
        remembered = startup.remembered_units(self.memory_file)
        items = startup.all_items(src, remembered)
        tree = self.tree
        selected = tree.selection()
        tree.delete(*tree.get_children(''))
        self.items = {}
        if not items:
            tree.insert('', 'end', iid='empty', text=t('startup.empty'), tags=('off',))
        for item in items:
            iid = f'{item.kind}:{item.id}'
            self.items[iid] = item
            tree.insert('', 'end', iid=iid, text=item.name, values=(
                t('startup.on') if item.enabled else t('startup.off'),
                t('startup.yours') if item.origin == 'user' else t('startup.system'),
                t('startup.app') if item.kind == AUTOSTART else t('startup.service'),
                item.description), tags=() if item.enabled else ('off',))
        if selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])
        self.selection_changed()

    def selected(self) -> Optional[StartupItem]:
        sel = self.tree.selection()
        return self.items.get(sel[0]) if sel else None

    def selection_changed(self) -> None:
        item = self.selected()
        if item is None:
            self.button.set_enabled(False)
            self._note("")
            return
        self.button.set_text(t('startup.turn_off') if item.enabled else t('startup.turn_on'))
        self.button.set_enabled(item.can_toggle and not self.busy)
        self._note(t('startup.system_service') if not item.can_toggle else item.path)

    def _note(self, text: str) -> None:
        if self.note.cget('text') != text:
            self.note.config(text=text, fg=T["muted"])

    def toggle(self) -> None:
        item = self.selected()
        if item is None or not item.can_toggle or self.busy:
            return
        on = not item.enabled
        if item.kind == AUTOSTART:
            try:
                startup.set_autostart(self.app.src, item, on)
            except OSError as exc:
                self.done(item, on, False, str(exc))
                return
            self.done(item, on, True, "")
            return
        # systemctl can take a moment: run it off the window's thread
        self.busy = True
        self.button.set_enabled(False)

        def work():
            ok, out = startup.set_service(item, on, self.runner)
            self.results.put((item, on, ok, out))
        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._wait)

    def _wait(self) -> None:
        try:
            item, on, ok, out = self.results.get_nowait()
        except queue.Empty:
            self.after(100, self._wait)
            return
        self.busy = False
        if ok:
            remembered = startup.remembered_units(self.memory_file)
            units: List[str] = [u for u in remembered if u != item.id]
            if not on:
                units.append(item.id)
            startup.remember_units(self.memory_file, units)
        self.done(item, on, ok, out)

    def done(self, item: StartupItem, on: bool, ok: bool, why: str) -> None:
        if ok:
            log.info("startup: %s %s", item.id, "on" if on else "off")
            self.app.set_status(
                t('startup.done_on' if on else 'startup.done_off', name=item.name))
            self.app.glitch.now(self.app.title)
        else:
            log.warning("startup: could not switch %s: %s", item.id, why)
            self.app.set_status(t('startup.failed', name=item.name, why=why or '?'),
                                T["pink"], hold_ms=6000)
            self.app.glitch.now(self.app.title, strong=True)
        self.reload()

    def refresh(self) -> None:
        pass                               # nothing here changes by itself every second
