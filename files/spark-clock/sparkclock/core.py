"""Folders, the log, the clock's own formats."""

import logging
import json
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler

from . import APP_NAME, APP_SLUG, VERSION
from .lang import ui_language

log = logging.getLogger(APP_SLUG)


def home() -> str:
    return os.path.expanduser('~')


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
    """True when animations are turned off in Spark Settings (appearance.json) or by env."""
    if os.environ.get('SPARK_CLOCK_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


def lib_dir() -> str:
    """The folder the package lives in (sounds/ is next to it)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hms(seconds: float, tenths: bool = False) -> str:
    """3725 -> '1:02:05'; 65.4 -> '01:05' (hours only when there are some)."""
    seconds = max(0.0, seconds)
    whole = int(seconds)
    h, rest = divmod(whole, 3600)
    m, s = divmod(rest, 60)
    text = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if tenths:
        text += f".{int((seconds - whole) * 10)}"
    return text


def duration_words(seconds: float) -> str:
    """5400 -> '1 h 30 min', 90 -> '1 min 30 s' (the same abbreviations in both languages)."""
    whole = int(round(max(0, seconds)))
    h, rest = divmod(whole, 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} h")
    if m:
        parts.append(f"{m} min")
    if s and not h:
        parts.append(f"{s} s")
    return " ".join(parts) or "0 s"


def parse_duration(text: str) -> int:
    """'90' -> 90 s, '5m' -> 300, '1h30m' -> 5400, '1:30' -> 90, '1:02:03' -> 3723. 0 if not one."""
    text = (text or '').strip().lower().replace(' ', '')
    if not text:
        return 0
    if ':' in text:
        try:
            parts = [int(p) for p in text.split(':')]
        except ValueError:
            return 0
        if not 2 <= len(parts) <= 3 or min(parts) < 0:
            return 0
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if text.isdigit():
        return int(text)
    match = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m(?:in)?)?(?:(\d+)s)?', text)
    if not match or not any(match.groups()):
        return 0
    h, m, s = (int(g or 0) for g in match.groups())
    return h * 3600 + m * 60 + s


def now() -> float:
    return time.time()


__all__ = ['log', 'ui_language']
