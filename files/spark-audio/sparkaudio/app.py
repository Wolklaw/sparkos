"""The window: header, tabs, and the three loops (PipeWire changes, meters, Scarlett polling)."""

import os
import re
import shutil
import subprocess
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Dict, List, Optional, Tuple

from . import APP_CLASS, APP_NAME, APP_SLUG, VERSION
from . import core
from .backend import make_backend
from .controls import Mark, TabBar
from .core import load_json, log, reduced_motion, save_json
from .eq import EqManager
from .instance import Listener
from .meter import MeterSet, MicTest
from .scarlett import Interface, default_runner, fake_runner, find_interfaces
from .text import t
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, Strip

TABS = ('outputs', 'inputs', 'apps', 'eq', 'scarlett')
METER_MS = 40
SCARLETT_MS = 2000


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux; the desktop publishes it as Xft.dpi."""
    forced = os.environ.get('SPARK_AUDIO_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True, timeout=3).stdout
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
    """The mono font, remembered between runs (listing every family is slow on some PCs)."""
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families), "TkFixedFont")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for size in (64, 256):
        path = os.path.join(here, 'icons', f'{APP_SLUG}-{size}.png')
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


class App:
    def __init__(self, fake_dir: Optional[str] = None, tab: Optional[str] = None):
        self.fake_dir = fake_dir
        self.fake = bool(fake_dir)
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
        self.settings = {} if self.fake else load_json('config.json')
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and self.settings.get("glitch", True) is not False)

        self.backend = make_backend(fake_dir)
        self.meters = MeterSet(fake=self.fake)
        self.mic = MicTest(lambda: self.backend.post(self._mic_changed), fake=self.fake)
        self.eqm = EqManager(fake=self.fake)
        if self.fake:
            self.eqm.conf_path = os.path.join(fake_dir, 'eq.conf.unused')
        self.scarlett: List[Interface] = []
        self.views: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.visible = True
        self._status_id: Optional[str] = None
        self._meter_id: Optional[str] = None
        self._scarlett_id: Optional[str] = None
        self._wanted: Dict[str, bool] = {}
        self._build()

        self.root.tk.createfilehandler(self.backend.wake_fd, tk.READABLE, self._woke)
        self.backend.start()
        self.show(tab if tab in TABS else (self.settings.get('tab') if self.settings.get('tab') in TABS
                                           and self.settings.get('tab') != 'scarlett' else 'outputs'),
                  glitch=False)
        self.root.deiconify()
        self.root.bind('<Map>', self._mapped, add='+')
        self.root.bind('<Unmap>', self._unmapped, add='+')
        self.glitch.add(self.title, self.mark, self.strip)
        for n in range(1, 6):
            self.root.bind(f'<Control-Key-{n}>', lambda _e, n=n: self._tab_number(n))
        self.root.bind('<Control-w>', lambda _e: self.close())
        self.listener = Listener(self.root, self.bring_to_front)
        self._meter_id = self.root.after(METER_MS, self._meter_tick)
        self._find_scarlett()

    def _tab_number(self, n: int) -> None:
        tabs = [k for k, _ in self._tab_list()]
        if n <= len(tabs):
            self.show(tabs[n - 1])

    # — look helpers —
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
        root.minsize(px(760), px(520))
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
        self.title = GlitchText(col, "SPARK AUDIO", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7), anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.tabs = TabBar(root, self._tab_list(), self.show, self.font(9), px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{min(px(980), int(sw * 0.8))}x{min(px(680), int(sh * 0.85))}")
        self._status_idle()

    def _tab_list(self):
        return [(k, t(f'tab.{k}')) for k in TABS if k != 'scarlett' or self.scarlett]

    # — tabs —
    def view(self, tab: str) -> tk.Frame:
        if tab not in self.views:
            from . import views
            self.views[tab] = {'outputs': views.OutputsView, 'inputs': views.InputsView,
                               'apps': views.AppsView, 'eq': views.EqView,
                               'scarlett': views.ScarlettView}[tab](self)
        return self.views[tab]

    def show(self, tab: str, glitch: bool = True):
        if tab == self.tab:
            return
        old = self.views.get(self.tab) if self.tab else None
        if old is not None:
            old.pack_forget()
        self.tab = tab
        self.settings['tab'] = tab
        self.tabs.select(tab)
        view = self.view(tab)
        view.pack(fill="both", expand=True)
        view.refresh()
        self._wanted = {}
        self._apply_meters()
        self._schedule_scarlett()
        if glitch:
            self.glitch.now(self.title)

    # — PipeWire changes —
    def _woke(self, _fd, _mask):
        if self.backend.drain():
            self._changed()

    def _changed(self):
        if not self.backend.connected and not self.fake:
            self.set_status(t('status.no_pipewire'), T["pink"], hold=True)
        else:
            if self._status_id in (None, 'hold'):
                self._status_idle()
        view = self.views.get(self.tab)
        if view is not None:
            view.refresh()
        if self.visible:
            self._apply_meters()

    def _mic_changed(self):
        view = self.views.get('inputs')
        if view is not None:
            view.mic_changed()
        if self.mic.state == 'failed':
            self.glitch.now(self.title, strong=True)

    # — meters —
    def _apply_meters(self):
        view = self.views.get(self.tab)
        wanted = view.wanted_meters() if view is not None and self.visible else {}
        if wanted != self._wanted:
            self._wanted = wanted
            self.meters.want(wanted)

    def _meter_tick(self):
        self._meter_id = self.root.after(METER_MS, self._meter_tick)
        if not self.visible:
            return
        view = self.views.get(self.tab)
        if view is not None:
            view.tick()

    # — Scarlett —
    def _find_scarlett(self):
        if self.fake:
            runner = fake_runner(self.fake_dir)
            try:
                with open(os.path.join(self.fake_dir, 'proc-asound-cards.txt'), encoding='utf-8') as f:
                    cards = f.read()
            except OSError:
                cards = None
            work = lambda: find_interfaces(runner, cards)       # noqa: E731
        else:
            if not shutil.which('amixer'):
                return
            work = lambda: find_interfaces(default_runner)       # noqa: E731
        self.backend.submit(work, self._found_scarlett)

    def _found_scarlett(self, found):
        if isinstance(found, Exception) or not found:
            return
        self.scarlett = found
        self.tabs.set_tabs(self._tab_list())
        self.tabs.select(self.tab)
        view = self.views.get('scarlett')
        if view is not None:
            view.refresh()
        self._schedule_scarlett()

    def _schedule_scarlett(self):
        if self._scarlett_id:
            self.root.after_cancel(self._scarlett_id)
            self._scarlett_id = None
        if self.tab == 'scarlett' and self.visible:
            self._scarlett_id = self.root.after(SCARLETT_MS, self._scarlett_tick)

    def _scarlett_tick(self):
        self._scarlett_id = None
        view = self.views.get('scarlett')
        if view is not None and self.tab == 'scarlett' and self.visible:
            view.poll()
        self._schedule_scarlett()

    # — window state —
    def _pause(self):
        if self.visible:
            self.visible = False
            self.meters.stop_all()
            self._wanted = {}
            self._schedule_scarlett()
            log.info("hidden: meters stopped")

    def _unmapped(self, event):
        if event.widget is self.root:
            self._pause()

    def _mapped(self, event):
        if event.widget is not self.root or self.visible:
            return
        self.visible = True
        self._changed()
        self._schedule_scarlett()

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
        if self.fake:
            self.status.config(text="● " + t('status.test_data'), fg=T["gold"])
        elif not self.backend.connected:
            self.status.config(text="● " + t('status.no_pipewire'), fg=T["pink"])
        else:
            self.status.config(text="● " + t('status.live'), fg=T["accent"])

    def set_status(self, text: str, colour: str = None, hold: bool = False):
        self.status.config(text="● " + text.upper(), fg=colour or T["accent"])
        if self._status_id and self._status_id != 'hold':
            self.root.after_cancel(self._status_id)
        self._status_id = None
        if not hold:
            self._status_id = self.root.after(4000, self._status_idle)
        else:
            self._status_id = 'hold'

    def message(self, text: str, colour: str = None, glitch: bool = True):
        self.set_status(text, colour)
        if glitch:
            self.glitch.now(self.title)

    # — closing —
    def close(self):
        try:
            self.settings['geometry'] = self.root.geometry()
            if not self.fake:
                save_json('config.json', self.settings)
        except tk.TclError:
            pass
        self.mic.cancel()
        self.meters.stop_all()
        for attr in ('_meter_id', '_scarlett_id', '_status_id'):
            job = getattr(self, attr)
            if job and job != 'hold':
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            setattr(self, attr, None)
        self.backend.close()
        self.listener.close()
        try:
            self.root.tk.deletefilehandler(self.backend.wake_fd)
        except Exception:                           # noqa: BLE001
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
