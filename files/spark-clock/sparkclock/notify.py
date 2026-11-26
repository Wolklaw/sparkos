"""Desktop notifications through the freedesktop.org Notifications service (what Spark Shell and
every other desktop answers on the session bus), with Stop and Snooze buttons. Needs GObject
(python3-gobject, in the SparkOS image). Notifier.on_action / on_closed are set by the service."""

from typing import Callable, Optional

from . import APP_ID, APP_NAME
from .core import log

BUS = 'org.freedesktop.Notifications'
PATH = '/org/freedesktop/Notifications'


class Notifier:
    def __init__(self, connection=None):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.conn = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.on_action: Optional[Callable[[int, str], None]] = None
        self.on_closed: Optional[Callable[[int, int], None]] = None
        self.conn.signal_subscribe(BUS, BUS, 'ActionInvoked', PATH, None,
                                   Gio.DBusSignalFlags.NONE, self._action)
        self.conn.signal_subscribe(BUS, BUS, 'NotificationClosed', PATH, None,
                                   Gio.DBusSignalFlags.NONE, self._closed)

    def _action(self, _c, _s, _p, _i, _n, params):
        notification, action = params.unpack()
        if self.on_action:
            self.on_action(notification, action)

    def _closed(self, _c, _s, _p, _i, _n, params):
        notification, reason = params.unpack()
        if self.on_closed:
            self.on_closed(notification, reason)

    def _notify(self, summary: str, body: str, replaces: int, actions, urgent: bool) -> int:
        GLib = self.GLib
        hints = {'desktop-entry': GLib.Variant('s', APP_ID),
                 'category': GLib.Variant('s', 'alarm' if urgent else 'device'),
                 'urgency': GLib.Variant('y', 2 if urgent else 1)}
        if urgent:
            hints['resident'] = GLib.Variant('b', True)
        try:
            result = self.conn.call_sync(
                BUS, PATH, BUS, 'Notify',
                GLib.Variant('(susssasa{sv}i)', (APP_NAME, replaces, APP_ID, summary, body,
                                                 list(actions), hints, 0 if urgent else 8000)),
                GLib.VariantType('(u)'), self.Gio.DBusCallFlags.NONE, 3000, None)
            return result.unpack()[0]
        except GLib.Error as exc:
            log.warning("notification failed: %s", exc.message)
            return 0

    def ring(self, ring, replaces: int = 0) -> int:
        """The notification of an alarm or timer going off: stays until answered."""
        return self._notify(ring.title, ring.body, replaces, ring.actions(), True)

    def info(self, summary: str, body: str, replaces: int = 0) -> int:
        """A quiet one that goes away on its own."""
        return self._notify(summary, body, replaces, [], False)

    def close(self, notification: int) -> None:
        if not notification:
            return
        try:
            self.conn.call_sync(BUS, PATH, BUS, 'CloseNotification',
                                self.GLib.Variant('(u)', (notification,)), None,
                                self.Gio.DBusCallFlags.NONE, 3000, None)
        except self.GLib.Error as exc:
            log.info("close notification: %s", exc.message)
