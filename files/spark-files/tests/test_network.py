"""Network places and Google Drive: addresses, bookmarks, the keyring, host keys, connecting
with a fake kio-fuse, timeouts, and the sidebar rows. No server and no account is needed;
the real thing (kio-fuse, a KIO worker, sshd) is in sftp_check.sh.

    python -m unittest discover -s files/spark-files/tests -v
"""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest

from test_spark_files import DISPLAY, TempDir   # also points the XDG folders at temp ones

from sparkfiles import core, network  # noqa: E402
from sparkfiles.network import NetworkError, Server, parse_address  # noqa: E402
from sparkfiles.places import free_space, network_places  # noqa: E402
from sparkfiles.text import t  # noqa: E402


class Addresses(unittest.TestCase):
    def test_sftp_with_everything(self):
        s, pw = parse_address('sftp://me@host.lan:2222/home/me/My Files')
        self.assertEqual((s.scheme, s.user, s.host, s.port, s.path),
                         ('sftp', 'me', 'host.lan', 2222, '/home/me/My Files'))
        self.assertIsNone(pw)
        self.assertEqual(s.display(), 'sftp://me@host.lan:2222/home/me/My Files')
        self.assertEqual(s.url(), 'sftp://me@host.lan:2222/home/me/My%20Files')
        self.assertEqual(s.key(), 'sftp://me@host.lan:2222')

    def test_defaults(self):
        s, _ = parse_address('smb://nas/photos')
        self.assertEqual((s.scheme, s.user, s.host, s.path), ('smb', '', 'nas', '/photos'))
        s, _ = parse_address('sftp://host')
        self.assertEqual(s.path, '/')
        s, _ = parse_address('sftp://host:22/x')
        self.assertEqual(s.display(), 'sftp://host/x')          # the default port isn't shown

    def test_user_field_is_the_fallback(self):
        self.assertEqual(parse_address('sftp://host', user='bob')[0].user, 'bob')
        self.assertEqual(parse_address('sftp://al@host', user='bob')[0].user, 'al')

    def test_ssh_means_sftp(self):
        self.assertEqual(parse_address('ssh://host/x')[0].scheme, 'sftp')

    def test_password_in_the_address_is_split_off(self):
        s, pw = parse_address('sftp://me:p%40ss%3Aw%2Frd@host/x')
        self.assertEqual(pw, 'p@ss:w/rd')
        self.assertNotIn('p', s.display().split('@')[0].replace('sftp://me', ''))
        self.assertNotIn('ss', s.display())
        self.assertEqual(s.url('p@ss:w/rd'), 'sftp://me:p%40ss%3Aw%2Frd@host/x')

    def test_ipv6(self):
        s, _ = parse_address('sftp://me@[fe80::1]:2200/')
        self.assertEqual(s.host, 'fe80::1')
        self.assertEqual(s.display(), 'sftp://me@[fe80::1]:2200/')

    def test_bad_addresses(self):
        for text, detail in (('host', 'scheme'), ('http://host/', 'scheme'),
                             ('ftp://host', 'scheme'), ('sftp://', 'host'),
                             ('sftp:///x', 'host'), ('', 'scheme'), ('sftp://h:port/', 'host')):
            with self.assertRaises(NetworkError, msg=text) as cm:
                parse_address(text)
            self.assertEqual((cm.exception.code, cm.exception.detail), ('address', detail),
                             text)


