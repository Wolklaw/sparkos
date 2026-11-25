"""The Windows fonts window: finds a Windows drive, lists its fonts that aren't installed here,
and installs the ones you tick. Copies only; the drive is mounted read-only and never written."""

import queue
import threading
import tkinter as tk
from typing import Callable, List, Optional, Tuple

from . import fcdata, store, winfonts
from .core import log
from .text import t
from .widgets import T, GlitchText, WolkButton, make_table

ON, OFF = "■", "□"


class WindowsDialog(tk.Toplevel):
    def __init__(self, app, finder: Callable[[], Tuple[List[winfonts.Source], str]]):
        super().__init__(app.root, bg=T["bg"])
        self.app, self.finder = app, finder
        self.title(t('win.title'))
        px = app.px
        self.geometry(f"{px(760)}x{px(560)}")
        self.minsize(px(600), px(420))
        self.transient(app.root)
        self.inbox: 'queue.Queue' = queue.Queue()
        self.cands: List[store.Candidate] = []
        self.chosen = set()
        self.closed = False
        self.heading = GlitchText(self, t('win.heading'), app.f_title, T["bg"])
        self.heading.pack(anchor="w", padx=px(16), pady=(px(12), 0))
        app.glitch.add(self.heading)
        tk.Label(self, text=t('win.note'), bg=T["bg"], fg=T["muted"], font=app.f_small,
                 anchor="w", justify="left", wraplength=px(700)).pack(
            fill="x", padx=px(16), pady=(px(4), px(8)))
        self.status = tk.Label(self, text=t('win.looking'), bg=T["bg"], fg=T["gold"],
                               font=app.f_body, anchor="w")
        self.status.pack(fill="x", padx=px(16))
        frame, self.tree = make_table(self, ("family", "where"), show="tree headings")
        self.tree.heading("#0", text=t('win.col_file'))
        self.tree.heading("family", text=t('win.col_font'))
        self.tree.heading("where", text=t('win.col_where'))
        self.tree.column("#0", width=px(250), stretch=True)
        self.tree.column("family", width=px(220), stretch=True)
        self.tree.column("where", width=px(200), stretch=True)
        frame.pack(fill="both", expand=True, padx=px(16), pady=px(8))
        self.tree.bind("<ButtonRelease-1>", self._click)
        self.tree.bind("<space>", lambda _e: self._toggle_selected())
        row = tk.Frame(self, bg=T["bg"])
        row.pack(fill="x", padx=px(16), pady=(0, px(14)))
        self.import_button = WolkButton(row, t('win.import'), self.do_import, app.f_label,
                                        variant="primary")
        self.import_button.pack(side="left")
        self.import_button.set_enabled(False)
        WolkButton(row, t('win.all'), lambda: self._all(True), app.f_label).pack(
            side="left", padx=(px(6), 0))
        WolkButton(row, t('win.none'), lambda: self._all(False), app.f_label).pack(
            side="left", padx=(px(6), 0))
        WolkButton(row, t('win.close'), self.close, app.f_label).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        threading.Thread(target=self._find, daemon=True, name='spark-fonts-windows').start()
        self._poll_job = self.after(60, self._poll)

    # ── finding ──

    def _find(self):
        try:
            sources, problem = self.finder()
            if problem:
                self.inbox.put(('problem', problem))
                return
            found = winfonts.list_files(sources)
            installed = fcdata.list_faces()
            cands = []
            for item in found:
                cand = store.examine(item.path, installed, item.name)
                if cand.status == store.NEW:
                    cand.reason = item.where
                    cands.append(cand)
            seen, unique = set(), []
            for cand in cands:                       # the same font may sit in two folders
                key = (cand.family.lower(), tuple(s.lower() for s in cand.styles))
                if key not in seen:
                    seen.add(key)
                    unique.append(cand)
            self.inbox.put(('found', unique, len(found)))
        except Exception as exc:                     # noqa: BLE001 (never leave it "looking")
            log.warning("windows fonts: %s", exc)
            self.inbox.put(('problem', 'generic'))

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                msg = self.inbox.get_nowait()
                if msg[0] == 'problem':
                    self.status.config(text=t('win.problem.' + msg[1]), fg=T["pink"])
                    self.app.event(self.heading, strong=True)
                else:
                    self._show(msg[1], msg[2])
        except queue.Empty:
            pass
        self._poll_job = self.after(80, self._poll)

    def _show(self, cands: List[store.Candidate], total: int):
        self.cands = cands
        self.chosen = set(range(len(cands)))
        for i, cand in enumerate(cands):
            self.tree.insert('', 'end', iid=str(i), text=f"{ON} {cand.name}",
                             values=(cand.family, cand.reason))
        if not cands:
            self.status.config(text=t('win.none_new', n=total), fg=T["muted"])
        else:
            self._count()
        self.app.event(self.heading)

    # ── ticking ──

    def _count(self):
        self.status.config(text=t('win.count', n=len(self.chosen), total=len(self.cands)),
                           fg=T["accent"])
        self.import_button.set_enabled(bool(self.chosen))

    def _paint(self, i: int):
        self.tree.item(str(i), text=f"{ON if i in self.chosen else OFF} {self.cands[i].name}")

    def _toggle(self, i: int):
        self.chosen.symmetric_difference_update({i})
        self._paint(i)
        self._count()

    def _toggle_selected(self):
        for iid in self.tree.selection():
            self._toggle(int(iid))

    def _click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_region(event.x, event.y) in ('tree', 'cell'):
            self._toggle(int(iid))

    def _all(self, on: bool):
        self.chosen = set(range(len(self.cands))) if on else set()
        for i in range(len(self.cands)):
            self._paint(i)
        self._count()

    # ── importing ──

    def do_import(self):
        picked = [self.cands[i] for i in sorted(self.chosen)]
        self.close()
        if picked:
            self.app.install_candidates(picked)

    def close(self):
        self.closed = True
        try:
            self.after_cancel(self._poll_job)
        except (tk.TclError, AttributeError):
            pass
        try:
            self.app.glitch.targets.remove(self.heading)
        except ValueError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
