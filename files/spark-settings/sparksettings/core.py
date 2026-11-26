"""Folders, the log, and running the system's tools. Every tool is found on PATH, so the tests
put fake ones (tests/fixtures/bin) first and never touch the real settings."""

import logging
import os
import shutil
import subprocess
from logging.handlers import RotatingFileHandler
from typing import Optional, Sequence, Tuple

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

def _xdg_dir(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def config_dir() -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def xdg_config_home() -> str:
    return os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')


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


def reduced_motion() -> bool:
    """True when animations are off: the "animations" switch in ~/.config/spark/appearance.json
    (Spark Settings' Appearance page), or SPARK_SETTINGS_REDUCED_MOTION=1."""
    if os.environ.get('SPARK_SETTINGS_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    return spark_load('appearance').get('animations', True) is False


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def run(cmd: Sequence[str], timeout: float = 20, text_in: Optional[str] = None
        ) -> Tuple[int, str, str]:
    """Run a tool and return (exit code, stdout, stderr). 127 when it isn't installed,
    124 when it ran out of time."""
    log.info("run %s", ' '.join(cmd))
    try:
        p = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                           input=text_in, errors='replace', stdin=None if text_in else subprocess.DEVNULL)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, '', f"{cmd[0]}: not installed"
    except subprocess.TimeoutExpired:
        return 124, '', f"{cmd[0]}: timed out"
    except OSError as exc:
        return 126, '', str(exc)


def out(cmd: Sequence[str], timeout: float = 20) -> str:
    rc, text, _ = run(cmd, timeout)
    return text if rc == 0 else ''


def spawn(cmd: Sequence[str]) -> bool:
    """Start a program and don't wait for it."""
    log.info("spawn %s", ' '.join(cmd))
    try:
        subprocess.Popen(list(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("could not start %s: %s", cmd[0], exc)
        return False


# ── Spark-side settings: ~/.config/spark/<name>.json, which the Spark shell reads too ──
def spark_file(name: str) -> str:
    return os.path.join(xdg_config_home(), 'spark', name + '.json')


def spark_load(name: str) -> dict:
    import json
    try:
        with open(spark_file(name), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def spark_save(name: str, **values) -> bool:
    """Merge values into ~/.config/spark/<name>.json (written whole, then renamed)."""
    import json
    data = spark_load(name)
    data.update(values)
    path = spark_file(name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write('\n')
        os.replace(path + '.tmp', path)
        return True
    except OSError as exc:
        log.warning("could not save %s: %s", path, exc)
        return False
