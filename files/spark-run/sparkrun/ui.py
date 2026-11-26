"""The windows: the chooser a double-click opens (Run once / Install as an app), the list of
installed Windows apps, options, and the plain error view. Slow work (downloads, wineboot,
installers, folder sizes) runs in a thread; the window only reads a queue."""

import os
import queue
import re
import shutil
import subprocess
import threading
import traceback
from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, GUIDE_URL, VERSION, apps, pe, sources
from . import wine as winemod
from .core import cache_dir, ensure, log, reduced_motion, size
from .errors import Problem
from .text import t
from .widgets import (MONO_FAMILIES, T, Glitch, GlitchPanel, GlitchText, Mark, Segmented,
                      Strip, WolkButton)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── Look helpers ────────────────────────────────────────────

def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_RUN_SCALE')
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
    """The mono font, remembered between runs (listing every font family takes a moment)."""
    path = os.path.join(cache_dir(), 'font')
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
        ensure(cache_dir())
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def open_path(path: str) -> None:
    apps.open_folder(path)


def load_image(root: tk.Misc, source, px: int) -> Optional[tk.PhotoImage]:
    """A square image of px pixels from a .png/.ico path or .ico bytes; None if it can't."""
    try:
        from PIL import Image, ImageTk
        import io
        image = Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)
        if hasattr(image, 'ico'):
            sizes = sorted(image.ico.sizes(), key=lambda s: s[0] * s[1])
            if sizes:
                image.size = sizes[-1]
        image.load()
        image = image.convert('RGBA').resize((px, px), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image, master=root)
    except Exception:            # noqa: BLE001 - no Pillow, or a broken icon
        pass
    if isinstance(source, str) and source.lower().endswith('.png'):
        try:
            image = tk.PhotoImage(master=root, file=source)
            factor = max(1, image.width() // px)
            return image.subsample(factor) if factor > 1 else image
        except tk.TclError:
            pass
    return None


def pick_file(parent: tk.Misc, callback: Callable[[Optional[str]], None]) -> None:
    """Spark's own file dialog (spark-pick, Spark Files through the desktop portal), else Tk's. Doesn't block."""
    start = os.path.expanduser('~/Downloads')
    if not os.path.isdir(start):
        start = os.path.expanduser('~')
    if picker():
        try:
            proc = subprocess.Popen(
                [picker(), '--title', t('pick.file'), '--getopenfilename', start,
                 f"*.exe *.msi *.EXE *.MSI|{t('pick.filter')}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            proc = None
        if proc is not None:
            def poll():                       # the window stays responsive meanwhile
                if proc.poll() is None:
                    parent.after(150, poll)
                    return
                path = proc.stdout.read().strip() if proc.returncode == 0 else ''
                proc.stdout.close()
                callback(path or None)
            parent.after(150, poll)
            return
    from tkinter import filedialog
    path = filedialog.askopenfilename(parent=parent, title=t('pick.file'), initialdir=start,
                                      filetypes=[(t('pick.filter'), '*.exe *.msi *.EXE *.MSI')])
    callback(path or None)


# ─── Work in a thread ────────────────────────────────────────

class Worker:
    """Runs fn(report=..., cancel=...) in a thread; on_report/on_done/on_error run in Tk."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.q: 'queue.Queue[tuple]' = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False

    def run(self, fn: Callable, on_done: Callable, on_error: Callable[[Problem], None],
            on_report: Optional[Callable] = None) -> None:
        self.cancel = threading.Event()
        self.busy = True
        cancel = self.cancel

        def report(stage: str, **kw) -> None:
            self.q.put(('report', stage, kw))

        def target():
            try:
                result = fn(report=report, cancel=cancel)
                self.q.put(('done', result))
            except apps.RunError as exc:
                self.q.put(('error', exc.problem))
            except Exception as exc:     # noqa: BLE001 - never a stack trace in the window
                log.error("unexpected error: %s\n%s", exc, traceback.format_exc())
                self.q.put(('error', Problem('error.unexpected', {'detail': str(exc)})))

        threading.Thread(target=target, daemon=True).start()
        self._poll(on_done, on_error, on_report)

    def ask(self, fn: Callable[[], object]) -> object:
        """From the thread: run fn in Tk and wait for its answer (a dialog)."""
        done = threading.Event()
        box: List[object] = [None]

        def call():
            def answer(value):
                box[0] = value
                done.set()
            fn(answer)

        self.q.put(('call', call))
        done.wait()
        return box[0]

    def _poll(self, on_done, on_error, on_report):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == 'report' and on_report:
                    on_report(item[1], **item[2])
                elif kind == 'call':
                    item[1]()
                elif kind == 'done':
                    self.busy = False
                    on_done(item[1])
                    return
                elif kind == 'error':
                    self.busy = False
                    on_error(item[1])
                    return
        except queue.Empty:
            pass
        try:
            self.root.after(60, lambda: self._poll(on_done, on_error, on_report))
        except tk.TclError:
            pass


# ─── The window ──────────────────────────────────────────────

class Window:
    def __init__(self, file: Optional[str] = None, error: Optional[tuple] = None):
        self.exit_code = 0
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
        self.glitch = Glitch(self.root, enabled=not reduced_motion())
        self.worker = Worker(self.root)
        self.images: Dict[str, tk.PhotoImage] = {}
        self.view: Optional[tk.Frame] = None
        self.from_list = False
        self._build()
        if error:
            self.show_error(*error)
        elif file:
            self.show_chooser(file)
        else:
            self.show_list()
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)

    # look helpers
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size_: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size_, "bold" if bold else "normal")

    def tkfont(self, size_: int, bold: bool = True) -> tkfont.Font:
        key = (size_, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size_,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def label(self, parent, text='', size_=10, bold=False, fg=None, bg=None, wrap=0, **kw):
        return tk.Label(parent, text=text, font=self.font(size_, bold), fg=fg or T["text"],
                        bg=bg or parent.cget('bg'), justify='left', anchor='w',
                        wraplength=self.px(wrap) if wrap else 0, **kw)

    def button(self, parent, text, command, variant='ghost'):
        return WolkButton(parent, text, command, self.font(9), variant=variant,
                          padx=self.px(12), pady=self.px(5))

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(t('status.crashed'), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(560), px(380))
        for path in (os.path.join(HERE, 'icons', f'{APP_SLUG}-64.png'),
                     os.path.join(HERE, 'icons', f'{APP_SLUG}-256.png')):
            if os.path.isfile(path):
                try:
                    self._icon = tk.PhotoImage(master=root, file=path)
                    root.iconphoto(True, self._icon)
                    break
                except tk.TclError:
                    pass
        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK RUN", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        self.status_idle()
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(px(760), int(sw * 0.8))}x{min(px(560), int(sh * 0.85))}")
        root.bind("<Escape>", lambda _e: self.escape())

    def status_idle(self):
        found = winemod.installed()
        if found is None:
            self.set_status(t('status.missing'), T["muted"])
        elif found.version == 'custom':
            self.set_status(t('status.custom'), T["gold"])
        else:
            self.set_status("● " + t('status.ready', version=found.version), T["accent"])

    def set_status(self, text: str, colour: str = None):
        self.status.config(text=text.upper(), fg=colour or T["accent"])

    def clear(self) -> tk.Frame:
        if self.view is not None:
            self.view.destroy()
        for seq in ("<Return>", "<Delete>"):
            self.root.unbind(seq)
        self.listing = False
        self.view = tk.Frame(self.body, bg=T["bg"])
        self.view.pack(fill="both", expand=True)
        return self.view

    def escape(self):
        if self.worker.busy:
            return
        if self.from_list:
            self.show_list()
        else:
            self.close()

    def close(self):
        if self.worker.busy:
            self.worker.cancel.set()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def icon_for(self, key: str, source, px_: int) -> Optional[tk.PhotoImage]:
        cache = f"{key}@{px_}"
        if cache not in self.images:
            image = load_image(self.root, source, px_) if source else None
            if image is None:
                return None
            self.images[cache] = image
        return self.images[cache]

    def placeholder(self, parent, px_: int) -> tk.Canvas:
        c = tk.Canvas(parent, width=px_, height=px_, bg=parent.cget('bg'), highlightthickness=0)
        c.create_rectangle(1, 1, px_ - 2, px_ - 2, outline=T["line2"], fill=T["tile"])
        c.create_text(px_ / 2, px_ / 2, text="EXE", fill=T["dim"], font=self.font(7))
        return c

    # ── the chooser: Run once / Install as an app ──

    def show_chooser(self, file: str, from_list: bool = False):
        self.from_list = from_list
        file = os.path.abspath(file)
        try:
            info = apps.check_file(file)
        except apps.RunError as exc:
            self.show_error(os.path.basename(file), exc.problem, '')
            return
        v = self.clear()
        px = self.px
        panel = GlitchPanel(v, T["panel"])
        panel.pack(fill="x")
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="x", padx=px(14), pady=px(12))
        icon = self.icon_for(file, info.icon_ico(), px(48))
        (tk.Label(inner, image=icon, bg=T["panel"]) if icon else
         self.placeholder(inner, px(48))).pack(side="left", anchor="n")
        text = tk.Frame(inner, bg=T["panel"])
        text.pack(side="left", fill="x", expand=True, padx=(px(12), 0))
        title = info.product or os.path.basename(file)
        self.label(text, title, 12, True, wrap=520).pack(anchor="w")
        if info.kind == 'msi':
            kind = t('file.kind.msi')
        elif info.looks_like_installer:
            kind = t('file.kind.installer', maker=info.installer) if info.installer else \
                t('file.kind.installer_plain')
        else:
            kind = t('file.kind.dotnet') if info.dotnet else t('file.kind.program')
        bits = [kind]
        if info.kind == 'pe':
            bits.append(t('file.bits', bits=info.bits))
        if info.publisher:
            bits.append(t('file.by', publisher=info.publisher))
        if info.version:
            bits.append(t('file.version', version=info.version))
        self.label(text, ' · '.join(bits), 9, fg=T["muted"], wrap=520).pack(anchor="w",
                                                                            pady=(px(2), 0))
        self.label(text, f"{os.path.basename(file)} · {size(info.size, 1)}", 9,
                   fg=T["dim"], wrap=520).pack(anchor="w", pady=(px(2), 0))

        notes = tk.Frame(v, bg=T["bg"])
        notes.pack(fill="x", pady=(px(12), 0))
        installs = info.looks_like_installer
        for key in ('file.install_hint' if installs else 'file.install_hint_program',
                    'file.run_once_hint'):
            self.label(notes, t(key), 9, fg=T["text"], wrap=640).pack(anchor="w",
                                                                    pady=(0, px(4)))
        need = winemod.needs_download()
        if need:
            self.label(notes, t('file.first_time', names=' + '.join(d.name for d in need),
                                size=size(sum(d.size for d in need))), 9, fg=T["gold"],
                       wrap=640).pack(anchor="w", pady=(px(4), px(4)))
        self.label(notes, t('file.games'), 9, fg=T["muted"], wrap=640).pack(anchor="w")

        self.progress_box = tk.Frame(v, bg=T["bg"])
        self.progress_box.pack(fill="x", pady=(px(14), 0))
        bar = tk.Frame(v, bg=T["bg"])
        bar.pack(side="bottom", fill="x")
        install = self.button(bar, t('btn.install'), lambda: self.do_install(file, info),
                              'primary')
        install.pack(side="left")
        self.button(bar, t('btn.run_once'), lambda: self.do_run_once(file)).pack(
            side="left", padx=(px(8), 0))
        self.button(bar, t('btn.cancel'), self.escape).pack(side="right")
        self.action_bar = bar
        install.label.focus_set()
        self.root.bind("<Return>", lambda _e: self.do_install(file, info)
                       if not self.worker.busy else None)
        self.glitch.now(self.title)

    def _progress_view(self) -> None:
        for child in self.action_bar.winfo_children():
            child.destroy()
        self.root.unbind("<Return>")
        box = self.progress_box
        for child in box.winfo_children():
            child.destroy()
        self.step = self.label(box, '', 10, True, fg=T["accent"], wrap=640)
        self.step.pack(anchor="w")
        self.bar = Strip(box, height=self.px(4))
        self.bar.pack(fill="x", pady=(self.px(8), self.px(4)))
        self.bar.draw(fraction=0.0)
        self.detail = self.label(box, '', 9, fg=T["muted"], wrap=640)
        self.detail.pack(anchor="w")
        self.cancel_button = self.button(self.action_bar, t('btn.cancel'),
                                         lambda: self.worker.cancel.set())
        self.cancel_button.pack(side="right")

    def on_report(self, stage: str, **kw) -> None:
        names = {'wine': sources.WINE.name, 'mono': sources.MONO.name,
                 'dxvk': sources.DXVK.name}
        if stage.startswith('progress.'):
            _, item, what = stage.split('.')
            done, total = kw.get('done', 0), kw.get('total', 0) or 1
            self.bar.draw(fraction=done / total)
            if what == 'download':
                self.detail.config(text=t('progress.download', name=names.get(item, item),
                                          done=size(done), total=size(total)))
            else:
                self.detail.config(text=t('progress.unpack', name=names.get(item, item)))
            return
        self.step.config(text=t('step.' + stage, **{k: str(v) for k, v in kw.items()}))
        self.detail.config(text='')
        self.bar.draw(fraction=0.0 if stage in ('setup',) else 1.0)
        self.glitch.now(self.title, self.strip)

    def do_install(self, file: str, info: pe.PEInfo) -> None:
        if self.worker.busy:
            return
        self._progress_view()
        name = info.product or os.path.basename(file)
        self.set_status(t('status.installing'), T["gold"])

        def choose(found):
            return self.worker.ask(lambda answer: PickDialog(self, found, answer))

        def work(report, cancel):
            return apps.install(file, report, choose=choose, cancel=cancel)

        self.worker.run(work, self.installed,
                        lambda p: self.show_error(name, p, '', install=True), self.on_report)

    def installed(self, app: apps.App) -> None:
        self.status_idle()
        v = self.clear()
        px = self.px
        panel = GlitchPanel(v, T["panel"])
        panel.pack(fill="x")
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="x", padx=px(14), pady=px(14))
        icon = self.icon_for(app.slug, app.icon, px(48))
        (tk.Label(inner, image=icon, bg=T["panel"]) if icon else
         self.placeholder(inner, px(48))).pack(side="left")
        self.label(inner, t('done.installed', name=app.name), 11, True, bg=T["panel"],
                   wrap=520).pack(side="left", padx=(px(12), 0))
        bar = tk.Frame(v, bg=T["bg"])
        bar.pack(side="bottom", fill="x")
        opener = self.button(bar, t('btn.open_now'), lambda: self.open_app(app), 'primary')
        opener.pack(side="left")
        self.button(bar, t('btn.close'), self.escape).pack(side="right")
        opener.label.focus_set()
        self.root.bind("<Return>", lambda _e: self.open_app(app))
        self.glitch.now(self.title, panel, self.mark, strong=True)

    def do_run_once(self, file: str) -> None:
        if self.worker.busy:
            return
        self._progress_view()
        name = os.path.basename(file)

        def work(report, cancel):
            launch = apps.run_once(file, report=report, cancel=cancel)
            report('starting', name=name)
            problem = launch.watch()
            if problem:
                raise apps.RunError(problem)
            return launch

        self.worker.run(work, lambda launch: self.running(launch, name),
                        lambda p: self.show_error(name, p, winemod.app_log('run-once')),
                        self.on_report)

    def running(self, launch: 'apps.Launch', name: str) -> None:
        """It started and survived the first seconds. From the list: back to the list. From a
        double-click: hide, and come back only to explain a crash."""
        self.status_idle()
        if self.from_list:
            self.show_list(message=t('done.running', name=name))
            return
        self.root.withdraw()

        def work(report, cancel):
            code = launch.wait()
            problem = launch.problem(quick=False)
            return problem if problem and code != 0 else None

        def after(problem):
            if problem:
                self.root.deiconify()
                self.show_error(name, problem, launch.log_path)
            else:
                self.close()

        self.worker.run(work, after, after)

    def open_app(self, app: apps.App) -> None:
        if self.worker.busy:
            return

        def work(report, cancel):
            launch = apps.open_app(app, report=report)
            problem = launch.watch(4)
            if problem:
                raise apps.RunError(problem)
            return launch

        self.set_status(t('step.starting', name=app.name), T["gold"])

        def started(_launch):
            self.status_idle()
            if self.from_list or self.view is not None and getattr(self, 'listing', False):
                self.show_list(message=t('done.running', name=app.name))
            else:
                self.close()

        self.worker.run(work, started,
                        lambda p: self.show_error(app.name, p, winemod.app_log(app.slug)))

    # ── errors ──

    def show_error(self, name: str, problem: Problem, log_path: str = '',
                   install: bool = False) -> None:
        self.status_idle()
        self.set_status(t('status.error'), T["pink"])
        v = self.clear()
        px = self.px
        panel = GlitchPanel(v, T["panel"])
        panel.pack(fill="x")
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="x", padx=px(14), pady=px(12))
        heading = GlitchText(inner, t('error.heading_install' if install else 'error.heading',
                                      name=name), self.tkfont(11), T["panel"], fg=T["pink"])
        heading.pack(anchor="w")
        self.label(inner, t(problem.key, **problem.values), 10, bg=T["panel"],
                   wrap=640).pack(anchor="w", pady=(px(8), 0))
        self.label(v, t('error.footer'), 9, fg=T["muted"], wrap=640).pack(anchor="w",
                                                                         pady=(px(12), 0))
        bar = tk.Frame(v, bg=T["bg"])
        bar.pack(side="bottom", fill="x")
        self.button(bar, t('btn.guide'), lambda: open_path(GUIDE_URL), 'primary').pack(
            side="left")
        if log_path and os.path.isfile(log_path):
            self.button(bar, t('btn.log'), lambda: open_path(log_path)).pack(
                side="left", padx=(px(8), 0))
        self.button(bar, t('btn.close'), self.escape).pack(side="right")
        self.exit_code = 1
        self.glitch.now(self.title, heading, panel, self.mark, strong=True)

    # ── the list of installed apps ──

    def show_list(self, message: str = '') -> None:
        self.from_list = False
        self.status_idle()
        v = self.clear()
        self.listing = True
        px = self.px
        top = tk.Frame(v, bg=T["bg"])
        top.pack(fill="x")
        self.label(top, t('apps.heading').upper(), 8, True, fg=T["muted"]).pack(
            side="left", anchor="s")
        self.button(top, t('btn.run_file'), self.run_file).pack(side="right")

        panel = GlitchPanel(v, T["panel"])
        panel.pack(fill="both", expand=True, pady=(px(8), 0))
        self.list_panel = panel
        self.apps = apps.all_apps()
        self.selected: Optional[str] = self.apps[0].slug if self.apps else None
        self.rows: Dict[str, tuple] = {}
        if not self.apps:
            self.label(panel.inner, t('apps.empty'), 10, fg=T["muted"], bg=T["panel"],
                       wrap=560).pack(anchor="w", padx=px(16), pady=px(16))
        else:
            canvas = tk.Canvas(panel.inner, bg=T["panel"], highlightthickness=0, bd=0)
            canvas.pack(side="left", fill="both", expand=True)
            rows = tk.Frame(canvas, bg=T["panel"])
            window = canvas.create_window(0, 0, window=rows, anchor="nw")
            rows.bind("<Configure>", lambda _e: canvas.configure(
                scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

            def wheel(event):
                step = -1 if (getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0) \
                    else 1
                try:
                    canvas.yview_scroll(step, 'units')
                except tk.TclError:          # the list was replaced by another view
                    pass
            for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
                canvas.bind_all(seq, wheel)
            for app in self.apps:
                self._row(rows, app)
            self._measure_sizes()

        bar = tk.Frame(v, bg=T["bg"])
        bar.pack(fill="x", pady=(px(10), 0))
        self.b_open = self.button(bar, t('btn.open'), self._open_selected, 'primary')
        self.b_open.pack(side="left")
        self.b_folder = self.button(bar, t('btn.folder'), self._folder_selected)
        self.b_folder.pack(side="left", padx=(px(8), 0))
        self.b_options = self.button(bar, t('btn.options'), self._options_selected)
        self.b_options.pack(side="left", padx=(px(8), 0))
        self.b_remove = self.button(bar, t('btn.uninstall'), self._remove_selected, 'danger')
        self.b_remove.pack(side="right")
        foot = tk.Frame(v, bg=T["bg"])
        foot.pack(fill="x", pady=(px(8), 0))
        self.message = self.label(foot, message, 9, fg=T["accent"], wrap=640)
        self.message.pack(anchor="w")
        self.label(foot, t('apps.games'), 9, fg=T["dim"]).pack(anchor="w")
        self._paint_rows()
        self.root.bind("<Return>", lambda _e: self._open_selected())
        self.root.bind("<Delete>", lambda _e: self._remove_selected())
        if message:
            self.glitch.now(self.title, panel)

    def _row(self, parent, app: apps.App):
        px = self.px
        row = tk.Frame(parent, bg=T["panel"], cursor="hand2")
        row.pack(fill="x")
        edge = tk.Frame(row, bg=T["panel"], width=px(3))
        edge.pack(side="left", fill="y")
        icon = self.icon_for(app.slug, app.icon, px(32))
        pic = tk.Label(row, image=icon, bg=T["panel"]) if icon else self.placeholder(row, px(32))
        pic.pack(side="left", padx=(px(10), px(10)), pady=px(8))
        col = tk.Frame(row, bg=T["panel"])
        col.pack(side="left", fill="x", expand=True)
        name = self.label(col, app.name, 11, True, bg=T["panel"])
        name.pack(anchor="w")
        meta = self.label(col, self._meta(app, None), 9, fg=T["muted"], bg=T["panel"])
        meta.pack(anchor="w")
        tk.Frame(parent, bg=T["line"], height=1).pack(fill="x")
        widgets = (row, edge, pic, col, name, meta)
        for w in widgets:
            w.bind("<Button-1>", lambda _e, s=app.slug: self._select(s))
            w.bind("<Double-Button-1>", lambda _e, s=app.slug: (self._select(s),
                                                                self._open_selected()))
        self.rows[app.slug] = widgets

    def _meta(self, app: apps.App, used: Optional[int]) -> str:
        windows = t('win.label', v=t('win.' + app.windows))
        if used is None:
            return t('apps.meta_nosize', windows=windows, added=app.added or '?')
        return t('apps.meta', windows=windows, size=size(used), added=app.added or '?')

    def _measure_sizes(self):
        """Folder sizes in a thread (a big prefix takes a moment); only Tk's own thread
        touches the window, by polling the results while the thread runs."""
        found = list(self.apps)
        results: 'queue.Queue[tuple]' = queue.Queue()

        def work():
            for app in found:
                results.put((app, apps.disk_use(app)))
        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def poll():
            try:
                while True:
                    self._set_size(*results.get_nowait())
            except queue.Empty:
                pass
            if thread.is_alive() or not results.empty():
                try:
                    self.root.after(100, poll)
                except tk.TclError:
                    pass
        self.root.after(100, poll)

    def _set_size(self, app: apps.App, used: int):
        app.used = used
        widgets = self.rows.get(app.slug)
        if widgets:
            try:
                widgets[5].config(text=self._meta(app, used))
            except tk.TclError:
                pass

    def _select(self, slug: str):
        self.selected = slug
        self._paint_rows()

    def _paint_rows(self):
        for slug, widgets in self.rows.items():
            on = slug == self.selected
            bg = T["hover"] if on else T["panel"]
            for w in widgets:
                try:
                    w.config(bg=bg)
                except tk.TclError:
                    pass
            widgets[1].config(bg=T["accent"] if on else bg)
        have = self.selected is not None
        for b in (self.b_open, self.b_folder, self.b_options, self.b_remove):
            b.set_enabled(have)

    def _current(self) -> Optional[apps.App]:
        return next((a for a in getattr(self, 'apps', []) if a.slug == self.selected), None)

    def _open_selected(self):
        app = self._current()
        if app:
            self.from_list = True
            self.open_app(app)

    def _folder_selected(self):
        app = self._current()
        if app:
            open_path(app.drive_c)

    def _options_selected(self):
        app = self._current()
        if app:
            OptionsDialog(self, app)

    def _remove_selected(self):
        app = self._current()
        if app and not self.worker.busy:
            ConfirmDialog(self, app)

    def run_file(self):
        def chosen(path):
            if path:
                self.show_chooser(path, from_list=True)
        pick_file(self.root, chosen)

    def note(self, text: str, colour: str = None) -> None:
        try:
            self.message.config(text=text, fg=colour or T["accent"])
            self.glitch.now(self.title, self.list_panel)
        except (tk.TclError, AttributeError):
            pass


# ─── Dialogs ─────────────────────────────────────────────────

class Dialog(tk.Toplevel):
    def __init__(self, ui: Window, title: str):
        super().__init__(ui.root, bg=T["bg"])
        self.ui = ui
        self.title(title)
        self.transient(ui.root)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self.body = tk.Frame(self, bg=T["bg"])
        self.body.pack(fill="both", expand=True, padx=ui.px(16), pady=ui.px(14))

    def present(self):
        self.update_idletasks()
        root = self.ui.root
        x = root.winfo_rootx() + max(0, (root.winfo_width() - self.winfo_reqwidth()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    def cancel(self):
        self.destroy()


class ConfirmDialog(Dialog):
    def __init__(self, ui: Window, app: apps.App):
        super().__init__(ui, t('rm.heading', name=app.name))
        px = ui.px
        heading = GlitchText(self.body, t('rm.heading', name=app.name), ui.tkfont(11),
                             T["bg"], fg=T["pink"])
        heading.pack(anchor="w")
        used = getattr(app, 'used', None)
        ui.label(self.body, t('rm.body', size=size(used) if used is not None else '?'), 10,
                 wrap=460).pack(anchor="w", pady=(px(8), px(14)))
        bar = tk.Frame(self.body, bg=T["bg"])
        bar.pack(fill="x")
        remove = ui.button(bar, t('btn.remove'), lambda: self.remove(app), 'danger')
        remove.pack(side="left")
        ui.button(bar, t('btn.cancel'), self.cancel).pack(side="right")
        self.present()
        ui.glitch.now(heading)

    def remove(self, app: apps.App):
        self.destroy()
        ui = self.ui

        def work(report, cancel):
            apps.uninstall(app)
            return app

        ui.worker.run(work, lambda a: ui.show_list(message=t('rm.done', name=a.name)),
                      lambda p: ui.show_error(app.name, p, winemod.app_log(app.slug)))


class PickDialog(Dialog):
    """After an install that added several programs: which one the menu entry opens."""

    def __init__(self, ui: Window, found: List['apps.Candidate'], answer: Callable):
        super().__init__(ui, t('choose.heading'))
        self.answer, self.found = answer, found
        self.choice = 0
        px = ui.px
        GlitchText(self.body, t('choose.heading'), ui.tkfont(11), T["bg"]).pack(anchor="w")
        ui.label(self.body, t('choose.body'), 10, wrap=480).pack(anchor="w",
                                                                pady=(px(6), px(10)))
        self.rows = []
        for i, c in enumerate(found[:12]):
            row = tk.Label(self.body, font=ui.font(10, False), anchor='w', justify='left',
                           padx=px(8), pady=px(4), cursor='hand2', highlightthickness=1)
            row.pack(fill='x', pady=(0, px(2)))
            row.bind("<Button-1>", lambda _e, n=i: self.pick(n))
            row.bind("<Double-Button-1>", lambda _e, n=i: (self.pick(n), self.ok()))
            self.rows.append((row, c))
        bar = tk.Frame(self.body, bg=T["bg"])
        bar.pack(fill="x", pady=(px(12), 0))
        ui.button(bar, t('btn.choose'), self.ok, 'primary').pack(side="left")
        ui.button(bar, t('btn.cancel'), self.cancel).pack(side="right")
        self.bind("<Return>", lambda _e: self.ok())
        self.pick(0)
        self.present()

    def pick(self, n: int):
        self.choice = n
        for i, (row, c) in enumerate(self.rows):
            on = i == n
            row.config(text=("■ " if on else "□ ") + f"{c.name}\n   {c.path}",
                       bg=T["hover"] if on else T["panel"],
                       fg=T["accent"] if on else T["text"],
                       highlightbackground=T["line2"] if on else T["line"])

    def ok(self):
        chosen = self.found[self.choice]
        self.destroy()
        self.answer(chosen)

    def cancel(self):
        self.destroy()
        self.answer(None)


class OptionsDialog(Dialog):
    def __init__(self, ui: Window, app: apps.App):
        super().__init__(ui, t('opt.heading', name=app.name))
        self.app = app
        px = ui.px
        GlitchText(self.body, t('opt.heading', name=app.name), ui.tkfont(11), T["bg"]).pack(
            anchor="w")

        def micro(text):
            ui.label(self.body, text, 8, True, fg=T["muted"]).pack(anchor="w",
                                                                   pady=(px(12), px(4)))
        micro(t('opt.name'))
        self.name = tk.Entry(self.body, font=ui.font(10, False), bg=T["panel2"], fg=T["text"],
                             insertbackground=T["accent"], relief='flat', highlightthickness=1,
                             highlightbackground=T["line"], highlightcolor=T["accent"],
                             width=44)
        self.name.insert(0, app.name)
        self.name.pack(anchor="w", ipady=px(3))

        self.program = app.program
        if len(app.candidates) > 1:
            micro(t('opt.program'))
            self.prog_rows = []
            for c in app.candidates[:8]:
                row = tk.Label(self.body, font=ui.font(9, False), anchor='w', padx=px(6),
                               pady=px(2), cursor='hand2')
                row.pack(fill='x')
                row.bind("<Button-1>", lambda _e, p=c.get('path', ''): self.pick_program(p))
                self.prog_rows.append((row, c))
            self.pick_program(app.program)

        micro(t('opt.windows'))
        self.windows = app.windows
        Segmented(self.body, [(t('win.' + w), w) for w in winemod.WINDOWS_VERSIONS],
                  app.windows, lambda w: setattr(self, 'windows', w), ui.font(9)).pack(
            anchor="w")
        ui.label(self.body, t('opt.windows_hint'), 9, fg=T["muted"], wrap=460).pack(
            anchor="w", pady=(px(4), 0))

        micro(t('opt.dxvk'))
        self.dxvk = 'on' if app.dxvk else 'off'
        Segmented(self.body, [(t('opt.dxvk_off'), 'off'), (t('opt.dxvk_on'), 'on')], self.dxvk,
                  lambda d: setattr(self, 'dxvk', d), ui.font(9)).pack(anchor="w")
        ui.label(self.body, t('opt.dxvk_hint', size=size(sources.DXVK.size)), 9,
                 fg=T["muted"], wrap=460).pack(anchor="w", pady=(px(4), 0))

        self.status = ui.label(self.body, '', 9, fg=T["accent"], wrap=460)
        self.status.pack(anchor="w", pady=(px(10), 0))
        bar = tk.Frame(self.body, bg=T["bg"])
        bar.pack(fill="x", pady=(px(10), 0))
        self.save_button = ui.button(bar, t('btn.save'), self.save, 'primary')
        self.save_button.pack(side="left")
        ui.button(bar, t('btn.run_in'), self.run_in).pack(side="left", padx=(px(8), 0))
        ui.button(bar, t('btn.close'), self.cancel).pack(side="right")
        self.present()

    def pick_program(self, path: str):
        self.program = path
        for row, c in self.prog_rows:
            on = c.get('path') == path
            row.config(text=("■ " if on else "□ ") + str(c.get('name', '')),
                       bg=T["hover"] if on else T["bg"], fg=T["accent"] if on else T["text"])

    def save(self):
        ui, app = self.ui, self.app
        if ui.worker.busy:
            return
        name, program = self.name.get().strip(), self.program
        windows, dxvk = self.windows, self.dxvk == 'on'
        self.save_button.set_enabled(False)
        self.status.config(text='…', fg=T["muted"])

        def work(report, cancel):
            if name and name != app.name:
                apps.rename(app, name)
            if program != app.program:
                args = next((c.get('arguments', '') for c in app.candidates
                             if c.get('path') == program), '')
                apps.set_program(app, program, args)
            if windows != app.windows:
                apps.set_windows(app, windows)
            if dxvk != app.dxvk:
                apps.set_dxvk(app, dxvk, report)
            return app

        def done(_app):
            try:
                self.save_button.set_enabled(True)
                self.status.config(text=t('opt.saved'), fg=T["accent"])
            except tk.TclError:
                pass
            ui.show_list(message=t('opt.saved'))

        def failed(problem):
            try:
                self.save_button.set_enabled(True)
                self.status.config(text=t(problem.key, **problem.values), fg=T["pink"])
            except tk.TclError:
                pass

        def progress(stage, **kw):
            if stage.startswith('progress.'):
                total = kw.get('total') or 1
                self.status.config(text=t('step.dxvk') + f" {kw.get('done', 0) * 100 // total}%",
                                   fg=T["gold"])

        ui.worker.run(work, done, failed, progress)

    def run_in(self):
        """Run another installer (a runtime the program needs) inside this app's folder."""
        ui, app = self.ui, self.app

        def chosen(path):
            if not path:
                return

            def work(report, cancel):
                apps.check_file(path)
                wine = apps.ensure_wine(report, cancel)
                proc = wine.start(app.prefix, os.path.abspath(path),
                                  log_path=winemod.app_log(app.slug))
                launch = apps.Launch(proc, winemod.app_log(app.slug), wine.has_mono,
                                     os.path.basename(path))
                problem = launch.watch()
                if problem:
                    raise apps.RunError(problem)
                return launch

            self.status.config(text=t('step.starting', name=os.path.basename(path)),
                               fg=T["gold"])
            ui.worker.run(work, lambda _l: self.status.config(
                text=t('done.running', name=os.path.basename(path)), fg=T["accent"]),
                lambda p: self.status.config(text=t(p.key, **p.values), fg=T["pink"]))
        pick_file(self, chosen)


# ─── Entry points ────────────────────────────────────────────

def run_window(file: Optional[str]) -> int:
    try:
        ui = Window(file)
    except tk.TclError as exc:
        print(f"{APP_SLUG}: {t('error.no_display')} ({exc})")
        return 1
    ui.root.mainloop()
    return ui.exit_code


def show_error(name: str, problem: Problem, log_path: str = '', install: bool = False) -> None:
    ui = Window(error=(name, problem, log_path, install))
    ui.root.mainloop()


def picker():
    """The file dialog to run: spark-pick (Spark Files' picker, through the desktop portal), or
    kdialog on a Plasma machine that doesn't have spark-pick. None: use Tk's own dialog."""
    return shutil.which('spark-pick') or shutil.which('kdialog')
