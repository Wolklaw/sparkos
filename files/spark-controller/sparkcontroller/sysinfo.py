"""Versions of what the system image ships (kernel, Mesa, GPU firmware) and the BIOS the board
reports. Read-only. The image is atomic, so these change with a system update (Spark Update),
never one by one."""

import os
import platform
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

DMI = "/sys/class/dmi/id"


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def rpm_version(package: str) -> str:
    """'26.2.7-1.fc45' for an installed package, '' when it isn't installed."""
    try:
        done = subprocess.run(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}\n", package],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    lines = done.stdout.strip().splitlines()
    return lines[0].strip() if lines else ""


def bios(dmi: str = DMI) -> Dict[str, str]:
    return {
        "board": " ".join(x for x in (_read(os.path.join(dmi, "board_vendor")),
                                      _read(os.path.join(dmi, "board_name"))) if x),
        "version": _read(os.path.join(dmi, "bios_version")),
        "date": _read(os.path.join(dmi, "bios_date")),
        "vendor": _read(os.path.join(dmi, "bios_vendor")),
    }


def system_versions(rpm: Callable[[str], str] = rpm_version) -> List[Tuple[str, str]]:
    """(what, version) rows for the Drivers tab."""
    mesa = rpm("mesa-dri-drivers") or rpm("mesa-libGL")
    firmware = rpm("amd-gpu-firmware") or rpm("linux-firmware")
    rows = [("kernel", platform.release()),
            ("mesa", mesa),
            ("gpu_firmware", firmware)]
    return [(k, v or "") for k, v in rows]


def kernel_has_module(name: str, release: Optional[str] = None,
                      base: str = "/usr/lib/modules") -> bool:
    """Whether the running kernel ships a module (checks modules.builtin and modules.dep)."""
    release = release or platform.release()
    for table in ("modules.dep", "modules.builtin"):
        text = _read(os.path.join(base, release, table))
        for line in text.splitlines():
            path = line.split(":", 1)[0]
            leaf = os.path.basename(path).split(".")[0]
            if leaf == name:
                return True
    return False
