"""spark-greeter: the greetd client, the lists, the worker, and (with a display) the window,
against a fake greetd. Safe on a desktop: the window tests skip without a display."""

import os
import sys
import tempfile
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from fake_greetd import FakeGreetd  # noqa: E402
from sparksession import greetd, greeter_data  # noqa: E402
from sparksession.greeter import LoginWorker  # noqa: E402

HAVE_DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def pw(name, uid, shell='/bin/bash', gecos=''):
    return types.SimpleNamespace(pw_name=name, pw_uid=uid, pw_shell=shell, pw_gecos=gecos)


def write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, 'w') as handle:
        handle.write(text)
    return path


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeGreetd()

    def tearDown(self):
        self.server.stop()

    def test_right_password_starts_the_session(self):
        client = greetd.Client(self.server.path)
        greetd.login(client, 'alice', lambda kind, text: FakeGreetd.PASSWORD,
                     ['/usr/bin/spark'], ['A=1'])
        client.close()
        self.assertEqual(self.server.started, [(['/usr/bin/spark'], ['A=1'])])

    def test_wrong_password_is_an_auth_error_and_nothing_starts(self):
        client = greetd.Client(self.server.path)
        with self.assertRaises(greetd.GreetdError) as caught:
            greetd.login(client, 'alice', lambda kind, text: 'nope', ['x'])
        self.assertEqual(caught.exception.kind, 'auth_error')
        self.assertEqual(self.server.started, [])
        # the session was cancelled, so the same connection can try again
        greetd.login(client, 'alice', lambda kind, text: FakeGreetd.PASSWORD, ['x'])
        self.assertEqual(len(self.server.started), 1)

    def test_unknown_user_is_an_auth_error(self):
        client = greetd.Client(self.server.path)
        with self.assertRaises(greetd.GreetdError) as caught:
            greetd.login(client, 'mallory', lambda *_: 'x', ['x'])
        self.assertEqual(caught.exception.kind, 'auth_error')

    def test_second_prompt_is_answered(self):
        self.server.second_factor = True
        client = greetd.Client(self.server.path)
        seen = []

        def answer(kind, text):
            seen.append((kind, text))
            return FakeGreetd.PASSWORD if kind == 'secret' else FakeGreetd.CODE
        greetd.login(client, 'alice', answer, ['x'])
        self.assertEqual([k for k, _ in seen], ['secret', 'visible'])
        self.assertEqual(len(self.server.started), 1)

    def test_no_socket_is_an_error_not_a_crash(self):
        with self.assertRaises(OSError):
            greetd.Client('/nonexistent/greetd.sock')


class DataTests(unittest.TestCase):
    def test_users_are_real_people_only(self):
        entries = [pw('root', 0), pw('daemon', 2, '/sbin/nologin'), pw('alice', 1000, gecos='Alice A,,,'),
                   pw('svc', 1001, '/usr/sbin/nologin'), pw('bob', 1002), pw('nobody', 65534)]
        users = greeter_data.list_users(entries)
        self.assertEqual([u.name for u in users], ['alice', 'bob'])
        self.assertEqual(users[0].label, 'Alice A')
        self.assertEqual(users[1].label, 'bob')

    def test_sessions_spark_first_hidden_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'plasma.desktop', '[Desktop Entry]\nName=Plasma (Wayland)\nExec=/usr/bin/startplasma-wayland\n'
                  'DesktopNames=KDE\n')
            write(d, 'spark.desktop', '[Desktop Entry]\nName=Spark\nName[fr]=Étincelle\nExec=/usr/bin/spark session\n'
                  'DesktopNames=Spark\n')
            write(d, 'hidden.desktop', '[Desktop Entry]\nName=H\nExec=h\nNoDisplay=true\n')
            write(d, 'gone.desktop', '[Desktop Entry]\nName=G\nExec=g\nTryExec=/nonexistent/binary\n')
            write(d, 'readme.txt', 'not a session')
            sessions = greeter_data.list_sessions((d,))
        self.assertEqual([s.ident for s in sessions], ['spark', 'plasma'])
        self.assertEqual(sessions[0].name, 'Spark')
        self.assertEqual(sessions[0].cmd, ['/usr/bin/spark', 'session'])
        self.assertIn('XDG_CURRENT_DESKTOP=Spark', sessions[0].env)
        self.assertIn('XDG_SESSION_DESKTOP=plasma', sessions[1].env)
        self.assertIn('XDG_SESSION_TYPE=wayland', sessions[1].env)

    def test_memory_round_trip_and_a_broken_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sub', 'state.json')
            memory = greeter_data.Memory(path)
            self.assertIsNone(memory.last_user())
            memory.remember('alice', 'plasma')
            again = greeter_data.Memory(path)
            self.assertEqual((again.last_user(), again.last_session('alice')), ('alice', 'plasma'))
            write(d, 'broken.json', '{not json')
            self.assertIsNone(greeter_data.Memory(os.path.join(d, 'broken.json')).last_user())

    def test_memory_in_an_unwritable_place_does_not_raise(self):
        greeter_data.Memory('/proc/nope/state.json').remember('alice', 'spark')


