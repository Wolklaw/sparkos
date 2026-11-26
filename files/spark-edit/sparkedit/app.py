"""The window: header with file tabs, the editors, the find bar, the status bar, and what
happens on open, save, close and quit."""

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import (APP_CLASS, APP_NAME, APP_SLUG, AUTOSAVE_BIG_MS, AUTOSAVE_MS, BIG_BUFFER,
               BIG_FILE, VERSION, core, fileio, session, syntax)
from .core import log
from .editor import Buffer
from .fileio import ENCODINGS, NEWLINES, Format
from .findbar import FindBar
from .instance import Listener
from .text import t
from .ui import StatusItem, TabStrip, ask, menu, style_scrollbars
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, IconButton, Mark, Strip, WolkButton

SYNC_OPEN = 1024 * 1024          # files up to this size are read before the tab shows


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but the desktop publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_EDIT_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if os.name != 'nt' and shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            match = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if match:
                return max(1.0, min(4.0, float(match.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def pick_mono_cached(root: tk.Tk) -> str:
    """The mono font, remembered between runs: listing every font family takes a moment on
    a PC with many fonts, and the window should open at once."""
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                "TkFixedFont")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in (f'{APP_SLUG}-64.png', f'{APP_SLUG}-256.png'):
        path = os.path.join(here, 'icons', name)
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


def same_file(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a) == os.path.realpath(b)


class App:
    def __init__(self, files: List[Tuple[str, int, int]] = (), restore: bool = True,
                 bench: bool = False):
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.bench = bench
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.settings = core.load_settings()
        size = self.settings['font_size']
        self.editor_font = tkfont.Font(self.root, family=self.mono, size=size)
        self.editor_bold = tkfont.Font(self.root, family=self.mono, size=size, weight='bold')
        self.gutter_font = tkfont.Font(self.root, family=self.mono, size=max(6, size - 1))
        self.glitch = Glitch(self.root, enabled=not reduced_motion_or_bench(bench)
                             and self.settings['glitch'])
        style_scrollbars(self.root)

        self.buffers: List[Buffer] = []
        self.current: Optional[Buffer] = None
        self.closed: List[Tuple[str, str]] = []          # (path, cursor) for Ctrl+Shift+T
        self.untitled_n = 0
        self._autosave_ids: Dict[int, str] = {}
        self._session_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self._jobs: 'queue.Queue[Callable[[], None]]' = queue.Queue()
        self._poll_id: Optional[str] = None
        self.message = ''
        self.listener = None

        self._build()
        self.root.protocol('WM_DELETE_WINDOW', self.quit)
        icon = load_icon(self.root)
        if icon is not None:
            self.root.iconphoto(True, icon)
            self._icon = icon
        geometry = self.settings.get('geometry') if isinstance(self.settings.get('geometry'),
                                                               str) else None
        self.root.geometry(geometry or f'{self.px(980)}x{self.px(680)}')
        self.root.minsize(self.px(480), self.px(300))

        restored = 0
        if restore and not bench:
            restored = self._restore()
        for path, line, col in files:
            self.open_path(path, line, col)
        if not self.buffers:
            self.new_buffer()
        elif self.current is None:
            self.select(self.buffers[-1])
        if restored:
            self.status(t('status.restored', n=restored), T["gold"])
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        if not bench:
            self.listener = Listener(self.root, self.bring_to_front, self.open_from_socket)

    # ─── Look helpers ──────────────────────────────────────────

    def px(self, n: float) -> int:
        return max(1, round(n * self.scale))

    def font(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight='bold' if bold else 'normal')
        return self._fonts[key]

    # ─── Building the window ───────────────────────────────────

    def _build(self) -> None:
        root, px = self.root, self.px
        root.configure(bg=T["bg"])
        self.main = tk.Frame(root, bg=T["bg"])
        self.main.pack(fill='both', expand=True)

        header = tk.Frame(self.main, bg=T["bg"], padx=px(10))
        header.pack(fill='x', side='top')
        self.mark = Mark(header, px(26), T["bg"])
        self.mark.pack(side='left', pady=px(6))
        self.title = GlitchText(header, APP_NAME.upper(), self.font(10, True), bg=T["bg"])
        self.title.pack(side='left', padx=(px(6), px(12)))
        buttons = tk.Frame(header, bg=T["bg"])
        buttons.pack(side='right')
        size = px(28)
        self.menu_button = IconButton(buttons, 'menu', self.show_menu, size, tip=t('tip.menu'))
        for icon, command, tip in (('new', self.new_buffer, 'tip.new'),
                                   ('folder', self.open_dialog, 'tip.open'),
                                   ('save', lambda: self.save(self.current), 'tip.save'),
                                   ('find', lambda: self.find('find'), 'tip.find')):
            b = IconButton(buttons, icon, command, size, tip=t(tip))
            b.pack(side='left', padx=(px(2), 0))
            b.bind('<Enter>', lambda _e, tip=t(tip): self.hint(tip), add='+')
            b.bind('<Leave>', lambda _e: self.hint(None), add='+')
        self.menu_button.pack(side='left', padx=(px(6), 0))
        self.tabs = TabStrip(header, self.font(9, False), px, on_select=self._tab_clicked,
                             on_close=self._tab_close, on_menu=self._tab_menu,
                             on_hover=self.hint)
        self.tabs.pack(side='left', fill='x', expand=True, padx=(0, px(8)))
        self.strip = Strip(self.main, height=max(2, px(2)))
        self.strip.pack(fill='x', side='top')

        # status bar (packed before the body so it keeps its place at the bottom)
        bar = tk.Frame(self.main, bg=T["panel"])
        bar.pack(fill='x', side='bottom')
        tk.Frame(bar, bg=T["line"], height=1).pack(fill='x', side='top')
        label = self.font(8, True)
        self.st_message = tk.Label(bar, text='', font=label, bg=T["panel"], fg=T["muted"],
                                   anchor='w', padx=px(10), pady=px(3))
        self.st_zoom = StatusItem(bar, label, px, lambda _e: self.zoom(0))
        self.st_wrap = StatusItem(bar, label, px, lambda _e: self.toggle_wrap())
        self.st_newline = StatusItem(bar, label, px, self._newline_menu)
        self.st_encoding = StatusItem(bar, label, px, self._encoding_menu)
        self.st_lang = StatusItem(bar, label, px, self._language_menu)
        self.st_access = StatusItem(bar, label, px, None)
        self.st_pos = StatusItem(bar, label, px, lambda _e: self.find('goto'))
        for item in (self.st_zoom, self.st_wrap, self.st_newline, self.st_encoding,
                     self.st_lang, self.st_pos, self.st_access):
            item.pack(side='right')
        # packed last, so a long message is the one cut short, not the items on the right
        self.st_message.pack(side='left', fill='x', expand=True)

        self.body = tk.Frame(self.main, bg=T["bg"])
        self.body.pack(fill='both', expand=True)
        self.findbar = FindBar(self)
        self.start = self._build_start()

        self.bind_shortcuts(self.root)
        self.root.bind('<FocusIn>', self._focus_in, add='+')
        self.root.bind('<Configure>', self._configured, add='+')

    def _build_start(self) -> tk.Frame:
        px = self.px
        frame = tk.Frame(self.body, bg=T["bg"])
        inner = tk.Frame(frame, bg=T["bg"])
        inner.place(relx=0.5, rely=0.42, anchor='center')
        self.start_title = GlitchText(inner, t('start.title').upper(), self.font(14, True),
                                      bg=T["bg"])
        self.start_title.pack(anchor='w')
        row = tk.Frame(inner, bg=T["bg"])
        row.pack(anchor='w', pady=(px(10), px(18)))
        WolkButton(row, t('start.new') + '  Ctrl+N', self.new_buffer, self.font(9, True),
                   variant='primary').pack(side='left', padx=(0, px(8)))
        WolkButton(row, t('start.open') + '  Ctrl+O', self.open_dialog,
                   self.font(9, True)).pack(side='left')
        tk.Label(inner, text=t('start.recent').upper(), font=self.font(8, True), bg=T["bg"],
                 fg=T["muted"]).pack(anchor='w')
        self.recent_box = tk.Frame(inner, bg=T["bg"])
        self.recent_box.pack(anchor='w', fill='x', pady=(px(4), 0))
        return frame

    def _fill_recent(self) -> None:
        for w in self.recent_box.winfo_children():
            w.destroy()
        recent = [p for p in core.load_recent() if os.path.exists(p)][:10]
        if not recent:
            tk.Label(self.recent_box, text=t('start.no_recent'), font=self.font(9, False),
                     bg=T["bg"], fg=T["dim"]).pack(anchor='w')
        for path in recent:
            row = tk.Frame(self.recent_box, bg=T["bg"], cursor='hand2')
            row.pack(anchor='w', fill='x')
            name = tk.Label(row, text=os.path.basename(path), font=self.font(10, False),
                            bg=T["bg"], fg=T["text"], anchor='w', padx=self.px(4),
                            pady=self.px(2))
            folder = tk.Label(row, text=core.home_short(os.path.dirname(path)),
                              font=self.font(9, False), bg=T["bg"], fg=T["dim"], anchor='w')
            name.pack(side='left')
            folder.pack(side='left', padx=(self.px(6), 0))
            parts = (row, name, folder)

            def hover(on, parts=parts):
                for w in parts:
                    w.configure(bg=T["panel"] if on else T["bg"])
                parts[1].configure(fg=T["accent"] if on else T["text"])
            for w in parts:
                w.bind('<Enter>', lambda _e, h=hover: h(True))
                w.bind('<Leave>', lambda _e, h=hover: h(False))
                w.bind('<ButtonRelease-1>', lambda _e, p=path: self.open_path(p))

    # ─── Keyboard ──────────────────────────────────────────────

    def bind_shortcuts(self, widget: tk.Misc) -> None:
        """App shortcuts, bound on each Text and Entry so they win over Tk's own class
        bindings (on X11, Ctrl+O, Ctrl+H, Ctrl+K... are Emacs-style editing keys there)."""
        def run(fn):
            def handler(_e=None):
                fn()
                return 'break'
            return handler

        keys = {
            '<Control-n>': self.new_buffer, '<Control-o>': self.open_dialog,
            '<Control-s>': lambda: self.save(self.current),
            '<Control-S>': lambda: self.save(self.current, as_new=True),
            '<Control-w>': lambda: self.close_buffer(self.current),
            '<Control-T>': self.reopen_closed, '<Control-q>': self.quit,
            '<Control-Tab>': lambda: self.cycle(+1), '<Control-Next>': lambda: self.cycle(+1),
            '<Control-Prior>': lambda: self.cycle(-1),
            '<Control-f>': lambda: self.find('find'), '<Control-h>': lambda: self.find('replace'),
            '<Control-g>': lambda: self.find('goto'), '<Control-l>': lambda: self.find('goto'),
            '<F3>': lambda: self.findbar.step(+1), '<Shift-F3>': lambda: self.findbar.step(-1),
            '<Alt-z>': self.toggle_wrap, '<Control-equal>': lambda: self.zoom(+1),
            '<Control-plus>': lambda: self.zoom(+1), '<Control-minus>': lambda: self.zoom(-1),
            '<Control-0>': lambda: self.zoom(0), '<Control-slash>': self.toggle_comment,
        }
        for seq in ('<Control-Shift-Tab>', '<Control-ISO_Left_Tab>'):
            keys[seq] = lambda: self.cycle(-1)
        for seq in ('<Control-KP_Add>',):
            keys[seq] = lambda: self.zoom(+1)
        for seq in ('<Control-KP_Subtract>',):
            keys[seq] = lambda: self.zoom(-1)
        for n in range(1, 10):
            keys[f'<Alt-Key-{n}>'] = lambda n=n: self.select_nth(n)
        for seq, fn in keys.items():
            try:
                widget.bind(seq, run(fn))
            except tk.TclError:
                pass                                # a keysym this platform doesn't have
        if isinstance(widget, tk.Text):
            widget.bind('<Control-a>', lambda _e: self._select_all(widget))
            widget.bind('<Control-z>', lambda _e: self.undo(widget, 'undo'))
            widget.bind('<Control-Z>', lambda _e: self.undo(widget, 'redo'))
            widget.bind('<Control-y>', lambda _e: self.undo(widget, 'redo'))
            widget.bind('<Escape>', lambda _e: (self.findbar.close(), 'break')[1])
            # Tk's X11 Emacs keys that would surprise people: do nothing instead
            for letter in 'bdekipt':
                widget.bind(f'<Control-{letter}>', lambda _e: 'break')
            widget.bind('<Control-backslash>', lambda _e: 'break')
            for seq in ('<Control-MouseWheel>', '<Control-Button-4>', '<Control-Button-5>'):
                widget.bind(seq, self._wheel_zoom)
        elif isinstance(widget, tk.Entry):
            widget.bind('<Control-a>', lambda _e: (widget.select_range(0, 'end'),
                                                   widget.icursor('end'), 'break')[2])

    def _select_all(self, text: tk.Text) -> str:
        text.tag_add('sel', '1.0', 'end-1c')
        text.mark_set('insert', 'end-1c')
        return 'break'

    def undo(self, text: tk.Text, which: str) -> str:
        try:
            text.edit_undo() if which == 'undo' else text.edit_redo()
        except tk.TclError:
            pass
        text.see('insert')
        return 'break'

    def _wheel_zoom(self, event) -> str:
        up = getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0
        self.zoom(+1 if up else -1)
        return 'break'

    # ─── Tabs ──────────────────────────────────────────────────

    def _next_untitled(self) -> str:
        self.untitled_n += 1
        return t('untitled') if self.untitled_n == 1 else t('untitled_n', n=self.untitled_n)

    def _add_buffer(self, buf: Buffer) -> None:
        self.buffers.append(buf)
        self.bind_shortcuts(buf.text)
        self.tabs.add(buf, buf.title)
        self.update_tab(buf)

    def new_buffer(self, select: bool = True) -> Buffer:
        buf = Buffer(self, None, self._next_untitled())
        self._add_buffer(buf)
        buf.load('', Format())
        if select:
            self.select(buf)
        return buf

    def select(self, buf: Optional[Buffer]) -> None:
        if buf is self.current and buf is not None and buf.frame.winfo_ismapped():
            buf.text.focus_set()
            return
        if self.current is not None and self.current in self.buffers:
            self.current.frame.pack_forget()
        self.current = buf
        if buf is None:
            self._fill_recent()
            self.start.pack(fill='both', expand=True)
            self.tabs.select(None)
            self.findbar.close()
            self.root.title(APP_NAME)
            self.update_status()
            self.glitch.now(self.start_title)
            return
        self.start.pack_forget()
        buf.frame.pack(fill='both', expand=True)
        self.tabs.select(buf)
        buf.text.focus_set()
        self.findbar.forget()
        if self.findbar.shown and self.findbar.mode != 'goto':
            self.findbar._changed()
        self.update_title()
        self.update_status()
        buf.schedule_refresh()
        self._save_session_soon()

    def _tab_clicked(self, buf) -> None:
        self.select(buf)

    def _tab_close(self, buf) -> None:
        self.close_buffer(buf)

    def _tab_menu(self, buf, event) -> None:
        m = menu(self.root, self.font(9, False))
        m.add_command(label=t('menu.close'), command=lambda: self.close_buffer(buf))
        m.add_command(label=t('menu.close_others'), command=lambda: self.close_others(buf))
        m.add_separator()
        m.add_command(label=t('menu.copy_path'), command=lambda: self.copy_path(buf),
                      state='normal' if buf.path else 'disabled')
        m.tk_popup(event.x_root, event.y_root)

    def cycle(self, step: int) -> None:
        if not self.buffers:
            return
        if self.current not in self.buffers:
            self.select(self.buffers[0])
            return
        i = self.buffers.index(self.current)
        self.select(self.buffers[(i + step) % len(self.buffers)])

    def select_nth(self, n: int) -> None:
        if self.buffers:
            self.select(self.buffers[min(n, len(self.buffers)) - 1])

    def tab_name(self, buf: Buffer) -> str:
        name = buf.title
        if buf.path:
            twins = [b for b in self.buffers if b is not buf and b.title == buf.title and b.path]
            if twins:
                name = f"{buf.title} · {os.path.basename(os.path.dirname(buf.path))}"
        return name

    def update_tab(self, buf: Buffer) -> None:
        tip = core.home_short(buf.path) if buf.path else buf.title
        self.tabs.update_tab(buf, self.tab_name(buf), buf.dirty, tip)

    def update_title(self) -> None:
        buf = self.current
        if buf is None:
            self.root.title(APP_NAME)
            return
        where = f" — {core.home_short(os.path.dirname(buf.path))}" if buf.path else ''
        self.root.title(f"{'● ' if buf.dirty else ''}{buf.title}{where} — {APP_NAME}")

    def copy_path(self, buf: Buffer) -> None:
        if buf.path:
            self.root.clipboard_clear()
            self.root.clipboard_append(buf.path)
            self.status(t('status.copied'))

    # ─── Opening ───────────────────────────────────────────────

    def open_dialog(self) -> None:
        start = os.path.dirname(self.current.path) if self.current and self.current.path \
            else os.path.expanduser('~')

        def done(paths: List[str]) -> None:
            for path in paths:
                self.open_path(path)

        self._pick_files(start, done)

    def _pick_files(self, start: str, done: Callable[[List[str]], None]) -> None:
        """The desktop's own file dialog (spark-pick: Spark Files through the desktop portal) in a worker thread, so this
        window keeps drawing; Tk's own dialog where spark-pick isn't there."""
        if picker() and os.name != 'nt':
            def work():
                try:
                    out = subprocess.run([picker(), '--getopenfilename', start + os.sep,
                                          '--multiple', '--separate-output',
                                          '--title', APP_NAME],
                                         capture_output=True, text=True).stdout
                    paths = [line for line in out.splitlines() if line.strip()]
                except OSError:
                    paths = []
                self.later(lambda: done(paths))
            threading.Thread(target=work, daemon=True).start()
            return
        from tkinter import filedialog
        done(list(filedialog.askopenfilenames(parent=self.root, title=APP_NAME,
                                              initialdir=start)))

    def _pick_save(self, buf: Buffer, done: Callable[[Optional[str]], None]) -> None:
        folder = os.path.dirname(buf.path) if buf.path else os.path.expanduser('~')
        name = buf.title if buf.path else f"{buf.title}.txt"
        if picker() and os.name != 'nt':
            def work():
                try:
                    out = subprocess.run([picker(), '--getsavefilename',
                                          os.path.join(folder, name), '--title', APP_NAME],
                                         capture_output=True, text=True).stdout.strip()
                except OSError:
                    out = ''
                self.later(lambda: done(out or None))
            threading.Thread(target=work, daemon=True).start()
            return
        from tkinter import filedialog
        done(filedialog.asksaveasfilename(parent=self.root, title=APP_NAME, initialdir=folder,
                                          initialfile=name) or None)

    def open_path(self, path: str, line: int = 0, col: int = 0, select: bool = True,
                  cursor: Optional[str] = None) -> Optional[Buffer]:
        path = os.path.abspath(os.path.expanduser(path))
        for buf in self.buffers:
            if buf.path and (buf.path == path or same_file(buf.path, path)):
                if select:
                    self.select(buf)
                if line:
                    buf.goto_line(line, max(0, col - 1))
                return buf
        if os.path.isdir(path):
            self.status(f"{core.home_short(path)}: {t('error.is_folder')}", T["pink"])
            return None
        # an untouched, empty Untitled tab makes way for the file
        spare = self.current if (self.current and not self.current.path
                                 and not self.current.dirty and not self.current.loading
                                 and self.current.line_count() == 1
                                 and not self.current.get_all()) else None
        buf = Buffer(self, path, os.path.basename(path))
        self._add_buffer(buf)
        if spare is not None:
            self._remove(spare)
        if select:
            self.select(buf)
        cursor = f'{line}.{max(0, col - 1)}' if line else cursor
        if not os.path.exists(path):
            buf.set_language(syntax.detect(path))
            buf.load('', Format())
            if cursor:
                buf.goto_index(cursor)
            self.status(t('status.new_file', path=core.home_short(path)), T["gold"])
            self.update_status()
            return buf
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size <= SYNC_OPEN:
            self._read_done(buf, path, cursor, self._read(path))
        else:
            self.status(t('status.opening', name=buf.title))
            self.update_status()

            def work():
                result = self._read(path)
                self.later(lambda: self._read_done(buf, path, cursor, result))
            threading.Thread(target=work, daemon=True).start()
        return buf

    @staticmethod
    def _read(path: str, encoding: Optional[str] = None, force: bool = False):
        try:
            return fileio.read_file(path, encoding, force)
        except (OSError, fileio.BinaryFile, LookupError) as exc:
            return exc

    def _read_done(self, buf: Buffer, path: str, cursor: Optional[str], result) -> None:
        if buf not in self.buffers:
            return
        if isinstance(result, fileio.BinaryFile):
            choice = ask(self, t('ask.binary_title'), t('ask.binary', name=buf.title),
                         [('open', t('button.open_anyway'), 'ghost'),
                          ('cancel', t('button.cancel'), 'primary')], default='cancel')
            if choice != 'open':
                self._remove(buf)
                return
            result = self._read(path, force=True)
        if isinstance(result, BaseException):
            log.warning("open %s: %s", path, result)
            why = result.strerror if isinstance(result, OSError) and result.strerror \
                else str(result)
            self._remove(buf)
            self.glitch.now(self.strip, self.title, strong=True)
            ask(self, t('ask.open_error_title'), t('ask.open_error', path=path, why=why),
                [('ok', t('button.ok'), 'primary')], cancel='ok')
            return
        text, fmt, st = result
        buf.disk_mtime, buf.disk_size = st.st_mtime, st.st_size
        if not buf.lang_forced:
            buf.set_language(syntax.detect(path, text[:200].split('\n', 1)[0]))
        buf.load(text, fmt, cursor)
        core.add_recent(path)
        if buf.huge_lines:
            self.on_huge(buf)
        elif len(text) > BIG_FILE:
            self.status(t('status.big', name=buf.title, size=core.size_text(st.st_size)))
        elif fmt.mixed:
            self.status(t('status.mixed', name=buf.title, nl=fmt.newline_label()), T["gold"])
        self.update_status()
        self._save_session_soon()

    def open_from_socket(self, items: List[Tuple[str, int, int]]) -> None:
        for path, line, col in items:
            self.open_path(path, line, col)
        self.bring_to_front()

    def bring_to_front(self) -> None:
        root = self.root
        if root.state() in ('iconic', 'withdrawn'):
            root.deiconify()
        root.lift()
        try:
            root.attributes('-topmost', True)
            root.after(200, lambda: root.attributes('-topmost', False))
        except tk.TclError:
            pass
        root.focus_force()
        if self.current:
            self.current.text.focus_set()

    def reload(self, buf: Optional[Buffer], encoding: Optional[str] = None) -> None:
        if buf is None or not buf.path or buf.loading or not os.path.exists(buf.path):
            return
        if buf.dirty:
            title = t('ask.reopen_dirty_title') if encoding else t('ask.changed_title')
            message = t('ask.reopen_dirty', name=buf.title, enc=dict(ENCODINGS).get(
                encoding, '')) if encoding else t('ask.changed_reload', name=buf.title)
            if ask(self, title, message, [('reload', t('button.reload'), 'danger'),
                                          ('cancel', t('button.cancel'), 'primary')],
                   default='cancel') != 'reload':
                return
        result = self._read(buf.path, encoding, force=True)
        if isinstance(result, BaseException):
            self.status(str(result), T["pink"])
            return
        text, fmt, st = result
        cursor = buf.text.index('insert')
        top = buf.text.yview()[0]
        session.drop_autosave(buf.autosave_id)
        buf.autosave_id = None
        buf.disk_mtime, buf.disk_size = st.st_mtime, st.st_size
        buf.load(text, fmt, cursor)
        if not buf.loading:
            buf.text.yview_moveto(top)
        self.update_tab(buf)
        self.update_status()

    # ─── Saving ────────────────────────────────────────────────

    def save(self, buf: Optional[Buffer], as_new: bool = False,
             then: Optional[Callable[[], None]] = None) -> bool:
        """Save buf. Returns True when it is saved now; False if it wasn't, or if it will
        be later (a file dialog or the password prompt is open), in which case `then` runs
        once it is."""
        if buf is None or buf.loading:
            return False
        if as_new or not buf.path:
            def chosen(path: Optional[str]) -> None:
                if path and self._save_to(buf, path, check_disk=False) and then:
                    then()
            self._pick_save(buf, chosen)
            return False
        return self._save_to(buf, buf.path, check_disk=True, then=then)

    def _save_to(self, buf: Buffer, path: str, check_disk: bool,
                 then: Optional[Callable[[], None]] = None) -> bool:
        if buf not in self.buffers:
            return False
        path = os.path.abspath(path)
        text = buf.get_all()
        try:
            data = fileio.encode(text, buf.fmt)
        except fileio.EncodeError as exc:
            buf.goto_line(exc.line, exc.col)
            if ask(self, t('ask.encode_title', enc=exc.encoding),
                   t('ask.encode', line=exc.line, col=exc.col + 1, char=exc.char,
                     enc=exc.encoding),
                   [('utf8', t('button.utf8'), 'primary'), ('cancel', t('button.cancel'),
                                                            'ghost')]) != 'utf8':
                return False
            buf.fmt = Format('utf-8', False, buf.fmt.newline)
            data = fileio.encode(text, buf.fmt)
            self.update_status()
        if check_disk and buf.disk_mtime is not None:
            try:
                changed = os.stat(path).st_mtime != buf.disk_mtime
            except OSError:
                changed = False
            if changed and ask(self, t('ask.changed_title'),
                               t('ask.changed', name=buf.title),
                               [('overwrite', t('button.overwrite'), 'danger'),
                                ('cancel', t('button.cancel'), 'primary')],
                               default='cancel') != 'overwrite':
                return False
        version = buf.version
        try:
            st = fileio.write_file(path, data)
        except OSError as exc:
            log.warning("save %s: %s", path, exc)
            self.glitch.now(self.strip, self.title, strong=True)
            if fileio.is_read_only_fs(exc):
                if ask(self, t('ask.rofs_title'), t('ask.rofs', path=path),
                       [('saveas', t('button.save_as'), 'primary'),
                        ('cancel', t('button.cancel'), 'ghost')]) == 'saveas':
                    self.save(buf, as_new=True, then=then)
                return False
            if fileio.is_permission_error(exc):
                if not fileio.pkexec_path():
                    choice = ask(self, t('ask.denied_title'),
                                 t('ask.denied_no_pkexec', path=path),
                                 [('saveas', t('button.save_as'), 'primary'),
                                  ('cancel', t('button.cancel'), 'ghost')])
                else:
                    choice = ask(self, t('ask.denied_title'), t('ask.denied', path=path),
                                 [('admin', t('button.admin'), 'primary'),
                                  ('saveas', t('button.save_as'), 'ghost'),
                                  ('cancel', t('button.cancel'), 'ghost')])
                if choice == 'admin':
                    self.save_admin(buf, path, data, version, then)
                elif choice == 'saveas':
                    self.save(buf, as_new=True, then=then)
                return False
            ask(self, t('ask.error_title'), t('ask.error', path=path,
                                              why=exc.strerror or str(exc)),
                [('ok', t('button.ok'), 'primary')], cancel='ok')
            return False
        self._saved(buf, path, st.st_mtime, version)
        self.status(t('status.saved', path=core.home_short(path)), T["accent"])
        if then:
            then()
        return True

    def save_admin(self, buf: Buffer, path: Optional[str] = None, data: Optional[bytes] = None,
                   version: Optional[int] = None,
                   then: Optional[Callable[[], None]] = None) -> None:
        """Save through pkexec, in a worker thread: the password prompt is Spark Polkit's."""
        if buf is None or buf.loading:
            return
        path = path or buf.path
        if not path:
            self.save(buf, as_new=True)
            return
        if data is None:
            try:
                data = fileio.encode(buf.get_all(), buf.fmt)
            except fileio.EncodeError:
                self._save_to(buf, path, check_disk=False)
                return
        version = buf.version if version is None else version
        self.status(t('status.admin_wait'), T["gold"])

        def work():
            error = fileio.admin_write(path, data, core.cache_dir())
            self.later(lambda: finished(error))

        def finished(error: Optional[str]) -> None:
            if error is None:
                try:
                    mtime = os.stat(path).st_mtime
                except OSError:
                    mtime = None
                self._saved(buf, path, mtime, version)
                self.status(t('status.saved_admin', path=core.home_short(path)), T["accent"])
                if then:
                    then()
            elif error == 'cancelled':
                self.status(t('error.cancelled'))
            else:
                self.glitch.now(self.strip, self.title, strong=True)
                ask(self, t('ask.error_title'), t('ask.admin_failed', why=error),
                    [('ok', t('button.ok'), 'primary')], cancel='ok')
        threading.Thread(target=work, daemon=True).start()

    def _saved(self, buf: Buffer, path: str, mtime: Optional[float], version: int) -> None:
        if buf not in self.buffers:
            return
        renamed = path != buf.path
        buf.path = path
        buf.title = os.path.basename(path)
        buf.disk_mtime = mtime
        if buf.version == version:
            buf.text.edit_modified(False)
            session.drop_autosave(buf.autosave_id)
            buf.autosave_id = None
        if renamed and not buf.lang_forced:
            buf.set_language(syntax.detect(path, buf.get_lines(1, 1)[0]))
        if not self.bench:
            core.add_recent(path)
        for b in self.buffers:
            self.update_tab(b)
        self.update_title()
        self.update_status()
        self.glitch.now(self.strip, self.title)
        self._save_session_soon()

    # ─── Closing ───────────────────────────────────────────────

    def close_buffer(self, buf: Optional[Buffer]) -> None:
        if buf is None or buf not in self.buffers:
            return
        if buf.dirty:
            self.select(buf)
            choice = ask(self, t('ask.unsaved_title'), t('ask.unsaved', name=buf.title),
                         [('save', t('button.save'), 'primary'),
                          ('discard', t('button.dont_save'), 'danger'),
                          ('cancel', t('button.cancel'), 'ghost')], default='save')
            if choice == 'cancel':
                return
            if choice == 'save':
                if not self.save(buf, then=lambda: self.close_buffer(buf)):
                    return
        if buf.path:
            self.closed.append((buf.path, buf.text.index('insert')))
        session.drop_autosave(buf.autosave_id)
        self._remove(buf)

    def close_others(self, keep: Buffer) -> None:
        for buf in list(self.buffers):
            if buf is not keep:
                self.close_buffer(buf)

    def _remove(self, buf: Buffer) -> None:
        if buf not in self.buffers:
            return
        i = self.buffers.index(buf)
        self.buffers.remove(buf)
        self.tabs.remove(buf)
        was_current = buf is self.current
        if was_current:
            self.current = None
        buf.destroy()
        if was_current:
            self.select(self.buffers[min(i, len(self.buffers) - 1)] if self.buffers else None)
        for b in self.buffers:
            self.update_tab(b)
        self._save_session_soon()

    def reopen_closed(self) -> None:
        while self.closed:
            path, cursor = self.closed.pop()
            if os.path.exists(path):
                self.open_path(path, cursor=cursor)
                return

    def quit(self) -> None:
        """Unsaved buffers are kept (autosaved now) and come back at the next start, unless
        "Reopen last session" is off: then each one asks to be saved."""
        if not self.settings['reopen_session'] or self.bench:
            for buf in list(self.buffers):
                if buf.dirty:
                    self.close_buffer(buf)
                    if buf in self.buffers:
                        return                     # cancelled, or saving later
        else:
            for buf in self.buffers:
                if buf.dirty and not buf.loading:
                    self.autosave(buf, sync=True)
        if self._session_id:
            self.root.after_cancel(self._session_id)
        self.save_session()
        try:
            if self.root.state() == 'normal':
                self.settings['geometry'] = self.root.geometry()
        except tk.TclError:
            pass
        if not self.bench:
            core.save_settings(self.settings)
        if self.listener:
            self.listener.close()
        for buf in self.buffers:
            buf.cancel_load()
        try:
            for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.tk.call('after', 'cancel', job)   # Tcl only: widgets free their own
        except tk.TclError:
            pass
        self.root.destroy()

    # ─── Autosave and session ──────────────────────────────────

    def on_change(self, buf: Buffer) -> None:
        self.findbar.forget()
        if buf.loading or self.bench:
            return
        old = self._autosave_ids.pop(id(buf), None)
        if old:
            self.root.after_cancel(old)
        delay = AUTOSAVE_BIG_MS if buf.load_total > BIG_BUFFER else AUTOSAVE_MS
        self._autosave_ids[id(buf)] = self.root.after(delay, lambda: self.autosave(buf))
        if buf is self.current:
            self._update_position()

    def autosave(self, buf: Buffer, sync: bool = False) -> None:
        self._autosave_ids.pop(id(buf), None)
        if buf not in self.buffers or buf.loading or self.bench:
            return
        if not buf.dirty:
            if buf.autosave_id:
                session.drop_autosave(buf.autosave_id)
                buf.autosave_id = None
            return
        if buf.autosaved_version == buf.version and buf.autosave_id:
            return
        if not buf.autosave_id:
            buf.autosave_id = session.new_id()
            self._save_session_soon()
        record = session.Autosave(id=buf.autosave_id, path=buf.path, title=buf.title,
                                  fmt=buf.fmt.as_dict(), language=buf.lang if buf.lang_forced
                                  else None, cursor=buf.text.index('insert'),
                                  disk_mtime=buf.disk_mtime)
        text = buf.get_all()
        buf.autosaved_version = buf.version
        if sync or len(text) < 1024 * 1024:
            session.write_autosave(record, text)
        else:
            threading.Thread(target=session.write_autosave, args=(record, text),
                             daemon=True).start()

    def _save_session_soon(self) -> None:
        if self.bench:
            return
        if self._session_id:
            self.root.after_cancel(self._session_id)
        self._session_id = self.root.after(500, self.save_session)

    def save_session(self) -> None:
        self._session_id = None
        if self.bench:
            return
        tabs = []
        for buf in self.buffers:
            if not buf.path and not buf.autosave_id:
                continue
            tabs.append({'path': buf.path, 'cursor': buf.text.index('insert'),
                         'autosave': buf.autosave_id if buf.dirty else None,
                         'language': buf.lang if buf.lang_forced else None,
                         'title': buf.title})
        current = 0
        if self.current is not None:
            listed = [b for b in self.buffers if b.path or b.autosave_id]
            if self.current in listed:
                current = listed.index(self.current)
        session.save_session(tabs, current)

    def _restore(self) -> int:
        """Reopen the last session's tabs, and any unsaved work a crash left behind.
        Returns how many unsaved buffers came back."""
        data = session.load_session()
        restored = 0
        claimed: List[str] = []
        other_window = data.get('pid') and data.get('pid') != os.getpid() and \
            session.pid_alive(int(data.get('pid') or 0))
        if self.settings['reopen_session'] and not other_window:
            for tab in data['tabs']:
                if not isinstance(tab, dict):
                    continue
                autosave_id = tab.get('autosave')
                if autosave_id:
                    claimed.append(autosave_id)
                    record = session.read_autosave(autosave_id)
                    if record is not None:
                        self._restore_autosave(record)
                        restored += 1
                        continue
                path = tab.get('path')
                if path and os.path.isfile(path):
                    buf = self.open_path(path, select=False, cursor=tab.get('cursor'))
                    if buf and tab.get('language') in syntax.FACTORIES:
                        buf.set_language(tab['language'], forced=True)
            current = data.get('current', 0)
            if self.buffers and isinstance(current, int):
                self.select(self.buffers[max(0, min(current, len(self.buffers) - 1))])
        if other_window:
            return 0
        for record in session.orphans(claimed):
            self._restore_autosave(record)
            restored += 1
        return restored

    def _restore_autosave(self, record: session.Autosave) -> Buffer:
        title = record.title or (os.path.basename(record.path) if record.path
                                 else self._next_untitled())
        if not record.path and re.fullmatch(re.escape(t('untitled')) + r'(?: \d+)?', title):
            self.untitled_n += 1
        buf = Buffer(self, record.path, title)
        buf.autosave_id = record.id
        self._add_buffer(buf)
        lang = record.language if record.language in syntax.FACTORIES else None
        if lang:
            buf.set_language(lang, forced=True)
        else:
            buf.set_language(syntax.detect(record.path, (record.text or '')[:200]
                                           .split('\n', 1)[0]))
        buf.disk_mtime = record.disk_mtime
        buf.load(record.text or '', Format.from_dict(record.fmt), record.cursor, modified=True)
        if record.path and record.disk_mtime is not None:
            try:
                if os.stat(record.path).st_mtime != record.disk_mtime:
                    self.status(t('status.restored_changed', name=title), T["gold"])
            except OSError:
                pass
        self.update_tab(buf)
        if self.current is None:
            self.select(buf)
        return buf

    # ─── Calls from the buffers ────────────────────────────────

    def on_dirty(self, buf: Buffer) -> None:
        self.update_tab(buf)
        if buf is self.current:
            self.update_title()
        if not buf.dirty and buf.autosave_id:
            session.drop_autosave(buf.autosave_id)
            buf.autosave_id = None
            self._save_session_soon()

    def on_cursor(self, buf: Buffer) -> None:
        if buf is self.current and self._status_id is None:
            self._status_id = self.root.after(30, self._update_position)

    def on_load_progress(self, buf: Buffer) -> None:
        if buf is self.current and buf.load_total:
            pct = int(100 * buf.load_done / buf.load_total)
            self.st_message.configure(text=f"{t('status.loading', pct=pct)}  "
                                           f"{buf.title}".upper(), fg=T["gold"])

    def on_loaded(self, buf: Buffer) -> None:
        self.update_tab(buf)
        if buf is self.current:
            if self.st_message.cget('fg') == T["gold"] and \
                    self.st_message.cget('text').startswith(t('status.loading', pct='')[:4]
                                                            .upper()):
                self.st_message.configure(text='')
            self.update_status()
            self.update_title()

    def on_huge(self, buf: Buffer) -> None:
        self.status(t('status.huge', name=buf.title), T["gold"])
        self.update_status()

    def on_refresh(self, buf: Buffer, first: int, last: int) -> None:
        if buf is self.current:
            self.findbar.paint(buf, first, last)

    # ─── Status bar ────────────────────────────────────────────

    def status(self, text: str, colour: Optional[str] = None) -> None:
        self.message = text
        self.st_message.configure(text=text.upper(), fg=colour or T["muted"])
        if colour == T["pink"]:
            self.glitch.now(self.strip, strong=True)

    def hint(self, text: Optional[str]) -> None:
        """A tab's path or a button's shortcut, shown while the pointer is on it."""
        if text:
            self.st_message.configure(text=text, fg=T["text"])
        else:
            self.st_message.configure(text=self.message.upper(), fg=T["muted"])

    def _update_position(self) -> None:
        self._status_id = None
        buf = self.current
        if buf is None:
            self.st_pos.set('')
            return
        line, col = buf.cursor()
        text = t('status.position', line=line, col=col + 1)
        if buf.text.tag_ranges('sel') and not buf.loading:
            n = len(buf.text.get('sel.first', 'sel.last'))
            if n:
                text += '  ' + t('status.selected', n=n)
        self.st_pos.set(text)

    def update_status(self) -> None:
        buf = self.current
        self.st_zoom.set(f"{round(100 * self.settings['font_size'] / 11)}%")
        if buf is None:
            for item in (self.st_wrap, self.st_newline, self.st_encoding, self.st_lang,
                         self.st_pos, self.st_access):
                item.set('')
            return
        self.st_wrap.set(t('status.wrap') if buf.wrap else t('status.nowrap'),
                         T["accent"] if buf.wrap else None)
        self.st_newline.set(buf.fmt.newline_label())
        self.st_encoding.set(buf.fmt.label())
        self.st_lang.set(syntax.name_of(buf.lang))
        access = ''
        if buf.path and os.path.exists(buf.path) and not fileio.can_write(buf.path):
            access = t('status.read_only')
        self.st_access.set(access, T["gold"])
        self._update_position()

    def _popup(self, m: tk.Menu, event) -> None:
        try:
            m.tk_popup(event.x_root, event.y_root - m.winfo_reqheight())
        finally:
            m.grab_release()

    def _language_menu(self, event) -> None:
        buf = self.current
        if buf is None:
            return
        m = menu(self.root, self.font(9, False))
        choice = tk.StringVar(m, value=buf.lang or '')
        m.add_radiobutton(label=t('menu.plain'), variable=choice, value='',
                          command=lambda: self._set_language(None))
        for lang in sorted(syntax.NAMES, key=lambda k: syntax.NAMES[k].lower()):
            m.add_radiobutton(label=syntax.NAMES[lang], variable=choice, value=lang,
                              command=lambda lang=lang: self._set_language(lang))
        m._var = choice
        self._popup(m, event)

    def _set_language(self, lang: Optional[str]) -> None:
        if self.current:
            self.current.set_language(lang, forced=True)
            self.update_status()
            self._save_session_soon()

    def _encoding_menu(self, event) -> None:
        buf = self.current
        if buf is None:
            return
        m = menu(self.root, self.font(9, False))
        reopen = menu(m, self.font(9, False))
        save_with = menu(m, self.font(9, False))
        current = buf.fmt.encoding + ('+bom' if buf.fmt.bom else '')
        var = tk.StringVar(m, value=current)
        options = [('utf-8', False), ('utf-8', True), ('utf-16-le', True), ('utf-16-be', True),
                   ('cp1252', False), ('latin-1', False)]
        for codec, bom in options:
            label = Format(codec, bom).label()
            save_with.add_radiobutton(label=label, variable=var,
                                      value=codec + ('+bom' if bom else ''),
                                      command=lambda c=codec, b=bom: self._save_with(c, b))
            if not bom or codec != 'utf-8':
                reopen.add_command(label=dict(ENCODINGS)[codec],
                                   command=lambda c=codec: self.reload(self.current, c),
                                   state='normal' if buf.path else 'disabled')
        m.add_cascade(label=t('menu.reopen_with'), menu=reopen,
                      state='normal' if buf.path and os.path.exists(buf.path) else 'disabled')
        m.add_cascade(label=t('menu.save_with'), menu=save_with)
        m._keep = (reopen, save_with, var)
        self._popup(m, event)

    def _save_with(self, codec: str, bom: bool) -> None:
        buf = self.current
        if buf is None:
            return
        buf.fmt = Format(codec, bom, buf.fmt.newline)
        self._mark_format_change(buf)
        self.status(t('status.encoding_set', name=buf.title, enc=buf.fmt.label()))

    def _newline_menu(self, event) -> None:
        buf = self.current
        if buf is None:
            return
        m = menu(self.root, self.font(9, False))
        var = tk.StringVar(m, value=buf.fmt.newline)
        for value, label in NEWLINES:
            m.add_radiobutton(label=label, variable=var, value=value,
                              command=lambda v=value: self._set_newline(v))
        m._var = var
        self._popup(m, event)

    def _set_newline(self, newline: str) -> None:
        buf = self.current
        if buf is None or buf.fmt.newline == newline:
            return
        buf.fmt = Format(buf.fmt.encoding, buf.fmt.bom, newline)
        self._mark_format_change(buf)
        self.status(t('status.newline_set', name=buf.title, nl=buf.fmt.newline_label()))

    def _mark_format_change(self, buf: Buffer) -> None:
        """A new encoding or line ending is a change to save, like an edit."""
        buf.text.edit_modified(True)
        buf.version += 1
        self.on_change(buf)
        self.update_status()

    # ─── Commands ──────────────────────────────────────────────

    def find(self, mode: str) -> None:
        if self.current is None:
            return
        self.findbar.open(mode)

    def toggle_comment(self) -> None:
        buf = self.current
        if buf and not buf.toggle_comment():
            self.status(t('status.no_comment', lang=syntax.name_of(buf.lang)))

    def toggle_wrap(self) -> None:
        buf = self.current
        if buf is None:
            return
        if not buf.set_wrap(not buf.wrap):
            self.status(t('status.huge', name=buf.title), T["gold"])
        else:
            self.settings['wrap'] = buf.wrap
        self.update_status()

    def zoom(self, step: int) -> None:
        size = 11 if step == 0 else max(6, min(48, self.settings['font_size'] + step))
        self.settings['font_size'] = size
        self.editor_font.configure(size=size)
        self.editor_bold.configure(size=size)
        self.gutter_font.configure(size=max(6, size - 1))
        for buf in self.buffers:
            buf.set_tabs()
        self.update_status()

    def toggle_session(self) -> None:
        self.settings['reopen_session'] = not self.settings['reopen_session']
        core.save_settings(self.settings)

    def show_menu(self) -> None:
        buf = self.current
        has = buf is not None
        f = self.font(9, False)
        m = menu(self.root, f)
        m.add_command(label=t('menu.new'), accelerator='Ctrl+N', command=self.new_buffer)
        m.add_command(label=t('menu.open'), accelerator='Ctrl+O', command=self.open_dialog)
        recent = menu(m, f)
        paths = [p for p in core.load_recent() if os.path.exists(p)][:15]
        for path in paths:
            recent.add_command(label=core.home_short(path),
                               command=lambda p=path: self.open_path(p))
        if paths:
            recent.add_separator()
            recent.add_command(label=t('menu.recent_clear'), command=self._clear_recent)
        else:
            recent.add_command(label=t('menu.recent_empty'), state='disabled')
        m.add_cascade(label=t('menu.recent'), menu=recent)
        m.add_separator()
        state = 'normal' if has else 'disabled'
        m.add_command(label=t('menu.save'), accelerator='Ctrl+S', state=state,
                      command=lambda: self.save(self.current))
        m.add_command(label=t('menu.save_as'), accelerator='Ctrl+Shift+S', state=state,
                      command=lambda: self.save(self.current, as_new=True))
        m.add_command(label=t('menu.save_admin'),
                      state='normal' if has and buf.path and fileio.pkexec_path() else 'disabled',
                      command=lambda: self.save_admin(self.current))
        m.add_command(label=t('menu.reload'),
                      state='normal' if has and buf.path and os.path.exists(buf.path)
                      else 'disabled', command=lambda: self.reload(self.current))
        m.add_command(label=t('menu.close'), accelerator='Ctrl+W', state=state,
                      command=lambda: self.close_buffer(self.current))
        m.add_command(label=t('menu.reopen_closed'), accelerator='Ctrl+Shift+T',
                      state='normal' if self.closed else 'disabled', command=self.reopen_closed)
        m.add_separator()
        m.add_command(label=t('menu.find'), accelerator='Ctrl+F', state=state,
                      command=lambda: self.find('find'))
        m.add_command(label=t('menu.replace'), accelerator='Ctrl+H', state=state,
                      command=lambda: self.find('replace'))
        m.add_command(label=t('menu.goto'), accelerator='Ctrl+G', state=state,
                      command=lambda: self.find('goto'))
        m.add_command(label=t('menu.comment'), accelerator='Ctrl+/', state=state,
                      command=self.toggle_comment)
        m.add_separator()
        wrap = tk.BooleanVar(m, value=bool(buf and buf.wrap))
        m.add_checkbutton(label=t('menu.wrap'), accelerator='Alt+Z', variable=wrap,
                          command=self.toggle_wrap, state=state)
        m.add_command(label=t('menu.zoom_in'), accelerator='Ctrl++', command=lambda: self.zoom(+1))
        m.add_command(label=t('menu.zoom_out'), accelerator='Ctrl+-',
                      command=lambda: self.zoom(-1))
        m.add_command(label=t('menu.zoom_reset'), accelerator='Ctrl+0',
                      command=lambda: self.zoom(0))
        reopen = tk.BooleanVar(m, value=self.settings['reopen_session'])
        m.add_checkbutton(label=t('menu.session'), variable=reopen, command=self.toggle_session)
        m.add_separator()
        m.add_command(label=t('menu.quit'), accelerator='Ctrl+Q', command=self.quit)
        m._keep = (recent, wrap, reopen)
        b = self.menu_button
        m.tk_popup(b.winfo_rootx() + b.winfo_width() - m.winfo_reqwidth(),
                   b.winfo_rooty() + b.winfo_height())

    def _clear_recent(self) -> None:
        for path in core.load_recent():
            core.remove_recent(path)

    # ─── Changes made elsewhere ────────────────────────────────

    def _focus_in(self, event) -> None:
        if event.widget is not self.root:
            return
        for buf in list(self.buffers):
            if not buf.path or buf.loading or buf.disk_mtime is None:
                continue
            try:
                mtime = os.stat(buf.path).st_mtime
            except OSError:
                continue
            if mtime == buf.disk_mtime:
                continue
            if buf.dirty:
                buf.disk_mtime = mtime         # ask once; saving later asks again
                self.status(t('ask.changed_title') + ': ' + buf.title, T["gold"])
            else:
                self.reload(buf)
                self.status(t('status.reloaded', name=buf.title), T["gold"])

    def _configured(self, event) -> None:
        if event.widget is self.root:
            self.tabs._fit()

    # ─── Plumbing ──────────────────────────────────────────────

    def later(self, fn: Callable[[], None]) -> None:
        """Run fn on the Tk thread (worker threads call this)."""
        self._jobs.put(fn)
        if self._poll_id is None:
            try:
                self._poll_id = self.root.after(15, self._poll)
            except (RuntimeError, tk.TclError):
                pass        # not on the Tk thread: the running poll picks it up

    def _poll(self) -> None:
        self._poll_id = None
        while True:
            try:
                fn = self._jobs.get_nowait()
            except queue.Empty:
                break
            fn()
        self._poll_id = self.root.after(50, self._poll)

    def _on_tk_error(self, exc, value, tb) -> None:
        import traceback
        log.error("interface error: %s", ''.join(traceback.format_exception(exc, value, tb)))
        try:
            self.status(f"{exc.__name__}: {value}", T["pink"])
        except tk.TclError:
            pass
        if self.bench or os.environ.get('SPARK_EDIT_RAISE'):
            traceback.print_exception(exc, value, tb)

    def run(self) -> None:
        self._poll_id = self.root.after(50, self._poll)
        self.root.mainloop()


def reduced_motion_or_bench(bench: bool) -> bool:
    return bench or core.reduced_motion()


# ─── --bench ──────────────────────────────────────────────────

def rss_mb() -> Optional[float]:
    try:
        with open('/proc/self/status', encoding='ascii') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return None


def bench(path: Optional[str], age: Callable[[], float]) -> int:
    """Open the window (and the file), print how long each step took from the moment the
    process started, the longest the window went without answering while loading, and the
    time to colour the end of the file; then close."""
    app = App([(path, 0, 0)] if path else [], restore=False, bench=True)
    root = app.root
    out: Dict[str, float] = {}
    beats: List[float] = []

    def beat():
        beats.append(time.perf_counter())
        if 'loaded' not in out:
            root.after(5, beat)

    root.update()
    out['window'] = age()
    buf = app.current
    beat()

    def wait_loaded():
        if buf is not None and 'first_screen' not in out and buf.first_screen_at is not None:
            root.update_idletasks()
            out['first_screen'] = age()
        if buf is not None and (buf.loading or 'first_screen' not in out):
            root.after(5, wait_loaded)
            return
        out['loaded'] = age()
        lines = buf.line_count() if buf else 0
        t0 = time.perf_counter()
        if buf is not None:
            buf.text.see('end')
            root.update_idletasks()
            buf.refresh()
            root.update()
        out['to_end'] = time.perf_counter() - t0
        t1 = time.perf_counter()
        if buf is not None:
            buf.content()
        out['text_get'] = time.perf_counter() - t1
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        out['pause'] = max(gaps) if gaps else 0.0
        size = os.path.getsize(path) if path else 0
        print(f"{APP_NAME} {VERSION} bench, Python {sys.version.split()[0]}, Tk {tk.TkVersion}")
        if path:
            print(f"file:          {os.path.basename(path)}, {core.size_text(size)}, "
                  f"{lines:,} lines, {syntax.name_of(buf.lang if buf else None)}")
        print(f"window shown:  {out['window']:.2f} s after the process started")
        if path:
            print(f"first screen:  {out['first_screen']:.2f} s (file read, decoded, first "
                  f"lines in the editor and drawn)")
            print(f"fully loaded:  {out['loaded']:.2f} s (whole file in the editor, editable)")
            print(f"longest pause: {out['pause'] * 1000:.0f} ms (the window answers at least "
                  f"this often while loading)")
            print(f"jump to end:   {out['to_end'] * 1000:.0f} ms (scroll, line numbers, colours)")
            print(f"whole text:    {out['text_get'] * 1000:.0f} ms to read it back (find, save)")
        mem = rss_mb()
        if mem is not None:
            print(f"memory:        {mem:.0f} MB resident")
        root.after(10, app.quit)

    root.after(1, wait_loaded)
    app.run()
    return 0


def picker():
    """The file dialog to run: spark-pick (Spark Files' picker, through the desktop portal).
    None: use Tk's own dialog."""
    return shutil.which('spark-pick')
