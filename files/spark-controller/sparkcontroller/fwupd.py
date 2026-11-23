"""Firmware through fwupd (LVFS): list devices, find updates, install them.

Talks to fwupdmgr's JSON output. Installing goes through fwupd's own polkit prompt, so this
file never needs root. The runner is a parameter so the tests feed it recorded output.
"""

import json
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from .rgb import run_command

Runner = Callable[[List[str], float], Tuple[int, str]]
GENERIC = {"system firmware", "uefi device firmware", "tpm", "secure processor", "firmware"}


class Release:
    def __init__(self, data: Dict[str, Any]):
        self.version = str(data.get("Version", "") or "")
        self.summary = str(data.get("Summary", "") or "")
        self.description = _plain(str(data.get("Description", "") or ""))
        self.urgency = str(data.get("Urgency", "") or "")
        self.size = data.get("Size") if isinstance(data.get("Size"), int) else None
        self.remote = str(data.get("RemoteId", "") or "")


class FwDevice:
    def __init__(self, data: Dict[str, Any]):
        self.id = str(data.get("DeviceId", "") or "")
        self.name = str(data.get("Name", "") or "")
        self.vendor = str(data.get("Vendor", "") or "")
        self.version = str(data.get("Version", "") or "").strip()
        self.summary = str(data.get("Summary", "") or "")
        self.plugin = str(data.get("Plugin", "") or "")
        flags = data.get("Flags")
        self.flags: List[str] = [str(f) for f in flags] if isinstance(flags, list) else []
        releases = data.get("Releases")
        self.releases = [Release(r) for r in releases if isinstance(r, dict)] \
            if isinstance(releases, list) else []

    @property
    def title(self) -> str:
        """A name that says what the thing is: 'ASUS System Firmware', not 'System Firmware'."""
        if self.name.lower() in GENERIC and self.vendor and self.vendor.lower() != "unknown" \
                and not self.name.lower().startswith(self.vendor.lower()):
            return f"{self.vendor} {self.name}"
        return self.name

    @property
    def updatable(self) -> bool:
        return "updatable" in self.flags

    @property
    def needs_reboot(self) -> bool:
        return "needs-reboot" in self.flags

    @property
    def internal(self) -> bool:
        return "internal" in self.flags


def _plain(text: str) -> str:
    """LVFS descriptions are small XML (<p>, <li>); show them as plain lines."""
    import re
    text = re.sub(r"</(p|li|ul|ol)>", "\n", text)
    text = re.sub(r"<li>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _json_from(output: str) -> Dict[str, Any]:
    """fwupdmgr can print notices before the JSON; take from the first brace."""
    start = output.find("{")
    if start < 0:
        raise ValueError("no JSON in fwupdmgr's output")
    data, _end = json.JSONDecoder().raw_decode(output[start:])
    if not isinstance(data, dict):
        raise ValueError("unexpected JSON from fwupdmgr")
    return data


def parse_devices(output: str) -> List[FwDevice]:
    """Devices a person would recognise: a name and a version. Updatable ones first."""
    data = _json_from(output)
    devices = [FwDevice(d) for d in data.get("Devices", []) if isinstance(d, dict)]
    shown = [d for d in devices if d.name and d.version]
    return sorted(shown, key=lambda d: (not d.updatable, d.internal is False, d.title.lower()))


def parse_updates(output: str) -> List[FwDevice]:
    data = _json_from(output)
    return [d for d in (FwDevice(x) for x in data.get("Devices", []) if isinstance(x, dict))
            if d.releases]


class Fwupd:
    def __init__(self, runner: Runner = run_command, path: Optional[str] = None):
        self.runner = runner
        self.path = path if path is not None else (shutil.which("fwupdmgr") or "")

    @property
    def available(self) -> bool:
        return bool(self.path)

    def devices(self) -> List[FwDevice]:
        code, out = self.runner([self.path, "get-devices", "--json", "--no-authenticate"], 60)
        if code != 0 and "{" not in out:
            raise RuntimeError(_last_line(out) or "fwupdmgr failed")
        return parse_devices(out)

    def updates(self) -> List[FwDevice]:
        code, out = self.runner([self.path, "get-updates", "--json", "--no-authenticate"], 60)
        if code == 2 and "{" not in out:        # "nothing to update"
            return []
        if code != 0 and "{" not in out:
            raise RuntimeError(_last_line(out) or "fwupdmgr failed")
        return parse_updates(out)

    def refresh(self) -> None:
        """Fetch the newest firmware list from LVFS."""
        code, out = self.runner([self.path, "refresh", "--force"], 120)
        if code not in (0, 2):                  # 2: nothing new
            raise RuntimeError(_last_line(out) or "couldn't reach LVFS")

    def update(self) -> str:
        """Install every pending update. fwupd asks for authorisation itself; some updates
        finish at the next restart."""
        code, out = self.runner([self.path, "update", "-y", "--no-reboot-check"], 1800)
        if code != 0:
            raise RuntimeError(_last_line(out) or "the update failed")
        return _last_line(out)


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""
