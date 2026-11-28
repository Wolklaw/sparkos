"""spark-portal on private buses: the real backend process, a fake login1 on a private "system"
bus, fake org.freedesktop.Notifications and org.freedesktop.ScreenSaver on the session bus, a
throwaway HOME and no display. Every impl interface is called directly, the way
xdg-desktop-portal calls it. Dialogs are answered by SPARK_PORTAL_TEST_DIALOG."""

import json
import os
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import gi
from gi.repository import Gio, GLib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
NAME = 'org.freedesktop.impl.portal.desktop.sparkos'
PATH = '/org/freedesktop/portal/desktop'
IMPL = 'org.freedesktop.impl.portal.'
SESSION_PATH = '/org/freedesktop/login1/session/_31'

LOGIND_XML = '''<node>
 <interface name="org.freedesktop.login1.Manager">
  <method name="Inhibit"><arg type="s" direction="in"/><arg type="s" direction="in"/>
   <arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="h" direction="out"/></method>
  <method name="GetSession"><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
  <method name="GetSessionByPID"><arg type="u" direction="in"/><arg type="o" direction="out"/></method>
  <signal name="PrepareForShutdown"><arg type="b"/></signal>
 </interface>
 <interface name="org.freedesktop.login1.Session">
  <property name="LockedHint" type="b" access="read"/>
 </interface></node>'''
NOTES_XML = '''<node><interface name="org.freedesktop.Notifications">
  <method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/>
   <arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/>
   <arg type="as" direction="in"/><arg type="a{sv}" direction="in"/><arg type="i" direction="in"/>
   <arg type="u" direction="out"/></method>
  <method name="CloseNotification"><arg type="u" direction="in"/></method>
  <signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
  <signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
 </interface></node>'''
SAVER_XML = '''<node><interface name="org.freedesktop.ScreenSaver">
  <method name="Inhibit"><arg type="s" direction="in"/><arg type="s" direction="in"/>
   <arg type="u" direction="out"/></method>
  <method name="UnInhibit"><arg type="u" direction="in"/></method></interface></node>'''

FAKE_LPSTAT = '''#!/bin/sh
echo "printer Office is idle.  enabled since Mon Jan  1 00:00:00 2024"
echo "printer Lab disabled since Mon Jan  1 00:00:00 2024 -"
echo "system default destination: Office"
'''
FAKE_LP = '''#!/bin/sh
echo "$*" > "$FAKE_LP_OUT.args"
cat > "$FAKE_LP_OUT.data"
'''

ANSWERS = {
    'access': [{'accept': True, 'values': {'choices': {'remember': 'true', 'mode': 'b'}}},
               {'accept': False}, {'accept': True, 'delay_ms': 60000}],
    'account': {'accept': True},
    'launcher': {'accept': True, 'values': {'name': 'Renamed'}},
    'print': {'accept': True, 'values': {'printer': 'Office', 'copies': 2}},
}


def vd(**kw):
    return dict(kw)


def start_bus():
    proc = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                            stdout=subprocess.PIPE, text=True)
    return proc, proc.stdout.readline().strip()


def connect(address):
    return Gio.DBusConnection.new_for_address_sync(
        address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
        Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.02)
    return None


