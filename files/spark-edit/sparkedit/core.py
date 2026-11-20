"""Folders, settings, the log, and the recent files list."""

import json
import locale
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)

DEFAULTS: Dict[str, Any] = {
    "font_size": 11,
    "wrap": True,
    "reopen_session": True,
    "glitch": True,
    "tab_width": 4,
}
RECENT_MAX = 20


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


def load_json(folder: str, name: str) -> Any:
    try:
        with open(os.path.join(folder, name), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", name, exc)
    return None


def save_json(folder: str, name: str, data: Any) -> bool:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    path = os.path.join(folder, name)
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(path + '.tmp', path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write %s: %s", name, exc)
        return False


def load_settings() -> Dict[str, Any]:
    data = load_json(config_dir(), 'config.json')
    settings = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in DEFAULTS and type(value) is type(DEFAULTS[key]):
                settings[key] = value
    settings['font_size'] = max(6, min(48, settings['font_size']))
    settings['tab_width'] = max(1, min(16, settings['tab_width']))
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    save_json(config_dir(), 'config.json', settings)


def load_recent() -> List[str]:
    data = load_json(config_dir(), 'recent.json')
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, str)][:RECENT_MAX]


def add_recent(path: str) -> List[str]:
    recent = [p for p in load_recent() if p != path]
    recent.insert(0, path)
    del recent[RECENT_MAX:]
    save_json(config_dir(), 'recent.json', recent)
    return recent


def remove_recent(path: str) -> List[str]:
    recent = [p for p in load_recent() if p != path]
    save_json(config_dir(), 'recent.json', recent)
    return recent


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_EDIT_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']"""
    lang = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


def home_short(path: str) -> str:
    """/home/me/notes/a.txt -> ~/notes/a.txt"""
    home = os.path.expanduser('~')
    if home and home != '/' and (path == home or path.startswith(home + os.sep)):
        return '~' + path[len(home):]
    return path


def size_text(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
