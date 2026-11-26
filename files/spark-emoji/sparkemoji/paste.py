"""Pasting into the window that was in front.

Wayland lets no program type into another program's window, on purpose. What a desktop does
allow is a keyboard session granted by the user through the XDG desktop portal (RemoteDesktop),
the same way remote-control tools get in. Spark Emoji asks for exactly that, once, and only
for the keyboard: after the user says yes (and the desktop remembers it, through a restore
token) it sends Ctrl+V after the character is on the clipboard. Without that permission the
character is only copied and Spark Emoji says so.

The portal calls are plain D-Bus through Gio, so they can be tested against a fake portal
(tests/test_paste.py); whether the real portal accepts them in a real session is what the first
test on a real desktop shows.
"""

import secrets
from typing import Callable, Optional

from gi.repository import Gio, GLib

from .core import log

PORTAL = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
REMOTE = 'org.freedesktop.portal.RemoteDesktop'
REQUEST = 'org.freedesktop.portal.Request'

DEVICE_KEYBOARD = 1
PERSIST_UNTIL_REVOKED = 2
KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_V = 29, 42, 47      # evdev codes
PRESSED, RELEASED = 1, 0

Done = Callable[[bool, str], None]


class PortalKeyboard:
    """A keyboard-only RemoteDesktop session. start() opens it (the desktop may ask the person
    the first time); paste() sends Ctrl+V (or Ctrl+Shift+V); close() ends it."""

    def __init__(self, token: str = '', bus: Optional[Gio.DBusConnection] = None):
        self.token = token
        self.bus = bus
        self.session: Optional[str] = None
        self.state = 'idle'            # idle, starting, ready, failed
        self.error = ''

    # --- the three steps, each a portal "request" answered by a Response signal ---

    def _connection(self) -> Gio.DBusConnection:
        if self.bus is None:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return self.bus

    def _request(self, method: str, build, reply) -> None:
        """Call a portal method whose options carry a handle_token; reply(code, results)
        comes from the Response signal on the request object."""
        bus = self._connection()
        token = 'spark' + secrets.token_hex(6)
        sender = bus.get_unique_name().lstrip(':').replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        holder = {}

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            bus.signal_unsubscribe(holder['id'])
            code, results = params.unpack()
            reply(code, results)

        # subscribe before calling: the answer can come before the call returns
        holder['id'] = bus.signal_subscribe(PORTAL, REQUEST, 'Response', path, None,
                                            Gio.DBusSignalFlags.NONE, on_response)

        def called(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as exc:
                bus.signal_unsubscribe(holder['id'])
                reply(-1, {'error': exc.message})
        params, _signature = build(token)
        bus.call(PORTAL, PORTAL_PATH, REMOTE, method, params, None,
                 Gio.DBusCallFlags.NONE, 120000, None, called)

    def start(self, done: Done) -> None:
        """Open the session. done(ok, message) is called once, when it's ready or has failed."""
        if self.state in ('starting', 'ready'):
            return
        self.state = 'starting'

        def fail(why: str) -> None:
            self.state, self.error = 'failed', why
            log.warning("portal keyboard: %s", why)
            done(False, why)

        def created(code, results):
            if code != 0 or 'session_handle' not in results:
                return fail(results.get('error') or 'the desktop has no remote-keyboard portal')
            self.session = results['session_handle']
            self._request('SelectDevices', lambda t: (GLib.Variant('(oa{sv})', (
                self.session, {'handle_token': GLib.Variant('s', t),
                               'types': GLib.Variant('u', DEVICE_KEYBOARD),
                               'persist_mode': GLib.Variant('u', PERSIST_UNTIL_REVOKED),
                               **({'restore_token': GLib.Variant('s', self.token)}
                                  if self.token else {})})), '(oa{sv})'), selected)

        def selected(code, results):
            if code != 0:
                return fail(results.get('error') or 'the desktop refused the keyboard')
            self._request('Start', lambda t: (GLib.Variant('(osa{sv})', (
                self.session, '', {'handle_token': GLib.Variant('s', t)})), '(osa{sv})'),
                started)

        def started(code, results):
            if code == 1:
                return fail('not allowed')
            if code != 0:
                return fail(results.get('error') or 'the desktop could not start it')
            devices = results.get('devices', DEVICE_KEYBOARD)
            if not devices & DEVICE_KEYBOARD:
                return fail('the desktop did not give a keyboard')
            self.token = results.get('restore_token') or self.token
            self.state = 'ready'
            done(True, '')

        self._request('CreateSession', lambda t: (GLib.Variant('(a{sv})', ({
            'handle_token': GLib.Variant('s', t),
            'session_handle_token': GLib.Variant('s', 'spark' + secrets.token_hex(6)),
        },)), '(a{sv})'), created)

    def paste(self, shift: bool = False) -> bool:
        """Press Ctrl+V (Ctrl+Shift+V when shift is set). False if there is no session."""
        if self.state != 'ready' or not self.session:
            return False
        keys = [(KEY_LEFTCTRL, PRESSED)] + ([(KEY_LEFTSHIFT, PRESSED)] if shift else []) + [
            (KEY_V, PRESSED), (KEY_V, RELEASED)] + (
            [(KEY_LEFTSHIFT, RELEASED)] if shift else []) + [(KEY_LEFTCTRL, RELEASED)]
        bus = self._connection()
        for code, state in keys:
            bus.call(PORTAL, PORTAL_PATH, REMOTE, 'NotifyKeyboardKeycode',
                     GLib.Variant('(oa{sv}iu)', (self.session, {}, code, state)), None,
                     Gio.DBusCallFlags.NONE, 5000, None, self._notify_done)
        return True

    @staticmethod
    def _notify_done(conn, res):
        try:
            conn.call_finish(res)
        except GLib.Error as exc:
            log.warning("portal keyboard: key not sent: %s", exc.message)

    def close(self) -> None:
        if self.session and self.state == 'ready':
            try:
                self._connection().call(PORTAL, self.session, 'org.freedesktop.portal.Session',
                                        'Close', None, None, Gio.DBusCallFlags.NONE, 2000,
                                        None, None)
            except GLib.Error:
                pass
        self.state = 'idle'
        self.session = None


def portal_available(bus: Optional[Gio.DBusConnection] = None) -> bool:
    """True if the desktop has the RemoteDesktop portal (a quick check; no session)."""
    try:
        bus = bus or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        value = bus.call_sync(PORTAL, PORTAL_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                              GLib.Variant('(ss)', (REMOTE, 'AvailableDeviceTypes')),
                              GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 3000,
                              None).unpack()[0]
        return bool(value & DEVICE_KEYBOARD)
    except GLib.Error:
        return False
