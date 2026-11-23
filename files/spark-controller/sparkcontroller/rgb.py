"""RGB lighting. NZXT and other USB controllers go through liquidctl (Python library); the
ASUS Aura controller and peripherals (mice, keyboards, RAM) go through OpenRGB's command line.
Settings are saved per device and applied again at login (spark-controller --apply-rgb).

OpenRGB is run as a program (not linked): it detects devices for several seconds, so callers
run discover() and apply() off the UI thread. The command runner is a parameter for the tests.
"""

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from .liquid import LiquidHub
from .log import config_dir, log

EFFECTS = ("static", "breathing", "fade", "spectrum", "off")
SPEEDS = ("slow", "normal", "fast")
DEFAULT_SETTING = {"effect": "static", "color": "#3de8c8", "speed": "normal"}

LIQUIDCTL_MODES = {"static": "fixed", "breathing": "breathing", "fade": "fading",
                   "spectrum": "spectrum-wave", "off": "off"}
LIQUIDCTL_SPEEDS = {"slow": "slower", "normal": "normal", "fast": "faster"}
# OpenRGB names modes per device; take the first of these that the device lists.
OPENRGB_MODES = {
    "static": ("Static", "Direct", "Custom"),
    "breathing": ("Breathing", "Breathe"),
    "fade": ("Fading", "Pulse", "Flashing", "Breathing"),
    "spectrum": ("Spectrum Cycle", "Rainbow Wave", "Rainbow", "Color Cycle", "Cycle"),
    "off": ("Off",),
}
OPENRGB_SPEEDS = {"slow": 20, "normal": 50, "fast": 90}


