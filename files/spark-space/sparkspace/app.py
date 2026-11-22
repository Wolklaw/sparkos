"""The Spark Space window: the drives, a scan in progress, and the results (treemap, lists,
actions)."""

import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from typing import Callable, Dict, List, Optional

from . import APP_CLASS, APP_NAME, dialogs, drives, hints as hintmod, safety, scan, trash
from .core import count, home, home_short, human_size, log, pct, reduced_motion
from .kinds import KINDS
from .text import t
from .treemap import squarify
from .widgets import (T, Glitch, GlitchPanel, GlitchText, IconButton, Mark, Segmented, Strip,
                      WolkButton, make_table, mix, pick_mono, style_tables)

# treemap colours: folders darken with depth, files by kind
DIR_FILL = ("#0e1f22", "#11272a", "#142e32", "#173539")
KIND_FILL = {
    'video': "#3b2d63", 'games': "#5a4718", 'models': "#4a2440", 'archives': "#5a3620",
    'apps': "#23395e", 'images': "#1d4a3b", 'audio': "#1f3f5c", 'documents': "#2b4446",
    'other': "#1b3134",
}
KIND_SWATCH = {
    'video': "#b9a6ff", 'games': T["gold"], 'models': T["pink"], 'archives': "#f0a671",
    'apps': "#8ec9ff", 'images': "#52e8a4", 'audio': T["ch_b"], 'documents': T["accent"],
    'other': T["muted"],
}
MAX_DEPTH = 3
MAP_BUDGET = 1400            # rectangles per drawing, so a huge folder still draws fast
LIST_LIMIT = 1500            # rows in the folder list; the rest are summed in one row


def launch(argv: List[str]) -> bool:
    """Start a program without waiting for it."""
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("couldn't start %s: %s", argv[0], exc)
        return False


def show_in_folder_command(path: str) -> List[str]:
    """Spark Files with the item selected; the desktop's file manager otherwise."""
    spark_files = shutil.which('spark-files')
    if spark_files:
        return [spark_files, '--select', path]
    return ['xdg-open', os.path.dirname(path) or '/']


def drive_title(d: drives.Drive) -> str:
    if d.letter:
        return t('drive.letter', letter=d.letter) + (f"  {d.label}" if d.label else '')
    if d.is_home:
        return t('drive.sparkos')
    return d.label or os.path.basename(d.path.rstrip('/')) or d.path


class App:
    def __init__(self, start: Optional[str] = None, threads: int = 4,
                 opener: Callable[[List[str]], bool] = launch,
                 ask: Optional[Callable[..., bool]] = None,
                 tell: Optional[Callable[..., object]] = None,
                 warn: Optional[Callable[..., object]] = None,
                 error: Optional[Callable[..., object]] = None):
        # the dialogs can be swapped (the tests answer them; nothing modal blocks a test)
        self.opener = opener
        self.ask = ask or dialogs.askyesno
        self.tell = tell or dialogs.showinfo
        self.warn = warn or dialogs.showwarning
        self.error = error or dialogs.showerror
        self.threads = threads
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        try:
            self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            self.scale = 1.0
        self.root.geometry(f"{self.px(1180)}x{self.px(760)}")
        self.root.minsize(self.px(820), self.px(560))
        family = pick_mono(self.root)
        self.f_body = tkfont.Font(root=self.root, family=family, size=9)
        self.f_small = tkfont.Font(root=self.root, family=family, size=8)
        self.f_label = tkfont.Font(root=self.root, family=family, size=7, weight="bold")
        self.f_title = tkfont.Font(root=self.root, family=family, size=11, weight="bold")
        self.f_head = tkfont.Font(root=self.root, family=family, size=15, weight="bold")
        self.f_brand = tkfont.Font(root=self.root, family=family, size=10, weight="bold")
        self.f_map = tkfont.Font(root=self.root, family=family, size=8)
        style_tables(self.root, self.f_body, self.f_label, self.px(22))
        self.glitch = Glitch(self.root, not reduced_motion())
        self.scanner: Optional[scan.Scanner] = None
        self.return_to: Optional[str] = None
        self.closed = False

        self._header()
        self.body = tk.Frame(self.root, bg=T["bg"])
        self.body.pack(fill="both", expand=True)
        self.home_screen = HomeScreen(self)
        self.progress_screen = ProgressScreen(self)
        self.results = ResultsScreen(self)
        self.screen: Optional[tk.Frame] = None
        self.show(self.home_screen)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for seq in ("<Control-q>", "<Control-w>"):
            self.root.bind(seq, lambda _e: self.close())
        self.root.bind("<Escape>", lambda _e: self.cancel_scan())
        self.root.bind("<F5>", lambda _e: self.rescan())
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        if start:
            self.root.after_idle(lambda: self.scan(start))

    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    # ── header ──

    def _header(self):
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=self.px(14), pady=(self.px(10), self.px(6)))
        self.mark = Mark(bar, self.px(26), T["bg"])
        self.mark.pack(side="left")
        self.title = GlitchText(bar, APP_NAME.upper(), self.f_brand, T["bg"])
        self.title.pack(side="left", padx=(self.px(8), 0))
        self.status = tk.Label(bar, text="", bg=T["bg"], fg=T["accent"], font=self.f_label)
        self.status.pack(side="right")
        self.strip = Strip(self.root, height=2)
        self.strip.pack(fill="x")
        self.set_status('status.ready')

    def set_status(self, key: str, colour: Optional[str] = None, **kw):
        self.status.config(text="● " + t(key, **kw), fg=colour or T["accent"])

    def show(self, screen: tk.Frame):
        if self.screen is screen:
            return
        if self.screen is not None:
            self.screen.pack_forget()
        self.screen = screen
        screen.pack(fill="both", expand=True)

    def event(self, *targets, strong: bool = False):
        """Something happened: the house fault on the header and whatever else is named."""
        self.glitch.now(self.title, self.strip, *targets, strong=strong)

    # ── scanning ──

    def scan(self, path: str, return_to: Optional[str] = None):
        if self.scanner is not None and not self.scanner.finished.is_set():
            self.scanner.cancel()
        path = os.path.abspath(os.path.expanduser(path))
        scanner = scan.Scanner(path, threads=self.threads, after=self._after_scan)
        scanner.hints = []                  # type: ignore[attr-defined]
        try:
            scanner.start()
        except OSError as exc:
            self.set_status('status.error', T["pink"])
            self.event(strong=True)
            self.error(t('error.cant_scan_title'),
                              t('error.cant_scan', path=path, error=exc.strerror or str(exc)),
                              parent=self.root)
            return
        log.info("scanning %s", path)
        self.scanner = scanner
        self.return_to = return_to
        self.progress_screen.begin(scanner)
        self.show(self.progress_screen)
        self.set_status('status.scanning', T["gold"])
        self.event(self.progress_screen.heading)
        self.root.after(100, self._poll)

    @staticmethod
    def _after_scan(scanner: scan.Scanner):
        # runs on the scan's thread, so the window gets a finished tree with its hints
        if scanner.root is not None:
            scanner.hints = hintmod.find_hints(scanner.root)   # type: ignore[attr-defined]

    def _poll(self):
        if self.closed or self.scanner is None:
            return
        if self.scanner.finished.is_set():
            self._done()
            return
        self.progress_screen.update_numbers()
        self.root.after(120, self._poll)

    def _done(self):
        s = self.scanner
        files, dirs, _size = s.progress()
        log.info("scanned %s: %d files, %d folders, %d bytes in %.2f s%s", s.root_path, files,
                 dirs, s.root.size, s.elapsed, " (cancelled)" if s.cancelled.is_set() else "")
        self.results.load(s, s.hints, self.return_to)     # type: ignore[attr-defined]
        self.show(self.results)
        if s.cancelled.is_set():
            self.set_status('status.cancelled', T["pink"])
        else:
            self.set_status('status.done', seconds=f"{s.elapsed:.1f}")
        self.event(self.results.map_panel, strong=True)

    def cancel_scan(self):
        if self.scanner is not None and not self.scanner.finished.is_set():
            self.scanner.cancel()

    def rescan(self):
        if self.scanner is not None and self.scanner.finished.is_set():
            current = self.results.current.path() if self.results.current else None
            self.scan(self.scanner.root_path, return_to=current)

    def choose_folder(self):
        path = filedialog.askdirectory(parent=self.root, title=t('home.choose_title'),
                                       initialdir=home(), mustexist=True)
        if path:
            self.scan(path)

    # ── actions ──

    def open_path(self, path: str):
        if not self.opener(['xdg-open', path]):
            self.error(t('error.open_title'), t('error.open', path=path), parent=self.root)

    def show_in_folder(self, path: str):
        if not self.opener(show_in_folder_command(path)):
            self.opener(['xdg-open', os.path.dirname(path) or '/'])

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel_scan()
        if self.results.map_job is not None:
            try:
                self.results.after_cancel(self.results.map_job)
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ─── The start screen: drives, home, a folder ─────────────────────────

