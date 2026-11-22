"""Desktop notifications while Spark Connect is open: once when something goes wrong, once more
when it recovers. Discord alerts stay with the servers' own watchdog; this doesn't send any."""

import shutil
import subprocess
from typing import Dict, List, Tuple

from . import APP_ID, APP_NAME
from .core import WINDOWS, log

BAD, RECOVERED = 'bad', 'recovered'


class Alerts:
    """Feed it everything that is wrong right now (key -> sentence) after each refresh; it
    returns what changed since the last time: new problems and recoveries."""

    def __init__(self):
        self.active: Dict[Tuple, str] = {}

    def update(self, wrong: Dict[Tuple, str], scope=None) -> List[Tuple[str, Tuple, str]]:
        """scope: only keys starting with this (one machine's refresh, or the sites) are
        compared; the rest keep their state."""
        events: List[Tuple[str, Tuple, str]] = []
        for key, text in wrong.items():
            if key not in self.active:
                events.append((BAD, key, text))
            self.active[key] = text
        for key in list(self.active):
            if scope is not None and key[:len(scope)] != scope:
                continue
            if key not in wrong:
                events.append((RECOVERED, key, self.active.pop(key)))
        return events


def notify(title: str, body: str) -> bool:
    """A desktop notification. On Linux through notify-send; on Windows there is no plain way
    without extra packages, so the window's status line carries it instead."""
    if WINDOWS:
        return False
    exe = shutil.which('notify-send')
    if not exe:
        return False
    try:
        subprocess.Popen([exe, '--app-name', APP_NAME, '--icon', APP_ID, title, body],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except OSError as exc:
        log.info("notify-send failed: %s", exc)
        return False