def clean_setting(data: Any) -> Dict[str, str]:
    setting = dict(DEFAULT_SETTING)
    if isinstance(data, dict):
        if data.get("effect") in EFFECTS:
            setting["effect"] = data["effect"]
        if isinstance(data.get("color"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", data["color"]):
            setting["color"] = data["color"].lower()
        if data.get("speed") in SPEEDS:
            setting["speed"] = data["speed"]
    return setting


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


# — saved settings —

def settings_path() -> str:
    return os.path.join(config_dir(), "rgb.json")


def load_saved(path: str = "") -> Dict[str, Dict[str, str]]:
    try:
        with open(path or settings_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    devices = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(devices, dict):
        return {}
    return {str(k): clean_setting(v) for k, v in devices.items()}


def save_saved(devices: Dict[str, Dict[str, str]], path: str = "") -> None:
    path = path or settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"version": 1, "devices": devices}, f, indent=2)
        os.replace(path + ".tmp", path)
    except OSError as exc:
        log.warning("could not save %s: %s", path, exc)


# — OpenRGB's output —

_MODE_TOKEN = re.compile(r"\[([^\]]+)\]|'([^']+)'|\"([^\"]+)\"|(\S+)")


def parse_openrgb_list(text: str) -> List[Dict[str, Any]]:
    """`openrgb --list-devices`: each device is '<n>: <name>' followed by indented fields,
    one of them 'Modes: [Direct] Static Breathing 'Spectrum Cycle''."""
    devices: List[Dict[str, Any]] = []
    for line in text.splitlines():
        head = re.match(r"^(\d+): (.+?)\s*$", line)
        if head:
            devices.append({"index": int(head.group(1)), "name": head.group(2),
                            "type": "", "modes": []})
            continue
        if not devices:
            continue
        field = re.match(r"^\s+(Type|Modes):\s*(.*)$", line)
        if not field:
            continue
        if field.group(1) == "Type":
            devices[-1]["type"] = field.group(2).strip()
        else:
            devices[-1]["modes"] = [next(g for g in m.groups() if g)
                                    for m in _MODE_TOKEN.finditer(field.group(2))]
    return devices


def pick_openrgb_mode(effect: str, modes: List[str]) -> Optional[str]:
    lowered = {m.lower(): m for m in modes}
    for wanted in OPENRGB_MODES.get(effect, ()):
        if wanted.lower() in lowered:
            return lowered[wanted.lower()]
    return None


def openrgb_args(index: int, setting: Dict[str, str], modes: List[str]) -> List[str]:
    """The arguments for one device. 'Off' without an Off mode is a static black."""
    effect = setting["effect"]
    mode = pick_openrgb_mode(effect, modes)
    color = "000000" if effect == "off" else setting["color"].lstrip("#")
    if mode is None and effect == "off":
        mode = pick_openrgb_mode("static", modes)
    if mode is None:
        raise ValueError(f"no {effect} mode on this device")
    args = ["--device", str(index), "--mode", mode]
    if effect != "spectrum":
        args += ["--color", color]
    if effect in ("breathing", "fade", "spectrum"):
        args += ["--speed", str(OPENRGB_SPEEDS[setting["speed"]])]
    return args


Runner = Callable[[List[str], float], Tuple[int, str]]


def run_command(args: List[str], timeout: float) -> Tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 127, str(exc)


class RgbDevice:
    def __init__(self, key: str, name: str, backend: str, kind: str = "",
                 modes: Optional[List[str]] = None, index: int = 0, liquid: Any = None):
        self.key, self.name, self.backend, self.kind = key, name, backend, kind
        self.modes = modes or []
        self.index, self.liquid = index, liquid


class RgbManager:
    def __init__(self, hub: Optional[LiquidHub] = None, runner: Runner = run_command,
                 openrgb: Optional[str] = None):
        self.hub = hub
        self.runner = runner
        self.openrgb = openrgb if openrgb is not None else (shutil.which("openrgb") or "")
        self.errors: List[str] = []

    def discover(self, use_openrgb: bool = True) -> List[RgbDevice]:
        self.errors = []
        found: List[RgbDevice] = []
        if self.hub is not None:
            for device in self.hub.devices:
                if device.color_channels:
                    found.append(RgbDevice(device.key, device.name, "liquidctl", "USB controller",
                                           liquid=device))
            if self.hub.error:
                self.errors.append(self.hub.error)
        owned = [d.name.lower() for d in found]
        if use_openrgb and self.openrgb:
            code, out = self.runner([self.openrgb, "--list-devices"], 90)
            if code != 0:
                self.errors.append(f"openrgb: {out.strip().splitlines()[-1] if out.strip() else code}")
            for item in parse_openrgb_list(out if code == 0 else ""):
                if any(w in item["name"].lower() for w in ("nzxt",)) and any(
                        "nzxt" in o for o in owned):
                    continue                    # liquidctl already drives it
                found.append(RgbDevice(f"openrgb:{item['name']}", item["name"], "openrgb",
                                       item["type"], item["modes"], item["index"]))
        elif use_openrgb:
            self.errors.append("openrgb is not installed")
        return found

    def apply(self, device: RgbDevice, setting: Dict[str, str]) -> Optional[str]:
        """Apply one setting. Returns None on success or a short error."""
        return self.apply_many([(device, setting)]).get(device.key)

    def apply_many(self, jobs: List[Tuple[RgbDevice, Dict[str, str]]]) -> Dict[str, Optional[str]]:
        results: Dict[str, Optional[str]] = {}
        openrgb_args_all: List[str] = []
        openrgb_jobs: List[RgbDevice] = []
        for device, raw in jobs:
            setting = clean_setting(raw)
            try:
                if device.backend == "liquidctl":
                    self._apply_liquidctl(device, setting)
                    results[device.key] = None
                else:
                    openrgb_args_all += openrgb_args(device.index, setting, device.modes)
                    openrgb_jobs.append(device)
            except Exception as exc:
                results[device.key] = str(exc) or exc.__class__.__name__
                log.warning("rgb: %s: %s", device.name, results[device.key])
        if openrgb_jobs:
            code, out = self.runner([self.openrgb] + openrgb_args_all, 120)
            message = None if code == 0 else (out.strip().splitlines() or ["failed"])[-1]
            for device in openrgb_jobs:
                results[device.key] = message
            if message:
                log.warning("rgb: openrgb: %s", message)
        return results

    def _apply_liquidctl(self, device: RgbDevice, setting: Dict[str, str]) -> None:
        dev = device.liquid
        if not dev.connect():
            raise RuntimeError(dev.error or "can't open the device")
        dev.initialise()
        mode = LIQUIDCTL_MODES[setting["effect"]]
        color = hex_to_rgb(setting["color"])
        colors = [] if setting["effect"] in ("spectrum", "off") else [list(color)]
        channel = "sync" if "sync" in dev.color_channels else dev.color_channels[0]
        dev.driver.set_color(channel, mode, colors, speed=LIQUIDCTL_SPEEDS[setting["speed"]])


def apply_saved(manager: RgbManager, saved: Optional[Dict[str, Dict[str, str]]] = None,
                use_openrgb: bool = True) -> Dict[str, Optional[str]]:
    """What runs at login: find the devices, apply what was saved for each."""
    saved = load_saved() if saved is None else saved
    if not saved:
        return {}
    devices = manager.discover(use_openrgb and any(k.startswith("openrgb:") for k in saved))
    jobs = [(d, saved[d.key]) for d in devices if d.key in saved]
    return manager.apply_many(jobs) if jobs else {}
