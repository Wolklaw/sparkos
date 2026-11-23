"""What Spark Games itself installed or took over: ~/.local/share/spark-games/stores.json.

  games      "epic:<app>" -> {store, app, title, path, platform, version, root, via, taken_from}
             via is "spark" (Spark Games downloaded it) or "heroic" (taken over: Heroic's files,
             not downloaded again, and never deleted or changed by Spark Games)
  launchers  "battlenet" -> {prefix, exe, via}   via is "spark" or "lutris"

Writes are serialised with a lock file, so the install helper and the window can both save.
"""

import os
from typing import Any, Callable, Dict

from .core import data_dir, read_json, write_json

try:
    import fcntl
except ImportError:                       # Windows dev runs only
    fcntl = None  # type: ignore[assignment]


def path() -> str:
    return os.path.join(data_dir(), 'stores.json')


def load() -> Dict[str, Dict[str, Any]]:
    data = read_json(path(), {})
    if not isinstance(data, dict):
        data = {}
    for name in ('games', 'launchers'):
        if not isinstance(data.get(name), dict):
            data[name] = {}
    return data


def update(change: Callable[[Dict[str, Dict[str, Any]]], None]) -> None:
    """Load, let change() edit it, save; all under a lock."""
    lock = None
    try:
        lock = open(path() + '.lock', 'w')
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        lock = None
    try:
        data = load()
        change(data)
        write_json(path(), data)
    finally:
        if lock:
            lock.close()


def add_game(key: str, record: Dict[str, Any]) -> None:
    update(lambda d: d['games'].__setitem__(key, record))


def remove_game(key: str) -> None:
    update(lambda d: d['games'].pop(key, None))


def add_launcher(slug: str, record: Dict[str, Any]) -> None:
    update(lambda d: d['launchers'].__setitem__(slug, record))


def remove_launcher(slug: str) -> None:
    update(lambda d: d['launchers'].pop(slug, None))
