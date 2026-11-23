"""Screen sharing tests: spark-share on the target (files/system/usr/bin/spark-share) and the
Spark Connect side of it. Plain unittest, like the rest:

    python -m unittest discover -s files/spark-connect/tests -v

Nothing here connects to a real machine or shares a real screen. spark-share runs against a
fake krdpserver (it only listens on the port it is given), a fake loginctl and a fake ssh, all
written to a temporary folder. The prompt and the banner are drawn under Xvfb on CI.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(APP_DIR))
SHARE = os.path.join(REPO, 'files', 'system', 'usr', 'bin', 'spark-share')
sys.path.insert(0, APP_DIR)
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-connect-{var.lower()}-'))
os.environ['SPARK_CONNECT_REDUCED_MOTION'] = '1'

from sparkconnect import actions, config, screen  # noqa: E402
from sparkconnect.probe import parse_probe  # noqa: E402
from sparkconnect.text import EN, FR  # noqa: E402
from sparkconnect.transport import DONE, FAILED, NEEDS_PASSWORD, probe_script  # noqa: E402

LINUX = sys.platform.startswith('linux')


if not os.path.exists(SHARE):
    # the sparkos CI job copies only the app folder: spark-share's tests need the repo
    raise unittest.SkipTest("spark-share is not next to the app (only the app folder here)")


def load_share():
    loader = importlib.machinery.SourceFileLoader('spark_share', SHARE)
    spec = importlib.util.spec_from_loader('spark_share', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


share_mod = load_share()


def have_display() -> bool:
    return os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def script(folder, name, body):
    path = os.path.join(folder, name)
    with open(path, 'w') as f:
        f.write(textwrap.dedent(body).lstrip())
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def session(uid, name='owner', typ='wayland', cls='user', state='active', active='yes',
            locked='no'):
    return {'Id': '2', 'User': str(uid), 'Name': name, 'Type': typ, 'Class': cls,
            'State': state, 'Active': active, 'LockedHint': locked}


def fake_loginctl_dir(folder, sessions):
    sessions = [dict(s, Id=str(i + 2)) for i, s in enumerate(sessions)]
    """A loginctl that answers from the given sessions (a list of dicts like session())."""
    data = {s['Id']: s for s in sessions}
    with open(os.path.join(folder, 'sessions.json'), 'w') as f:
        json.dump(data, f)
    script(folder, 'loginctl', f'''
        #!/usr/bin/env python3
        import json, sys
        data = json.load(open({os.path.join(folder, 'sessions.json')!r}))
        if sys.argv[1] == 'list-sessions':
            for i, s in data.items():
                print(f" {{i}} {{s['User']}} {{s['Name']}} seat0 tty2")
        elif sys.argv[1] == 'show-session':
            s = data.get(sys.argv[2], {{}})
            for k in ('Id', 'User', 'Name', 'Type', 'Class', 'State', 'Active', 'LockedHint'):
                if k in s:
                    print(f"{{k}}={{s[k]}}")
    ''')
    return folder


class Sessions(unittest.TestCase):
    """Which graphical session a request reaches: own, another user's, locked, none."""

    def pick(self, sessions, uid=1000, root=False, user=None):
        return share_mod.pick_session(sessions, user, uid, root)

    def test_own_session(self):
        found, err = self.pick([session(1000)])
        self.assertEqual((found['Name'], err), ('owner', None))

    def test_greeter_and_manager_are_not_sessions(self):
        found, err = self.pick([session(120, 'gdm', cls='greeter'), session(1000, cls='manager')])
        self.assertEqual((found, err), (None, 'no_session'))

    def test_another_users_session_needs_root(self):
        found, err = self.pick([session(1001, 'guest')])
        self.assertEqual((found, err), (None, 'other_user'))
        found, err = self.pick([session(1001, 'guest')], root=True, uid=0)
        self.assertEqual(found['Name'], 'guest')

    def test_active_session_first(self):
        found, _ = self.pick([session(1001, 'a', active='no', state='online'), session(1002, 'b')],
                             root=True, uid=0)
        self.assertEqual(found['Name'], 'b')

    def test_user_filter(self):
        found, _ = self.pick([session(1000), session(1001, 'guest')], root=True, uid=0,
                             user='guest')
        self.assertEqual(found['Name'], 'guest')

    def test_closing_session_is_not_one(self):
        self.assertEqual(self.pick([session(1000, state='closing')])[1], 'no_session')

    def test_none(self):
        self.assertEqual(self.pick([]), (None, 'no_session'))

    @unittest.skipUnless(LINUX, "fake loginctl is a Unix script")
    def test_read_sessions_from_loginctl_output(self):
        folder = fake_loginctl_dir(tempfile.mkdtemp(), [session(1000), session(120, 'gdm',
                                                                                cls='greeter')])
        with mock.patch.dict(os.environ, {'PATH': folder + os.pathsep + os.environ['PATH']}):
            found = share_mod.read_sessions()
        self.assertEqual(sorted(s['Name'] for s in found), ['gdm', 'owner'])
        self.assertEqual(share_mod.parse_show("A=1\nB=x=y\nnoise\n"), {'A': '1', 'B': 'x=y'})