class Bookmarks(TempDir):
    def test_add_replaces_and_never_keeps_a_password(self):
        settings = {'servers': []}
        s, _ = parse_address('sftp://me@host/x')
        network.add_bookmark(settings, 'Work', s)
        network.add_bookmark(settings, 'Work box', s)           # same server: renamed
        self.assertEqual(settings['servers'], [{'name': 'Work box',
                                                'url': 'sftp://me@host/x'}])
        network.remove_bookmark(settings, 'sftp://me@host/x')
        self.assertEqual(settings['servers'], [])

    def test_a_stored_password_is_dropped_on_load(self):
        settings = {'servers': [{'name': 'x', 'url': 'sftp://me:secret@host/'},
                                {'name': 'bad', 'url': 'http://nope'}, 'junk', {'url': 5}]}
        out = network.bookmarks(settings)
        self.assertEqual(out, [{'name': 'x', 'url': 'sftp://me@host/'}])
        self.assertNotIn('secret', json.dumps(out))

    def test_settings_file_round_trip(self):
        s = core.load_settings()
        s['servers'] = [{'name': 'a', 'url': 'smb://nas/share'}]
        s['servers'].append({'name': 'b', 'url': 'sftp://u:pw@h/'})
        core.save_settings(s)
        again = core.load_settings()
        self.assertEqual([b['url'] for b in again['servers']],
                         ['smb://nas/share', 'sftp://u@h/'])
        with open(os.path.join(core.config_dir(), 'settings.json'), encoding='utf-8') as f:
            self.assertNotIn('pw', f.read().replace('"servers"', ''))
        s['servers'] = []
        core.save_settings(s)


class FakeRun:
    """Stands in for subprocess.run."""

    def __init__(self, code=0, out=''):
        self.calls, self.code, self.out = [], code, out

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, self.code, self.out, '')


class KeyringTests(unittest.TestCase):
    def test_password_goes_on_stdin_not_the_command_line(self):
        run = FakeRun()
        k = network.Keyring(run=run, tool='/usr/bin/secret-tool')
        self.assertTrue(k.store('sftp://me@host', 's3cret', label='L'))
        argv, kw = run.calls[0]
        self.assertEqual(kw['input'], 's3cret')
        self.assertNotIn('s3cret', ' '.join(argv))
        self.assertEqual(argv[:3], ['/usr/bin/secret-tool', 'store', '--label=L'])
        self.assertIn('sftp://me@host', argv)

    def test_lookup_and_clear(self):
        k = network.Keyring(run=FakeRun(out='pw'), tool='/x/secret-tool')
        self.assertEqual(k.lookup('sftp://me@host'), 'pw')
        self.assertTrue(k.clear('sftp://me@host'))
        self.assertIsNone(network.Keyring(run=FakeRun(code=1), tool='/x').lookup('k'))
        self.assertIsNone(network.Keyring(run=FakeRun(code=0, out=''), tool='/x').lookup('k'))

    def test_without_the_tool_nothing_is_saved(self):
        k = network.Keyring(run=FakeRun(), tool='')
        self.assertFalse(k.available)
        self.assertFalse(k.store('k', 'pw'))
        self.assertIsNone(k.lookup('k'))
        self.assertFalse(k.clear('k'))

    def test_a_tool_that_fails_or_hangs_is_not_fatal(self):
        def boom(*a, **kw):
            raise subprocess.TimeoutExpired('secret-tool', 30)
        k = network.Keyring(run=boom, tool='/x')
        self.assertFalse(k.store('k', 'pw'))
        self.assertIsNone(k.lookup('k'))

    def test_empty_password_is_not_stored(self):
        run = FakeRun()
        self.assertFalse(network.Keyring(run=run, tool='/x').store('k', ''))
        self.assertEqual(run.calls, [])


