"""The window: header, the list of steps on the left, the page, and Back/Next at the bottom.
Also the command line and the self-test."""

import argparse
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from . import APP_CLASS, APP_ID, APP_NAME, APP_SLUG, PAGES, VERSION
from . import catalog as catalog_mod
from . import checks, core, flatpak
from .core import log
from .strings import t
from .widgets import T, Glitch, GlitchText, Mark, Strip, WolkButton, pick_mono


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_WELCOME_SCALE')
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


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_image(root: tk.Misc, name: str, system: str = '') -> Optional[tk.PhotoImage]:
    for path in (os.path.join(HERE, 'icons', name), system):
        if path and os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                log.exception("could not load %s", path)
    return None


class App:
    def __init__(self, start_page: str = 'welcome'):
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
        self.mono = pick_mono(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.icon = load_image(self.root, f'{APP_SLUG}-256.png',
                               f'/usr/share/icons/hicolor/256x256/apps/{APP_ID}.png')
        if self.icon is not None:
            self.root.iconphoto(True, self.icon)
        self.settings = core.load_json('config.json')
        self.glitch = Glitch(self.root, enabled=not core.reduced_motion()
                             and self.settings.get("glitch", True) is not False)
        self.show_again = core.show_at_login()
        try:
            self.catalog = catalog_mod.load()
        except catalog_mod.CatalogError as exc:
            log.error("catalog: %s", exc)
            self.catalog = catalog_mod.Catalog([])
        self.installed: set = set()
        self.installer = flatpak.Installer(on_change=self.install_changed)
        self.rows: Dict[str, Any] = {}           # app id -> AppRow, for install progress
        self._inbox: 'queue.Queue[Tuple[Callable, tuple]]' = queue.Queue()
        self._busy = 0
        self._pump_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self.pages: Dict[str, Any] = {}
        self.page: Optional[str] = None
        self.closing = False
        self._build()
        self.go(start_page if start_page in PAGES else 'welcome')
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip)
        self.bg(flatpak.installed_ids, self._got_installed)

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
        self.set_status(t('status.error'), T["pink"])
        self.glitch.now(self.title, strong=True)
        if os.environ.get('SPARK_WELCOME_TEST'):
            raise exc_value
        messagebox.showerror(APP_NAME, t('error.unexpected', error=exc_value), parent=self.root)

    # window
    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(760), px(520))

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, APP_NAME.upper(), self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text=f"● {t('status.ready')}", bg=bg, fg=T["accent"],
                               font=self.font(7))
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")

        # bottom bar: install progress on the left, Back and Next on the right
        foot = tk.Frame(root, bg=T["panel"], highlightthickness=1, highlightbackground=T["line"])
        foot.pack(side="bottom", fill="x")
        inner = tk.Frame(foot, bg=T["panel"])
        inner.pack(fill="x", padx=px(14), pady=px(10))
        self.next_btn = WolkButton(inner, t('nav.next'), self.next, self.font(9), "primary")
        self.next_btn.pack(side="right")
        self.back_btn = WolkButton(inner, t('nav.back'), self.back, self.font(9))
        self.back_btn.pack(side="right", padx=(0, px(8)))
        work = tk.Frame(inner, bg=T["panel"])
        work.pack(side="left", fill="x", expand=True, padx=(0, px(16)))
        self.work_label = tk.Label(work, text="", bg=T["panel"], fg=T["muted"], font=self.font(8),
                                   anchor="w")
        self.work_label.pack(fill="x")
        self.work_bar = Strip(work, height=px(3))
        self.work_bar.configure(bg=T["panel"])

        body = tk.Frame(root, bg=bg)
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=T["panel"], width=px(210), highlightthickness=1,
                        highlightbackground=T["line"])
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text=t('nav.steps'), bg=T["panel"], fg=T["dim"], font=self.font(7),
                 anchor="w").pack(fill="x", padx=px(14), pady=(px(14), px(6)))
        self.steps: Dict[str, Tuple[tk.Frame, tk.Label]] = {}
        for i, name in enumerate(PAGES, 1):
            row = tk.Frame(side, bg=T["panel"], cursor="hand2")
            row.pack(fill="x")
            bar = tk.Frame(row, bg=T["panel"], width=px(3))
            bar.pack(side="left", fill="y")
            label = tk.Label(row, text=f"{i:02d}  {t(f'nav.{name}')}", bg=T["panel"],
                             fg=T["muted"], font=self.font(9), anchor="w", padx=px(11),
                             pady=px(7), cursor="hand2")
            label.pack(side="left", fill="x", expand=True)
            for w in (row, label):
                w.bind("<ButtonRelease-1>", lambda _e, n=name: self.go(n))
            self.steps[name] = (bar, label)
        tk.Label(side, text=t('nav.note'), bg=T["panel"], fg=T["dim"], font=self.font(8, False),
                 justify="left", anchor="w", wraplength=px(180)).pack(
                     side="bottom", fill="x", padx=px(14), pady=px(14))
        self.content = tk.Frame(body, bg=bg)
        self.content.pack(side="left", fill="both", expand=True)

        root.bind_all("<MouseWheel>", self._wheel)
        root.bind_all("<Button-4>", self._wheel)
        root.bind_all("<Button-5>", self._wheel)
        root.bind("<Control-q>", lambda _e: self.close())
        root.bind("<Alt-Left>", lambda _e: self.back())
        root.bind("<Alt-Right>", lambda _e: self.next())
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(px(1040), int(sw * 0.85)), min(px(740), int(sh * 0.85))
        root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

    def _wheel(self, event):
        page = self.pages.get(self.page or '')
        if page is None:
            return
        if getattr(event, 'num', None) in (4, 5):
            units = -3 if event.num == 4 else 3
        else:
            delta = event.delta if abs(event.delta) >= 120 else event.delta * 120
            units = -int(delta / 120) * 3
        page.scroll(units)

    # status line in the header
    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 3000):
        self.status.config(text=f"● {text}", fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(hold_ms, self._status_idle)

    def _status_idle(self):
        self._status_id = None
        self.status.config(text=f"● {t('status.ready')}", fg=T["accent"])

    def event(self, error: bool = False):
        """Something happened: the heading and the page's panel tear."""
        page = self.pages.get(self.page or '')
        targets = [self.title] + ([page.heading] if page is not None and page.heading else [])
        self.glitch.now(*targets, strong=error)

    # navigation
    def go(self, name: str):
        from . import pages as pages_mod
        if name not in PAGES or name == self.page:
            return
        if self.page in self.pages:
            self.pages[self.page].pack_forget()
        if name not in self.pages:
            self.pages[name] = pages_mod.PAGE_CLASSES[name](self.content, self)
        page = self.pages[name]
        page.pack(fill="both", expand=True)
        self.page = name
        for step, (bar, label) in self.steps.items():
            on = step == name
            bar.config(bg=T["accent"] if on else T["panel"])
            label.config(fg=T["accent"] if on else T["muted"],
                         bg=T["panel2"] if on else T["panel"])
        index = PAGES.index(name)
        self.back_btn.set_enabled(index > 0)
        self.next_btn.set_text(t('nav.close') if name == 'done' else t('nav.next'))
        page.shown()
        if page.heading is not None:
            self.glitch.now(page.heading)
        if name == 'done':
            core.mark_done(self.show_again)

    def next(self):
        if self.page == 'done':
            self.close()
            return
        self.go(PAGES[min(len(PAGES) - 1, PAGES.index(self.page or 'welcome') + 1)])

    def back(self):
        index = PAGES.index(self.page or 'welcome')
        if index > 0:
            self.go(PAGES[index - 1])

    # background work: fn runs in a thread; done(result) and post()ed calls run in Tk
    def bg(self, fn: Callable[..., Any], done: Optional[Callable[[Any], None]] = None,
           *args) -> threading.Thread:
        self._busy += 1

        def work():
            try:
                result = fn(*args)
            except Exception as exc:         # noqa: BLE001 - reported, never lost
                log.exception("background job failed")
                result = exc
            self._inbox.put((self._finished, (done, result)))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        self._ensure_pump()
        return thread

    def post(self, fn: Callable, *args) -> None:
        """From any thread: run fn(*args) in the Tk thread."""
        self._inbox.put((fn, args))

    def _finished(self, done, result):
        self._busy -= 1
        if done is not None and not self.closing:
            done(result)

    def _ensure_pump(self):
        if self._pump_id is None and not self.closing:
            self._pump_id = self.root.after(80, self._pump)

    def _pump(self):
        """Runs only while something is working, so an idle window uses no CPU."""
        self._pump_id = None
        while True:
            try:
                fn, args = self._inbox.get_nowait()
            except queue.Empty:
                break
            if not self.closing:
                fn(*args)
        if self.closing:
            return
        self.installer.poll()
        self._show_install_progress()
        if self._busy > 0 or self.installer.busy() or not self._inbox.empty():
            self._ensure_pump()

    # installing
    def _got_installed(self, result):
        if isinstance(result, set):
            self.installed = result
            for app_id, row in self.rows.items():
                if app_id in result:
                    row.set_installed()

    def install(self, entries: List[Any]) -> None:
        for entry in entries:
            self.installer.add(entry.id, entry.label())
        log.info("queued %s", ', '.join(e.id for e in entries))
        self.event()
        self._ensure_pump()

    def retry(self, app_id: str) -> None:
        self.installer.retry(app_id)
        self._ensure_pump()

    def install_changed(self, job: flatpak.Job) -> None:
        row = self.rows.get(job.app_id)
        if row is not None:
            row.set_job(job)
        if job.state == flatpak.DONE:
            self.installed.add(job.app_id)
            self.set_status(t('status.installed', name=job.name.upper()))
        elif job.state == flatpak.FAILED:
            self.set_status(t('status.failed', name=job.name.upper()), T["pink"], 6000)
            self.event(error=True)

    def _show_install_progress(self):
        job = self.installer.current()
        finished, total = self.installer.counts()
        if job is not None:
            pct = f" {job.percent}%" if job.percent is not None else ''
            self.work_label.config(text=t('work.installing', name=job.name, pct=pct,
                                          n=finished + 1, total=total), fg=T["accent"])
            if not self.work_bar.winfo_ismapped():
                self.work_bar.pack(fill="x", pady=(self.px(4), 0))
            self.work_bar.draw(fraction=(job.percent or 0) / 100)
        elif self.installer.busy():
            self.work_label.config(text=t('work.starting'), fg=T["accent"])
        elif total:
            failed = sum(1 for j in self.installer.jobs.values() if j.state == flatpak.FAILED)
            self.work_label.config(text=t('work.done_failed', failed=failed, total=total)
                                   if failed else t('work.done', total=total),
                                   fg=T["pink"] if failed else T["muted"])
            if self.work_bar.winfo_ismapped():
                self.work_bar.pack_forget()

    # actions the pages' buttons share
    def action(self, key: str) -> None:
        ok = False
        if key == 'store':
            ok = core.open_store()
        elif key == 'settings':
            ok = core.open_settings()
        elif key == 'snip':
            ok = core.launch(['spark-snip'])
        elif key == 'anticheat':
            ok = core.open_url(catalog_mod.ANTICHEAT_URL)
        elif key == 'test_sound':
            cmd = checks.test_sound_cmd()
            ok = core.launch(cmd) if cmd else False
        elif key in checks.SETTINGS_PAGES:
            ok = core.open_settings(checks.SETTINGS_PAGES[key])
        if ok:
            self.set_status(t('status.opened'))
            self.event()
        else:
            self.set_status(t('status.cant_open'), T["pink"], 6000)
            self.event(error=True)

    def set_show_again(self, value: bool) -> None:
        self.show_again = value
        core.mark_done(value)

    # closing
    def close(self):
        if self.closing:
            return
        if self.installer.busy() and not os.environ.get('SPARK_WELCOME_TEST'):
            if not messagebox.askyesno(APP_NAME, t('close.installing'), parent=self.root):
                return
        self.closing = True
        for page in self.pages.values():
            stop = getattr(page, 'stop', None)
            if stop:
                stop()
        self.installer.stop()
        core.mark_done(self.show_again)
        core.save_json('config.json', self.settings)
        log.info("--- shutting down ---")
        try:                                    # no glitch frame may fire after this
            for pending in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.after_cancel(pending)
        except tk.TclError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Self-test: no display, no network, nothing installed ─────

AUTOSTART_PLACES = ('/etc/xdg/autostart',)


def self_test() -> int:
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    try:
        cat = catalog_mod.load()
        print(f"catalog: ok ({len(cat.launchers)} launchers, "
              f"{sum(len(c.apps) for c in cat.categories)} apps in {len(cat.categories)} "
              "categories)")
    except catalog_mod.CatalogError as exc:
        print(f"catalog: FAILED ({exc})")
        failures.append("catalog")
    try:
        import tkinter  # noqa: F401
        print(f"tk: ok ({tk.TkVersion})")
    except ImportError as exc:
        print(f"tk: FAILED ({exc})")
        failures.append("tk")
    for tool in ('flatpak', 'udisksctl', 'lsblk'):
        path = shutil.which(tool)
        print(f"{tool}: {path or 'MISSING'}")
        if not path:
            failures.append(tool)
    optional = ('xdg-user-dir', 'xdg-open', 'vulkaninfo', 'wpctl', 'pw-play', 'lpstat',
                'scanimage', 'nmcli', 'bluetoothctl', 'rpm-ostree', 'systemsettings')
    print("optional: " + "  ".join(f"{name}:{'yes' if shutil.which(name) else 'no'}"
                                   for name in optional))
    places = [core.autostart_file()] + [os.path.join(d, f'{APP_ID}.desktop')
                                        for d in AUTOSTART_PLACES]
    found = next((p for p in places if os.path.isfile(p)), None)
    print(f"autostart: {found or 'MISSING (looked in ' + ', '.join(places) + ')'}")
    if not found:
        failures.append("autostart entry")
    if found:
        try:
            with open(found, encoding='utf-8') as f:
                text = f.read()
            if '--first-login' not in text:
                print("autostart: FAILED (doesn't pass --first-login)")
                failures.append("autostart --first-login")
        except OSError as exc:
            print(f"autostart: FAILED ({exc})")
            failures.append("autostart readable")
    print(f"first login: {core.skip_first_login() or 'would open the window'}")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: first-login "
                                     "setup for SparkOS.")
    parser.add_argument('--first-login', action='store_true',
                        help="open only if this is the first login (the autostart entry)")
    parser.add_argument('--page', choices=PAGES, default='welcome', help="start on this page")
    parser.add_argument('--self-test', action='store_true',
                        help="check the app list and the programs it needs; no display needed")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.first_login and core.skip_first_login():
        return 0
    core.setup_logging()
    try:
        app = App(args.page)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
