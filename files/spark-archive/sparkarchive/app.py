"""The main window: what's inside an archive (folders, sizes, dates), Extract all or the
selected items, open one file from it, and Compress files. Every job runs in a thread; the
window only reads its progress."""

import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk

from . import APP_NAME
from . import core
from .core import log, pick_archive, pick_files, pick_folder, show_in_file_manager
from .formats import describe
from .jobs import ZIP, CompressJob, ExtractJob, Job, Listing, ListJob
from .safety import DIR, FILE, HARDLINK, LINK, is_root
from .text import t
from .ui import Look, Progress, home_short, middle, result_lines, version_chip
from .widgets import T, GlitchPanel, Strip


class Node:
    __slots__ = ('name', 'path', 'kind', 'size', 'mtime', 'target', 'children', 'unsafe',
                 'encrypted')

    def __init__(self, name: str, path: str, kind: str = DIR):
        self.name, self.path, self.kind = name, path, kind
        self.size, self.mtime, self.target = 0, None, ''
        self.children: Dict[str, 'Node'] = {}
        self.unsafe = False
        self.encrypted = False


def build_tree(listing: Listing) -> Node:
    """Folders from the paths (an archive needn't list a folder to have files in it), with
    each folder's size the sum of what's in it."""
    top = Node('', '')
    odd = 0
    for e in listing.entries:
        parts = e.parts
        if parts is None and e.kind == DIR and is_root(e.name):
            continue                            # the folder itself (iso images list it)
        if parts is None:                       # shown, marked, never extracted
            odd += 1
            node = Node(e.name or '?', f'\0unsafe{odd}', e.kind)
            node.unsafe = True
            top.children[node.path] = node
            continue
        node = top
        for i, part in enumerate(parts):
            child = node.children.get(part)
            if child is None:
                child = Node(part, '/'.join(parts[:i + 1]))
                node.children[part] = child
            node = child
        if e.kind != DIR or not node.children:
            node.kind = e.kind
        node.size = max(e.size, 0) if e.kind == FILE else node.size
        node.mtime = e.mtime if e.mtime else node.mtime
        node.target = e.target
        node.encrypted = e.encrypted
    # folder sizes, without recursion (archives can be deep)
    order: List[Node] = []
    stack = [top]
    while stack:
        n = stack.pop()
        order.append(n)
        stack.extend(c for c in n.children.values() if c.kind == DIR)
    for n in reversed(order):
        if n.kind == DIR:
            n.size = sum(c.size for c in n.children.values())
    return top


def sort_key(n: Node):
    return (0 if n.kind == DIR else 1, n.name.lower(), n.name)


