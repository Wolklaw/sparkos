"""The clipboard popup and the notes window. Needs a display (run under xvfb-run); skipped without
one. Files go in a temporary folder, never the person's own.

SPARK_SHOT_DIR=/some/folder saves screenshots from two of the tests (needs a real display or
xvfb)."""

import os
import sys
import tempfile
import time
import unittest
import warnings

os.environ.setdefault('GDK_DEBUG', 'no-portals')     # no desktop portal in a test display
warnings.filterwarnings('ignore', message='.*get_event_loop_policy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gdk, GLib, Gtk
    HAVE_GTK = Gtk.init_check() if hasattr(Gtk, 'init_check') else True
except (ImportError, ValueError):
    HAVE_GTK = False

from sparknotes import core, text  # noqa: E402

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\xa5'
       b'\xd8\x87\xf0\x00\x00\x00\x00IEND\xaeB`\x82')


_APP = None
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons',
                       'spark-notes-128.png'), 'rb') as _f:
    REAL_PNG = _f.read()          # a picture GTK can decode; PNG above is only bytes


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


def shot(window, name):
    """Save the window as a PNG. window.paintable must have been made before it was shown."""
    folder = os.environ.get('SPARK_SHOT_DIR')
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    seen = []
    handler = window.paintable.connect('invalidate-contents', lambda *_: seen.append(1))
    window.queue_draw()
    wait(lambda: seen, 2)               # the frame with the latest changes
    window.paintable.disconnect(handler)
    settle(300)
    paintable = window.paintable
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, window.get_width(), window.get_height())
    node = snap.to_node()
    if node is None:
        return
    texture = window.get_native().get_renderer().render_texture(node, None)
    texture.save_to_png(os.path.join(folder, name))


def labels(widget, found=None):
    found = [] if found is None else found
    if isinstance(widget, Gtk.Label):
        found.append(widget.get_text())
    child = widget.get_first_child()
    while child is not None:
        labels(child, found)
        child = child.get_next_sibling()
    return found


class Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['XDG_CONFIG_HOME'] = os.path.join(cls.tmp.name, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(cls.tmp.name, 'state')
        os.environ['XDG_DATA_HOME'] = os.path.join(cls.tmp.name, 'data')
        os.environ['LANG'] = 'en_US.UTF-8'
        for var in ('LC_ALL', 'LC_MESSAGES', 'LANGUAGE'):
            os.environ.pop(var, None)
        from sparknotes import style
        cls.style = style
        style.install()
        global _APP
        if _APP is None:
            _APP = Gtk.Application(application_id='dev.wolklaw.SparkNotesTest')
            _APP.register(None)
        cls.app = _APP

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


@unittest.skipUnless(HAVE_GTK, 'needs a display and GTK 4')
class ClipboardPopupTest(Base):

    def setUp(self):
        from sparknotes.clip_window import ClipWindow
        self.history = core.History(os.path.join(self.tmp.name, f'h{time.monotonic_ns()}'))
        for s in ('first copy', 'Dîner à Québec', 'https://example.org/a/long/link'):
            self.history.add_text(s)
        self.copied = []
        self.paused = []
        self.notes_opened = []
        self.settings = dict(core.DEFAULTS)
        self.win = ClipWindow(self.app, self.settings, self.history,
                              lambda item: (self.copied.append(item) or (True, '')),
                              self.paused.append, lambda: self.notes_opened.append(1),
                              glitch=self.style.Glitch(True))
        self.win.keep_open = True       # a test display gives it no focus; don't close on that
        self.win.paintable = Gtk.WidgetPaintable.new(self.win)
        self.win.present()
        settle()

    def tearDown(self):
        self.win.destroy()

    def test_lists_newest_first(self):
        self.assertEqual([r.item.text for r in self.win.rows],
                         ['https://example.org/a/long/link', 'Dîner à Québec', 'first copy'])
        self.assertIn(text.t('clip.count', n=3), labels(self.win))

    def test_search_filters_and_ignores_accents(self):
        self.win.entry.set_text('quebec')
        settle(300)
        self.assertEqual([r.item.text for r in self.win.rows], ['Dîner à Québec'])
        self.win.entry.set_text('zzzz')
        settle(300)
        self.assertEqual(self.win.rows, [])
        self.assertTrue(self.win.empty.get_visible())

    def test_enter_copies_the_first_and_closes(self):
        self.win.entry.emit('activate')
        self.assertEqual(self.copied[0].text, 'https://example.org/a/long/link')
        self.assertFalse(self.win.get_visible())

    def test_click_on_a_row_copies_it(self):
        self.win.list.emit('row-activated', self.win.rows[2])
        self.assertEqual(self.copied[0].text, 'first copy')
        self.assertFalse(self.win.get_visible())

    def test_failed_copy_stays_open_and_says_why(self):
        self.win.on_copy = lambda item: (False, 'wl-copy is missing')
        self.win.list.emit('row-activated', self.win.rows[0])
        self.assertTrue(self.win.get_visible())
        self.assertIn('wl-copy is missing', self.win.status.get_text())

    def test_pin_moves_an_item_to_the_top(self):
        self.win.toggle_pin(self.win.rows[2].item)
        self.assertEqual(self.win.rows[0].item.text, 'first copy')
        self.assertTrue(self.win.rows[0].has_css_class('pinned'))

    def test_delete_removes_it(self):
        self.win.delete_item(self.win.rows[0].item)
        self.assertEqual(len(self.win.rows), 2)
        self.assertEqual(len(self.history.items()), 2)

    def test_clear_keeps_pinned(self):
        self.win.toggle_pin(self.win.rows[0].item)
        self.win._on_clear()
        self.assertEqual(len(self.win.rows), 1)
        self.assertIn('2', self.win.status.get_text())

    def test_pause_button_toggles_and_reports(self):
        self.assertEqual(self.win.pause_button.get_label(), text.t('clip.pause'))
        self.win.pause_button.emit('clicked')
        self.assertEqual(self.paused, [True])
        self.assertEqual(self.win.pause_button.get_label(), text.t('clip.paused'))
        self.assertTrue(self.win.pause_button.has_css_class('paused'))
        self.win.pause_button.emit('clicked')
        self.assertEqual(self.paused, [True, False])

    def test_notes_button_opens_notes_and_closes(self):
        self.win.on_open_notes()
        self.assertEqual(self.notes_opened, [1])

    def test_escape_clears_the_search_then_closes(self):
        self.win.entry.set_text('abc')
        self.win._on_key(None, Gdk.KEY_Escape, 0, 0)
        self.assertEqual(self.win.entry.get_text(), '')
        self.assertTrue(self.win.get_visible())
        self.win._on_key(None, Gdk.KEY_Escape, 0, 0)
        self.assertFalse(self.win.get_visible())

    def test_empty_history_says_so(self):
        self.history.clear(keep_pinned=False)
        self.win.reload()
        self.assertEqual(self.win.empty.get_text(), text.t('clip.empty'))

    def test_paused_and_empty_says_paused(self):
        self.history.clear(keep_pinned=False)
        self.win.settings['paused'] = True
        self.win.reload()
        self.assertEqual(self.win.empty.get_text(), text.t('clip.paused_empty'))

    def test_image_row_has_a_thumbnail(self):
        self.history.add_image(REAL_PNG, 'image/png')
        self.win.reload()
        kinds = [r.item.kind for r in self.win.rows]
        self.assertEqual(kinds[0], 'image')
        self.assertIn('128 x 128', ' '.join(labels(self.win.rows[0])))      # decoded for the thumbnail

    def test_stays_a_small_popup(self):
        w, h = self.win.get_default_size()
        self.assertLessEqual(w, 520)
        self.assertLessEqual(h, 560)

    def test_screenshot(self):
        # a window on a live desktop may not repaint, so show it only after it is filled
        from sparknotes.clip_window import ClipWindow
        self.win.destroy()
        self.history.add_image(REAL_PNG, 'image/png')
        pinned = self.history.add_text('Meeting notes template')
        self.history.set_pinned(pinned.id, True)
        self.win = ClipWindow(self.app, self.settings, self.history, lambda i: (True, ''),
                              lambda p: None, lambda: None, glitch=self.style.Glitch(False))
        self.win.keep_open = True
        self.win.paintable = Gtk.WidgetPaintable.new(self.win)
        self.win.present()
        settle(500)
        shot(self.win, 'spark-notes-clipboard.png')


@unittest.skipUnless(HAVE_GTK, 'needs a display and GTK 4')
class NotesWindowTest(Base):

    def setUp(self):
        from sparknotes.notes_window import NotesWindow
        self.store = core.NoteStore(os.path.join(self.tmp.name, f'n{time.monotonic_ns()}'))
        self.store.save('aaa111', "# Shopping\nmilk\neggs\n")
        self.store.save('bbb222', "Ideas\nbuild a thing\n")
        self.opened = []
        self.win = NotesWindow(self.app, self.store, dict(core.DEFAULTS),
                               on_open_clipboard=lambda: self.opened.append(1),
                               glitch=self.style.Glitch(True))
        self.win.paintable = Gtk.WidgetPaintable.new(self.win)
        self.win.present()
        settle()

    def tearDown(self):
        self.win.destroy()

    def type(self, s):
        self.win.buffer.insert_at_cursor(s)

    def test_lists_notes_and_opens_the_first(self):
        self.assertEqual(len(self.win.rows), 2)
        self.assertIsNotNone(self.win.current_id)
        self.assertIn(self.win._text().split('\n')[0], ('# Shopping', 'Ideas'))

    def test_autosaves_after_typing(self):
        self.win.open_note('aaa111')
        self.win.buffer.set_text("# Shopping\nmilk\neggs\nbread\n")
        self.assertTrue(wait(lambda: 'bread' in self.store.load('aaa111').body, 3))

    def test_close_flushes_a_pending_edit(self):
        self.win.open_note('bbb222')
        self.win.buffer.set_text("Ideas\nchanged right before closing")
        self.win._on_close()
        self.assertIn('changed right before closing', self.store.load('bbb222').body)

    def test_new_note_and_empty_is_not_kept(self):
        before = len(self.store.list())
        self.win.new_note()
        self.win.flush()
        self.assertEqual(len(self.store.list()), before)
        self.type("fresh thought")
        self.win.flush()
        self.assertEqual(len(self.store.list()), before + 1)

    def test_search_narrows_the_list(self):
        self.win.search.set_text('milk')
        settle(400)
        self.assertEqual(len(self.win.rows), 1)
        self.assertEqual(self.win.rows[0].note.id, 'aaa111')

    def test_pin(self):
        self.win.open_note('bbb222')
        self.win.toggle_pin()
        self.assertTrue(self.store.load('bbb222').pinned)
        self.assertEqual(self.win.rows[0].note.id, 'bbb222')

    def test_delete_and_undo(self):
        self.win.open_note('aaa111')
        self.win.delete_current()
        self.assertIsNone(self.store.load('aaa111'))
        self.win.undo_delete()
        self.assertIsNotNone(self.store.load('aaa111'))

    def test_task_toggle(self):
        self.win.open_note('bbb222')
        self.win.buffer.set_text("- [ ] one")
        self.win.buffer.place_cursor(self.win.buffer.get_start_iter())
        self.win.toggle_task()
        self.assertEqual(self.win._text(), "- [x] one")
        self.win.toggle_task()
        self.assertEqual(self.win._text(), "- [ ] one")

    def test_clipboard_button_calls_back(self):
        self.win.on_open_clipboard()
        self.assertEqual(self.opened, [1])

    def test_screenshot(self):
        from sparknotes.notes_window import NotesWindow
        self.win.destroy()
        self.store.save('aaa111', "# Shopping\n- [ ] milk\n- [x] eggs\n\nA **bold** word and `code`.\n")
        self.store.set_pinned('aaa111', True)
        self.win = NotesWindow(self.app, self.store, dict(core.DEFAULTS),
                               glitch=self.style.Glitch(False))
        self.win.paintable = Gtk.WidgetPaintable.new(self.win)
        self.win.present()
        settle(500)
        shot(self.win, 'spark-notes-notes.png')


@unittest.skipUnless(HAVE_GTK, 'needs a display and GTK 4')
class GlitchTest(Base):

    def test_burst_classes_come_and_go(self):
        glitch = self.style.Glitch(True)
        label = Gtk.Label(label='x')
        if not self.style.animations_on():
            glitch.now(label)
            self.assertFalse(label.has_css_class('burst'))
            return
        glitch.now(label)
        self.assertTrue(label.has_css_class('burst'))
        self.assertTrue(wait(lambda: not label.has_css_class('burst')
                             and not label.has_css_class('burst-2'), 2))

    def test_off_does_nothing(self):
        label = Gtk.Label(label='x')
        self.style.Glitch(False).now(label)
        self.assertFalse(label.has_css_class('burst'))


if __name__ == '__main__':
    unittest.main()
