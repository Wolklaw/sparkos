"""A stand-in for KWin's ScreenShot2 interface and the portal's Screenshot call, for the tests.

Run on a private session bus. It answers the way KWin 6.8 does: the reply (size, stride,
pixel format) first, then the raw pixels written into the caller's pipe from another thread.

    python3 fake_desktop.py FOLDER [--no-kwin] [--kwin-refuses] [--no-portal]

Prints READY once its names are owned. Every pixel is (x % 256, y % 256, 77).
"""

import os
import sys
import threading

import gi

gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib  # noqa: E402

from PIL import Image  # noqa: E402

WIDTH, HEIGHT = 300, 200
PAD = 16                                 # stride padding, as Qt may add

KWIN_XML = """
<node><interface name="org.kde.KWin.ScreenShot2">
  <property name="Version" type="u" access="read"/>
  <method name="CaptureWorkspace"><arg type="a{sv}" direction="in"/>
    <arg type="h" direction="in"/><arg type="a{sv}" direction="out"/></method>
  <method name="CaptureActiveScreen"><arg type="a{sv}" direction="in"/>
    <arg type="h" direction="in"/><arg type="a{sv}" direction="out"/></method>
  <method name="CaptureActiveWindow"><arg type="a{sv}" direction="in"/>
    <arg type="h" direction="in"/><arg type="a{sv}" direction="out"/></method>
  <method name="CaptureScreen"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>
    <arg type="h" direction="in"/><arg type="a{sv}" direction="out"/></method>
  <method name="CaptureArea"><arg type="i" direction="in"/><arg type="i" direction="in"/>
    <arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="a{sv}" direction="in"/>
    <arg type="h" direction="in"/><arg type="a{sv}" direction="out"/></method>
</interface></node>"""

PORTAL_XML = """
<node><interface name="org.freedesktop.portal.Screenshot">
  <method name="Screenshot"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>
    <arg type="o" direction="out"/></method>
</interface></node>"""


def pixels(width, height, stride):
    rows = []
    for y in range(height):
        row = bytearray(stride)
        for x in range(width):
            row[x * 4:x * 4 + 4] = bytes((x % 256, y % 256, 77, 255))
        rows.append(bytes(row))
    return b''.join(rows)


def write_later(fd, data):
    def run():
        try:
            view = memoryview(data)
            while view:
                done = os.write(fd, view)
                view = view[done:]
        finally:
            os.close(fd)
    threading.Thread(target=run, daemon=True).start()


def main():
    folder = sys.argv[1]
    flags = set(sys.argv[2:])
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    calls = open(os.path.join(folder, 'calls.txt'), 'a', encoding='utf-8')

    def kwin_call(conn, sender, path, iface, method, params, invocation):
        args = params.unpack()
        calls.write(f"{method} {args[:-1]}\n")
        calls.flush()
        if '--kwin-refuses' in flags:
            invocation.return_dbus_error('org.kde.KWin.ScreenShot2.Error.NoAuthorized',
                                         'The process is not authorized to take a screenshot')
            return
        fds = invocation.get_message().get_unix_fd_list()
        fd = fds.get(args[-1])
        width, height = (args[2], args[3]) if method == 'CaptureArea' else (WIDTH, HEIGHT)
        stride = width * 4 + PAD
        results = {'type': GLib.Variant('s', 'raw'), 'format': GLib.Variant('u', 16),
                   'width': GLib.Variant('u', width), 'height': GLib.Variant('u', height),
                   'stride': GLib.Variant('u', stride), 'scale': GLib.Variant('d', 1.0)}
        invocation.return_value(GLib.Variant('(a{sv})', (results,)))
        write_later(fd, pixels(width, height, stride))

    def kwin_property(conn, sender, path, iface, name):
        return GLib.Variant('u', 5)

    def portal_call(conn, sender, path, iface, method, params, invocation):
        _parent, options = params.unpack()
        calls.write(f"portal {method} interactive={options.get('interactive')}\n")
        calls.flush()
        token = options['handle_token']
        request = f"/org/freedesktop/portal/desktop/request/{sender[1:].replace('.', '_')}/{token}"
        invocation.return_value(GLib.Variant('(o)', (request,)))
        shot = os.path.join(folder, 'portal-shot.png')
        Image.new('RGB', (120, 80), (1, 2, 3)).save(shot)

        def respond():
            conn.emit_signal(sender, request, 'org.freedesktop.portal.Request', 'Response',
                             GLib.Variant('(ua{sv})', (0, {'uri': GLib.Variant(
                                 's', 'file://' + shot)})))
            return False
        GLib.timeout_add(50, respond)

    names = []
    if '--no-kwin' not in flags:
        node = Gio.DBusNodeInfo.new_for_xml(KWIN_XML)
        bus.register_object('/org/kde/KWin/ScreenShot2', node.interfaces[0], kwin_call,
                            kwin_property, None)
        names.append('org.kde.KWin.ScreenShot2')
    if '--no-portal' not in flags:
        node = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
        bus.register_object('/org/freedesktop/portal/desktop', node.interfaces[0],
                            portal_call, None, None)
        names.append('org.freedesktop.portal.Desktop')
    for name in names:
        reply = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'RequestName',
                              GLib.Variant('(su)', (name, 4)), GLib.VariantType('(u)'),
                              Gio.DBusCallFlags.NONE, -1, None)
        assert reply.unpack()[0] == 1, f"could not own {name}"
    print('READY', flush=True)
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
