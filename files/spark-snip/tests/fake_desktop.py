"""A stand-in for the XDG portal's Screenshot call, for the tests.

Run on a private session bus.

    python3 fake_desktop.py FOLDER [--no-portal]

Prints READY once its name is owned, and logs every call to FOLDER/calls.txt. The picture it
hands back is a 120 x 80 PNG of one colour, (1, 2, 3).
"""

import os
import sys

import gi

gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib  # noqa: E402

from PIL import Image  # noqa: E402

PORTAL_XML = """
<node><interface name="org.freedesktop.portal.Screenshot">
  <method name="Screenshot"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>
    <arg type="o" direction="out"/></method>
</interface></node>"""


def main():
    folder = sys.argv[1]
    flags = set(sys.argv[2:])
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    calls = open(os.path.join(folder, 'calls.txt'), 'a', encoding='utf-8')

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
