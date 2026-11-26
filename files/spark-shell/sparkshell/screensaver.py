"""org.freedesktop.ScreenSaver and org.freedesktop.PowerManagement.Inhibit for the Spark session.

Steam, Chrome, Discord and most video players ask one of these D-Bus services to keep the
screen on. The shell answers them: while any app holds an inhibit,
the flag file $XDG_RUNTIME_DIR/spark-wl/idle-inhibit exists, and the compositor's idle timer
treats it like a Wayland idle inhibitor (no lock, no screen off, no suspend). An app that
quits without letting go loses its inhibits when it leaves the bus."""

import logging
import os

from gi.repository import Gio

from .dbusutil import export

log = logging.getLogger('spark-shell')

SCREENSAVER_XML = """
<node>
  <interface name="org.freedesktop.ScreenSaver">
    <method name="Inhibit">
      <arg type="s" name="application_name" direction="in"/>
      <arg type="s" name="reason_for_inhibit" direction="in"/>
      <arg type="u" name="cookie" direction="out"/>
    </method>
    <method name="UnInhibit"><arg type="u" name="cookie" direction="in"/></method>
    <method name="GetActive"><arg type="b" name="active" direction="out"/></method>
    <method name="SimulateUserActivity"/>
  </interface>
</node>
"""
POWER_XML = """
<node>
  <interface name="org.freedesktop.PowerManagement.Inhibit">
    <method name="Inhibit">
      <arg type="s" name="application" direction="in"/>
      <arg type="s" name="reason" direction="in"/>
      <arg type="u" name="cookie" direction="out"/>
    </method>
    <method name="UnInhibit"><arg type="u" name="cookie" direction="in"/></method>
    <method name="HasInhibit"><arg type="b" name="has_inhibit" direction="out"/></method>
  </interface>
</node>
"""


def flag_path():
    runtime = os.environ.get('XDG_RUNTIME_DIR') or '/run/user/%d' % os.getuid()
    return os.path.join(runtime, 'spark-wl', 'idle-inhibit')


class Inhibitors:
    """The inhibits apps hold, by cookie; on_change(active) fires when the first one starts
    or the last one ends."""

    def __init__(self, on_change=lambda active: None):
        self.held = {}          # cookie -> (sender, app, reason)
        self.next_cookie = 1
        self.on_change = on_change

    @property
    def active(self):
        return bool(self.held)

    def add(self, sender, app, reason):
        was = self.active
        cookie = self.next_cookie
        self.next_cookie += 1
        self.held[cookie] = (sender, app, reason)
        log.info('keep screen on: %s (%s) cookie %d', app, reason, cookie)
        if not was:
            self.on_change(True)
        return cookie

    def remove(self, cookie, sender=None):
        entry = self.held.get(cookie)
        if entry is None or (sender is not None and entry[0] != sender):
            return False
        del self.held[cookie]
        log.info('screen may sleep again: %s cookie %d', entry[1], cookie)
        if not self.held:
            self.on_change(False)
        return True

    def drop_sender(self, sender):
        """The app left the bus: drop what it still held."""
        for cookie in [c for c, e in self.held.items() if e[0] == sender]:
            self.remove(cookie)

    def senders(self):
        return {e[0] for e in self.held.values()}


def write_flag(active, path=None):
    path = path or flag_path()
    try:
        if active:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write('1\n')
        elif os.path.exists(path):
            os.remove(path)
    except OSError as e:
        log.warning('idle inhibit flag %s: %s', path, e)


class ScreenSaverService:
    def __init__(self, conn):
        self.conn = conn
        self.inhibitors = Inhibitors(write_flag)
        self.watches = {}       # sender -> watch id

    def start(self):
        write_flag(False)       # a flag left by a shell that crashed
        for path in ('/ScreenSaver', '/org/freedesktop/ScreenSaver'):
            export(self.conn, path, SCREENSAVER_XML, self._call)
        export(self.conn, '/org/freedesktop/PowerManagement/Inhibit', POWER_XML, self._call)
        for name in ('org.freedesktop.ScreenSaver', 'org.freedesktop.PowerManagement',
                     'org.freedesktop.PowerManagement.Inhibit'):
            Gio.bus_own_name_on_connection(self.conn, name, Gio.BusNameOwnerFlags.REPLACE,
                                           None, lambda c, n: log.warning('lost %s', n))

    def stop(self):
        write_flag(False)

    def _call(self, interface, method, args, sender):
        if method == 'Inhibit':
            cookie = self.inhibitors.add(sender, args[0], args[1])
            self._watch(sender)
            return (cookie,)
        if method == 'UnInhibit':
            self.inhibitors.remove(args[0], sender)
            self._unwatch_gone()
            return None
        if method in ('GetActive',):
            return (False,)     # "is the screensaver showing": never while anything can ask
        if method == 'HasInhibit':
            return (self.inhibitors.active,)
        return None             # SimulateUserActivity

    def _watch(self, sender):
        if sender in self.watches:
            return

        def vanished(_c, name):
            self.inhibitors.drop_sender(name)
            self._unwatch_gone()
        self.watches[sender] = Gio.bus_watch_name_on_connection(
            self.conn, sender, Gio.BusNameWatcherFlags.NONE, None, vanished)

    def _unwatch_gone(self):
        live = self.inhibitors.senders()
        for sender in [s for s in self.watches if s not in live]:
            Gio.bus_unwatch_name(self.watches.pop(sender))
