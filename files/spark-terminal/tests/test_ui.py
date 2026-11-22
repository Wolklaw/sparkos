"""Windows, tabs, panes and real programs inside them. Needs a display (run under xvfb-run)
and VTE for GTK 4; skipped without them.

SPARK_SHOT_DIR=/some/folder saves a screenshot of the window from a few of the tests."""

import os
import shutil
import sys
import tempfile
import time
import unittest
import warnings

# PyGObject 3.58 on Python 3.15 warns about asyncio on every main loop turn
warnings.filterwarnings('ignore', message='.*get_event_loop_policy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Vte', '3.91')
    from gi.repository import GLib, Gtk, Vte
    HAVE_GTK = Gtk.init_check() if hasattr(Gtk, 'init_check') else True
except (ImportError, ValueError):
    HAVE_GTK = False

from sparkterminal import cli, core  # noqa: E402


def wait(condition, timeout=10.0) -> bool:
    """Run the main loop until condition() is true or timeout seconds pass."""
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if condition():
            return True
        ctx.iteration(False)
        time.sleep(0.01)
    return bool(condition())


def screen_text(pane) -> str:
    result = pane.terminal.get_text_format(Vte.Format.TEXT)
    return result or ''


@unittest.skipUnless(HAVE_GTK, 'needs a display and VTE for GTK 4')
class WindowTest(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        # again here: unittest's runner resets the warning filters before the tests run
        warnings.filterwarnings('ignore', message='.*get_event_loop_policy')
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['XDG_CONFIG_HOME'] = os.path.join(cls.tmp.name, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(cls.tmp.name, 'state')
        os.environ['SHELL'] = shutil.which('bash') or '/bin/sh'
        os.environ['PS1'] = '$ '
        from sparkterminal.app import make_application
        cls.app = make_application(cli.parse([]))
        cls.app.register(None)          # runs startup: the CSS and the shortcuts
        cls.app.hold()                  # keep the app alive between windows

    @classmethod
    def tearDownClass(cls):
        for window in cls.app.get_windows():
            window.destroy()
        cls.tmp.cleanup()

    def setUp(self):
        self.app.settings = dict(core.DEFAULTS)

    def tearDown(self):
        for window in list(self.app.get_windows()):
            if hasattr(window, 'force_close'):
                window.force_close()
        wait(lambda: not self.app.get_windows(), 3)

    def open(self, **kw):
        window = self.app.new_window(**kw)
        self.assertTrue(wait(lambda: window.get_mapped(), 5))
        pane = window.active_pane()
        if not kw.get('argv'):
            self.assertTrue(wait(lambda: pane.pid > 0, 5), 'the shell did not start')
        return window, pane

    def type(self, pane, line: str) -> None:
        pane.terminal.feed_child((line + '\n').encode())

    def shot(self, window, name):
        folder = os.environ.get('SPARK_SHOT_DIR')
        if not folder:
            return
        wait(lambda: False, 0.3)
        w, h = window.get_width(), window.get_height()
        paintable = Gtk.WidgetPaintable.new(window)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, w, h)
        node = snapshot.to_node()
        texture = window.get_renderer().render_texture(node, None)
        texture.save_to_png(os.path.join(folder, name + '.png'))

    # ─── the basics ─────────────────────────────────────────

    def test_echo_output_appears(self):
        window, pane = self.open()
        self.type(pane, 'echo spark-$((40+2))')
        self.assertTrue(wait(lambda: 'spark-42' in screen_text(pane)), screen_text(pane))
        self.assertIsNone(pane.running())          # back at the prompt
        self.shot(window, 'echo')

    def test_tabs_open_and_close(self):
        window, pane = self.open()
        second = window.new_tab()
        third = window.new_tab()
        self.assertEqual(window.notebook.get_n_pages(), 3)
        self.assertIs(window.active_pane(), third)
        window.goto_tab(1)
        self.assertIs(window.active_pane(), pane)
        window._step_tab(-1)
        self.assertIs(window.active_pane(), third)
        window.close_tab(window.tab_of(second))
        self.assertEqual(window.notebook.get_n_pages(), 2)
        # exiting the shell closes its tab
        self.assertTrue(wait(lambda: third.pid > 0))
        self.type(third, 'exit')
        self.assertTrue(wait(lambda: window.notebook.get_n_pages() == 1))
        # and the last one closes the window
        self.type(pane, 'exit')
        self.assertTrue(wait(lambda: not window.get_visible() or window not in
                             self.app.get_windows()))

    def test_splits_open_and_close(self):
        window, first = self.open()
        right = window.split(Gtk.Orientation.HORIZONTAL)
        below = window.split(Gtk.Orientation.VERTICAL)
        tab = window.current_tab()
        self.assertEqual(tab.panes(), [first, right, below])
        self.assertIs(window.active_pane(), below)
        self.assertTrue(wait(lambda: below.pid > 0 and right.pid > 0))
        self.type(below, 'echo in-the-bottom-pane')
        self.assertTrue(wait(lambda: 'in-the-bottom-pane' in screen_text(below)))
        self.assertNotIn('in-the-bottom-pane', screen_text(first))
        wait(lambda: False, 0.3)                    # let the panes get their sizes
        window.focus_direction(0, -1)               # up from the bottom: the right pane
        self.assertTrue(wait(lambda: window.active_pane() is right))
        window.focus_direction(-1, 0)
        self.assertTrue(wait(lambda: window.active_pane() is first))
        self.shot(window, 'splits')
        window.close_pane(below)
        self.assertEqual(tab.panes(), [first, right])
        self.type(right, 'exit')
        self.assertTrue(wait(lambda: tab.panes() == [first]))
        self.assertIsInstance(tab.get_first_child(), type(first))
        self.assertEqual(window.notebook.get_n_pages(), 1)

    def test_new_tab_and_split_start_in_the_same_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            window, pane = self.open(cwd=folder)
            self.assertTrue(wait(lambda: pane.cwd() == os.path.realpath(folder)), pane.cwd())
            sub = os.path.join(folder, 'sub dir')
            os.makedirs(sub)
            self.type(pane, f"cd '{sub}'")
            self.assertTrue(wait(lambda: pane.cwd() == os.path.realpath(sub)))
            other = window.new_tab()
            self.assertTrue(wait(lambda: other.pid > 0 and other.cwd() == os.path.realpath(sub)))
            window.force_close()

    # ─── -e, --workdir, --hold ──────────────────────────────

    def test_workdir_and_command(self):
        with tempfile.TemporaryDirectory() as folder:
            out = os.path.join(folder, 'out.txt')
            opts = cli.parse(['--workdir', folder, '-e', 'sh', '-c', 'pwd > out.txt'])
            cwd = core.start_folder(opts.workdir, self.app.settings)
            window = self.app.new_window(cwd=cwd, argv=opts.command)
            self.assertTrue(wait(lambda: os.path.exists(out) and os.path.getsize(out) > 0))
            with open(out) as f:
                self.assertEqual(f.read().strip(), os.path.realpath(folder))
            # without --hold the window closes when the command ends
            self.assertTrue(wait(lambda: window not in self.app.get_windows()))

    def test_hold_keeps_the_tab_and_shows_the_code(self):
        window, pane = self.open(argv=['sh', '-c', 'echo held-output; exit 3'], hold=True)
        self.assertTrue(wait(lambda: pane.exited))
        self.assertTrue(wait(lambda: 'code 3' in screen_text(pane)), screen_text(pane))
        self.assertIn('held-output', screen_text(pane))
        self.assertIn(window, self.app.get_windows())
        self.assertTrue(window.current_tab().label.has_css_class('exited'))

    def test_missing_command_says_so(self):
        window, pane = self.open(argv=['no-such-program-xyz'])
        self.assertTrue(wait(lambda: pane.exited))
        self.assertIn('no-such-program-xyz', screen_text(pane))
        self.assertIn(window, self.app.get_windows())      # kept open to show why

    # ─── what's running, closing ────────────────────────────

    def test_running_program_is_seen(self):
        window, pane = self.open()
        self.type(pane, 'sleep 30')
        self.assertTrue(wait(lambda: pane.running() == 'sleep'), pane.running())
        self.assertEqual(window.running(), ['sleep'])
        # closing asks; the dialog is GTK's own, so check the question is put
        asked = []
        window._ask = lambda detail, on_yes: asked.append(detail)
        window.close_tab(window.current_tab())
        self.assertEqual(len(asked), 1)
        self.assertIn('sleep', asked[0])
        self.assertEqual(window.notebook.get_n_pages(), 1)        # not closed yet
        self.app.settings['confirm_close'] = False
        window.close_tab(window.current_tab())
        self.assertTrue(wait(lambda: window not in self.app.get_windows()))

    def test_close_request_asks_when_running(self):
        window, pane = self.open()
        self.type(pane, 'sleep 30')
        self.assertTrue(wait(lambda: pane.running() == 'sleep'))
        asked = []
        window._ask = lambda detail, on_yes: asked.append(on_yes)
        window.close()
        self.assertEqual(len(asked), 1)
        self.assertIn(window, self.app.get_windows())
        asked[0]()
        self.assertTrue(wait(lambda: window not in self.app.get_windows()))

    # ─── full-screen programs ───────────────────────────────

    def _full_screen(self, argv, quit_keys, marker):
        window, pane = self.open(argv=argv, hold=True)
        self.assertTrue(wait(lambda: pane.pid > 0))
        # the program switched to the alternate screen and drew something
        self.assertTrue(wait(lambda: marker(screen_text(pane)), 10), screen_text(pane))
        self.shot(window, os.path.basename(argv[0]))
        pane.terminal.feed_child(quit_keys)
        self.assertTrue(wait(lambda: pane.exited, 10), screen_text(pane))
        self.assertTrue(wait(lambda: 'code 0' in screen_text(pane)), screen_text(pane))

    def test_vim_starts_and_quits(self):
        vim = shutil.which('vim') or shutil.which('vi')
        if not vim:
            self.skipTest('no vim')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'note.txt')
            with open(path, 'w') as f:
                f.write('spark vim test\n')
            self._full_screen([vim, '-u', 'NONE', '-N', path], b'\x1b:q!\r',
                              lambda s: 'spark vim test' in s and '~' in s)

    def test_less_starts_and_quits(self):
        less = shutil.which('less')
        if not less:
            self.skipTest('no less')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'long.txt')
            with open(path, 'w') as f:
                f.write(''.join(f'line {i}\n' for i in range(500)))
            self._full_screen([less, path], b'q', lambda s: 'line 0' in s and 'line 499' not in s)

    def test_title_from_the_program(self):
        window, pane = self.open()
        # sleep, so the shell's prompt (which sets its own title on some systems) doesn't
        # come back and replace it while we look
        self.type(pane, "printf '\\e]0;my-title\\a'; sleep 10")
        self.assertTrue(wait(lambda: window.current_tab().label.get_label() == 'my-title'),
                        window.current_tab().label.get_label())
        self.assertIn('my-title', window.get_title())

    def test_unicode_wide_characters_and_true_colour(self):
        window, pane = self.open()
        self.type(pane, "printf '\\e[38;2;255;46;136mé漢字🙂\\e[0m-end\\n'")
        self.assertTrue(wait(lambda: 'é漢字🙂-end' in screen_text(pane)), screen_text(pane))

    # ─── search, scrollback, copy, zoom ─────────────────────

    def test_search_in_scrollback(self):
        window, pane = self.open()
        self.type(pane, 'for i in $(seq 1 300); do echo row-$i; done; echo needle-here')
        # the output, not the command line echoed as it was typed
        self.assertTrue(wait(lambda: 'row-300\nneedle-here' in screen_text(pane)))
        window.show_find()
        window.find_entry.set_text('row-1')            # scrolled out of view
        self.assertTrue(window.find(backwards=True))
        window.find_entry.set_text('nowhere-to-be-found')
        self.assertFalse(window.find(backwards=True))
        self.assertTrue(window.find_status.get_label())
        window.find_regex.set_active(True)
        window.find_entry.set_text('row-[0-9]+(')       # broken pattern
        self.assertFalse(window.find(backwards=True))
        window.find_entry.set_text('row-29[0-9]')
        self.assertTrue(window.find(backwards=True))
        self.shot(window, 'search')
        window.hide_find()
        self.assertFalse(window.findbar.get_visible())

    def test_scrollback_setting(self):
        self.app.settings = dict(core.DEFAULTS, scrollback=1234)
        window, pane = self.open()
        self.assertEqual(pane.terminal.get_scrollback_lines(), 1234)
        self.app.save_settings(dict(core.DEFAULTS, scrollback=50, font_size=14))
        self.assertEqual(pane.terminal.get_scrollback_lines(), 50)
        self.assertEqual(core.load_settings()['scrollback'], 50)

    def test_copy_on_select_and_select_all(self):
        window, pane = self.open()
        self.type(pane, 'echo copy-me')
        self.assertTrue(wait(lambda: 'copy-me' in screen_text(pane)))
        pane.terminal.select_all()
        self.assertTrue(pane.terminal.get_has_selection())
        got = {}
        clipboard = window.get_clipboard()
        clipboard.read_text_async(None, lambda cb, res: got.setdefault('text',
                                                                       cb.read_text_finish(res)))
        self.assertTrue(wait(lambda: 'text' in got))
        self.assertIn('copy-me', got['text'] or '')

    def test_zoom(self):
        window, pane = self.open()
        window.activate_action('win.zoom-in', None)
        self.assertGreater(pane.terminal.get_font_scale(), 1.0)
        window.activate_action('win.zoom-reset', None)
        self.assertEqual(pane.terminal.get_font_scale(), 1.0)
        window.activate_action('win.zoom-out', None)
        self.assertLess(pane.terminal.get_font_scale(), 1.0)

    def test_links_are_found(self):
        window, pane = self.open()
        self.type(pane, "clear; printf 'https://wolklaw.dev/x /etc/hostname-not-here\\n'")
        self.assertTrue(wait(lambda: 'https://wolklaw.dev/x' in screen_text(pane)))
        wait(lambda: False, 0.3)
        term = pane.terminal
        cw, ch = term.get_char_width(), term.get_char_height()
        # find the row the link is on
        rows = screen_text(pane).split('\n')
        row = next(i for i, line in enumerate(rows) if line.startswith('https://'))
        link = None
        for dx in (0, 4, 8):          # VTE's padding: try a few spots inside the first cell
            link = pane.link_at(dx + cw * 3, dx + ch * row + ch / 2)
            if link:
                break
        self.assertIsNotNone(link)
        self.assertEqual(link['kind'], 'url')
        self.assertEqual(link['target'], 'https://wolklaw.dev/x')


if __name__ == '__main__':
    unittest.main()
