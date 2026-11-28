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


def _loginctl(*args):
    import subprocess
    try:
        return subprocess.run(['loginctl', *args], capture_output=True, text=True,
                              timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def _props(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def _session(sid):
    return _props(_loginctl('show-session', sid, '-p', 'Leader', '-p', 'User', '-p', 'Class',
                            '-p', 'State', '-p', 'Type')) if sid else {}


def _scope_of(pid):
    """The cgroup of a process, if it is a login session's scope."""
    try:
        with open(f'/proc/{pid}/cgroup') as f:
            path = f.read().strip().split('::', 1)[1]
    except (OSError, IndexError):
        return ''
    return path if path.endswith('.scope') and '/session-' in path else ''


def _procs(path):
    try:
        with open(f'/sys/fs/cgroup{path}/cgroup.procs') as f:
            return [int(x) for x in f.read().split()]
    except (OSError, ValueError):
        return []


def candidates(env, uid, loginctl=_loginctl):
    """Which login sessions might be this desktop, best guess first: the one this process says
    it is in, the one logind calls the user's graphical session, then every other session of the
    user. The shell's own XDG_SESSION_ID is only a guess: a shell started by hand (from a
    terminal, systemd-run, env -i) has none, or one from somewhere else."""
    out = [env.get('XDG_SESSION_ID', ''),
           _props(loginctl('show-user', str(uid), '-p', 'Display')).get('Display', '')]
    out += [line.split()[0] for line in loginctl('list-sessions', '--no-legend').splitlines()
            if len(line.split()) > 2 and line.split()[1] == str(uid)]
    seen, ordered = set(), []
    for sid in out:
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


def find_session(env=os.environ, uid=None, session=_session, scope_of=_scope_of, procs=_procs,
                 find_compositors=None, loginctl=_loginctl):
    """The desktop session to end: (id, leader, its processes), or None. It has to be this
    user's own 'user' session (not the systemd --user manager, not someone else's), and the one
    with the Spark compositor in it wins; without one anywhere, the first such session."""
    uid = os.getuid() if uid is None else uid
    find_compositors = find_compositors or compositors
    first = None
    for sid in candidates(env, uid, loginctl):
        p = session(sid)
        try:
            leader = int(p.get('Leader') or 0)
        except ValueError:
            leader = 0
        if p.get('User') != str(uid) or p.get('Class') != 'user' or p.get('State') == 'closing' \
                or not leader:
            continue
        path = scope_of(leader)
        pids = procs(path) if path else []
        found = (sid, leader, pids)
        if pids and find_compositors(pids):
            return found
        first = first or found
    return first


def _journal():
    """Sign out runs detached with no stderr, so it writes to the journal (journalctl -t spark-sign-out)."""
    import logging.handlers
    try:
        h = logging.handlers.SysLogHandler(address='/dev/log')
        h.ident = 'spark-sign-out: '
        h.setFormatter(logging.Formatter('%(message)s'))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    except OSError:
        pass


def _failed(reason):
    import subprocess
    from .strings import tr
    log.error('sign out failed: %s', reason)
    try:
        subprocess.run(['notify-send', '-u', 'critical', '-a', 'Spark', tr('sign_out_failed'),
                        tr('sign_out_failed_body') % reason], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
    return 1


def _wait_closed(sid, seconds):
    import time
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _session(sid).get('State', 'closing') == 'closing':
            return True
        time.sleep(0.2)
    return False


def sign_out(wait_s=3.0) -> int:
    import signal
    import subprocess
    _journal()
    found = find_session()
    if not found:
        return _failed('No login session of yours was found.')
    sid, leader, pids = found
    log.info('signing out of session %s (leader %d, %d processes)', sid, leader, len(pids))
    # 1. the apps
    apps = leftovers(pids, os.getpid(), leader)
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
    comps = compositors(pids)
    for p in comps:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    if comps and not _wait_gone(comps, 5.0) and _wait_closed(sid, 5.0):
        return 0
    if comps:
        log.warning('sign out: the compositor did not end session %s by itself', sid)
    # 4. the fallback, checked: a session still there after this is reported, not left silently
    r = subprocess.run(['loginctl', 'terminate-session', sid], capture_output=True, text=True)
    if _wait_closed(sid, 10.0):
        return 0
    return _failed((r.stderr.strip() or f'Session {sid} is still open.').rstrip('.') + '.')
