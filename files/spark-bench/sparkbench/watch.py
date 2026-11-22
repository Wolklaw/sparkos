"""Start and stop alerts. MangoHud creates <game>_<date>.csv when a recording starts and writes
<game>_<date>_summary.csv next to it when it ends; listing the output folder twice a second is
enough to tell, and costs next to nothing.

The window alerts while it is open. The background watcher (`spark-bench --watch`, a systemd
user service the app can turn on and off) alerts when the window is closed. Only one of them
alerts at a time: whoever holds the lock file in $XDG_RUNTIME_DIR does, the other stays quiet."""

import fcntl
import os
import shutil
import subprocess
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import APP_ID, APP_NAME, APP_SLUG, WATCH_INTERVAL_MS, core
from .core import log

STARTED, STOPPED = 'started', 'stopped'
SOUNDS = '/usr/share/sounds/freedesktop/stereo'
SOUND_FOR = {STARTED: 'bell.oga', STOPPED: 'complete.oga'}
UNIT = f'{APP_SLUG}-watch.service'
UNIT_MARK = '# Written by Spark Bench; it removes this file when the watcher is turned off.'


class FolderWatcher:
    """Call poll() now and then; it returns what started and stopped since the last call. Files
    already there the first time are not news."""

    def __init__(self, folders: Iterable[str]):
        self.folders = list(dict.fromkeys(folders))
        self.seen: Dict[str, Set[str]] = {f: self._list(f) for f in self.folders}

    def set_folders(self, folders: Iterable[str]) -> None:
        folders = list(dict.fromkeys(folders))
        for f in folders:
            if f not in self.seen:
                self.seen[f] = self._list(f)
        self.folders = folders

    @staticmethod
    def _list(folder: str) -> Set[str]:
        try:
            return {n for n in os.listdir(folder) if n.lower().endswith('.csv')}
        except OSError:
            return set()

    def poll(self) -> List[Tuple[str, str]]:
        events = []
        for folder in self.folders:
            now = self._list(folder)
            for name in sorted(now - self.seen.get(folder, set())):
                kind = STOPPED if name.endswith('_summary.csv') else STARTED
                events.append((kind, os.path.join(folder, name)))
            self.seen[folder] = now
        return events


# ─── Telling the player ───────────────────────────────────────

def play(kind: str) -> bool:
    """The freedesktop bell when a recording starts, 'complete' when it ends."""
    path = os.path.join(SOUNDS, SOUND_FOR[kind])
    if not os.path.exists(path):
        return False
    for player in (['pw-play', path], ['paplay', path], ['canberra-gtk-play', '-f', path]):
        if shutil.which(player[0]):
            try:
                subprocess.Popen(player, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    return False


def notify(title: str, body: str) -> bool:
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


def message(kind: str, duration: int) -> Tuple[str, str]:
    from .text import t
    if kind == STARTED:
        return t('alert.started'), t('alert.started_body', s=duration)
    return t('alert.stopped'), t('alert.stopped_body')


# ─── Who alerts ───────────────────────────────────────────────

class AlertLock:
    """Held by whoever alerts. try_take() is non-blocking; the lock goes when the process
    does, so a crashed watcher never keeps the window quiet."""

    def __init__(self, path: Optional[str] = None):
        runtime = os.environ.get('XDG_RUNTIME_DIR') or core.state_dir()
        self.path = path or os.path.join(runtime, f'{APP_SLUG}-alerts.lock')
        self.fd: Optional[int] = None

    def try_take(self) -> bool:
        if self.fd is not None:
            return True
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            return True               # no place for a lock: alert anyway
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


def run_watch(folders: List[str], duration: int, sound: bool = True,
              stop_after: Optional[float] = None) -> int:
    """The background watcher. Waits for the alert lock (the window may have it), then alerts
    on every start and stop. stop_after is for tests."""
    lock = AlertLock()
    watcher = FolderWatcher(folders)
    end = None if stop_after is None else time.monotonic() + stop_after
    log.info("watching %s", folders)
    while end is None or time.monotonic() < end:
        time.sleep(WATCH_INTERVAL_MS / 1000)
        events = watcher.poll()
        if not lock.try_take():
            continue                 # the window is open and alerting
        for kind, path in events:
            log.info("%s: %s", kind, path)
            if sound:
                play(kind)
            notify(*message(kind, duration))
    lock.release()
    return 0


# ─── The background service (systemd, this user only) ─────────

def unit_path() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(core.home(), '.config')
    return os.path.join(base, 'systemd', 'user', UNIT)


def command() -> List[str]:
    """How to start Spark Bench again: its own launcher when installed, else this Python."""
    exe = shutil.which(APP_SLUG)
    if exe:
        return [exe]
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(here, 'spark_bench.py')]


def unit_text(argv: List[str]) -> str:
    quoted = ' '.join('"' + a.replace('\\', '\\\\').replace('"', '\\"') + '"' if ' ' in a else a
                      for a in argv + ['--watch'])
    return (f"{UNIT_MARK}\n[Unit]\nDescription={APP_NAME}: sound and notification when a "
            f"MangoHud recording starts and ends\n\n[Service]\nExecStart={quoted}\n"
            f"Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n")


def _systemctl(*args: str) -> Tuple[int, str]:
    from .mangohud import run_command
    return run_command(['systemctl', '--user'] + list(args), timeout=15)


def background_on(systemctl=_systemctl) -> bool:
    code, _ = systemctl('is-enabled', UNIT)
    return code == 0 and os.path.exists(unit_path())


def enable_background(systemctl=_systemctl) -> Tuple[bool, str]:
    core.write_text(unit_path(), unit_text(command()))
    systemctl('daemon-reload')
    code, out = systemctl('enable', '--now', UNIT)
    return code == 0, out


def disable_background(systemctl=_systemctl) -> Tuple[bool, str]:
    code, out = systemctl('disable', '--now', UNIT)
    path = unit_path()
    text = None
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        pass
    if text is not None and text.startswith(UNIT_MARK):
        os.unlink(path)
    systemctl('daemon-reload')
    return code == 0 or text is None, out
