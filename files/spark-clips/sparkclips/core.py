"""Folders, settings, the log, and numbers for people."""

import json
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units

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


def runtime_dir(create: bool = True) -> str:
    """$XDG_RUNTIME_DIR/spark-clips (the control socket); /tmp/spark-clips-<uid> without one."""
    base = os.environ.get('XDG_RUNTIME_DIR')
    path = os.path.join(base, APP_SLUG) if base else f'/tmp/{APP_SLUG}-{os.getuid()}'
    if create:
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
        except OSError:
            pass
    return path


def socket_path() -> str:
    return os.path.join(runtime_dir(), 'control.sock')


def buffer_dir(create: bool = True) -> str:
    """Where the one-second pieces live: RAM (tmpfs), so hours of play never reach the SSD."""
    path = os.environ.get('SPARK_CLIPS_SHM') or f'/dev/shm/{APP_SLUG}-{os.getuid()}'
    if create:
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
        except OSError:
            pass
    return path


def clips_dir() -> str:
    return os.path.join(home(), 'Videos', 'Clips')


def fake() -> bool:
    """SPARK_CLIPS_FAKE=1: a test pattern and a test tone instead of the portal and the
    sound server. The tests and the self-test use it; it is not a setting."""
    return os.environ.get('SPARK_CLIPS_FAKE', '') == '1'


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
    if os.environ.get('SPARK_CLIPS_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


def human_size(n: float) -> str:
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


def duration_text(seconds: float) -> str:
    """72.4 -> '1:12', 3725 -> '1:02:05'."""
    s = int(max(0, seconds + 0.5))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def stamp(when: Optional[float] = None) -> str:
    """The time part of a new file name: 2026-11-24 14.05.09 (colons break on Windows drives)."""
    return time.strftime('%Y-%m-%d %H.%M.%S', time.localtime(when))


def file_when(mtime: float) -> str:
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))


def clean_name(text: str) -> str:
    """A file or folder name someone typed or a game reported, made safe: no folders, no
    leading dots, no control marks."""
    text = re.sub(r'[\x00-\x1f/\\:*?"<>|]', ' ', text or '').lstrip(' .').rstrip(' .')
    return re.sub(r'\s+', ' ', text)[:100]


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

LENGTHS = (15, 30, 60, 120, 300)
FRAME_RATES = ('30', '60', '120', 'native')
CODECS = ('h264', 'hevc')
BITRATES = (10, 20, 40, 60)               # Mbit/s at 2560x1440 and 60 fps
SIZES = ('native', '1080', '720')

DEFAULTS: Dict[str, Any] = {
    'keep': True,               # "Keep a replay": the buffer may run
    'only_in_game': True,       # ... only while a game is running
    'seconds': 30,
    'sound': True,              # what the speakers play, as the first audio track
    'mic': False,               # the microphone, as a second track
    'codec': 'h264',
    'fps': '60',
    'bitrate': 40,
    'size': 'native',
}
CHOICES = {'seconds': LENGTHS, 'fps': FRAME_RATES, 'codec': CODECS, 'bitrate': BITRATES,
           'size': SIZES}


def settings_path() -> str:
    return os.path.join(config_dir(), 'config.json')


def load_settings() -> Dict[str, Any]:
    out = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, default in DEFAULTS.items():
                value = data.get(key, default)
                if isinstance(value, bool) != isinstance(default, bool):
                    continue
                if not isinstance(value, type(default)):
                    continue
                if key in CHOICES and value not in CHOICES[key]:
                    continue
                out[key] = value
    except (OSError, ValueError):
        pass
    return out


def save_settings(values: Dict[str, Any]) -> None:
    try:
        tmp = settings_path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({k: values.get(k, v) for k, v in DEFAULTS.items()}, f, indent=1)
        os.replace(tmp, settings_path())
    except OSError as exc:
        log.warning("couldn't save settings: %s", exc)


def portal_path() -> str:
    return os.path.join(config_dir(), 'portal.json')


def load_portal() -> Dict[str, Any]:
    """What the share portal told us last time: the restore token (so the share dialog shows
    once) and a description of the screen it picked. Written by the service only."""
    try:
        with open(portal_path(), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_portal(data: Dict[str, Any]) -> None:
    try:
        tmp = portal_path() + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, portal_path())
    except OSError as exc:
        log.warning("couldn't save the portal token: %s", exc)
