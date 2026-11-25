"""Desktop notifications through the freedesktop.org Notifications service (Plasma answers on
the session bus), with buttons. Needs GObject; without it or without a bus, Notifier() raises
and the service goes on silently."""

from typing import Callable, Dict, List, Optional, Tuple

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
        self.conn.signal_subscribe(BUS, BUS, 'ActionInvoked', PATH, None,
                                   Gio.DBusSignalFlags.NONE, self._action)

    def _action(self, _c, _s, _p, _i, _n, params):
        notification, action = params.unpack()
        if self.on_action:
            self.on_action(notification, action)

    def show(self, summary: str, body: str = '', actions: Optional[List[Tuple[str, str]]] = None,
             replaces: int = 0, seconds: int = 8) -> int:
        """actions: (id, label) pairs. Returns the notification's number, 0 when it failed."""
        GLib = self.GLib
        flat: List[str] = []
        for key, label in actions or []:
            flat += [key, label]
        hints: Dict[str, object] = {'desktop-entry': GLib.Variant('s', APP_ID),
                                    'urgency': GLib.Variant('y', 1)}
        try:
            result = self.conn.call_sync(
                BUS, PATH, BUS, 'Notify',
                GLib.Variant('(susssasa{sv}i)', (APP_NAME, replaces, APP_ID, summary, body,
                                                 flat, hints, seconds * 1000)),
                GLib.VariantType('(u)'), self.Gio.DBusCallFlags.NONE, 3000, None)
            return result.unpack()[0]
        except GLib.Error as exc:
            log.warning("notification failed: %s", exc.message)
            return 0
