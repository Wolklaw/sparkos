"""Folders, settings, the log, and the small formatting helpers every part uses."""

import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_SLUG
from .lang import local_units, ui_language

log = logging.getLogger(APP_SLUG)

DEFAULTS: Dict[str, Any] = {
    "view": "list",               # list | grid
    "sort": "name",               # name | modified | size | type
    "sort_reverse": False,
    "folders_first": True,
    "show_hidden": False,
    "thumbnails": True,
    "preview": False,             # the preview pane
    "sidebar": True,
    "zoom": 1.0,                  # grid tile size factor
    "pinned": [],                 # folders pinned to the sidebar
    "glitch": True,
    "confirm_trash": False,
    "geometry": None,
    "split": False,
}


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


def data_home() -> str:
    return os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'),
                                                           '.local', 'share')


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


def load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULTS)
    try:
        with open(os.path.join(config_dir(), 'settings.json'), encoding='utf-8') as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULTS and (DEFAULTS[key] is None or value is None
                                        or isinstance(value, type(DEFAULTS[key]))
                                        or (isinstance(DEFAULTS[key], float)
                                            and isinstance(value, int))):
                    settings[key] = value
    except (OSError, ValueError):
        pass
    if settings['view'] not in ('list', 'grid'):
        settings['view'] = 'list'
    if settings['sort'] not in ('name', 'modified', 'size', 'type'):
        settings['sort'] = 'name'
    settings['pinned'] = [p for p in settings['pinned'] if isinstance(p, str)]
    settings['zoom'] = max(0.6, min(2.5, float(settings['zoom'])))
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    path = os.path.join(config_dir(), 'settings.json')
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({k: settings.get(k, v) for k, v in DEFAULTS.items()}, f, indent=1)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("could not save settings: %s", exc)


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_FILES_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def home() -> str:
    return os.path.expanduser('~')


def home_short(path: str) -> str:
    """/home/me/notes -> ~/notes"""
    h = home()
    if h and h != '/' and (path == h or path.startswith(h + os.sep)):
        return '~' + path[len(h):]
    return path


def expand_path(text: str, base: Optional[str] = None) -> str:
    """What someone typed in the path bar: ~, $VARS, file:// links and relative paths."""
    text = text.strip()
    if text.startswith('file://'):
        from urllib.parse import unquote, urlparse
        text = unquote(urlparse(text).path)
    text = os.path.expandvars(os.path.expanduser(text))
    if not os.path.isabs(text):
        text = os.path.join(base or home(), text)
    return os.path.normpath(text)


def human_size(n: Optional[float], language: Optional[str] = None) -> str:
    if n is None:
        return ''
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            text = f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            return local_units(text, language)
        value /= 1024
    return str(n)


_MONTHS = {
    'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'),
    'fr': ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.',
           'nov.', 'déc.'),
}


def human_date(ts: Optional[float], now: Optional[float] = None,
               language: Optional[str] = None) -> str:
    """Today 14:05 / Yesterday 09:12 / 3 Mar 14:05 / 3 Mar 2023. 24-hour clock in both
    languages (Quebec uses it)."""
    if ts is None:
        return ''
    lang = language or ui_language()
    now = time.time() if now is None else now
    try:
        t = time.localtime(ts)
        n = time.localtime(now)
    except (OverflowError, OSError, ValueError):
        return ''
    clock = f"{t.tm_hour:02d}:{t.tm_min:02d}"
    if (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday):
        return ("Aujourd'hui " if lang == 'fr' else "Today ") + clock
    y = time.localtime(now - 86400)
    if (t.tm_year, t.tm_yday) == (y.tm_year, y.tm_yday):
        return ("Hier " if lang == 'fr' else "Yesterday ") + clock
    month = _MONTHS.get(lang, _MONTHS['en'])[t.tm_mon - 1]
    if t.tm_year == n.tm_year:
        return f"{t.tm_mday} {month} {clock}"
    return f"{t.tm_mday} {month} {t.tm_year}"


def full_date(ts: Optional[float]) -> str:
    if ts is None:
        return ''
    try:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return ''


def uniq(items: List[str]) -> List[str]:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
