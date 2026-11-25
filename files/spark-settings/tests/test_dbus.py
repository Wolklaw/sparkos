"""The D-Bus backends against fake services (python-dbusmock): timedated, localed,
AccountsService, logind and power-profiles-daemon on a private system bus; KWin's input devices
and kglobalaccel on a private session bus. Nothing here can reach the real system or session
bus: the addresses point at buses this file starts and stops. Skipped when python-dbusmock
isn't installed (CI installs it)."""

import os
import shutil
import subprocess
import sys
import unittest

import test_spark_settings as base      # noqa: F401  (sets up HOME, PATH and the fake tools)
from test_spark_settings import calls, reset_calls

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
    from sparksettings import accounts, clock, core, inputdev, plasma, power, shortcuts


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
class SessionServices(dbusmock.DBusTestCase if HAVE_MOCK else object):
    @classmethod
    def setUpClass(cls):
        cls.start_session_bus()
        cls.procs = []
        bus = cls.get_dbus(False)
        p = cls.spawn_server('org.kde.KWin', '/KWin', 'org.kde.KWin', stdout=subprocess.DEVNULL)
        cls.procs.append(p)
        kwin = dbus.Interface(bus.get_object('org.kde.KWin', '/KWin'), dbusmock.MOCK_IFACE)
        kwin.AddMethod('org.kde.KWin', 'reconfigure', '', '', 'pass')
        # the input devices: a mouse, a virtual twin of it, a touchpad
        kwin.AddObject('/org/kde/KWin/InputDevice', 'org.kde.KWin.InputDeviceManager',
                       {'devicesSysNames': dbus.Array(['event2', 'event3', 'event4'], signature='s')}, [])
        for sysname, name, touch, virt in (('event2', 'Test Mouse', False, False),
                                           ('event3', 'Test Mouse', False, True),
                                           ('event4', 'Test Touchpad', True, False)):
            kwin.AddObject(f'/org/kde/KWin/InputDevice/{sysname}', 'org.kde.KWin.InputDevice', {
                'name': name, 'sysName': sysname, 'pointer': True, 'touchpad': touch, 'keyboard': False,
                'isVirtual': virt, 'vendor': dbus.UInt32(1133), 'product': dbus.UInt32(49291),
                'pointerAcceleration': 0.0, 'pointerAccelerationProfileFlat': False,
                'supportsPointerAcceleration': True, 'naturalScroll': False,
                'supportsNaturalScroll': True, 'leftHanded': False,
                'supportsLeftHanded': not touch, 'tapToClick': False,
                'disableWhileTyping': False, 'supportsDisableWhileTyping': touch}, [])
        # kglobalaccel: one component with two actions
        p = cls.spawn_server('org.kde.kglobalaccel', '/kglobalaccel', 'org.kde.KGlobalAccel',
                             stdout=subprocess.DEVNULL)
        cls.procs.append(p)
        cls.ga = dbus.Interface(bus.get_object('org.kde.kglobalaccel', '/kglobalaccel'), dbusmock.MOCK_IFACE)
        cls.ga.AddMethod('org.kde.KGlobalAccel', 'allComponents', '', 'ao', 'ret = ["/component/kwin"]')
        cls.ga.AddMethod('org.kde.KGlobalAccel', 'setForeignShortcut', 'asai', '',
                         'open(%r, "a").write(repr([list(args[0]), list(args[1])]) + "\\n")' % os.path.join(
                             os.environ['HOME'], 'shortcut-calls'))
        cls.ga.AddObject('/component/kwin', 'org.kde.kglobalaccel.Component',
                         {'uniqueName': 'kwin', 'friendlyName': 'KWin'}, [
            ('allShortcutInfos', '', 'a(ssssssaiai)',
             'ret = [("default", "Default Context", "kwin", "KWin", "Overview", "Toggle Overview", '
             '[0x10000000 | 0x57], [0x10000000 | 0x57]), '
             '("default", "Default Context", "kwin", "KWin", "Show Desktop", "Peek at Desktop", [], [0x10000000 | 0x44])]')])

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
            p.wait()
        super().tearDownClass()
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/nonexistent'

    def test_input_devices_are_real_pointers_once_each(self):
        devs = inputdev.devices()
        self.assertEqual([d.name for d in devs], ['Test Mouse', 'Test Touchpad'])
        mouse, pad = devs
        self.assertFalse(mouse.touchpad)
        self.assertTrue(pad.touchpad)
        self.assertIn('leftHanded', [s[0] for s in mouse.settings()])
        self.assertNotIn('leftHanded', [s[0] for s in pad.settings()])
        self.assertIn('tapToClick', [s[0] for s in pad.settings()])

    def test_changing_a_setting_goes_live_and_is_saved(self):
        mouse = inputdev.devices()[0]
        self.assertTrue(inputdev.set_property(mouse, 'naturalScroll', 'b', True))
        self.assertTrue(inputdev.set_property(mouse, 'pointerAcceleration', 'd', 0.5))
        self.assertEqual(inputdev.devices()[0].props['naturalScroll'], True)
        self.assertAlmostEqual(inputdev.devices()[0].props['pointerAcceleration'], 0.5)
        reset_calls()
        self.assertTrue(inputdev.save(inputdev.devices()[0]))
        written = [c for c in calls() if c.startswith('kwriteconfig6 --file kcminputrc')]
        self.assertTrue(any('--group Libinput --group 1133 --group 49291 --group Test Mouse '
                            '--key NaturalScroll true' in c for c in written), written)
        self.assertTrue(any('--key PointerAcceleration 0.500' in c for c in written))
        saved = core.spark_load('input')['devices']['1133:49291:Test Mouse']
        self.assertEqual(saved['naturalScroll'], True)

    def test_kwin_is_asked_to_reread(self):
        self.assertTrue(plasma.kwin_reconfigure())

    def test_shortcuts_list_and_change(self):
        comps = shortcuts.components()
        self.assertEqual([c['name'] for c in comps], ['KWin'])
        acts = shortcuts.actions(comps[0]['path'])
        self.assertEqual([a.name for a in acts], ['Peek at Desktop', 'Toggle Overview'])
        overview = acts[1]
        self.assertEqual(overview.text, 'Meta+W')
        self.assertEqual(acts[0].text, '')
        self.assertEqual(acts[0].default_text, 'Meta+D')
        code = shortcuts.key_code('e', 0x40 | 0x4)       # Super + Ctrl + E
        self.assertEqual(shortcuts.key_text(code), 'Meta+Ctrl+E')
        self.assertIsNone(shortcuts.conflict(acts, acts[0], code))
        self.assertIs(shortcuts.conflict(acts, acts[0], overview.keys[0]), overview)
        log = os.path.join(os.environ['HOME'], 'shortcut-calls')
        if os.path.exists(log):
            os.remove(log)
        self.assertEqual(shortcuts.set_key(acts[0], code), '')
        sent = eval(open(log).read().splitlines()[-1])
        self.assertEqual(sent[0], ['kwin', 'Show Desktop', 'KWin', 'Peek at Desktop'])
        self.assertEqual(sent[1], [code])
        self.assertEqual(shortcuts.reset(acts[0]), '')
        self.assertEqual(eval(open(log).read().splitlines()[-1])[1], [0x10000000 | 0x44])


@unittest.skipUnless(HAVE_MOCK, 'python-dbusmock, dbus-daemon or busctl missing')
class NoBus(unittest.TestCase):
    """With no service answering (the case on a machine without Plasma), every backend gives
    an empty answer or an error text, never an exception."""

    def test_nothing_answers(self):
        old = {k: os.environ.get(k) for k in ('DBUS_SYSTEM_BUS_ADDRESS', 'DBUS_SESSION_BUS_ADDRESS')}
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/nonexistent'
        try:
            self.assertIsNone(clock.ntp())
            self.assertNotEqual(clock.set_zone('Europe/Paris'), '')
            self.assertEqual(accounts.users(), [])
            self.assertEqual(inputdev.devices(), [])
            self.assertEqual(shortcuts.components(), [])
            self.assertFalse(power.can_sleep())
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == '__main__':
    unittest.main()
