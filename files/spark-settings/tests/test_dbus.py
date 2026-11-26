"""The D-Bus backends against fake services (python-dbusmock): timedated, localed,
AccountsService, logind and power-profiles-daemon on a private system bus. Nothing here can
reach the real system or session bus: the addresses point at buses this file starts and stops. Skipped when python-dbusmock
isn't installed (CI installs it)."""

import os
import shutil
import subprocess
import unittest

import test_spark_settings as base      # noqa: F401  (sets up HOME, PATH and the fake tools)

# the fixtures' busctl is a fake for the other tests; these ones need the real one
_clean = os.pathsep.join(d for d in os.environ['PATH'].split(os.pathsep) if d != os.path.join(base.FIX, 'bin'))
REAL_BUSCTL = shutil.which('busctl', path=_clean)
try:
    import dbus
    import dbusmock
    HAVE_MOCK = shutil.which('dbus-daemon') is not None and REAL_BUSCTL is not None
except ImportError:
    HAVE_MOCK = False

if HAVE_MOCK:
    from sparksettings import accounts, clock, power


def setUpModule():
    os.environ['SPARK_TEST_REAL_BUSCTL'] = REAL_BUSCTL or ''


def tearDownModule():
    os.environ.pop('SPARK_TEST_REAL_BUSCTL', None)


