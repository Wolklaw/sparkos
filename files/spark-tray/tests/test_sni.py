"""The StatusNotifierItem and its menu, talked to the way a tray (the Spark shell's)
talks to it: through a fake StatusNotifierWatcher on a private session bus."""

import unittest

import harness
from harness import MockCase, call_async, pump, session_connection

from gi.repository import Gio, GLib   # noqa: E402

from sparktray import sni   # noqa: E402
from sparktray.dbusutil import Bus   # noqa: E402

WATCHER_XML = """<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
</interface></node>"""


class FakeWatcher:
    def __init__(self):
        self.conn = session_connection()
        self.items = []
        info = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML).interfaces[0]
        self.conn.register_object(sni.WATCHER_PATH, info, self._call, None, None)
        self.own = Gio.bus_own_name_on_connection(self.conn, sni.WATCHER,
                                                  Gio.BusNameOwnerFlags.NONE, None, None)

    def _call(self, _c, _s, _p, _i, _m, params, invocation):
        self.items.append(params.unpack()[0])
        invocation.return_value(None)

    def stop(self):
        Gio.bus_unown_name(self.own)
        self.conn.close_sync(None)


class SniTest(MockCase):
    def setUp(self):
        super().setUp()
        self.clicked, self.activated, self.scrolls, self.second = [], [], [], []
        self.entries = [sni.MenuEntry('One', lambda: self.clicked.append(1)),
                        sni.MenuEntry(separator=True),
                        sni.MenuEntry('Two', lambda: self.clicked.append(2), checked=True),
                        sni.MenuEntry('Off', lambda: self.clicked.append(3), enabled=False)]
        look = sni.Appearance('spark-tray-test', 'Hardware', lambda: 'Title', lambda: 'network-wired',
                              lambda: 'Tip', lambda: self.entries,
                              lambda x, y: self.activated.append((x, y)),
                              lambda: self.second.append(1),
                              lambda d, o: self.scrolls.append((d, o)))
        self.item = sni.StatusNotifierItem(Bus.session().conn, look)
        self.client = session_connection()
        self.addCleanup(self.client.close_sync, None)

    def start(self, watcher=True):
        if watcher:
            self.watcher = FakeWatcher()
            self.addCleanup(self.watcher.stop)
        self.item.show()
        self.addCleanup(self.item.hide)

    def get(self, path, iface, method, params=None):
        out, err = call_async(self.client, self.item.name, path, iface, method, params)
        self.assertIsNone(err, err)
        return out

    def test_registers_with_the_watcher(self):
        self.start()
        self.assertTrue(pump(lambda: self.watcher.items))
        self.assertEqual(self.watcher.items, [self.item.name])

    def test_registers_when_the_watcher_comes_later(self):
        self.start(watcher=False)
        pump(timeout=0.3)
        self.assertFalse(self.item.registered_with_watcher)
        self.watcher = FakeWatcher()
        self.addCleanup(self.watcher.stop)
        self.assertTrue(pump(lambda: self.watcher.items))

    def test_properties(self):
        self.start()
        out = self.get(sni.SNI_PATH, 'org.freedesktop.DBus.Properties', 'GetAll',
                       GLib.Variant('(s)', (sni.SNI_IFACE,)))
        props = out[0]
        self.assertEqual(props['IconName'], 'network-wired')
        self.assertEqual(props['Id'], 'spark-tray-test')
        self.assertEqual(props['Status'], 'Active')
        self.assertEqual(props['Menu'], sni.MENU_PATH)
        self.assertEqual(props['ToolTip'][3], 'Tip')

    def test_menu_layout_has_the_entries(self):
        self.start()
        rev, (root, _p, kids) = self.get(sni.MENU_PATH, sni.MENU_IFACE, 'GetLayout',
                                          GLib.Variant('(iias)', (0, -1, [])))
        self.assertEqual(root, 0)
        labels = [k[1].get('label') for k in kids]
        self.assertEqual(labels, ['One', None, 'Two', 'Off'])
        self.assertEqual(kids[1][1]['type'], 'separator')
        self.assertEqual(kids[2][1]['toggle-state'], 1)
        self.assertFalse(kids[3][1]['enabled'])

    def event(self, i):
        self.get(sni.MENU_PATH, sni.MENU_IFACE, 'Event',
                 GLib.Variant('(isvu)', (i, 'clicked', GLib.Variant('i', 0), 0)))

    def test_clicking_runs_the_entry(self):
        self.start()
        self.event(1)
        self.event(3)
        self.assertEqual(self.clicked, [1, 2])

    def test_disabled_and_separator_do_nothing(self):
        self.start()
        self.event(2)      # separator
        self.event(4)      # disabled
        self.event(99)     # no such entry
        self.assertEqual(self.clicked, [])

    def test_a_failing_entry_does_not_break_the_item(self):
        def boom():
            raise RuntimeError("no")
        self.entries[0].callback = boom
        self.start()
        self.event(1)
        self.event(3)
        self.assertEqual(self.clicked, [2])

    def test_activate_secondary_and_scroll(self):
        self.start()
        self.get(sni.SNI_PATH, sni.SNI_IFACE, 'Activate', GLib.Variant('(ii)', (10, 20)))
        self.get(sni.SNI_PATH, sni.SNI_IFACE, 'SecondaryActivate', GLib.Variant('(ii)', (0, 0)))
        self.get(sni.SNI_PATH, sni.SNI_IFACE, 'Scroll', GLib.Variant('(is)', (-1, 'vertical')))
        self.assertEqual(self.activated, [(10, 20)])
        self.assertEqual(self.second, [1])
        self.assertEqual(self.scrolls, [(-1, 'vertical')])

    def test_menu_is_rebuilt_when_it_changes(self):
        self.start()
        self.entries.append(sni.MenuEntry('Three'))
        self.item.rebuild_menu()
        _rev, (_r, _p, kids) = self.get(sni.MENU_PATH, sni.MENU_IFACE, 'GetLayout',
                                        GLib.Variant('(iias)', (0, -1, [])))
        self.assertEqual(len(kids), 5)

    def has_name(self):
        out, err = call_async(self.client, 'org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'NameHasOwner',
                              GLib.Variant('(s)', (self.item.name,)))
        return out[0]

    def test_hide_gives_the_name_back_and_show_takes_it_again(self):
        self.start()
        self.assertTrue(pump(self.has_name))
        self.item.hide()
        self.assertTrue(pump(lambda: not self.has_name()))
        self.item.show()
        self.assertTrue(pump(self.has_name))


if __name__ == '__main__':
    unittest.main()