class Mounts(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get('XDG_RUNTIME_DIR')
        os.environ['XDG_RUNTIME_DIR'] = '/run/user/1000'
        self.addCleanup(lambda: os.environ.__setitem__('XDG_RUNTIME_DIR', self.old)
                        if self.old is not None else os.environ.pop('XDG_RUNTIME_DIR'))

    def test_remote_paths(self):
        p = '/run/user/1000/kio-fuse-AbC123/sftp/me@host:2222/home/me/x'
        self.assertTrue(network.is_remote(p))
        self.assertEqual(network.split_remote(p),
                         ('/run/user/1000/kio-fuse-AbC123/sftp/me@host:2222',
                          'sftp://me@host:2222'))
        self.assertEqual(network.split_remote('/run/user/1000/kio-fuse-AbC123/smb/nas/share'),
                         ('/run/user/1000/kio-fuse-AbC123/smb/nas', 'smb://nas'))
        self.assertEqual(network.split_remote(
            '/run/user/1000/kio-fuse-AbC123/gdrive/me@gmail.com/x'),
            ('/run/user/1000/kio-fuse-AbC123/gdrive', 'Google Drive'))

    def test_local_paths_are_not(self):
        for p in ('/home/me', '/run/user/1000/bus', '/var/mnt/c', '', '/run/user/1000/kio-fusee'):
            self.assertFalse(network.is_remote(p), p)
            self.assertIsNone(network.split_remote(p), p)

    def test_free_space_never_asks_a_server(self):
        self.assertIsNone(free_space('/run/user/1000/kio-fuse-AbC123/sftp/h/x'))


class FakeBackend:
    def __init__(self, path=None, delay=0.0, error=None):
        self.path, self.delay, self.error, self.urls = path, delay, error, []

    def mount(self, url, timeout=30):
        self.urls.append(url)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.path


class Connecting(TempDir):
    def setUp(self):
        super().setUp()
        os.mkdir(self.path('share'))
        self.write('share/a.txt')

    def test_connects_and_checks_the_listing(self):
        be = FakeBackend(self.path('share'))
        s, _ = parse_address('sftp://me@host/x')
        self.assertEqual(network.connect_blocking(s, 'p w', backend=be), self.path('share'))
        self.assertEqual(be.urls, ['sftp://me:p%20w@host/x'])

    def test_a_server_that_does_not_answer_times_out_without_waiting_for_it(self):
        be = FakeBackend(self.path('share'), delay=3)
        s, _ = parse_address('sftp://host/')
        began = time.monotonic()
        with self.assertRaises(NetworkError) as cm:
            network.connect_blocking(s, None, backend=be, timeout=0.3)
        self.assertEqual(cm.exception.code, 'timeout')
        self.assertLess(time.monotonic() - began, 1.5)

    def test_a_listing_that_hangs_times_out_too(self):
        be = FakeBackend(self.path('missing-but-slow'))
        s, _ = parse_address('smb://nas/')
        real = os.listdir
        gate = threading.Event()
        self.addCleanup(gate.set)
        os.listdir = lambda p: (gate.wait(3), real(self.path('share')))[1]
        self.addCleanup(setattr, os, 'listdir', real)
        with self.assertRaises(NetworkError) as cm:
            network.connect_blocking(s, None, backend=be, timeout=0.3)
        self.assertEqual(cm.exception.code, 'timeout')

    def test_errors_keep_their_code_and_lose_the_password(self):
        s, _ = parse_address('smb://me@nas/share')
        be = FakeBackend(error=NetworkError('failed', 'Could not authenticate with hunter2'))
        with self.assertRaises(NetworkError) as cm:
            network.connect_blocking(s, 'hunter2', backend=be)
        self.assertEqual(cm.exception.code, 'failed')
        be = FakeBackend(error=RuntimeError('login me:hunter2@nas refused'))
        with self.assertRaises(NetworkError) as cm:
            network.connect_blocking(s, 'hunter2', backend=be)
        self.assertNotIn('hunter2', str(cm.exception))

    def test_mount_that_is_not_a_folder_fails(self):
        s, _ = parse_address('smb://nas/')
        with self.assertRaises(NetworkError):
            network.connect_blocking(s, None, backend=FakeBackend(self.path('nope')))

    def test_start_reports_back_through_post_and_can_be_cancelled(self):
        got, posted = [], []
        done = threading.Event()

        def post(fn):
            posted.append(fn)
            fn()
            done.set()
        network.start(lambda: 5, post, lambda r, e: got.append((r, e)))
        self.assertTrue(done.wait(2))
        self.assertEqual(got, [(5, None)])
        got.clear()
        done.clear()

        def failing():
            raise NetworkError('timeout')
        network.start(failing, post, lambda r, e: got.append((r, e.code)))
        self.assertTrue(done.wait(2))
        self.assertEqual(got, [(None, 'timeout')])
        got.clear()
        done.clear()
        release = threading.Event()
        cancel = network.start(lambda: release.wait(2), post,
                               lambda r, e: got.append((r, e)))
        cancel()
        release.set()
        time.sleep(0.3)
        self.assertEqual(got, [])


class HostKeys(TempDir):
    @unittest.skipUnless(shutil.which('ssh-keygen'), 'needs ssh-keygen')
    def test_known_after_accept(self):
        kh = self.path('ssh/known_hosts')
        s, _ = parse_address('sftp://host.example:2222/')
        self.assertFalse(network.host_key_known(s, kh))          # no file yet
        key = subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f',
                              self.path('k')], capture_output=True)
        self.assertEqual(key.returncode, 0)
        with open(self.path('k.pub')) as f:
            type_, blob = f.read().split()[:2]
        network.accept_host_key(f'[host.example]:2222 {type_} {blob}', kh)
        self.assertTrue(network.host_key_known(s, kh))
        other, _ = parse_address('sftp://other.example:2222/')
        self.assertFalse(network.host_key_known(other, kh))
        self.assertEqual(os.stat(kh).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(os.path.dirname(kh)).st_mode & 0o777, 0o700)

    @unittest.skipUnless(shutil.which('ssh-keygen') and shutil.which('ssh-keyscan'),
                         'needs ssh-keygen and ssh-keyscan')
    def test_scan_reads_the_fingerprint(self):
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', self.path('k')],
                       check=True, capture_output=True)
        with open(self.path('k.pub')) as f:
            type_, blob = f.read().split()[:2]
        run_real = subprocess.run

        def run(argv, **kw):
            if 'ssh-keyscan' in argv[0]:
                return subprocess.CompletedProcess(argv, 0, f'[h]:2200 {type_} {blob}\n', '')
            return run_real(argv, **kw)
        s, _ = parse_address('sftp://h:2200/')
        line, shown = network.scan_host_key(s, run=run)
        self.assertEqual(line, f'[h]:2200 {type_} {blob}')
        self.assertTrue(shown.startswith('SHA256:'), shown)
        self.assertIn('ED25519', shown)

    @unittest.skipUnless(shutil.which('ssh-keygen') and shutil.which('ssh-keyscan'),
                         'needs ssh-keygen and ssh-keyscan')
    def test_scan_failures(self):
        s, _ = parse_address('sftp://h/')
        empty = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, '', 'no route\n')  # noqa

        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 20)
        with self.assertRaises(NetworkError) as cm:
            network.scan_host_key(s, run=empty)
        self.assertEqual(cm.exception.code, 'failed')
        with self.assertRaises(NetworkError) as cm:
            network.scan_host_key(s, run=hang)
        self.assertEqual(cm.exception.code, 'timeout')


