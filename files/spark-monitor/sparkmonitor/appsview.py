"""The Apps tab: apps, background tasks and the system, one row per app, with End task."""

from typing import Dict, List, Optional, Tuple

import tkinter as tk

from . import core
from .procs import APP, BACKGROUND, SECTIONS, SYSTEM, Group
from .text import t
from .ui import make_table
from .widgets import T, WolkButton

COLUMNS = ('cpu', 'memory', 'gpu', 'disk')
NUMERIC = {'cpu': lambda g: g.cpu, 'memory': lambda g: g.mem,
           'gpu': lambda g: -1 if g.gpu is None else g.gpu, 'disk': lambda g: g.disk}


class AppsView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        sort = app.settings.get('apps_sort')
        self.sort: Tuple[str, bool] = (sort[0], bool(sort[1])) \
            if isinstance(sort, list) and len(sort) == 2 and sort[0] in ('name',) + COLUMNS \
            else ('name', False)
        frame, self.tree = make_table(self, COLUMNS)
        frame.pack(fill="both", expand=True, padx=px(14), pady=(px(10), 0))
        tree = self.tree
        tree.heading('#0', text=t('col.name').upper(), anchor="w",
                     command=lambda: self.sort_by('name'))
        tree.column('#0', width=px(330), minwidth=px(160), stretch=True)
        for col in COLUMNS:
            tree.heading(col, text=t(f'col.{col}').upper(), anchor="e",
                         command=lambda c=col: self.sort_by(c))
            tree.column(col, width=px(96), minwidth=px(70), anchor="e", stretch=False)
        self.headings: Dict[str, str] = {}
        self.sections = {}
        for sec in SECTIONS:
            self.sections[sec] = tree.insert('', 'end', iid=f'sec:{sec}', open=sec != SYSTEM,
                                             text=t(f'section.{sec}').upper(), tags=('section',))
        self.iids: Dict[str, str] = {}          # group key -> row id
        self.keys: Dict[str, str] = {}          # row id -> group key
        self.shown: Dict[str, tuple] = {}       # row id -> what the row shows now
        self.next_id = 0
        self.open_groups: set = set()

        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=px(10))
        self.summary = tk.Label(bar, text="", bg=T["bg"], fg=T["muted"], font=app.font(8))
        self.summary.pack(side="left")
        self.end_button = WolkButton(bar, t('apps.end'), self.end_task, app.font(9),
                                     variant="danger")
        self.end_button.pack(side="right")
        self.end_button.set_enabled(False)
        self.note = tk.Label(self, text="", bg=T["bg"], fg=T["gold"], font=app.font(8, False),
                             anchor="w", justify="left")
        self.note.bind("<Configure>", lambda e: self.note.config(wraplength=e.width - px(4)))

        tree.bind("<<TreeviewSelect>>", lambda _e: self.selection_changed())
        tree.bind("<<TreeviewOpen>>", lambda _e: self.after_idle(self._opened))
        tree.bind("<<TreeviewClose>>", lambda _e: self.after_idle(self._opened))
        tree.bind("<Delete>", lambda _e: self.end_task())

    # — rows —
    def _row_id(self, key: str) -> str:
        iid = self.iids.get(key)
        if iid is None:
            self.next_id += 1
            iid = self.iids[key] = f'g{self.next_id}'
            self.keys[iid] = key
        return iid

    def _values(self, cpu: float, mem: int, gpu: Optional[float], disk: float) -> tuple:
        return (core.pct(cpu), core.size(mem), '—' if gpu is None else core.pct(gpu, 0),
                core.rate(disk))

    def _sort_key(self, g: Group):
        col, _desc = self.sort
        if col == 'name':
            return g.name.lower()
        return NUMERIC[col](g)

    def refresh(self) -> None:
        tree, app = self.tree, self.app
        groups = app.procs.groups
        col, desc = self.sort
        by_section: Dict[str, List[Group]] = {s: [] for s in SECTIONS}
        for g in groups.values():
            by_section[g.section].append(g)
        live = set()
        icons_changed = app.icons.changed
        app.icons.changed = False
        for sec, items in by_section.items():
            parent = self.sections[sec]
            items.sort(key=self._sort_key, reverse=desc)
            order = []
            for g in items:
                iid = self._row_id(g.key)
                live.add(iid)
                order.append(iid)
                count = len(g.pids)
                name = f"{g.name} ({count})" if count > 1 else g.name
                values = self._values(g.cpu, g.mem, g.gpu, g.disk)
                tags = ('system',) if sec == SYSTEM else (('busy',) if g.cpu >= 25 else ())
                state = (name, values, tags)
                if iid not in self.shown:
                    image = app.icons.get(g.icon, g.name) if sec == APP else ''
                    tree.insert(parent, 'end', iid=iid, text=name, values=values, tags=tags,
                                image=image)
                    self.shown[iid] = state
                elif self.shown[iid] != state:
                    tree.item(iid, text=name, values=values, tags=tags)
                    self.shown[iid] = state
                if icons_changed and sec == APP:
                    tree.item(iid, image=app.icons.get(g.icon, g.name))
                self._children(iid, g)
            current = tree.get_children(parent)
            if list(current) != order:
                for i, iid in enumerate(order):
                    tree.move(iid, parent, i)
            label = f"{t(f'section.{sec}').upper()} ({len(items)})"
            if tree.item(parent, 'text') != label:
                tree.item(parent, text=label)
        for iid in list(self.shown):
            if iid not in live:
                if tree.exists(iid):
                    tree.delete(iid)
                del self.shown[iid]
                key = self.keys.pop(iid, None)
                self.iids.pop(key, None)
                self.open_groups.discard(iid)
        self._headings()
        procs, _kernel = app.procs.totals()
        apps = len(by_section[APP])
        text = t('apps.summary', procs=procs, apps=apps)
        if self.summary.cget('text') != text:
            self.summary.config(text=text)
        self.selection_changed()

    def _children(self, iid: str, g: Group) -> None:
        """A group's processes, listed only while it's open; a placeholder keeps the arrow."""
        tree = self.tree
        kids = tree.get_children(iid)
        if len(g.pids) < 2:
            if kids:
                tree.delete(*kids)
            return
        if iid not in self.open_groups:
            if not kids:
                tree.insert(iid, 'end', iid=f'{iid}|…', text='…')
            elif len(kids) > 1 or kids[0] != f'{iid}|…':
                tree.delete(*kids)
                tree.insert(iid, 'end', iid=f'{iid}|…', text='…')
            return
        procs = self.app.procs.procs
        want = sorted((p for p in (procs.get(pid) for pid in g.pids) if p),
                      key=lambda p: -p.cpu if self.sort[0] != 'name' else p.pid)
        want_ids = [f'{iid}|{p.pid}' for p in want]
        stale = [k for k in kids if k not in want_ids]
        if stale:
            tree.delete(*stale)
        for i, p in enumerate(want):
            cid = want_ids[i]
            values = self._values(p.cpu, p.mem, p.gpu if p.gpu_fds else None, p.disk)
            text = f"{p.comm}  ·  {p.pid}"
            if tree.exists(cid):
                if tree.item(cid, 'values') != values:
                    tree.item(cid, values=values)
            else:
                tree.insert(iid, i, iid=cid, text=text, values=values)
        if list(tree.get_children(iid)) != want_ids:
            for i, cid in enumerate(want_ids):
                tree.move(cid, iid, i)

    def _opened(self) -> None:
        tree = self.tree
        self.open_groups = {iid for iid in self.keys if tree.exists(iid) and
                            tree.item(iid, 'open')}
        self.refresh()

    def _headings(self) -> None:
        """Totals in the column headings, like Windows: "CPU 23%"."""
        snap = self.app.system.last
        if snap is None:
            return
        totals = {'cpu': snap.cpu, 'memory': snap.mem.percent, 'gpu': snap.gpu_busy,
                  'disk': snap.disk_active}
        col, desc = self.sort
        for c in COLUMNS:
            arrow = (' ▼' if desc else ' ▲') if c == col else ''
            value = totals[c]
            text = f"{t(f'col.{c}').upper()} {value:.0f}%{arrow}" if value is not None \
                else f"{t(f'col.{c}').upper()}{arrow}"
            if self.headings.get(c) != text:
                self.tree.heading(c, text=text)
                self.headings[c] = text
        name = t('col.name').upper() + ((' ▼' if desc else ' ▲') if col == 'name' else '')
        if self.headings.get('#0') != name:
            self.tree.heading('#0', text=name)
            self.headings['#0'] = name

    def sort_by(self, col: str) -> None:
        cur, desc = self.sort
        if cur == col:
            desc = not desc
        else:
            desc = col != 'name'          # numbers: biggest first
        self.sort = (col, desc)
        self.app.settings['apps_sort'] = [col, desc]
        self.refresh()

    # — selection and End task —
    def selected_group(self) -> Optional[Group]:
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0].split('|', 1)[0]
        key = self.keys.get(iid)
        return self.app.procs.groups.get(key) if key else None

    def selection_changed(self) -> None:
        g = self.selected_group()
        note = ""
        ok = False
        if g is not None:
            if not g.endable:
                note = t('apps.system_note')
            elif self.app.procs.self_pid in g.pids:
                note = t('apps.self_note')
            elif not g.mine:
                note = t('apps.not_mine')
            else:
                ok = not self.app.ending
        if self.end_button.enabled != ok:
            self.end_button.set_enabled(ok)
        if self.note.cget('text') != note:
            self.note.config(text=note)
            if note:
                self.note.pack(fill="x", padx=self.app.px(14), pady=(0, self.app.px(10)),
                               before=self.end_button.master)
            else:
                self.note.pack_forget()

    def end_task(self) -> None:
        g = self.selected_group()
        if g is None or not g.endable or not g.mine or self.app.procs.self_pid in g.pids:
            if g is not None:
                self.app.glitch.now(self.app.title, strong=True)
            return
        key = g.key
        self.app.end_processes(g.name, g.pids, more=lambda: self.app.procs.group_pids(key))

    def key_select_first(self) -> None:
        apps = self.tree.get_children(self.sections[APP]) or \
            self.tree.get_children(self.sections[BACKGROUND])
        if apps:
            self.tree.selection_set(apps[0])
            self.tree.focus(apps[0])

    def row_for(self, key: str) -> Optional[str]:
        return self.iids.get(key)
