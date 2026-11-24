"""The window, the once-a-second loop, End task, and --bench."""

import os
import re
import shutil
import subprocess
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, END_GRACE_S, HISTORY, INTERVAL_MS, UNFOCUSED_INTERVAL_MS, VERSION
from . import core
from .core import load_json, log, reduced_motion, save_json
from .desktop import find_icon
from .ender import ENDED, FAILED, FORCED, PARTLY, RUNNING, Ender
from .instance import Listener
from .procs import ProcSampler
from .source import Source, listdir
from .system import SystemSampler
from .text import t
from .ui import Icons, TabBar, style_tables
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, Mark, Strip

TABS = ('apps', 'performance', 'startup', 'details', 'logs', 'system')


# ─── The window ───────────────────────────────────────────────

def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_MONITOR_SCALE')
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
                 os.path.join(here, 'icons', f'{APP_SLUG}-256.png')):
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


class _Fill:
    """append() on a history deque that adds `steps` points, a straight line from the last."""

    def __init__(self, dq: Deque[Optional[float]], steps: int):
        self.dq, self.steps = dq, steps

    def append(self, value: Optional[float]):
        dq = self.dq
        prev = dq[-1] if dq else None
        if self.steps > 1 and prev is not None and value is not None:
            for k in range(1, self.steps):
                dq.append(prev + (value - prev) * k / self.steps)
        elif self.steps > 1:
            for _ in range(self.steps - 1):
                dq.append(value)
        dq.append(value)


class _History:
    def __init__(self, hist: Dict[str, Deque[Optional[float]]], steps: int):
        self.hist, self.steps = hist, steps

    def __getitem__(self, key: str) -> _Fill:
        return _Fill(self.hist[key], self.steps)