class GoogleDrive(TempDir):
    def db(self, rows):
        path = self.path('accounts.db')
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE Accounts (id INTEGER PRIMARY KEY AUTOINCREMENT,'
                     'name TEXT,provider TEXT,enabled INTEGER)')
        conn.executemany('INSERT INTO Accounts (name, provider, enabled) VALUES (?,?,?)', rows)
        conn.commit()
        conn.close()
        return path

    def test_counts_only_enabled_google_accounts(self):
        db = self.db([('a', 'google', 1), ('b', 'google', 0), ('c', 'nextcloud', 1)])
        self.assertEqual(network.google_accounts(db), 1)
        self.assertEqual(network.google_accounts(self.path('missing.db')), 0)
        with open(self.path('bad.db'), 'wb') as f:
            f.write(b'not a database')
        self.assertEqual(network.google_accounts(self.path('bad.db')), 0)

    def test_state(self):
        self.assertEqual(network.gdrive_state(worker=False, db=self.db([('a', 'google', 1)])),
                         'none')
        self.assertEqual(network.gdrive_state(worker=True, db=self.path('missing.db')),
                         'no-account')
        os.remove(self.path('accounts.db')) if os.path.exists(self.path('accounts.db')) else 0
        self.assertEqual(network.gdrive_state(worker=True, db=self.db([('a', 'google', 1)])),
                         'ready')

    def test_the_database_is_only_read(self):
        db = self.db([('a', 'google', 1)])
        before = os.stat(db).st_mtime_ns
        network.google_accounts(db)
        self.assertEqual(os.stat(db).st_mtime_ns, before)

    def test_sidebar_rows(self):
        servers = [{'name': 'Work', 'url': 'sftp://me@host/'}]
        keys = lambda state: [p.key for p in network_places(t, servers, state)]    # noqa: E731
        self.assertEqual(keys('none'), ['net-server-sftp://me@host/', 'net-connect'])
        self.assertEqual(keys('no-account')[-1], 'net-gdrive-add')
        self.assertEqual(keys('ready')[-1], 'net-gdrive')

    def test_account_setup_command(self):
        cmd = network.account_setup_command()
        if cmd:
            self.assertIn('kcm_kaccounts', cmd)


