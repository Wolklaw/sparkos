"""Settings, log, running programs. The settings say which tray items are on."""

import json
import logging
import os
import shutil
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Sequence

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)

ITEMS = ('network', 'bluetooth', 'power', 'printers', 'volume')


def _xdg(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def config_dir() -> str:
    return _xdg('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _xdg('XDG_STATE_HOME', os.path.join('.local', 'state'))


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


DEFAULTS: Dict[str, Any] = {
    'items': {name: True for name in ITEMS},
    'power_show_without_battery': False,   # a desktop with no battery shows no power icon
    'popup_corner': 'bottom-right',        # where popups sit under a Wayland layer shell
}


def load_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(os.path.join(config_dir(), 'config.json'), encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as exc:
        log.warning("could not read config.json: %s", exc)
        return cfg
    if isinstance(data, dict):
        if isinstance(data.get('items'), dict):
            for name in ITEMS:
                if isinstance(data['items'].get(name), bool):
                    cfg['items'][name] = data['items'][name]
        if isinstance(data.get('power_show_without_battery'), bool):
            cfg['power_show_without_battery'] = data['power_show_without_battery']
        if data.get('popup_corner') in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
            cfg['popup_corner'] = data['popup_corner']
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    path = os.path.join(config_dir(), 'config.json')
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        os.replace(path + '.tmp', path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write config.json: %s", exc)


def set_item_enabled(name: str, on: bool) -> Dict[str, Any]:
    cfg = load_config()
    cfg['items'][name] = on
    save_config(cfg)
    return cfg


def run(cmd: Sequence[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
    """Run a program. A missing program or a timeout doesn't raise: returncode 127 / 124."""
    env = dict(os.environ, LC_ALL='C', LANG='C')       # the output is parsed, so keep it English
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                              errors='replace', env=env)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, '', f"{cmd[0]}: not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, '', f"{cmd[0]}: timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 126, '', f"{cmd[0]}: {exc}")


def spawn(cmd: List[str]) -> bool:
    """Start a program and don't wait for it."""
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("could not start %s: %s", cmd[0], exc)
        return False


def which(name: str) -> Optional[str]:
    return shutil.which(name)
