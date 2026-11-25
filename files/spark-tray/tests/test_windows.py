"""The popups and question windows, opened once each on a display (CI runs this under Xvfb in
English and French; it is skipped when there is no display). The services are the mocked ones
from the other tests, so nothing real is asked or changed."""

import os
import unittest

import harness
from harness import AUDIO_FIXTURES, SPARK_AUDIO, pump

os.environ['SPARK_AUDIO_DIR'] = SPARK_AUDIO

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    DISPLAY = Gtk.init_check()[0] if hasattr(Gtk, 'init_check') else False
except Exception:                                     # noqa: BLE001 - no GTK, or no display
    DISPLAY = False

import test_tray   # noqa: E402

if DISPLAY:
    from sparktray import text, ui   # noqa: E402


def labels(widget):
    out = []
    if isinstance(widget, Gtk.Label):
        out.append(widget)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            out += labels(child)
    return out


def clipped(widget):
    """Labels that got less room than their text needs."""
    bad = []
    for lab in labels(widget):
        if not lab.get_mapped() or not lab.get_text():
            continue
        if lab.get_line_wrap() or lab.get_ellipsize() != 0:
            continue
        need = lab.get_preferred_width()[0]
        if lab.get_allocated_width() + 1 < need:
            bad.append((lab.get_text(), lab.get_allocated_width(), need))
    return bad


@unittest.skipUnless(DISPLAY, "needs a display")
class Windows(test_tray.TrayBase):
    def test_every_popup_opens_and_reads_in_the_language(self):
        self.services()
        tray = self.tray()
        for name in ('network', 'bluetooth', 'power', 'printers', 'volume'):
            item = tray.items[name]
            with self.subTest(item=name):
                item.toggle_popup(100, 100)
                pump(timeout=0.5)
                self.assertTrue(item.popup.get_visible())
                shown = [lab.get_text() for lab in labels(item.popup) if lab.get_text()]
                self.assertTrue(shown)
                for s in shown:
                    self.assertNotRegex(s, r'^[a-z]+\.[a-z_]+$', "a text key leaked")
                self.assertEqual(clipped(item.popup), [])
                item.toggle_popup(100, 100)
                self.assertFalse(item.popup.get_visible())

    def test_escape_closes_a_popup(self):
        self.services()
        tray = self.tray()
        item = tray.items['volume']
        item.toggle_popup(0, 0)
        pump(timeout=0.3)
        item.popup.hide()
        self.assertFalse(item.popup.get_visible())

    def test_password_window_answers_and_cancels(self):
        prompter = ui.Prompter()
        got = []
        prompter.ask_password('Home', got.append)
        pump(timeout=0.3)
        win = prompter.open[0]
        win.answer()                     # empty is not an answer
        self.assertEqual(got, [])
        win.entries['password'].set_text('hunter22')
        win.answer()
        self.assertEqual(got, ['hunter22'])
        self.assertEqual(prompter.open, [])
        prompter.ask_password('Home', got.append)
        pump(timeout=0.3)
        prompter.open[0].cancel()
        self.assertEqual(got, ['hunter22', None])

    def test_confirm_window_and_withdrawn_question(self):
        prompter = ui.Prompter()
        got = []
        close = prompter.confirm(text.t('pw.confirm_shutdown'), got.append, danger=True)
        pump(timeout=0.3)
        self.assertEqual(len(prompter.open), 1)
        self.assertEqual(clipped(prompter.open[0]), [])
        close()                          # BlueZ or NM withdrew it: no answer is sent
        pump(timeout=0.3)
        self.assertEqual(got, [])
        self.assertEqual(prompter.open, [])


if __name__ == '__main__':
    unittest.main()
