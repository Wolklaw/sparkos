#!/usr/bin/env python3
"""Checks a running Spark session (headless KWin + spark-shell) from the outside, over D-Bus.

Run it by tests/headless.sh, which starts the session first. It: waits for the shell, checks the
panels and wallpapers (one per output), registers a fake StatusNotifierItem and checks the tray
took it, sends notifications (plain, replacing, critical), opens a real window and checks the
task list data, opens the launcher, then takes a screenshot of the whole workspace through KWin.

    session_check.py --outputs 3 --screenshot out-dir
Exit status 0 when every check passed."""

import argparse
import json
import os
import subprocess
import sys
import time

import gi

from gi.repository import Gio, GLib  # noqa: E402

SHELL = 'dev.wolklaw.SparkShell'
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%s  %s%s' % ('PASS' if ok else 'FAIL', name, ('  (%s)' % detail) if detail and not ok
                        else ''), flush=True)
    return ok


def pump(seconds):
    end = time.time() + seconds
    ctx = GLib.MainContext.default()
    while time.time() < end:
        ctx.iteration(False)
        time.sleep(0.01)


def wait_for(predicate, timeout=30.0):
    end = time.time() + timeout
    ctx = GLib.MainContext.default()
    while time.time() < end:
        ctx.iteration(False)
        try:
            value = predicate()
        except GLib.Error:
            value = None
        if value:
            return value
        time.sleep(0.05)
    return None


