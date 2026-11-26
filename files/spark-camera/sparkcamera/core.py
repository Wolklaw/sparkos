"""Folders, settings, the log, and numbers for people."""

import json
import logging
import os
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
    """True when animations are turned off in Spark Settings (appearance.json) or by env."""
    if os.environ.get('SPARK_CAMERA_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
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


# ─── Where files go ───

def photos_dir() -> str:
    return os.path.join(home(), 'Pictures', 'Camera')


def videos_dir() -> str:
    return os.path.join(home(), 'Videos', 'Camera')


def recordings_dir() -> str:
    return os.path.join(home(), 'Music', 'Recordings')


def duration_text(seconds: float) -> str:
    """72.4 -> '1:12', 3725 -> '1:02:05'."""
    s = int(max(0, seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def stamp(when=None) -> str:
    """The time part of a new file name: 2026-11-24 14.05.09 (colons break on Windows drives)."""
    import datetime
    return (when or datetime.datetime.now()).strftime('%Y-%m-%d %H.%M.%S')


def unique_path(folder: str, base: str, ext: str) -> str:
    """folder/base.ext, or folder/base 2.ext when that exists. Creates the folder."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} {n}{ext}")
        n += 1
    return path


# ─── Settings ───

DEFAULTS = {
    'camera': '', 'mode': '', 'mic': '', 'sound': True, 'mirror': True, 'countdown': 0,
    'video_format': '', 'voice_mic': '', 'voice_format': 'opus',
}


def settings_path() -> str:
    return os.path.join(config_dir(), 'settings.json')


def load_settings() -> dict:
    out = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, default in DEFAULTS.items():
                if key in data and isinstance(data[key], type(default)):
                    out[key] = data[key]
    except (OSError, ValueError):
        pass
    return out


def save_settings(values: dict) -> None:
    try:
        tmp = settings_path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({k: values.get(k, v) for k, v in DEFAULTS.items()}, f, indent=1)
        os.replace(tmp, settings_path())
    except OSError as exc:
        log.warning("couldn't save settings: %s", exc)
