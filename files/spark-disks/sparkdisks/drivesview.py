"""The Drives tab: every drive with its partitions and free space, and the actions. A button is
only lit when safety.check allows it for the picked row; ops.py checks again when it is pressed."""

import os
from typing import Dict, List, Optional

import tkinter as tk

from . import safety
from .dialogs import Ask, Field, ask
from .model import MIB, Node, drive_of, find, human_size, parse_size
from .text import t
from .ui import make_table
from .viewkit import View, size_text
from .widgets import T

FS_ORDER = ('ext4', 'btrfs', 'xfs', 'ntfs', 'exfat', 'vfat')
FS_NAMES = {'ext4': 'ext4', 'btrfs': 'Btrfs', 'xfs': 'XFS', 'ntfs': 'NTFS', 'exfat': 'exFAT',
            'vfat': 'FAT32', 'swap': 'swap'}
ACTIONS = (('mount', 'btn.mount'), ('unmount', 'btn.unmount'), ('format', 'btn.format'),
           ('create', 'btn.create'), ('resize', 'btn.resize'), ('delete', 'btn.delete'),
           ('erase', 'btn.erase'), ('eject', 'btn.eject'))


def fs_choices(formats: List[str], with_empty: bool = False):
    options = [(FS_NAMES.get(f, f), f) for f in FS_ORDER if f in formats]
    if with_empty:
        options.append((t('fs.empty'), 'empty'))
    return options or [('ext4', 'ext4')]


def tag_text(node: Node) -> str:
    key = safety.tag_for(node)
    return t(key) if key else ''


def what_text(node: Node) -> str:
    if node.kind == 'disk':
        if node.pttype:
            return {'gpt': 'GPT', 'dos': 'MBR'}.get(node.pttype, node.pttype.upper())
        return node.fstype or t('what.no_table')
    if node.kind == 'free':
        return ''
    parts = [p for p in (node.label or node.partlabel, node.fstype) if p]
    return ' · '.join(parts) if parts else t('what.unknown')


