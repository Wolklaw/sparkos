"""Settings, history and the log."""

import json
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)
HISTORY_KEEP = 100


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
                                      maxBytes=128 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


def _load(path: str) -> Any:
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return None


def _save(path: str, data: Any) -> None:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(path + '.tmp', path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write %s: %s", path, exc)


def load_settings() -> Dict[str, Any]:
    data = _load(os.path.join(config_dir(), 'config.json'))
    return data if isinstance(data, dict) else {}


def save_settings(data: Dict[str, Any]) -> None:
    _save(os.path.join(config_dir(), 'config.json'), data)


def load_history() -> List[Dict[str, Any]]:
    """[{'expr', 'result', 'mode'}], oldest first. Kept in ~/.local/state/spark-calc."""
    data = _load(os.path.join(state_dir(), 'history.json'))
    if not isinstance(data, list):
        return []
    keep = []
    for item in data[-HISTORY_KEEP:]:
        if isinstance(item, dict) and isinstance(item.get('expr'), str) and \
                isinstance(item.get('result'), str):
            entry = {'expr': item['expr'], 'result': item['result'],
                     'mode': str(item.get('mode', 'standard'))}
            for k in ('base', 'bits'):
                if isinstance(item.get(k), int):
                    entry[k] = item[k]
            keep.append(entry)
    return keep


def save_history(items: List[Dict[str, Any]]) -> None:
    _save(os.path.join(state_dir(), 'history.json'), items[-HISTORY_KEEP:])


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_CALC_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False
