"""The window: header, three tabs (Setup, Recordings, Compare), the watch loop and the worker
threads.

Reading a recording and the setup check run on worker threads; results come back through a
queue that Tk's thread drains, so the window never waits. While the window is open it lists
MangoHud's output folder twice a second and alerts on a start or a stop (unless the background
watcher has the alert lock)."""

import os
import queue
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import (APP_CLASS, APP_NAME, APP_SLUG, VERSION, WATCH_INTERVAL_MS, core, library,
               mangohud, watch)
from .core import log, reduced_motion
from .text import t
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, Mark, Segmented, Strip

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS = ('setup', 'recordings', 'compare')


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux; Plasma publishes it as Xft.dpi."""
    forced = os.environ.get('SPARK_BENCH_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if shutil.which('xrdb'):
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


class App:
    def __init__(self, tab: str = 'recordings', runner: Optional[mangohud.Runner] = None,
                 systemctl=None, alerter: Optional[Callable[[str, str], None]] = None,
                 auto: bool = True):
        """runner, systemctl and alerter stand in for flatpak, systemctl and the sound and
        notification in tests. auto=False: no watch loop (tests drive poll() by hand)."""
        self.settings = core.load_settings()
        self.runner = runner or mangohud.run_command
        self.systemctl = systemctl or watch._systemctl
        self.alerter = alerter or self._alert
        self.auto = auto
        self.report: Optional[mangohud.Report] = None
        self.library = library.Library(self.settings, mangohud.choose_output_folder(
            self.settings, os.path.isdir(mangohud.steam_dir()), []))
        self.stats: Dict[str, object] = {}         # run id -> Stats, or an error string
        self.queue: "queue.Queue" = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix=APP_SLUG)
        self.watcher = watch.FolderWatcher([])
        self.lock = watch.AlertLock()
        self.live: Optional[Dict] = None           # the recording in progress
        self._timer: Optional[str] = None
        self._status_after: Optional[str] = None
        self.closed = False
        self.pending = 0

        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict = {}
        self.glitch = Glitch(self.root, enabled=not reduced_motion())
        self._style()
        self._build()
        from .views import CompareView, RecordingsView, SetupView
        self.views = {'setup': SetupView(self), 'recordings': RecordingsView(self),
                      'compare': CompareView(self)}
        self.tab = ''
        self.show(tab if tab in TABS else 'recordings')
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.check_setup()
        self.rescan()
        self._drain_after = self.root.after(50, self._drain)
        if self.auto:
            self._timer = self.root.after(WATCH_INTERVAL_MS, self._tick)

    # — look helpers —
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True):
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        row = self.tkfont(9, False).metrics('linespace') + self.px(8)
        style.configure("Spark.Treeview", background=T["panel"], fieldbackground=T["panel"],
                        foreground=T["text"], bordercolor=T["line"], lightcolor=T["panel"],
                        darkcolor=T["panel"], rowheight=row, font=self.font(9, False),
                        borderwidth=0)
        style.map("Spark.Treeview", background=[("selected", T["hover"])],
                  foreground=[("selected", T["accent"])])
        style.configure("Spark.Treeview.Heading", background=T["panel2"], foreground=T["muted"],
                        bordercolor=T["line"], lightcolor=T["panel2"], darkcolor=T["panel2"],
                        font=self.font(7), relief="flat", padding=(6, 4))
        style.map("Spark.Treeview.Heading", background=[("active", T["hover"])],
                  foreground=[("active", T["text"])])
        style.layout("Spark.Treeview", [("Spark.Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Spark.Vertical.TScrollbar", background=T["panel2"], troughcolor=T["bg"],
                        bordercolor=T["bg"], arrowcolor=T["muted"], lightcolor=T["panel2"],
                        darkcolor=T["panel2"], gripcount=0)
        style.map("Spark.Vertical.TScrollbar", background=[("active", T["line2"])])

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(t('status.crashed'), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(760), px(500))
        for path in (os.path.join(APP_DIR, 'icons', f'{APP_SLUG}-64.png'),
                     os.path.join(APP_DIR, 'icons', f'{APP_SLUG}-256.png')):
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
        self.title = GlitchText(col, "SPARK BENCH", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.tabs = Segmented(head, [(t('tab.' + k), k) for k in TABS], 'recordings',
                              self.show, self.font(8))
        self.tabs.pack(side="right", padx=(0, px(14)))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        root.bind("<F5>", lambda _e: self.refresh_all())
        root.bind("<Control-w>", lambda _e: self.close())
        root.bind("<Control-q>", lambda _e: self.close())
        for i, key in enumerate(TABS, 1):
            root.bind(f"<Control-Key-{i}>", lambda _e, k=key: self.show(k))
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(px(1100), int(sw * 0.9))}x{min(px(720), int(sh * 0.88))}")

    # — tabs —
    def show(self, tab: str):
        if tab == self.tab:
            return
        if self.tab:
            self.views[self.tab].pack_forget()
        self.tab = tab
        self.tabs.set(tab)
        self.views[tab].pack(fill="both", expand=True)
        self.views[tab].refresh()
        self.glitch.now(self.title)

    def refresh_all(self):
        self.check_setup()
        self.rescan()

    # — status line —
    def status_idle(self):
        self._status_after = None
        if self.live:
            return
        r = self.report
        if r is None:
            self.status.config(text="● " + t('status.checking'), fg=T["muted"])
        elif not r.ready:
            self.status.config(text="● " + t('status.setup_needed'), fg=T["gold"])
        else:
            key = mangohud.pretty_key(self.settings['hotkey']).upper()
            self.status.config(text="● " + t('status.ready', key=key,
                                             s=self.settings['duration']), fg=T["accent"])

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 6000):
        self.status.config(text="● " + text.upper(), fg=colour)
        if self._status_after:
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(hold_ms, self.status_idle)

    # — work on threads —
    def submit(self, tag: str, job: Callable, *args):
        def run():
            try:
                return tag, args, job(*args), None
            except Exception as exc:              # noqa: BLE001 - shown, not raised
                log.exception("%s failed", tag)
                return tag, args, None, exc

        self.pending += 1
        self.pool.submit(lambda: self.queue.put(run()))

    def _drain(self):
        if self.closed:
            return
        try:
            while True:
                tag, args, result, error = self.queue.get_nowait()
                self.pending -= 1
                self._done(tag, args, result, error)
        except queue.Empty:
            pass
        self._drain_after = self.root.after(50, self._drain)

    def wait_idle(self, timeout: float = 10.0) -> None:
        """Tests: run Tk until every job is back."""
        end = time.monotonic() + timeout
        while self.pending and time.monotonic() < end:
            self.root.update()
            time.sleep(0.02)
        self.root.update()

    def _done(self, tag, args, result, error):
        if tag == 'setup':
            if error is None:
                self.report = result
                self.library.output_folder = result.output_folder
                self.library.extra_watched = [f for f in result.output_folders
                                              if f != result.output_folder]
                self.watcher.set_folders(result.output_folders)
                self.rescan()
            self.status_idle()
            self.views['setup'].refresh()
        elif tag == 'stats':
            run_id = args[0].id
            self.stats[run_id] = result if error is None else str(error)
            self.views[self.tab].stats_ready(run_id)
        elif tag in ('fix', 'undo', 'layer', 'background'):
            self.views['setup'].action_done(tag, result, error)

    # — setup —
    def check_setup(self):
        self.submit('setup', mangohud.inspect, self.settings, self.runner)

    def save_settings(self):
        core.save_settings(self.settings)

    # — recordings —
    def rescan(self):
        """List the recordings again (first lines only) and read new ones on the workers."""
        before = {r.id: (r.size, r.mtime) for r in self.library.runs}
        runs = self.library.scan()
        for run in runs:
            if run.recording_now:
                continue
            if before.get(run.id) != (run.size, run.mtime) or run.id not in self.stats:
                self.stats.pop(run.id, None)
                self.submit('stats', self.library.stats, run)
        for view in self.views.values():
            view.runs_changed()

    def restat(self, run: library.Run):
        """After a trim changed: work its numbers out again."""
        self.stats.pop(run.id, None)
        self.submit('stats', self.library.stats, run)

    # — watching —
    def _tick(self):
        self._timer = None
        if self.closed:
            return
        self.poll()
        self._timer = self.root.after(WATCH_INTERVAL_MS, self._tick)

    def poll(self):
        events = self.watcher.poll()
        for kind, path in events:
            self.on_event(kind, path)
        if self.live:
            duration = max(1, int(self.settings.get('duration') or 90))
            elapsed = time.time() - self.live['start']
            left = duration - elapsed
            if left < -30:
                self.live = None          # no summary came: MangoHud stopped some other way
                self.strip.draw(fraction=1.0)
                self.status_idle()
                self.rescan()
            else:
                self.strip.draw(fraction=max(0.0, left / duration))
                self.status.config(text="● " + t('status.recording',
                                                 left=core.seconds(max(0, left))),
                                   fg=T["pink"])

    def on_event(self, kind: str, path: str):
        alerting = self.lock.try_take()
        log.info("%s: %s (alerting: %s)", kind, path, alerting)
        duration = int(self.settings.get('duration') or 90)
        if alerting:
            self.alerter(kind, *watch.message(kind, duration))
        if kind == watch.STARTED:
            self.live = {'path': path, 'start': time.time()}
            self.glitch.now(self.title, self.mark, strong=True)
        else:
            self.live = None
            self.strip.draw(fraction=1.0)
            self.set_status(t('status.saved'), T["accent"])
            self.glitch.now(self.title, self.mark, self.strip)
            self.root.after(300, self.rescan)

    def _alert(self, kind: str, title: str, body: str):
        if self.settings.get('sound', True):
            watch.play(kind)
        watch.notify(title, body)

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for after in (self._timer, getattr(self, '_drain_after', None), self._status_after):
            if after:
                try:
                    self.root.after_cancel(after)
                except tk.TclError:
                    pass
        self.lock.release()
        self.pool.shutdown(wait=False, cancel_futures=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass
