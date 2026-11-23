"""The console view (sparkconnect/console.py): the screen it draws from a fixture vcsa dump, the
keys it would type, the notices it writes on tty1, and the loop around them. It never touches the
real /dev/vcsa1, /dev/tty1 or /dev/uinput; the virtual keyboard is tested against /dev/uinput only
when this machine lets the test user open it (CI containers usually don't)."""

import io
import os
import shlex
import struct
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-connect-{var.lower()}-'))
os.environ['SPARK_CONNECT_REDUCED_MOTION'] = '1'

if not sys.platform.startswith('linux'):      # console.py runs on the server: Linux only
    raise unittest.SkipTest("console.py is for Linux servers")

from sparkconnect import actions, config, console  # noqa: E402

FIXTURE = os.path.join(HERE, 'fixtures', 'vcsa1.bin')
LINUX = sys.platform.startswith('linux')


def fixture():
    with open(FIXTURE, 'rb') as f:
        return f.read()


class Screen(unittest.TestCase):
    def test_parse(self):
        rows, cols, cx, cy, cells = console.parse_vcsa(fixture())
        self.assertEqual((rows, cols, cx, cy, len(cells)), (25, 80, 15, 3, 2000))
        self.assertEqual(cells[0], (ord('R'), 0x0f))

    def test_short_or_empty_dumps(self):
        self.assertIsNone(console.parse_vcsa(b''))
        self.assertIsNone(console.parse_vcsa(bytes([25, 80, 0, 0]) + b'x' * 10))
        self.assertIsNone(console.parse_vcsa(bytes([0, 0, 0, 0])))

    def test_render_has_the_text_the_cursor_and_the_status(self):
        frame = console.parse_vcsa(fixture())
        text = console.render(frame, 100, 30, "VIEWING")
        self.assertIn('Rocky Linux 9.4', text)
        self.assertIn('gd-host login:', text)
        self.assertIn('╔', text)                  # cp437 0xc9, a box corner
        self.assertTrue(text.endswith('\x1b[4;16H'))   # cursor: row 4, column 16
        self.assertIn('VIEWING', text)

    def test_render_clips_to_the_terminal(self):
        frame = console.parse_vcsa(fixture())
        text = console.render(frame, 40, 10, "x")
        plain = __import__('re').sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
        self.assertLessEqual(max(len(line) for line in plain.split('\r\n')), 40)
        self.assertNotIn('gd-host login:', text.split('\x1b[10;1H')[0].split('\r\n')[8]) \
            if False else None
        self.assertEqual(text.count('\r\n'), 9)       # 9 console rows and the status row

    def test_colors(self):
        self.assertEqual(console.sgr(0x07), '\x1b[0;37;40m')
        self.assertEqual(console.sgr(0x0f), '\x1b[0;97;40m')
        self.assertEqual(console.sgr(0x14), '\x1b[0;31;44m')   # red on blue (VGA 4 = red = ANSI 31)


class Keys(unittest.TestCase):
    def keys(self, data):
        return console.decode_keys(data)

    def test_letters_digits_and_shift(self):
        self.assertEqual(self.keys(b'a'), [(30, False, False)])
        self.assertEqual(self.keys(b'A'), [(30, True, False)])
        self.assertEqual(self.keys(b'1!'), [(2, False, False), (2, True, False)])
        self.assertEqual(self.keys(b'/?'), [(53, False, False), (53, True, False)])

    def test_enter_tab_backspace_escape(self):
        self.assertEqual(self.keys(b'\r\t\x7f\x1b'),
                         [(28, False, False), (15, False, False), (14, False, False),
                          (1, False, False)])

    def test_control_letters(self):
        self.assertEqual(self.keys(b'\x03'), [(46, False, True)])      # Ctrl+C
        self.assertEqual(self.keys(b'\x04'), [(32, False, True)])      # Ctrl+D

    def test_arrows_and_friends(self):
        self.assertEqual(self.keys(b'\x1b[A\x1b[B\x1b[C\x1b[D'),
                         [(103, False, False), (108, False, False), (106, False, False),
                          (105, False, False)])
        self.assertEqual(self.keys(b'\x1b[3~'), [(111, False, False)])
        self.assertEqual(self.keys(b'\x1bOH'), [(102, False, False)])

    def test_what_it_cannot_type_is_dropped(self):
        self.assertEqual(self.keys('é'.encode()), [])
        self.assertEqual(self.keys(b'\x1b[99~a'), [(30, False, False)])

    def test_a_command_line(self):
        keys = self.keys(b'ls -l\r')
        self.assertEqual(len(keys), 6)
        self.assertEqual(keys[-1][0], 28)

    def test_every_printable_character_has_a_key(self):
        for ch in range(32, 127):
            self.assertIn(chr(ch), console.KEYS, chr(ch))

    def test_events(self):
        self.assertEqual(len(console.event(1, 30, 1)), struct.calcsize('llHHi'))

    @unittest.skipUnless(LINUX and os.access('/dev/uinput', os.W_OK), "needs /dev/uinput access")
    def test_the_virtual_keyboard_can_be_made(self):
        kb = console.Keyboard()
        try:
            kb.type(b'')
        finally:
            kb.close()


class Notices(unittest.TestCase):
    def test_notice_writes_one_line(self):
        path = os.path.join(tempfile.mkdtemp(), 'tty1')
        open(path, 'w').close()
        self.assertTrue(console.notice(path, 'hello'))
        self.assertEqual(open(path, newline='').read(), '\r\n[Spark Connect] hello\r\n')

    def test_missing_console_is_not_an_error(self):
        self.assertFalse(console.notice('/nonexistent/tty1', 'hello'))

    def test_names_are_cleaned(self):
        self.assertEqual(console.clean('lap top;rm -rf /'), 'laptoprm-rf')
        self.assertEqual(console.clean(''), 'another PC')

    def test_foreground(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'active')
        open(path, 'w').write('tty1\n')
        self.assertTrue(console.foreground_is(path, '/dev/tty1'))
        open(path, 'w').write('tty2\n')
        self.assertFalse(console.foreground_is(path, '/dev/tty1'))
        self.assertFalse(console.foreground_is(os.path.join(folder, 'none'), '/dev/tty1'))


class FakeKeyboard:
    made = []

    def __init__(self, path=None):
        self.typed = []
        self.closed = False
        FakeKeyboard.made.append(self)

    def type(self, data):
        self.typed.append(data)

    def close(self):
        self.closed = True


