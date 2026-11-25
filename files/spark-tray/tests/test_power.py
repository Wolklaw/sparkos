"""Battery, power profiles and sleep/restart/shutdown, against python-dbusmock's UPower,
power-profiles-daemon and logind. The logind mock only records calls: nothing is slept."""

import unittest

import harness
from harness import MockCase, mock_object, pump

from sparktray import power                           # noqa: E402
from sparktray.dbusutil import Bus                    # noqa: E402

M = 'org.freedesktop.DBus.Mock'


class PowerTest(MockCase):
    def make(self, battery=True, profiles=True, logind=True):
        self.up = self.mock('upower')
        if battery:
            self.up.AddDischargingBattery('mock_BAT', 'Battery', 55.0, 5400, dbus_interface=M)
            # real UPower keeps the DisplayDevice in step; the mock needs telling
            self.up.SetupDisplayDevice(2, 2, 55.0, 30.0, 55.0, 10.0, 5400, 0, True,
                                       'battery-good', 1, dbus_interface=M)
        if profiles:
            self.ppd = self.mock('power_profiles_daemon')
        if logind:
            self.ld = self.mock('logind')
        self.pw = power.Power(Bus.system())
        self.assertTrue(self.pw.start())
        self.addCleanup(self.pw.stop)

    def test_battery_reads_percent_state_and_time(self):
        self.make()
        self.assertTrue(self.pw.has_battery())
        b = self.pw.battery()
        self.assertEqual(round(b.percent), 55)
        self.assertFalse(b.charging)
        self.assertEqual(b.seconds, 5400)

    def test_a_desktop_has_no_battery(self):
        self.make(battery=False)
        self.assertFalse(self.pw.has_battery())

    def test_profiles_and_switching(self):
        self.make()
        s = self.pw.state()
        self.assertIn('balanced', s.profiles)
        self.assertEqual(s.profile, 'balanced')
        self.pw.set_profile('performance')
        self.assertEqual(self.pw.state().profile, 'performance')

    def test_no_profile_service_means_no_profiles(self):
        self.make(profiles=False)
        s = self.pw.state()
        self.assertEqual(s.profiles, [])
        self.assertFalse(self.pw.has_profiles())

    def test_actions_are_asked_of_logind_interactively(self):
        self.make()
        s = self.pw.state()
        self.assertEqual(set(s.can), {'sleep', 'restart', 'shutdown'})
        for action, method in (('sleep', 'Suspend'), ('restart', 'Reboot'),
                               ('shutdown', 'PowerOff')):
            done = []
            self.pw.act(action, lambda e: done.append(e))
            self.assertTrue(pump(lambda: done), action)
            self.assertIsNone(done[0], action)
            calls = mock_object('org.freedesktop.login1', '/org/freedesktop/login1').GetCalls()
            hit = [c for c in calls if c[1] == method]
            self.assertTrue(hit, f"{method} not called")
            self.assertEqual(bool(hit[-1][2][0]), True)     # interactive: polkit may ask


class FormatTest(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(power.format_time(0), '')
        self.assertEqual(power.format_time(12 * 60), '12 min')
        self.assertEqual(power.format_time(65 * 60), '1 h 05')

    def test_battery_icon_follows_charge_and_state(self):
        low = power.Battery(present=True, percent=8, state=power.DISCHARGING)
        full = power.Battery(present=True, percent=100, state=power.FULL)
        charging = power.Battery(present=True, percent=50, state=power.CHARGING)
        self.assertNotEqual(power.battery_icon(low), power.battery_icon(full))
        self.assertIn('charging', power.battery_icon(charging))


if __name__ == '__main__':
    unittest.main()
