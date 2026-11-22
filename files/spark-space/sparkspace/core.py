"""Folders, the log, and numbers for people."""

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units, ui_language

log = logging.getLogger(APP_SLUG)


def home() -> str:
    return os.path.expanduser('~')


def data_home() -> str:
    return os.environ.get('XDG_DATA_HOME') or os.path.join(home(), '.local', 'share')


def _dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(home(), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir(create: bool = True) -> str:
    return _dir('XDG_CONFIG_HOME', '.config', create)


def state_dir(create: bool = True) -> str:
    return _dir('XDG_STATE_HOME', os.path.join('.local', 'state'), create)


def cache_dir(create: bool = True) -> str:
    return _dir('XDG_CACHE_HOME', '.cache', create)


def setup_logging() -> None:
    if log.handlers:
        return
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
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_SPACE_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def human_size(n: float) -> str:
    """1536 -> '1.5 KB' (powers of 1024, the way file managers count), in the PC's language."""
    n = float(max(0, n))
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            if unit == 'B':
                text = f"{int(n)} B"
            elif n < 10:
                text = f"{n:.1f} {unit}"
            else:
                text = f"{n:.0f} {unit}"
            return local_units(text)
        n /= 1024
    return local_units(f"{n:.0f} TB")         # not reached


def pct(part: float, whole: float) -> str:
    value = 100.0 * part / whole if whole > 0 else 0.0
    text = f"{value:.1f}%" if value < 10 else f"{value:.0f}%"
    return local_units(text)


def count(n: int) -> str:
    """12345 -> '12,345' in English, '12 345' in French."""
    text = f"{n:,}"
    return text.replace(',', ' ') if ui_language() == 'fr' else text


def home_short(path: str) -> str:
    """'/home/me/x' (or the real '/var/home/me/x') -> '~/x'."""
    for h in (home(), os.path.realpath(home())):
        h = h.rstrip(os.sep)
        if path == h:
            return '~'
        if h and path.startswith(h + os.sep):
            return '~' + path[len(h):]
    return path