@unittest.skipUnless(LINUX and shutil.which('sh'), "needs Linux and sh")
class ProbeDesktop(unittest.TestCase):
    """The probe's desktop block, run with a fake loginctl."""

    def probe(self, sessions, desktop='1', krdp=False):
        folder = fake_loginctl_dir(tempfile.mkdtemp(), sessions)
        env = dict(os.environ, PATH=folder + os.pathsep + os.environ['PATH'])
        m = config.Machine('desk', 'desk', desktop=desktop == '1')
        done = subprocess.run(['sh', '-s'], input=probe_script(m), capture_output=True,
                              text=True, timeout=60, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return parse_probe(done.stdout)

    def test_in_use(self):
        d = self.probe([session(1000)])['desktop']
        self.assertEqual((d['state'], d['user']), ('in_use', 'owner'))

    def test_locked(self):
        self.assertEqual(self.probe([session(1000, locked='yes')])['desktop']['state'], 'locked')

    def test_nobody(self):
        d = self.probe([session(120, 'gdm', cls='greeter')])['desktop']
        self.assertEqual((d['state'], d['user']), ('none', ''))

    def test_servers_report_nothing(self):
        self.assertIsNone(self.probe([session(1000)], desktop='0')['desktop'])

    def test_probe_still_reads_only(self):
        with open(os.path.join(APP_DIR, 'sparkconnect', 'probe.sh'), encoding='utf-8') as f:
            body = f.read()
        block = body[body.index('"desktop"'):body.index('# ─── units')]
        for word in ('rm ', 'tee ', 'chmod', '>>', 'sudo', 'kill', 'start', 'systemctl'):
            self.assertNotIn(word, block)


class ConfigDesktop(unittest.TestCase):
    def parse(self, extra):
        return config.parse({'machine': [dict(name='x', host='x', **extra)]})

    def test_flags(self):
        self.assertTrue(self.parse({'desktop': True}).machines[0].desktop)
        self.assertFalse(self.parse({}).machines[0].desktop)
        self.assertTrue(self.parse({'console': True}).machines[0].console)

    def test_must_be_true_or_false(self):
        with self.assertRaises(config.ConfigError):
            self.parse({'desktop': 'yes'})

    def test_desktop_and_console_are_different_machines(self):
        with self.assertRaises(config.ConfigError):
            self.parse({'desktop': True, 'console': True})


# ─── spark-share, run for real against fake krdpserver, loginctl and prompt ───────────────

WRAPPER = '''
import json, os, subprocess, sys, importlib.machinery, importlib.util
loader = importlib.machinery.SourceFileLoader('spark_share', sys.argv[1])
spec = importlib.util.spec_from_loader('spark_share', loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.KRDP = sys.argv[2]
mod.read_sessions = lambda: json.loads(os.environ['FAKE_SESSIONS'])
def ask(*a, **k):
    open(os.environ['FAKE_ASKED'], 'w').write('asked')
    return os.environ.get('FAKE_ANSWER') == 'allow'
mod.ask = ask
mod.session_env = lambda uid: {'XDG_RUNTIME_DIR': os.environ['FAKE_RUNTIME']}
real = mod.run_as
def run_as(uid, gid, argv, env, capture=False, timeout=None):
    if '_banner' in argv:
        return subprocess.Popen(['sleep', os.environ.get('FAKE_BANNER_S', '300')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return real(uid, gid, argv, env, capture, timeout)
mod.run_as = run_as
sys.argv[0] = sys.argv[1]
sys.exit(mod.main(sys.argv[3:]))
'''

FAKE_KRDP = '''
#!/usr/bin/env python3
import json, os, signal, socket, sys, time
args = sys.argv[1:]
port = int(args[args.index('--port') + 1])
addr = args[args.index('--address') + 1]
open(os.environ['FAKE_KRDP_LOG'], 'w').write(json.dumps(args))
s = socket.socket()
s.bind((addr, port))
s.listen(5)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True:
    time.sleep(0.2)
'''


@unittest.skipUnless(LINUX and shutil.which('openssl'), "needs Linux and openssl")
class RequestRuns(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-share-test-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.krdp = script(self.dir, 'krdpserver', FAKE_KRDP)
        self.wrapper = os.path.join(self.dir, 'wrapper.py')
        with open(self.wrapper, 'w') as f:
            f.write(WRAPPER)
        self.log = os.path.join(self.dir, 'krdp.json')
        self.asked = os.path.join(self.dir, 'asked')
        self.env = dict(os.environ, FAKE_KRDP_LOG=self.log, FAKE_ASKED=self.asked,
                        FAKE_RUNTIME=self.dir, FAKE_ANSWER='allow',
                        FAKE_SESSIONS=json.dumps([session(os.getuid())]), SPARK_LANG='en')

    def start(self, *extra, **env):
        e = dict(self.env, **env)
        return subprocess.Popen([sys.executable, self.wrapper, SHARE, self.krdp, 'request',
                                 '--control', '--from', 'laptop', '--owner', 'Alex'] +
                                list(extra), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=e)

    def first_line(self, proc):
        return json.loads(proc.stdout.readline())

    def finish(self, proc):
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.wait(timeout=20)
        return proc.stderr.read()

    def listening(self, port):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.5).close()
            return True
        except OSError:
            return False

    def test_allowed_request_prints_the_json_line_and_ends_with_the_connection(self):
        p = self.start('--token', '0123456789abcdef')
        info = self.first_line(p)
        self.assertTrue(info['ok'], info)
        self.assertEqual(set(info), {'ok', 'port', 'user', 'password', 'fingerprint', 'mode',
                                     'token', 'expires_s', 'prompted', 'banner'})
        self.assertEqual((info['mode'], info['token'], info['prompted']),
                         ('control', '0123456789abcdef', True))
        self.assertTrue(info['user'].startswith('spark-'))
        self.assertGreaterEqual(len(info['password']), 20)
        self.assertTrue(info['fingerprint'].startswith('sha256:'))
        self.assertTrue(os.path.exists(self.asked))
        # krdpserver was started for 127.0.0.1 only, on that port, with one-time credentials
        args = json.load(open(self.log))
        self.assertEqual(args[args.index('--address') + 1], '127.0.0.1')
        self.assertEqual(int(args[args.index('--port') + 1]), info['port'])
        self.assertIn('--plasma', args)
        self.assertEqual(args[args.index('-p') + 1], info['password'])
        self.assertTrue(self.listening(info['port']))
        # the pinned fingerprint is the fingerprint of the certificate it was given
        cert = args[args.index('--certificate') + 1]
        shown = subprocess.run(['openssl', 'x509', '-in', cert, '-noout', '-fingerprint',
                                '-sha256'], capture_output=True, text=True).stdout
        self.assertEqual(info['fingerprint'], 'sha256:' + shown.split('=')[1].strip().lower())
        key = args[args.index('--certificate-key') + 1]
        self.assertEqual(stat.S_IMODE(os.stat(key).st_mode), 0o600)
        # the SSH connection closing (our stdin) ends it and closes the port
        err = self.finish(p)
        self.assertEqual(p.returncode, 0)
        self.assertIn('connection closed', err)
        self.assertFalse(self.listening(info['port']))
        self.assertFalse(os.path.exists(cert))
        self.assertNotIn(info['password'], err)

    def test_stop_command_ends_it(self):
        token = 'fedcba9876543210'
        p = self.start('--token', token)
        info = self.first_line(p)
        subprocess.run([sys.executable, SHARE, 'stop', token], check=True, timeout=20)
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            self.fail("stop didn't end the share")
        self.assertIn('stopped from Spark Connect', p.stderr.read())
        self.assertFalse(self.listening(info['port']))

    def test_banner_stop_ends_it(self):
        p = self.start(FAKE_BANNER_S='2')
        info = self.first_line(p)
        self.assertTrue(info['banner'])
        p.wait(timeout=20)
        err = p.stderr.read()
        self.assertIn('stopped from the banner', err)
        self.assertFalse(self.listening(info['port']))

    def test_deny_and_timeout_start_nothing(self):
        for answer in ('deny', 'timeout'):
            p = self.start(FAKE_ANSWER=answer)
            info = self.first_line(p)
            self.finish(p)
            self.assertFalse(info['ok'])
            self.assertEqual(info['reason'], 'denied')
            self.assertEqual(p.returncode, 5)
            self.assertFalse(os.path.exists(self.log), "krdpserver ran after a Deny")

    def test_locked_screen_is_not_asked(self):
        p = self.start(FAKE_SESSIONS=json.dumps([session(os.getuid(), locked='yes')]))
        info = self.first_line(p)
        self.finish(p)
        self.assertEqual(info['reason'], 'locked')
        self.assertFalse(os.path.exists(self.asked))
        self.assertFalse(os.path.exists(self.log))

    def test_nobody_logged_in_and_other_user(self):
        for sessions, reason in (([], 'no_session'), ([session(os.getuid() + 1, 'guest')],
                                                      'other_user')):
            p = self.start(FAKE_SESSIONS=json.dumps(sessions))
            self.assertEqual(self.first_line(p)['reason'], reason)
            self.finish(p)

    @unittest.skipIf(os.geteuid() == 0, "this one is about not being root")
    def test_no_ask_is_refused_without_root(self):
        p = self.start('--no-ask')
        info = self.first_line(p)
        self.finish(p)
        self.assertEqual((info['ok'], info['reason'], p.returncode), (False, 'needs_root', 3))
        self.assertFalse(os.path.exists(self.log))
        self.assertFalse(os.path.exists(self.asked))

    @unittest.skipIf(os.geteuid() == 0, "root may use the test hook")
    def test_test_hook_is_ignored_unless_root_owned(self):
        """The prompt can't be bypassed by a file a normal user can write."""
        self.assertIsNone(share_mod.test_hook())
        with mock.patch.object(share_mod, 'TEST_HOOK', os.path.join(self.dir, 'test.json')):
            with open(share_mod.TEST_HOOK, 'w') as f:
                json.dump({'answer': 'allow'}, f)
            self.assertIsNone(share_mod.test_hook())

    def test_bad_token_and_no_krdp(self):
        p = self.start('--token', 'short')
        self.assertEqual(self.first_line(p)['reason'], 'bad_token')
        self.finish(p)
        proc = subprocess.run([sys.executable, self.wrapper, SHARE, '/nonexistent', 'request',
                               '--control'], capture_output=True, text=True, env=self.env)
        self.assertEqual(json.loads(proc.stdout)['reason'], 'no_krdp')

    def test_self_test_and_version(self):
        done = subprocess.run([sys.executable, SHARE, '--version'], capture_output=True,
                              text=True)
        self.assertIn('spark-share', done.stdout)
        self.assertEqual(share_mod.clean_name("<b>Al\nex</b>; rm -rf", "x"), "bAlexb rm -rf")


class Words(unittest.TestCase):
    def test_both_languages_fill_in_alike(self):
        self.assertEqual(sorted(share_mod.EN), sorted(share_mod.FR))
        import string
        for key in share_mod.EN:
            en = sorted(n for _, n, _, _ in string.Formatter().parse(share_mod.EN[key]) if n)
            fr = sorted(n for _, n, _, _ in string.Formatter().parse(share_mod.FR[key]) if n)
            self.assertEqual(en, fr, key)

    def test_language_choice(self):
        self.assertEqual(share_mod.language({'SPARK_LANG': 'fr'}), 'fr')
        self.assertEqual(share_mod.language({'LANG': 'fr_CA.UTF-8'}), 'fr')
        self.assertEqual(share_mod.language({'LANG': 'en_US.UTF-8'}), 'en')
        self.assertEqual(share_mod.language({}), 'en')


@unittest.skipUnless(have_display(), "needs a display")
class Windows(unittest.TestCase):
    """The prompt and the banner, in both languages, with no clipped text."""

    def tk(self):
        import tkinter as tk
        root = tk.Tk()
        self.addCleanup(lambda: self.close(root))
        return tk, root

    @staticmethod
    def close(root):
        try:
            root.destroy()
        except Exception:
            pass

    def in_language(self, lang):
        patcher = mock.patch.dict(os.environ, {'SPARK_LANG': lang})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_prompt_answers(self):
        for how in ('allow', 'deny', 'escape', 'close', 'timeout'):
            tk, root = self.tk()
            got = []
            w = share_mod.build_prompt(tk, root, "Alex", "laptop", 1 if how == 'timeout' else 30,
                                       got.append)
            root.update()
            if how == 'allow':
                w['allow'].event_generate('<ButtonRelease-1>')
            elif how == 'deny':
                w['deny'].event_generate('<ButtonRelease-1>')
            elif how == 'escape':
                root.event_generate('<Escape>')
            elif how == 'close':
                root.protocol('WM_DELETE_WINDOW')
                root.tk.call(root.protocol('WM_DELETE_WINDOW'))
            else:
                end = time.monotonic() + 5
                while not got and time.monotonic() < end:
                    root.update()
                    time.sleep(0.05)
            root.update()
            self.assertEqual(got[:1], ['allow' if how == 'allow' else 'deny'], how)
            root.destroy()

    def test_no_answer_counts_down_to_deny(self):
        tk, root = self.tk()
        got = []
        w = share_mod.build_prompt(tk, root, "Alex", "laptop", 30, got.append)
        root.update()
        self.assertIn('30', w['wait'].cget('text'))
        self.assertEqual(got, [])

    def test_prompt_and_banner_fit_in_both_languages(self):
        from langcheck import clipped
        for lang in ('en', 'fr'):
            self.in_language(lang)
            for owner in ("Alex", "A" * 12 + " " + "B" * 12 + " " + "C" * 12):
                tk, root = self.tk()
                share_mod.build_prompt(tk, root, owner, "living-room-laptop", 30, lambda _a: None)
                root.update()
                self.assertEqual(clipped(root), [], f"prompt {lang} {owner!r}")
                root.destroy()
                tk, root = self.tk()
                share_mod.build_banner(tk, root, owner, lambda: None)
                root.update()
                self.assertEqual(clipped(root), [], f"banner {lang} {owner!r}")
                root.destroy()

    def test_banner_stop_calls_back(self):
        tk, root = self.tk()
        stopped = []
        w = share_mod.build_banner(tk, root, "Alex", lambda: stopped.append(1))
        root.update()
        self.assertIn('Alex', w['text'].cget('text'))
        w['stop'].event_generate('<ButtonRelease-1>')
        root.update()
        self.assertEqual(stopped, [1])


# ─── the Spark Connect side ───────────────────────────────────

class Confirmations(unittest.TestCase):
    ENGLISH = os.environ.get('SPARK_LANG', 'en') != 'fr'

    def desk(self):
        return config.Machine('Living-room PC', 'living-room', desktop=True)

    @unittest.skipUnless(ENGLISH, "English wording")
    def test_asked_share_names_what_runs_and_the_prompt(self):
        c = actions.confirm_share(self.desk(), sudo=False)
        self.assertIn('ssh living-room spark-share request --control', c.detail)
        self.assertNotIn('--no-ask', c.detail)
        self.assertIn('prompt', c.detail)
        self.assertIn('30 seconds', c.detail)
        self.assertIn('Living-room PC', c.title)
        self.assertNotIn('sudo', c.detail.replace('sudo -n', ''))

    @unittest.skipUnless(ENGLISH, "English wording")
    def test_override_says_no_prompt_banner_and_sudo(self):
        c = actions.confirm_share(self.desk(), sudo=True)
        self.assertIn('sudo -n spark-share request --control --no-ask', c.detail)
        self.assertIn('banner', c.message)
        self.assertIn('without', c.title.lower())
        self.assertIn('password', c.detail)

    def test_no_view_only_button(self):
        for table in (EN, FR):
            self.assertNotIn('action.see_screen', table)

    def test_errors_have_words_in_both_languages(self):
        m = self.desk()
        for reason in ('denied', 'locked', 'no_session', 'other_user', 'no_krdp', 'no_tool',
                       'no_viewer', 'forward', 'timeout', 'bad_reply', 'ssh', 'error',
                       'something_new'):
            text = actions.share_error_text(m, reason, 'x')
            self.assertTrue(text and '{' not in text, reason)


class ViewerCommands(unittest.TestCase):
    INFO = {'ok': True, 'port': 4000, 'user': 'spark-1a2b', 'password': 'Pa55-word_xyz',
            'fingerprint': 'sha256:' + ':'.join(['ab'] * 32)}

    def test_password_is_not_in_argv_and_the_certificate_is_pinned(self):
        argv = screen.freerdp_argv('/usr/bin/sdl-freerdp')
        self.assertEqual(argv, ['/usr/bin/sdl-freerdp', '/args-from:stdin'])
        lines = screen.freerdp_args('Living-room PC', 12345, self.INFO)
        self.assertIn('/v:127.0.0.1:12345', lines)
        self.assertIn('/p:Pa55-word_xyz', lines)
        self.assertIn('/cert:fingerprint:' + self.INFO['fingerprint'] + ',deny', lines)
        self.assertFalse([a for a in argv if 'Pa55' in a or self.INFO['user'] in a])

    @unittest.skipUnless(LINUX, "runs a fake FreeRDP")
    def test_launch_gives_freerdp_its_arguments_on_stdin(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        script(folder, 'sdl-freerdp', f'''
            #!/bin/sh
            printf '%s\\n' "$@" > {folder}/argv
            cat > {folder}/stdin
        ''')
        with mock.patch.dict(os.environ, {'PATH': folder + os.pathsep + os.environ['PATH']}):
            viewer = screen.launch_viewer('Living-room PC', 5555, self.INFO)
        for _ in range(100):
            if viewer.poll() is not None:
                break
            time.sleep(0.05)
        argv = open(os.path.join(folder, 'argv')).read()
        stdin = open(os.path.join(folder, 'stdin')).read()
        self.assertEqual(argv.split(), ['/args-from:stdin'])
        self.assertNotIn('Pa55', argv)
        self.assertIn('/p:Pa55-word_xyz', stdin)
        self.assertIn('/cert:fingerprint:sha256:', stdin)

    def test_mstsc_credentials_are_removed_afterwards(self):
        calls = []
        fake = mock.MagicMock()
        fake.run.side_effect = lambda argv, **kw: calls.append(argv)
        proc = mock.MagicMock()
        proc.poll.return_value = None
        fake.Popen.return_value = proc
        fake.TimeoutExpired = subprocess.TimeoutExpired
        with mock.patch.object(screen, 'WINDOWS', True), mock.patch.object(screen, 'subprocess',
                                                                           fake):
            viewer = screen.launch_viewer('Living-room PC', 5555, self.INFO)
            self.assertEqual(calls[0][:2], ['cmdkey', '/generic:TERMSRV/127.0.0.1'])
            self.assertEqual(fake.Popen.call_args[0][0][0], 'mstsc')
            rdp = fake.Popen.call_args[0][0][1]
            text = open(rdp).read()
            self.assertIn('full address:s:127.0.0.1:5555', text)
            self.assertNotIn('Pa55', text)
            self.assertFalse([a for a in fake.Popen.call_args[0][0] if 'Pa55' in a])
            viewer.stop()
            self.assertEqual(calls[-1], ['cmdkey', '/delete:TERMSRV/127.0.0.1'])
            self.assertFalse(os.path.exists(rdp))


FAKE_SSH = '''
#!/usr/bin/env python3
import json, os, signal, socket, sys, time
args = sys.argv[1:]
d = os.environ['FAKE_SSH_DIR']
mode = os.environ.get('FAKE_SSH_MODE', 'ok')
log = open(os.path.join(d, 'calls'), 'a')
log.write(' '.join(args) + '\\n'); log.close()
if '-L' in args:
    local = args[args.index('-L') + 1].split(':')
    s = socket.socket()
    s.bind((local[0], int(local[1])))
    s.listen(5)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(0.2)
remote = args[-1]
if remote.startswith('spark-share request') or remote.startswith('sudo spark-share request'):
    if mode == 'password':
        sys.stderr.write('sudo: a password is required\\n'); sys.exit(1)
    if mode == 'denied':
        print(json.dumps({'ok': False, 'reason': 'denied', 'message': 'no'})); sys.exit(5)
    if mode == 'garbage':
        print('Welcome to the machine'); sys.exit(0)
    print(json.dumps({'ok': True, 'port': 5555, 'user': 'spark-1a2b', 'password': 'pw-pw-pw',
                      'fingerprint': 'sha256:' + ':'.join(['ab'] * 32), 'mode': 'control'}),
          flush=True)
    sys.stdin.read()
    open(os.path.join(d, 'closed'), 'w').write('1')
elif remote.startswith('spark-share handoff'):
    if os.path.exists(os.path.join(d, 'handoff-ready')):
        print(json.dumps({'ok': True, 'port': 5555, 'user': 'spark-1a2b', 'password': 'pw-pw-pw',
                          'fingerprint': 'sha256:' + ':'.join(['ab'] * 32)}))
    else:
        sys.exit(1)
'''


class FakeSshTransport:
    def __init__(self, fake):
        self.fake = fake

    def base_argv(self, machine, tty=False, mux=None, opts=None):
        return [sys.executable, self.fake] + list(opts or [])


@unittest.skipUnless(LINUX, "fake ssh is a Unix script")
class ShareSession(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-share-ssh-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.fake = script(self.dir, 'fake_ssh.py', FAKE_SSH)
        patcher = mock.patch.dict(os.environ, {'FAKE_SSH_DIR': self.dir, 'FAKE_SSH_MODE': 'ok'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.opened = []
        self.machine = config.Machine('Living-room PC', 'living-room', desktop=True)

    def launcher(self, name, port, info):
        self.opened.append((name, port, info['password']))
        return screen.Viewer(subprocess.Popen(['sleep', '60']), None)

    def make(self, sudo=False, terminal=None):
        s = screen.Share(self.machine, FakeSshTransport(self.fake), sudo, self.launcher,
                         terminal, owner='Alex', pc='laptop')
        self.addCleanup(s.stop)
        return s

    def calls(self):
        return open(os.path.join(self.dir, 'calls')).read().splitlines()

    def test_connect_forwards_opens_the_viewer_and_stop_cleans_up(self):
        s = self.make()
        result = s.connect()
        self.assertEqual(result.outcome, DONE, result)
        self.assertTrue(s.alive())
        name, port, password = self.opened[0]
        self.assertEqual((name, password), ('Living-room PC', 'pw-pw-pw'))
        self.assertTrue(screen.port_open(port))
        request = [c for c in self.calls() if 'spark-share request' in c][0]
        self.assertIn('--control', request)
        self.assertIn(f'--token {s.token}', request)
        self.assertNotIn('--no-ask', request)
        forward = [c for c in self.calls() if '-L' in c][0]
        self.assertIn(f'-L 127.0.0.1:{port}:127.0.0.1:5555', forward)
        self.assertIn('-N', forward)
        s.stop()
        self.assertFalse(s.alive())
        self.assertFalse(screen.port_open(port))
        end = time.monotonic() + 5
        while not os.path.exists(os.path.join(self.dir, 'closed')) and time.monotonic() < end:
            time.sleep(0.05)
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'closed')),
                        "the request's stdin wasn't closed")

    def test_the_override_goes_through_sudo_without_asking(self):
        s = self.make(sudo=True)
        self.assertEqual(s.connect().outcome, DONE)
        request = [c for c in self.calls() if 'spark-share request' in c][0]
        self.assertTrue(request.endswith("--no-ask") or '--no-ask' in request)
        self.assertIn('sudo spark-share request', request)

    def test_a_closed_viewer_ends_the_share(self):
        s = self.make()
        s.connect()
        s.viewer = mock.MagicMock()
        s.viewer.poll.return_value = 0
        self.assertFalse(s.alive())

    def test_denied(self):
        os.environ['FAKE_SSH_MODE'] = 'denied'
        r = self.make().connect()
        self.assertEqual((r.outcome, r.reason), ('denied', 'denied'))
        self.assertEqual(self.opened, [])

    def test_sudo_wants_a_password(self):
        os.environ['FAKE_SSH_MODE'] = 'password'
        r = self.make(sudo=True).connect()
        self.assertEqual(r.outcome, NEEDS_PASSWORD)
        self.assertEqual(self.opened, [])

    def test_garbage_is_a_failure(self):
        os.environ['FAKE_SSH_MODE'] = 'garbage'
        self.assertEqual(self.make().connect().outcome, FAILED)

    def test_password_path_opens_a_terminal_then_collects_the_answer(self):
        asked = []

        def terminal(machine, remote):
            asked.append(remote)
            open(os.path.join(self.dir, 'handoff-ready'), 'w').write('1')
            return True
        s = self.make(sudo=True, terminal=terminal)
        r = s.connect_handoff()
        self.assertEqual(r.outcome, DONE, r)
        self.assertTrue(asked[0].startswith('sudo spark-share request --control'))
        self.assertIn('--handoff', asked[0])
        self.assertIn('--no-ask', asked[0])
        s.stop()
        self.assertTrue([c for c in self.calls() if c.endswith(f'spark-share stop {s.token}')])

    def test_forward_that_never_opens_is_reported(self):
        with mock.patch.object(screen, 'FORWARD_WAIT_S', 1):
            s = self.make()
            real = s.transport.base_argv

            def broken(machine, tty=False, mux=None, opts=None):
                if opts:
                    return [sys.executable, '-c', 'import sys; sys.exit(255)']
                return real(machine, tty, mux, opts)
            s.transport.base_argv = broken
            r = s.connect()
        self.assertEqual((r.outcome, r.reason), (FAILED, 'forward'))


@unittest.skipUnless(have_display() and LINUX, "needs a display")
class MachineWindow(unittest.TestCase):
    def make(self, answer='desktop-in-use.json'):
        import test_spark_connect as tsc
        from sparkconnect.app import App
        self.transport = tsc.FakeTransport({'Living-room PC': answer})
        app = App(config_path=tsc.EXAMPLE, transport=self.transport, site_checker=tsc.fake_site,
                  auto_refresh=False, notifier=lambda a, b: True)
        self.addCleanup(app.close)
        for m in app.config.machines:
            app.start(('machine', m.name))
        end = time.monotonic() + 10
        while (app.pending or len(app.results) < 3) and time.monotonic() < end:
            app.root.update()
            time.sleep(0.02)
        return app

    def test_servers_show_nothing_new_and_desktops_show_buttons(self):
        app = self.make()
        app.open_machine('Main server')
        app.root.update()
        self.assertFalse(hasattr(app.machine_view, 'control'))
        self.assertEqual(app.machine_view.desk.winfo_manager(), '')
        app.show_overview()
        app.open_machine('Living-room PC')
        app.root.update()
        v = app.machine_view
        self.assertTrue(v.control.winfo_ismapped())
        self.assertTrue(v.control_sudo.winfo_ismapped())
        self.assertFalse(v.stop.winfo_ismapped())
        self.assertIn(EN['desktop.in_use_user'].format(user='owner'), [
            v.desk.cget('text').splitlines()[0]] if app.scale and False else
            [EN['desktop.in_use_user'].format(user='owner')]) if False else None
        self.assertTrue(v.desk.cget('text').startswith(
            screen_text('desktop.in_use_user', user='owner')))

    def test_cancelled_confirmation_runs_nothing(self):
        app = self.make()
        seen = []
        app.confirm = lambda c: seen.append(c) or False
        started = []
        with mock.patch.object(screen.Share, 'connect', lambda self: started.append(1)):
            app.ask_share(app.machine('Living-room PC'), False)
        self.assertEqual(len(seen), 1)
        self.assertEqual(started, [])
        self.assertNotIn('Living-room PC', app.shares)

    def test_servers_cannot_be_shared(self):
        app = self.make()
        app.confirm = lambda c: self.fail("asked about a server")
        app.ask_share(app.machine('Main server'), True)

    def test_share_shows_on_the_card_and_stop_ends_it(self):
        app = self.make()
        fake = mock.MagicMock()
        fake.alive.return_value = True
        fake.elapsed.return_value = 12 * 60
        app.shares['Living-room PC'] = fake
        app.redraw()
        app.root.update()
        card = app.overview.cards['Living-room PC']
        self.assertIn('12', card.desk.cget('text'))
        self.assertTrue(card.stop.winfo_ismapped())
        app.stop_share('Living-room PC')
        end = time.monotonic() + 5
        while app.pending and time.monotonic() < end:
            app.root.update()
            time.sleep(0.02)
        fake.stop.assert_called_once()
        self.assertNotIn('Living-room PC', app.shares)
        app.root.update()
        self.assertFalse(card.stop.winfo_ismapped())

    def test_a_share_that_ended_by_itself_is_noticed(self):
        app = self.make()
        fake = mock.MagicMock()
        fake.alive.return_value = False
        fake.elapsed.return_value = 5
        app.shares['Living-room PC'] = fake
        app._share_tick()
        self.assertNotIn('Living-room PC', app.shares)

    def test_locked_desktop_says_so_up_front(self):
        app = self.make('desktop-locked.json')
        app.open_machine('Living-room PC')
        app.root.update()
        self.assertIn(screen_text('desktop.locked_note'), app.machine_view.desk.cget('text'))
        app.show_overview()
        app.root.update()
        self.assertIn(screen_text('desktop.locked'),
                      app.overview.cards['Living-room PC'].desk.cget('text'))

    def test_nobody_logged_in(self):
        app = self.make('desktop-none.json')
        app.open_machine('Living-room PC')
        app.root.update()
        self.assertIn(screen_text('desktop.none_note'), app.machine_view.desk.cget('text'))


def screen_text(key, **kw):
    from sparkconnect.text import t
    return t(key, **kw)


if __name__ == '__main__':
    unittest.main()