class HomeScreen(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        top = tk.Frame(self, bg=T["bg"])
        top.pack(fill="x", padx=px(22), pady=(px(18), px(4)))
        self.heading = GlitchText(top, t('home.heading'), app.f_head, T["bg"])
        self.heading.pack(anchor="w")
        tk.Label(top, text=t('home.sub'), bg=T["bg"], fg=T["muted"], font=app.f_body,
                 anchor="w").pack(fill="x", pady=(px(2), 0))
        self.grid_frame = tk.Frame(self, bg=T["bg"])
        self.grid_frame.pack(fill="both", expand=True, padx=px(16), pady=px(10))
        self.cards: Dict[str, Dict] = {}
        self.measured: 'queue.Queue' = queue.Queue()
        self.drives = drives.list_drives()
        self._build()
        app.glitch.add(self.heading)
        threading.Thread(target=self._measure, daemon=True, name='spark-space-df').start()
        self.after(60, self._poll_measure)

    def _card(self, column: int, row: int) -> tk.Frame:
        panel = GlitchPanel(self.grid_frame, T["panel"])
        panel.grid(row=row, column=column, sticky="nsew", padx=self.app.px(6),
                   pady=self.app.px(6))
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="both", expand=True, padx=self.app.px(14), pady=self.app.px(12))
        return panel, inner

    def _build(self):
        app, px = self.app, self.app.px
        for c in range(2):
            self.grid_frame.columnconfigure(c, weight=1, uniform="cards")
        items = list(self.drives)
        n = 0
        for d in items:
            panel, inner = self._card(n % 2, n // 2)
            head = tk.Frame(inner, bg=T["panel"])
            head.pack(fill="x")
            tk.Label(head, text=drive_title(d).upper(), bg=T["panel"], fg=T["text"],
                     font=app.f_title, anchor="w").pack(side="left")
            chips = []
            if d.fstype:
                chips.append((d.fstype.replace('ntfs3', 'ntfs').upper(), T["muted"]))
            if d.read_only:
                chips.append((t('chip.read_only'), T["gold"]))
            if not d.mounted:
                chips.append((t('chip.not_mounted'), T["pink"]))
            for text, colour in reversed(chips):
                tk.Label(head, text=text, bg=T["panel"], fg=colour, font=app.f_label,
                         highlightthickness=1, highlightbackground=T["line2"], padx=px(5),
                         pady=px(1)).pack(side="right", padx=(px(4), 0))
            tk.Label(inner, text=home_short(d.path) if d.path != home() else d.path,
                     bg=T["panel"], fg=T["muted"], font=app.f_small, anchor="w").pack(fill="x")
            bar = tk.Canvas(inner, height=px(10), bg=T["panel"], highlightthickness=0, bd=0)
            bar.pack(fill="x", pady=(px(8), px(4)))
            numbers = tk.Label(inner, text=t('drive.measuring') if d.mounted else '',
                               bg=T["panel"], fg=T["text"], font=app.f_body, anchor="w")
            numbers.pack(fill="x")
            note = self._note(d)
            if note:
                tk.Label(inner, text=note, bg=T["panel"], fg=T["gold"] if d.read_only or
                         d.problem else T["muted"], font=app.f_small, anchor="w",
                         justify="left", wraplength=px(470)).pack(fill="x", pady=(px(4), 0))
            if d.mounted:
                row = tk.Frame(inner, bg=T["panel"])
                row.pack(fill="x", pady=(px(10), 0))
                WolkButton(row, t('home.scan_drive'), lambda p=d.path: app.scan(p),
                           app.f_label, variant="primary").pack(side="left")
                if d.is_home:
                    WolkButton(row, t('home.scan_home'), lambda: app.scan(home()),
                               app.f_label).pack(side="left", padx=(px(6), 0))
            bar.bind("<Configure>", lambda _e, k=d.path: self._draw_bar(k))
            self.cards[d.path] = {'drive': d, 'bar': bar, 'numbers': numbers, 'panel': panel}
            n += 1
        # your home (when no drive card already offers it) and any folder
        if not any(d.is_home for d in items):
            panel, inner = self._card(n % 2, n // 2)
            tk.Label(inner, text=t('home.home_title'), bg=T["panel"], fg=T["text"],
                     font=app.f_title, anchor="w").pack(fill="x")
            tk.Label(inner, text=home(), bg=T["panel"], fg=T["muted"], font=app.f_small,
                     anchor="w").pack(fill="x")
            WolkButton(inner, t('home.scan_home'), lambda: app.scan(home()), app.f_label,
                       variant="primary").pack(anchor="w", pady=(px(10), 0))
            n += 1
        panel, inner = self._card(n % 2, n // 2)
        tk.Label(inner, text=t('home.folder_title'), bg=T["panel"], fg=T["text"],
                 font=app.f_title, anchor="w").pack(fill="x")
        tk.Label(inner, text=t('home.folder_body'), bg=T["panel"], fg=T["muted"],
                 font=app.f_small, anchor="w", justify="left",
                 wraplength=px(470)).pack(fill="x")
        WolkButton(inner, t('home.choose'), app.choose_folder, app.f_label).pack(
            anchor="w", pady=(px(10), 0))

    @staticmethod
    def _note(d: drives.Drive) -> str:
        lines = []
        if d.letter.lower() in safety.NEVER_DRIVE_LETTERS or \
                d.path in safety.NEVER_DRIVE_PATHS:
            lines.append(t('drive.never_note'))
        elif d.read_only:
            lines.append(t('drive.ro_note'))
        if d.problem:
            lines.append(d.problem)
        if d.fstype == 'btrfs':
            lines.append(t('drive.btrfs_note'))
        if d.is_home and d.fstype == 'btrfs':
            lines.append(t('drive.var_note'))
        return "\n".join(lines)

    def _measure(self):
        for d in self.drives:
            if d.mounted:
                d.measure()
            self.measured.put(d.path)

    def _poll_measure(self):
        done = 0
        while True:
            try:
                path = self.measured.get_nowait()
            except queue.Empty:
                break
            done += 1
            card = self.cards.get(path)
            if card:
                d = card['drive']
                if d.total:
                    card['numbers'].config(text=t('drive.numbers', used=human_size(d.used),
                                                  free=human_size(d.free),
                                                  total=human_size(d.total)))
                elif d.mounted:
                    card['numbers'].config(text=t('drive.no_numbers'))
                self._draw_bar(path)
        self.remaining = getattr(self, 'remaining', len(self.drives)) - done
        if self.remaining > 0 and self.winfo_exists():
            self.after(60, self._poll_measure)

    def _draw_bar(self, path: str):
        card = self.cards.get(path)
        if not card:
            return
        bar, d = card['bar'], card['drive']
        bar.delete("all")
        w, h = bar.winfo_width(), int(bar.cget("height"))
        bar.create_rectangle(0, 0, w - 1, h - 1, fill=T["bg"], outline=T["line"])
        if d.total:
            frac = d.used / d.total
            colour = T["pink"] if frac >= 0.9 else (T["gold"] if frac >= 0.75 else T["accent"])
            x = max(2, int((w - 2) * frac))
            bar.create_rectangle(1, 1, x, h - 2, fill=colour, outline="")


# ─── A scan in progress ───────────────────────────────────────────────

class ProgressScreen(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        box = tk.Frame(self, bg=T["bg"])
        box.place(relx=0.5, rely=0.42, anchor="center")
        self.heading = GlitchText(box, t('progress.heading'), app.f_head, T["bg"])
        self.heading.pack(anchor="w")
        self.path = tk.Label(box, text="", bg=T["bg"], fg=T["muted"], font=app.f_body,
                             anchor="w")
        self.path.pack(fill="x", pady=(px(2), px(14)))
        grid = tk.Frame(box, bg=T["bg"])
        grid.pack(fill="x")
        self.values = {}
        for i, key in enumerate(('files', 'folders', 'size', 'unreadable')):
            tk.Label(grid, text=t('progress.' + key), bg=T["bg"], fg=T["muted"],
                     font=app.f_label, anchor="w").grid(row=0, column=i, sticky="w",
                                                        padx=(0, px(28)))
            value = tk.Label(grid, text="0", bg=T["bg"], fg=T["text"], font=app.f_title,
                             anchor="w")
            value.grid(row=1, column=i, sticky="w", padx=(0, px(28)))
            self.values[key] = value
        self.current = tk.Label(box, text="", bg=T["bg"], fg=T["dim"], font=app.f_small,
                                anchor="w", width=80)
        self.current.pack(fill="x", pady=(px(14), px(14)))
        self.cancel = WolkButton(box, t('progress.cancel'), app.cancel_scan, app.f_label,
                                 variant="danger")
        self.cancel.pack(anchor="w")
        self.scanner: Optional[scan.Scanner] = None
        self.ticks = 0

    def begin(self, scanner: scan.Scanner):
        self.scanner = scanner
        self.ticks = 0
        self.path.config(text=scanner.root_path)
        self.update_numbers()

    def update_numbers(self):
        s = self.scanner
        if s is None:
            return
        files, dirs, size = s.progress()
        self.values['files'].config(text=count(files))
        self.values['folders'].config(text=count(dirs))
        self.values['size'].config(text=human_size(size))
        self.values['unreadable'].config(text=count(s.unreadable_count),
                                         fg=T["gold"] if s.unreadable_count else T["text"])
        current = s.current
        if len(current) > 78:
            current = "…" + current[-77:]
        self.current.config(text=current)
        self.ticks += 1
        if self.ticks % 12 == 0:            # a small tear every second and a half: it's alive
            self.app.strip.burst()


# ─── Results ──────────────────────────────────────────────────────────

class ResultsScreen(tk.Frame):
    TABS = ('folder', 'largest', 'types', 'hints')

    def __init__(self, app: App):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        self.scanner: Optional[scan.Scanner] = None
        self.root_node: Optional[scan.Node] = None
        self.current: Optional[scan.Node] = None
        self.selected: Optional[scan.Node] = None
        self.hints: List[hintmod.Hint] = []
        self.hint_nodes: Dict[int, hintmod.Hint] = {}
        self.kind_filter: Optional[str] = None
        self.summary: Optional[scan.Summary] = None
        self.summary_for: Optional[scan.Node] = None
        self.summary_gen = 0
        self.summary_queue: 'queue.Queue' = queue.Queue()
        self.summary_polling = False
        self.map_items: Dict[str, scan.Node] = {}
        self.map_job: Optional[str] = None
        self.hover_tag: Optional[str] = None
        self.tab = 'folder'

        # toolbar: back to drives, up, the breadcrumb, rescan
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(8), px(4)))
        IconButton(bar, "back", lambda: app.show(app.home_screen), px(26),
                   tip=t('results.drives')).pack(side="left")
        self.up_button = IconButton(bar, "up", self.go_up, px(26), tip=t('results.up'))
        self.up_button.pack(side="left", padx=(px(4), px(8)))
        self.crumbs = tk.Frame(bar, bg=T["bg"])
        self.crumbs.pack(side="left", fill="x", expand=True)
        WolkButton(bar, t('results.rescan'), app.rescan, app.f_label).pack(side="right")

        info = tk.Frame(self, bg=T["bg"])
        info.pack(fill="x", padx=px(16))
        self.summary_label = tk.Label(info, text="", bg=T["bg"], fg=T["text"], font=app.f_body,
                                      anchor="w", justify="left")
        self.summary_label.pack(side="left")
        self.unreadable_button = WolkButton(info, t('results.which'), self.show_unreadable,
                                            app.f_label, padx=8, pady=2)
        self.note_label = tk.Label(self, text="", bg=T["bg"], fg=T["muted"], font=app.f_small,
                                   anchor="w", justify="left")
        self.note_label.pack(fill="x", padx=px(16), pady=(px(2), px(6)))
        self.note_label.bind("<Configure>", lambda e: self.note_label.config(
            wraplength=max(200, e.width - 10)))

        # actions at the bottom (packed before the middle so they keep their room)
        actions = tk.Frame(self, bg=T["panel"], highlightthickness=1,
                           highlightbackground=T["line"])
        actions.pack(side="bottom", fill="x", padx=px(14), pady=(px(6), px(12)))
        left = tk.Frame(actions, bg=T["panel"])
        left.pack(side="left", fill="x", expand=True, padx=px(10), pady=px(6))
        self.sel_name = tk.Label(left, text=t('results.nothing_selected'), bg=T["panel"],
                                 fg=T["text"], font=app.f_body, anchor="w")
        self.sel_name.pack(fill="x")
        self.sel_detail = tk.Label(left, text="", bg=T["panel"], fg=T["muted"],
                                   font=app.f_small, anchor="w")
        self.sel_detail.pack(fill="x")
        buttons = tk.Frame(actions, bg=T["panel"])
        buttons.pack(side="right", padx=px(8), pady=px(6))
        self.b_open = WolkButton(buttons, t('action.open'), self.open_selected, app.f_label)
        self.b_show = WolkButton(buttons, t('action.show'), self.show_selected, app.f_label)
        self.b_trash = WolkButton(buttons, t('action.trash'), self.trash_selected, app.f_label,
                                  variant="danger")
        for b in (self.b_open, self.b_show, self.b_trash):
            b.pack(side="left", padx=(px(4), 0))

        # the middle: treemap | lists
        middle = tk.PanedWindow(self, orient="horizontal", bg=T["bg"], sashwidth=px(6),
                                bd=0, opaqueresize=False)
        middle.pack(fill="both", expand=True, padx=px(14))
        self.map_panel = GlitchPanel(middle, T["panel"])
        self.canvas = tk.Canvas(self.map_panel.inner, bg=T["panel"], highlightthickness=0,
                                bd=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        middle.add(self.map_panel, stretch="always", minsize=px(300))
        side = tk.Frame(middle, bg=T["bg"])
        middle.add(side, stretch="never", minsize=px(330), width=px(460))
        self.tabs = Segmented(side, [(t('tab.' + k), k) for k in self.TABS], 'folder',
                              self.set_tab, app.f_label)
        self.tabs.pack(anchor="w", pady=(0, px(6)))
        self.pages = tk.Frame(side, bg=T["bg"])
        self.pages.pack(fill="both", expand=True)
        self._build_pages()

        c = self.canvas
        c.bind("<Configure>", lambda _e: self.schedule_map())
        c.bind("<Motion>", self._map_motion)
        c.bind("<Leave>", lambda _e: self._map_hover(None))
        c.bind("<ButtonRelease-1>", self._map_click)
        c.bind("<Double-Button-1>", self._map_double)
        c.bind("<Button-3>", self._map_menu)
        for widget in (self, c):
            widget.bind("<BackSpace>", lambda _e: self.go_up())
            widget.bind("<Alt-Up>", lambda _e: self.go_up())
            widget.bind("<Delete>", lambda _e: self.trash_selected())
        self.menu = tk.Menu(self, tearoff=0, bg=T["panel"], fg=T["text"],
                            activebackground=T["hover"], activeforeground=T["accent"],
                            font=app.f_body, bd=1, relief="flat")
        self.menu.add_command(label=t('action.open'), command=self.open_selected)
        self.menu.add_command(label=t('action.show'), command=self.show_selected)
        self.menu.add_separator()
        self.menu.add_command(label=t('action.trash'), command=self.trash_selected)
        self.update_actions()

    # ── the lists ──

    def _build_pages(self):
        app, px = self.app, self.app.px
        self.page = {}
        # this folder
        frame, tree = make_table(self.pages, ('size', 'pct', 'bar', 'files'))
        tree.heading('#0', text=t('col.name'), anchor="w")
        for col, width, anchor in (('size', 80, 'e'), ('pct', 52, 'e'), ('bar', 70, 'w'),
                                   ('files', 72, 'e')):
            tree.heading(col, text=t('col.' + col), anchor=anchor)
            tree.column(col, width=px(width), minwidth=px(40), stretch=False, anchor=anchor)
        tree.column('#0', width=px(140), minwidth=px(80), stretch=True)
        self.folder_tree = tree
        self.page['folder'] = frame
        # largest files
        page = tk.Frame(self.pages, bg=T["bg"])
        self.filter_row = tk.Frame(page, bg=T["bg"])
        self.filter_label = tk.Label(self.filter_row, text="", bg=T["bg"], fg=T["gold"],
                                     font=app.f_label)
        self.filter_label.pack(side="left")
        WolkButton(self.filter_row, t('largest.all_types'), lambda: self.set_filter(None),
                   app.f_label, padx=8, pady=2).pack(side="left", padx=(px(8), 0))
        frame, tree = make_table(page, ('size', 'kind', 'where'))
        frame.pack(fill="both", expand=True)
        tree.heading('#0', text=t('col.name'), anchor="w")
        tree.heading('size', text=t('col.size'), anchor="e")
        tree.heading('kind', text=t('col.kind'), anchor="w")
        tree.heading('where', text=t('col.where'), anchor="w")
        tree.column('#0', width=px(170), minwidth=px(90), stretch=True)
        tree.column('size', width=px(78), stretch=False, anchor="e")
        tree.column('kind', width=px(80), stretch=False)
        tree.column('where', width=px(160), minwidth=px(60), stretch=True)
        self.largest_tree = tree
        self.page['largest'] = page
        # types
        page = tk.Frame(self.pages, bg=T["bg"])
        frame, tree = make_table(page, ('size', 'pct', 'files'))
        frame.pack(fill="both", expand=True)
        tree.heading('#0', text=t('col.kind'), anchor="w")
        for col, width in (('size', 84), ('pct', 60), ('files', 84)):
            tree.heading(col, text=t('col.' + col), anchor="e")
            tree.column(col, width=px(width), stretch=False, anchor="e")
        tree.column('#0', width=px(150), stretch=True)
        tk.Label(page, text=t('types.help'), bg=T["bg"], fg=T["muted"], font=app.f_small,
                 anchor="w", justify="left", wraplength=px(420)).pack(fill="x", pady=(px(6), 0))
        for kind in KINDS:
            tree.tag_configure('k_' + kind, foreground=KIND_SWATCH[kind])
        self.types_tree = tree
        self.page['types'] = page
        # hints
        page = tk.Frame(self.pages, bg=T["bg"])
        frame, tree = make_table(page, ('size',))
        frame.pack(fill="both", expand=True)
        tree.heading('#0', text=t('col.spot'), anchor="w")
        tree.heading('size', text=t('col.size'), anchor="e")
        tree.column('#0', width=px(260), stretch=True)
        tree.column('size', width=px(84), stretch=False, anchor="e")
        detail = tk.Frame(page, bg=T["panel"], highlightthickness=1,
                          highlightbackground=T["line"])
        detail.pack(fill="x", pady=(px(6), 0))
        self.hint_text = tk.Label(detail, text=t('hints.intro'), bg=T["panel"], fg=T["text"],
                                  font=app.f_small, anchor="w", justify="left",
                                  wraplength=px(420))
        self.hint_text.pack(fill="x", padx=px(10), pady=(px(8), px(4)))
        self.hint_command_row = tk.Frame(detail, bg=T["panel"])
        self.hint_command = tk.Entry(self.hint_command_row, font=app.f_small, bg=T["bg"],
                                     fg=T["accent"], readonlybackground=T["bg"],
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=T["line2"], state="readonly")
        self.hint_command.pack(side="left", fill="x", expand=True, ipady=px(3))
        WolkButton(self.hint_command_row, t('hints.copy'), self.copy_command, app.f_label,
                   padx=8, pady=2).pack(side="left", padx=(px(6), 0))
        self.hints_tree = tree
        self.page['hints'] = page
        self.hint_text.bind("<Configure>", lambda e: self.hint_text.config(
            wraplength=max(200, e.width - 4)))

        self.rows: Dict[str, Dict[str, scan.Node]] = {k: {} for k in self.TABS}
        for name, tree in (('folder', self.folder_tree), ('largest', self.largest_tree),
                           ('hints', self.hints_tree)):
            tree.bind("<<TreeviewSelect>>", lambda _e, n=name: self._row_selected(n))
            tree.bind("<Double-Button-1>", lambda _e, n=name: self._row_double(n))
            tree.bind("<Return>", lambda _e, n=name: self._row_double(n))
            tree.bind("<Button-3>", lambda e, n=name: self._row_menu(n, e))
            tree.bind("<BackSpace>", lambda _e: self.go_up())
            tree.bind("<Delete>", lambda _e: self.trash_selected())
        self.types_tree.bind("<<TreeviewSelect>>", lambda _e: self._type_selected())
        self.page['folder'].pack(fill="both", expand=True)

    def set_tab(self, tab: str):
        if tab == self.tab:
            return
        self.page[self.tab].pack_forget()
        self.tab = tab
        self.tabs.set(tab)
        self.page[tab].pack(fill="both", expand=True)
        if tab in ('largest', 'types'):
            self.need_summary()
        self.app.event(self.map_panel)

    # ── loading a scan ──

    def load(self, scanner: scan.Scanner, hints: List[hintmod.Hint],
             return_to: Optional[str] = None):
        self.scanner = scanner
        self.root_node = scanner.root
        self.hints = hints
        self.hint_nodes = {id(h.node): h for h in hints}
        self.kind_filter = None
        self.selected = None
        target = scan.find(scanner.root, return_to) if return_to else None
        self._show_summary()
        self._fill_hints()
        self.go(target if target is not None and target.is_dir else scanner.root)

    def _show_summary(self):
        s, root = self.scanner, self.root_node
        files, dirs, _ = s.progress()
        text = t('results.summary', size=human_size(root.size), files=count(root.count),
                 folders=count(dirs), seconds=f"{s.elapsed:.1f}")
        notes = []
        if s.cancelled.is_set():
            notes.append(t('results.partial'))
        if s.unreadable_count:
            text += "  ·  " + t('results.unreadable', n=count(s.unreadable_count))
            self.unreadable_button.pack(side="left", padx=(self.app.px(8), 0))
        else:
            self.unreadable_button.pack_forget()
        self.summary_label.config(text=text, fg=T["text"])
        if s.skipped_mounts:
            notes.append(t('results.other_fs', n=len(s.skipped_mounts)))
        mount = drives.mount_of(s.root_path)
        if mount is not None and mount.fstype == 'btrfs':
            notes.append(t('results.btrfs'))
        if mount is not None and os.path.normpath(mount.target) == s.root_path:
            d = drives.Drive(s.root_path, '')
            d.measure()
            if d.used is not None:
                notes.append(t('results.df', used=human_size(d.used),
                               found=human_size(root.size)))
        if mount is not None and mount.read_only:
            notes.append(t('results.read_only'))
        self.note_label.config(text="\n".join(notes), fg=T["gold"] if s.cancelled.is_set()
                               else T["muted"])

    def show_unreadable(self):
        s = self.scanner
        if s is None:
            return
        shown = s.unreadable[:40]
        detail = "\n".join(shown)
        if s.unreadable_count > len(shown):
            detail += "\n" + t('unreadable.more', n=count(s.unreadable_count - len(shown)))
        self.app.tell(t('unreadable.title'), t('unreadable.body'), detail=detail,
                      parent=self.app.root)

    # ── moving around ──

    def go(self, node: scan.Node):
        if node is None or not node.is_dir:
            return
        self.current = node
        self.selected = None
        self.summary = None
        self.summary_for = None
        self._crumbs()
        self._fill_folder()
        self.schedule_map(0)
        self.update_actions()
        self.up_button.set_enabled(node.parent is not None)
        if self.tab in ('largest', 'types'):
            self.need_summary()
        else:
            self.largest_tree.delete(*self.largest_tree.get_children())
            self.types_tree.delete(*self.types_tree.get_children())

    def go_up(self):
        if self.current is not None and self.current.parent is not None:
            child = self.current
            self.go(self.current.parent)
            self.select(child)
            self.app.event(self.map_panel)

    def drill(self, node: scan.Node):
        if node.is_dir and not node.flags & (scan.OTHER_FS | scan.SYSTEM):
            self.go(node)
            self.app.event(self.map_panel)

    def _crumbs(self):
        for w in self.crumbs.winfo_children():
            w.destroy()
        chain = self.current.ancestors()
        if len(chain) > 6:
            chain = chain[:1] + [None] + chain[-4:]
        for i, node in enumerate(chain):
            if i:
                tk.Label(self.crumbs, text="/", bg=T["bg"], fg=T["dim"],
                         font=self.app.f_body).pack(side="left")
            if node is None:
                tk.Label(self.crumbs, text="…", bg=T["bg"], fg=T["dim"],
                         font=self.app.f_body).pack(side="left")
                continue
            name = home_short(node.name) if node.parent is None else node.name
            last = node is self.current
            label = tk.Label(self.crumbs, text=name, bg=T["bg"],
                             fg=T["accent"] if last else T["muted"],
                             font=self.app.f_title if last else self.app.f_body,
                             cursor="arrow" if last else "hand2", padx=2)
            label.pack(side="left")
            if not last:
                label.bind("<ButtonRelease-1>", lambda _e, n=node: (self.go(n),
                                                                     self.app.event()))
                label.bind("<Enter>", lambda _e, w=label: w.config(fg=T["text"]))
                label.bind("<Leave>", lambda _e, w=label: w.config(fg=T["muted"]))

    def _label(self, node: scan.Node) -> str:
        name = node.name + ("/" if node.is_dir else "")
        if node.flags & scan.OTHER_FS:
            name += "  " + t('flag.other_fs')
        elif node.flags & scan.SYSTEM:
            name += "  " + t('flag.system')
        elif node.flags & scan.UNREADABLE:
            name += "  " + t('flag.unreadable')
        elif node.flags & scan.SHARED:
            name += "  " + t('flag.shared')
        elif node.flags & scan.LINK:
            name += "  " + t('flag.link')
        return name

    def _tag(self, node: scan.Node) -> tuple:
        if id(node) in self.hint_nodes:
            return ('hint',)
        if node.flags & (scan.OTHER_FS | scan.SYSTEM | scan.SHARED | scan.LINK):
            return ('off',)
        if node.flags & scan.UNREADABLE:
            return ('warn',)
        return ()

    def _fill_folder(self):
        tree = self.folder_tree
        tree.delete(*tree.get_children())
        rows = self.rows['folder'] = {}
        node = self.current
        total = node.size or 1
        kids = node.sorted_children()
        for i, child in enumerate(kids[:LIST_LIMIT]):
            frac = child.size / total
            filled = int(round(frac * 10))
            bar = "█" * filled + "·" * (10 - filled)
            iid = f"f{i}"
            tree.insert('', 'end', iid=iid, text=self._label(child), tags=self._tag(child),
                        values=(human_size(child.size), pct(child.size, total), bar,
                                count(child.count) if child.is_dir else ''))
            rows[iid] = child
        if len(kids) > LIST_LIMIT:
            rest = kids[LIST_LIMIT:]
            size = sum(k.size for k in rest)
            tree.insert('', 'end', iid='rest', text=t('list.more', n=count(len(rest))),
                        tags=('muted',), values=(human_size(size), pct(size, total), '', ''))
        if not kids:
            tree.insert('', 'end', iid='empty', text=t('list.empty'), tags=('muted',),
                        values=('', '', '', ''))

    def _fill_hints(self):
        tree = self.hints_tree
        tree.delete(*tree.get_children())
        rows = self.rows['hints'] = {}
        for i, h in enumerate(self.hints):
            iid = f"h{i}"
            tree.insert('', 'end', iid=iid, text=f"{t('hint.' + h.key + '.title')}  ·  "
                        f"{home_short(h.node.path())}", values=(human_size(h.node.size),),
                        tags=('hint',))
            rows[iid] = h.node
        if not self.hints:
            tree.insert('', 'end', iid='none', text=t('hints.none'), tags=('muted',),
                        values=('',))
        self.tabs.labels['hints'].config(
            text=t('tab.hints') + (f" {len(self.hints)}" if self.hints else ''))

    # ── largest files and types (worked out on a thread) ──

    def need_summary(self):
        node = self.current
        if node is None:
            return
        key = (id(node), self.kind_filter)
        if self.summary is not None and self.summary_for == key:
            self._fill_summary()
            return
        self.summary_gen += 1
        gen = self.summary_gen
        self.summary_for = key
        self.largest_tree.delete(*self.largest_tree.get_children())
        self.largest_tree.insert('', 'end', iid='wait', text=t('list.working'), tags=('muted',),
                                 values=('', '', ''))
        kind = self.kind_filter

        def work():
            result = scan.summarize(node, kind=kind)
            self.summary_queue.put((gen, result))
        threading.Thread(target=work, daemon=True, name='spark-space-summary').start()
        if not self.summary_polling:
            self.summary_polling = True
            self.after(50, self._poll_summary)

    def _poll_summary(self):
        # one poll loop at a time; it ends once the newest request's answer is in
        self.summary_polling = False
        while True:
            try:
                gen, result = self.summary_queue.get_nowait()
            except queue.Empty:
                break
            if gen == self.summary_gen:
                self.summary = result
                self._fill_summary()
                return
        if self.winfo_exists():
            self.summary_polling = True
            self.after(50, self._poll_summary)

    def _fill_summary(self):
        s = self.summary
        tree = self.largest_tree
        tree.delete(*tree.get_children())
        rows = self.rows['largest'] = {}
        base = self.current.path() if self.current else ''
        for i, (f, kind) in enumerate(s.largest):
            iid = f"l{i}"
            where = os.path.dirname(f.path())
            if where.startswith(base):
                where = "." + where[len(base):]
            tree.insert('', 'end', iid=iid, text=f.name, tags=self._tag(f),
                        values=(human_size(f.size), t('kind.' + kind), where))
            rows[iid] = f
        if not s.largest:
            tree.insert('', 'end', iid='none', text=t('list.no_files'), tags=('muted',),
                        values=('', '', ''))
        if self.kind_filter:
            self.filter_label.config(text=t('largest.only', kind=t('kind.' + self.kind_filter)))
            self.filter_row.pack(fill="x", pady=(0, self.app.px(6)),
                                 before=tree.master)
        else:
            self.filter_row.pack_forget()
        # types
        tt = self.types_tree
        tt.delete(*tt.get_children())
        total = sum(v[0] for v in s.kinds.values()) or 1
        for kind in sorted(KINDS, key=lambda k: -s.kinds[k][0]):
            size, n = s.kinds[kind]
            if not n:
                continue
            tt.insert('', 'end', iid=kind, text="■ " + t('kind.' + kind),
                      tags=('k_' + kind,), values=(human_size(size), pct(size, total),
                                                  count(n)))
        self.schedule_map(0)

    def _type_selected(self):
        sel = self.types_tree.selection()
        if sel and sel[0] in KINDS:
            self.set_filter(sel[0])
            self.set_tab('largest')

    def set_filter(self, kind: Optional[str]):
        self.kind_filter = kind
        self.need_summary()
        self.schedule_map(0)

    # ── selection and actions ──

    def _row_selected(self, name: str):
        tree = {'folder': self.folder_tree, 'largest': self.largest_tree,
                'hints': self.hints_tree}[name]
        sel = tree.selection()
        node = self.rows[name].get(sel[0]) if sel else None
        if node is not None:
            self.selected = node
            self.update_actions()
            self._highlight(node)
        if name == 'hints' and node is not None:
            hint = self.hint_nodes.get(id(node))
            if hint:
                self.hint_text.config(text=t('hint.' + hint.key + '.body'))
                self.hint_command.config(state="normal")
                self.hint_command.delete(0, "end")
                self.hint_command.insert(0, hint.command)
                self.hint_command.config(state="readonly")
                if hint.command:
                    self.hint_command_row.pack(fill="x", padx=self.app.px(10),
                                               pady=(0, self.app.px(8)))
                else:
                    self.hint_command_row.pack_forget()

    def _row_double(self, name: str):
        node = self.selected
        if node is None:
            return
        if node.is_dir:
            self.drill(node)
            if name != 'folder':
                self.set_tab('folder')
        else:
            self.open_selected()

    def _row_menu(self, name: str, event):
        tree = {'folder': self.folder_tree, 'largest': self.largest_tree,
                'hints': self.hints_tree}[name]
        iid = tree.identify_row(event.y)
        if iid and iid in self.rows[name]:
            tree.selection_set(iid)
            self._row_selected(name)
            self._popup(event)

    def _popup(self, event):
        self.update_actions()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def select(self, node: Optional[scan.Node]):
        self.selected = node
        self.update_actions()
        if node is None:
            return
        for iid, n in self.rows['folder'].items():
            if n is node:
                self.folder_tree.selection_set(iid)
                self.folder_tree.see(iid)
                break
        self._highlight(node)

    def refusal(self, node: Optional[scan.Node]) -> Optional[str]:
        if node is None:
            return 'nothing'
        if node.flags & (scan.OTHER_FS | scan.SYSTEM):
            return 'protected'
        return safety.trash_refusal(node.path(), scan_root=self.scanner.root_path
                                    if self.scanner else None)

    def update_actions(self):
        node = self.selected
        if node is None:
            self.sel_name.config(text=t('results.nothing_selected'), fg=T["muted"])
            self.sel_detail.config(text=t('results.select_help'), fg=T["dim"])
            for b in (self.b_open, self.b_show, self.b_trash):
                b.set_enabled(False)
            self._menu_state(False, False)
            return
        path = node.path()
        bits = [human_size(node.size)]
        if node.is_dir:
            bits.append(t('results.files', n=count(node.count)))
        if self.current is not None and self.current.size:
            bits.append(t('results.of_folder', pct=pct(node.size, self.current.size)))
        self.sel_name.config(text=f"{node.name}{'/' if node.is_dir else ''}  ·  "
                             + "  ·  ".join(bits), fg=T["text"])
        reason = self.refusal(node)
        detail = home_short(path)
        if reason and reason != 'nothing':
            detail = t('refuse.' + reason) + "  ·  " + detail
        self.sel_detail.config(text=detail, fg=T["gold"] if reason else T["muted"])
        self.b_open.set_enabled(True)
        self.b_show.set_enabled(True)
        self.b_trash.set_enabled(reason is None)
        self._menu_state(True, reason is None)

    def _menu_state(self, any_on: bool, trash_on: bool):
        state = "normal" if any_on else "disabled"
        self.menu.entryconfig(0, state=state)
        self.menu.entryconfig(1, state=state)
        self.menu.entryconfig(3, state="normal" if trash_on else "disabled")

    def open_selected(self):
        if self.selected is not None:
            self.app.open_path(self.selected.path())

    def show_selected(self):
        if self.selected is not None:
            self.app.show_in_folder(self.selected.path())

    def trash_selected(self):
        node = self.selected
        if node is None:
            return
        reason = self.refusal(node)
        if reason is not None:
            self.app.event(self.map_panel, strong=True)
            if reason != 'nothing':
                self.app.warn(t('trash.refused_title'), t('refuse.' + reason),
                                    detail=node.path(), parent=self.app.root)
            return
        path = node.path()
        what = t('trash.what_folder', n=count(node.count)) if node.is_dir else t('trash.what_file')
        if not self.app.ask(t('trash.confirm_title', name=node.name),
                            t('trash.confirm', what=what, size=human_size(node.size)),
                            detail=path + "\n\n" + t('trash.confirm_detail'),
                            parent=self.app.root):
            return
        try:
            safety.move_to_trash(path, scan_root=self.scanner.root_path)
        except safety.Refused as exc:
            self.app.warn(t('trash.refused_title'), t('refuse.' + exc.reason),
                                detail=path, parent=self.app.root)
            return
        except trash.NoTrash:
            self.app.event(self.map_panel, strong=True)
            self.app.set_status('status.error', T["pink"])
            self.app.error(t('trash.failed_title'), t('trash.no_trash'), detail=path,
                              parent=self.app.root)
            return
        except OSError as exc:
            self.app.event(self.map_panel, strong=True)
            self.app.set_status('status.error', T["pink"])
            self.app.error(t('trash.failed_title'),
                              t('trash.failed', error=exc.strerror or str(exc)), detail=path,
                              parent=self.app.root)
            return
        log.info("moved to the trash: %s (%d bytes)", path, node.size)
        size = node.size
        parent = node.parent
        scan.remove(node)
        self.hints = [h for h in self.hints if self._still_in_tree(h.node)]
        self.hint_nodes = {id(h.node): h for h in self.hints}
        self.selected = None
        self.summary = None
        self.summary_for = None
        self._fill_hints()
        here = self.current if self._still_in_tree(self.current) else parent
        self.go(here if here is not None else self.root_node)
        self._show_summary()
        self.app.set_status('status.trashed', size=human_size(size))
        self.app.event(self.map_panel, strong=True)

    def _still_in_tree(self, node: scan.Node) -> bool:
        while node.parent is not None:
            node = node.parent
        return node is self.root_node

    def copy_command(self):
        text = self.hint_command.get()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.app.set_status('status.copied')
            self.app.event()

    # ── the treemap ──

    def schedule_map(self, delay: int = 80):
        if self.map_job is not None:
            self.after_cancel(self.map_job)
        self.map_job = self.after(delay, self.draw_map)

    def draw_map(self):
        self.map_job = None
        c = self.canvas
        c.delete("all")
        self.map_items = {}
        self.hover_tag = None
        if self.current is None:
            return
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20:
            return
        self._budget = MAP_BUDGET
        self._n = 0
        self._layout(self.current, 1, 1, w - 2, h - 2, 0, self._games_above(self.current))
        if not self.current.children:
            c.create_text(w / 2, h / 2, text=t('list.empty'), fill=T["muted"],
                          font=self.app.f_body)
        if self.selected is not None:
            self._highlight(self.selected)

    def _games_above(self, node: scan.Node) -> bool:
        from .kinds import is_game_dir
        return any(is_game_dir(a.name) for a in node.ancestors()[1:])

    def _layout(self, node, x, y, w, h, depth, games):
        from .kinds import is_game_dir, kind_of
        kids = [k for k in node.sorted_children() if k.size > 0]
        total = sum(k.size for k in kids)
        if not kids or total <= 0 or w < 4 or h < 4:
            return
        area = w * h
        keep, rest, rest_n = [], 0, 0
        for k in kids:
            if self._budget > 0 and k.size / total * area >= 40:
                keep.append(k)
                self._budget -= 1
            else:
                rest += k.size
                rest_n += 1
        sizes = [k.size for k in keep] + ([rest] if rest else [])
        rects = squarify(sizes, x, y, w, h)
        c = self.canvas
        dim = self.kind_filter is not None
        for k, (rx, ry, rw, rh) in zip(keep, rects):
            if rw < 2 or rh < 2:
                continue
            self._n += 1
            tag = f"n{self._n}"
            self.map_items[tag] = k
            hint = id(k) in self.hint_nodes
            if k.is_dir:
                fill = DIR_FILL[min(depth, len(DIR_FILL) - 1)]
                outline = T["gold"] if hint else T["line2"]
            else:
                kind = kind_of(k.name, games)
                fill = KIND_FILL[kind]
                if dim and kind != self.kind_filter:
                    fill = mix(fill, T["panel"], 0.75)
                elif dim:
                    fill = mix(fill, KIND_SWATCH[kind], 0.35)
                outline = T["gold"] if hint else T["panel"]
            c.create_rectangle(rx, ry, rx + rw - 1, ry + rh - 1, fill=fill, outline=outline,
                               tags=(tag, "cell"))
            header = self.app.px(15)
            if k.is_dir and depth < MAX_DEPTH and rw > 46 and rh > header + 24 and \
                    not k.flags & (scan.OTHER_FS | scan.SYSTEM):
                self._text(rx, ry, rw, header, k, tag, header_line=True)
                self._layout(k, rx + 2, ry + header, rw - 4, rh - header - 2, depth + 1,
                             games or is_game_dir(k.name))
            else:
                self._text(rx, ry, rw, rh, k, tag)
        if rest and len(rects) > len(keep):
            rx, ry, rw, rh = rects[-1]
            if rw >= 2 and rh >= 2:
                c.create_rectangle(rx, ry, rx + rw - 1, ry + rh - 1, fill=T["panel"],
                                   outline=T["line"], stipple="gray50")
                if rw > 70 and rh > 16:
                    c.create_text(rx + 4, ry + 3, anchor="nw", fill=T["dim"],
                                  font=self.app.f_map,
                                  text=t('map.small', n=count(rest_n)))

    def _text(self, x, y, w, h, node, tag, header_line: bool = False):
        if w < 40 or h < 14:
            return
        font = self.app.f_map
        name = node.name + ("/" if node.is_dir else "")
        size = human_size(node.size)
        room = w - 8
        label = name if header_line or h < 30 else name
        if font.measure(label) > room:
            # cut to fit, by characters (mono font: every character is the same width)
            per = max(1, font.measure("M"))
            keep = max(1, int(room / per) - 1)
            label = label[:keep] + "…"
        colour = T["text"] if not node.flags & scan.OTHER_FS else T["dim"]
        if header_line:
            line = label
            if font.measure(f"{label}  {size}") <= room:
                line = f"{label}  {size}"
            self.canvas.create_text(x + 4, y + 2, anchor="nw", text=line, fill=T["muted"],
                                    font=font, tags=(tag,))
            return
        self.canvas.create_text(x + 4, y + 3, anchor="nw", text=label, fill=colour,
                                font=font, tags=(tag,))
        if h >= 30 and font.measure(size) <= room:
            self.canvas.create_text(x + 4, y + 3 + font.metrics("linespace"), anchor="nw",
                                    text=size, fill=T["muted"], font=font, tags=(tag,))

    def _tag_at(self, event) -> Optional[str]:
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(items):
            for tag in self.canvas.gettags(item):
                if tag in self.map_items:
                    return tag
        return None

    def _map_motion(self, event):
        self._map_hover(self._tag_at(event))

    def _map_hover(self, tag: Optional[str]):
        if tag == self.hover_tag:
            return
        self.hover_tag = tag
        c = self.canvas
        c.delete("hover")
        if tag is None:
            self.canvas.config(cursor="")
            return
        node = self.map_items[tag]
        box = c.bbox(tag)
        if box:
            coords = c.coords(c.find_withtag(tag)[0])
            x0, y0, x1, y1 = coords if len(coords) == 4 else box
            # the house fault on hover: the cell's edge slips into the two channels
            c.create_rectangle(x0 - 2, y0, x1 - 2, y1, outline=T["ch_a"], tags=("hover",))
            c.create_rectangle(x0 + 2, y0, x1 + 2, y1, outline=T["ch_b"], tags=("hover",))
            c.create_rectangle(x0, y0, x1, y1, outline=T["accent"], tags=("hover",))
        c.config(cursor="hand2")
        self.app.status.config(text="● " + home_short(node.path())[-70:] + "  ·  "
                               + human_size(node.size), fg=T["muted"])

    def _highlight(self, node: scan.Node):
        c = self.canvas
        c.delete("selected")
        for tag, n in self.map_items.items():
            if n is node:
                items = c.find_withtag(tag)
                if items:
                    coords = c.coords(items[0])
                    if len(coords) == 4:
                        c.create_rectangle(*coords, outline=T["text"], width=2,
                                           tags=("selected",))
                break

    def _map_click(self, event):
        self.canvas.focus_set()
        tag = self._tag_at(event)
        if tag is not None:
            self.select(self.map_items[tag])

    def _map_double(self, event):
        tag = self._tag_at(event)
        if tag is None:
            return
        node = self.map_items[tag]
        if node.is_dir:
            self.drill(node)
        else:
            self.select(node)
            self.open_selected()

    def _map_menu(self, event):
        tag = self._tag_at(event)
        if tag is not None:
            self.select(self.map_items[tag])
            self._popup(event)


def bench(path: str, threads: int = 4, started: float = 0.0) -> int:
    """--bench: open the window, scan path, draw the results, report the times, quit."""
    t0 = time.monotonic()
    app = App(threads=threads)
    app.root.update()
    shown = time.monotonic() - t0
    app.scan(path)
    s = app.scanner
    while app.screen is not app.results:
        app.root.update()
        time.sleep(0.01)
    app.root.update()
    drawn = time.monotonic() - t0
    files, dirs, _ = s.progress()
    print(f"window shown in {shown:.3f} s (process start to window: {started + shown:.3f} s)")
    print(f"scanned {files:,} files and {dirs:,} folders ({human_size(s.root.size)}) in "
          f"{s.elapsed:.2f} s with {threads} threads; results drawn at {drawn:.2f} s")
    app.close()
    return 0
