"""The Spark Clock window: a header with the service's state, a banner for anything ringing, and
four tabs (alarms, timers, stopwatch, world). The window only edits files; the background
service rings. Closing the window changes nothing about what rings."""

import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable, Dict, List, Optional

from . import APP_CLASS, APP_NAME, core, servicectl, store
from .core import log, reduced_motion
from .tabs import AlarmsTab, StopwatchTab, TimersTab, WorldTab
from .text import t
from .widgets import (Glitch, GlitchPanel, GlitchText, Mark, Segmented, Strip, T, WolkButton,
                      pick_mono, style_tables)
from . import dialogs

TABS = ('alarms', 'timers', 'stopwatch', 'world')


class App:
    def __init__(self, tab: str = 'alarms',
                 ask: Optional[Callable[..., bool]] = None,
                 error: Optional[Callable[..., object]] = None,
                 clock: Callable[[], float] = time.time,
                 start_service: bool = True):
        # the dialogs and the clock can be swapped (the tests answer them and set the time)
        self.ask = ask or dialogs.askyesno
        self.error = error or dialogs.showerror
        self.clock = clock
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        try:
            self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            self.scale = 1.0
        self.root.geometry(f"{self.px(860)}x{self.px(700)}")
        self.root.minsize(self.px(640), self.px(520))
        family = pick_mono(self.root)
        mk = lambda size, weight="normal": tkfont.Font(root=self.root, family=family,   # noqa: E731
                                                       size=size, weight=weight)
        self.f_body, self.f_small = mk(9), mk(8)
        self.f_label, self.f_title = mk(7, "bold"), mk(11, "bold")
        self.f_head, self.f_brand = mk(15, "bold"), mk(10, "bold")
        self.f_big, self.f_huge = mk(22, "bold"), mk(40, "bold")
        style_tables(self.root, self.f_body, self.f_label, self.px(22))
        self.glitch = Glitch(self.root, not reduced_motion())
        self.closed = False

        self.config: Dict[str, Any] = store.load_config()
        self.timers: List[Dict[str, Any]] = store.load_timers()
        self.stopwatch: Dict[str, Any] = store.load_stopwatch()
        self.service: Dict[str, Any] = store.load_service()
        self.seen = self._mtimes()
        self.ring_keys: tuple = ()
        self.banners: Dict[str, Dict[str, Any]] = {}
        self.alive = False
        self.flash_until = 0.0

        self._header()
        self.banner_area = tk.Frame(self.root, bg=T["bg"])
        self.banner_area.pack(fill="x")
        bar = tk.Frame(self.root, bg=T["bg"])
        bar.pack(fill="x", padx=self.px(16), pady=(self.px(8), self.px(2)))
        self.tabs_bar = Segmented(bar, [(t('tab.' + name), name) for name in TABS], tab,
                                  self.show, self.f_label)
        self.tabs_bar.pack(side="left")
        self.body = tk.Frame(self.root, bg=T["bg"])
        self.body.pack(fill="both", expand=True)
        note = tk.Label(self.root, text=t('service.note'), bg=T["bg"], fg=T["dim"],
                        font=self.f_small, anchor="w", justify="left",
                        wraplength=self.px(820))
        note.pack(fill="x", padx=self.px(18), pady=(0, self.px(8)))
        self.note = note
        self.root.bind("<Configure>", self._resized)

        self.tabs = {'alarms': AlarmsTab(self), 'timers': TimersTab(self),
                     'stopwatch': StopwatchTab(self), 'world': WorldTab(self)}
        self.current = tab if tab in TABS else 'alarms'
        self.show(self.current)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for seq in ("<Control-q>", "<Control-w>"):
            self.root.bind(seq, lambda _e: self.close())
        for number, name in enumerate(TABS, 1):
            self.root.bind(f"<Alt-Key-{number}>", lambda _e, n=name: self.show(n, fire=True))
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        if start_service:
            self.root.after(300, self._ensure_service)
        self._after = self.root.after(100, self._tick)

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
        self.turn_on = WolkButton(bar, t('service.turn_on'), self.start_service, self.f_label,
                                  variant="primary", padx=8, pady=2)
        self.strip = Strip(self.root, height=2)
        self.strip.pack(fill="x")
        self.set_service_status(False)

    def set_service_status(self, alive: bool):
        self.alive = alive
        if time.monotonic() < self.flash_until:
            return
        if alive:
            self.status.config(text="● " + t('service.on'), fg=T["accent"])
            self.turn_on.pack_forget()
        else:
            self.status.config(text="● " + t('service.off'), fg=T["gold"])
            self.turn_on.pack(side="right", padx=(0, self.px(10)))

    def flash(self, text: str, colour: Optional[str] = None):
        """A short word in the header's status spot, for a few seconds."""
        self.status.config(text="● " + text, fg=colour or T["accent"])
        self.flash_until = time.monotonic() + 3.5
        self.root.after(3600, lambda: None if self.closed else self.set_service_status(self.alive))

    def _resized(self, event):
        if event.widget is self.root:
            self.note.config(wraplength=max(200, event.width - self.px(36)))

    def event(self, *targets, strong: bool = False):
        """Something happened: the house fault on the header and whatever else is named."""
        self.glitch.now(self.title, self.strip, *targets, strong=strong)

    # ── tabs ──

    def show(self, name: str, fire: bool = False):
        for key, tab in self.tabs.items() if hasattr(self, 'tabs') else ():
            tab.pack_forget()
        self.current = name
        self.tabs_bar.set(name)
        tab = self.tabs[name]
        tab.pack(in_=self.body, fill="both", expand=True)
        tab.reload()
        tab.tick(self.clock())
        self.event(tab.heading, strong=False)

    # ── the service ──

    def _ensure_service(self):
        if self.closed:
            return
        self.service = store.load_service()
        if not store.service_alive(self.clock(), self.service) and servicectl.unit_installed():
            self.start_service(quiet=True)

    def start_service(self, quiet: bool = False):
        ok, why = servicectl.start()
        if ok:
            if not quiet:
                self.flash(t('service.started'))
            return
        log.warning("service didn't start: %s", why)
        self.event(strong=True)
        self.flash(t('service.cant_start'), T["pink"])
        if not quiet:
            self.error(t('service.cant_start'), t('service.cant_start_body', error=why),
                       parent=self.root)

    # ── data ──

    @staticmethod
    def _mtimes():
        return tuple(store.mtime(n) for n in ('clock.json', 'timers.json', 'stopwatch.json',
                                              'service.json'))

    def refresh_data(self, force: bool = False):
        """Read the files again if any changed (the service writes too)."""
        seen = self._mtimes()
        if seen == self.seen and not force:
            return
        self.seen = seen
        self.config = store.load_config()
        self.timers = store.load_timers()
        self.stopwatch = store.load_stopwatch()
        self.service = store.load_service()
        self.tabs[self.current].reload()

    def _tick(self):
        if self.closed:
            return
        try:
            now = self.clock()
            self.refresh_data()
            alive = store.service_alive(now, self.service)
            if alive != self.alive:
                self.set_service_status(alive)
            self._banners(now)
            self.tabs[self.current].tick(now)
        except Exception:                      # a bad frame must not stop the clock
            log.exception("tick failed")
        self._after = self.root.after(100 if self.current == 'stopwatch' else 250, self._tick)

    # ── what is ringing ──

    def _banners(self, now: float):
        rings = self.service.get('ringing', []) if store.service_alive(now, self.service) else []
        keys = tuple(sorted(r.get('key', '') for r in rings))
        if keys == self.ring_keys:
            if rings and int(now) % 4 == 0 and now - getattr(self, '_last_burst', 0) > 3:
                self._last_burst = now
                self.event(*[b['panel'] for b in self.banners.values()], strong=True)
            return
        self.ring_keys = keys
        for banner in self.banners.values():
            banner['panel'].destroy()
        self.banners = {}
        for ring in rings:
            self._banner(ring)
        if rings:
            self.event(*[b['panel'] for b in self.banners.values()], strong=True)

    def _banner(self, ring: Dict[str, Any]):
        panel = GlitchPanel(self.banner_area, T["panel"])
        panel.pack(fill="x", padx=self.px(16), pady=(self.px(8), 0))
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="x", padx=self.px(14), pady=self.px(10))
        heading = GlitchText(inner, ring.get('title', '').upper(), self.f_title, T["panel"],
                             fg=T["pink"])
        heading.pack(side="left")
        if ring.get('body'):
            tk.Label(inner, text=ring['body'], bg=T["panel"], fg=T["text"], font=self.f_body
                     ).pack(side="left", padx=(self.px(12), 0))
        key, kind = ring.get('key', ''), ring.get('kind')
        buttons = tk.Frame(inner, bg=T["panel"])
        buttons.pack(side="right")
        stop = WolkButton(buttons, t('banner.stop'), lambda: self.answer(key, 'stop'),
                          self.f_label, variant="primary", padx=10, pady=3)
        stop.pack(side="left", padx=(0, self.px(6)))
        if kind == 'alarm':
            more = WolkButton(buttons, t('banner.snooze', minutes=ring.get('snooze', 9)),
                              lambda: self.answer(key, 'snooze'), self.f_label, padx=10, pady=3)
        else:
            more = WolkButton(buttons, t('banner.plus'), lambda: self.answer(key, 'plus'),
                              self.f_label, padx=10, pady=3)
        more.pack(side="left")
        self.banners[key] = {'panel': panel, 'stop': stop, 'more': more, 'heading': heading}
        self.glitch.add(heading)

    def answer(self, key: str, cmd: str):
        store.send_command(cmd, key)
        banner = self.banners.pop(key, None)
        if banner:
            banner['panel'].destroy()
        self.ring_keys = tuple(k for k in self.ring_keys if k != key)

    # ── closing ──

    def run(self):
        self.root.mainloop()

    def close(self):
        self.closed = True
        try:
            self.root.after_cancel(self._after)
        except (tk.TclError, AttributeError):
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
