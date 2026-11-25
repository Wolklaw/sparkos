"""The Network backend and the secrets agent, against python-dbusmock's NetworkManager."""

import unittest

import harness
from harness import MOCK, MockCase, call_async, pump, second_connection

from gi.repository import GLib   # noqa: E402

from sparktray import nm                              # noqa: E402
from sparktray.dbusutil import Bus                    # noqa: E402

PSK = 0x100
ENTERPRISE = 0x200


class FakePrompter:
    def __init__(self, answer=None):
        self.answer, self.asked = answer, []

    def ask_secrets(self, name, fields, done):
        self.asked.append((name, fields))
        done(self.answer)
        return lambda: None


class NetworkTest(MockCase):
    def setUp(self):
        super().setUp()
        self.nm = self.mock('networkmanager')
        self.wifi = self.nm.AddWiFiDevice('wifi0', 'wlan0', 30, dbus_interface=MOCK)
        self.eth = self.nm.AddEthernetDevice('eth0', 'enp1s0', 30, dbus_interface=MOCK)
        self.nm.AddAccessPoint(self.wifi, 'home', 'Home', '00:11:22:33:44:55', 2, 2412, 54000, 80,
                               PSK, dbus_interface=MOCK)
        self.nm.AddAccessPoint(self.wifi, 'cafe', 'Cafe', '00:11:22:33:44:56', 2, 2412, 54000, 35,
                               0, dbus_interface=MOCK)
        self.nm.AddAccessPoint(self.wifi, 'work', 'Work', '00:11:22:33:44:57', 2, 2412, 54000, 60,
                               ENTERPRISE, dbus_interface=MOCK)
        self.changes = 0
        self.net = nm.Network(Bus.system(), self._changed)
        self.assertTrue(self.net.start())

    def tearDown(self):
        self.net.stop()
        super().tearDown()

    def _changed(self):
        self.changes += 1

    def test_lists_networks_by_signal(self):
        s = self.net.state()
        self.assertTrue(s.available)
        self.assertEqual([a.ssid for a in s.aps], ['Home', 'Work', 'Cafe'])
        by = {a.ssid: a for a in s.aps}
        self.assertTrue(by['Home'].secured)
        self.assertFalse(by['Cafe'].secured)
        self.assertTrue(by['Work'].enterprise)
        self.assertEqual(s.wifi_device, self.wifi)
        self.assertTrue(s.wifi_present)

    def test_wired_status(self):
        s = self.net.state()
        self.assertEqual([w.interface for w in s.wired], ['enp1s0'])
        self.assertFalse(s.wired[0].connected)

    def test_connect_new_secured_network(self):
        s = self.net.state()
        home = next(a for a in s.aps if a.ssid == 'Home')
        result = []
        self.net.connect(home, s.wifi_device, 'hunter22', lambda err: result.append(err))
        self.assertTrue(pump(lambda: result))
        self.assertIsNone(result[0])
        self.assertEqual(self.net.state().active_ssid, 'Home')
        self.assertGreater(self.changes, 0)

    def test_connect_open_network_sends_no_key(self):
        s = self.net.state()
        cafe = next(a for a in s.aps if a.ssid == 'Cafe')
        result = []
        self.net.connect(cafe, s.wifi_device, None, lambda err: result.append(err))
        self.assertTrue(pump(lambda: result))
        self.assertIsNone(result[0])
        self.assertEqual(self.net.state().active_ssid, 'Cafe')

    def test_enterprise_is_refused_not_guessed(self):
        s = self.net.state()
        work = next(a for a in s.aps if a.ssid == 'Work')
        result = []
        self.net.connect(work, s.wifi_device, 'x', lambda err: result.append(err))
        self.assertTrue(result and result[0] is not None)

    def test_disconnect(self):
        s = self.net.state()
        home = next(a for a in s.aps if a.ssid == 'Home')
        done = []
        self.net.connect(home, s.wifi_device, 'hunter22', lambda e: done.append(e))
        pump(lambda: done)
        s = self.net.state()
        self.assertTrue(s.active_path)
        gone = []
        self.net.disconnect(s.active_path, lambda e: gone.append(e))
        self.assertTrue(pump(lambda: gone))
        self.assertEqual(self.net.state().active_ssid, '')

    def test_wifi_switch_and_airplane(self):
        self.assertTrue(self.net.state().wifi_enabled)
        self.net.set_wifi(False)
        self.assertFalse(self.net.state().wifi_enabled)
        self.net.set_airplane(False)
        self.assertTrue(self.net.state().wifi_enabled)
        self.net.set_airplane(True)
        self.assertFalse(self.net.state().wifi_enabled)

    def test_vpn_lists_what_nm_knows(self):
        V = GLib.Variant
        Bus.system().call(nm.NM, '/org/freedesktop/NetworkManager/Settings',
                          'org.freedesktop.NetworkManager.Settings', 'AddConnection',
                          V('(a{sa{sv}})', ({
                              'connection': {'id': V('s', 'Office'), 'type': V('s', 'vpn'),
                                             'uuid': V('s', '11111111-1111-1111-1111-111111111111')},
                              'vpn': {'service-type': V('s', 'org.freedesktop.NetworkManager.openvpn')}
                          },)))
        vpns = self.net.state().vpns
        self.assertEqual([v.name for v in vpns], ['Office'])
        self.assertFalse(vpns[0].active)

    def test_available_when_the_service_runs(self):
        self.net.stop()
        net = nm.Network(Bus.system())
        self.assertTrue(net.available())


class SecretAgentTest(MockCase):
    def setUp(self):
        super().setUp()
        self.nm = self.mock('networkmanager')
        self.bus = Bus.system()

    def agent(self, answer):
        self.prompter = FakePrompter(answer)
        agent = nm.SecretAgent(self.bus, self.prompter, lambda k: k)
        agent.start()
        self.addCleanup(agent.stop)
        return agent

    def get_secrets(self, flags=nm.FLAG_ALLOW_INTERACTION, setting='802-11-wireless-security'):
        conn = second_connection()
        settings = {'connection': {'id': GLib.Variant('s', 'Home'),
                                   'type': GLib.Variant('s', '802-11-wireless')},
                    setting: {'key-mgmt': GLib.Variant('s', 'wpa-psk')}}
        params = GLib.Variant('(a{sa{sv}}osasu)', (settings, '/org/freedesktop/NetworkManager/Settings/1',
                                                   setting, [], flags))
        out, err = call_async(conn, self.bus.conn.get_unique_name(), nm.AGENT_PATH, nm.AGENT_IFACE,
                              'GetSecrets', params)
        conn.close_sync(None)
        return out, err

    def test_asks_for_the_password_and_returns_it(self):
        self.agent({'psk': 'hunter22'})
        out, err = self.get_secrets()
        self.assertIsNone(err, err)
        self.assertEqual(out[0]['802-11-wireless-security']['psk'], 'hunter22')
        self.assertEqual(self.prompter.asked[0][0], 'Home')
        self.assertEqual([k for k, _l in self.prompter.asked[0][1]], ['psk'])

    def test_cancel_says_user_canceled(self):
        self.agent(None)
        out, err = self.get_secrets()
        self.assertIsNotNone(err)
        self.assertIn('UserCanceled', err.message)

    def test_no_interaction_means_no_window(self):
        self.agent({'psk': 'x'})
        out, err = self.get_secrets(flags=0)
        self.assertIsNotNone(err)
        self.assertIn('NoSecrets', err.message)
        self.assertEqual(self.prompter.asked, [])


if __name__ == '__main__':
    unittest.main()