# -- fake StatusNotifierItem ---------------------------------------------------------------
ITEM_XML = """<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>"""
MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/><property name="Status" type="s" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
<arg type="as" direction="in"/><arg type="u" direction="out"/>
<arg type="(ia{sv}av)" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
</interface></node>"""


def s(text):
    return GLib.Variant('s', text)


class FakeItem:
    def __init__(self, conn, name, item_id):
        self.conn = conn
        self.name = name
        self.id = item_id
        self.calls = []
        item_info = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        conn.register_object('/StatusNotifierItem', item_info, self._item_call, self._item_get,
                             None)
        conn.register_object('/MenuBar', menu_info, self._menu_call, self._menu_get, None)

    def _item_get(self, conn, sender, path, iface, prop):
        values = {'Category': ('s', 'ApplicationStatus'), 'Id': ('s', self.id),
                  'Title': ('s', 'Fake tray item'), 'Status': ('s', 'Active'),
                  'IconName': ('s', 'dialog-information'), 'Menu': ('o', '/MenuBar'),
                  'ItemIsMenu': ('b', False)}
        sig, value = values[prop]
        return GLib.Variant(sig, value)

    def _menu_get(self, conn, sender, path, iface, prop):
        return GLib.Variant('u', 3) if prop == 'Version' else GLib.Variant('s', 'normal')

    def _item_call(self, conn, sender, path, iface, method, params, invocation):
        self.calls.append(method)
        invocation.return_value(None)

    def _menu_call(self, conn, sender, path, iface, method, params, invocation):
        if method == 'GetLayout':
            def entry(ident, props, kids=()):
                return GLib.Variant('(ia{sv}av)', (ident, props, list(kids)))
            sub = entry(3, {'label': s('Sub entry')})
            layout = (0, {'children-display': s('submenu')}, [
                entry(1, {'label': s('_First')}),
                entry(2, {'type': s('separator')}),
                entry(4, {'label': s('More'), 'children-display': s('submenu')}, [sub]),
            ])
            invocation.return_value(GLib.Variant('(u(ia{sv}av))', (1, layout)))
        elif method == 'AboutToShow':
            invocation.return_value(GLib.Variant('(b)', (False,)))
        else:
            self.calls.append('menu-' + method)
            invocation.return_value(None)


def shell_state(conn):
    reply = conn.call_sync(SHELL, '/Shell', SHELL, 'State', None, None,
                           Gio.DBusCallFlags.NONE, 5000, None)
    return json.loads(reply.unpack()[0])


def screenshot(conn, directory):
    """The shell renders each of its windows to a PNG (a headless KWin cannot be captured:
    KWin's ScreenShot2 crashed it in the first container runs)."""
    try:
        reply = conn.call_sync(SHELL, '/Shell', SHELL, 'Screenshot',
                               GLib.Variant('(s)', (directory,)), None,
                               Gio.DBusCallFlags.NONE, 30000, None)
    except GLib.Error as e:
        return False, str(e)
    files = json.loads(reply.unpack()[0])
    return bool(files), ', '.join(os.path.basename(f) for f in files)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outputs', type=int, default=1)
    parser.add_argument('--screenshot', default='', help='directory for the PNGs')
    parser.add_argument('--wayland-display', default='wayland-spark')
    args = parser.parse_args()
    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    up = wait_for(lambda: conn.call_sync(
        'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
        GLib.Variant('(s)', (SHELL,)), None, Gio.DBusCallFlags.NONE, 2000,
        None).unpack()[0], 60)
    if not check('shell is on the bus', bool(up)):
        return 1

    def has_name(name):
        return conn.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', (name,)),
                              None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
    for name in ('org.freedesktop.Notifications', 'org.kde.StatusNotifierWatcher',
                 'org.kde.plasmashell'):
        check('owns ' + name, bool(wait_for(lambda n=name: has_name(n), 20)))

    state = wait_for(lambda: (lambda st: st if len(st['panels']) >= args.outputs else None)(
        shell_state(conn)), 30) or shell_state(conn)
    check('layer-shell is available', state['layer_shell'])
    check('one panel per output (%d)' % args.outputs, len(state['panels']) == args.outputs,
          str(state['panels']))
    check('one wallpaper per output', state['wallpapers'] == args.outputs, str(state['wallpapers']))
    check('window tracker is loaded in KWin', bool(wait_for(
        lambda: shell_state(conn)['tracker_loaded'], 20)))

    # tray: a fake item, as Steam or Discord would register one
    item_name = 'org.kde.StatusNotifierItem-%d-1' % os.getpid()
    fake = FakeItem(conn, item_name, 'spark-fake-item')
    Gio.bus_own_name_on_connection(conn, item_name, Gio.BusNameOwnerFlags.NONE, None, None)
    pump(0.3)
    conn.call_sync('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
                   'org.kde.StatusNotifierWatcher', 'RegisterStatusNotifierItem',
                   GLib.Variant('(s)', (item_name,)), None, Gio.DBusCallFlags.NONE, 3000, None)
    check('tray shows the fake item', bool(wait_for(
        lambda: 'spark-fake-item' in shell_state(conn)['tray'], 15)),
        str(shell_state(conn)['tray']))

    # notifications
    def notify(replaces, summary, hints, actions=()):
        reply = conn.call_sync(
            'org.freedesktop.Notifications', '/org/freedesktop/Notifications',
            'org.freedesktop.Notifications', 'Notify',
            GLib.Variant('(susssasa{sv}i)', ('spark-check', replaces, 'dialog-information',
                                             summary, 'Body of <b>%s</b>' % summary,
                                             list(actions), hints, -1)),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        return reply.unpack()[0]
    first = notify(0, 'First', {}, ['default', 'Open', 'reply', 'Reply'])
    check('Notify returns an id', first > 0)
    again = notify(first, 'First, replaced', {})
    check('replace-id keeps the id', again == first, '%s vs %s' % (again, first))
    crit = notify(0, 'Critical', {'urgency': GLib.Variant('y', 2)})
    check('a second notification gets a new id', crit != first)
    pump(0.5)
    st = shell_state(conn)
    check('two notifications on screen', st['notifications']['active'] == 2, str(st))
    check('history has both', st['notifications']['history'] == 2, str(st))
    caps = conn.call_sync('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                          'org.freedesktop.Notifications', 'GetCapabilities', None, None,
                          Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
    check('capabilities include actions and body', 'actions' in caps and 'body' in caps)

    # a real window: the task list data comes from KWin
    env = dict(os.environ, WAYLAND_DISPLAY=args.wayland_display, GDK_BACKEND='wayland',
               GSK_RENDERER='cairo')
    window = subprocess.Popen(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_window.py')],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        found = wait_for(lambda: [w for w in shell_state(conn)['windows']
                                  if w['title'] == 'Spark test window'], 20)
        check('task list sees a real window', bool(found), str(shell_state(conn)['windows']))
        if found:
            check('window carries its app id', found[0]['app'] == 'dev.wolklaw.SparkTestWindow',
                  str(found[0]))
        pump(1.0)
        conn.call_sync(SHELL, '/Shell', SHELL, 'Key', GLib.Variant('(s)', ('osd-test',)), None,
                       Gio.DBusCallFlags.NONE, 3000, None)
        pump(1.0)
        if args.screenshot:
            ok, detail = screenshot(conn, os.path.join(args.screenshot, 'desktop'))
            check('screenshots of panels, wallpaper, notifications and OSD', ok, detail)
        conn.call_sync(SHELL, '/Shell', SHELL, 'ToggleLauncher', None, None,
                       Gio.DBusCallFlags.NONE, 3000, None)
        check('launcher opens', bool(wait_for(lambda: shell_state(conn)['launcher_open'], 10)))
        pump(1.0)
        if args.screenshot:
            ok, detail = screenshot(conn, os.path.join(args.screenshot, 'launcher-open'))
            check('screenshot with the launcher open', ok, detail)
        conn.call_sync(SHELL, '/Shell', SHELL, 'ToggleLauncher', None, None,
                       Gio.DBusCallFlags.NONE, 3000, None)
    finally:
        window.terminate()
        try:
            window.wait(5)
        except subprocess.TimeoutExpired:
            window.kill()
    pump(0.5)
    check('window gone from the task list after it closes', not [
        w for w in shell_state(conn)['windows'] if w['title'] == 'Spark test window'])
    print('%d of %d checks passed' % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
