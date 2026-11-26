"""Folders, the log, and numbers for people. Runs on Linux and on Windows."""

import logging
import json
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Optional

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units

log = logging.getLogger(APP_SLUG)
WINDOWS = os.name == 'nt'


def _dir(variable: str, fallback: str, create: bool = True) -> str:
    """XDG folders on Linux; on Windows everything goes under %APPDATA% or %LOCALAPPDATA%."""
    if WINDOWS:
        base = os.environ.get('APPDATA' if variable == 'XDG_CONFIG_HOME' else 'LOCALAPPDATA') \
            or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        path = os.path.join(base, APP_SLUG)
        if variable == 'XDG_STATE_HOME':
            path = os.path.join(path, 'log')
        elif variable == 'XDG_CACHE_HOME':
            path = os.path.join(path, 'cache')
    else:
        base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
        path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir(create: bool = False) -> str:
    """Where machines.toml lives. Spark Connect never writes machines.toml itself."""
    return _dir('XDG_CONFIG_HOME', '.config', create)


def config_path() -> str:
    return os.path.join(config_dir(), 'machines.toml')


def state_dir() -> str:
    return _dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir() -> str:
    return _dir('XDG_CACHE_HOME', '.cache')


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


def reduced_motion() -> bool:
    """True when animations are turned off in Spark Settings (appearance.json) or by env."""
    if os.environ.get('SPARK_CONNECT_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


# ─── Numbers for people ───────────────────────────────────────

def size(n: Optional[float], digits: int = 1) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(value) < 1000 or unit == 'TB':
            text = f"{value:.0f} {unit}" if unit == 'B' else f"{value:.{digits}f} {unit}"
            return local_units(text)
        value /= 1000
    return "—"


def rate(bps: Optional[float]) -> str:
    return "—" if bps is None else size(bps) + "/s"


def pct(value: Optional[float], digits: int = 0) -> str:
    return "—" if value is None else local_units(f"{value:.{digits}f}%")


def temp(c: Optional[float]) -> str:
    return "—" if c is None else local_units(f"{c:.0f} °C")


def duration(seconds: Optional[float]) -> str:
    """3 d 4 h, 5 h 12 min, 12 min, 40 s."""
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min"
    return f"{s} s"


def clock(epoch: Optional[float]) -> str:
    """HH:MM in this PC's own time zone (the owner's: Eastern)."""
    return "—" if epoch is None else time.strftime('%H:%M', time.localtime(epoch))


def date(epoch: Optional[float]) -> str:
    return "—" if epoch is None else time.strftime('%Y-%m-%d', time.localtime(epoch))


def day_clock(epoch: Optional[float]) -> str:
    return "—" if epoch is None else time.strftime('%Y-%m-%d %H:%M', time.localtime(epoch))