class App:
    def __init__(self, src: Optional[Source] = None, tab: Optional[str] = None):
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.src = src or Source()
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
        style_tables(self.root, self.font(9, False), self.font(8), self.px(24))
        self.icons = Icons(self.root, self.px(18), lambda name: find_icon(self.src, name))

        self.system = SystemSampler(self.src)
        self.system.sample(time.monotonic())
        self.procs = ProcSampler(self.src, threads=self.system.threads or os.cpu_count() or 1)
        self.hist: Dict[str, Deque[Optional[float]]] = defaultdict(lambda: deque(maxlen=HISTORY))
        self.ending: Optional[Ender] = None
        self.views: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.visible = True
        self.focused = True               # no focus events (no window manager) counts as focused
        self._last_sample: Optional[float] = None
        self.hidden_at: Optional[float] = None
        self._tick_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self.first_paint: Optional[float] = None
        self.cost = {'system': 0.0, 'procs': 0.0, 'view': 0.0, 'samples': 0}
        self._build()

        wanted = tab if tab in TABS else self.settings.get('tab')
        self.show(wanted if wanted in TABS else 'apps', glitch=False)
        self.root.deiconify()
        self.root.bind('<Map>', self._mapped, add='+')
        self.root.bind('<Unmap>', self._unmapped, add='+')
        self.root.bind('<FocusIn>', self._focus_in, add='+')
        self.root.bind('<FocusOut>', self._focus_out, add='+')
        self.glitch.add(self.title, self.mark, self.strip)
        self.listener = Listener(self.root, self.bring_to_front)
        # CPU % needs two samples; take the second sooner than the usual second
        self._tick_id = self.root.after(500, self._tick)

    # look helpers
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
        self.set_status(t('status.crashed'), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(720), px(480))
        icon = load_icon(root)
        if icon is not None:
            root.iconphoto(True, icon)
            self._icon = icon

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK MONITOR", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        self._status_idle()
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.tabs = TabBar(root, [(k, t(f'tab.{k}')) for k in TABS], self.show, self.font(9),
                           px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)

        root.bind("<KeyPress>", self._key)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(px(1000), int(sw * 0.8)), min(px(680), int(sh * 0.8))
            root.geometry(f"{w}x{h}")
        root.bind('<Expose>', self._exposed, add='+')

    def _exposed(self, event):
        if self.first_paint is None and event.widget is self.root:
            self.first_paint = time.monotonic()

    # — tabs —
    def view(self, tab: str) -> tk.Frame:
        if tab not in self.views:
            if tab == 'apps':
                from .appsview import AppsView
                self.views[tab] = AppsView(self)
            elif tab == 'performance':
                from .perfview import PerfView
                self.views[tab] = PerfView(self)
            elif tab == 'startup':
                from .startupview import StartupView
                self.views[tab] = StartupView(self)
            elif tab == 'logs':
                from .logsview import LogsView
                self.views[tab] = LogsView(self)
            elif tab == 'system':
                from .systemview import SystemView
                self.views[tab] = SystemView(self)
            else:
                from .detailsview import DetailsView
                self.views[tab] = DetailsView(self)
        return self.views[tab]

    def show(self, tab: str, glitch: bool = True):
        if tab == self.tab:
            return
        old = self.views.get(self.tab) if self.tab else None
        if old is not None:
            old.pack_forget()
            if hasattr(old, 'on_hide'):
                old.on_hide()
        self.tab = tab
        self.settings['tab'] = tab
        self.tabs.select(tab)
        view = self.view(tab)
        view.pack(fill="both", expand=True)
        if hasattr(view, 'on_show'):
            view.on_show()
        if tab in ('apps', 'details') and (not self.procs.procs or
                                           time.monotonic() - (self.procs.prev_time or 0) > 1.5):
            self.procs.sample(time.monotonic(), gpu=tab == 'apps')
        if tab == 'performance':
            self.system.find_sensors()
        view.refresh()
        if glitch:
            self.glitch.now(self.title)

    # — the loop —
    def _tick(self):
        self._tick_id = None
        if not self.visible:
            return
        if self.root.state() == 'iconic':
            self._pause()
            return
        started = time.monotonic()
        self.sample()
        self.refresh()
        took = time.monotonic() - started
        step = INTERVAL_MS if self.focused else UNFOCUSED_INTERVAL_MS
        delay = max(100, step - int(took * 1000))
        self._tick_id = self.root.after(delay, self._tick)

    def sample(self):
        now = time.monotonic()
        a = time.perf_counter()
        snap = self.system.sample(now, full=self.tab == 'performance')
        self.procs.threads = self.system.threads or 1
        b = time.perf_counter()
        if self.tab in ('apps', 'details'):
            self.procs.sample(now, gpu=self.tab == 'apps')
        c = time.perf_counter()
        # Each point of history is one second. When the window is unfocused it samples every
        # few seconds, so the gap is filled with a straight line to the new value: the graphs
        # keep their 60 s width.
        steps = 1
        if self._last_sample is not None:
            steps = max(1, min(HISTORY, round((now - self._last_sample) / (INTERVAL_MS / 1000))))
        self._last_sample = now
        h = _History(self.hist, steps)
        h['cpu'].append(snap.cpu)
        for i in range(self.system.threads):
            h[f'cpu{i}'].append(snap.threads[i] if i < len(snap.threads) else None)
        h['mem'].append(snap.mem.percent)
        for i, g in enumerate(snap.gpus):
            h[f'gpu{i}'].append(g.busy)
            h[f'gpu{i}.vram'].append(100.0 * g.vram_used / g.vram_total
                                     if g.vram_used is not None and g.vram_total else None)
        for i, d in enumerate(snap.disks):
            h[f'disk{i}.active'].append(d.active)
            h[f'disk{i}.read'].append(d.read_bps)
            h[f'disk{i}.write'].append(d.write_bps)
        for i, n in enumerate(snap.nics):
            h[f'net{i}.rx'].append(n.rx_bps)
            h[f'net{i}.tx'].append(n.tx_bps)
        self.cost['system'] += b - a
        self.cost['procs'] += c - b
        self.cost['samples'] += 1

    def refresh(self):
        a = time.perf_counter()
        view = self.views.get(self.tab)
        if view is not None:
            view.refresh()
        self.cost['view'] += time.perf_counter() - a

    def _pause(self):
        if self.visible:
            self.visible = False
            self.hidden_at = time.monotonic()
            if self._tick_id:
                self.root.after_cancel(self._tick_id)
                self._tick_id = None
            log.info("hidden: sampling paused")

    def _focus_out(self, event):
        if event.widget is self.root:
            self.focused = False

    def _focus_in(self, event):
        if event.widget is not self.root or self.focused:
            return
        self.focused = True
        if self.visible and self._tick_id is not None:    # back to every second, now
            self.root.after_cancel(self._tick_id)
            self._tick_id = self.root.after(50, self._tick)

    def _unmapped(self, event):
        if event.widget is self.root:
            self._pause()

    def _mapped(self, event):
        if event.widget is not self.root or self.visible:
            return
        self.visible = True
        if self.hidden_at and time.monotonic() - self.hidden_at > 3:
            self.hist.clear()               # the graphs restart rather than draw a false line
        self.hidden_at = None
        self._last_sample = None
        if self._tick_id is None:
            self._tick_id = self.root.after(50, self._tick)

    def bring_to_front(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    # — status line —
    def _status_idle(self):
        self._status_id = None
        if self.src.fake:
            text, colour = t('status.test_data'), T["gold"]
        else:
            text, colour = t('status.watching'), T["accent"]
        self.status.config(text=f"● {text}", fg=colour)

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 4000):
        self.status.config(text=f"● {text}", fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(hold_ms, self._status_idle)

    # — End task —
    def end_processes(self, name: str, pids: List[int],
                      more: Optional[Callable[[], List[int]]] = None):
        if self.ending is not None:
            return
        if not self.src.can_signal():
            self.set_status(t('end.test_data'), T["gold"], hold_ms=5000)
            self.glitch.now(self.title, strong=True)
            return
        log.info("end task: %s, pids %s", name, pids[:50])
        self.ending = Ender(self.src, pids, grace=END_GRACE_S, more=more)
        self.ending.start()
        self.set_status(t('end.ending', name=name.upper()), T["gold"], hold_ms=60000)
        self.glitch.now(self.title)
        self._poll_end(name)

    def _poll_end(self, name: str):
        ender = self.ending
        if ender is None:
            return
        result = ender.poll()
        if result == RUNNING:
            self.root.after(200, lambda: self._poll_end(name))
            return
        self.ending = None
        message = {ENDED: t('end.ended', name=name),
                   FORCED: t('end.forced', name=name, secs=int(END_GRACE_S)),
                   FAILED: t('end.failed', name=name),
                   PARTLY: t('end.partly', name=name)}[result]
        log.info("end task: %s -> %s", name, result)
        bad = result in (FAILED, PARTLY)
        self.set_status(message.upper().rstrip('.'), T["pink"] if bad else T["accent"],
                        hold_ms=6000)
        self.glitch.now(self.title, strong=bad)
        if self.visible:
            self.sample()
            self.refresh()

    # — misc —
    def process_count(self) -> int:
        if self.procs.procs and time.monotonic() - (self.procs.prev_time or 0) < 2:
            return self.procs.totals()[0]
        return sum(1 for n in listdir(self.src.proc) if n.isdigit())

    def uptime(self) -> float:
        from .perfview import read_uptime
        return read_uptime(self.src.proc)

    def _key(self, event):
        k = event.keysym
        ctrl = bool(event.state & 0x4)
        if ctrl and k in ('1', '2', '3', '4', '5', '6'):
            self.show(TABS[int(k) - 1])
            return "break"
        if ctrl and k in ('Tab', 'ISO_Left_Tab'):
            step = -1 if (event.state & 0x1 or k == 'ISO_Left_Tab') else 1
            self.show(TABS[(TABS.index(self.tab) + step) % len(TABS)])
            return "break"
        if ctrl and k in ('w', 'W', 'q', 'Q'):
            self.close()
            return "break"
        if k == 'F5':
            view = self.views.get(self.tab)
            if hasattr(view, 'reload'):
                view.reload()
            self.sample()
            self.refresh()
            return "break"
        return None

    def close(self):
        for view in self.views.values():
            if hasattr(view, 'shutdown'):
                view.shutdown()
        for job in (self._tick_id, self._status_id, self.glitch._loop):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._tick_id = self._status_id = self.glitch._loop = None
        self.visible = False
        try:                                # glitch frames and other short timers still queued
            for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.after_cancel(job)
        except tk.TclError:
            pass
        if self.root.state() == 'normal':
            self.settings["geometry"] = self.root.geometry()
        self.settings["version"] = VERSION
        save_json('config.json', self.settings)
        self.listener.close()
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Measuring ────────────────────────────────────────────────

def bench(src: Source, seconds: float, fill: int, tab: str) -> int:
    """Open the window, report the time to first paint, then the CPU it uses over `seconds`
    of normal running. With --fill, start sleeping processes until there are that many."""
    children = []
    if fill:
        count = sum(1 for n in listdir(src.proc) if n.isdigit())
        sleeper = shutil.which('sleep')
        while sleeper and count < fill:
            children.append(subprocess.Popen([sleeper, str(int(seconds) + 60)]))
            count += 1
    app = App(src, tab=tab)
    age_at_paint: Optional[float] = None
    wait_until = time.monotonic() + 5
    while app.first_paint is None and time.monotonic() < wait_until:
        app.root.update()
    painted = time.monotonic()
    from .cli import process_age
    age_now = process_age()
    if age_now is not None:
        age_at_paint = age_now - (time.monotonic() - (app.first_paint or painted))
    from .cli import T0
    since_import = (app.first_paint or painted) - T0
    results: Dict[str, float] = {}

    def start_measuring():
        app.cost = {'system': 0.0, 'procs': 0.0, 'view': 0.0, 'samples': 0}
        results['t'] = time.monotonic()
        results['cpu'] = sum(os.times()[:2])
        app.root.after(int(seconds * 1000), stop)

    def stop():
        results['wall'] = time.monotonic() - results['t']
        results['used'] = sum(os.times()[:2]) - results['cpu']
        app.close()

    app.root.after(3000, start_measuring)    # let the first samples and icons settle
    app.run()
    for child in children:
        child.kill()
        child.wait()
    procs, kernel = app.procs.totals()
    n = max(1, app.cost['samples'])
    print(f"{APP_NAME} {VERSION} bench, tab: {tab}")
    if age_at_paint is not None:
        print(f"first paint:  {age_at_paint:.2f} s after the process started")
    print(f"first paint:  {since_import:.2f} s after the app's code was loaded")
    print(f"processes:    {procs} ({kernel} kernel threads), {len(app.procs.groups)} rows")
    if 'wall' in results:
        share = 100.0 * results['used'] / results['wall']
        print(f"cpu:          {share:.2f}% of one core over {results['wall']:.0f} s "
              f"({app.cost['samples']} samples)")
        print(f"per sample:   system {1000 * app.cost['system'] / n:.2f} ms, processes "
              f"{1000 * app.cost['procs'] / n:.2f} ms, table {1000 * app.cost['view'] / n:.2f} ms")
    return 0


