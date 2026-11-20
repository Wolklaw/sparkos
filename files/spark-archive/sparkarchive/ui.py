"""What both windows share: the Tk root with the house look, the questions a job asks
(password, overwrite) as dialogs, the progress panel, and the result text."""

import os
import queue
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import APP_CLASS, APP_ID, APP_NAME, APP_SLUG, VERSION
from . import core
from .core import load_json, log, reduced_motion, save_json
from .jobs import (CANCEL, DEFAULT_PASSWORD_KIND, FORMATS, KEEP_BOTH, PASSWORD_KINDS,
                   REPLACE, SEVEN_Z, SKIP, TAR_ZST, ZIP, Job, Result)
from .text import t, why
from .widgets import (MONO_FAMILIES, T, Glitch, GlitchPanel, GlitchText, Mark, Segmented,
                      Strip, Toggle, WolkButton, mix)


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_ARCHIVE_SCALE')
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
    for path in (os.path.join(here, 'icons', f'{APP_SLUG}-64.png'),
                 os.path.join(here, 'icons', f'{APP_SLUG}-256.png'),
                 f'/usr/share/icons/hicolor/64x64/apps/{APP_ID}.png'):
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


def middle(text: str, limit: int) -> str:
    """Shorten in the middle, keeping the start and the file name's end."""
    if len(text) <= limit:
        return text
    keep = max(4, limit - 1)
    return text[:keep // 2] + '…' + text[-(keep - keep // 2):]


def home_short(path: str) -> str:
    home = os.path.expanduser('~')
    if path == home or path.startswith(home + '/'):
        return '~' + path[len(home):]
    return path


class Look:
    """A Tk root in the house style. Both windows are one of these."""

    def __init__(self):
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.settings = load_json('config.json')
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and self.settings.get("glitch", True) is not False)
        self.root.configure(bg=T["bg"])
        self.root.title(APP_NAME)
        icon = load_icon(self.root)
        if icon is not None:
            self.root.iconphoto(True, icon)
            self._icon = icon
        self.bridge = Bridge(self)

    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))

    def button(self, parent, text: str, command, variant: str = "ghost") -> WolkButton:
        return WolkButton(parent, text, command, self.font(9), variant, padx=self.px(12),
                          pady=self.px(5))

    def header(self, parent: tk.Misc, title: str, size: int = 14) -> Tuple[Mark, GlitchText,
                                                                         tk.Label, tk.Frame]:
        px, bg = self.px, T["bg"]
        head = tk.Frame(parent, bg=bg)
        mark = Mark(head, px(34 if size >= 13 else 28), bg)
        mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0), fill="x", expand=True)
        title_w = GlitchText(col, title, self.tkfont(size), bg)
        title_w.pack(anchor="w")
        status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7), anchor="w")
        status.pack(anchor="w", padx=(px(6), 0), fill="x")
        return mark, title_w, status, head

    def style_table(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure("Spark.Treeview", background=T["panel"], fieldbackground=T["panel"],
                        foreground=T["text"], bordercolor=T["line"], lightcolor=T["panel"],
                        darkcolor=T["panel"], rowheight=self.px(24), font=self.font(9, False),
                        borderwidth=0, indent=self.px(16))
        style.map("Spark.Treeview", background=[("selected", T["hover"])],
                  foreground=[("selected", T["accent"])])
        style.configure("Spark.Treeview.Heading", background=T["panel2"], foreground=T["muted"],
                        bordercolor=T["line"], lightcolor=T["panel2"], darkcolor=T["panel2"],
                        font=self.font(8), relief="flat", padding=(6, 4))
        style.map("Spark.Treeview.Heading", background=[("active", T["hover"])],
                  foreground=[("active", T["text"])])
        style.layout("Spark.Treeview", [("Spark.Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Spark.Vertical.TScrollbar", background=T["panel2"], troughcolor=T["bg"],
                        bordercolor=T["bg"], arrowcolor=T["muted"], lightcolor=T["panel2"],
                        darkcolor=T["panel2"], gripcount=0)
        style.map("Spark.Vertical.TScrollbar", background=[("active", T["line2"])])

    # ─── dialogs ──────────────────────────────────────────────

    def _dialog(self, title: str) -> Tuple[tk.Toplevel, tk.Frame, GlitchText]:
        px = self.px
        if not self.root.winfo_viewable():
            self.root.deiconify()
        top = tk.Toplevel(self.root, bg=T["bg"])
        top.title(f"{title} - {APP_NAME}")
        top.transient(self.root)
        top.resizable(False, False)
        panel = GlitchPanel(top, T["panel"])
        panel.pack(fill="both", expand=True, padx=px(8), pady=px(8))
        inner = panel.inner
        heading = GlitchText(inner, title.upper(), self.tkfont(11), T["panel"])
        heading.pack(anchor="w", padx=px(14), pady=(px(12), px(4)))
        body = tk.Frame(inner, bg=T["panel"])
        body.pack(fill="both", expand=True, padx=px(16), pady=(0, px(14)))
        top.after(60, lambda: (self.glitch.now(heading, panel) if top.winfo_exists() else None))
        return top, body, heading

    def _show_modal(self, top: tk.Toplevel, focus: tk.Misc) -> None:
        top.update_idletasks()
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            w, h = top.winfo_reqwidth(), top.winfo_reqheight()
            if rw > 50:
                top.geometry(f"+{rx + max(0, (rw - w) // 2)}+{ry + max(0, (rh - h) // 3)}")
        except tk.TclError:
            pass
        try:
            top.grab_set()
        except tk.TclError:
            pass
        focus.focus_set()
        self.root.wait_window(top)

    def ask_password(self, archive: str, retry: bool) -> Optional[str]:
        px = self.px
        top, body, heading = self._dialog(t('password.title'))
        msg = t('password.retry' if retry else 'password.body', archive=archive)
        tk.Label(body, text=msg, bg=T["panel"], fg=T["pink"] if retry else T["text"],
                 font=self.font(9, False), wraplength=px(380), justify="left",
                 anchor="w").pack(anchor="w", fill="x")
        if retry:
            top.after(120, lambda: self.glitch.now(heading, strong=True))
        value = tk.StringVar()
        row = tk.Frame(body, bg=T["panel"])
        row.pack(fill="x", pady=(px(10), px(4)))
        entry = tk.Entry(row, textvariable=value, show='•', bg=T["out_bg"], fg=T["text"],
                         insertbackground=T["accent"], relief="flat", font=self.font(10, False),
                         highlightthickness=1, highlightbackground=T["line2"],
                         highlightcolor=T["accent"], width=30)
        entry.pack(side="left", fill="x", expand=True, ipady=px(4))
        Toggle(row, t('password.show'), False,
               lambda on: entry.configure(show='' if on else '•'), self.font(8)).pack(
            side="left", padx=(px(8), 0))
        answer: Dict[str, Optional[str]] = {'value': None}

        def ok(_e=None):
            answer['value'] = value.get()
            top.destroy()

        buttons = tk.Frame(body, bg=T["panel"])
        buttons.pack(fill="x", pady=(px(12), 0))
        self.button(buttons, t('button.ok'), ok, "primary").pack(side="right")
        self.button(buttons, t('button.cancel'), top.destroy).pack(side="right",
                                                                   padx=(0, px(8)))
        entry.bind('<Return>', ok)
        top.bind('<Escape>', lambda _e: top.destroy())
        self._show_modal(top, entry)
        return answer['value']

    def ask_compress(self, n: int, fmt: str = ZIP, with_password: bool = False,
                     kind: Optional[str] = None
                     ) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        """Which format, and a password if wanted: (fmt, password or None, zip encryption or
        None), or None for Cancel. With a password there are three kinds to pick from: a zip
        that opens on any PC (ZipCrypto, weak), a zip with strong protection (AES-256), a 7z
        with strong protection and hidden names. The last kind picked is remembered. The
        password is asked twice; .tar.zst can't have one."""
        px = self.px
        top, body, heading = self._dialog(t('button.compress'))
        tk.Label(body, text=t('compress.as', n=n), bg=T["panel"], fg=T["text"],
                 font=self.font(9, False)).pack(anchor="w")
        kinds = {k: (f, enc) for k, f, enc in PASSWORD_KINDS}
        remembered = self.settings.get('password_kind')
        if kind not in kinds:
            kind = SEVEN_Z if fmt == SEVEN_Z else (
                remembered if remembered in kinds else DEFAULT_PASSWORD_KIND)
        state = {'fmt': fmt if fmt in FORMATS else ZIP, 'pw': with_password, 'kind': kind}
        formats = tk.Frame(body, bg=T["panel"])               # shown without a password
        formats.pack(anchor="w", fill="x")
        seg = Segmented(formats, [('.ZIP', ZIP), ('.7Z', SEVEN_Z), ('.TAR.ZST', TAR_ZST)],
                        state['fmt'], lambda v: state.update(fmt=v), self.font(9))
        seg.pack(anchor="w", pady=(px(10), 0))

        def password_on(on: bool) -> None:
            state['pw'] = on
            if on:
                pick(SEVEN_Z if state['fmt'] == SEVEN_Z else state['kind'])
            else:
                state['fmt'] = kinds[state['kind']][0]
                seg.set(state['fmt'])
            refresh()

        Toggle(body, t('compress.with_password'), with_password, password_on,
               self.font(8)).pack(anchor="w", pady=(px(12), 0))
        fields = tk.Frame(body, bg=T["panel"])                # shown with a password
        radios = {}
        for k, _f, _enc in PASSWORD_KINDS:
            radios[k] = Toggle(fields, t('compress.kind_' + k.replace('-', '_')),
                               k == state['kind'], lambda _on, k=k: pick(k), self.font(8))
            radios[k].pack(anchor="w", pady=(px(8) if k == PASSWORD_KINDS[0][0] else px(4), 0))
        note = tk.Label(fields, text='', bg=T["panel"], fg=T["dim"], font=self.font(8, False),
                        wraplength=px(380), justify="left", anchor="w")
        note.pack(anchor="w", fill="x", pady=(px(6), 0))
        entries = []
        for key in ('compress.password', 'compress.again'):
            tk.Label(fields, text=t(key), bg=T["panel"], fg=T["muted"],
                     font=self.font(8, False)).pack(anchor="w", pady=(px(8), px(2)))
            entry = tk.Entry(fields, show='•', bg=T["out_bg"], fg=T["text"],
                             insertbackground=T["accent"], relief="flat",
                             font=self.font(10, False), highlightthickness=1,
                             highlightbackground=T["line2"], highlightcolor=T["accent"],
                             width=34)
            entry.pack(fill="x", ipady=px(4))
            entries.append(entry)
        message = tk.Label(body, text='', bg=T["panel"], fg=T["pink"], font=self.font(8, False),
                           wraplength=px(380), justify="left", anchor="w")
        buttons = tk.Frame(body, bg=T["panel"])

        def pick(k: str) -> None:
            state['kind'] = k
            for other, radio in radios.items():
                radio.set(other == k)
            note.config(text=t('compress.note_' + k.replace('-', '_')),
                        fg=T["gold"] if k == 'zip-any' else T["dim"])

        def refresh() -> None:
            message.config(text='')
            message.pack_forget()
            buttons.pack_forget()
            if state['pw']:
                formats.pack_forget()
                fields.pack(fill="x", pady=(px(4), 0))
            else:
                fields.pack_forget()
                formats.pack(anchor="w", fill="x", after=first)
            message.pack(anchor="w", fill="x", pady=(px(6), 0))
            buttons.pack(fill="x", pady=(px(10), 0))

        first = body.winfo_children()[0]                      # the "Compress n items as" line
        answer: Dict[str, Any] = {'value': None}

        def ok(_e=None) -> None:
            if not state['pw']:
                answer['value'] = (state['fmt'], None, None)
                top.destroy()
                return
            problem = None
            if not entries[0].get():
                problem = 'compress.empty'
            elif entries[0].get() != entries[1].get():
                problem = 'compress.mismatch'
            if problem:
                message.config(text=t(problem))
                self.glitch.now(heading, strong=True)
                return
            chosen_fmt, encryption = kinds[state['kind']]
            if self.settings.get('password_kind') != state['kind']:
                self.settings['password_kind'] = state['kind']
                save_json('config.json', self.settings)
            answer['value'] = (chosen_fmt, entries[0].get(),
                               encryption if chosen_fmt == ZIP else None)
            top.destroy()

        go = self.button(buttons, t('button.ok'), ok, "primary")
        go.pack(side="right")
        self.button(buttons, t('button.cancel'), top.destroy).pack(side="right",
                                                                   padx=(0, px(8)))
        pick(state['kind'])
        refresh()
        top.spark_ok = ok                       # for the tests
        top.spark_pick = pick
        for entry in entries:
            entry.bind('<Return>', ok)
        top.bind('<Escape>', lambda _e: top.destroy())
        self._show_modal(top, entries[0] if with_password else go.label)
        return answer['value']

    def ask_overwrite(self, info: Dict[str, Any]) -> Tuple[str, bool]:
        px = self.px
        top, body, _heading = self._dialog(t('overwrite.title'))
        key = 'overwrite.link' if info.get('old_is_link') else 'overwrite.body'
        tk.Label(body, text=t(key, name=middle(info.get('path') or info['name'], 70)),
                 bg=T["panel"], fg=T["text"], font=self.font(9, False), wraplength=px(420),
                 justify="left", anchor="w").pack(anchor="w", fill="x")
        facts = tk.Frame(body, bg=T["panel"])
        facts.pack(anchor="w", fill="x", pady=(px(8), 0))
        for line_key, size_key, when_key in (('overwrite.existing', 'old_size', 'old_mtime'),
                                             ('overwrite.new', 'new_size', 'new_mtime')):
            tk.Label(facts, text=t(line_key, size=core.size(info.get(size_key)),
                                   when=core.when(info.get(when_key))),
                     bg=T["panel"], fg=T["muted"], font=self.font(8, False),
                     anchor="w").pack(anchor="w")
        every = {'on': False}
        Toggle(body, t('overwrite.all'), False, lambda on: every.update(on=on),
               self.font(8)).pack(anchor="w", pady=(px(10), 0))
        answer = {'choice': CANCEL}

        def pick(choice: str):
            answer['choice'] = choice
            top.destroy()

        buttons = tk.Frame(body, bg=T["panel"])
        buttons.pack(fill="x", pady=(px(12), 0))
        replace = self.button(buttons, t('button.replace'), lambda: pick(REPLACE), "primary")
        replace.pack(side="right")
        self.button(buttons, t('button.keep_both'), lambda: pick(KEEP_BOTH)).pack(
            side="right", padx=(0, px(8)))
        self.button(buttons, t('button.skip'), lambda: pick(SKIP)).pack(side="right",
                                                                         padx=(0, px(8)))
        self.button(buttons, t('button.cancel'), lambda: pick(CANCEL), "danger").pack(
            side="left")
        top.bind('<Escape>', lambda _e: pick(CANCEL))
        self._show_modal(top, replace.label)
        return answer['choice'], every['on']


class Bridge:
    """Lets a job's thread ask the window a question and wait for the answer."""

    def __init__(self, look: Look):
        self.look = look
        self.q: "queue.Queue[Tuple[str, Dict[str, Any], threading.Event, Dict[str, Any]]]" = \
            queue.Queue()
        self.closing = False

    def ask(self, question: str, info: Dict[str, Any]) -> Any:
        if self.closing:
            return None if question == 'password' else (CANCEL, False)
        done = threading.Event()
        box: Dict[str, Any] = {}
        self.q.put((question, info, done, box))
        done.wait()
        return box.get('answer')

    def pump(self) -> None:
        """Called from the window's loop: show any waiting question."""
        while True:
            try:
                question, info, done, box = self.q.get_nowait()
            except queue.Empty:
                return
            try:
                if self.closing:
                    box['answer'] = None if question == 'password' else (CANCEL, False)
                elif question == 'password':
                    box['answer'] = self.look.ask_password(info['archive'], info.get('retry'))
                elif question == 'overwrite':
                    box['answer'] = self.look.ask_overwrite(info)
            finally:
                done.set()

    def release(self) -> None:
        """The window is closing: answer everything with Cancel."""
        self.closing = True
        self.pump()


class Progress(tk.Frame):
    """A job's progress: a bar in the house strip colours, counts, the current name, Cancel."""

    def __init__(self, parent: tk.Misc, look: Look, on_cancel: Callable[[], None]):
        super().__init__(parent, bg=parent.cget("bg"))
        px, bg = look.px, parent.cget("bg")
        self.look = look
        top = tk.Frame(self, bg=bg)
        top.pack(fill="x")
        self.label = tk.Label(top, text="", bg=bg, fg=T["text"], font=look.font(9), anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        self.cancel_btn = look.button(top, t('button.cancel'), on_cancel, "danger")
        self.cancel_btn.pack(side="right")
        trough = tk.Frame(self, bg=T["line"], padx=1, pady=1)
        trough.pack(fill="x", pady=(px(8), px(6)))
        self.bar = Strip(trough, height=px(6))
        self.bar.configure(bg=T["out_bg"])
        self.bar.pack(fill="x")
        self.counts = tk.Label(self, text="", bg=bg, fg=T["muted"], font=look.font(8, False),
                               anchor="w")
        self.counts.pack(fill="x")
        self.current = tk.Label(self, text="", bg=bg, fg=T["dim"], font=look.font(8, False),
                                anchor="w")
        self.current.pack(fill="x")
        self._pulse = 0

    def show_job(self, job: Job, title: str) -> None:
        self.label.config(text=title)
        if job.phase == 'reading':
            self._pulse = (self._pulse + 1) % 40
            self.bar.draw(fraction=0.12, shift=self._pulse * 10)
            self.counts.config(text=t('progress.reading', name=''))
            self.current.config(text='')
            return
        frac = job.fraction
        self.bar.draw(fraction=frac if frac is not None else 0.0)
        parts = []
        if job.total_files:
            parts.append(t('progress.files', done=min(job.done_files, job.total_files),
                           total=job.total_files))
        if job.total_bytes:
            parts.append(t('progress.bytes', done=core.size(min(job.done_bytes,
                                                                 job.total_bytes)),
                           total=core.size(job.total_bytes)))
        self.counts.config(text='  ·  '.join(parts))
        self.current.config(text=middle(job.current, 78))

    def cancelling(self) -> None:
        self.counts.config(text=t('progress.cancelling'))
        self.cancel_btn.set_enabled(False)


def result_lines(res: Result, kind: str, selected: bool = False) -> Tuple[str, List[str], bool]:
    """(headline, detail lines, is_error) for a finished job."""
    if res.cancelled:
        if kind == 'extract':
            head = t('done.cancelled_extract_replaced', n=res.replaced) if res.replaced \
                else t('done.cancelled_extract')
        else:
            head = t('done.cancelled_compress')
        return head, [], False
    if not res.ok:
        detail = res.detail
        return t('error.' + (res.error or 'bug'), detail=detail), \
            _problem_lines(res), True
    if kind == 'extract':
        head = t('done.extracted_selected' if selected else 'done.extracted',
                 files=res.files + res.links, folder=home_short(res.output or ''))
    else:
        try:
            size = core.size(os.path.getsize(res.output or ''))
        except OSError:
            size = '?'
        head = t('done.compressed', name=os.path.basename(res.output or ''), size=size)
    lines = []
    if res.replaced:
        lines.append(t('done.replaced', n=res.replaced))
    if res.skipped:
        lines.append(t('done.skipped', n=res.skipped))
    lines += _problem_lines(res)
    return head, lines, False


def _problem_lines(res: Result, limit: int = 8) -> List[str]:
    if not res.problems:
        return []
    out = [t('done.problems', n=len(res.problems))]
    for name, reason in res.problems[:limit]:
        out.append(f"  {middle(name, 48)}: {why(reason)}")
    if len(res.problems) > limit:
        out.append(f"  … +{len(res.problems) - limit}")
    return out


def version_chip(look: Look, parent: tk.Misc) -> tk.Label:
    return tk.Label(parent, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"],
                    font=look.font(7), padx=look.px(6), pady=look.px(2), highlightthickness=1,
                    highlightbackground=T["line"])


__all__ = ['Look', 'Bridge', 'Progress', 'result_lines', 'middle', 'home_short', 'mix',
           'version_chip']
