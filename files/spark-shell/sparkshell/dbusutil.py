"""Small helpers over Gio's D-Bus API, shared by the tray, the notification server and the
shell's own control interface. Needs only PyGObject (Gio, GLib)."""

import logging

from gi.repository import Gio, GLib

log = logging.getLogger('spark-shell')


class DBusFail(Exception):
    """Raise from a method handler to send a D-Bus error back to the caller."""

    def __init__(self, message, name='org.freedesktop.DBus.Error.Failed'):
        super().__init__(message)
        self.name = name


def export(conn, path, xml, handler, properties=None):
    """Export every interface in the introspection `xml` at `path`.

    handler(interface, method, args, sender) returns the out arguments as a tuple (or a single
    value for one out argument, or None). `properties` is a dict {(interface, name): value or
    callable} that answers Get/GetAll; values are converted with the XML's signature."""
    info = Gio.DBusNodeInfo.new_for_xml(xml)
    properties = properties or {}

    def on_call(connection, sender, object_path, interface, method, params, invocation):
        try:
            result = handler(interface, method, params.unpack(), sender)
            out = [a.signature for a in invocation.get_method_info().out_args]
            if not out:
                invocation.return_value(None)
                return
            if len(out) == 1 and not isinstance(result, tuple):
                result = (result,)
            invocation.return_value(GLib.Variant('(' + ''.join(out) + ')', result))
        except DBusFail as e:
            invocation.return_dbus_error(e.name, str(e))
        except Exception as e:      # a bug in a handler must not take the shell down
            log.exception('%s.%s failed', interface, method)
            invocation.return_dbus_error('org.freedesktop.DBus.Error.Failed', str(e))

    def on_get(connection, sender, object_path, interface, name):
        prop = None
        for iface in info.interfaces:
            if iface.name == interface:
                prop = iface.lookup_property(name)
        if prop is None:
            return None
        value = properties.get((interface, name))
        value = value() if callable(value) else value
        return GLib.Variant(prop.signature, value)

    ids = []
    for iface in info.interfaces:
        ids.append(conn.register_object(path, iface, on_call, on_get, None))
    return ids


def emit(conn, path, interface, signal, signature, *values):
    conn.emit_signal(None, path, interface, signal,
                     GLib.Variant('(' + signature + ')', tuple(values)) if signature else None)


def call(conn, bus_name, path, interface, method, signature, args, callback=None,
         reply_type=None, timeout=3000):
    """Async method call. callback(result_tuple_or_None, error_or_None)."""
    params = GLib.Variant('(' + signature + ')', tuple(args)) if signature is not None else None

    def done(source, res):
        try:
            reply = source.call_finish(res)
        except GLib.Error as e:
            if callback:
                callback(None, e)
            return
        if callback:
            callback(reply.unpack(), None)

    conn.call(bus_name, path, interface, method, params,
              GLib.VariantType(reply_type) if reply_type else None,
              Gio.DBusCallFlags.NONE, timeout, None, done)


def get_all(conn, bus_name, path, interface, callback):
    """callback(dict_of_properties, error)."""
    def done(result, error):
        callback((result[0] if result else {}), error)
    call(conn, bus_name, path, 'org.freedesktop.DBus.Properties', 'GetAll', 's', (interface,),
         done, '(a{sv})')
