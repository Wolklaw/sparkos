"""Settings, log, and formatting numbers for people."""

import json
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units

log = logging.getLogger(APP_SLUG)


def _xdg_dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir() -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir() -> str:
    return _xdg_dir('XDG_CACHE_HOME', '.cache')


def setup_logging() -> None:
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=256 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


def load_json(name: str) -> Dict[str, Any]:
    try:
        with open(os.path.join(config_dir(), name), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", name, exc)
    return {}


def save_json(name: str, data: Dict[str, Any]) -> None:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    path = os.path.join(config_dir(), name)
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(path + '.tmp', path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write %s: %s", name, exc)


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_MONITOR_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


# ─── Numbers for people ───────────────────────────────────────

def _size(n: Optional[float], digits: int = 1) -> str:
    """Bytes, in the units Windows uses (1 KB = 1024 bytes)."""
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.{digits}f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def size(n: Optional[float], digits: int = 1) -> str:
    """Bytes, in the units Windows uses (1 KB = 1024 bytes)."""
    return local_units(_size(n, digits))


def _rate(n: Optional[float]) -> str:
    if n is None:
        return "—"
    if n < 0.05 * 1024 * 1024:
        return "0 MB/s" if n < 1024 else f"{n / 1024:.0f} KB/s"
    return f"{n / 1024 / 1024:.1f} MB/s"


def rate(n: Optional[float]) -> str:
    return local_units(_rate(n))


def _bits(n: Optional[float]) -> str:
    """Network speed in bits per second, like Windows."""
    if n is None:
        return "—"
    b = n * 8
    for unit in ("bps", "Kbps", "Mbps", "Gbps"):
        if b < 1000 or unit == "Gbps":
            return f"{b:.0f} {unit}" if unit == "bps" else f"{b:.1f} {unit}"
        b /= 1000
    return f"{b:.1f} Gbps"


def bits(n: Optional[float]) -> str:
    """Network speed in bits per second, like Windows."""
    return local_units(_bits(n))


def _pct(n: Optional[float], digits: int = 1) -> str:
    return "—" if n is None else f"{n:.{digits}f}%"


def pct(n: Optional[float], digits: int = 1) -> str:
    return local_units(_pct(n, digits))


def _mhz(n: Optional[float]) -> str:
    if n is None:
        return "—"
    return f"{n / 1000:.2f} GHz" if n >= 1000 else f"{n:.0f} MHz"


def mhz(n: Optional[float]) -> str:
    return local_units(_mhz(n))


def temp(n: Optional[float]) -> str:
    return "—" if n is None else f"{n:.0f} °C"


def watts(n: Optional[float]) -> str:
    return "—" if n is None else f"{n:.0f} W"


def uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{d}:{h:02d}:{m:02d}:{s:02d}"
