"""spark-polkit's logic with a fake PolkitAgent.Session: no display, no bus, no root."""

import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sparksession import polkit_agent  # noqa: E402
from sparksession.polkit_agent import AuthFlow, Choice, program_of  # noqa: E402


class FakeSession:
    def __init__(self, identity, cookie):
        self.identity, self.cookie = identity, cookie
        self.handlers, self.sent, self.cancelled, self.initiated = {}, [], False, False

    def connect(self, name, callback):
        self.handlers[name] = callback

    def initiate(self):
        self.initiated = True

    def response(self, secret):
        self.sent.append(secret)

    def cancel(self):
        self.cancelled = True

    def emit(self, name, *args):
        self.handlers[name](self, *args)


class FakeUi:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))


class Req:
    action_id, cookie, details = 'dev.wolklaw.test', 'cookie-1', {}

    def __init__(self, n=1):
        self.choices = [Choice(f'id{i}', 1000 + i, f'user{i}', f'user{i}') for i in range(n)]


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.sessions, self.results = [], []

    def make(self, n=1):
        def factory(identity, cookie):
            self.sessions.append(FakeSession(identity, cookie))
            return self.sessions[-1]
        self.ui = FakeUi()
        self.flow = AuthFlow(Req(n), self.ui, self.results.append, factory)
        self.flow.start()

    def test_start_uses_the_first_identity_and_cookie(self):
        self.make(2)
        self.assertEqual(self.sessions[0].identity, 'id0')
        self.assertEqual(self.sessions[0].cookie, 'cookie-1')
        self.assertTrue(self.sessions[0].initiated)

    def test_prompt_reaches_the_window_and_password_the_session(self):
        self.make()
        self.sessions[0].emit('request', 'Password: ', False)
        self.assertIn(('ask', ('Password: ', False)), self.ui.calls)
        self.flow.answer('s3cret')
        self.assertEqual(self.sessions[0].sent, ['s3cret'])

    def test_success_closes_and_reports_true(self):
        self.make()
        self.sessions[0].emit('completed', True)
        self.assertEqual(self.results, [True])
        self.assertIn(('close', ()), self.ui.calls)

    def test_wrong_password_starts_a_new_session_for_the_same_user(self):
        self.make(2)
        self.sessions[0].emit('completed', False)
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(self.sessions[1].identity, 'id0')
        self.assertIn(('wrong', ()), self.ui.calls)
        self.assertEqual(self.results, [])

    def test_choosing_another_admin_cancels_the_old_session(self):
        self.make(2)
        self.flow.choose(self.flow.request.choices[1])
        self.assertTrue(self.sessions[0].cancelled)
        self.assertEqual(self.sessions[1].identity, 'id1')
        # a late event from the dropped session is ignored
        self.sessions[0].emit('completed', True)
        self.assertEqual(self.results, [])

    def test_cancel_reports_false_once(self):
        self.make()
        self.flow.cancel()
        self.flow.cancel()
        self.assertEqual(self.results, [False])
        self.assertTrue(self.sessions[0].cancelled)

    def test_no_identity_fails_closed(self):
        self.ui = FakeUi()
        req = Req(0)
        AuthFlow(req, self.ui, self.results.append, lambda *a: None).start()
        self.assertEqual(self.results, [False])

    def test_nothing_typed_is_logged(self):
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
        handler = Handler()
        polkit_agent.log.addHandler(handler)
        polkit_agent.log.setLevel(logging.DEBUG)
        try:
            self.make()
            self.sessions[0].emit('request', 'Password: ', False)
            self.flow.answer('hunter2-secret')
            self.sessions[0].emit('completed', False)
            self.sessions[1].emit('completed', True)
        finally:
            polkit_agent.log.removeHandler(handler)
        self.assertTrue(records)
        self.assertFalse([r for r in records if 'hunter2' in r])


class HelperTests(unittest.TestCase):
    def test_program_from_details(self):
        self.assertEqual(program_of({'program': '/usr/bin/pkexec', 'command_line': 'pkexec ls'}),
                         ('/usr/bin/pkexec', 'pkexec ls'))

    def test_program_from_the_pid(self):
        program, command = program_of({'polkit.caller-pid': str(os.getpid())})
        self.assertEqual(os.path.realpath(program), os.path.realpath(sys.executable))

    def test_no_details_is_empty(self):
        self.assertEqual(program_of({}), ('', ''))

    def test_identities_current_user_first_root_last_groups_expanded(self):
        import gi
        gi.require_version('Polkit', '1.0')
        from gi.repository import Polkit
        uid = os.getuid()
        ids = [Polkit.UnixUser.new(0), Polkit.UnixUser.new(uid), Polkit.UnixUser.new(uid)]
        choices = polkit_agent.describe_identities(ids, you=uid, language='en')
        self.assertEqual([c.uid for c in choices], [uid, 0] if uid != 0 else [0])
        self.assertTrue(choices[0].label.endswith('(you)'))
        french = polkit_agent.describe_identities(ids, you=uid, language='fr')
        self.assertTrue(french[0].label.endswith('(vous)'))


if __name__ == '__main__':
    unittest.main()