class App(Look):
    def __init__(self, path: Optional[str] = None):
        super().__init__()
        self.listing: Optional[Listing] = None
        self.tree_top: Optional[Node] = None
        self.nodes: Dict[str, Node] = {}
        self.job: Optional[Job] = None
        self.job_kind = ''
        self.job_title = ''
        self.after_job = None
        self.temp_dirs: List[str] = []
        self.first_paint: Optional[float] = None
        self.started = time.monotonic()
        self.style_table()
        self._build()
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.root.bind('<Expose>', self._exposed, add='+')
        if path:
            self.root.after(1, lambda: self.open(path))
        else:
            self._show_empty()

    def _exposed(self, event) -> None:
        if self.first_paint is None and event.widget is self.root:
            self.first_paint = time.monotonic()

    # ─── building ─────────────────────────────────────────────

    def _build(self) -> None:
        px, bg, root = self.px, T["bg"], self.root
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(640), px(420))
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(px(900), int(sw * 0.8))}x{min(px(620), int(sh * 0.8))}")

        self.mark, self.title, self.status, head = self.header(root, "SPARK ARCHIVE")
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        version_chip(self, head).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")

        bar = tk.Frame(root, bg=bg)
        bar.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.b_extract = self.button(bar, t('button.extract_all'), self.extract_all, "primary")
        self.b_extract.pack(side="left")
        self.b_selected = self.button(bar, t('button.extract_selected'), self.extract_selected)
        self.b_selected.pack(side="left", padx=(px(8), 0))
        self.b_to = self.button(bar, t('button.extract_to'), self.extract_to)
        self.b_to.pack(side="left", padx=(px(8), 0))
        self.b_compress = self.button(bar, t('button.compress'), self.compress)
        self.b_compress.pack(side="right")
        self.b_open = self.button(bar, t('button.open'), self.choose)
        self.b_open.pack(side="right", padx=(0, px(8)))

        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True, padx=px(14))

        # the table
        self.table_frame = tk.Frame(self.body, bg=T["line"], padx=1, pady=1)
        self.table = ttk.Treeview(self.table_frame, columns=('size', 'modified'),
                                  style="Spark.Treeview", show="tree headings",
                                  selectmode="extended")
        scroll = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.table.yview,
                               style="Spark.Vertical.TScrollbar")
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.heading('#0', text=t('col.name').upper(), anchor="w")
        self.table.heading('size', text=t('col.size').upper(), anchor="e")
        self.table.heading('modified', text=t('col.modified').upper(), anchor="w")
        self.table.column('#0', width=px(460), stretch=True)
        self.table.column('size', width=px(110), anchor="e", stretch=False)
        self.table.column('modified', width=px(150), anchor="w", stretch=False)
        self.table.tag_configure('dir', foreground=T["text"])
        self.table.tag_configure('file', foreground=T["text"])
        self.table.tag_configure('link', foreground=T["muted"])
        self.table.tag_configure('unsafe', foreground=T["pink"])
        self.table.bind('<<TreeviewOpen>>', self._expand)
        self.table.bind('<<TreeviewSelect>>', lambda _e: self._update_buttons())
        self.table.bind('<Double-1>', self._activate)
        self.table.bind('<Return>', self._activate)

        # nothing open
        self.empty = GlitchPanel(self.body, T["panel"])
        inner = self.empty.inner
        tk.Label(inner, text=t('empty.title').upper(), bg=T["panel"], fg=T["text"],
                 font=self.font(11)).pack(anchor="w", padx=px(18), pady=(px(18), px(6)))
        tk.Label(inner, text=t('empty.body'), bg=T["panel"], fg=T["muted"],
                 font=self.font(9, False), wraplength=px(560), justify="left",
                 anchor="w").pack(anchor="w", fill="x", padx=px(18), pady=(0, px(18)))

        # footer: summary, then the job or its result
        foot = tk.Frame(root, bg=bg)
        foot.pack(fill="x", padx=px(14), pady=(px(6), px(10)))
        self.summary = tk.Label(foot, text="", bg=bg, fg=T["muted"], font=self.font(8, False),
                                anchor="w")
        self.summary.pack(side="left", fill="x", expand=True)
        self.chip = tk.Label(foot, text=t('chip.password'), bg=T["panel"], fg=T["gold"],
                             font=self.font(7), padx=px(6), pady=px(1), highlightthickness=1,
                             highlightbackground=T["line2"])
        self.lower = tk.Frame(root, bg=bg)
        self.lower.pack(fill="x", padx=px(14), pady=(0, px(12)))
        self.progress = Progress(self.lower, self, self.cancel_job)
        self.result = tk.Frame(self.lower, bg=T["panel"], highlightthickness=1,
                               highlightbackground=T["line"])

        root.bind('<Control-o>', lambda _e: self.choose())
        root.bind('<Control-e>', lambda _e: self.extract_all())
        root.bind('<Escape>', lambda _e: self.cancel_job())
        self._update_buttons()

    def _show_empty(self) -> None:
        self.table_frame.pack_forget()
        self.empty.pack(fill="both", expand=True)
        self.summary.config(text="")
        self.chip.pack_forget()
        self.set_status('status.ready')
        self._update_buttons()

    def set_status(self, key: str, colour: Optional[str] = None, extra: str = '') -> None:
        text = f"● {t(key)}"
        if extra:
            text += f"  ·  {extra}"
        self.status.config(text=text, fg=colour or T["accent"])

    def _update_buttons(self) -> None:
        busy = self.job is not None
        have = self.listing is not None
        self.b_extract.set_enabled(have and not busy)
        self.b_to.set_enabled(have and not busy)
        selected = [i for i in self.table.selection() if i in self.nodes] if have else []
        self.b_selected.set_enabled(bool(selected) and not busy)
        self.b_open.set_enabled(not busy)
        self.b_compress.set_enabled(not busy)

    # ─── opening ──────────────────────────────────────────────

    def choose(self) -> None:
        if self.job is not None:
            return
        start = os.path.dirname(self.listing.path) if self.listing else os.path.expanduser('~')
        path = pick_archive(start)
        if path:
            self.open(path)

    def open(self, path: str) -> None:
        path = os.path.abspath(path)
        self.root.title(f"{os.path.basename(path)} - {APP_NAME}")
        self._hide_result()
        self.run_job(ListJob(path, asker=self.bridge.ask), 'list',
                     t('progress.reading', name=os.path.basename(path)))

    def _fill(self, listing: Listing) -> None:
        self.listing = listing
        self.tree_top = build_tree(listing)
        self.nodes = {}
        self.table.delete(*self.table.get_children())
        self._insert(self.tree_top, '')
        self.empty.pack_forget()
        self.table_frame.pack(fill="both", expand=True)
        kids = self.table.get_children()
        if len(kids) == 1 and self.nodes[kids[0]].kind == DIR:
            self.table.item(kids[0], open=True)
            self._expand_iid(kids[0])
        if kids:
            self.table.focus(kids[0])
        self.table.focus_set()
        summary = t('summary', files=listing.file_count, size=core.size(listing.total_size),
                    fmt=describe(listing.kind))
        if listing.volumes and len(listing.volumes.parts) > 1:
            summary += '  ·  ' + t('summary.parts', n=len(listing.volumes.parts))
        if listing.backend != 'python':
            summary += '  ·  ' + t('summary.read_with', backend=listing.backend)
        self.summary.config(text=summary)
        if listing.encrypted:
            self.chip.pack(side="right")
        else:
            self.chip.pack_forget()
        self.set_status('status.ready', extra=middle(os.path.basename(listing.path), 60))
        self._update_buttons()
        self.glitch.now(self.title)

    def _insert(self, node: Node, parent_iid: str) -> None:
        for child in sorted(node.children.values(), key=sort_key):
            iid = child.path
            self.nodes[iid] = child
            if child.unsafe:
                text, tag = f"{child.name}   (left out: outside the folder)", 'unsafe'
            elif child.kind == DIR:
                text, tag = child.name + '/', 'dir'
            elif child.kind in (LINK, HARDLINK):
                text, tag = f"{child.name}  →  {child.target}", 'link'
            else:
                text, tag = child.name, 'file'
            if child.encrypted:
                text += '  *'
            size = core.size(child.size) if child.kind in (FILE, DIR) and child.size else ''
            self.table.insert(parent_iid, 'end', iid=iid, text=text,
                              values=(size, core.when(child.mtime)), tags=(tag,))
            if child.kind == DIR and child.children:
                self.table.insert(iid, 'end', iid=iid + '/\0', text='')

    def _expand(self, _event=None) -> None:
        iid = self.table.focus()
        if iid:
            self._expand_iid(iid)

    def _expand_iid(self, iid: str) -> None:
        dummy = iid + '/\0'
        if self.table.exists(dummy):
            self.table.delete(dummy)
            self._insert(self.nodes[iid], iid)

    def _activate(self, _event=None) -> None:
        iid = self.table.focus()
        node = self.nodes.get(iid)
        if not node or node.unsafe or node.kind != FILE or self.job is not None:
            return
        self.open_inside(node)

    # ─── jobs ─────────────────────────────────────────────────

    def run_job(self, job: Job, kind: str, title: str, after=None) -> None:
        self.job, self.job_kind, self.job_title, self.after_job = job, kind, title, after
        self._hide_result()
        self.progress.cancel_btn.set_enabled(True)
        self.progress.pack(fill="x")
        word = {'list': 'status.reading', 'compress': 'status.compressing'}.get(
            kind, 'status.extracting')
        self.set_status(word)
        self._update_buttons()
        job.start()
        self._poll()

    def _poll(self) -> None:
        job = self.job
        if job is None:
            return
        self.bridge.pump()
        if job.phase == 'done' and job.result is not None:
            self.job = None
            self.progress.pack_forget()
            self._done(job, job.result)
            self._update_buttons()
            return
        self.progress.show_job(job, self.job_title)
        self.root.after(100, self._poll)

    def cancel_job(self) -> None:
        if self.job is not None:
            self.job.cancel()
            self.progress.cancelling()

    def _done(self, job: Job, res) -> None:
        kind = self.job_kind
        if kind == 'list':
            if res.ok and isinstance(job, ListJob) and job.listing:
                self._fill(job.listing)
                return
            if res.cancelled:
                self.set_status('status.cancelled', T["gold"])
                if self.listing is None:
                    self._show_empty()
                return
            head, lines, _err = result_lines(res, 'extract')
            self.set_status('status.error', T["pink"])
            self._show_result(head, lines, None, error=True)
            if self.listing is None:
                self._show_empty()
                self.set_status('status.error', T["pink"])
            return
        if self.after_job:
            callback, self.after_job = self.after_job, None
            if res.ok:
                callback(res)
                self.set_status('status.ready')
                return
        head, lines, error = result_lines(res, kind if kind != 'open' else 'extract',
                                          selected=kind == 'selected')
        if res.cancelled:
            self.set_status('status.cancelled', T["gold"])
        elif error:
            self.set_status('status.error', T["pink"])
        else:
            self.set_status('status.done')
        target = res.output if res.ok else None
        self._show_result(head, lines, target, error=error)

    def _show_result(self, head: str, lines: List[str], target: Optional[str],
                     error: bool = False) -> None:
        px = self.px
        for w in self.result.winfo_children():
            w.destroy()
        self.result.configure(highlightbackground=T["pink"] if error else T["line"])
        row = tk.Frame(self.result, bg=T["panel"])
        row.pack(fill="x", padx=px(12), pady=(px(10), px(4) if lines else px(10)))
        tk.Label(row, text=head, bg=T["panel"], fg=T["pink"] if error else T["text"],
                 font=self.font(9, False), anchor="w", justify="left",
                 wraplength=px(600)).pack(side="left", fill="x", expand=True)
        close = tk.Label(row, text="×", bg=T["panel"], fg=T["muted"], font=self.font(11),
                         cursor="hand2", padx=px(6))
        close.pack(side="right")
        close.bind('<ButtonRelease-1>', lambda _e: self._hide_result())
        if target:
            self.button(row, t('button.show'), lambda: show_in_file_manager(target)).pack(
                side="right", padx=(0, px(8)))
        for line in lines[:10]:
            tk.Label(self.result, text=line, bg=T["panel"], fg=T["muted"],
                     font=self.font(8, False), anchor="w").pack(fill="x", padx=px(12))
        if lines:
            tk.Frame(self.result, bg=T["panel"], height=px(8)).pack(fill="x")
        self.result.pack(fill="x")
        self.glitch.now(self.title, self.mark, strong=error)

    def _hide_result(self) -> None:
        self.result.pack_forget()

    # ─── extracting ───────────────────────────────────────────

    def _writable_dest(self) -> Optional[str]:
        """Next to the archive, or (on a read-only disk) a folder you pick."""
        folder = os.path.dirname(self.listing.path)
        if os.access(folder, os.W_OK):
            return folder
        return pick_folder(os.path.expanduser('~'))

    def _extract(self, dest: str, selection: Optional[List[str]] = None) -> None:
        listing = self.listing
        job = ExtractJob(listing.path, dest, new_folder=True, selection=selection,
                         asker=self.bridge.ask, listing=listing)
        name = os.path.basename(listing.path)
        self.run_job(job, 'selected' if selection else 'extract',
                     t('progress.extract_title', name=middle(name, 50)))

    def extract_all(self) -> None:
        if self.listing is None or self.job is not None:
            return
        dest = self._writable_dest()
        if dest:
            self._extract(dest)

    def extract_selected(self) -> None:
        if self.listing is None or self.job is not None:
            return
        chosen = [i for i in self.table.selection() if i in self.nodes and
                  not self.nodes[i].unsafe]
        if not chosen:
            return
        dest = self._writable_dest()
        if dest:
            self._extract(dest, chosen)

    def extract_to(self) -> None:
        if self.listing is None or self.job is not None:
            return
        dest = pick_folder(os.path.dirname(self.listing.path))
        if dest:
            chosen = [i for i in self.table.selection() if i in self.nodes and
                      not self.nodes[i].unsafe]
            self._extract(dest, chosen or None)

    def open_inside(self, node: Node) -> None:
        """Extract one file to a private temporary folder and open it with its usual app."""
        listing = self.listing
        temp = tempfile.mkdtemp(prefix='open-', dir=core.cache_dir())
        self.temp_dirs.append(temp)
        job = ExtractJob(listing.path, temp, new_folder=False, selection=[node.path],
                         asker=self.bridge.ask, listing=listing)

        def opened(res) -> None:
            path = os.path.join(temp, *node.path.split('/'))
            if os.path.isfile(path) and shutil.which('xdg-open'):
                subprocess.Popen(['xdg-open', path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                show_in_file_manager(path)

        self.run_job(job, 'open', t('progress.extract_title', name=middle(node.name, 50)),
                     after=opened)

    # ─── compressing ──────────────────────────────────────────

    def compress(self) -> None:
        if self.job is not None:
            return
        start = os.path.dirname(self.listing.path) if self.listing else os.path.expanduser('~')
        paths = pick_files(start)
        if not paths:
            return
        choice = self.ask_compress(len(paths), self.settings.get('format') or ZIP)
        if not choice:
            return
        fmt, password = choice
        job = CompressJob(paths, fmt, asker=self.bridge.ask, password=password)
        self.run_job(job, 'compress', t('progress.compress_title',
                                        name=os.path.basename(paths[0]) + f'.{fmt}'))

    # ─── closing ──────────────────────────────────────────────

    def close(self) -> None:
        if self.job is not None:
            self.bridge.release()
            self.job.cancel()
            self.progress.cancelling()
            self.root.after(100, self._close_when_stopped)
            return
        self._cleanup()
        self.root.destroy()

    def _close_when_stopped(self) -> None:
        self.bridge.release()
        if self.job is not None and self.job.phase != 'done':
            self.root.after(100, self._close_when_stopped)
            return
        self._cleanup()
        self.root.destroy()

    def _cleanup(self) -> None:
        # files opened from the archive: their apps may still have them open, so leave them a
        # while; anything older than a day goes
        cache = core.cache_dir()
        now = time.time()
        try:
            for name in os.listdir(cache):
                path = os.path.join(cache, name)
                if name.startswith('open-') and os.path.isdir(path) and \
                        now - os.lstat(path).st_mtime > 86400:
                    shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass

    def run(self) -> None:
        self.root.mainloop()


def process_age() -> Optional[float]:
    """Seconds since this process started (Python's own start-up included), from /proc."""
    try:
        with open('/proc/self/stat', encoding='ascii') as f:
            stat = f.read()
        with open('/proc/uptime', encoding='ascii') as f:
            up = float(f.read().split()[0])
        start = int(stat[stat.rfind(')') + 2:].split()[19])
        return up - start / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def bench(path: Optional[str], seconds: float) -> int:
    """Open the window (and an archive); report the time to first paint and to the listing,
    from the moment the process started (Python's own start-up included)."""
    age = process_age()
    base = time.monotonic() - (age or 0.0)
    app = App(path)
    shown: Dict[str, float] = {}

    def check():
        if app.first_paint and 'paint' not in shown:
            shown['paint'] = app.first_paint - base
        if path and app.listing is not None and 'listed' not in shown:
            shown['listed'] = time.monotonic() - base
        if time.monotonic() - base > seconds or ('paint' in shown and
                                                 (not path or 'listed' in shown)):
            app.root.destroy()
            return
        app.root.after(20, check)

    app.root.after(20, check)
    app.root.mainloop()
    since = "process start" if age is not None else "window creation"
    paint = shown.get('paint')
    print(f"first paint: {paint * 1000:.0f} ms after {since}" if paint is not None
          else "first paint: none")
    if path:
        listed = shown.get('listed')
        print(f"listed {os.path.basename(path)}: {listed * 1000:.0f} ms after {since}"
              if listed is not None else "listing: not finished")
    log.info("bench: %s", shown)
    return 0 if paint is not None else 1


__all__ = ['App', 'bench', 'home_short']
