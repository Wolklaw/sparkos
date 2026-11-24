"""The window: header, tabs, a sample every two seconds, and background work."""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import (APP_CLASS, APP_NAME, APP_SLUG, INTERVAL_MS, RUN_DIR, VERSION, config)
from .hwmon import Hwmon
from .liquid import LiquidHub
from .log import cache_dir, config_dir, log
from .mouse import RatbagBackend
from .rgb import RgbManager
from .text import t
from .ui import TabBar, style_tables
from .widgets import T, Glitch, GlitchText, Mark, Strip, pick_mono

TABS = ("overview", "fans", "rgb", "mouse", "pads", "drivers")
HELPER = "/usr/libexec/spark-controller-helper"
STATE_STALE_S = 10.0


def reduced_motion() -> bool:
    if os.environ.get("SPARK_CONTROLLER_REDUCED_MOTION", "").lower() in ("1", "true", "yes"):
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


def read_daemon_state(run_dir: str = "") -> Optional[Dict[str, Any]]:
    """What the fan service last wrote, or None when it isn't running (or stopped writing)."""
    path = os.path.join(run_dir or os.environ.get("SPARK_CONTROLLER_RUN_DIR") or RUN_DIR,
                        "state.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - float(data.get("time", 0)) > STATE_STALE_S:
            return None
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def save_fan_config(cfg: Dict[str, Any]) -> None:
    """Write the fan configuration. As the user this goes through pkexec and the helper (which
    validates it again); as root, or when SPARK_CONTROLLER_CONFIG points at a file (tests,
    development), it writes the file itself."""
    cfg = config.validate(cfg)
    if os.geteuid() == 0 or os.environ.get("SPARK_CONTROLLER_CONFIG"):
        config.save(cfg)
        return
    helper = HELPER if os.path.exists(HELPER) else shutil.which("spark-controller-helper") or HELPER
    done = subprocess.run(["pkexec", helper, "install-config"], input=json.dumps(cfg),
                          capture_output=True, text=True, timeout=300)
    if done.returncode == 126:
        raise PermissionError(t("fans.cancelled"))
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip().splitlines()[-1]
                           if (done.stderr or done.stdout).strip() else f"exit {done.returncode}")


class Worker:
    """Runs slow things (USB, OpenRGB, fwupd, pkexec) off the UI thread."""

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


class Snapshot:
    def __init__(self):
        self.temps: Dict[str, Optional[float]] = {}
        self.fans: List[Tuple[Any, Optional[int], Optional[float]]] = []   # fan, rpm, duty
        self.daemon: Optional[Dict[str, Any]] = None
        self.sensors: List[Tuple[str, Optional[float]]] = []


class App:
    def __init__(self, hwmon: Optional[Hwmon] = None, tab: Optional[str] = None,
                 use_usb: bool = True, mouse_backend: Optional[RatbagBackend] = None):
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

        self.hwmon = hwmon or Hwmon(os.environ.get("SPARK_CONTROLLER_HWMON") or "/sys/class/hwmon")
        self.hub: Optional[LiquidHub] = None
        self.rgb: Optional[RgbManager] = None
        self.use_usb = use_usb
        self.mouse_backend = mouse_backend or RatbagBackend()
        self.worker = Worker(self.root)
        self.snap = Snapshot()
        self.views: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.visible = True
        self._tick_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self._hub_busy = False
        self._build()
        self.take_sample()
        self.show(tab if tab in TABS else (self.settings.get("tab") if
                  self.settings.get("tab") in TABS else "overview"), glitch=False)
        self.root.deiconify()
        self.root.bind("<Map>", self._mapped, add="+")
        self.root.bind("<Unmap>", self._unmapped, add="+")
        self.glitch.add(self.title, self.mark, self.strip)
        self._tick_id = self.root.after(INTERVAL_MS, self._tick)
        self.worker.run(self._open_usb, self._usb_ready)

    # — look —
    def _detect_scale(self) -> float:
        forced = os.environ.get("SPARK_CONTROLLER_SCALE")
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
        root.minsize(px(760), px(520))
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
        self.title = GlitchText(col, "SPARK CONTROLLER", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7), anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        self.set_status(t("status.watching"), T["accent"])
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
            root.geometry(f"{min(px(1040), int(sw * 0.8))}x{min(px(700), int(sh * 0.85))}")

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
                hold_ms, lambda: self.set_status(t("status.watching"), T["accent"]))

    # — USB, in the background —
    def _open_usb(self) -> Tuple[Optional[LiquidHub], RgbManager]:
        hub = LiquidHub() if self.use_usb else None
        return hub, RgbManager(hub)

    def _usb_ready(self, value, error) -> None:
        if error is not None or value is None:
            log.warning("USB scan failed: %s", error)
            self.rgb = RgbManager(None)
        else:
            self.hub, self.rgb = value
        for view in self.views.values():
            ready = getattr(view, "usb_ready", None)
            if ready:
                ready()

    # — tabs —
    def view(self, tab: str) -> tk.Frame:
        if tab not in self.views:
            if tab == "overview":
                from .overviewview import OverviewView
                self.views[tab] = OverviewView(self)
            elif tab == "fans":
                from .fansview import FansView
                self.views[tab] = FansView(self)
            elif tab == "rgb":
                from .rgbview import RgbView
                self.views[tab] = RgbView(self)
            elif tab == "mouse":
                from .mouseview import MouseView
                self.views[tab] = MouseView(self)
            elif tab == "pads":
                from .padsview import PadsView
                self.views[tab] = PadsView(self)
            else:
                from .driversview import DriversView
                self.views[tab] = DriversView(self)
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
        view.refresh()
        if glitch:
            self.glitch.now(self.title)

    # — sampling —
    def take_sample(self) -> None:
        snap = Snapshot()
        snap.temps = self.hwmon.source_temps()
        if self.hub is not None:
            snap.temps["liquid"] = self.hub.liquid_temp()
        fans = list(self.hwmon.fans())
        if self.hub is not None:
            fans += self.hub.fans()
        snap.fans = [(f, f.rpm(), f.duty()) for f in fans]
        snap.sensors = [(s.label, s.read()) for s in self.hwmon.temps()]
        snap.daemon = read_daemon_state()
        self.snap = snap

    def _tick(self) -> None:
        self._tick_id = None
        if not self.visible:
            return
        self.take_sample()
        view = self.views.get(self.tab)
        if view is not None:
            view.refresh()
        if self.hub is not None and self.hub.devices and not self._hub_busy \
                and any(d.speed_channels for d in self.hub.devices):
            self._hub_busy = True
            self.worker.run(self.hub.refresh, lambda *_: setattr(self, "_hub_busy", False))
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

    # — closing —
    def close(self) -> None:
        try:
            self.settings["geometry"] = self.root.geometry()
            save_json("config.json", self.settings)
        except tk.TclError:
            pass
        if self.hub is not None:
            self.hub.close()
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
