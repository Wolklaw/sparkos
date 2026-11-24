"""The window: header, tabs, a sample every few seconds, and background work. The window never
writes to a disk as root: anything that needs root goes through the helper and pkexec."""

import datetime as dt
import json
import os
import queue
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, HELPER, INTERVAL_MS, VERSION, config, state, targets
from .engine import Backup
from .lang import local_units
from .log import cache_dir, config_dir, log
from .runner import Runner
from .text import t
from .ui import TabBar, style_tables
from .widgets import T, Glitch, GlitchText, Mark, Strip, pick_mono

TABS = ("backups", "browse", "settings")
DRIVES_EVERY_S = 15


def reduced_motion() -> bool:
    if os.environ.get("SPARK_BACKUP_REDUCED_MOTION", "").lower() in ("1", "true", "yes"):
        return True
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    try:
        with open(os.path.join(base, "kdeglobals"), encoding="utf-8", errors="replace") as f:
            match = re.search(r"^AnimationDurationFactor\s*=\s*([0-9.]+)", f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def load_json(name: str) -> Dict[str, Any]:
    try:
        with open(os.path.join(config_dir(), name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(name: str, data: Dict[str, Any]) -> None:
    path = os.path.join(config_dir(), name)
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(path + ".tmp", path)
    except (OSError, ValueError) as exc:
        log.warning("could not write %s: %s", name, exc)


def human(n: Optional[int]) -> str:
    """12.3 GB in English, 12,3 Go in French."""
    if n is None:
        return "--"
    value, unit = float(n), "B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            break
        value /= 1000
    text = f"{value:.0f} {unit}" if unit == "B" or value >= 100 else f"{value:.1f} {unit}"
    return local_units(text)


def pick_folder(parent: tk.Misc, start: str) -> Optional[str]:
    """The desktop's folder dialog (kdialog on Plasma), Tk's as a fallback."""
    if shutil.which("kdialog"):
        try:
            done = subprocess.run(["kdialog", "--getexistingdirectory", start, "--title",
                                   APP_NAME], capture_output=True, text=True, timeout=600)
            return done.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    from tkinter import filedialog
    return filedialog.askdirectory(parent=parent, title=APP_NAME, initialdir=start) or None


def call_helper(args: List[str], stdin: Optional[str] = None) -> Tuple[int, str]:
    """Run the root helper through pkexec (one password per session). As root, or with
    SPARK_BACKUP_DIRECT set (tests), it runs in this process instead."""
    if os.geteuid() == 0 or os.environ.get("SPARK_BACKUP_DIRECT"):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from . import helper
        old_stdin, out, err = os.sys.stdin, io.StringIO(), io.StringIO()
        os.sys.stdin = io.StringIO(stdin or "")
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = helper.main(list(args))
        finally:
            os.sys.stdin = old_stdin
        return code, (err.getvalue() or out.getvalue()).strip()
    path = HELPER if os.path.exists(HELPER) else shutil.which("spark-backup-helper") or HELPER
    done = subprocess.run(["pkexec", path, *args], input=stdin, capture_output=True, text=True,
                          timeout=900)
    if done.returncode in (126, 127) and not done.stderr.strip():
        return 126, t("msg.cancelled")
    text = (done.stderr or done.stdout).strip()
    return done.returncode, text.splitlines()[-1] if text else ""


class Worker:
    """Runs slow things (pkexec, lsblk) off the UI thread."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.results: "queue.Queue[Tuple[Callable, Any, Optional[BaseException]]]" = queue.Queue()
        self.polling = False

    def run(self, fn: Callable[[], Any], done: Callable[[Any, Optional[BaseException]], None]) -> None:
        def job():
            try:
                self.results.put((done, fn(), None))
            except BaseException as exc:         # report it on the UI thread, don't lose it
                log.warning("background job failed: %s", exc)
                self.results.put((done, None, exc))
        threading.Thread(target=job, daemon=True).start()
        if not self.polling:
            self.polling = True
            self.root.after(60, self._poll)

    def _poll(self) -> None:
        try:
            while True:
                done, value, error = self.results.get_nowait()
                try:
                    done(value, error)
                except tk.TclError:
                    pass                          # the window closed meanwhile
        except queue.Empty:
            pass
        if threading.active_count() > 1 or not self.results.empty():
            self.root.after(120, self._poll)
        else:
            self.polling = False


class Model:
    """What the tabs show, read again on every sample."""

    def __init__(self):
        self.cfg: Dict[str, Any] = config.default()
        self.cfg_error = ""
        self.local: List[str] = []
        self.copies: List[str] = []
        self.drives: List[targets.Drive] = []
        self.drive: Optional[targets.Drive] = None
        self.copy_root: Optional[str] = None
        self.progress: Optional[Dict[str, Any]] = None
        self.last: Optional[Dict[str, Any]] = None
        self.layout = True            # /home is a Btrfs subvolume (read only check)
        self.snap_dir = ""


class App:
    def __init__(self, tab: Optional[str] = None, drives: Optional[List[targets.Drive]] = None,
                 source: str = ""):
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = self._detect_scale()
        try:
            self.root.tk.call("tk", "scaling", self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = self._pick_mono()
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.settings = load_json("config.json")
        self.glitch = Glitch(self.root, enabled=not reduced_motion())
        style_tables(self.root, self.font(9, False), self.font(8), self.px(24))

        self.runner = Runner()
        self.source = source
        self.fixed_drives = drives            # tests give the drives; the app lists them itself
        self.worker = Worker(self.root)
        self.model = Model()
        if drives is not None:
            self.model.drives = drives
        self.views: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.visible = True
        self._tick_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self._drives_busy = False
        self._drives_at = 0.0
        self._build()
        self.take_sample()
        self.show(tab if tab in TABS else (self.settings.get("tab") if
                  self.settings.get("tab") in TABS else "backups"), glitch=False)
        self.root.deiconify()
        self.root.bind("<Map>", self._mapped, add="+")
        self.root.bind("<Unmap>", self._unmapped, add="+")
        self.glitch.add(self.title, self.mark, self.strip)
        self._tick_id = self.root.after(INTERVAL_MS, self._tick)
        self.refresh_drives()

    # — look —
    def _detect_scale(self) -> float:
        forced = os.environ.get("SPARK_BACKUP_SCALE")
        if forced:
            try:
                return max(0.5, min(4.0, float(forced)))
            except ValueError:
                pass
        if shutil.which("xrdb"):
            try:
                out = subprocess.run(["xrdb", "-query"], capture_output=True, text=True,
                                     timeout=3).stdout
                match = re.search(r"^Xft\.dpi:\s*([0-9.]+)", out, re.M)
                if match:
                    return max(1.0, min(4.0, float(match.group(1)) / 96))
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        try:
            return max(1.0, min(4.0, self.root.winfo_fpixels("1i") / 96))
        except tk.TclError:
            return 1.0

    def _pick_mono(self) -> str:
        path = os.path.join(cache_dir(), "font")
        try:
            with open(path, encoding="utf-8") as f:
                name = f.read().strip()
            if name and tkfont.Font(self.root, family=name).actual("family") == name:
                return name
        except OSError:
            pass
        name = pick_mono(self.root)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(name)
        except OSError:
            pass
        return name

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

    def _on_tk_error(self, exc_type, exc_value, exc_tb) -> None:
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(t("status.crashed"), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self) -> None:
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(700), px(480))
        icon = self._load_icon()
        if icon is not None:
            root.iconphoto(True, icon)
            self._icon = icon
        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK BACKUP", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7), anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        self.set_status(t("status.ready"), T["accent"])
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.tabs = TabBar(root, [(k, t(f"tab.{k}")) for k in TABS], self.show, self.font(9), px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r"\d+x\d+(\+-?\d+\+-?\d+)?", geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{min(px(980), int(sw * 0.8))}x{min(px(660), int(sh * 0.85))}")

    def _load_icon(self) -> Optional[tk.PhotoImage]:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in (f"{APP_SLUG}-64.png", f"{APP_SLUG}-256.png"):
            path = os.path.join(here, "icons", name)
            if os.path.isfile(path):
                try:
                    return tk.PhotoImage(master=self.root, file=path)
                except tk.TclError:
                    pass
        return None

    def set_status(self, text: str, colour: str = "", hold_ms: int = 0) -> None:
        self.status.config(text="● " + text.upper(), fg=colour or T["accent"])
        if self._status_id:
            self.root.after_cancel(self._status_id)
            self._status_id = None
        if hold_ms:
            self._status_id = self.root.after(
                hold_ms, lambda: self.set_status(t("status.ready"), T["accent"]))

    # — tabs —
    def view(self, tab: str) -> tk.Frame:
        if tab not in self.views:
            if tab == "backups":
                from .backupsview import BackupsView
                self.views[tab] = BackupsView(self)
            elif tab == "browse":
                from .browseview import BrowseView
                self.views[tab] = BrowseView(self)
            else:
                from .settingsview import SettingsView
                self.views[tab] = SettingsView(self)
        return self.views[tab]

    def show(self, tab: str, glitch: bool = True) -> None:
        if tab == self.tab:
            return
        old = self.views.get(self.tab) if self.tab else None
        if old is not None:
            old.pack_forget()
        self.tab = tab
        self.settings["tab"] = tab
        self.tabs.select(tab)
        view = self.view(tab)
        view.pack(fill="both", expand=True)
        if tab == "settings":
            self.refresh_drives()
        view.refresh()
        if glitch:
            self.glitch.now(self.title)

    # — sampling —
    def backup(self) -> Backup:
        return Backup(self.model.cfg, self.runner, source=self.source,
                      drives=lambda: self.model.drives)

    def take_sample(self) -> None:
        m = self.model
        try:
            m.cfg, m.cfg_error = config.load(), ""
        except config.ConfigError as exc:
            m.cfg, m.cfg_error = config.default(), str(exc)
        backup = self.backup()
        m.layout = backup.fs.is_subvolume(backup.source)
        m.snap_dir = backup.snap_dir
        m.local = backup.local()
        m.drive = targets.find(m.drives, m.cfg["target"]["uuid"]) if m.cfg.get("target") else None
        m.copy_root, m.copies = None, []
        if m.drive is not None and m.drive.mountpoint and m.drive.usable:
            m.copy_root = targets.backup_root(m.drive.mountpoint, backup.host)
            m.copies = backup.copy_names(m.copy_root, m.drive.method, check=False)
        m.progress = state.read_progress()
        m.last = state.last_run()
        self.set_busy(m.progress)

    def set_busy(self, progress: Optional[Dict[str, Any]]) -> None:
        if progress:
            phase = progress.get("phase", "")
            key = f"status.{phase}" if phase in ("snapshot", "copy", "prune") else "status.working"
            self.set_status(t(key), T["gold"])
        elif self.status.cget("text").lower().startswith("● " + t("status.working").lower()[:4]) \
                or any(self.status.cget("text").lower() == "● " + t(f"status.{k}").lower()
                       for k in ("snapshot", "copy", "prune", "working")):
            self.set_status(t("status.ready"), T["accent"])

    def refresh_drives(self) -> None:
        import time
        if self.fixed_drives is not None or self._drives_busy:
            return
        self._drives_busy = True
        self._drives_at = time.time()

        def done(value, error):
            self._drives_busy = False
            if error is None and value is not None:
                self.model.drives = value
            view = self.views.get(self.tab) if self.tab else None
            if view is not None:
                view.refresh()

        self.worker.run(lambda: targets.list_drives(self.runner, self.source or "/home"), done)

    def _tick(self) -> None:
        import time
        self._tick_id = None
        if not self.visible:
            return
        self.take_sample()
        if time.time() - self._drives_at > DRIVES_EVERY_S:
            self.refresh_drives()
        view = self.views.get(self.tab)
        if view is not None:
            view.refresh()
        self._tick_id = self.root.after(INTERVAL_MS, self._tick)

    def _unmapped(self, event) -> None:
        if event.widget is self.root and self.visible:
            self.visible = False
            if self._tick_id:
                self.root.after_cancel(self._tick_id)
                self._tick_id = None

    def _mapped(self, event) -> None:
        if event.widget is self.root and not self.visible:
            self.visible = True
            if self._tick_id is None:
                self._tick_id = self.root.after(50, self._tick)

    # — actions that need root —
    def helper(self, args: List[str], done: Callable[[int, str], None],
               stdin: Optional[str] = None) -> None:
        self.set_status(t("status.password"), T["gold"])

        def finished(value, error):
            if error is not None:
                code, message = 1, str(error)
            else:
                code, message = value
            self.set_status(t("status.done") if code == 0 else t("status.failed"),
                            T["accent"] if code == 0 else T["pink"], hold_ms=4000)
            self.take_sample()
            done(code, message)

        self.worker.run(lambda: call_helper(args, stdin), finished)

    # — closing —
    def close(self) -> None:
        try:
            self.settings["geometry"] = self.root.geometry()
            save_json("config.json", self.settings)
        except tk.TclError:
            pass
        self.glitch.stop()
        self.visible = False
        if self._tick_id:
            try:
                self.root.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def next_text(cfg: Dict[str, Any], now: Optional[dt.datetime] = None) -> str:
    from . import schedule
    if not cfg.get("enabled"):
        return t("tile.off")
    when = schedule.next_run(cfg, now or dt.datetime.now())
    return when.strftime("%a %H:%M") if (when - (now or dt.datetime.now())).days < 6 \
        else when.strftime("%Y-%m-%d %H:%M")
