"""Folders, settings and the log. Settings are ~/.config/spark-link/settings.json; keys and
paired phones are in ~/.local/share/spark-link/ (0700, files 0600); the log is
~/.local/state/spark-link/spark-link.log; the control socket is in $XDG_RUNTIME_DIR."""

import json
import logging
import os
import socket
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from . import APP_NAME, APP_SLUG, DEFAULT_FEATURES, DEFAULT_PORT, VERSION

log = logging.getLogger(APP_SLUG)


def _xdg(var: str, fallback: str) -> str:
    value = os.environ.get(var, '')
    if value and os.path.isabs(value):
        return value
    return os.path.join(os.path.expanduser('~'), fallback)


def config_dir() -> str:
    return os.path.join(_xdg('XDG_CONFIG_HOME', '.config'), APP_SLUG)


def cache_dir() -> str:
    return os.path.join(_xdg('XDG_CACHE_HOME', '.cache'), APP_SLUG)


def snip_latest() -> str:
    """Where Spark Snip keeps its last screenshot as a PNG (its cache folder, latest.png)."""
    return os.path.join(_xdg('XDG_CACHE_HOME', '.cache'), 'spark-snip', 'latest.png')


def data_dir() -> str:
    return os.path.join(_xdg('XDG_DATA_HOME', os.path.join('.local', 'share')), APP_SLUG)


def state_dir() -> str:
    return os.path.join(_xdg('XDG_STATE_HOME', os.path.join('.local', 'state')), APP_SLUG)


def runtime_dir() -> str:
    """$XDG_RUNTIME_DIR/spark-link (systemd makes the parent 0700 for the user). Without it,
    a private folder in the temp dir named after the user."""
    base = os.environ.get('XDG_RUNTIME_DIR', '')
    if base and os.path.isabs(base) and os.path.isdir(base):
        return os.path.join(base, APP_SLUG)
    uid = os.getuid() if hasattr(os, 'getuid') else 0
    return os.path.join(tempfile.gettempdir(), f'{APP_SLUG}-{uid}')


def control_path() -> str:
    return os.path.join(runtime_dir(), 'control.sock')


def private_dir(path: str) -> str:
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def write_private(path: str, data: bytes) -> None:
    """Write a file only this user can read, atomically (a temp file, then rename)."""
    folder = os.path.dirname(path)
    private_dir(folder)
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
    return {}


def save_json(path: str, data: Dict[str, Any]) -> None:
    write_private(path, (json.dumps(data, indent=1, sort_keys=True) + '\n').encode('utf-8'))


def pc_name() -> str:
    """The PC's pretty name from /etc/machine-info, else its host name."""
    try:
        with open('/etc/machine-info', encoding='utf-8') as f:
            for line in f:
                if line.startswith('PRETTY_HOSTNAME='):
                    value = line.split('=', 1)[1].strip().strip('"\'')
                    if value:
                        return value[:64]
    except OSError:
        pass
    return (socket.gethostname().split('.')[0] or 'SparkOS PC')[:64]


class Settings:
    """settings.json: which features are on, the port, the PC's name."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(config_dir(), 'settings.json')
        data = load_json(self.path)
        feats = data.get('features') if isinstance(data.get('features'), dict) else {}
        self.features: Dict[str, bool] = {
            k: bool(feats.get(k, v)) for k, v in DEFAULT_FEATURES.items()}
        port = data.get('port', DEFAULT_PORT)
        self.port = port if isinstance(port, int) and 0 <= port < 65536 else DEFAULT_PORT
        name = data.get('name')
        self.name = name.strip()[:64] if isinstance(name, str) and name.strip() else None

    def save(self) -> None:
        data: Dict[str, Any] = {'features': self.features, 'port': self.port}
        if self.name:
            data['name'] = self.name
        save_json(self.path, data)

    def display_name(self) -> str:
        return self.name or pc_name()

    def enabled(self) -> list:
        return [k for k, on in self.features.items() if on]


def setup_logging(to_stderr: bool = False) -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s')
    try:
        handler = RotatingFileHandler(os.path.join(private_dir(state_dir()), f'{APP_SLUG}.log'),
                                      maxBytes=256 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(fmt)
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    if to_stderr:
        err = logging.StreamHandler(sys.stderr)
        err.setFormatter(fmt)
        log.addHandler(err)
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])
