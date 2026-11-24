"""The window: header, tabs, a read of firewalld every few seconds, and the list of changes that
wait for Apply. Reading needs no password; Apply asks once (polkit) and sends the whole list to
the helper."""

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, INTERVAL_MS, VERSION, ops as opsmod
from .fw import Firewall, Network, Snapshot, Zone
from .log import cache_dir, config_dir, log
from .text import t
from .ui import TabBar, style_tables
from .widgets import T, Glitch, GlitchText, Mark, Strip, WolkButton, pick_mono

TABS = ("overview", "rules", "ports")
HELPER = "/usr/libexec/spark-firewall-helper"

Sender = Callable[[List[Dict[str, Any]]], None]


def reduced_motion() -> bool:
    if os.environ.get("SPARK_FIREWALL_REDUCED_MOTION", "").lower() in ("1", "true", "yes"):
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


def send_with_pkexec(ops: List[Dict[str, Any]]) -> None:
    """Run the helper through pkexec (as root already: directly). Raises PermissionError when
    the password prompt is cancelled, RuntimeError with the helper's own sentence on failure."""
    ops = opsmod.validate(ops)
    helper = HELPER if os.path.exists(HELPER) else shutil.which("spark-firewall-helper") or HELPER
    argv = [helper, "apply"] if os.geteuid() == 0 else ["pkexec", helper, "apply"]
    done = subprocess.run(argv, input=json.dumps({"ops": ops}), capture_output=True, text=True,
                          timeout=300)
    if done.returncode in (126, 127) and not done.stderr.strip().startswith("spark-firewall"):
        raise PermissionError(t("apply.cancelled"))
    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"exit {done.returncode}")


class Pending:
    """Changes made in the window and not applied yet. One entry per thing: toggling a rule
    back to what the firewall already does removes the entry instead of adding another."""

    def __init__(self):
        self.items: Dict[Tuple[str, ...], Dict[str, Any]] = {}

    @staticmethod
    def key(op: Dict[str, Any]) -> Tuple[str, ...]:
        kind = op["op"]
        if kind == "service":
            return (kind, op["zone"], op["name"])
        if kind == "port":
            return (kind, op["zone"], op["port"])
        if kind == "network-zone":
            return (kind, op["device"])
        return (kind,)

    def set(self, op: Dict[str, Any], same_as_now: bool) -> None:
        op = opsmod.validate_op(op)
        key = self.key(op)
        if same_as_now:
            self.items.pop(key, None)
        else:
            self.items[key] = op

    def get(self, *key: str) -> Optional[Dict[str, Any]]:
        return self.items.get(tuple(key))

    def ops(self) -> List[Dict[str, Any]]:
        return list(self.items.values())

    def clear(self) -> None:
        self.items.clear()

    def __len__(self) -> int:
        return len(self.items)