class Fakes(threading.Thread):
    """login1 on the system bus, Notifications and ScreenSaver on the session bus, and a
    listener that collects every signal the backend sends."""

    def __init__(self, session_addr, system_addr):
        super().__init__(daemon=True)
        self.session_addr, self.system_addr = session_addr, system_addr
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.inhibitors, self.pipes = [], []     # logind Inhibit calls, the read ends we keep
        self.notified, self.closed, self.saver, self.unsaver = [], [], [], []
        self.signals = []                        # (interface, signal, args)
        self.locked, self.next_note, self.next_cookie = False, 100, 7

    def run(self):
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        self.system = connect(self.system_addr)
        self.session = connect(self.session_addr)
        self.system.register_object('/org/freedesktop/login1',
                                    Gio.DBusNodeInfo.new_for_xml(LOGIND_XML).interfaces[0],
                                    self._login_call, None, None)
        self.system.register_object(SESSION_PATH,
                                    Gio.DBusNodeInfo.new_for_xml(LOGIND_XML).interfaces[1],
                                    None, lambda *a: GLib.Variant('b', self.locked), None)
        Gio.bus_own_name_on_connection(self.system, 'org.freedesktop.login1',
                                       Gio.BusNameOwnerFlags.NONE, None, None)
        self.session.register_object('/org/freedesktop/Notifications',
                                     Gio.DBusNodeInfo.new_for_xml(NOTES_XML).interfaces[0],
                                     self._notes_call, None, None)
        self.session.register_object('/org/freedesktop/ScreenSaver',
                                     Gio.DBusNodeInfo.new_for_xml(SAVER_XML).interfaces[0],
                                     self._saver_call, None, None)
        for name in ('org.freedesktop.Notifications', 'org.freedesktop.ScreenSaver'):
            Gio.bus_own_name_on_connection(self.session, name, Gio.BusNameOwnerFlags.NONE, None, None)
        self.session.signal_subscribe(NAME, None, None, None, None, 0, self._signal)
        self.ready.set()
        GLib.MainLoop.new(ctx, False).run()

    def _signal(self, conn, sender, path, iface, name, params):
        with self.lock:
            self.signals.append((iface, name, params.unpack()))

    def _login_call(self, conn, sender, path, iface, method, params, inv):
        if method == 'Inhibit':
            with self.lock:
                self.inhibitors.append(params.unpack())
            r, w = os.pipe()
            fds = Gio.UnixFDList()
            idx = fds.append(w)
            os.close(w)
            self.pipes.append(r)
            inv.return_value_with_unix_fd_list(GLib.Variant('(h)', (idx,)), fds)
        else:
            inv.return_value(GLib.Variant('(o)', (SESSION_PATH,)))

    def _notes_call(self, conn, sender, path, iface, method, params, inv):
        with self.lock:
            if method == 'Notify':
                self.notified.append(params.unpack())
                self.next_note += 1
                inv.return_value(GLib.Variant('(u)', (self.next_note,)))
                return
            self.closed.append(params.unpack()[0])
        inv.return_value(None)

    def _saver_call(self, conn, sender, path, iface, method, params, inv):
        with self.lock:
            if method == 'Inhibit':
                self.saver.append(params.unpack())
                self.next_cookie += 1
                inv.return_value(GLib.Variant('(u)', (self.next_cookie,)))
                return
            self.unsaver.append(params.unpack()[0])
        inv.return_value(None)

    def emit(self, conn, path, iface, name, params, dest=None):
        conn.emit_signal(dest, path, iface, name, params)

    def signals_named(self, name):
        with self.lock:
            return [s for s in self.signals if s[1] == name]


def pipe_closed(fd) -> bool:
    """True when the other end of the pipe is closed (what the backend dropping its inhibitor looks like)."""
    ready, _, _ = select.select([fd], [], [], 0)
    return bool(ready) and os.read(fd, 1) == b''


