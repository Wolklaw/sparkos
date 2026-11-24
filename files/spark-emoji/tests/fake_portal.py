#!/usr/bin/env python3
"""A fake xdg-desktop-portal RemoteDesktop on the session bus, for tests/test_paste.py.

    fake_portal.py LOGFILE [--deny] [--no-keyboard]

Answers like the real portal: each call returns a request path, then a Response signal is
emitted there. Every call is appended to LOGFILE as one JSON line. Never run it on a real
session bus: it would take the portal's name (it only can if nothing else owns it)."""

import json
import sys

from gi.repository import Gio, GLib

PORTAL = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
REQUEST = 'org.freedesktop.portal.Request'
XML = """
<node>
  <interface name="org.freedesktop.portal.RemoteDesktop">
    <method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="SelectDevices"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="Start"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="NotifyKeyboardKeycode"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="in"/></method>
  </interface>
  <interface name="org.freedesktop.portal.Session">
    <method name="Close"/>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
  </interface>
</node>
"""


def main():
    log_path = sys.argv[1]
    deny = '--deny' in sys.argv
    no_keyboard = '--no-keyboard' in sys.argv
    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def log(entry):
        with open(log_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def respond(path, code, results):
        def go():
            conn.emit_signal(None, path, REQUEST, 'Response',
                             GLib.Variant('(ua{sv})', (code, results)))
            return False
        GLib.idle_add(go)

    def on_call(_conn, sender, _path, iface, method, params, invocation):
        args = params.unpack()
        if iface == 'org.freedesktop.DBus.Properties':
            devices = 0 if no_keyboard else 3
            invocation.return_value(GLib.Variant('(v)', (GLib.Variant('u', devices),)))
            return
        if method == 'NotifyKeyboardKeycode':
            log({'method': method, 'code': args[2], 'state': args[3]})
            invocation.return_value(None)
            return
        if method == 'Close':
            log({'method': 'Close'})
            invocation.return_value(None)
            return
        options = args[-1]
        log({'method': method, 'options': {k: v for k, v in options.items()}})
        req = '/org/freedesktop/portal/desktop/request/%s/%s' % (
            sender.lstrip(':').replace('.', '_'), options['handle_token'])
        invocation.return_value(GLib.Variant('(o)', (req,)))
        if method == 'CreateSession':
            respond(req, 0, {'session_handle': GLib.Variant('s', '/fake/session/1')})
        elif method == 'SelectDevices':
            respond(req, 0, {})
        elif method == 'Start':
            if deny:
                respond(req, 1, {})
            else:
                respond(req, 0, {'devices': GLib.Variant('u', 1),
                                 'restore_token': GLib.Variant('s', 'token-from-portal')})

    node = Gio.DBusNodeInfo.new_for_xml(XML)
    for info in node.interfaces:
        conn.register_object(PATH, info, on_call, None, None)
    loop = GLib.MainLoop()
    Gio.bus_own_name_on_connection(conn, PORTAL, Gio.BusNameOwnerFlags.NONE,
                                   lambda *a: log({'method': 'ready'}), None)
    loop.run()


if __name__ == '__main__':
    main()