class Ui:
    """Records what LoginWorker tells the screen."""

    def __init__(self):
        self.events, self.done = [], threading.Event()

    def message(self, kind, text):
        self.events.append(('message', kind, text))

    def prompt(self, text, visible):
        self.events.append(('prompt', text, visible))
        self.done.set()

    def failed(self, why, detail):
        self.events.append(('failed', why, detail))
        self.done.set()

    def succeeded(self, username, session):
        self.events.append(('succeeded', username, session.ident))
        self.done.set()


def direct(fn, *args):
    fn(*args)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeGreetd()
        self.session = greeter_data.Session('Spark', ['/usr/bin/spark'], 'Spark', 'spark')
        self.ui = Ui()
        self.worker = LoginWorker(lambda: greetd.Client(self.server.path), direct, self.ui)

    def tearDown(self):
        self.server.stop()

    def run_login(self, user, secret):
        self.worker.start(user, secret, self.session)
        self.assertTrue(self.ui.done.wait(10), self.ui.events)

    def test_success(self):
        self.run_login('alice', FakeGreetd.PASSWORD)
        self.assertEqual(self.ui.events[-1], ('succeeded', 'alice', 'spark'))
        self.assertEqual(self.server.started[0][0], ['/usr/bin/spark'])

    def test_wrong(self):
        self.run_login('alice', 'bad')
        self.assertEqual(self.ui.events[-1][:2], ('failed', 'wrong'))
        self.assertEqual(self.server.started, [])

    def test_second_prompt_waits_for_the_screen(self):
        self.server.second_factor = True
        self.run_login('alice', FakeGreetd.PASSWORD)
        self.assertEqual(self.ui.events[-1][:2], ('prompt', 'Verification code: '))
        self.ui.done.clear()
        self.worker.reply(FakeGreetd.CODE)
        self.assertTrue(self.ui.done.wait(10))
        self.assertEqual(self.ui.events[-1][0], 'succeeded')

    def test_back_during_a_prompt_cancels(self):
        self.server.second_factor = True
        self.run_login('alice', FakeGreetd.PASSWORD)
        self.ui.done.clear()
        self.worker.abort()
        self.assertTrue(self.ui.done.wait(10))
        self.assertEqual(self.ui.events[-1][:2], ('failed', 'cancelled'))
        self.assertEqual(self.server.started, [])

    def test_greetd_not_there(self):
        worker = LoginWorker(lambda: greetd.Client('/nonexistent.sock'), direct, self.ui)
        worker.start('alice', 'x', self.session)
        self.assertTrue(self.ui.done.wait(10))
        self.assertEqual(self.ui.events[-1][:2], ('failed', 'no_daemon'))

    def test_the_password_is_not_in_what_the_screen_hears(self):
        self.run_login('alice', FakeGreetd.PASSWORD)
        self.assertNotIn(FakeGreetd.PASSWORD, repr(self.ui.events))


if HAVE_DISPLAY:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    from sparksession import style
    from sparksession.greeter import build_window


def pump(seconds=0.0, until=None):
    context = GLib.MainContext.default()
    end = time.time() + seconds
    while True:
        while context.pending():
            context.iteration(False)
        if until and until():
            return True
        if time.time() >= end:
            return bool(until and until())
        time.sleep(0.01)


def texts(widget, out=None):
    out = [] if out is None else out
    if isinstance(widget, Gtk.Label):
        out.append(widget.get_label())
    if isinstance(widget, Gtk.Button) and widget.get_label():
        out.append(widget.get_label())
    child = widget.get_first_child()
    while child:
        texts(child, out)
        child = child.get_next_sibling()
    return out