class App:
    def __init__(self, firewall: Optional[Firewall] = None, tab: Optional[str] = None,
                 sender: Optional[Sender] = None):
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

        self.fw = firewall or Firewall()
        self.sender: Sender = sender or send_with_pkexec
        self.snap = Snapshot()
        self.pending = Pending()
        self.zone_name = ""            # the zone the Rules and Ports tabs work on
        self.busy = False
        self.reading = False
        self.fail: Optional[str] = None     # the helper's last complaint, until the next change
        self.views: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.visible = True
        self._tick_id: Optional[str] = None
        self._status_id: Optional[str] = None
        self._results: List[Tuple[Callable, Any, Optional[BaseException]]] = []
        self._build()
        self.read(wait=True)
        self.show(tab if tab in TABS else (self.settings.get("tab") if
                  self.settings.get("tab") in TABS else "overview"), glitch=False)
        self.root.deiconify()
        self.root.bind("<Map>", self._mapped, add="+")
        self.root.bind("<Unmap>", self._unmapped, add="+")
        self.glitch.add(self.title, self.mark, self.strip)
        self._tick_id = self.root.after(INTERVAL_MS, self._tick)

    # — look —
    def _detect_scale(self) -> float:
        forced = os.environ.get("SPARK_FIREWALL_SCALE")
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
        self.title = GlitchText(col, "SPARK FIREWALL", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7), anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.tabs = TabBar(root, [(k, t(f"tab.{k}")) for k in TABS], self.show, self.font(9), px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")
        # The Apply bar sits under the pages and only shows while changes are waiting
        self.bar = tk.Frame(root, bg=T["panel"], highlightthickness=1,
                            highlightbackground=T["line2"])
        self.bar_text = tk.Label(self.bar, text="", font=self.font(8), fg=T["gold"],
                                 bg=T["panel"], anchor="w")
        self.bar_text.pack(side="left", padx=px(12), pady=px(8))
        self.apply_button = WolkButton(self.bar, t("apply.apply"), self.apply, self.font(8),
                                       "primary", padx=px(12), pady=px(5))
        self.apply_button.pack(side="right", padx=(px(8), px(12)), pady=px(6))
        self.revert_button = WolkButton(self.bar, t("apply.revert"), self.revert, self.font(8),
                                        "ghost", padx=px(12), pady=px(5))
        self.revert_button.pack(side="right", pady=px(6))
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        self.set_status(t("status.watching"), T["accent"])
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r"\d+x\d+(\+-?\d+\+-?\d+)?", geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{min(px(1000), int(sw * 0.8))}x{min(px(680), int(sh * 0.85))}")

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

    # — background work: one thread at a time, results handled on the UI thread —
    def work(self, fn: Callable[[], Any], done: Callable[[Any, Optional[BaseException]], None]):
        import threading

        def job():
            try:
                self._results.append((done, fn(), None))
            except BaseException as exc:         # report it on the UI thread
                log.warning("background job failed: %s", exc)
                self._results.append((done, None, exc))
        threading.Thread(target=job, daemon=True).start()
        self.root.after(80, self._poll)

    def _poll(self) -> None:
        while self._results:
            done, value, error = self._results.pop(0)
            try:
                done(value, error)
            except tk.TclError:
                pass                              # the window closed meanwhile
        if self._results or self.busy or self.reading:
            self.root.after(120, self._poll)

    # — reading firewalld —
    def read(self, wait: bool = False) -> None:
        """Read firewalld and the networks. At start (wait=True) the first read is done here,
        so the first thing on screen is real; later reads run in the background."""
        if self.reading:
            return
        self.reading = True
        if wait:
            self._took(self.fw.snapshot(self.zone_name or None), None)
            return
        self.work(lambda: self.fw.snapshot(self.zone_name or None), self._took)

    def _took(self, snap, error) -> None:
        self.reading = False
        if error is not None or snap is None:
            log.warning("could not read the firewall: %s", error)
            return
        self.snap = snap
        zones = list(snap.zone)
        if self.zone_name not in snap.zone:
            first = next((n.zone for n in snap.networks if n.zone in snap.zone), "")
            self.zone_name = first or (snap.default_zone if snap.default_zone in snap.zone
                                       else (zones[0] if zones else ""))
        self._bar()
        view = self.views.get(self.tab) if self.tab else None
        if view is not None:
            view.refresh()

    def zone(self) -> Zone:
        return self.snap.zone.get(self.zone_name) or Zone(self.zone_name)

    def choose_zone(self, name: str) -> None:
        self.zone_name = name
        self.read()
        view = self.views.get(self.tab) if self.tab else None
        if view is not None:
            view.refresh()

    # — what the window shows, with the waiting changes counted in —
    def service_on(self, zone: str, name: str) -> bool:
        waiting = self.pending.get("service", zone, name)
        if waiting is not None:
            return waiting["add"]
        info = self.snap.zone.get(zone)
        return bool(info) and name in info.services

    def port_state(self, zone: str, port: str) -> str:
        """'open', 'closed', 'adding' or 'removing'."""
        waiting = self.pending.get("port", zone, port)
        info = self.snap.zone.get(zone)
        there = bool(info) and port in info.ports
        if waiting is not None:
            return "adding" if waiting["add"] else "removing"
        return "open" if there else "closed"

    def set_service(self, zone: str, name: str, add: bool) -> None:
        now = name in (self.snap.zone[zone].services if zone in self.snap.zone else [])
        self.pending.set({"op": "service", "zone": zone, "name": name, "add": add}, add == now)
        self.changed()

    def set_port(self, zone: str, port: str, add: bool) -> None:
        port = opsmod.normalise_port(port)
        now = port in (self.snap.zone[zone].ports if zone in self.snap.zone else [])
        self.pending.set({"op": "port", "zone": zone, "port": port, "add": add}, add == now)
        self.changed()

    def set_network_zone(self, net: Network, zone: str) -> None:
        self.pending.set({"op": "network-zone", "device": net.device,
                          "connection": net.uuid, "zone": zone}, zone == net.zone)
        self.changed()

    def set_default_zone(self, zone: str) -> None:
        self.pending.set({"op": "default-zone", "zone": zone}, zone == self.snap.default_zone)
        self.changed()

    def network_zone(self, net: Network) -> str:
        waiting = self.pending.get("network-zone", net.device)
        return waiting["zone"] if waiting else net.zone

    def default_zone(self) -> str:
        waiting = self.pending.get("default-zone")
        return waiting["zone"] if waiting else self.snap.default_zone

    def changed(self) -> None:
        self._bar()
        view = self.views.get(self.tab) if self.tab else None
        if view is not None:
            view.refresh()

    def _bar(self) -> None:
        count = len(self.pending)
        if count:
            self.bar_text.config(text=t("apply.waiting", n=count))
            self.apply_button.set_enabled(not self.busy)
            if not self.bar.winfo_ismapped():
                self.bar.pack(fill="x", before=self.body)
        elif self.bar.winfo_ismapped():
            self.bar.pack_forget()

    # — changing it —
    def apply(self) -> None:
        if self.busy or not len(self.pending):
            return
        ops = self.pending.ops()
        self.send(ops, t("status.applying"), on_ok=self.pending.clear)

    def revert(self) -> None:
        self.pending.clear()
        self.changed()

    def send(self, ops: List[Dict[str, Any]], status: str, on_ok: Callable[[], None] = lambda: None):
        """Send operations to the helper in the background and read the firewall again."""
        if self.busy:
            return
        self.busy = True
        self.apply_button.set_enabled(False)
        self.set_status(status, T["gold"])

        def done(_value, error) -> None:
            self.busy = False
            self.fail = None
            if error is None:
                on_ok()
                self.set_status(t("status.done"), T["accent"], hold_ms=4000)
                self.glitch.now(self.title)
            elif isinstance(error, PermissionError):
                self.set_status(t("status.cancelled"), T["gold"], hold_ms=5000)
            else:
                log.error("the firewall change failed: %s", error)
                self.fail = str(error)
                self.set_status(t("status.failed"), T["pink"], hold_ms=8000)
                self.glitch.now(self.title, self.mark, strong=True)
            self.read()
            self.changed()
        self.work(lambda: self.sender(ops), done)

    # — tabs —
    def view(self, tab: str) -> tk.Frame:
        if tab not in self.views:
            if tab == "overview":
                from .overviewview import OverviewView
                self.views[tab] = OverviewView(self)
            elif tab == "rules":
                from .rulesview import RulesView
                self.views[tab] = RulesView(self)
            else:
                from .portsview import PortsView
                self.views[tab] = PortsView(self)
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

    def _tick(self) -> None:
        self._tick_id = None
        if not self.visible:
            return
        if not self.busy:
            self.read()
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
