"""Folders, settings, the log, the user's language, and numbers for people."""

import json
import locale
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units

log = logging.getLogger(APP_SLUG)


def home() -> str:
    return os.path.expanduser('~')


def xdg(variable: str, fallback: str) -> str:
    return os.environ.get(variable) or os.path.join(home(), fallback)


def _app_dir(variable: str, fallback: str, create: bool = True) -> str:
    path = os.path.join(xdg(variable, fallback), APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir() -> str:
    return _app_dir('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _app_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir(create: bool = True) -> str:
    return _app_dir('XDG_CACHE_HOME', '.cache', create)


def data_home() -> str:
    return xdg('XDG_DATA_HOME', os.path.join('.local', 'share'))


def data_dirs() -> List[str]:
    raw = os.environ.get('XDG_DATA_DIRS') or os.pathsep.join(['/usr/local/share', '/usr/share'])
    return [d for d in raw.split(os.pathsep) if d]


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
    if os.environ.get('SPARK_STORE_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    try:
        with open(os.path.join(xdg('XDG_CONFIG_HOME', '.config'), 'kdeglobals'),
                  encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']; the order the catalog's translations are tried in."""
    lang = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or \
        os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    if lang in ('C', 'POSIX'):
        return []
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


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


_UNITS = {'b': 1, 'bytes': 1, 'kb': 1000, 'kib': 1024, 'mb': 1000 ** 2, 'mib': 1024 ** 2,
          'gb': 1000 ** 3, 'gib': 1024 ** 3, 'tb': 1000 ** 4, 'tib': 1024 ** 4,
          'k': 1000, 'm': 1000 ** 2, 'g': 1000 ** 3}


def parse_size(text: str) -> Optional[int]:
    """'41.5 MB', '1,2 GB' or '812 kB' (flatpak's words for a size) -> bytes."""
    match = re.search(r'([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z]+)', text or '')
    if not match:
        return None
    unit = _UNITS.get(match.group(2).lower())
    if unit is None:
        return None
    return int(float(match.group(1).replace(',', '.')) * unit)