@unittest.skipUnless(HAVE_DISPLAY, 'needs a display (Xvfb in CI)')
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeGreetd()
        self.dir = tempfile.mkdtemp()
        self.memory = greeter_data.Memory(os.path.join(self.dir, 'state.json'))
        self.users = [greeter_data.User('alice', 'Alice A', 1000), greeter_data.User('bob', 'Bob B', 1001)]
        self.sessions = [greeter_data.Session('Spark', ['/usr/bin/spark'], 'Spark', 'spark'),
                         greeter_data.Session('Plasma', ['/usr/bin/startplasma-wayland'], 'KDE', 'plasma')]
        self.powered, self.finished = [], []
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.destroy()
        self.server.stop()
        os.environ.pop('SPARK_LANG', None)

    def open(self, language='en', power_ok=True):
        os.environ['SPARK_LANG'] = language
        style.install()
        self.window = build_window(
            client_factory=lambda: greetd.Client(self.server.path), users=self.users,
            sessions=self.sessions, memory=self.memory,
            power=lambda action: self.powered.append(action) or power_ok,
            fullscreen=False, on_done=lambda: self.finished.append(True))
        pump(0.1)
        return self.window

    def test_english_screen_has_everything(self):
        text = '\n'.join(texts(self.open()))
        for word in ('SIGN IN', 'USER', 'SESSION', 'Alice A', 'Spark', 'Plasma', 'SLEEP', 'RESTART',
                     'SHUT DOWN', 'Other user...'):
            self.assertIn(word, text)

    def test_french_screen(self):
        text = '\n'.join(texts(self.open('fr')))
        for word in ('OUVERTURE DE SESSION', 'UTILISATEUR', 'VEILLE', 'REDÉMARRER', 'ÉTEINDRE',
                     'SE CONNECTER'):
            self.assertIn(word, text)

    def test_right_password_signs_in_and_remembers(self):
        win = self.open()
        win.session_drop.set_selected(1)               # Plasma
        win.password.set_text(FakeGreetd.PASSWORD)
        win.go.emit('clicked')
        self.assertTrue(pump(10, lambda: self.finished))
        self.assertEqual(self.server.started[0][0], ['/usr/bin/startplasma-wayland'])
        self.assertIn('XDG_CURRENT_DESKTOP=KDE', self.server.started[0][1])
        self.assertEqual(win.password.get_text(), '')
        self.assertEqual(self.memory.last_user(), 'alice')
        self.assertEqual(self.memory.last_session('alice'), 'plasma')

    def test_wrong_password_shows_a_warning_and_stays(self):
        win = self.open()
        win.password.set_text('nope')
        win.password.emit('activate')
        self.assertTrue(pump(10, lambda: win.status.get_label()
                             == 'That did not work. Try again.'))
        self.assertFalse(self.finished)
        self.assertTrue(win.go.get_sensitive())
        self.assertEqual(win.password.get_text(), '')

    def test_second_prompt_is_shown_and_answered(self):
        self.server.second_factor = True
        win = self.open()
        win.password.set_text(FakeGreetd.PASSWORD)
        win.go.emit('clicked')
        self.assertTrue(pump(10, lambda: win.prompt_label.get_label() == 'VERIFICATION CODE'))
        win.password.set_text(FakeGreetd.CODE)
        win.password.emit('activate')
        self.assertTrue(pump(10, lambda: self.finished))

    def test_other_user_shows_the_name_field(self):
        win = self.open()
        self.assertFalse(win.name_entry.get_visible())
        win.user_drop.set_selected(len(self.users))
        pump(0.1)
        self.assertTrue(win.name_entry.get_visible())

    def test_remembered_user_and_session_are_preselected(self):
        self.memory.remember('bob', 'plasma')
        win = self.open()
        self.assertEqual(win.user_drop.get_selected(), 1)
        self.assertEqual(win.session_drop.get_selected(), 1)

    def test_power_buttons_call_systemctl_and_failures_show(self):
        win = self.open()
        win.power_buttons['reboot'].emit('clicked')
        self.assertEqual(self.powered, ['reboot'])
        self.window.destroy()
        win = self.open('en', power_ok=False)
        win.power_buttons['poweroff'].emit('clicked')
        self.assertIn('did not work', win.status.get_label())

    def test_no_greetd_says_so(self):
        win = self.open()
        self.server.stop()
        win.password.set_text('x')
        win.go.emit('clicked')
        self.assertTrue(pump(10, lambda: win.status.get_label()
                             == 'The sign-in service is not answering.'))


if __name__ == '__main__':
    unittest.main()
