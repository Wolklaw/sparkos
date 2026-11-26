"""Settings, log, running programs, and a little number formatting."""

import json
import logging
import math
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Sequence

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)


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
    """True when animations are turned off in Spark Settings (appearance.json) or by env."""
    if os.environ.get('SPARK_AUDIO_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


def run(cmd: Sequence[str], timeout: float = 5.0,
        input: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a program and return the result. A missing program or a timeout does not raise:
    returncode 127 / 124 and the reason in stderr."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                              input=input, errors='replace')
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, '', f"{cmd[0]}: not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, '', f"{cmd[0]}: timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 126, '', f"{cmd[0]}: {exc}")


def pct(volume: Optional[float]) -> str:
    return "—" if volume is None else f"{round(volume * 100)}%"


def volume_to_gain(v: float) -> float:
    """The slider shows the cube root of the gain PipeWire applies, the scale wpctl and
    other desktops use: 0.5 on the slider is a gain of 0.125."""
    return max(0.0, v) ** 3


def gain_to_volume(gain: float) -> float:
    return max(0.0, gain) ** (1.0 / 3.0)


def db(gain: float) -> str:
    if gain <= 1e-6:
        return "-inf dB"
    return f"{20 * math.log10(gain):+.1f} dB"
