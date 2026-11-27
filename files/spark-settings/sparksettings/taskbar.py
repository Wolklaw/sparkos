"""Taskbar options: the Spark Connect status widget (shell.json) and the workspace count
(compositor.conf). Settings and the shell share ~/.config/spark/shell.json; only the
connect_widget key is touched here and every other key stays."""
from typing import Dict, List, Tuple

from . import core, displays, inputdev

DEFAULT_WORKSPACES = 4
MIN_WORKSPACES, MAX_WORKSPACES = 1, 9


def connect_installed() -> bool:
    return core.have('spark-connect')


def connect_get() -> Dict[str, object]:
    raw = core.spark_load('shell').get('connect_widget')
    raw = raw if isinstance(raw, dict) else {}
    monitor = raw.get('monitor')
    return {'enabled': raw.get('enabled') is True,
            'monitor': monitor.strip() if isinstance(monitor, str) else ''}


def connect_set(enabled=None, monitor=None) -> bool:
    """Change one or both fields; the other one keeps its saved value."""
    now = connect_get()
    if enabled is not None:
        now['enabled'] = bool(enabled)
    if monitor is not None:
        now['monitor'] = str(monitor).strip()
    return core.spark_save('shell', connect_widget=now)


def screens() -> List[Tuple[str, str]]:
    """(connector, label) for each enabled screen; empty when the list is unavailable."""
    return [(o.name, o.name) for o in displays.load() if o.enabled and o.name]


def clamp_workspaces(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_WORKSPACES
    return max(MIN_WORKSPACES, min(MAX_WORKSPACES, n))


def workspaces_get() -> int:
    return clamp_workspaces(core.spark_load('appearance').get('workspaces', DEFAULT_WORKSPACES))


def workspaces_set(count) -> bool:
    """Save the count, then rewrite compositor.conf's `workspaces count=N` line."""
    n = clamp_workspaces(count)
    if not core.spark_save('appearance', workspaces=n):
        return False
    return inputdev._compositor_write()
