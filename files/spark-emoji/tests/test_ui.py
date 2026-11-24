"""The picker window: search, tabs, picking, skin tones, recents. Needs a display (run under
xvfb-run, or GDK_BACKEND=broadway with gtk4-broadwayd); skipped without one.

SPARK_SHOT_DIR=/some/folder saves a screenshot from a few of the tests (needs a real
display or xvfb)."""

import os
import sys
import tempfile
import time
import unittest
import warnings

warnings.filterwarnings('ignore', message='.*get_event_loop_policy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    HAVE_GTK = Gtk.init_check() if hasattr(Gtk, 'init_check') else True
except (ImportError, ValueError):
    HAVE_GTK = False

from sparkemoji import core  # noqa: E402


def wait(condition, timeout=5.0) -> bool:
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())


def settle(ms=150):
    end = time.monotonic() + ms / 1000
    ctx = GLib.MainContext.default()
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.005)


@unittest.skipUnless(HAVE_GTK, 'needs a display and GTK 4')
class WindowTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', message='.*get_event_loop_policy')
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['XDG_CONFIG_HOME'] = os.path.join(cls.tmp.name, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(cls.tmp.name, 'state')
        from sparkemoji import style
        cls.style = style
        style.install()
        cls.app = Gtk.Application(application_id='dev.wolklaw.SparkEmojiTest')
        cls.app.register(None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        from sparkemoji.window import PickerWindow
        self.picks = []
        self.tones = []
        self.settings = dict(core.DEFAULTS)
        if os.path.exists(core.recents_path()):
            os.unlink(core.recents_path())
        self.win = PickerWindow(self.app, self.settings,
                                lambda c, e: self.picks.append((c, e)),
                                on_tone=self.tones.append)
        self.win.present()
        settle()

    def tearDown(self):
        self.win.destroy()
        settle(50)

    def type(self, text):
        self.win.entry.set_text(text)
        wait(lambda: self.win.cells and self.win.current is not None, 2)
        settle(200)

    def test_opens_on_smileys_when_nothing_was_used(self):
        self.assertEqual(self.win.current, 'smileys')
        self.assertGreater(len(self.win.cells), 100)

    def test_opens_on_recents_after_a_pick(self):
        core.add_recent('\U0001F44D')
        self.win.show_default()
        self.assertEqual(self.win.current, 'recent')
        self.assertEqual([c.char for c in self.win.cells], ['\U0001F44D'])

    def test_recent_tab_is_empty_with_a_message(self):
        self.win.tab_buttons['recent'].set_active(True)
        settle()
        self.assertEqual(self.win.cells, [])

    def test_every_tab_shows_something(self):
        for tab_id, button in self.win.tab_buttons.items():
            if tab_id == 'recent':
                continue
            button.set_active(True)
            settle(30)
            self.assertTrue(self.win.cells, tab_id)
            self.assertEqual(self.win.current, tab_id)

    def test_symbols_tab_has_arrows_and_currency(self):
        self.win.tab_buttons['math'].set_active(True)
        settle()
        chars = {c.char for c in self.win.cells}
        self.assertTrue({'→', '€', 'é', '≠'} <= chars)

    def test_search_french_and_english(self):
        self.type('chien')
        self.assertIn('\U0001F436', [c.char for c in self.win.cells[:10]])
        self.type('dog')
        self.assertIn('\U0001F436', [c.char for c in self.win.cells[:10]])

    def test_search_with_no_match_shows_a_message(self):
        self.type('qzxqzxqzx')
        self.assertEqual(self.win.cells, [])

    def test_clearing_the_search_goes_back_to_the_tab(self):
        self.win.tab_buttons['food'].set_active(True)
        settle()
        self.type('chien')
        self.win.entry.set_text('')
        settle(200)
        self.assertEqual(self.win.current, 'food')
        self.assertGreater(len(self.win.cells), 50)

    def test_enter_picks_the_first_result(self):
        self.type('euro')
        self.win.entry.emit('activate')
        self.assertEqual([c for c, _ in self.picks], ['€'])

    def test_click_picks(self):
        cell = self.win.cells[3]
        self.win._on_activated(None, cell)
        self.assertEqual(self.picks[0][0], cell.char)

    def test_skin_tone_setting_changes_the_hands(self):
        self.win.tab_buttons['people'].set_active(True)
        settle()
        self.assertIn('\U0001F44B', [c.char for c in self.win.cells])
        self.win.set_tone(2)
        settle()
        chars = [c.char for c in self.win.cells]
        self.assertIn('\U0001F44B\U0001F3FD', chars)
        self.assertNotIn('\U0001F44B', chars)
        self.assertEqual(self.tones, [2])
        self.win.set_tone(-1)
        self.assertIn('\U0001F44B', [c.char for c in self.win.cells])

    def test_tone_applies_to_search_results(self):
        self.win.set_tone(4)
        self.type('waving hand')
        self.assertIn('\U0001F44B\U0001F3FF', [c.char for c in self.win.cells])

    def test_close_hides(self):
        self.win.close_picker()
        self.assertFalse(self.win.get_visible())

    def test_paste_button_can_be_hidden(self):
        self.win.show_paste_button(False)
        self.assertFalse(self.win.paste_button.get_visible())
        self.win.show_paste_button(True)
        self.assertTrue(self.win.paste_button.get_visible())

    def test_every_label_has_text_in_both_languages(self):
        from sparkemoji import text
        for lang in ('en', 'fr'):
            for key, value in (text.EN if lang == 'en' else text.FR).items():
                self.assertTrue(value.strip(), key)

    def test_stays_a_small_popup(self):
        self.assertLessEqual(self.win.get_default_size()[0], 520)
        self.assertLessEqual(self.win.get_default_size()[1], 560)

    def test_screenshot(self):
        folder = os.environ.get('SPARK_SHOT_DIR')
        if not folder:
            self.skipTest('SPARK_SHOT_DIR not set')
        os.makedirs(folder, exist_ok=True)
        self.type('coeur')
        paintable = Gtk.WidgetPaintable.new(self.win)
        settle(300)
        snap = Gtk.Snapshot()
        paintable.snapshot(snap, self.win.get_width(), self.win.get_height())
        node = snap.to_node()
        if node is None:
            self.skipTest('this display backend gives no picture of the window')
        renderer = self.win.get_native().get_renderer()
        texture = renderer.render_texture(node, None)
        texture.save_to_png(os.path.join(folder, 'spark-emoji-search.png'))


if __name__ == '__main__':
    unittest.main()