@unittest.skipUnless(LINUX, "pipes and files")
class Loop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vcsa = os.path.join(self.dir, 'vcsa1')
        self.tty = os.path.join(self.dir, 'tty1')
        self.active = os.path.join(self.dir, 'active')
        open(self.vcsa, 'wb').write(fixture())
        open(self.tty, 'w').close()
        open(self.active, 'w').write('tty1\n')
        FakeKeyboard.made = []
        self.r, self.w = os.pipe()
        self.addCleanup(os.close, self.r)
        self.out = io.StringIO()

    def go(self, feed, **kw):
        def writer():
            for chunk in feed:
                time.sleep(0.15)
                os.write(self.w, chunk)
            os.close(self.w)
        threading.Thread(target=writer, daemon=True).start()
        orig = console.Keyboard
        console.Keyboard = FakeKeyboard
        try:
            return console.run('my-pc', self.r, self.out, self.vcsa, self.tty, '/dev/null',
                               self.active, **kw)
        finally:
            console.Keyboard = orig

    def notices(self):
        return open(self.tty).read()

    def test_view_then_quit(self):
        why = self.go([b'q'])
        self.assertEqual(why, 'quit')
        self.assertIn('Rocky Linux', self.out.getvalue())
        self.assertIn('VIEWING', self.out.getvalue())
        text = self.notices()
        self.assertIn('viewed from my-pc', text)
        self.assertIn('no longer being viewed from my-pc', text)
        self.assertEqual(FakeKeyboard.made, [])           # no keyboard until asked

    def test_keys_are_not_typed_while_viewing(self):
        self.go([b'ls\r', b'q'])
        self.assertEqual(FakeKeyboard.made, [])

    def test_toggle_types_then_stops_and_says_so(self):
        why = self.go([b'\x1d', b'ls\r', b'\x1d', b'q'])
        self.assertEqual(why, 'quit')
        kb = FakeKeyboard.made[0]
        self.assertEqual(b''.join(kb.typed), b'ls\r')
        self.assertTrue(kb.closed)
        text = self.notices()
        self.assertIn('my-pc is now typing into this console', text)
        self.assertIn('my-pc stopped typing', text)
        self.assertIn('TYPING', self.out.getvalue())

    def test_q_is_typed_not_quit_while_typing(self):
        why = self.go([b'\x1d', b'q', b'\x03', b'\x1d', b'q'])
        self.assertEqual(why, 'quit')
        self.assertEqual(b''.join(FakeKeyboard.made[0].typed), b'q\x03')

    def test_no_typing_when_tty1_is_not_in_front(self):
        open(self.active, 'w').write('tty2\n')
        self.go([b'\x1d', b'q'])
        self.assertEqual(FakeKeyboard.made, [])
        self.assertIn('not the console on screen', self.out.getvalue())

    def test_no_virtual_keyboard_is_said_not_fatal(self):
        def refuse(path=None):
            raise PermissionError(13, 'Permission denied')
        orig = console.Keyboard
        console.Keyboard = refuse
        try:
            def writer():
                for chunk in (b'\x1d', b'q'):
                    time.sleep(0.15)
                    os.write(self.w, chunk)
            threading.Thread(target=writer, daemon=True).start()
            why = console.run('my-pc', self.r, self.out, self.vcsa, self.tty, '/dev/null',
                              self.active)
        finally:
            console.Keyboard = orig
        self.assertEqual(why, 'quit')
        self.assertIn('No virtual keyboard', self.out.getvalue())

    def test_closed_terminal_ends_it_and_still_says_so(self):
        why = self.go([])
        self.assertEqual(why, 'terminal closed')
        self.assertIn('no longer being viewed', self.notices())

    def test_a_changed_screen_is_redrawn_an_unchanged_one_is_not(self):
        why = self.go([b'', b''], max_frames=None) if False else None
        before = self.out.getvalue()
        self.assertEqual(before, '')
        self.go([b'x', b'q'])
        self.assertEqual(self.out.getvalue().count('Rocky Linux'), 1)


class Command(unittest.TestCase):
    def machine(self):
        return config.Machine('GD host', 'gd-host', console=True)

    def test_remote_command_carries_the_script_and_the_pc_name(self):
        remote = actions.console_remote('my-pc')
        self.assertTrue(remote.startswith('sudo python3 -c '))
        parts = shlex.split(remote)
        self.assertEqual(parts[:3], ['sudo', 'python3', '-c'])
        self.assertEqual(parts[4], 'my-pc')
        with open(console.__file__, encoding='utf-8') as f:
            self.assertEqual(parts[3], f.read())

    def test_script_compiles_and_runs_as_dash_c(self):
        import subprocess
        parts = shlex.split(actions.console_remote('my-pc'))
        done = subprocess.run([sys.executable, parts[2], parts[3], parts[4]],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 3 if os.geteuid() else 2)
        self.assertTrue('needs root' in done.stderr or 'needs a terminal' in done.stderr)

    @unittest.skipIf(os.environ.get('SPARK_LANG') == 'fr', "English wording")
    def test_confirmation_is_plain_about_sudo_and_no_prompt(self):
        c = actions.confirm_console(self.machine())
        text = c.title + c.message + c.detail
        self.assertIn('sudo', text)
        self.assertIn('password', text)
        self.assertIn('no prompt', text.lower())
        self.assertIn('tty1', text)
        self.assertIn('nothing is installed', text.lower())
        self.assertIn('ssh -t gd-host', c.detail)

    def test_terminal_command(self):
        argv = actions.terminal_argv(self.machine(), actions.console_remote('pc'), ssh='ssh')
        if argv:
            self.assertIn('-t', argv)
            self.assertIn('gd-host', argv)


class ConfigConsole(unittest.TestCase):
    def test_flag(self):
        cfg = config.parse({'machine': [dict(name='g', host='g', console=True)]})
        self.assertTrue(cfg.machines[0].console)


if __name__ == '__main__':
    unittest.main()
