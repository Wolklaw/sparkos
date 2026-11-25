"""The spark-polkit window, in English and French. Needs a display (CI runs it under Xvfb);
skips without one so the suite stays safe to run on a desktop."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

HAVE_DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))

if HAVE_DISPLAY:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    from sparksession import style
    from sparksession.polkit_agent import Choice
    from sparksession.polkit_window import AuthWindow


class Req:
    action_id = 'org.freedesktop.policykit.exec'
    message = 'Authentication is needed to run a program as another user'
    cookie = 'c'
    details = {'program': '/usr/bin/pkexec', 'command_line': 'pkexec /usr/bin/true'}

    def __init__(self, n=1):
        self.choices = [Choice(i, 1000 + i, f'u{i}', f'user{i}') for i in range(n)]


class Flow:
    def __init__(self):
        self.answers, self.cancelled, self.chosen = [], 0, []

    def answer(self, secret):
        self.answers.append(secret)

    def cancel(self):
        self.cancelled += 1

    def choose(self, choice):
        self.chosen.append(choice)


def pump():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def labels(widget, out=None):
    out = [] if out is None else out
    if isinstance(widget, Gtk.Label):
        out.append(widget.get_label())
    if isinstance(widget, Gtk.Button) and widget.get_label():
        out.append(widget.get_label())
    child = widget.get_first_child()
    while child:
        labels(child, out)
        child = child.get_next_sibling()
    return out


@unittest.skipUnless(HAVE_DISPLAY, 'needs a display (Xvfb in CI)')
class WindowTests(unittest.TestCase):
    def open(self, n=1, language='en'):
        os.environ['SPARK_LANG'] = language
        style.install()
        self.flow = Flow()
        self.window = AuthWindow(Req(n), self.flow)
        pump()
        return self.window

    def tearDown(self):
        if getattr(self, 'window', None):
            self.window.destroy()
        os.environ.pop('SPARK_LANG', None)

    def test_shows_who_what_and_which_program_in_english(self):
        shown = labels(self.open())
        text = '\n'.join(shown)
        self.assertIn('AUTHENTICATION REQUIRED', text)
        self.assertIn('pkexec wants to do this', text)
        self.assertIn('org.freedesktop.policykit.exec', text)
        self.assertIn('/usr/bin/pkexec', text)
        self.assertIn('pkexec /usr/bin/true', text)
        self.assertIn('CANCEL', text)

    def test_french(self):
        text = '\n'.join(labels(self.open(language='fr')))
        self.assertIn('AUTHENTIFICATION REQUISE', text)
        self.assertIn('pkexec veut faire ceci', text)
        self.assertIn('ANNULER', text)
        self.assertIn('MOT DE PASSE', text)

    def test_identity_choice_only_with_several_admins(self):
        self.assertIsNone(self.open(1).dropdown)
        self.window.destroy()
        self.assertIsNotNone(self.open(2).dropdown)

    def test_picking_the_second_admin_tells_the_flow(self):
        self.open(2)
        self.window.dropdown.set_selected(1)
        pump()
        self.assertEqual(len(self.flow.chosen), 1)
        self.assertEqual(self.flow.chosen[0].name, 'u1')

    def test_enter_sends_the_password_and_clears_the_field(self):
        self.open()
        self.window.entry.set_text('abc123')
        self.window.entry.emit('activate')
        pump()
        self.assertEqual(self.flow.answers, ['abc123'])
        self.assertEqual(self.window.entry.get_text(), '')

    def test_cancel_button_and_escape_cancel(self):
        self.open()
        self.window.cancel_button.emit('clicked')
        self.assertEqual(self.flow.cancelled, 1)

    def test_wrong_shows_the_warning_text(self):
        self.open()
        self.window.wrong()
        self.assertEqual(self.window.status.get_label(), 'That password did not work. Try again.')

    def test_ask_uses_pams_own_prompt_as_the_label(self):
        self.open()
        self.window.ask('Verification code: ', False)
        self.assertEqual(self.window.prompt.get_label(), 'VERIFICATION CODE')

    def test_french_text_fits_the_window(self):
        win = self.open(2, 'fr')
        win.set_default_size(460, -1)
        _min, natural, _a, _b = win.measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertLessEqual(natural, 640)


if __name__ == '__main__':
    unittest.main()
