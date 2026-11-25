"""spark-polkit against a fake authority (python-dbusmock) on a private system bus, with the real
polkit-agent-helper-1 and real PAM. The test plays polkitd: it calls the agent's
BeginAuthentication and watches what the agent does.

Needs root (the helper is setuid and the test makes a user with a password), python3-dbusmock and
polkit. Without them the tests skip, so the suite stays runnable on a desktop. CI runs them in a
container (.github/workflows/spark-session.yml)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = '/usr/lib/polkit-1/polkit-agent-helper-1'
USER, PASSWORD = 'sparktest', 'correct-horse-9'
SECRET_IN_LOGS = 'never-log-this-1234'

try:
    import dbusmock
    HAVE_MOCK = True
except ImportError:
    HAVE_MOCK = False


BUS_CONF = '''<busconfig><type>system</type>
<listen>unix:path=/run/dbus/system_bus_socket</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/>
<allow own="*"/><allow user="*"/></policy></busconfig>'''


def can_run():
    return HAVE_MOCK and os.geteuid() == 0 and os.path.exists(HELPER) and shutil.which('useradd')


@unittest.skipUnless(can_run(), 'needs root, python3-dbusmock and polkit (runs in CI)')
class FakeAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['useradd', '-m', USER], check=False)
        subprocess.run(['chpasswd'], input=f'{USER}:{PASSWORD}\n', text=True, check=True)
        cls.uid = int(subprocess.check_output(['id', '-u', USER]))
        # polkit-agent-helper-1 is setuid and drops the environment, so it only finds a system
        # bus at the default socket: run the private one there (the container is throwaway).
        os.makedirs('/run/dbus', exist_ok=True)
        cls.conf = tempfile.NamedTemporaryFile('w', suffix='.conf', delete=False)
        cls.conf.write(BUS_CONF)
        cls.conf.close()
        cls.bus_process = subprocess.Popen(['dbus-daemon', '--nofork', '--config-file', cls.conf.name,
                                            '--address', 'unix:path=/run/dbus/system_bus_socket'])
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=/run/dbus/system_bus_socket'
        for _ in range(100):
            if os.path.exists('/run/dbus/system_bus_socket'):
                break
            time.sleep(0.05)
        cls.mock = dbusmock.SpawnedMock.spawn_with_template(os.path.join(HERE, 'mock_authority.py'))
        from gi.repository import Gio
        cls.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    @classmethod
    def tearDownClass(cls):
        cls.mock.process.terminate()
        cls.mock.process.wait()
        cls.bus_process.terminate()
        cls.bus_process.wait()
        os.unlink(cls.conf.name)
        subprocess.run(['userdel', '-r', USER], check=False, capture_output=True)

    def setUp(self):
        self.mock.obj.ClearCalls()
        self.events_file = tempfile.NamedTemporaryFile('w+', suffix='.jsonl', delete=False).name
        self.agent = None

    def tearDown(self):
        if self.agent and self.agent.poll() is None:
            self.agent.terminate()
            self.agent.wait(10)
        if self.agent and os.environ.get('SPARK_TEST_DEBUG'):
            print('--- agent stderr:\n' + self.agent.stderr.read(), file=sys.stderr)
        os.unlink(self.events_file)

    # --- helpers ---
    def start_agent(self, passwords, language='en'):
        env = dict(os.environ, SPARK_TEST_EVENTS=self.events_file,
                   SPARK_TEST_PASSWORDS=passwords, SPARK_LANG=language)
        env.pop('XDG_SESSION_ID', None)
        self.agent = subprocess.Popen([sys.executable, '-I', '-X', 'faulthandler', os.path.join(HERE, 'agent_harness.py')],
                                      env=env, stderr=subprocess.PIPE, text=True)
        self.wait_for('registered')
        name = [e for e in self.events() if e['event'] == 'registered'][0]['name']
        return name

    def events(self):
        with open(self.events_file) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def wait_for(self, kind, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if any(e['event'] == kind for e in self.events()):
                return
            if self.agent.poll() is not None:
                self.fail(f'agent exited: {self.agent.stderr.read()}')
            time.sleep(0.05)
        self.fail(f'no {kind!r} event; got {self.events()}')

    def begin(self, name, cookie, identities=None, message='Change the system', timeout=30):
        """Call BeginAuthentication on the agent like polkitd does. Returns '' on success or
        the error text."""
        from gi.repository import Gio, GLib
        uids = identities or [self.uid]
        ids = GLib.Variant('a(sa{sv})', [('unix-user', {'uid': GLib.Variant('u', u)}) for u in uids])
        args = GLib.Variant.new_tuple(
            GLib.Variant('s', 'dev.wolklaw.test.change'), GLib.Variant('s', message),
            GLib.Variant('s', 'dialog-password'),
            GLib.Variant('a{ss}', {'program': '/usr/bin/pkexec', 'command_line': 'pkexec true'}),
            GLib.Variant('s', cookie), ids)
        try:
            self.bus.call_sync(name, '/dev/wolklaw/SparkPolkit/AuthenticationAgent',
                               'org.freedesktop.PolicyKit1.AuthenticationAgent', 'BeginAuthentication',
                               args, None, Gio.DBusCallFlags.NONE, timeout * 1000, None)
            return ''
        except GLib.Error as exc:
            return exc.message

    def authority_calls(self, method):
        return [c for c in self.mock.obj.GetCalls() if c[1] == method]

    # --- the tests ---
    def test_registers_with_the_authority(self):
        self.start_agent(PASSWORD)
        calls = (self.authority_calls('RegisterAuthenticationAgent')
                 + self.authority_calls('RegisterAuthenticationAgentWithOptions'))
        self.assertTrue(calls, 'the agent never registered')
        self.assertEqual(calls[-1][2][2], '/dev/wolklaw/SparkPolkit/AuthenticationAgent')

    def test_right_password_authenticates(self):
        name = self.start_agent(PASSWORD)
        error = self.begin(name, 'cookie-right')
        self.assertEqual(error, '')
        kinds = [e['event'] for e in self.events()]
        self.assertIn('window', kinds)
        self.assertIn('closed', kinds)
        window = [e for e in self.events() if e['event'] == 'window'][0]
        self.assertEqual(window['action_id'], 'dev.wolklaw.test.change')
        self.assertEqual(window['details']['program'], '/usr/bin/pkexec')
        responses = self.authority_calls('AuthenticationAgentResponse2')
        self.assertEqual(len(responses), 1, 'the helper reports success to the authority once')
        who = responses[0][2][2]
        self.assertEqual((str(who[0]), int(who[1]['uid'])), ('unix-user', self.uid))
        self.assertEqual(responses[0][2][1], 'cookie-right')

    def test_wrong_password_then_right_one(self):
        name = self.start_agent(f'wrong-password-1,{PASSWORD}')
        self.assertEqual(self.begin(name, 'cookie-retry'), '')
        kinds = [e['event'] for e in self.events()]
        self.assertIn('wrong', kinds)
        self.assertEqual(len(self.authority_calls('AuthenticationAgentResponse2')), 1)

    def test_wrong_password_never_answers_the_authority(self):
        name = self.start_agent('wrong-1,wrong-2,CANCEL')
        error = self.begin(name, 'cookie-wrong')
        self.assertNotEqual(error, '', 'a cancelled request must be an error for polkitd')
        self.assertEqual(len(self.authority_calls('AuthenticationAgentResponse2')), 0)

    def test_cancel_is_an_error(self):
        name = self.start_agent('CANCEL')
        error = self.begin(name, 'cookie-cancel')
        self.assertIn('cancel', error.lower())
        self.assertEqual(len(self.authority_calls('AuthenticationAgentResponse2')), 0)
        self.assertIn('closed', [e['event'] for e in self.events()])

    def test_authority_cancels_the_request(self):
        """polkitd calls CancelAuthentication (the program asking went away): the window closes."""
        from gi.repository import Gio, GLib
        name = self.start_agent('WAIT')      # never answers the prompt
        import threading
        result = {}
        thread = threading.Thread(target=lambda: result.update(error=self.begin(name, 'cookie-gone')))
        thread.start()
        self.wait_for('window')
        self.bus.call_sync(name, '/dev/wolklaw/SparkPolkit/AuthenticationAgent',
                           'org.freedesktop.PolicyKit1.AuthenticationAgent', 'CancelAuthentication',
                           GLib.Variant('(s)', ('cookie-gone',)), None, Gio.DBusCallFlags.NONE,
                           10000, None)
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertNotEqual(result.get('error'), '')

    def test_password_is_never_logged(self):
        name = self.start_agent(SECRET_IN_LOGS + ',CANCEL')
        self.begin(name, 'cookie-secret')
        self.agent.terminate()
        self.agent.wait(10)
        stderr = self.agent.stderr.read()
        self.assertNotIn(SECRET_IN_LOGS, stderr)
        with open(self.events_file) as handle:
            self.assertNotIn(SECRET_IN_LOGS, handle.read())

    def test_two_admins_are_offered(self):
        name = self.start_agent('CANCEL')
        self.begin(name, 'cookie-two', identities=[self.uid, 0])
        window = [e for e in self.events() if e['event'] == 'window'][0]
        self.assertEqual(len(window['choices']), 2)
        joined = ' '.join(window['choices'])
        self.assertIn(USER, joined)
        self.assertIn('root', joined)


if __name__ == '__main__':
    unittest.main()