@unittest.skipUnless(HAVE_MOCK, 'python-dbusmock, dbus-daemon or busctl missing')
class SystemServices(dbusmock.DBusTestCase if HAVE_MOCK else object):
    @classmethod
    def setUpClass(cls):
        cls.start_system_bus()
        cls.procs = []
        sysbus = cls.get_dbus(True)
        cls.timedated = cls.spawn_server_template('timedated', {'Timezone': 'America/Toronto', 'NTP': True},
                                                  stdout=subprocess.DEVNULL)
        cls.procs.append(cls.timedated[0])
        cls.logind = cls.spawn_server_template('logind', {'CanSuspend': 'yes', 'IdleAction': 'ignore'},
                                               stdout=subprocess.DEVNULL)
        cls.procs.append(cls.logind[0])
        cls.ppd = cls.spawn_server_template('power_profiles_daemon', {}, stdout=subprocess.DEVNULL)
        cls.procs.append(cls.ppd[0])

        # localed: no template, so a plain object with the two things Spark Settings uses
        p = cls.spawn_server('org.freedesktop.locale1', '/org/freedesktop/locale1',
                             'org.freedesktop.locale1', system_bus=True, stdout=subprocess.DEVNULL)
        cls.procs.append(p)
        loc = dbus.Interface(sysbus.get_object('org.freedesktop.locale1', '/org/freedesktop/locale1'),
                             dbusmock.MOCK_IFACE)
        loc.AddProperty('org.freedesktop.locale1', 'Locale', dbus.Array(['LANG=en_CA.UTF-8'], signature='s'))
        loc.AddMethod('org.freedesktop.locale1', 'SetLocale', 'asb', '',
                      'self.Set("org.freedesktop.locale1", "Locale", args[0])')

        # AccountsService: two users
        p = cls.spawn_server('org.freedesktop.Accounts', '/org/freedesktop/Accounts',
                             'org.freedesktop.Accounts', system_bus=True, stdout=subprocess.DEVNULL)
        cls.procs.append(p)
        acc = dbus.Interface(sysbus.get_object('org.freedesktop.Accounts', '/org/freedesktop/Accounts'),
                             dbusmock.MOCK_IFACE)
        cls.acc = acc
        mine = os.getuid()
        for path, name, real, uid, kind in (('/org/freedesktop/Accounts/User1000', 'tester', 'Test User', mine, 1),
                                            ('/org/freedesktop/Accounts/User1001', 'guest', 'Guest', mine + 1, 0)):
            acc.AddObject(path, 'org.freedesktop.Accounts.User', {
                'UserName': name, 'RealName': real, 'Uid': dbus.UInt64(uid), 'AccountType': dbus.Int32(kind),
                'IconFile': '', 'Locked': False}, [
                ('SetRealName', 's', '', 'self.Set("org.freedesktop.Accounts.User", "RealName", args[0])'),
                ('SetAccountType', 'i', '', 'self.Set("org.freedesktop.Accounts.User", "AccountType", args[0])'),
                ('SetIconFile', 's', '', 'self.Set("org.freedesktop.Accounts.User", "IconFile", args[0])')])
        acc.AddMethod('org.freedesktop.Accounts', 'ListCachedUsers', '', 'ao',
                      'ret = ["/org/freedesktop/Accounts/User1000", "/org/freedesktop/Accounts/User1001"]')
        acc.AddMethod('org.freedesktop.Accounts', 'CreateUser', 'ssi', 'o',
                      'ret = "/org/freedesktop/Accounts/User1002"')
        acc.AddMethod('org.freedesktop.Accounts', 'DeleteUser', 'xb', '', '')

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
            p.wait()
        super().tearDownClass()
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=/nonexistent'

    def test_timezone_and_ntp(self):
        self.assertEqual(clock.zone(), 'America/Toronto')
        self.assertTrue(clock.ntp())
        self.assertEqual(clock.set_zone('Europe/Paris'), '')
        self.assertEqual(clock.zone(), 'Europe/Paris')
        self.assertEqual(clock.set_ntp(False), '')
        self.assertFalse(clock.ntp())
        # the mock has no ListTimezones, so the list comes from timedatectl (a fake here)
        self.assertIn('Europe/Paris', clock.zones())

    def test_set_time_sends_microseconds(self):
        self.assertEqual(clock.set_time(2026, 11, 25, 14, 30), '')
        self.assertIn(clock.set_time(2026, 13, 1, 0, 0), [clock.set_time(2026, 13, 1, 0, 0)])
        self.assertNotEqual(clock.set_time(2026, 13, 1, 0, 0), '')      # month 13 is refused

    def test_system_language(self):
        self.assertEqual(clock.system_language(), 'en_CA.UTF-8')
        self.assertEqual(clock.set_system_language('fr_CA.UTF-8'), '')
        self.assertEqual(clock.system_language(), 'fr_CA.UTF-8')

    def test_users(self):
        users = accounts.users()
        self.assertEqual([u.name for u in users], ['tester', 'guest'])
        self.assertTrue(users[0].me and users[0].admin)
        self.assertFalse(users[1].admin)
        self.assertEqual(accounts.set_real_name(users[1], 'Visitor'), '')
        self.assertEqual(accounts.set_admin(users[1], True), '')
        again = {u.name: u for u in accounts.users()}
        self.assertEqual(again['guest'].real_name, 'Visitor')
        self.assertTrue(again['guest'].admin)
        self.assertEqual(accounts.create('newbie', 'New B', False), '')
        self.assertEqual(accounts.remove(again['guest'], False), '')
        self.assertTrue(accounts.valid_name('newbie'))
        self.assertFalse(accounts.valid_name('New User'))
        self.assertFalse(accounts.valid_name('1abc'))

    def test_logind_and_profiles(self):
        self.assertTrue(power.can_sleep())
        self.assertEqual(power.logind_idle(), 'ignore')
        # without powerprofilesctl (Fedora's tuned-ppd has none) the profile goes over D-Bus
        from unittest import mock
        with mock.patch.object(power, 'have', lambda tool: False):
            self.assertEqual(power.profiles(), ['power-saver', 'balanced', 'performance'])
            self.assertEqual(power.current(), 'balanced')
            self.assertTrue(power.set_profile('performance'))
            self.assertEqual(power.current(), 'performance')


@unittest.skipUnless(HAVE_MOCK, 'python-dbusmock, dbus-daemon or busctl missing')
class NoBus(unittest.TestCase):
    """With no service answering (the case in a bare container), every backend gives
    an empty answer or an error text, never an exception."""

    def test_nothing_answers(self):
        old = {k: os.environ.get(k) for k in ('DBUS_SYSTEM_BUS_ADDRESS', 'DBUS_SESSION_BUS_ADDRESS')}
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/nonexistent'
        try:
            self.assertIsNone(clock.ntp())
            self.assertNotEqual(clock.set_zone('Europe/Paris'), '')
            self.assertEqual(accounts.users(), [])
            self.assertFalse(power.can_sleep())
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == '__main__':
    unittest.main()