class DrivesView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.rows: Dict[str, Node] = {}
        pad = tk.Frame(self, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.heading(pad, t("drives.heading")).pack(anchor="w")
        self.empty = self.note(pad, "", px(860))
        columns = ("what", "size", "used", "mount", "tag")
        frame, self.tree = make_table(pad, columns, show="tree headings")
        self.tree.heading("#0", text=t("col.device").upper(), anchor="w")
        self.tree.column("#0", width=px(260), anchor="w", stretch=True)
        for column, key, width, anchor in (
                ("what", "col.what", 170, "w"), ("size", "col.size", 90, "e"),
                ("used", "col.used", 90, "e"), ("mount", "col.mount", 200, "w"),
                ("tag", "col.tag", 90, "w")):
            self.tree.heading(column, text=t(key).upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "mount")
        frame.pack(fill="both", expand=True, pady=(px(6), 0))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._picked())
        self.detail = self.note(pad, "", px(900))
        self.detail.pack(anchor="w", pady=(px(8), 0), fill="x")
        self.reason = self.note(pad, "", px(900), T["gold"])
        self.reason.pack(anchor="w", pady=(px(2), px(6)), fill="x")
        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(fill="x")
        self.buttons = {}
        for i, (action, key) in enumerate(ACTIONS):
            variant = "danger" if action in ("format", "delete", "erase") else "ghost"
            button = self.button(bar, t(key), lambda a=action: self.act(a), variant)
            button.grid(row=i // 4, column=i % 4, padx=(0, px(8)), pady=(0, px(6)), sticky="w")
            self.buttons[action] = button
        self.disks_changed()

    # — the list —
    def disks_changed(self) -> None:
        app = self.app
        keep = self.tree.selection()
        opened = set()
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        if app.list_error:
            self.empty.config(text=t("drives.list_failed", error=app.list_error), fg=T["pink"])
            self.empty.pack(anchor="w", before=self.tree.master)
        elif app.loaded and not app.disks:
            self.empty.config(text=t("drives.none"), fg=T["muted"])
            self.empty.pack(anchor="w", before=self.tree.master)
        else:
            self.empty.pack_forget()
        for disk in app.disks:
            self._insert(disk, "", opened)
        for iid in keep:
            if iid in self.rows:
                self.tree.selection_set(iid)
                self.tree.see(iid)
        self._picked()

    def _iid(self, node: Node) -> str:
        return node.path if node.kind != 'free' else f"free:{node.parent}:{node.start}"

    def _insert(self, node: Node, parent: str, opened) -> None:
        iid = self._iid(node)
        if not iid or iid in self.rows:
            return
        self.rows[iid] = node
        if node.kind == 'disk':
            name = node.title or os.path.basename(node.path)
            name = f"{name}  ({node.path})"
        elif node.kind == 'free':
            name = t("what.free")
        else:
            name = os.path.basename(node.path) or node.name
        used = size_text(node.fsused) if node.fsused and node.kind == 'part' else ''
        mounts = ', '.join(node.mounts)
        tags = []
        if node.kind == 'disk':
            tags.append('section')
        if node.kind == 'free':
            tags.append('free')
        if node.is_d:
            tags.append('locked')
        elif node.is_system or node.windows:
            tags.append('danger')
        self.tree.insert(parent, "end", iid=iid, text=name, open=True,
                         values=(what_text(node), size_text(node.size), used, mounts,
                                 tag_text(node)), tags=tuple(tags))
        for child in node.children:
            self._insert(child, iid, opened)

    def selected(self) -> Optional[Node]:
        picked = self.tree.selection()
        return self.rows.get(picked[0]) if picked else None

    # — the picked row —
    def _picked(self) -> None:
        app = self.app
        node = self.selected()
        for action, _key in ACTIONS:
            button = self.buttons[action]
            if node is None or not app.loaded or app.busy:
                button.set_enabled(False)
            else:
                button.set_enabled(safety.check(action, node, app.disks).allowed)
        if node is None:
            self.detail.config(text=t("drives.pick"))
            self.reason.config(text="")
            return
        self.detail.config(text=self._detail(node))
        self.reason.config(text=self._reason(node))

    def _detail(self, node: Node) -> str:
        if node.kind == 'free':
            return t("detail.free", size=size_text(node.size))
        lines = [node.path]
        if node.kind == 'disk':
            if node.title:
                lines.append(node.title)
            if node.serial:
                lines.append(t("detail.serial", serial=node.serial))
            lines.append(t("detail.usb") if node.removable or node.tran == 'usb'
                         else t("detail.internal"))
        else:
            if node.uuid:
                lines.append(f"UUID {node.uuid}")
        if node.letter:
            lines.append(t("detail.letter", letter=node.letter))
        return "   ·   ".join(lines)

    def _reason(self, node: Node) -> str:
        app = self.app
        primary = 'create' if node.kind == 'free' else ('erase' if node.kind == 'disk' else 'format')
        verdict = safety.check(primary, node, app.disks)
        if not verdict.allowed:
            return t(verdict.key, **verdict.args)
        if verdict.hard:
            return t("hint.hard")
        return ""

    # — doing things —
    def _facts(self, node: Node, disk: Node) -> List[tuple]:
        rows = [(t("fact.device"), node.path or disk.path)]
        if disk.title:
            rows.append((t("fact.drive"), disk.title))
        rows.append((t("fact.size"), size_text(node.size)))
        if node.kind == 'part' or (node.kind == 'disk' and node.fstype):
            rows.append((t("fact.holds"), what_text(node)))
            if node.mounts:
                rows.append((t("fact.mounted"), ', '.join(node.mounts)))
        tag = tag_text(node) or tag_text(disk)
        if tag:
            rows.append((t("fact.marked"), tag))
        return rows

    def _notes(self, verdict: safety.Verdict, node: Node, disk: Node) -> List[str]:
        notes = [t(n) for n in verdict.notes]
        if node.windows:
            notes.append(t("note.windows"))
        if disk.is_system:
            notes.append(t("note.system_disk"))
        elif verdict.hard and not node.windows:
            notes.append(t("note.internal"))
        return notes

    def _typed(self, verdict: safety.Verdict, node: Node) -> str:
        return os.path.basename(node.path) if verdict.hard else ''

    def act(self, action: str) -> None:
        app = self.app
        node = self.selected()
        if node is None or app.busy:
            return
        # look it up again: the list may have changed since the row was picked
        verdict = safety.check(action, node, app.disks)
        if not verdict.allowed:
            app.set_status(t(verdict.key, **verdict.args), T["pink"], hold_ms=10000)
            app.glitch.now(app.title, strong=True)
            return
        disk = drive_of(app.disks, node)
        assert disk is not None
        ops, path = app.ops, node.path
        if action == 'mount':
            app.run_change(t("status.mounting"), lambda: ops.mount(path), t("done.mounted"),
                           lambda where: app.set_status(t("done.mounted_at", where=where),
                                                        T["accent"], hold_ms=8000))
        elif action == 'unmount':
            app.run_change(t("status.unmounting"), lambda: ops.unmount(path), t("done.unmounted"))
        elif action == 'eject':
            app.run_change(t("status.ejecting"), lambda: ops.eject(path), t("done.ejected"))
        elif action == 'format':
            self._format(node, disk, verdict)
        elif action == 'create':
            self._create(node, disk, verdict)
        elif action == 'resize':
            self._resize(node, disk, verdict)
        elif action == 'delete':
            self._delete(node, disk, verdict)
        elif action == 'erase':
            self._erase(node, disk, verdict)

    def _format(self, node: Node, disk: Node, verdict: safety.Verdict) -> None:
        app, path = self.app, node.path
        default = 'exfat' if node.removable and 'exfat' in app.formats else 'ext4'
        spec = Ask(t("dlg.format"), t("btn.format"), self._facts(node, disk),
                   self._notes(verdict, node, disk) + [t("note.format_all")],
                   [Field('fs', t("field.fs"), 'choice', fs_choices(app.formats), default),
                    Field('label', t("field.label"), 'text', default=node.label),
                    Field('zero', t("field.zero"), 'check', default=False, hint=t("hint.zero"))],
                   self._typed(verdict, node))
        got = ask(app, spec)
        if got is None:
            return
        app.run_change(t("status.formatting"),
                       lambda: app.ops.format(path, got['fs'], got['label'].strip(),
                                              bool(got['zero']), got.get('confirm', '')),
                       t("done.formatted"))

    def _create(self, free: Node, disk: Node, verdict: safety.Verdict) -> None:
        app = self.app
        top = free.size

        def validate(values) -> str:
            if values['size'].strip().lower() in ('max', ''):
                return ''
            size = parse_size(values['size'])
            if size is None:
                return t("bad.size_text")
            if size < MIB or size > top + MIB - 1:
                return t("bad.size", max=size_text(top))
            return ''
        default = 'exfat' if disk.removable and 'exfat' in app.formats else 'ext4'
        spec = Ask(t("dlg.create"), t("btn.create"),
                   [(t("fact.drive"), disk.title or disk.path), (t("fact.device"), disk.path),
                    (t("fact.free"), size_text(top))],
                   self._notes(verdict, free, disk),
                   [Field('size', t("field.size"), 'text', default=human_size(top)),
                    Field('fs', t("field.fs"), 'choice', fs_choices(app.formats, True), default),
                    Field('label', t("field.label"), 'text')],
                   os.path.basename(disk.path) if verdict.hard else '', danger=verdict.hard,
                   validate=validate)
        got = ask(app, spec)
        if got is None:
            return
        wanted = parse_size(got['size']) if got['size'].strip().lower() not in ('max', '') else top
        size = top if wanted is None or wanted >= top - MIB else (wanted // MIB) * MIB
        app.run_change(t("status.creating"),
                       lambda: app.ops.create(disk.path, free.start, size, got['fs'],
                                              got['label'].strip(), got.get('confirm', '')),
                       t("done.created"))

    def _resize(self, node: Node, disk: Node, verdict: safety.Verdict) -> None:
        app, path = self.app, node.path
        top = app.ops.max_resize(node, app.disks)
        low = int(node.fsused * 1.05) if node.fsused else MIB

        def validate(values) -> str:
            size = parse_size(values['size'])
            if size is None:
                return t("bad.size_text")
            if size > top:
                return t("bad.size", max=size_text(top))
            if size < low:
                return t("bad.too_small")
            return ''
        facts = self._facts(node, disk) + [(t("fact.smallest"), size_text(low)),
                                           (t("fact.largest"), size_text(top))]
        spec = Ask(t("dlg.resize"), t("btn.resize"), facts,
                   self._notes(verdict, node, disk) + [t("note.resize_backup")],
                   [Field('size', t("field.new_size"), 'text', default=human_size(node.size))],
                   self._typed(verdict, node), validate=validate)
        got = ask(app, spec)
        if got is None:
            return
        size = (parse_size(got['size']) or node.size)
        app.run_change(t("status.resizing"),
                       lambda: app.ops.resize(path, size, got.get('confirm', '')),
                       t("done.resized"))

    def _delete(self, node: Node, disk: Node, verdict: safety.Verdict) -> None:
        app, path = self.app, node.path
        spec = Ask(t("dlg.delete"), t("btn.delete"), self._facts(node, disk),
                   self._notes(verdict, node, disk) + [t("note.delete_all")], (),
                   self._typed(verdict, node))
        got = ask(app, spec)
        if got is None:
            return
        app.run_change(t("status.deleting"),
                       lambda: app.ops.delete(path, got.get('confirm', '')), t("done.deleted"))

    def _erase(self, node: Node, disk: Node, verdict: safety.Verdict) -> None:
        app, path = self.app, node.path
        spec = Ask(t("dlg.erase"), t("btn.erase"), self._facts(node, disk),
                   self._notes(verdict, node, disk),
                   [Field('table', t("field.table"), 'choice',
                          [("GPT", 'gpt'), ("MBR", 'dos')], 'gpt')],
                   self._typed(verdict, node))
        got = ask(app, spec)
        if got is None:
            return
        app.run_change(t("status.erasing"),
                       lambda: app.ops.erase(path, got['table'], got.get('confirm', '')),
                       t("done.erased"))
