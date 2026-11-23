"""Bluetooth through bluetoothctl."""

import re
from typing import List, Optional

from .core import out, run


class Device:
    def __init__(self, mac: str, name: str):
        self.mac, self.name = mac, name
        self.paired = self.connected = False
        self.battery: Optional[int] = None


def powered() -> Optional[bool]:
    text = out(['bluetoothctl', 'show'])
    if not text.strip() or 'No default controller' in text:
        return None
    return bool(re.search(r'Powered:\s*yes', text))


def set_power(on: bool) -> bool:
    return run(['bluetoothctl', 'power', 'on' if on else 'off'])[0] == 0


def parse_info(dev: Device, text: str) -> Device:
    dev.paired = bool(re.search(r'Paired:\s*yes', text))
    dev.connected = bool(re.search(r'Connected:\s*yes', text))
    m = re.search(r'Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)', text)
    dev.battery = int(m.group(1)) if m else None
    return dev


def devices() -> List[Device]:
    found = []
    for line in out(['bluetoothctl', 'devices']).splitlines():
        m = re.match(r'^Device\s+([0-9A-Fa-f:]{17})\s+(.*)$', line.strip())
        if m:
            found.append(parse_info(Device(m.group(1), m.group(2)),
                                    out(['bluetoothctl', 'info', m.group(1)])))
    return sorted(found, key=lambda d: (not d.connected, not d.paired, d.name.lower()))


def scan(seconds: int = 8) -> None:
    run(['bluetoothctl', '--timeout', str(seconds), 'scan', 'on'], timeout=seconds + 5)


def _act(verb: str, mac: str) -> str:
    rc, text, err = run(['bluetoothctl', verb, mac], timeout=40)
    failed = rc != 0 or 'Failed' in text
    return (text.strip().splitlines() or [err.strip() or "failed"])[-1] if failed else ''


def pair(mac: str) -> str:
    msg = _act('pair', mac)
    if not msg:
        run(['bluetoothctl', 'trust', mac])
        msg = _act('connect', mac)
    return msg


def connect(mac: str) -> str:
    return _act('connect', mac)


def disconnect(mac: str) -> str:
    return _act('disconnect', mac)


def forget(mac: str) -> str:
    return _act('remove', mac)
