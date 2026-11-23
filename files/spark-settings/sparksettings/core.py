"""Folders, the log, and running the system's tools. Every tool is found on PATH, so the tests
put fake ones (tests/fixtures/bin) first and never touch the real settings."""

import logging
import os
import shutil
import subprocess
from logging.handlers import RotatingFileHandler
from typing import List, Optional, Sequence, Tuple

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

# KDE's own tools, moved aside by the image build so Spark Settings can still open them while
# /usr/bin/systemsettings and /usr/bin/kcmshell6 route pages here (files/scripts/spark-settings.sh)
REAL_DIR = os.environ.get('SPARK_SETTINGS_REAL_DIR', '/usr/libexec/sparkos/kde-settings')


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
    if os.environ.get('SPARK_SETTINGS_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    try:
        with open(os.path.join(xdg_config_home(), 'kdeglobals'), encoding='utf-8',
                  errors='replace') as f:
            import re
            m = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(m) and float(m.group(1)) == 0
    except (OSError, ValueError):
        return False


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def kde_tool(name: str) -> Optional[str]:
    """KDE's systemsettings or kcmshell6: the moved-aside original if the image moved it,
    else the one on PATH."""
    real = os.path.join(REAL_DIR, name)
    if os.access(real, os.X_OK):
        return real
    found = shutil.which(name)
    return None if found is None or is_wrapper(found) else found


def is_wrapper(path: str) -> bool:
    """True for the stand-ins the image puts at /usr/bin/systemsettings and /usr/bin/kcmshell6
    (they call spark-settings --route), so a missing original can't loop back into itself."""
    try:
        with open(path, 'rb') as f:
            return b'spark-settings --route' in f.read(400)
    except OSError:
        return False


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


def kwrite(file: str, group: str, key: str, value: str) -> int:
    """Write one KDE config value (kwriteconfig6)."""
    groups: List[str] = []
    for g in group.split('/'):
        groups += ['--group', g]
    return run(['kwriteconfig6', '--file', file, *groups, '--key', key, value])[0]


def kread(file: str, group: str, key: str, default: str = '') -> str:
    groups: List[str] = []
    for g in group.split('/'):
        groups += ['--group', g]
    rc, text, _ = run(['kreadconfig6', '--file', file, *groups, '--key', key, '--default', default])
    return text.strip() if rc == 0 else default
