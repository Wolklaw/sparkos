"""Folders, settings, the log, and numbers for people."""

import json
import logging
import os
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from . import APP_NAME, APP_SLUG, DEFAULT_DURATION_S, DEFAULT_HOTKEY, VERSION
from .lang import ui_language

log = logging.getLogger(APP_SLUG)


def home() -> str:
    return os.path.expanduser('~')


def _xdg(variable: str, fallback: str) -> str:
    return os.environ.get(variable) or os.path.join(home(), fallback)


def _dir(variable: str, fallback: str, create: bool = True) -> str:
    path = os.path.join(_xdg(variable, fallback), APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir() -> str:
    return _dir('XDG_CONFIG_HOME', '.config')


def data_dir() -> str:
    return _dir('XDG_DATA_HOME', os.path.join('.local', 'share'))


def state_dir() -> str:
    return _dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir() -> str:
    return _dir('XDG_CACHE_HOME', '.cache')


def imported_dir() -> str:
    """Where imported recordings (Windows PresentMon CSVs) are copied to."""
    return os.path.join(data_dir(), 'imported')


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
    if os.environ.get('SPARK_BENCH_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    try:
        with open(os.path.join(_xdg('XDG_CONFIG_HOME', '.config'), 'spark', 'appearance.json'),
                  encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


# ─── JSON files written whole or not at all ───────────────────

def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def write_text(path: str, text: str) -> None:
    """Write through a temporary file in the same folder, so a crash never leaves half a file."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: str, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


# ─── Settings ─────────────────────────────────────────────────

DEFAULTS: Dict[str, Any] = {
    'hotkey': DEFAULT_HOTKEY,
    'duration': DEFAULT_DURATION_S,
    'output_folder': '',         # empty: the default (see mangohud.default_output_folder)
    'sound': True,
    'folders': [],               # more folders with recordings: [{"path": ..., "system": ...}]
    'games': {},                 # game key -> the name shown (two keys, one name: one game)
    'baseline': '',              # the system the others are compared with
}


def settings_path() -> str:
    return os.path.join(config_dir(), 'settings.json')


def load_settings() -> Dict[str, Any]:
    stored = read_json(settings_path(), {})
    out = dict(DEFAULTS)
    for key, value in stored.items():
        if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
            out[key] = value
    return out


def save_settings(settings: Dict[str, Any]) -> None:
    write_json(settings_path(), {k: settings[k] for k in DEFAULTS if k in settings})


# ─── Numbers for people ───────────────────────────────────────

def num(value: Optional[float], digits: int = 1) -> str:
    """12.3 in English, 12,3 in French; a dash when there is nothing."""
    if value is None:
        return "—"
    text = f"{value:.{digits}f}"
    return text.replace('.', ',') if ui_language() == 'fr' else text


def pct(value: Optional[float]) -> str:
    """+12.3% (English) or +12,3 % (French)."""
    if value is None:
        return "—"
    text = f"{value:+.1f}"
    return text.replace('.', ',') + " %" if ui_language() == 'fr' else text + "%"


def seconds(value: Optional[float]) -> str:
    """1:30 for 90 s."""
    if value is None:
        return "—"
    s = int(round(value))
    return f"{s // 60}:{s % 60:02d}"


def day_clock(epoch: Optional[float]) -> str:
    """Date and time in this PC's own time zone (the owner's: Eastern)."""
    return "—" if epoch is None else time.strftime('%Y-%m-%d %H:%M', time.localtime(epoch))


def short_path(path: str) -> str:
    h = home()
    return '~' + path[len(h):] if path == h or path.startswith(h + os.sep) else path
