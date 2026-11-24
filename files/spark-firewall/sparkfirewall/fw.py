"""Reading firewalld. Everything here only asks (firewall-cmd queries, nmcli, systemctl
is-enabled); nothing changes the firewall. Changes are built in ops.py and run by helper.py.

Every call goes through a runner, run(argv) -> (returncode, stdout, stderr), so the tests feed it
recorded output and no firewalld has to exist."""

import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

from .catalog import KNOWN_SERVICES

Runner = Callable[[List[str]], Tuple[int, str, str]]


def default_run(argv: List[str], timeout: float = 15.0) -> Tuple[int, str, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


class Zone:
    def __init__(self, name: str = ""):
        self.name = name
        self.target = ""
        self.interfaces: List[str] = []
        self.sources: List[str] = []
        self.services: List[str] = []
        self.ports: List[str] = []
        self.default = False
        self.active = False

    def __repr__(self) -> str:
        return f"Zone({self.name!r}, services={self.services}, ports={self.ports})"


class Network:
    def __init__(self, name: str, uuid: str, device: str, kind: str, zone: str):
        self.name, self.uuid, self.device, self.kind, self.zone = name, uuid, device, kind, zone


class Snapshot:
    def __init__(self):
        self.available = False          # firewall-cmd exists
        self.running = False
        self.at_boot: Optional[bool] = None
        self.default_zone = ""
        self.zones: List[str] = []
        self.zone: Dict[str, Zone] = {}
        self.networks: List[Network] = []
        self.services: List[str] = []   # every service firewalld defines
        self.service_ports: Dict[str, List[str]] = {}
        self.error = ""


def parse_zone(text: str) -> Zone:
    """The output of firewall-cmd --zone=NAME --list-all."""
    zone = Zone()
    lines = text.splitlines()
    if not lines:
        return zone
    head = re.match(r"^(\S+)(?:\s+\(([^)]*)\))?", lines[0])
    if head:
        zone.name = head.group(1)
        flags = [f.strip() for f in (head.group(2) or "").split(",")]
        zone.default, zone.active = "default" in flags, "active" in flags
    for line in lines[1:]:
        key, _sep, value = line.strip().partition(":")
        words = value.split()
        if key == "target":
            zone.target = value.strip()
        elif key == "interfaces":
            zone.interfaces = words
        elif key == "sources":
            zone.sources = words
        elif key == "services":
            zone.services = words
        elif key == "ports":
            zone.ports = words
    return zone


def parse_service(text: str) -> List[str]:
    """The ports of firewall-cmd --info-service=NAME ('47100/tcp', '27031-27036/udp')."""
    for line in text.splitlines():
        key, _sep, value = line.strip().partition(":")
        if key == "ports":
            return value.split()
    return []


def parse_port(spec: str) -> Optional[Tuple[int, int, str]]:
    match = re.fullmatch(r"(\d{1,5})(?:-(\d{1,5}))?/(tcp|udp|sctp|dccp)", spec.strip())
    if not match:
        return None
    low = int(match.group(1))
    high = int(match.group(2) or low)
    if not (1 <= low <= high <= 65535):
        return None
    return low, high, match.group(3)


def covered(ports: List[str], open_ports: List[str]) -> bool:
    """True when every port in `ports` already lies inside one of the open ranges. Fedora's
    desktop zone opens 1025-65535, and then a rule for a high port changes nothing."""
    ranges = [p for p in (parse_port(o) for o in open_ports) if p]
    wanted = [p for p in (parse_port(o) for o in ports) if p]
    if not wanted:
        return False
    return all(any(low <= w[0] and w[1] <= high and proto == w[2] for low, high, proto in ranges)
               for w in wanted)


def parse_active_zones(text: str) -> Dict[str, List[str]]:
    """firewall-cmd --get-active-zones: a zone name, then an indented 'interfaces:' line."""
    zones: Dict[str, List[str]] = {}
    current = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            current = line.strip().split()[0]
            zones[current] = []
        elif current and line.strip().startswith("interfaces:"):
            zones[current] = line.split(":", 1)[1].split()
    return zones


def parse_connections(text: str) -> List[Tuple[str, str, str, str]]:
    """nmcli -t -f NAME,UUID,TYPE,DEVICE connection show --active (colons in names are
    escaped as \\:). Loopback and devices without a name are left out."""
    rows = []
    for line in text.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) != 4:
            continue
        name, uuid, kind, device = (p.replace("\\:", ":") for p in parts)
        if device and device != "lo" and kind != "loopback":
            rows.append((name, uuid, kind, device))
    return rows


class Firewall:
    def __init__(self, run: Runner = default_run):
        self.run = run
        self._ports: Dict[str, List[str]] = {}

    def _out(self, *argv: str) -> Optional[str]:
        code, out, _err = self.run(list(argv))
        return out.strip() if code == 0 else None

    def snapshot(self, want: Optional[str] = None, has_cmd: Optional[bool] = None) -> Snapshot:
        snap = Snapshot()
        snap.available = shutil.which("firewall-cmd") is not None if has_cmd is None else has_cmd
        if not snap.available:
            snap.error = "firewall-cmd"
            return snap
        _code, state, _err = self.run(["systemctl", "is-enabled", "firewalld.service"])
        state = state.strip()      # "disabled" comes with a non-zero exit code
        snap.at_boot = state in ("enabled", "enabled-runtime") if state else None
        code, _out, _err = self.run(["firewall-cmd", "--state"])
        snap.running = code == 0
        snap.networks = self.networks()
        if not snap.running:
            return snap
        snap.default_zone = self._out("firewall-cmd", "--get-default-zone") or ""
        snap.zones = (self._out("firewall-cmd", "--get-zones") or "").split()
        snap.services = (self._out("firewall-cmd", "--get-services") or "").split()
        wanted_services = set(KNOWN_SERVICES)
        active = parse_active_zones(self._out("firewall-cmd", "--get-active-zones") or "")
        wanted = set(active) | {snap.default_zone} | ({want} if want else set())
        for name in sorted(n for n in wanted if n):
            text = self._out("firewall-cmd", f"--zone={name}", "--list-all")
            if text is not None:
                snap.zone[name] = parse_zone(text)
        for info in snap.zone.values():
            wanted_services.update(info.services)
        for name in sorted(wanted_services & set(snap.services)):
            snap.service_ports[name] = self.ports_of(name)
        for net in snap.networks:
            net.zone = self._out("firewall-cmd", f"--get-zone-of-interface={net.device}") or ""
        return snap

    def networks(self) -> List[Network]:
        text = self._out("nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show",
                         "--active")
        return [Network(n, u, d, k, "") for n, u, k, d in parse_connections(text or "")]

    def ports_of(self, service: str) -> List[str]:
        if service not in self._ports:
            self._ports[service] = parse_service(
                self._out("firewall-cmd", f"--info-service={service}") or "")
        return self._ports[service]
