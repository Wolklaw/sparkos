"""The Bluetooth backend and the pairing agent, against python-dbusmock's BlueZ 5."""

import unittest

import dbus
import harness
from harness import MockCase, call_async, mock_object, pump, second_connection

from gi.repository import GLib   # noqa: E402

from sparktray import bluez                           # noqa: E402
from sparktray.dbusutil import Bus                    # noqa: E402
from sparktray.text import t                          # noqa: E402

MOCK = 'org.bluez.Mock'
ADDRESS = '11:22:33:44:55:66'


class FakePrompter:
    def __init__(self, answer=True):
        self.answer, self.asked, self.notes = answer, [], []

    def confirm(self, text, done, **_kw):
        self.asked.append(('confirm', text))
        done(self.answer)
        return lambda: None

    def ask(self, text, numeric, done):
        self.asked.append(('ask', text, numeric))
        done(self.answer)
        return lambda: None

    def notify(self, text):
        self.notes.append(text)


class BluetoothTest(MockCase):
    def setUp(self):
        super().setUp()
        self.bz = self.mock('bluez5')
        self.adapter = self.bz.AddAdapter('hci0', 'my-pc', dbus_interface=MOCK)
        self.dev = self.bz.AddDevice('hci0', ADDRESS, 'Headphones', dbus_interface=MOCK)
        self.changes = 0
        self.bt = bluez.Bluetooth(Bus.system(), self._changed)
        self.assertTrue(self.bt.start())

    def tearDown(self):
        self.bt.stop()
        super().tearDown()

    def _changed(self):
        self.changes += 1

    def device(self):
        return next(d for d in self.bt.state().devices if d.address == ADDRESS)

    def calls(self):
        return [c[1] for c in mock_object('org.bluez', self.dev).GetCalls()]

    def test_state_has_adapter_and_devices(self):
        s = self.bt.state()
        self.assertTrue(s.available)
        self.assertEqual(s.adapter, self.adapter)
        self.assertTrue(s.powered)
        self.assertEqual([d.name for d in s.devices], ['Headphones'])
        self.assertFalse(self.device().paired)

    def test_power_off_and_on(self):
        self.bt.set_power(self.adapter, False)
        self.assertFalse(self.bt.state().powered)
        self.bt.set_power(self.adapter, True)
        self.assertTrue(self.bt.state().powered)

    def test_scan_starts_and_stops(self):
        mock_object('org.bluez', self.adapter).AddProperty('org.bluez.Adapter1', 'DiscoveryFilter',
                                                           dbus.Boolean(False))
        done = []
        self.bt.scan(self.adapter, True, lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertIsNone(done[0])
        self.assertTrue(self.bt.state().discovering)
        done.clear()
        self.bt.scan(self.adapter, False, lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertFalse(self.bt.state().discovering)

    def test_pair_trust_connect_disconnect_forget(self):
        done = []
        self.bt.pair(self.device(), lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertIsNone(done[0])
        self.assertTrue(self.device().paired)
        self.assertTrue(self.device().trusted)

        done.clear()
        self.bt.connect(self.device(), lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertIsNone(done[0])
        # the mock doesn't write Connected back into its object list (real BlueZ does), so
        # check the call arrived rather than the state it would produce
        self.assertIn('Connect', self.calls())

        done.clear()
        self.bt.disconnect(self.device(), lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertIsNone(done[0])
        self.assertIn('Disconnect', self.calls())

        done.clear()
        self.bt.forget(self.adapter, self.device(), lambda e: done.append(e))
        self.assertTrue(pump(lambda: done))
        self.assertEqual(self.bt.state().devices, [])

    def test_battery_level_is_read(self):
        mock_object('org.bluez', self.dev).AddProperties(
            'org.bluez.Battery1', {'Percentage': dbus.Byte(73)})
        self.assertEqual(self.device().battery, 73)

    def test_no_adapter_is_not_available(self):
        mock_object('org.bluez', '/').RemoveObject(self.adapter)
        self.assertFalse(self.bt.state().available)


class PairingAgentTest(MockCase):
    def setUp(self):
        super().setUp()
        self.bz = self.mock('bluez5')
        self.bz.AddAdapter('hci0', 'my-pc', dbus_interface=MOCK)
        self.dev = self.bz.AddDevice('hci0', ADDRESS, 'Headphones', dbus_interface=MOCK)
        self.bus = Bus.system()
        self.bt = bluez.Bluetooth(self.bus)
        self.bt.start()

    def tearDown(self):
        self.bt.stop()
        super().tearDown()

    def agent(self, answer=True):
        self.prompter = FakePrompter(answer)
        agent = bluez.PairingAgent(self.bus, self.prompter, bluez.agent_names(self.bt.state), t)
        self.assertTrue(agent.start())
        self.addCleanup(agent.stop)
        return agent

    def call(self, method, params):
        conn = second_connection()
        out, err = call_async(conn, self.bus.conn.get_unique_name(), bluez.AGENT_PATH,
                              bluez.AGENT_IFACE, method, params)
        conn.close_sync(None)
        return out, err

    def test_confirm_shows_the_passkey_and_accepts(self):
        self.agent(True)
        out, err = self.call('RequestConfirmation', GLib.Variant('(ou)', (self.dev, 123456)))
        self.assertIsNone(err, err)
        kind, text = self.prompter.asked[0]
        self.assertIn('123456', text)
        self.assertIn('Headphones', text)

    def test_confirm_refused_is_rejected(self):
        self.agent(False)
        out, err = self.call('RequestConfirmation', GLib.Variant('(ou)', (self.dev, 5)))
        self.assertIsNotNone(err)
        self.assertIn('Rejected', err.message)

    def test_pin_is_passed_back(self):
        self.agent('0000')
        out, err = self.call('RequestPinCode', GLib.Variant('(o)', (self.dev,)))
        self.assertIsNone(err, err)
        self.assertEqual(out, ('0000',))

    def test_passkey_must_be_a_number(self):
        self.agent('12ab')
        out, err = self.call('RequestPasskey', GLib.Variant('(o)', (self.dev,)))
        self.assertIsNotNone(err)
        self.agent_obj = None

    def test_passkey_number_goes_back_as_a_number(self):
        self.agent('482913')
        out, err = self.call('RequestPasskey', GLib.Variant('(o)', (self.dev,)))
        self.assertIsNone(err, err)
        self.assertEqual(out, (482913,))

    def test_display_pin_is_shown_not_asked(self):
        self.agent()
        out, err = self.call('DisplayPinCode', GLib.Variant('(os)', (self.dev, '9876')))
        self.assertIsNone(err, err)
        self.assertIn('9876', self.prompter.notes[0])
        self.assertEqual(self.prompter.asked, [])

    def test_authorize_asks(self):
        self.agent(True)
        out, err = self.call('AuthorizeService', GLib.Variant('(os)', (self.dev, '0000110b-0000-1000-8000-00805f9b34fb')))
        self.assertIsNone(err, err)
        self.assertEqual(self.prompter.asked[0][0], 'confirm')


if __name__ == '__main__':
    unittest.main()