class PortalBus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('dbus-daemon'):
            raise unittest.SkipTest('no dbus-daemon')
        cls.tmp = tempfile.mkdtemp(prefix='spark-portal-test-')
        home = cls.home = os.path.join(cls.tmp, 'home')
        cls.runtime = os.path.join(cls.tmp, 'run')
        for d in (home, cls.runtime, os.path.join(home, '.config', 'spark'),
                  os.path.join(cls.tmp, 'bin')):
            os.makedirs(d)
        os.chmod(cls.runtime, 0o700)
        for name, body in (('lpstat', FAKE_LPSTAT), ('lp', FAKE_LP)):
            path = os.path.join(cls.tmp, 'bin', name)
            with open(path, 'w') as f:
                f.write(body)
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        cls.lp_out = os.path.join(cls.tmp, 'lp')
        cls.log = os.path.join(cls.tmp, 'dialogs.log')
        cls.session_proc, cls.session_addr = start_bus()
        cls.system_proc, cls.system_addr = start_bus()
        cls.fakes = Fakes(cls.session_addr, cls.system_addr)
        cls.fakes.start()
        assert cls.fakes.ready.wait(10)
        env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'WAYLAND_DISPLAY')}
        env.update({
            'HOME': home, 'XDG_CONFIG_HOME': os.path.join(home, '.config'),
            'XDG_DATA_HOME': os.path.join(home, '.local', 'share'),
            'XDG_CACHE_HOME': os.path.join(home, '.cache'), 'XDG_RUNTIME_DIR': cls.runtime,
            'DBUS_SESSION_BUS_ADDRESS': cls.session_addr,
            'DBUS_SYSTEM_BUS_ADDRESS': cls.system_addr, 'XDG_SESSION_ID': '31',
            'GSETTINGS_BACKEND': 'keyfile', 'PYTHONPATH': ROOT, 'SPARK_LANG': 'en',
            'PATH': os.path.join(cls.tmp, 'bin') + os.pathsep + os.environ['PATH'],
            'SPARK_PORTAL_TEST_DIALOG': json.dumps(ANSWERS), 'SPARK_PORTAL_TEST_LOG': cls.log,
            'FAKE_LP_OUT': cls.lp_out})
        cls.backend = subprocess.Popen([sys.executable, '-s', '-m', 'sparksession.portal_backend'],
                                       env=env, cwd=ROOT)
        cls.client = connect(cls.session_addr)
        if not wait_for(lambda: cls.client.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                'NameHasOwner', GLib.Variant('(s)', (NAME,)), None, 0, -1, None).unpack()[0], 15):
            raise RuntimeError('the backend did not start')
        # let it find the logind session before the tests look at screensaver-active
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.backend.terminate()
        cls.backend.wait(10)
        cls.client.close_sync(None)
        for p in (cls.session_proc, cls.system_proc):
            p.terminate()
            p.wait(5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # helpers

    def call(self, iface, method, params, sig, conn=None, fds=None):
        conn = conn or self.client
        if fds is not None:
            return conn.call_with_unix_fd_list_sync(
                NAME, PATH, IMPL + iface, method, GLib.Variant(sig, params), None, 0, 20000,
                fds, None)[0]
        return conn.call_sync(NAME, PATH, IMPL + iface, method, GLib.Variant(sig, params), None,
                              0, 20000, None)

    def prop(self, iface, name):
        return self.client.call_sync(NAME, PATH, 'org.freedesktop.DBus.Properties', 'Get',
                                     GLib.Variant('(ss)', (IMPL + iface, name)), None, 0, 5000,
                                     None).unpack()[0]

    def close_request(self, handle):
        self.client.call_sync(NAME, handle, IMPL + 'Request', 'Close', None, None, 0, 5000, None)

    def dialog_specs(self):
        with open(self.log) as f:
            return [d for d in (json.loads(line) for line in f if line.strip()) if 'kind' in d]

    # Settings

    def test_01_settings_read(self):
        v = self.call('Settings', 'Read', ('org.freedesktop.appearance', 'color-scheme'), '(ss)').unpack()[0]
        self.assertEqual(v, 1)
        r, g, b = self.call('Settings', 'Read', ('org.freedesktop.appearance', 'accent-color'),
                            '(ss)').unpack()[0]
        self.assertEqual((round(r * 255), round(g * 255), round(b * 255)), (0x3d, 0xe8, 0xc8))
        self.assertEqual(self.call('Settings', 'Read', ('org.freedesktop.appearance', 'contrast'),
                                   '(ss)').unpack()[0], 0)
        with self.assertRaises(GLib.Error) as cm:
            self.call('Settings', 'Read', ('org.freedesktop.appearance', 'nope'), '(ss)')
        self.assertIn('NotFound', cm.exception.message)
        self.assertEqual(self.prop('Settings', 'version'), 2)

    def test_02_settings_read_all(self):
        got = self.call('Settings', 'ReadAll', (['org.freedesktop.*'],), '(as)').unpack()[0]
        self.assertEqual(list(got), ['org.freedesktop.appearance'])
        self.assertEqual(got['org.freedesktop.appearance']['color-scheme'], 1)
        none = self.call('Settings', 'ReadAll', (['org.nothing.*'],), '(as)').unpack()[0]
        self.assertEqual(none, {})
        everything = self.call('Settings', 'ReadAll', ([],), '(as)').unpack()[0]
        self.assertIn('org.freedesktop.appearance', everything)
        if Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.interface', True):
            gnome = self.call('Settings', 'ReadAll', (['org.gnome.*'],), '(as)').unpack()[0]
            self.assertEqual(gnome['org.gnome.desktop.interface']['color-scheme'], 'prefer-dark')

    def test_03_reduced_motion_and_signal(self):
        path = os.path.join(self.home, '.config', 'spark', 'appearance.json')
        before = len(self.fakes.signals_named('SettingChanged'))
        with open(path, 'w') as f:
            json.dump({'animations': False}, f)
        self.assertEqual(self.call('Settings', 'Read', ('org.freedesktop.appearance',
                                                        'reduced-motion'), '(ss)').unpack()[0], 1)
        got = wait_for(lambda: self.fakes.signals_named('SettingChanged')[before:])
        self.assertTrue(got, 'no SettingChanged')
        self.assertEqual(got[0][2][:2], ('org.freedesktop.appearance', 'reduced-motion'))
        self.assertEqual(got[0][2][2], 1)
        os.unlink(path)
        self.assertEqual(self.call('Settings', 'Read', ('org.freedesktop.appearance',
                                                        'reduced-motion'), '(ss)').unpack()[0], 0)

    # Inhibit

    def inhibit(self, handle, flags, conn=None, app='org.example.Player'):
        self.call('Inhibit', 'Inhibit', (handle, app, '', flags, {'reason': GLib.Variant('s', 'Playing')}),
                  '(ossua{sv})', conn=conn)

    def test_10_suspend_holds_and_releases(self):
        n = len(self.fakes.inhibitors)
        self.inhibit('/org/freedesktop/portal/desktop/request/t/sus', 4)
        self.assertTrue(wait_for(lambda: len(self.fakes.inhibitors) > n))
        what, who, why, mode = self.fakes.inhibitors[n]
        self.assertEqual((what, mode, why), ('sleep', 'delay', 'Playing'))
        fd = self.fakes.pipes[n]
        time.sleep(0.2)
        self.assertFalse(pipe_closed(fd))
        self.close_request('/org/freedesktop/portal/desktop/request/t/sus')
        self.assertTrue(wait_for(lambda: pipe_closed(fd)), 'inhibitor fd was kept')

    def test_11_logout_registry(self):
        reg = os.path.join(self.runtime, 'spark-wl', 'portal-inhibit.json')
        n = len(self.fakes.inhibitors)
        handle = '/org/freedesktop/portal/desktop/request/t/out'
        self.inhibit(handle, 1)
        self.assertTrue(wait_for(lambda: len(self.fakes.inhibitors) > n))
        self.assertEqual(self.fakes.inhibitors[n][0], 'shutdown')
        with open(reg) as f:
            entries = json.load(f)
        self.assertEqual([e['app_id'] for e in entries], ['org.example.Player'])
        self.close_request(handle)
        self.assertTrue(wait_for(lambda: not os.path.exists(reg) or json.load(open(reg)) == []))
        self.assertTrue(wait_for(lambda: pipe_closed(self.fakes.pipes[n])))

    def test_12_idle_goes_to_the_shell(self):
        handle = '/org/freedesktop/portal/desktop/request/t/idle'
        n = len(self.fakes.saver)
        before = len(self.fakes.inhibitors)
        self.inhibit(handle, 8)
        self.assertTrue(wait_for(lambda: len(self.fakes.saver) > n))
        self.assertEqual(self.fakes.saver[n], ('org.example.Player', 'Playing'))
        self.assertEqual(len(self.fakes.inhibitors), before, 'idle alone needs no logind inhibitor')
        cookie = self.fakes.next_cookie
        self.close_request(handle)
        self.assertTrue(wait_for(lambda: cookie in self.fakes.unsaver))

    def test_13_caller_leaving_releases(self):
        conn = connect(self.session_addr)
        n = len(self.fakes.inhibitors)
        self.inhibit('/org/freedesktop/portal/desktop/request/t/gone', 4 | 8, conn=conn)
        self.assertTrue(wait_for(lambda: len(self.fakes.inhibitors) > n))
        cookie = self.fakes.next_cookie
        time.sleep(0.2)
        self.assertFalse(pipe_closed(self.fakes.pipes[n]))
        conn.close_sync(None)
        self.assertTrue(wait_for(lambda: pipe_closed(self.fakes.pipes[n])), 'fd kept after the app left')
        self.assertTrue(wait_for(lambda: cookie in self.fakes.unsaver))

    def test_14_monitor(self):
        session = '/org/freedesktop/portal/desktop/session/t/mon'
        before = len(self.fakes.signals_named('StateChanged'))
        r = self.call('Inhibit', 'CreateMonitor', ('/org/freedesktop/portal/desktop/request/t/m',
                                                   session, 'org.example.Player', ''), '(ooss)')
        self.assertEqual(r.unpack(), (0,))
        first = wait_for(lambda: self.fakes.signals_named('StateChanged')[before:])
        self.assertTrue(first)
        self.assertEqual(first[0][2][0], session)
        self.assertEqual(first[0][2][1]['session-state'], 1)
        self.assertFalse(first[0][2][1]['screensaver-active'])
        n = len(self.fakes.signals_named('StateChanged'))
        self.fakes.locked = True
        self.fakes.emit(self.fakes.system, SESSION_PATH, 'org.freedesktop.DBus.Properties',
                        'PropertiesChanged',
                        GLib.Variant('(sa{sv}as)', ('org.freedesktop.login1.Session',
                                                    {'LockedHint': GLib.Variant('b', True)}, [])))
        got = wait_for(lambda: self.fakes.signals_named('StateChanged')[n:])
        self.assertTrue(got, 'lock did not reach the monitor')
        self.assertTrue(got[-1][2][1]['screensaver-active'])
        n = len(self.fakes.signals_named('StateChanged'))
        self.fakes.emit(self.fakes.system, '/org/freedesktop/login1', 'org.freedesktop.login1.Manager',
                        'PrepareForShutdown', GLib.Variant('(b)', (True,)))
        got = wait_for(lambda: self.fakes.signals_named('StateChanged')[n:])
        self.assertTrue(got)
        self.assertEqual(got[-1][2][1]['session-state'], 3)
        self.client.call_sync(NAME, PATH, IMPL + 'Inhibit', 'QueryEndResponse',
                              GLib.Variant('(o)', (session,)), None, 0, 5000, None)
        closed = len(self.fakes.signals_named('Closed'))
        self.client.call_sync(NAME, session, IMPL + 'Session', 'Close', None, None, 0, 5000, None)
        self.assertTrue(wait_for(lambda: len(self.fakes.signals_named('Closed')) > closed))
        self.assertEqual(self.prop('Inhibit', 'version'), 3)

    # Notification

    def test_20_notification_round_trip(self):
        note = vd(title=GLib.Variant('s', 'New mail'), body=GLib.Variant('s', 'Hi'),
                  priority=GLib.Variant('s', 'high'),
                  icon=GLib.Variant('(sv)', ('themed', GLib.Variant('as', ['mail-unread']))),
                  **{'default-action': GLib.Variant('s', 'app.open'),
                     'default-action-target': GLib.Variant('s', 'inbox'),
                     'buttons': GLib.Variant('aa{sv}', [
                         {'label': GLib.Variant('s', 'Reply'), 'action': GLib.Variant('s', 'app.reply')}])})
        n = len(self.fakes.notified)
        self.call('Notification', 'AddNotification', ('org.example.Mail', 'n1', note), '(ssa{sv})')
        self.assertTrue(wait_for(lambda: len(self.fakes.notified) > n))
        app, replaces, icon, summary, body, actions, hints, _timeout = self.fakes.notified[n]
        self.assertEqual((app, replaces, icon, summary, body), ('org.example.Mail', 0, 'mail-unread',
                                                               'New mail', 'Hi'))
        self.assertEqual(actions, ['default', '', '0:app.reply', 'Reply'])
        self.assertEqual(hints['urgency'], 1)
        shell_id = self.fakes.next_note
        # the same id again replaces
        self.call('Notification', 'AddNotification', ('org.example.Mail', 'n1', note), '(ssa{sv})')
        self.assertTrue(wait_for(lambda: len(self.fakes.notified) > n + 1))
        self.assertEqual(self.fakes.notified[n + 1][1], shell_id)
        shell_id = self.fakes.next_note
        before = len(self.fakes.signals_named('ActionInvoked'))
        self.fakes.emit(self.fakes.session, '/org/freedesktop/Notifications',
                        'org.freedesktop.Notifications', 'ActionInvoked',
                        GLib.Variant('(us)', (shell_id, 'default')))
        got = wait_for(lambda: self.fakes.signals_named('ActionInvoked')[before:])
        self.assertTrue(got, 'no ActionInvoked came back')
        app_id, nid, action, params = got[0][2]
        self.assertEqual((app_id, nid, action, params), ('org.example.Mail', 'n1', 'app.open', ['inbox']))
        self.fakes.emit(self.fakes.session, '/org/freedesktop/Notifications',
                        'org.freedesktop.Notifications', 'ActionInvoked',
                        GLib.Variant('(us)', (shell_id, '0:app.reply')))
        got = wait_for(lambda: self.fakes.signals_named('ActionInvoked')[before + 1:])
        self.assertEqual(got[0][2], ('org.example.Mail', 'n1', 'app.reply', []))
        self.call('Notification', 'RemoveNotification', ('org.example.Mail', 'n1'), '(ss)')
        self.assertTrue(wait_for(lambda: shell_id in self.fakes.closed))
        self.assertEqual(self.prop('Notification', 'SupportedOptions'), {})
        self.assertEqual(self.prop('Notification', 'version'), 2)

    # Dialogs

    def test_30_access_dialog(self):
        handle = '/org/freedesktop/portal/desktop/request/t/acc1'
        opts = vd(grant_label=GLib.Variant('s', 'Share'),
                  choices=GLib.Variant('a(ssa(ss)s)', [('remember', 'Remember', [], 'false'),
                                                       ('mode', 'Mode', [('a', 'A'), ('b', 'B')], 'a')]))
        r = self.call('Access', 'AccessDialog', (handle, 'org.example.App', '', 'Camera',
                                                 'Use the camera?', 'It wants to.', opts),
                      '(osssssa{sv})').unpack()
        self.assertEqual(r[0], 0)
        self.assertEqual(sorted(r[1]['choices']), [('mode', 'b'), ('remember', 'true')])
        spec = self.dialog_specs()[-1]
        self.assertEqual((spec['kind'], spec['title'], spec['grant']), ('access', 'Camera', 'Share'))
        # the second answer refuses
        r = self.call('Access', 'AccessDialog', ('/org/freedesktop/portal/desktop/request/t/acc2',
                                                 'org.example.App', '', 'Mic', '', '', vd()),
                      '(osssssa{sv})').unpack()
        self.assertEqual(r, (1, {}))

    def test_31_request_close_ends_the_dialog(self):
        handle = '/org/freedesktop/portal/desktop/request/t/acc3'
        result = {}

        def ask():
            conn = connect(self.session_addr)
            result['r'] = self.call('Access', 'AccessDialog', (handle, 'org.example.App', '', 'Late',
                                                                '', '', vd()), '(osssssa{sv})',
                                    conn=conn).unpack()
            conn.close_sync(None)
        t = threading.Thread(target=ask)
        t.start()
        time.sleep(0.5)
        self.close_request(handle)
        t.join(10)
        self.assertEqual(result.get('r'), (2, {}))

    def test_32_account(self):
        r = self.call('Account', 'GetUserInformation', ('/org/freedesktop/portal/desktop/request/t/acct',
                                                        'org.example.App', '',
                                                        vd(reason=GLib.Variant('s', 'To greet you'))),
                      '(ossa{sv})').unpack()
        self.assertEqual(r[0], 0)
        self.assertTrue(r[1]['id'])
        self.assertTrue(r[1]['name'])
        spec = self.dialog_specs()[-1]
        self.assertEqual(spec['kind'], 'account')
        self.assertIn('To greet you', spec['body'])

    def test_33_email(self):
        r = self.call('Email', 'ComposeEmail', ('/org/freedesktop/portal/desktop/request/t/mail',
                                                'org.example.App', '',
                                                vd(addresses=GLib.Variant('as', ['a@b.c']),
                                                   subject=GLib.Variant('s', 'Hi there'))),
                      '(ossa{sv})').unpack()
        self.assertEqual(r, (0, {}))
        with open(self.log) as f:
            last = [json.loads(line) for line in f if '"opened"' in line][-1]
        self.assertEqual(last['opened'], 'mailto:a@b.c?subject=Hi%20there')

    def test_34_launcher(self):
        icon = GLib.Variant('v', GLib.Variant('(sv)', ('themed', GLib.Variant('as', ['firefox']))))
        r = self.call('DynamicLauncher', 'PrepareInstall',
                      ('/org/freedesktop/portal/desktop/request/t/dl', 'org.example.Browser', '', 'Site',
                       icon, vd()), '(osssva{sv})').unpack()
        self.assertEqual(r[0], 0)
        self.assertEqual(r[1]['name'], 'Renamed')
        self.assertEqual(r[1]['icon'], ('themed', ['firefox']))
        self.assertEqual(self.call('DynamicLauncher', 'RequestInstallToken',
                                   ('dev.wolklaw.SparkStore', vd()), '(sa{sv})').unpack(), (0,))
        self.assertEqual(self.call('DynamicLauncher', 'RequestInstallToken',
                                   ('org.example.Browser', vd()), '(sa{sv})').unpack(), (1,))
        self.assertEqual(self.prop('DynamicLauncher', 'SupportedLauncherTypes'), 3)

    def test_35_lockdown(self):
        for key in ('disable-printing', 'disable-camera', 'disable-sound-output'):
            self.assertIs(self.prop('Lockdown', key), False)
        self.client.call_sync(NAME, PATH, 'org.freedesktop.DBus.Properties', 'Set',
                              GLib.Variant('(ssv)', (IMPL + 'Lockdown', 'disable-camera',
                                                     GLib.Variant('b', True))), None, 0, 5000, None)
        self.assertIs(self.prop('Lockdown', 'disable-camera'), True)
        self.assertIs(self.prop('Lockdown', 'disable-printing'), False)

    # Print

    def test_40_print(self):
        r = self.call('Print', 'PreparePrint',
                      ('/org/freedesktop/portal/desktop/request/t/pp', 'org.example.Doc', '', 'Report',
                       vd(), vd(), vd()), '(osssa{sv}a{sv}a{sv})').unpack()
        self.assertEqual(r[0], 0)
        token = r[1]['token']
        self.assertEqual(r[1]['settings']['printer'], 'Office')
        self.assertEqual(r[1]['settings']['n-copies'], '2')
        spec = [s for s in self.dialog_specs() if s['kind'] == 'print'][-1]
        self.assertEqual([p['name'] for p in spec['printers']], ['Office', 'Lab'])
        self.assertEqual(spec['default_printer'], 'Office')
        self.assertEqual(spec['subtitle'], 'Report')
        src = os.path.join(self.tmp, 'doc.pdf')
        with open(src, 'wb') as f:
            f.write(b'%PDF-fake')
        fd = os.open(src, os.O_RDONLY)
        fds = Gio.UnixFDList()
        idx = fds.append(fd)
        os.close(fd)
        r = self.call('Print', 'Print', ('/org/freedesktop/portal/desktop/request/t/pr', 'org.example.Doc',
                                         '', 'Report', idx, vd(token=GLib.Variant('u', token))),
                      '(osssha{sv})', fds=fds).unpack()
        self.assertEqual(r[0], 0)
        self.assertEqual(wait_for(lambda: os.path.exists(self.lp_out + '.data')
                                  and open(self.lp_out + '.data', 'rb').read()), b'%PDF-fake')
        self.assertEqual(open(self.lp_out + '.args').read().strip(), '-d Office -n 2 -t Report')
        self.assertEqual(self.prop('Print', 'version'), 3)

    def test_99_backend_still_running(self):
        self.assertIsNone(self.backend.poll())


if __name__ == '__main__':
    unittest.main()
