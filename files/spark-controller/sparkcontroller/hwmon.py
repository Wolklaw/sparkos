"""Fans and temperatures from the kernel's hwmon tree (/sys/class/hwmon).

Reading needs no privileges. Writing a fan's pwm needs root, which only the daemon has.
The root folder is a parameter so the tests can point it at a fake tree."""

import os
import re
from typing import Dict, List, Optional

ROOT = "/sys/class/hwmon"

# pwmN_enable values the kernel documents: 0 full speed, 1 manual. Anything else (2 automatic,
# 5 "smart fan IV" on Nuvoton chips) is the chip's own control. We save what we found before
# taking over and write it back afterwards, so we never assume which one a board uses.
MANUAL = 1


def read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return None


def read_int(path: str) -> Optional[int]:
    text = read(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def write(path: str, value: int) -> None:
    with open(path, "w", encoding="ascii") as f:
        f.write(str(int(value)))


def _numbers(folder: str, prefix: str, suffix: str) -> List[int]:
    pattern = re.compile(rf"^{prefix}(\d+){suffix}$")
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        match = pattern.match(name)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


CHIP_NAMES = (
    (re.compile(r"^(nct|it8|f718|w836|sch5|asus_wmi_sensors|asus-ec)"), "Motherboard"),
    (re.compile(r"^amdgpu"), "GPU"),
    (re.compile(r"^(nouveau|nvidia)"), "GPU"),
    (re.compile(r"^(k10temp|zenpower|coretemp)"), "CPU"),
    (re.compile(r"^nvme"), "NVMe drive"),
)


def friendly_chip(name: str) -> str:
    for pattern, label in CHIP_NAMES:
        if pattern.match(name):
            return label
    return name


class Chip:
    def __init__(self, path: str, name: str):
        self.path, self.name = path, name


class TempSensor:
    def __init__(self, key: str, label: str, chip: str, path: str):
        self.key, self.label, self.chip, self.path = key, label, chip, path

    def read(self) -> Optional[float]:
        raw = read_int(self.path)
        if raw is None or raw <= -127000 or raw > 250000:
            return None
        return raw / 1000.0


class HwmonFan:
    """One fan header or fan: its speed, and (when the chip allows) its pwm."""
    kind = "hwmon"

    def __init__(self, key: str, label: str, chip: str, rpm_path: Optional[str],
                 pwm_path: Optional[str], enable_path: Optional[str], pwm_max: int = 255):
        self.key, self.label, self.chip = key, label, chip
        self.rpm_path, self.pwm_path, self.enable_path = rpm_path, pwm_path, enable_path
        self.pwm_max = pwm_max or 255

    @property
    def controllable(self) -> bool:
        return bool(self.pwm_path and self.enable_path and os.path.exists(self.pwm_path)
                    and os.path.exists(self.enable_path))

    def rpm(self) -> Optional[int]:
        return read_int(self.rpm_path) if self.rpm_path else None

    def duty(self) -> Optional[float]:
        raw = read_int(self.pwm_path) if self.pwm_path else None
        return None if raw is None else round(100.0 * raw / self.pwm_max, 1)

    def mode(self) -> Optional[int]:
        return read_int(self.enable_path) if self.enable_path else None

    # — what only the daemon does —
    def takeover(self) -> Optional[int]:
        """Switch to manual and return the mode the fan was in (None if unreadable)."""
        original = self.mode()
        write(self.enable_path, MANUAL)
        return original

    def set_duty(self, percent: float) -> None:
        percent = max(0.0, min(100.0, percent))
        write(self.pwm_path, round(percent * self.pwm_max / 100.0))

    def release(self, original: Optional[int]) -> None:
        """Give the fan back: write the mode it had, or the kernel's 'automatic' (2) when we
        don't know. Never leaves it in manual."""
        if not self.enable_path:
            return
        value = original if original not in (None, MANUAL) else 2
        try:
            write(self.enable_path, value)
        except OSError:
            if value != 0:                      # a chip without 2: full speed is the safe fallback
                write(self.enable_path, 0)


class Hwmon:
    def __init__(self, root: str = ROOT):
        self.root = root

    def chips(self) -> List[Chip]:
        try:
            names = sorted(os.listdir(self.root),
                           key=lambda n: (len(n), n))      # hwmon2 before hwmon10
        except OSError:
            return []
        chips = []
        for entry in names:
            path = os.path.join(self.root, entry)
            name = read(os.path.join(path, "name"))
            if name:
                chips.append(Chip(path, name))
        return chips

    def _keys(self, chips: List[Chip]) -> Dict[str, str]:
        """A name for each chip that survives reboots, when hwmon numbers move: the chip's own
        name, with #2, #3 added when a PC has several of one kind (two NVMe drives)."""
        seen: Dict[str, int] = {}
        keys = {}
        for chip in chips:
            seen[chip.name] = seen.get(chip.name, 0) + 1
            n = seen[chip.name]
            keys[chip.path] = chip.name if n == 1 else f"{chip.name}#{n}"
        return keys

    def temps(self) -> List[TempSensor]:
        chips = self.chips()
        keys = self._keys(chips)
        out = []
        for chip in chips:
            for n in _numbers(chip.path, "temp", "_input"):
                label = read(os.path.join(chip.path, f"temp{n}_label")) or f"temp{n}"
                out.append(TempSensor(f"{keys[chip.path]}/temp{n}",
                                      f"{friendly_chip(chip.name)} {label}", chip.name,
                                      os.path.join(chip.path, f"temp{n}_input")))
        return out

    def fans(self) -> List[HwmonFan]:
        chips = self.chips()
        keys = self._keys(chips)
        out = []
        for chip in chips:
            rpms = _numbers(chip.path, "fan", "_input")
            pwms = _numbers(chip.path, "pwm", "")
            for n in sorted(set(rpms) | set(pwms)):
                where = friendly_chip(chip.name)
                label = read(os.path.join(chip.path, f"fan{n}_label"))
                title = f"{where} {label}" if label else f"{where} fan {n}"
                if where == "GPU" and not label:
                    title = "GPU fan" if n == 1 else f"GPU fan {n}"
                pwm = os.path.join(chip.path, f"pwm{n}") if n in pwms else None
                enable = os.path.join(chip.path, f"pwm{n}_enable")
                pwm_max = read_int(os.path.join(chip.path, f"pwm{n}_max")) or 255
                out.append(HwmonFan(
                    f"{keys[chip.path]}/fan{n}", title, chip.name,
                    os.path.join(chip.path, f"fan{n}_input") if n in rpms else None,
                    pwm, enable if pwm else None, pwm_max))
        return out

    # — temperature sources the curves use —
    def _pick(self, chip_pattern: str, labels: List[str]) -> Optional[TempSensor]:
        regex = re.compile(chip_pattern)
        candidates = [s for s in self.temps() if regex.match(s.chip)]
        for wanted in labels:
            for sensor in candidates:
                if sensor.label.lower().endswith(wanted):
                    return sensor
        return candidates[0] if candidates else None

    def cpu_sensor(self) -> Optional[TempSensor]:
        return self._pick(r"^(k10temp|zenpower|coretemp)$",
                          ["tctl", "tdie", "package id 0"])

    def gpu_sensor(self) -> Optional[TempSensor]:
        return self._pick(r"^(amdgpu|nouveau)$", ["edge", "junction"])

    def source_temps(self) -> Dict[str, Optional[float]]:
        cpu, gpu = self.cpu_sensor(), self.gpu_sensor()
        values: Dict[str, Optional[float]] = {
            "cpu": cpu.read() if cpu else None,
            "gpu": gpu.read() if gpu else None,
        }
        # "max" needs every sensor that exists to answer: a missing reading must not hide a hot CPU
        present = [v for v, sensor in ((values["cpu"], cpu), (values["gpu"], gpu)) if sensor]
        values["max"] = max(present) if present and None not in present else None
        return values
