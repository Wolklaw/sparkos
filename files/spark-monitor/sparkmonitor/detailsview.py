"""The Details tab: every process on its own row, for people who want PIDs and command lines.
Kernel threads are left out, like Windows leaves out its kernel's."""

from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox

from . import core
from .procs import Proc, users
from .text import t
from .ui import make_table
from .widgets import T, WolkButton

COLUMNS = ('name', 'pid', 'user', 'state', 'cpu', 'memory', 'nice', 'command')
WIDTHS = {'name': 170, 'pid': 70, 'user': 90, 'state': 110, 'cpu': 70, 'memory': 90,
          'nice': 50, 'command': 420}
RIGHT = ('pid', 'cpu', 'memory', 'nice')


class DetailsView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        sort = app.settings.get('details_sort')
        self.sort: Tuple[str, bool] = (sort[0], bool(sort[1])) \
            if isinstance(sort, list) and len(sort) == 2 and sort[0] in COLUMNS \
            else ('cpu', True)
        frame, self.tree = make_table(self, COLUMNS, show="headings")
        frame.pack(fill="both", expand=True, padx=px(14), pady=(px(10), 0))
        for col in COLUMNS:
            self.tree.heading(col, text=t(f'col.{col}').upper(),
                              anchor="e" if col in RIGHT else "w",
                              command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=px(WIDTHS[col]), minwidth=px(40),
                             anchor="e" if col in RIGHT else "w",
                             stretch=col == 'command')
        self.users = users()
        self.shown: Dict[str, tuple] = {}
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=px(10))
        self.summary = tk.Label(bar, text="", bg=T["bg"], fg=T["muted"], font=app.font(8))
        self.summary.pack(side="left")
        self.tree_button = WolkButton(bar, t('end.tree'), lambda: self.end(tree=True),
                                      app.font(9), variant="ghost")
        self.tree_button.pack(side="right")
        self.end_button = WolkButton(bar, t('end.process'), lambda: self.end(tree=False),
                                     app.font(9), variant="danger")
        self.end_button.pack(side="right", padx=(0, px(8)))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.selection_changed())
        self.tree.bind("<Delete>", lambda _e: self.end(tree=False))
        self._headings()
        self.selection_changed()

    def user(self, uid: int) -> str:
        if uid < 0:
            return "?"
        return self.users.get(uid, str(uid))

    def _values(self, p: Proc) -> tuple:
        return (p.comm, p.pid, self.user(p.uid), t(f'state.{p.state}') if p.state else '',
                core.pct(p.cpu), core.size(p.mem), p.nice, self.app.procs.cmdline(p) or
                f'[{p.comm}]')

    def _sort_key(self, p: Proc):
        col = self.sort[0]
        return {'name': lambda: p.comm.lower(), 'pid': lambda: p.pid,
                'user': lambda: self.user(p.uid), 'state': lambda: p.state,
                'cpu': lambda: p.cpu, 'memory': lambda: p.mem, 'nice': lambda: p.nice,
                'command': lambda: (p.cmdline or '').lower()}[col]()

    def refresh(self) -> None:
        tree = self.tree
        procs = [p for p in self.app.procs.procs.values() if not p.kthread]
        procs.sort(key=self._sort_key, reverse=self.sort[1])
        order: List[str] = []
        for p in procs:
            iid = str(p.pid)
            order.append(iid)
            values = self._values(p)
            tags = ('busy',) if p.cpu >= 25 else ()
            state = (values, tags)
            old = self.shown.get(iid)
            if old is None:
                tree.insert('', 'end', iid=iid, values=values, tags=tags)
                self.shown[iid] = state
            elif old != state:
                tree.item(iid, values=values, tags=tags)
                self.shown[iid] = state
        live = set(order)
        gone = [iid for iid in self.shown if iid not in live]
        for iid in gone:
            if tree.exists(iid):
                tree.delete(iid)
            del self.shown[iid]
        if list(tree.get_children('')) != order:
            for i, iid in enumerate(order):
                tree.move(iid, '', i)
        text = t('apps.summary', procs=len(procs),
                 apps=sum(1 for g in self.app.procs.groups.values() if g.section == 'app'))
        if self.summary.cget('text') != text:
            self.summary.config(text=text)
        self.selection_changed()

    def _headings(self) -> None:
        col, desc = self.sort
        for c in COLUMNS:
            arrow = (' ▼' if desc else ' ▲') if c == col else ''
            self.tree.heading(c, text=t(f'col.{c}').upper() + arrow)

    def sort_by(self, col: str) -> None:
        cur, desc = self.sort
        desc = (not desc) if cur == col else col in ('cpu', 'memory')
        self.sort = (col, desc)
        self.app.settings['details_sort'] = [col, desc]
        self._headings()
        self.refresh()

    def selected(self) -> Optional[Proc]:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return self.app.procs.procs.get(int(sel[0]))
        except ValueError:
            return None

    def selection_changed(self) -> None:
        p = self.selected()
        ok = p is not None and not self.app.ending and p.pid != self.app.procs.self_pid
        for button in (self.end_button, self.tree_button):
            if button.enabled != ok:
                button.set_enabled(ok)

    def end(self, tree: bool) -> None:
        p = self.selected()
        if p is None or p.pid == self.app.procs.self_pid or self.app.ending:
            return
        sampler = self.app.procs
        if sampler.protected_pid(p.pid):
            if not messagebox.askyesno(t('end.confirm_title'),
                                       t('end.confirm', name=p.comm, pid=p.pid),
                                       icon='warning', default='no', parent=self.app.root):
                return
        pids = sampler.children(p.pid) if tree else [p.pid]
        name = f"{p.comm} ({p.pid})"
        self.app.end_processes(name, pids,
                               more=(lambda: sampler.children(p.pid)) if tree else None)

    def select_pid(self, pid: int) -> bool:
        iid = str(pid)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            return True
        return False

