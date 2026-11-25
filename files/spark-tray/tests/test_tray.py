"""The whole tray, with no window: the controller and the five items against the mocked
services, a fake StatusNotifierWatcher and Spark Audio's saved data. It checks what is shown,
what the menus hold, and that turning an item off gives its tray name back.
Popups need a display and are tested in test_windows.py."""

import os
import tempfile
import unittest

import harness
from harness import AUDIO_FIXTURES, SPARK_AUDIO, MockCase, call_async, pump, session_connection

os.environ['SPARK_AUDIO_DIR'] = SPARK_AUDIO

from gi.repository import GLib   # noqa: E402

from sparktray import core, printers, text   # noqa: E402
from sparktray.app import Tray               # noqa: E402
from sparktray.dbusutil import Bus           # noqa: E402

from test_sni import FakeWatcher             # noqa: E402

M = 'org.freedesktop.DBus.Mock'
PRINTER_P = "printer Office is idle.  enabled since Tue 25 Nov 2026 09:00:00\n" \
            "system default destination: Office\n"


def fake_lpstat(argv):
    import subprocess
    out = PRINTER_P if argv[:2] == ['lpstat', '-p'] else ''
    return subprocess.CompletedProcess(argv, 0, out, '')


class TrayBase(MockCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for k in ('XDG_CONFIG_HOME', 'XDG_STATE_HOME'):
            old = os.environ.get(k)
            os.environ[k] = os.path.join(self.tmp.name, k)
            self.addCleanup(lambda k=k, old=old: os.environ.pop(k, None) if old is None
                            else os.environ.__setitem__(k, old))
        self.watcher = FakeWatcher()
        self.addCleanup(self.watcher.stop)
        self.client = session_connection()
        self.addCleanup(self.client.close_sync, None)

    def services(self, battery=True):
        nm = self.mock('networkmanager')
        wifi = nm.AddWiFiDevice('wifi0', 'wlan0', 30, dbus_interface=M)
        nm.AddAccessPoint(wifi, 'home', 'Home', '00:11:22:33:44:55', 2, 2412, 54000, 80, 0x100,
                          dbus_interface=M)
        bz = self.mock('bluez5')
        bz.AddAdapter('hci0', 'my-pc', dbus_interface='org.bluez.Mock')
        up = self.mock('upower')
        if battery:
            up.AddDischargingBattery('mock_BAT', 'Battery', 55.0, 5400, dbus_interface=M)
            up.SetupDisplayDevice(2, 2, 55.0, 30.0, 55.0, 10.0, 5400, 0, True, 'battery-good', 1,
                                  dbus_interface=M)
        self.mock('power_profiles_daemon')
        self.mock('logind')

    def tray(self, **cfg):
        for k, v in cfg.items():
            c = core.load_config()
            c[k] = v
            core.save_config(c)
        tray = Tray(Bus.system(), Bus.session(), AUDIO_FIXTURES, on_quit=lambda: None)
        tray.items['printers'].printing = printers.Printing(fake_lpstat)
        tray.start(own_name=False)
        self.addCleanup(tray.stop)
        pump(timeout=0.3)
        return tray

    def names(self):
        out, err = call_async(self.client, 'org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'ListNames')
        return [n for n in out[0] if n.startswith('org.kde.StatusNotifierItem-')]


class TrayTest(TrayBase):
    def test_every_item_shows_when_its_service_is_there(self):
        self.services()
        tray = self.tray()
        self.assertEqual(sorted(tray.shown()),
                         ['bluetooth', 'network', 'power', 'printers', 'volume'])
        self.assertTrue(pump(lambda: len(self.names()) == 5))
        self.assertTrue(pump(lambda: len(self.watcher.items) == 5))

    def test_a_desktop_shows_no_power_icon_until_asked(self):
        self.services(battery=False)
        tray = self.tray()
        self.assertNotIn('power', tray.shown())
        self.assertIn('network', tray.shown())
        core.set_item_enabled('power', True)
        c = core.load_config()
        c['power_show_without_battery'] = True
        core.save_config(c)
        tray._reload_config()
        self.assertIn('power', tray.shown())

    def test_no_service_means_no_icon_not_an_error(self):
        up = self.mock('upower')            # only UPower exists on this PC
        tray = self.tray()
        self.assertEqual([n for n in tray.shown() if n not in ('volume', 'printers')], [])

    def test_hide_icon_gives_the_name_back_and_is_remembered(self):
        self.services()
        tray = self.tray()
        self.assertTrue(pump(lambda: len(self.names()) == 5))
        entry = next(e for e in tray.items['bluetooth'].menu() if e.label == text.t('common.hide_icon'))
        entry.callback()
        self.assertNotIn('bluetooth', tray.shown())
        self.assertTrue(pump(lambda: len(self.names()) == 4))
        self.assertFalse(core.load_config()['items']['bluetooth'])

    def test_a_change_made_by_the_command_line_applies_without_a_restart(self):
        self.services()
        tray = self.tray()
        core.set_item_enabled('printers', False)
        self.assertTrue(pump(lambda: 'printers' not in tray.shown(), 4))
        core.set_item_enabled('printers', True)
        self.assertTrue(pump(lambda: 'printers' in tray.shown(), 4))

    def test_icons_titles_tooltips_and_menus_are_filled_in(self):
        self.services()
        tray = self.tray()
        for name in tray.shown():
            item = tray.items[name]
            with self.subTest(item=name):
                self.assertTrue(item.icon())
                self.assertTrue(item.title())
                self.assertNotIn('.', item.title())          # not a raw text key
                labels = [e.label for e in item.menu() if e.label]
                self.assertIn(text.t('common.hide_icon'), labels)
                self.assertIn(text.t('common.quit'), labels)
                for label in labels:
                    self.assertNotRegex(label, r'^[a-z]+\.[a-z_]+$')

    def test_airplane_mode_turns_wifi_and_bluetooth_off_and_back_on(self):
        self.services()
        tray = self.tray()
        net, bt = tray.items['network'], tray.items['bluetooth']
        self.assertTrue(net.net.state().wifi_enabled)
        self.assertTrue(bt.bt.state().powered)
        net.set_airplane(True)
        self.assertFalse(net.net.state().wifi_enabled)
        self.assertFalse(bt.bt.state().powered)
        net.set_airplane(False)
        self.assertTrue(net.net.state().wifi_enabled)
        self.assertTrue(bt.bt.state().powered)

    def test_scroll_and_middle_click_move_the_volume(self):
        self.services()
        tray = self.tray()
        vol = tray.items['volume']
        vol.vol.set_level(0.5)
        vol.scroll(1, 'vertical')
        self.assertGreater(vol.vol.level(), 0.5)
        before = vol.vol.muted()
        vol.secondary()
        self.assertNotEqual(vol.vol.muted(), before)

    def test_stop_gives_every_name_back(self):
        self.services()
        tray = self.tray()
        self.assertTrue(pump(lambda: len(self.names()) == 5))
        tray.stop()
        self.assertTrue(pump(lambda: len(self.names()) == 0))


if __name__ == '__main__':
    unittest.main()
