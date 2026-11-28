"""spark-secrets on a private session bus, driven by secret-tool, raw D-Bus and (when installed)
secretstorage and python-keyring. A throwaway HOME and runtime folder; nothing of the real
session is touched. Run: python3 -s -m unittest tests.test_secrets_service"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

import secrets_harness as harness  # noqa: E402
from sparksession import secrets_store as store  # noqa: E402

try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = None

NAME = 'org.freedesktop.secrets'
BASE = '/org/freedesktop/secrets'
DH = 'dh-ietf1024-sha256-aes128-cbc-pkcs7'
USER = __import__('pwd').getpwuid(os.getuid()).pw_name
HAVE = Gio is not None and shutil.which('dbus-daemon') and shutil.which('secret-tool')

ASK_SCRIPT = '''#!/bin/sh
# fake spark-ask: log the call, answer with the next line of $ASK_ANSWERS
echo "$*" >> "$ASK_LOG"
line=$(head -n 1 "$ASK_ANSWERS")
sed -i 1d "$ASK_ANSWERS"
[ -n "$line" ] || exit 1
printf '%s\\n' "$line"
'''


class Env:
    """One private bus, one HOME, and daemons started on it."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='ssvc-')
        self.home = os.path.join(self.tmp, 'home')
        self.run = os.path.join(self.tmp, 'run')
        os.makedirs(self.home)
        os.makedirs(self.run, mode=0o700)
        self.dir = os.path.join(self.tmp, 'data')
        self.keyfile = os.path.join(self.tmp, 'keyfile')
        self.ask = os.path.join(self.tmp, 'ask')
        self.ask_log = os.path.join(self.tmp, 'ask.log')
        self.answers = os.path.join(self.tmp, 'answers')
        with open(self.ask, 'w') as handle:
            handle.write(ASK_SCRIPT)
        os.chmod(self.ask, 0o755)
        open(self.ask_log, 'w').close()
        self.set_answers([])
        self.bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                    stdout=subprocess.PIPE, text=True)
        self.address = self.bus.stdout.readline().strip()
        self.daemon = None
        self.conn = None

    def env(self):
        e = {k: v for k, v in os.environ.items() if k not in ('WAYLAND_DISPLAY', 'DISPLAY')}
        e.update(HOME=self.home, XDG_RUNTIME_DIR=self.run, DBUS_SESSION_BUS_ADDRESS=self.address,
                 SPARK_SECRETS_DIR=self.dir, SPARK_SECRETS_KEYFILE=self.keyfile,
                 SPARK_SECRETS_ASK=self.ask, ASK_LOG=self.ask_log, ASK_ANSWERS=self.answers,
                 PYTHONPATH=os.path.join(HERE, '..'), LANG='C.UTF-8')
        return e

    def set_answers(self, lines):
        with open(self.answers, 'w') as handle:
            handle.write(''.join(l + '\n' for l in lines))

    def ask_calls(self):
        with open(self.ask_log) as handle:
            return [l for l in handle.read().splitlines() if l]

    def put_keyfile(self, password):
        key = store.wrapping_key(password.encode(), USER)
        with open(self.keyfile, 'w') as handle:
            handle.write(key.hex() + '\n')

    def start(self):
        self.stop()
        self.daemon = subprocess.Popen([sys.executable, '-s', '-m', 'sparksession.secrets_service'],
                                       env=self.env(), stderr=subprocess.PIPE, text=True)
        self.conn = Gio.DBusConnection.new_for_address_sync(
            self.address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
            Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        for _ in range(100):
            owned = self.conn.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                                        'NameHasOwner', GLib.Variant('(s)', (NAME,)), None,
                                        Gio.DBusCallFlags.NONE, -1, None).unpack()[0]
            portal = self.conn.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                                         'NameHasOwner', GLib.Variant('(s)', ('org.freedesktop.impl.portal.desktop.sparksecrets',)),
                                         None, Gio.DBusCallFlags.NONE, -1, None).unpack()[0]
            if owned and portal:
                return
            if self.daemon.poll() is not None:
                raise RuntimeError('spark-secrets exited: ' + self.daemon.stderr.read())
            time.sleep(0.1)
        raise RuntimeError('spark-secrets did not take its bus name')

    def stop(self):
        if self.daemon is not None and self.daemon.poll() is None:
            self.daemon.terminate()
            self.daemon.wait(10)
        self.daemon = None
        if self.conn is not None:
            self.conn.close_sync(None)
            self.conn = None

    def close(self):
        self.stop()
        self.bus.terminate()
        self.bus.wait(10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tool(self, *args, stdin=None):
        return subprocess.run(['secret-tool', *args], env=self.env(), input=stdin, capture_output=True,
                              timeout=60)

    def call(self, path, iface, method, params=None, sig=None, dest=NAME):
        reply = self.conn.call_sync(dest, path, iface, method,
                                    GLib.Variant(sig, params) if sig else None, None,
                                    Gio.DBusCallFlags.NONE, 30000, None)
        return reply.unpack()

    def prop(self, path, iface, name):
        return self.call(path, 'org.freedesktop.DBus.Properties', 'Get', (iface, name), '(ss)')[0]

    def set_prop(self, path, iface, name, variant):
        self.call(path, 'org.freedesktop.DBus.Properties', 'Set', (iface, name, variant), '(ssv)')


@unittest.skipUnless(HAVE, 'needs python3-gobject, dbus-daemon and secret-tool')
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.addCleanup(self.e.close)

    # --- libsecret (secret-tool) with the keyfile from sign-in ---
    def test_secret_tool_round_trip_with_the_signin_key(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        r = e.tool('store', '--label=Mail', 'service', 'mail', 'user', 'me', stdin=b'p\xc3\xa4ss')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(e.tool('lookup', 'service', 'mail', 'user', 'me').stdout, 'päss'.encode())
        self.assertIn(b'label = Mail', e.tool('search', 'service', 'mail').stdout)
        self.assertEqual(e.tool('lookup', 'service', 'nothing').stdout, b'')
        # same attributes again replaces
        e.tool('store', '--label=Mail', 'service', 'mail', 'user', 'me', stdin=b'new')
        self.assertEqual(e.tool('lookup', 'service', 'mail', 'user', 'me').stdout, b'new')
        self.assertEqual(e.tool('clear', 'service', 'mail', 'user', 'me').returncode, 0)
        self.assertEqual(e.tool('lookup', 'service', 'mail', 'user', 'me').stdout, b'')
        self.assertEqual(e.ask_calls(), [])
        # the files are private
        self.assertEqual(stat.S_IMODE(os.stat(e.dir).st_mode), 0o700)

    def test_data_survives_a_restart(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        e.tool('store', '--label=Keep', 'k', 'v', stdin=b'kept')
        e.start()
        self.assertEqual(e.tool('lookup', 'k', 'v').stdout, b'kept')

    def test_only_one_daemon_works_on_a_store(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        second = subprocess.run([sys.executable, '-s', '-m', 'sparksession.secrets_service'],
                                env=e.env(), capture_output=True, timeout=30)
        self.assertEqual(second.returncode, 1)

    # --- no key from sign-in: the password window ---
    def test_without_the_signin_key_it_asks_once(self):
        e = self.e
        e.set_answers(['first-pw'])
        e.start()
        r = e.tool('store', '--label=A', 'k', 'v', stdin=b'1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(e.ask_calls()), 1)
        self.assertIn('--password', e.ask_calls()[0])
        e.tool('store', '--label=B', 'k', 'w', stdin=b'2')
        self.assertEqual(len(e.ask_calls()), 1)
        # new start: locked until asked; a wrong password then the right one
        e.start()
        e.set_answers(['wrong', 'first-pw'])
        self.assertEqual(e.tool('lookup', 'k', 'v').stdout, b'1')
        self.assertEqual(len(e.ask_calls()), 3)

    def test_cancelled_window_leaves_it_locked(self):
        e = self.e
        e.set_answers(['first-pw'])
        e.start()
        e.tool('store', '--label=A', 'k', 'v', stdin=b'1')
        e.start()
        e.set_answers([''])
        r = e.tool('lookup', 'k', 'v')
        self.assertEqual(r.stdout, b'')
        coll = e.prop(BASE + '/collection/login', 'org.freedesktop.Secret.Collection', 'Locked')
        self.assertTrue(coll)

    def test_changed_password_rewraps_with_the_signin_key(self):
        e = self.e
        e.put_keyfile('old')
        e.start()
        e.tool('store', '--label=A', 'k', 'v', stdin=b'1')
        e.stop()
        e.put_keyfile('new')        # sign-in with the new password (passwd was used)
        e.set_answers(['old'])
        e.start()
        self.assertEqual(e.tool('lookup', 'k', 'v').stdout, b'1')
        self.assertEqual(len(e.ask_calls()), 1)
        e.start()
        self.assertEqual(e.tool('lookup', 'k', 'v').stdout, b'1')
        self.assertEqual(len(e.ask_calls()), 1)     # no second question

    # --- the Secret Service API, raw ---
    def open_dh(self):
        e = self.e
        private = int.from_bytes(os.urandom(64), 'big') | 2
        public = store.int_to_bytes(pow(2, private, store.DH_PRIME))
        out, path = e.call(BASE, 'org.freedesktop.Secret.Service', 'OpenSession',
                           (DH, GLib.Variant('ay', public)), '(sv)')
        return path, store.dh_session_key(private, bytes(out))

    def enc(self, path, key, secret, ctype='text/plain'):
        iv, blob = store.aes_cbc_encrypt(key, secret)
        return (path, iv, blob, ctype)

    def test_dh_session_create_get_lock_unlock(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        spath, key = self.open_dh()
        ifc = 'org.freedesktop.Secret.Collection'
        props = {'org.freedesktop.Secret.Item.Label': GLib.Variant('s', 'Site'),
                 'org.freedesktop.Secret.Item.Attributes': GLib.Variant('a{ss}', {'host': 'h', 'user': 'u'})}
        item, prompt = e.call(BASE + '/aliases/default', ifc, 'CreateItem',
                              (props, self.enc(spath, key, b'sekrit'), False),
                              '(a{sv}(oayays)b)')
        self.assertEqual(prompt, '/')
        self.assertTrue(item.startswith(BASE + '/collection/login/'))
        got = e.call(item, 'org.freedesktop.Secret.Item', 'GetSecret', (spath,), '(o)')[0]
        self.assertEqual(store.aes_cbc_decrypt(key, bytes(got[1]), bytes(got[2])), b'sekrit')
        self.assertEqual(e.prop(item, 'org.freedesktop.Secret.Item', 'Label'), 'Site')
        self.assertEqual(e.prop(item, 'org.freedesktop.Secret.Item', 'Attributes'), {'host': 'h', 'user': 'u'})
        self.assertFalse(e.prop(item, 'org.freedesktop.Secret.Item', 'Locked'))
        self.assertGreater(e.prop(item, 'org.freedesktop.Secret.Item', 'Created'), 1_600_000_000)
        # settable properties
        e.set_prop(item, 'org.freedesktop.Secret.Item', 'Label', GLib.Variant('s', 'Renamed'))
        e.set_prop(item, 'org.freedesktop.Secret.Item', 'Attributes', GLib.Variant('a{ss}', {'host': 'h2'}))
        self.assertEqual(e.prop(item, 'org.freedesktop.Secret.Item', 'Label'), 'Renamed')
        found = e.call(BASE, 'org.freedesktop.Secret.Service', 'SearchItems', ({'host': 'h2'},), '(a{ss})')
        self.assertEqual(found, ([item], []))
        # SetSecret
        e.call(item, 'org.freedesktop.Secret.Item', 'SetSecret', (self.enc(spath, key, b'other'),), '((oayays))')
        gs = e.call(BASE, 'org.freedesktop.Secret.Service', 'GetSecrets', ([item], spath), '(aoo)')[0]
        self.assertEqual(store.aes_cbc_decrypt(key, bytes(gs[item][1]), bytes(gs[item][2])), b'other')
        # Lock: the item is found, but locked, and has no secret
        e.call(BASE, 'org.freedesktop.Secret.Service', 'Lock', ([BASE + '/collection/login'],), '(ao)')
        self.assertTrue(e.prop(BASE + '/collection/login', ifc, 'Locked'))
        found = e.call(BASE, 'org.freedesktop.Secret.Service', 'SearchItems', ({'host': 'h2'},), '(a{ss})')
        self.assertEqual(found, ([], [item]))
        self.assertEqual(e.call(BASE, 'org.freedesktop.Secret.Service', 'GetSecrets', ([item], spath), '(aoo)')[0], {})
        # Unlock: the sign-in key opens it with no prompt
        unlocked, prompt = e.call(BASE, 'org.freedesktop.Secret.Service', 'Unlock',
                                  ([BASE + '/collection/login'],), '(ao)')
        self.assertEqual((unlocked, prompt), ([BASE + '/collection/login'], '/'))
        self.assertFalse(e.prop(BASE + '/collection/login', ifc, 'Locked'))
        # Delete
        e.call(item, 'org.freedesktop.Secret.Item', 'Delete')
        self.assertEqual(e.call(BASE + '/collection/login', ifc, 'SearchItems', ({'host': 'h2'},), '(a{ss})'), ([],))
        e.call(spath, 'org.freedesktop.Secret.Session', 'Close')
        with self.assertRaises(GLib.Error):
            e.call(item, 'org.freedesktop.Secret.Item', 'GetSecret', (spath,), '(o)')

    def test_plain_session_and_create_item_replace(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        out, spath = e.call(BASE, 'org.freedesktop.Secret.Service', 'OpenSession', ('plain', GLib.Variant('s', '')), '(sv)')
        props = {'org.freedesktop.Secret.Item.Label': GLib.Variant('s', 'L'),
                 'org.freedesktop.Secret.Item.Attributes': GLib.Variant('a{ss}', {'a': 'b'})}
        first = e.call(BASE + '/collection/login', 'org.freedesktop.Secret.Collection', 'CreateItem',
                       (props, (spath, b'', b'one', 'text/plain'), False), '(a{sv}(oayays)b)')[0]
        again = e.call(BASE + '/collection/login', 'org.freedesktop.Secret.Collection', 'CreateItem',
                       (props, (spath, b'', b'two', 'text/plain'), True), '(a{sv}(oayays)b)')[0]
        self.assertEqual(first, again)
        got = e.call(first, 'org.freedesktop.Secret.Item', 'GetSecret', (spath,), '(o)')[0]
        self.assertEqual(bytes(got[2]), b'two')
        self.assertEqual(len(e.prop(BASE + '/collection/login', 'org.freedesktop.Secret.Collection', 'Items')), 1)

    def test_bad_requests_are_refused(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        with self.assertRaises(GLib.Error):
            e.call(BASE, 'org.freedesktop.Secret.Service', 'OpenSession', ('rot13', GLib.Variant('s', '')), '(sv)')
        with self.assertRaises(GLib.Error):
            e.call(BASE, 'org.freedesktop.Secret.Service', 'OpenSession',
                   (DH, GLib.Variant('ay', b'\x01')), '(sv)')
        with self.assertRaises(GLib.Error):
            e.call(BASE + '/collection/nope', 'org.freedesktop.Secret.Collection', 'SearchItems', ({},), '(a{ss})')

    def test_aliases_and_collections(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        svc = 'org.freedesktop.Secret.Service'
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('default',), '(s)')[0], BASE + '/collection/login')
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('nope',), '(s)')[0], '/')
        self.assertIn(BASE + '/collection/login', e.prop(BASE, svc, 'Collections'))
        self.assertIn(BASE + '/collection/session', e.prop(BASE, svc, 'Collections'))
        made, prompt = e.call(BASE, svc, 'CreateCollection',
                              ({'org.freedesktop.Secret.Collection.Label': GLib.Variant('s', 'Work')}, 'work'),
                              '(a{sv}s)')
        self.assertEqual(prompt, '/')
        self.assertEqual(e.prop(made, 'org.freedesktop.Secret.Collection', 'Label'), 'Work')
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('work',), '(s)')[0], made)
        e.call(BASE, svc, 'SetAlias', ('other', made), '(so)')
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('other',), '(s)')[0], made)
        e.start()           # still there after a restart
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('work',), '(s)')[0], made)
        e.call(made, 'org.freedesktop.Secret.Collection', 'Delete')
        self.assertEqual(e.call(BASE, svc, 'ReadAlias', ('work',), '(s)')[0], '/')

    def test_session_collection_is_never_saved(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        r = e.tool('store', '--label=T', '--collection=/org/freedesktop/secrets/collection/session', 'k', 'tmp', stdin=b'x')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(e.tool('lookup', 'k', 'tmp').stdout, b'x')
        e.start()
        self.assertEqual(e.tool('lookup', 'k', 'tmp').stdout, b'')

    def test_signals(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        seen = []
        e.conn.signal_subscribe(NAME, 'org.freedesktop.Secret.Collection', None, None, None,
                                Gio.DBusSignalFlags.NONE, lambda *a: seen.append(a[4]))
        e.tool('store', '--label=S', 'k', 'sig', stdin=b'1')
        ctx = GLib.MainContext.default()
        end = time.time() + 3
        while time.time() < end and 'ItemCreated' not in seen:
            ctx.iteration(False)
            time.sleep(0.02)
        self.assertIn('ItemCreated', seen)

    # --- the Secret portal ---
    def retrieve(self, app_id):
        e = self.e
        r, w = os.pipe()
        fds = Gio.UnixFDList.new()
        idx = fds.append(w)
        os.close(w)
        reply = e.conn.call_with_unix_fd_list_sync(
            'org.freedesktop.impl.portal.desktop.sparksecrets', '/org/freedesktop/portal/desktop',
            'org.freedesktop.impl.portal.Secret', 'RetrieveSecret',
            GLib.Variant('(osha{sv})', ('/org/freedesktop/portal/desktop/request/x/y', app_id, idx, {})),
            None, Gio.DBusCallFlags.NONE, 30000, fds, None)[0]
        del fds                 # the list holds a copy of the write end; EOF needs it gone
        data = b''
        while True:
            chunk = os.read(r, 4096)
            if not chunk:
                break
            data += chunk
        os.close(r)
        return reply.unpack(), data

    def test_portal_gives_each_app_its_own_stable_secret(self):
        e = self.e
        e.put_keyfile('pw')
        e.start()
        (code, _), a1 = self.retrieve('org.example.A')
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(a1), 32)
        self.assertEqual(self.retrieve('org.example.A')[1], a1)
        self.assertNotEqual(self.retrieve('org.example.B')[1], a1)
        e.start()
        self.assertEqual(self.retrieve('org.example.A')[1], a1)

    # --- other client libraries ---
    def test_secretstorage(self):
        try:
            import secretstorage
        except ImportError:
            self.skipTest('secretstorage is not installed')
        e = self.e
        e.put_keyfile('pw')
        e.start()
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = e.address
        try:
            conn = secretstorage.dbus_init()
            coll = secretstorage.get_default_collection(conn)
            self.assertFalse(coll.is_locked())
            coll.create_item('ss item', {'who': 'ss'}, b'ss-secret', replace=True)
            items = list(coll.search_items({'who': 'ss'}))
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].get_secret(), b'ss-secret')
            self.assertEqual(items[0].get_label(), 'ss item')
            items[0].set_secret(b'changed')
            self.assertEqual(e.tool('lookup', 'who', 'ss').stdout, b'changed')
            items[0].delete()
            self.assertEqual(list(coll.search_items({'who': 'ss'})), [])
            conn.close()
        finally:
            os.environ.pop('DBUS_SESSION_BUS_ADDRESS', None)

    def test_python_keyring(self):
        try:
            import keyring  # noqa: F401
        except ImportError:
            self.skipTest('keyring is not installed')
        e = self.e
        e.put_keyfile('pw')
        e.start()
        code = ('import keyring, keyring.backends.SecretService as s\n'
                'keyring.set_keyring(s.Keyring())\n'
                'keyring.set_password("svc", "me", "kr-secret")\n'
                'assert keyring.get_password("svc", "me") == "kr-secret"\n'
                'keyring.delete_password("svc", "me")\n'
                'assert keyring.get_password("svc", "me") is None\n'
                'print("ok")\n')
        r = subprocess.run([sys.executable, '-c', code], env=e.env(), capture_output=True, timeout=60)
        self.assertEqual(r.stdout.strip(), b'ok', r.stderr)

    # --- importing a GNOME Keyring made by the real daemon, then using it ---
    @unittest.skipUnless(harness.available(), 'gnome-keyring-daemon is missing')
    def test_import_then_serve(self):
        e = self.e
        gk_home = os.path.join(e.tmp, 'gkhome')
        os.makedirs(gk_home)
        path = harness.make_keyring(gk_home)
        cmd = [sys.executable, '-s', '-m', 'sparksession.secrets_service',
               '--import-gnome-keyring', path, '--password-stdin']
        r = subprocess.run(cmd, input=b'hunter2', env=e.env(), capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b'2 added', r.stdout)
        # the import wrapped the master key with the keyring password, the same one as sign-in
        e.put_keyfile('hunter2')
        e.start()
        for label, attrs, secret in harness.ITEMS:
            args = [x for kv in attrs.items() for x in kv]
            self.assertEqual(e.tool('lookup', *args).stdout, secret.encode())
        # a running daemon holds the store: the import says so and changes nothing
        r = subprocess.run(cmd, input=b'hunter2', env=e.env(), capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b'stop spark-secrets', r.stderr)
        e.stop()
        r = subprocess.run(cmd, input=b'hunter2', env=e.env(), capture_output=True, timeout=60)
        self.assertIn(b'0 added, 2 already there', r.stdout)


if __name__ == '__main__':
    unittest.main()
