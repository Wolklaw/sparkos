"""Sign out, restart and shut down without killing open apps.

Nothing else asks the apps to close before the session ends, so the shell does it: it asks the
compositor, through spark-wl-windows, to close every window (the same close as the title bar's
button, so an app can save or ask about unsaved work), waits for the window list to empty, then
runs the command. If windows are still open when the wait is over,
nothing is run: on_stuck(titles) lets the person choose to go anyway or stay."""

import logging
import os

from gi.repository import GLib

log = logging.getLogger('spark-shell')

WAIT_S = 8.0
TICK_MS = 250


class SessionEnd:
    def __init__(self, tracker, run, on_stuck, wait_s=WAIT_S, timeout_add=None):
        self.tracker = tracker          # .windows (list of dicts), .loaded, .act('close', id)
        self.run = run                  # run(command)
        self.on_stuck = on_stuck        # on_stuck(command, [titles still open], label)
        self.wait_s = wait_s
        self.timeout_add = timeout_add or GLib.timeout_add
        self._ticks = 0
        self._command = None
        self._label = None

    @property
    def busy(self):
        return self._command is not None

    def start(self, command, force=False, label=None):
        """Close the windows, then run command. force runs it at once (the second ask).
        label comes back to on_stuck (which button it was)."""
        if force or not self.tracker.loaded or not self.tracker.windows:
            self._finish(command)
            return
        if self.busy:
            return
        self._command = command
        self._label = label
        self._ticks = 0
        for w in list(self.tracker.windows):
            self.tracker.act('close', w['id'])
        self.timeout_add(TICK_MS, self._tick)

    def _tick(self):
        command = self._command
        if command is None:
            return False
        if not self.tracker.windows:
            self._finish(command)
            return False
        self._ticks += 1
        if self._ticks * TICK_MS / 1000.0 >= self.wait_s:
            self._command = None
            titles = [w.get('title') or w.get('app') or '?' for w in self.tracker.windows]
            log.info('still open after %.0fs: %s', self.wait_s, ', '.join(titles))
            self.on_stuck(command, titles, self._label)
            return False
        return True

    def _finish(self, command):
        self._command = None
        self.run(command)


# ─── Sign out ─────────────────────────────────────────────────
# loginctl terminate-session kills everything in the session at once. With Wine, a browser or
# Nova still running, that takes long enough (half a second) that the login screen starts before
# the session is gone; it then can't open the graphics card and the screen stays black. And the
# session's services (portal, polkit agent, clipboard, tray) lost their display mid-run, failed,
# and systemd restarted them into nothing. So it goes in order: the apps, then the services
# (the session targets are stopped), then the compositor quits by itself, which frees the
# graphics card before the login screen is started. terminate-session is only the fallback.

SESSION_TARGETS = ['xdg-desktop-autostart.target', 'spark-wl-workspace.target',
                   'graphical-session.target']


def _exe(pid, proc='/proc'):
    try:
        return os.path.basename(os.readlink(f'{proc}/{pid}/exe'))
    except OSError:
        return ''


def compositors(pids, exe=_exe):
    """The Spark compositor among the session's processes (its binary, not a wrapper script)."""
    return [p for p in pids if exe(p).startswith('spark-compositor')]


def _parent(pid, proc='/proc'):
    try:
        with open(f'{proc}/{pid}/stat') as f:
            return int(f.read().rsplit(')', 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def leftovers(pids, keep_from, leader, parent=_parent):
    """The session's processes that are apps: not the session leader and what it started (the
    compositor), and not keep_from and the processes above it (the shell running this)."""
    keep, pid = set(), keep_from
    while pid > 1 and pid not in keep:
        keep.add(pid)
        pid = parent(pid)
    out = []
    for p in pids:
        q, seen = p, set()
        while q > 1 and q not in seen and q != leader:
            seen.add(q)
            q = parent(q)
        if p not in keep and q != leader and p != leader:
            out.append(p)
    return out


def _wait_gone(pids, seconds):
    import time
    end = time.monotonic() + seconds
    while time.monotonic() < end and any(os.path.exists(f'/proc/{p}') for p in pids):
        time.sleep(0.05)
    return [p for p in pids if os.path.exists(f'/proc/{p}')]


def sign_out(wait_s=3.0) -> int:
    import signal
    import subprocess
    sid = os.environ.get('XDG_SESSION_ID', '')
    path = ''
    try:
        with open('/proc/self/cgroup') as f:
            path = f.read().strip().split('::', 1)[1]
        with open(f'/sys/fs/cgroup{path}/cgroup.procs') as f:
            pids = [int(x) for x in f.read().split()]
        leader = int(subprocess.run(['loginctl', 'show-session', sid, '-p', 'Leader', '--value'],
                                    capture_output=True, text=True, timeout=5).stdout.strip() or 0)
    except (OSError, IndexError, ValueError, subprocess.SubprocessError) as e:
        log.warning('sign out: could not list the session (%s); ending it as is', e)
        pids, leader = [], 0
    in_scope = leader and path.endswith('.scope')
    # 1. the apps
    apps = leftovers(pids, os.getpid(), leader) if in_scope else []
    for sig, wait in ((signal.SIGTERM, wait_s), (signal.SIGKILL, 1.0)):
        for p in apps:
            try:
                os.kill(p, sig)
            except OSError:
                pass
        apps = _wait_gone(apps, wait)
        if not apps:
            break
    # 2. the session's services, while the display they run on is still there
    try:
        subprocess.run(['systemctl', '--user', 'stop', *SESSION_TARGETS],
                       timeout=10, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning('sign out: could not stop the session services (%s)', e)
    # 3. the compositor quits; the session ends when it is gone
    comps = compositors(pids) if in_scope else []
    for p in comps:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    if comps and not _wait_gone(comps, 5.0):
        return 0
    return subprocess.call(['loginctl', 'terminate-session', sid])
