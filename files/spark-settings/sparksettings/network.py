"""Network through nmcli (terse mode): Wi-Fi, wired, and VPN connections."""

from typing import Dict, List

from .core import out, run


def split_terse(line: str) -> List[str]:
    """nmcli -t separates fields with ':' and writes a literal one as '\\:'."""
    fields, cur, i = [], '', 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ':':
            fields.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    fields.append(cur)
    return fields


class Wifi:
    def __init__(self, active: bool, ssid: str, signal: int, security: str):
        self.active, self.ssid, self.signal, self.security = active, ssid, signal, security

    @property
    def secured(self) -> bool:
        return self.security not in ('', '--')


def parse_wifi(text: str) -> List[Wifi]:
    best: Dict[str, Wifi] = {}
    for line in text.splitlines():
        f = split_terse(line)
        if len(f) < 4 or not f[1]:
            continue
        w = Wifi(f[0] == 'yes', f[1], int(f[2] or 0), f[3])
        old = best.get(w.ssid)
        if old is None or w.active or (not old.active and w.signal > old.signal):
            best[w.ssid] = w
    return sorted(best.values(), key=lambda w: (not w.active, -w.signal))


def wifi_list(rescan: bool = False) -> List[Wifi]:
    return parse_wifi(out(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL,SECURITY', 'dev', 'wifi',
                           'list', '--rescan', 'yes' if rescan else 'auto'], timeout=25))


def wifi_enabled() -> bool:
    return out(['nmcli', 'radio', 'wifi']).strip() == 'enabled'


def set_wifi(on: bool) -> bool:
    return run(['nmcli', 'radio', 'wifi', 'on' if on else 'off'])[0] == 0


def connect_wifi(ssid: str, password: str = '') -> str:
    """'' when it worked, else nmcli's own message."""
    cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
    if password:
        cmd += ['password', password]
    rc, _, err = run(cmd, timeout=40)
    return '' if rc == 0 else (err.strip() or "could not connect")


class Device:
    def __init__(self, name: str, type_: str, state: str, connection: str):
        self.name, self.type, self.state, self.connection = name, type_, state, connection


def devices() -> List[Device]:
    devs = []
    for line in out(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'dev']).splitlines():
        f = split_terse(line)
        if len(f) >= 4:
            devs.append(Device(*f[:4]))
    return devs


class Connection:
    def __init__(self, name: str, type_: str, device: str):
        self.name, self.type, self.device = name, type_, device

    @property
    def active(self) -> bool:
        return bool(self.device)


def vpns() -> List[Connection]:
    rows = []
    for line in out(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'con', 'show']).splitlines():
        f = split_terse(line)
        if len(f) >= 3 and f[1] in ('vpn', 'wireguard'):
            rows.append(Connection(f[0], f[1], f[2]))
    return rows


def vpn_up(name: str, up: bool) -> str:
    rc, _, err = run(['nmcli', 'con', 'up' if up else 'down', name], timeout=40)
    return '' if rc == 0 else (err.strip() or "failed")


def vpn_import(path: str) -> str:
    kind = 'openvpn' if path.lower().endswith('.ovpn') else 'wireguard'
    rc, _, err = run(['nmcli', 'con', 'import', 'type', kind, 'file', path])
    return '' if rc == 0 else (err.strip() or "could not import")