@unittest.skipUnless(DISPLAY, 'needs a display')
class NetworkWindow(TempDir):
    """The sidebar and the connect flow, with a fake kio-fuse."""

    @classmethod
    def setUpClass(cls):
        from sparkfiles.app import App
        cls.app = App()
        cls.app.quit = lambda: None

    @classmethod
    def tearDownClass(cls):
        for w in list(cls.app.windows):
            w.destroy()
        cls.app.shutdown()

    def setUp(self):
        super().setUp()
        os.makedirs(self.path('home/sub'))
        self.write('server/doc.txt', b'remote')
        self.app.settings['servers'] = [{'name': 'Work box', 'url': 'smb://nas/share'}]
        self.app._gdrive = (time.monotonic(), 'ready')
        self.w = self.app.new_window(self.path('home'))
        self.addCleanup(lambda: self.w.winfo_exists() and self.w.close())
        self.addCleanup(lambda: self.app.settings.__setitem__('servers', []))
        self.addCleanup(lambda: setattr(self.app, '_gdrive', None))
        self.real_connect = network.connect_blocking
        self.addCleanup(setattr, network, 'connect_blocking', self.real_connect)
        self.old_ask = None

    def pump(self, seconds=0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.root.update()
            time.sleep(0.005)

    def wait_for(self, cond, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.root.update()
            if cond():
                return
            time.sleep(0.01)
        self.fail('timed out waiting')

    def place(self, key):
        return next(p for p in self.w.sidebar.places if p.key == key)

    def test_sidebar_has_the_network_group(self):
        keys = [p.key for p in self.w.sidebar.places]
        self.assertIn('net-server-smb://nas/share', keys)
        self.assertIn('net-connect', keys)
        self.assertIn('net-gdrive', keys)
        self.assertEqual(self.place('net-server-smb://nas/share').label, 'Work box')

    def test_clicking_a_saved_server_opens_it(self):
        seen = []

        def fake(server, password, backend=None, timeout=30):
            seen.append((server.display(), password))
            return self.path('server')
        network.connect_blocking = fake
        self.w.sidebar.open(self.place('net-server-smb://nas/share'))
        self.wait_for(lambda: self.w.active.path == self.path('server'))
        self.assertEqual(seen[0][0], 'smb://nas/share')
        self.wait_for(lambda: [e.name for e in self.w.active.view.entries] == ['doc.txt'])

    def test_google_drive_row_opens_the_drive(self):
        seen = []

        def fake(target, password, backend=None, timeout=30):
            seen.append(target.url())
            return self.path('server')
        network.connect_blocking = fake
        self.w.sidebar.open(self.place('net-gdrive'))
        self.wait_for(lambda: self.w.active.path == self.path('server'))
        self.assertEqual(seen, ['gdrive:///'])

    def test_unreachable_server_does_not_freeze_the_window(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(server, password, backend=None, timeout=30):
            release.wait(5)
            raise NetworkError('timeout')
        network.connect_blocking = slow
        began = time.monotonic()
        self.w.sidebar.open(self.place('net-server-smb://nas/share'))
        self.assertLess(time.monotonic() - began, 0.5)           # returned at once
        # the window keeps working: browse a folder while it "connects"
        self.w.active.go(self.path('home/sub'))
        self.wait_for(lambda: self.w.active.path == self.path('home/sub'))
        self.assertIn('Work box', self.w.active.message)         # "Connecting to Work box…"
        release.set()
        self.wait_for(lambda: self.w.active.message ==
                      t('net.err.timeout', name='Work box', s=network.CONNECT_TIMEOUT))
        self.assertEqual(self.w.active.path, self.path('home/sub'))   # we stayed put

    def test_failure_is_shown_and_nothing_navigates(self):
        def fail(server, password, backend=None, timeout=30):
            raise NetworkError('failed', 'Permission denied')
        network.connect_blocking = fail
        self.w.sidebar.open(self.place('net-server-smb://nas/share'))
        self.wait_for(lambda: 'Permission denied' in self.w.active.message)
        self.assertEqual(self.w.active.path, self.path('home'))

    def test_typing_an_address_in_the_path_bar_connects(self):
        seen = []

        def fake(server, password, backend=None, timeout=30):
            seen.append((server.display(), password))
            return self.path('server')
        network.connect_blocking = fake
        bar = self.w.active.pathbar
        bar.edit()
        bar.field.delete(0, 'end')
        bar.field.insert(0, 'smb://me:pw@nas/share')
        bar._commit()
        self.wait_for(lambda: self.w.active.path == self.path('server'))
        self.assertEqual(seen, [('smb://me@nas/share', 'pw')])
        self.assertNotIn('pw', json.dumps(self.app.settings['servers']))

    def test_bad_address_in_the_path_bar_says_so(self):
        bar = self.w.active.pathbar
        bar.edit()
        bar.field.delete(0, 'end')
        bar.field.insert(0, 'http://example.com/')
        bar._commit()
        self.assertIn('sftp://', self.w.active.message)

    def test_dialog_connect_saves_the_bookmark_without_the_password(self):
        from sparkfiles.netdialogs import ConnectDialog
        stored = []

        def fake(server, password, backend=None, timeout=30):
            return self.path('server')
        network.connect_blocking = fake
        real_store = network.Keyring.store
        network.Keyring.store = lambda self_, key, pw, label='': stored.append((key, pw)) or True
        self.addCleanup(setattr, network.Keyring, 'store', real_store)
        d = ConnectDialog(self.app, self.w)
        d.address.delete(0, 'end')
        d.address.insert(0, 'smb://nas2/docs')
        d.user.insert(0, 'me')
        d.password.insert(0, 'hunter2')
        d.remember.set(True)
        d.name.insert(0, 'Docs')
        d.connect()
        self.wait_for(lambda: self.w.active.path == self.path('server'))
        self.wait_for(lambda: not d.winfo_exists())
        self.assertEqual(stored, [('smb://me@nas2', 'hunter2')])
        self.assertIn({'name': 'Docs', 'url': 'smb://me@nas2/docs'},
                      self.app.settings['servers'])
        self.assertNotIn('hunter2', json.dumps(self.app.settings))

    def test_dialog_shows_errors_and_stays_open(self):
        from sparkfiles.netdialogs import ConnectDialog

        def fail(server, password, backend=None, timeout=30):
            raise NetworkError('timeout')
        network.connect_blocking = fail
        d = ConnectDialog(self.app, self.w)
        self.addCleanup(lambda: d.winfo_exists() and d.destroy())
        d.address.delete(0, 'end')
        d.address.insert(0, 'smb://nas3/x')
        d.connect()
        self.wait_for(lambda: d.status.cget('text') ==
                      t('net.err.timeout', name='nas3', s=network.CONNECT_TIMEOUT))
        self.assertTrue(d.winfo_exists())
        self.assertIsNone(d.cancel_connect)
        d.address.delete(0, 'end')
        d.address.insert(0, 'nonsense')
        d.connect()
        self.assertIn('sftp://', d.status.cget('text'))


if __name__ == '__main__':
    unittest.main()
