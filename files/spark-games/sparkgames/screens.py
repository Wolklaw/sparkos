"""Keeping an added launcher's Wine session in step with the screens.

Wine reads the monitor layout when a session starts. If a screen drops out and comes back while
the session runs (a monitor going to sleep, a cable, a KVM), Wine sees it leave but not return,
and from then on every game that launcher starts gets the wrong layout: it doesn't open
fullscreen, it lands on the wrong screen or offset from it, and clicks miss what they aim at,
because the game and the desktop disagree on where its window is. A new session reads the
layout again and is right. Battle.net and the other launchers stay open for hours, minimized
to the tray, so this is the usual case on a desk with more than one screen.

So while a launcher started from its tile is running, the --track helper watches the screens
once a second: which are connected (/sys/class/drm). When that changes, it waits for the
screens to settle, waits until no game from that launcher is running, then closes the launcher's
Wine session, starts the launcher again and says so in a notification. Turning a screen off and
on in the display settings doesn't upset Wine (tested), so only a connect or disconnect counts. A game is never stopped: a
program the helper doesn't recognise as part of the launcher or of Wine counts as a game.
"""

import glob
import os
import signal
import subprocess
import time
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional

from .core import data_dir, log

try:
    import fcntl
except ImportError:                       # Windows dev runs only
    fcntl = None  # type: ignore[assignment]

DRM = '/sys/class/drm'
POLL = 1.0            # seconds between looks at the screens
SETTLE = 5.0          # screens unchanged this long before acting (they wake one by one)
GAME_POLL = 10.0      # seconds between looks for a running game, once a restart is due
STOP_WAIT = 20.0      # how long the launcher's session gets to close before it is killed

# Programs that belong to Wine or Proton, never to a game (Windows paths, lower case).
WINE_HOMES = ('c:\\windows\\',)
WINE_MARKS = ('\\compatibilitytools.d\\', '\\proton\\', '\\umu\\')


def connected(drm: str = DRM) -> FrozenSet[str]:
    """The connectors with a screen on them, e.g. {'card1-DP-1', 'card1-HDMI-A-1'}."""
    found = set()
    for path in glob.glob(os.path.join(drm, 'card*-*', 'status')):
        try:
            with open(path, encoding='ascii') as f:
                if f.read().strip() == 'connected':
                    found.add(os.path.basename(os.path.dirname(path)))
        except OSError:
            continue
    return frozenset(found)



def windows_dir(prefix: str, path: str) -> str:
    """A folder inside the prefix's drive_c as Wine names it: 'c:\\program files (x86)\\x\\'."""
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(os.path.join(prefix, 'drive_c')))
    if rel.startswith('..'):
        return ''
    return ('c:\\' + rel.replace('/', '\\')).lower().rstrip('\\') + '\\'


def _norm(arg0: str) -> str:
    path = arg0.replace('/', '\\').lower()
    if path.startswith('\\\\?\\'):
        path = path[4:]
    return path


def _session(prefix: str, proc: str, skip: Iterable[str]) -> List[Dict[str, Any]]:
    """The processes of this prefix's Wine session: [{pid, arg0}]. Found by their WINEPREFIX
    (umu-run adds a /pfx link to the prefix, hence realpath)."""
    want = os.path.realpath(prefix)
    skip = set(skip)
    found = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit() and p not in skip]
    except OSError:
        return []
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, 'environ'), 'rb') as f:
                env = f.read().split(b'\0')
            with open(os.path.join(proc, pid, 'cmdline'), 'rb') as f:
                arg0 = f.read().split(b'\0')[0].decode('utf-8', 'replace')
        except OSError:
            continue
        value = next((e[11:] for e in env if e.startswith(b'WINEPREFIX=')), None)
        if value is None:
            continue
        if os.path.realpath(value.decode('utf-8', 'surrogateescape')) != want:
            continue
        found.append({'pid': int(pid), 'arg0': arg0})
    return found


def game_running(prefix: str, homes: Iterable[str], proc: str = '/proc',
                 skip: Iterable[str] = ()) -> bool:
    """Whether a Windows program runs in this session that isn't the launcher's or Wine's own.
    homes: the launcher's folders, as windows_dir() gives them."""
    homes = tuple(h for h in homes if h) + WINE_HOMES
    for p in _session(prefix, proc, skip):
        path = _norm(p['arg0'])
        if not path.endswith('.exe'):
            continue                           # wineserver, umu-run, the runtime: not Windows
        if '\\' not in path or any(m in path for m in WINE_MARKS):
            continue                           # Wine's start.exe shows up by name alone
        inside = [h for h in homes if path.startswith(h)]
        if not inside or '\\games\\' in path[len(inside[0]) - 1:]:
            return True                        # unknown, or a game kept in the launcher's
    return False                               # folder (Ubisoft): leave it running


def stop_session(prefix: str, child: subprocess.Popen, proc: str = '/proc',
                 skip: Iterable[str] = (), wait: float = STOP_WAIT) -> None:
    """Close every process of the session, then wait for the launcher command to return."""
    skip = set(skip) | {str(os.getpid())}
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in _session(prefix, proc, skip):
            try:
                os.kill(p['pid'], sig)
            except OSError:
                pass
        try:
            child.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            log.warning("the launcher's Wine session didn't close; killing it")
    child.wait()


def notify(text: str) -> None:
    try:
        subprocess.Popen(['notify-send', '-a', 'Spark Games', '-i', 'spark-games',
                          'Spark Games', text], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _lock(prefix: str) -> Optional[Any]:
    """One keeper per launcher: a second click on the tile mustn't restart it twice."""
    if fcntl is None:
        return None
    path = os.path.join(data_dir(), 'prefixes', os.path.basename(os.path.realpath(prefix))
                        + '.keeper.lock')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f = open(path, 'a')
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        return None


def keep(child: subprocess.Popen, start: Callable[[], subprocess.Popen],
         session: Dict[str, Any], look: Optional[Callable[[], Any]] = None,
         proc: str = '/proc', poll: float = POLL,
         settle: float = SETTLE, game_poll: float = GAME_POLL,
         clock: Callable[[], float] = time.monotonic,
         sleep: Callable[[float], None] = time.sleep,
         tell: Callable[[str], None] = notify) -> int:
    """Run while the launcher runs; restart it when the screens changed. Returns how many
    times it restarted. child: the running launcher command; start(): starts it again;
    look(): the connected screens (connected() by default)."""
    look = look or connected
    prefix = session.get('prefix') or ''
    homes = session.get('homes') or []
    if not prefix:
        child.wait()
        return 0
    held = _lock(prefix)
    if held is None and fcntl is not None:
        child.wait()                           # another helper already keeps this launcher
        return 0
    from .strings import tr
    restarts = 0
    screens = look()
    changed_at: Optional[float] = None
    looked_at = 0.0
    try:
        while child.poll() is None:
            sleep(poll)
            now = look()
            if now != screens:
                log.info("screens changed: %s -> %s", screens, now)
                screens, changed_at = now, clock()
            if changed_at is None or clock() - changed_at < settle:
                continue
            if clock() - looked_at < game_poll:
                continue
            looked_at = clock()
            if game_running(prefix, homes, proc, skip={str(os.getpid())}):
                continue                       # after the game, not during it
            log.info("restarting %s so it sees the screens again", session.get('name'))
            stop_session(prefix, child, proc)
            child = start()
            changed_at, looked_at = None, 0.0
            restarts += 1
            tell(tr('screens_restarted', name=session.get('name') or 'The launcher'))
    finally:
        if held is not None:
            held.close()
    return restarts
