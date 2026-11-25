"""Starts the lock screen (spark-shell --lock) when logind asks the session to lock: Super+L,
the launcher's Lock button and the compositor's idle timer all go through `loginctl
lock-session`. Also locks before sleep when lock.json says so, and starts the lock screen again
if it crashes (the compositor keeps the screen black until a lock client unlocks)."""

import json
import logging
import os
import signal
import sys
import time

from gi.repository import Gio, GLib

log = logging.getLogger('spark-shell')

LOGIN1 = 'org.freedesktop.login1'
SHELL_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'spark_shell.py')
EXIT_UNLOCKED, EXIT_NOT_LOCKED = 0, 3


def lock_on_sleep() -> bool:
    path = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'),
                        'spark', 'lock.json')
    try:
        with open(path, encoding='utf-8') as f:
            return bool(json.load(f).get('on_resume', True))
    except (OSError, ValueError):
        return True


class LockControl:
    def __init__(self):
        self.proc = None
        self.crashes = []
        self.system = None

    def start(self):
        try:
            self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            log.warning('no system bus, no lock screen: %s', e.message)
            return
        session = self._session_path()
        if session:
            for member in ('Lock', 'Unlock'):
                self.system.signal_subscribe(LOGIN1, 'org.freedesktop.login1.Session', member,
                                             session, None, Gio.DBusSignalFlags.NONE,
                                             self._on_session, None)
        self.system.signal_subscribe(LOGIN1, 'org.freedesktop.login1.Manager', 'PrepareForSleep',
                                     '/org/freedesktop/login1', None, Gio.DBusSignalFlags.NONE,
                                     self._on_sleep, None)
        log.info('lock screen: listening to logind on %s', session)

    def _session_path(self):
        try:
            reply = self.system.call_sync(LOGIN1, '/org/freedesktop/login1',
                                          'org.freedesktop.login1.Manager', 'GetSessionByPID',
                                          GLib.Variant('(u)', (os.getpid(),)), GLib.VariantType('(o)'),
                                          Gio.DBusCallFlags.NONE, 2000, None)
            return reply.unpack()[0]
        except GLib.Error as e:
            sid = os.environ.get('XDG_SESSION_ID')
            log.warning('GetSessionByPID: %s', e.message)
            return '/org/freedesktop/login1/session/' + sid if sid else None

    def _on_session(self, _conn, _sender, _path, _iface, member, _params, _data):
        if member == 'Lock':
            self.lock()
        elif member == 'Unlock' and self.proc is not None:
            self.proc.send_signal(signal.SIGUSR1)

    def _on_sleep(self, _conn, _sender, _path, _iface, _member, params, _data):
        if params.unpack()[0] and lock_on_sleep():
            log.info('going to sleep: locking first')
            self.lock()

    def lock(self):
        if self.proc is not None:
            return
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
        # the lock screen loads gtk4-layer-shell itself, before GTK: don't let it think it's done
        launcher.unsetenv('SPARK_SHELL_PRELOADED')
        try:
            self.proc = launcher.spawnv([sys.executable, SHELL_SCRIPT, '--lock'])
        except GLib.Error as e:
            log.error('could not start the lock screen: %s', e.message)
            return
        log.info('lock screen started')
        self.proc.wait_async(None, self._exited)

    def _exited(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        self.proc = None
        if proc.get_if_exited() and proc.get_exit_status() in (EXIT_UNLOCKED, EXIT_NOT_LOCKED):
            log.info('lock screen done (%d)', proc.get_exit_status())
            return
        # crashed while the screen may still be locked: start it again, slower if it keeps dying
        now = time.monotonic()
        self.crashes = [t for t in self.crashes if now - t < 60] + [now]
        delay = 500 if len(self.crashes) < 3 else 5000
        log.error('lock screen died (%s); starting it again in %d ms',
                  proc.get_term_sig() if proc.get_if_signaled() else proc.get_exit_status(), delay)
        GLib.timeout_add(delay, lambda: self.lock() and False)
