"""The phones paired with this PC, in ~/.local/share/spark-link/devices.json (0600): each one's
id, name, pinned certificate and what was last heard from it."""

import base64
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .config import data_dir, load_json, save_json
from .identity import FP_RE, ID_RE, der_to_pem, fingerprint_der


def clean_name(value, fallback: str = 'Phone', limit: int = 64) -> str:
    """A device or app name fit to show: no control or format characters, one line."""
    if not isinstance(value, str):
        return fallback
    text = ''.join(' ' if unicodedata.category(c)[0] in 'CZ' and c != ' ' else c
                   for c in value if unicodedata.category(c) not in ('Cf', 'Co', 'Cn'))
    text = ' '.join(text.split())[:limit]
    return text or fallback


@dataclass
class Device:
    id: str
    name: str
    fp: str
    cert: str                              # base64 DER
    paired_at: float = 0.0
    last_seen: float = 0.0
    battery: Optional[int] = None
    charging: Optional[bool] = None
    always_accept: bool = False
    extra: Dict = field(default_factory=dict)

    def pem(self) -> str:
        return der_to_pem(base64.b64decode(self.cert))


class Devices:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(data_dir(), 'devices.json')
        self.items: Dict[str, Device] = {}
        self.load()

    def load(self) -> None:
        data = load_json(self.path)
        self.items = {}
        for raw in data.get('devices', []) if isinstance(data.get('devices'), list) else []:
            try:
                dev = Device(**{k: raw[k] for k in Device.__dataclass_fields__ if k in raw})
                der = base64.b64decode(dev.cert, validate=True)
            except (TypeError, KeyError, ValueError):
                continue
            # the pin is the certificate itself: never trust a stored fp that doesn't match it
            if ID_RE.match(dev.id) and FP_RE.match(dev.fp) and fingerprint_der(der) == dev.fp:
                self.items[dev.id] = dev

    def save(self) -> None:
        save_json(self.path, {'devices': [asdict(d) for d in self.items.values()]})

    def all(self) -> List[Device]:
        return sorted(self.items.values(), key=lambda d: -d.paired_at)

    def by_id(self, device_id: str) -> Optional[Device]:
        return self.items.get(device_id)

    def by_fp(self, fp: str) -> Optional[Device]:
        for dev in self.items.values():
            if dev.fp == fp:
                return dev
        return None

    def add(self, device_id: str, name: str, cert_der: bytes) -> Device:
        fp = fingerprint_der(cert_der)
        for other in [d for d in self.items.values() if d.fp == fp and d.id != device_id]:
            del self.items[other.id]               # one certificate, one device
        dev = Device(id=device_id, name=clean_name(name), fp=fp,
                     cert=base64.b64encode(cert_der).decode('ascii'), paired_at=time.time(),
                     last_seen=time.time())
        self.items[device_id] = dev
        self.save()
        return dev

    def remove(self, device_id: str) -> bool:
        if self.items.pop(device_id, None) is None:
            return False
        self.save()
        return True

    def cadata(self) -> str:
        return ''.join(d.pem() for d in self.items.values())

    def __len__(self) -> int:
        return len(self.items)
