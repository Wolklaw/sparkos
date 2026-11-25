"""A small D-Bus helper over Gio, so the backends read like plain calls. Reads are
synchronous with a short timeout (every service here answers at once); anything that can wait
for a person (a pairing, a connection) goes through call_async."""

from typing import Any, Callable, Optional

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib   # noqa: E402

PROPS = 'org.freedesktop.DBus.Properties'


class BusError(Exception):
    """A D-Bus call failed. .name is the D-Bus error name when there is one."""

    def __init__(self, message: str, name: str = ''):
        super().__init__(message)
        self.name = name


def _wrap(exc: GLib.Error) -> BusError:
    name = ''
    try:
        name = Gio.DBusError.get_remote_error(exc) or ''
        Gio.DBusError.strip_remote_error(exc)
    except Exception:       # noqa: BLE001
        pass
    return BusError(exc.message, name)


class Bus:
    def __init__(self, connection: Gio.DBusConnection):
        self.conn = connection

    @classmethod
    def system(cls) -> 'Bus':
        return cls(Gio.bus_get_sync(Gio.BusType.SYSTEM, None))

    @classmethod
    def session(cls) -> 'Bus':
        return cls(Gio.bus_get_sync(Gio.BusType.SESSION, None))

    def call(self, dest: str, path: str, iface: str, method: str,
             params: Optional[GLib.Variant] = None, timeout: int = 3000) -> Any:
        try:
            result = self.conn.call_sync(dest, path, iface, method, params, None,
                                         Gio.DBusCallFlags.NONE, timeout, None)
        except GLib.Error as exc:
            raise _wrap(exc) from None
        return result.unpack() if result is not None else ()

    def call_async(self, dest: str, path: str, iface: str, method: str,
                   params: Optional[GLib.Variant] = None,
                   done: Optional[Callable[[Any, Optional[BusError]], None]] = None,
                   timeout: int = 120000) -> None:
        def finished(conn, res):
            try:
                value = conn.call_finish(res)
                out, err = (value.unpack() if value is not None else ()), None
            except GLib.Error as exc:
                out, err = None, _wrap(exc)
            if done:
                done(out, err)
        self.conn.call(dest, path, iface, method, params, None, Gio.DBusCallFlags.NONE,
                       timeout, None, finished)

    def get(self, dest: str, path: str, iface: str, prop: str) -> Any:
        return self.call(dest, path, PROPS, 'Get', GLib.Variant('(ss)', (iface, prop)))[0]

    def get_all(self, dest: str, path: str, iface: str) -> dict:
        return self.call(dest, path, PROPS, 'GetAll', GLib.Variant('(s)', (iface,)))[0]

    def set(self, dest: str, path: str, iface: str, prop: str, value: GLib.Variant) -> None:
        self.call(dest, path, PROPS, 'Set', GLib.Variant('(ssv)', (iface, prop, value)))

    def has_owner(self, name: str) -> bool:
        try:
            return bool(self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                  'org.freedesktop.DBus', 'NameHasOwner',
                                  GLib.Variant('(s)', (name,)))[0])
        except BusError:
            return False

    def subscribe(self, sender: Optional[str], iface: str, member: Optional[str],
                  path: Optional[str], callback: Callable[..., None]) -> int:
        """callback(sender, path, iface, member, params_tuple)."""
        def handler(_c, sender_, path_, iface_, member_, params):
            callback(sender_, path_, iface_, member_, params.unpack())
        return self.conn.signal_subscribe(sender, iface, member, path, None,
                                          Gio.DBusSignalFlags.NONE, handler)

    def unsubscribe(self, sub_id: int) -> None:
        self.conn.signal_unsubscribe(sub_id)
