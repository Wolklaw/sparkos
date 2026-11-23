"""Folders and the log. The window logs to ~/.local/state/spark-controller; the daemon logs to
the journal (stderr), which systemd captures."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)


def _xdg_dir(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser("~"), fallback)
    path = os.path.join(base, APP_SLUG)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def config_dir() -> str:
    return _xdg_dir("XDG_CONFIG_HOME", ".config")


def state_dir() -> str:
    return _xdg_dir("XDG_STATE_HOME", os.path.join(".local", "state"))


def cache_dir() -> str:
    return _xdg_dir("XDG_CACHE_HOME", ".cache")


def setup_logging(to_file: bool = True) -> None:
    log.setLevel(logging.INFO)
    if log.handlers:
        return
    try:
        if not to_file:
            raise OSError
        handler = RotatingFileHandler(os.path.join(state_dir(), f"{APP_SLUG}.log"),
                                      maxBytes=256 * 1024, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log.addHandler(handler)
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])
