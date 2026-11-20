"""The app: window, header, switching screens, background work, and the command line."""

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import APP_CLASS, APP_ID, APP_NAME, APP_SLUG, VERSION
from . import anticheat, heroic, launch, library, lutris, steam
from .core import (Game, home, load_settings, log, mtime, open_uri, reduced_motion,
                   save_settings, setup_logging, spawn, which)
from .strings import tr

STORE_DESKTOP = 'io.github.kolunmi.Bazaar.desktop'
FOCUS_CHECK = 2.0          # seconds between looks at the launchers' files on window focus


def detect_scale(root) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    import tkinter as tk
    forced = os.environ.get('SPARK_GAMES_SCALE')
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


def load_icon(root):
    import tkinter as tk
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(here, 'icons', f'{APP_SLUG}-256.png'),
                 os.path.join(home(), '.local', 'share', 'icons', 'hicolor', '256x256', 'apps',
                              f'{APP_ID}.png'),
                 f'/usr/share/icons/hicolor/256x256/apps/{APP_ID}.png'):
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                log.exception("could not load %s", path)
    return None


class App:
    def __init__(self, scan_home: Optional[str] = None):
        import tkinter as tk
        import tkinter.font as tkfont
        from .views import LibraryView
        from .widgets import Glitch, pick_mono
        self.tk, self.tkfont_mod = tk, tkfont
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.scan_home = scan_home
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono(self.root)
        self._fonts: Dict[Tuple[int, bool], Any] = {}
        self.icon = load_icon(self.root)
        if self.icon is not None:
            self.root.iconphoto(True, self.icon)
        self.settings = load_settings()
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and self.settings.get("glitch", True) is not False)
        self.session_totals: Dict[str, Dict[str, int]] = {}
        self.ac_entries: Optional[List[Any]] = None
        self.games: List[Game] = []
        self.launchers: set = set()
        self.watch: List[str] = []
        self.sig: Optional[list] = None
        self.scanning = False
        self._scan_again = False
        self._last_focus_check = 0.0
        self._calls: "queue.Queue[Tuple[Callable, Any]]" = queue.Queue()
        self._busy = 0
        self._pump_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self.view = None
        self._build()

        self.library = LibraryView(self)
        self._show(self.library)
        cached = library.load_cache()
        if cached is not None:
            self._apply(cached, scanning=True)
        else:
            self.library.set_games([], scanning=True)
        self.root.deiconify()
        self.library.focus_default()
        self.glitch.add(self.title, self.mark, self.strip)
        self.rescan()
        if self.anticheat_on():
            self._load_anticheat()
        self.root.bind("<FocusIn>", self._focus_in, add="+")

    # look helpers
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = self.tkfont_mod.Font(self.root, family=self.mono, size=size,
                                                    weight="bold" if bold else "normal")
        return self._fonts[key]

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        from tkinter import messagebox
        from .widgets import T
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status("SOMETHING WENT WRONG", T["pink"])
        self.glitch.now(self.title, strong=True)
        messagebox.showerror(APP_NAME, tr('err_unexpected', detail=exc_value), parent=self.root)

    # window
    def _build(self):
        from .widgets import T, GlitchText, IconButton, Mark, Strip
        tk = self.tk
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.minsize(px(640), px(460))

        self.head = tk.Frame(root, bg=bg)
        self.head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.back = IconButton(self.head, "back", self.go_back, px(30), tip=tr('back'))
        self.mark = Mark(self.head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(self.head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, tr('title'), self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text=f"● {tr('ready')}", bg=bg, fg=T["accent"],
                               font=self.font(7))
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(self.head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        IconButton(self.head, "settings", self.show_settings, px(28),
                   tip=tr('tip_settings')).pack(side="right", padx=(0, px(10)))
        IconButton(self.head, "rescan", self.rescan, px(28),
                   tip=tr('tip_rescan')).pack(side="right", padx=(0, px(4)))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)

        root.bind("<KeyPress>", self._key)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(px(1240), int(sw * 0.85)), min(px(820), int(sh * 0.85))
            root.geometry(f"{w}x{h}")

    def set_status(self, text: str, colour: Optional[str] = None, hold_ms: int = 2500):
        from .widgets import T
        self.status.config(text=f"● {text}", fg=colour or T["accent"])
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(hold_ms, self._status_idle)

    def _status_idle(self):
        from .widgets import T
        self._status_id = None
        if self.scanning:
            text = tr('scanning')
        else:
            n = len(self.games)
            text = tr('game_1') if n == 1 else tr('games_n', n=n)
        self.status.config(text=f"● {text}", fg=T["accent"])

    # screens
    def _show(self, view):
        if self.view is view:
            return
        if self.view is not None:
            if self.view is self.library:
                self.view.pack_forget()
            else:
                self.view.destroy()
        self.view = view
        view.pack(fill="both", expand=True)
        on_library = view is self.library
        if on_library and self.back.winfo_ismapped():
            self.back.pack_forget()
        elif not on_library and not self.back.winfo_ismapped():
            self.back.pack(side="left", padx=(0, self.px(8)), before=self.mark)
        view.focus_default()

    def go_back(self):
        if self.view is not self.library:
            self._show(self.library)
            self.library.render()
            self.glitch.now(self.title)

    def show_game(self, game: Game):
        from .views import GamePage
        self._show(GamePage(self, game))
        self.root.title(f"{game.title} — {APP_NAME}")

    def show_add(self):
        from .views import AddGameView
        self._show(AddGameView(self))

    def show_settings(self):
        from .views import SettingsView
        self._show(SettingsView(self))
        self.glitch.now(self.view.heading)

    # background work: fn runs in a thread, done(result) runs here; no polling when idle
    def background(self, fn: Callable[[], Any], done: Callable[[Any], None]):
        def run():
            try:
                result = fn()
            except Exception as exc:       # noqa: BLE001
                log.exception("background job failed")
                result = exc
            self._calls.put((done, result))
        self._busy += 1
        threading.Thread(target=run, daemon=True).start()
        if self._pump_id is None:
            self._pump_id = self.root.after(50, self._pump)

    def _pump(self):
        self._pump_id = None
        while True:
            try:
                done, result = self._calls.get_nowait()
            except queue.Empty:
                break
            self._busy -= 1
            done(result)
        if self._busy > 0:
            self._pump_id = self.root.after(50, self._pump)

    # the library
    def rescan(self):
        if self.scanning:
            self._scan_again = True
            return
        self.scanning = True
        self.set_status(tr('scanning'), hold_ms=600000)
        base = self.scan_home

        def work():
            result = library.scan_all(base)
            totals = launch.totals()
            library.merge_sessions(result.games, totals)
            library.save_cache(result)
            return result, totals, library.signature(result.watch)

        self.background(work, self._scanned)

    def _scanned(self, outcome):
        from .widgets import T
        self.scanning = False
        if isinstance(outcome, Exception):
            self.set_status(tr('err_unexpected', detail=outcome).upper(), T["pink"])
            self.glitch.now(self.title, strong=True)
            self.library.set_games(self.games, scanning=False)
            return
        result, totals, sig = outcome
        self.session_totals = totals
        self.sig = sig
        self._apply(result, scanning=False)
        if result.problems:
            names = ', '.join(p.upper() for p in result.problems)
            self.set_status(tr('scan_problem', names=names), T["gold"], hold_ms=6000)
            self.glitch.now(self.title, strong=True)
        else:
            self._status_idle()
        log.info("scan: %d games from %s", len(result.games), ', '.join(sorted(result.launchers))
                 or 'no launchers')
        if self._scan_again:
            self._scan_again = False
            self.rescan()

    def _apply(self, result, scanning: bool):
        self.games = result.games
        self.watch = result.watch
        self.launchers = result.launchers
        if self.ac_entries is not None:
            anticheat.mark(self.games, self.ac_entries)
        self.library.set_games(self.games, scanning)
        if not scanning:
            self._status_idle()

    def _focus_in(self, _event=None):
        """Scan again when a launcher's files changed while the window was in the background."""
        now = time.monotonic()
        if self.scanning or now - self._last_focus_check < FOCUS_CHECK or self.sig is None:
            return
        self._last_focus_check = now
        if library.signature(self.watch) != self.sig:
            log.info("launcher files changed; scanning again")
            self.rescan()

    # anti-cheat list
    def anticheat_on(self) -> bool:
        return self.settings.get('anticheat', True) is not False

    def set_anticheat(self, on: bool):
        self.settings['anticheat'] = on
        if on:
            self._load_anticheat()
        else:
            self.ac_entries = None
            for game in self.games:
                game.anticheat = ''
            self.library.render()

    def _load_anticheat(self):
        def done(entries):
            if isinstance(entries, list) and self.anticheat_on():
                self.ac_entries = entries
                count = anticheat.mark(self.games, entries)
                log.info("anti-cheat list: %d entries, %d installed games marked",
                         len(entries), count)
                self.library.render()
        self.background(lambda: anticheat.load(online=True), done)

    def anticheat_checked(self) -> str:
        stamp = mtime(anticheat.cache_path())
        return time.strftime('%Y-%m-%d', time.localtime(stamp)) if stamp else '?'

    # per-game options (MangoHud, GameMode)
    def game_options(self, key: str) -> Dict[str, Any]:
        options = self.settings.get('options')
        if not isinstance(options, dict):
            options = self.settings['options'] = {}
        value = options.get(key)
        return value if isinstance(value, dict) else {}

    def set_game_option(self, key: str, name: str, value: bool):
        options = self.game_options(key)
        options[name] = value
        self.settings['options'][key] = options
        save_settings(self.settings)

    def launchers_found(self) -> List[Tuple[str, str]]:
        base = self.scan_home or home()
        out = []
        for path, flatpak in steam.roots(base):
            out.append(("Steam" + (" (Flatpak)" if flatpak else ""), path))
        for path, flatpak in heroic.roots(base):
            out.append(("Heroic" + (" (Flatpak)" if flatpak else ""), path))
        for data, _cache, flatpak in lutris.roots(base):
            out.append(("Lutris" + (" (Flatpak)" if flatpak else ""), data))
        return out

    # playing
    def play(self, game: Game):
        from tkinter import messagebox
        from .widgets import T
        try:
            launch.start(game, self.game_options(game.key))
        except launch.LaunchError as exc:
            log.warning("can't start %s: %s %s", game.key, exc.code, exc.detail)
            self.set_status(tr('err_' + exc.code, detail=exc.detail).upper()[:60], T["pink"])
            self.glitch.now(self.title, strong=True)
            messagebox.showerror(APP_NAME, tr('err_' + exc.code, detail=exc.detail),
                                 parent=self.root)
            return
        self.set_status(tr('starting', title=game.title.upper())[:60])
        self.glitch.now(self.title, self.mark, strong=True)
        after = self.settings.get('after_launch', 'stay')
        if after == 'minimize':
            self.root.after(800, self.root.iconify)
        elif after == 'close':
            self.root.after(800, self._on_close)

    def open_store(self):
        for folder in ('/usr/share/applications', '/var/lib/flatpak/exports/share/applications',
                       os.path.join(home(), '.local', 'share', 'flatpak', 'exports', 'share',
                                    'applications')):
            path = os.path.join(folder, STORE_DESKTOP)
            if os.path.isfile(path) and which('gio'):
                spawn(['gio', 'launch', path])
                return
        if which('plasma-discover'):
            spawn(['plasma-discover'])
            return
        open_uri('https://flathub.org')

    def open_welcome(self):
        spawn(['spark-welcome', '--page', 'games'])

    def _key(self, event):
        k = event.keysym
        if k in ('q', 'Q') and event.state & 0x4:
            self._on_close()
            return "break"
        if k == 'F5':
            self.rescan()
            return "break"
        handler = getattr(self.view, 'key', None)
        if handler and handler(event):
            return "break"
        if k == 'Escape' and self.view is not self.library:
            self.go_back()
            self.root.title(APP_NAME)
            return "break"
        return None

    def _on_close(self):
        if self.root.state() == 'normal':
            self.settings["geometry"] = self.root.geometry()
        self.settings["version"] = VERSION
        save_settings(self.settings)
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Self-test: no display, no network ────────────────────────

def self_test() -> int:
    """Parse the bundled fixtures with every scanner, cut a cover, build each launch command,
    and check what the app needs. Exit 1 when something required is missing."""
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test (python {sys.version.split()[0]})")

    def check(name: str, ok: bool, detail: str = '', required: bool = True):
        word = 'ok' if ok else ('FAILED' if required else 'missing (optional)')
        print(f"  {name}: {word}" + (f" ({detail})" if detail else ''))
        if not ok and required:
            failures.append(name)

    try:
        import tkinter
        check("tkinter", True, f"Tk {tkinter.TkVersion}")
    except ImportError as exc:
        check("tkinter", False, str(exc))
    try:
        import PIL
        from PIL import ImageTk  # noqa: F401
        check("pillow", True, PIL.__version__)
    except ImportError as exc:
        check("pillow", False, str(exc))
        print("FAILED: " + ", ".join(failures))
        return 1
    import sqlite3
    check("sqlite3", True, sqlite3.sqlite_version)
    check("xdg-open", bool(which('xdg-open')))

    from . import covers, fixtures, vdf
    scratch = tempfile.mkdtemp(prefix='spark-games-test-')
    for var in ('XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
        os.environ[var] = os.path.join(scratch, var.lower())
    try:
        parsed = vdf.loads('"a" { "b" "say \\"hi\\"" "C" { "d" "1" } }')
        check("vdf parser", vdf.get(parsed, 'A', 'B') == 'say "hi"' and
              vdf.get(parsed, 'a', 'c', 'D') == '1')
        if fixtures.source_dir() is None:
            check("fixtures", False, "not found next to the program")
        else:
            fake = fixtures.materialize(os.path.join(scratch, 'home'))
            result = library.scan_all(fake)
            counts: Dict[str, int] = {}
            for game in result.games:
                counts[game.source] = counts.get(game.source, 0) + 1
            for source, expected in fixtures.EXPECTED.items():
                check(f"scan {source}", counts.get(source, 0) == expected,
                      f"{counts.get(source, 0)} of {expected}")
            check("scan problems", not result.problems, ', '.join(result.problems))
            with_cover = [g for g in result.games if g.cover]
            thumb = covers.thumbnail(with_cover[0].cover, 148, 222) if with_cover else None
            check("cover thumbnail", thumb is not None and thumb.size == (148, 222))
            with open(fixtures.anticheat_list(), encoding='utf-8') as f:
                marked = anticheat.mark(result.games, json.load(f))
            check("anti-cheat matching", marked == 2, f"{marked} marked")
            fake_which = lambda name: f'/usr/bin/{name}'      # noqa: E731
            bad = []
            for game in result.games:
                try:
                    launch.plan(game, which=fake_which)
                except launch.LaunchError as exc:
                    bad.append(f"{game.key}: {exc.code}")
            check("launch commands", not bad, '; '.join(bad))
    except Exception as exc:          # noqa: BLE001 - report, don't crash
        check("fixtures", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("optional:")
    for name in ('flatpak', 'steam', 'lutris', 'gamemoderun', 'mangohud', 'umu-run', 'kdialog'):
        check(name, bool(which(name)), required=False)
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: one library for "
                                     "every installed game on SparkOS.")
    parser.add_argument('--self-test', action='store_true',
                        help="check the parsers against the bundled fixtures; no display needed")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    parser.add_argument('--track', metavar='JSON', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    setup_logging()
    if args.track:
        try:
            spec = json.loads(args.track)
        except ValueError:
            return 2
        launch.track(spec)
        return 0
    try:
        app = App(os.environ.get('SPARK_GAMES_HOME') or None)
    except Exception as exc:          # noqa: BLE001 - TclError without a display
        if type(exc).__name__ == 'TclError':
            print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
            return 1
        raise
    app.run()
    return 0
