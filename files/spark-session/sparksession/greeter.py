"""spark-greeter: the sign-in screen for greetd (GTK4, house style).

greetd starts this inside a compositor (spark-greeter-session runs kwin_wayland for it), as the
`greetd` user, with GREETD_SOCK set. The screen has a clock, the users, a session picker (Spark,
Plasma), the password field and sleep, restart and shut down. It talks greetd's IPC from a worker
thread so a slow PAM stack (the failure delay) never freezes the window."""

import logging
import os
import queue
import subprocess
import sys
import threading
import time

from . import greetd
from .greeter_data import Memory, list_sessions, list_users
from .strings import t

log = logging.getLogger('spark-greeter')


def run_power(action):
    """systemctl poweroff|reboot|suspend. The greetd user is allowed these by the polkit rule
    that ships with the greeter. Returns True when systemctl accepted it."""
    try:
        return subprocess.run(['systemctl', action], timeout=20, capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class LoginWorker:
    """One sign-in attempt on its own thread. ui is called back through `post`
    (GLib.idle_add in the real greeter, a direct call in tests)."""

    def __init__(self, client_factory, post, ui):
        self.client_factory, self.post, self.ui = client_factory, post, ui
        self.answers = queue.Queue()

    def start(self, username, secret, session):
        threading.Thread(target=self._run, args=(username, secret, session), daemon=True).start()

    def reply(self, text):
        self.answers.put(text)

    def abort(self):
        self.answers.put(None)

    def _answer(self, kind, text, state):
        if kind in ('info', 'error'):
            self.post(self.ui.message, kind, text)
            return None
        if state['first'] is not None:
            secret, state['first'] = state['first'], None
            return secret
        self.post(self.ui.prompt, text, kind == 'visible')
        reply = self.answers.get()
        if reply is None:
            raise greetd.GreetdError('error', 'cancelled')
        return reply

    def _run(self, username, secret, session):
        state = {'first': secret}
        try:
            client = self.client_factory()
        except (OSError, greetd.GreetdError):
            self.post(self.ui.failed, 'no_daemon', '')
            return
        try:
            greetd.login(client, username, lambda kind, text: self._answer(kind, text, state),
                         session.cmd, session.env)
        except greetd.GreetdError as exc:
            if exc.kind == 'auth_error':
                self.post(self.ui.failed, 'wrong', '')
            elif exc.description == 'cancelled':
                self.post(self.ui.failed, 'cancelled', '')
            else:
                self.post(self.ui.failed, 'error', exc.description)
            return
        except OSError:
            self.post(self.ui.failed, 'no_daemon', '')
            return
        finally:
            state['first'] = None
            client.close()
        self.post(self.ui.succeeded, username, session)


def build_window(client_factory=None, users=None, sessions=None, memory=None, power=run_power,
                 fullscreen=True, on_done=None):
    """The window. Imported lazily so the module's logic loads without GTK."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk

    from . import style

    client_factory = client_factory or greetd.Client
    users = list_users() if users is None else users
    sessions = list_sessions() if sessions is None else sessions
    memory = memory or Memory()

    class Window(Gtk.Window):
        def __init__(self):
            super().__init__()
            self.add_css_class('spark-sec')
            self.set_title('Spark')
            self.users, self.sessions = users, sessions
            self.other = not users
            self.worker = None
            self.busy = False

            outer = Gtk.Overlay()
            self.set_child(outer)
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                             halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            outer.set_child(column)

            self.clock = Gtk.Label(label='')
            self.clock.add_css_class('big')
            column.append(self.clock)
            self.date = Gtk.Label(label='')
            self.date.add_css_class('micro')
            column.append(self.date)

            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            panel.add_css_class('panel')
            panel.set_size_request(380, -1)
            column.append(panel)
            self.panel = panel

            self.heading = Gtk.Label(label=t('greet.title'), xalign=0)
            self.heading.add_css_class('heading')
            panel.append(self.heading)

            self.user_label = _micro(t('greet.user'))
            panel.append(self.user_label)
            self.user_drop = Gtk.DropDown.new_from_strings(
                [u.label for u in users] + [t('greet.other')])
            self.user_drop.connect('notify::selected', self._user_changed)
            panel.append(self.user_drop)
            self.name_entry = Gtk.Entry(placeholder_text=t('greet.name'))
            self.name_entry.connect('activate', lambda *_: self.password.grab_focus())
            panel.append(self.name_entry)

            panel.append(_micro(t('greet.session')))
            self.session_drop = Gtk.DropDown.new_from_strings([s.name for s in sessions] or ['-'])
            panel.append(self.session_drop)

            self.prompt_label = _micro(t('greet.password').upper())
            panel.append(self.prompt_label)
            self.password = Gtk.PasswordEntry()
            self.password.set_show_peek_icon(False)
            self.password.connect('activate', self._submit)
            panel.append(self.password)

            self.status = Gtk.Label(label='', xalign=0, wrap=True)
            self.status.add_css_class('status')
            panel.append(self.status)

            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            self.back_button = Gtk.Button(label=t('greet.back'))
            self.back_button.connect('clicked', self._back)
            self.back_button.set_visible(False)
            self.go = Gtk.Button(label=t('greet.sign_in'))
            self.go.add_css_class('primary')
            self.go.connect('clicked', self._submit)
            buttons.append(self.back_button)
            buttons.append(self.go)
            panel.append(buttons)

            power_row = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.END,
                                margin_end=20, margin_bottom=20)
            self.power_buttons = {}
            for action, key in (('suspend', 'greet.suspend'), ('reboot', 'greet.reboot'),
                                ('poweroff', 'greet.poweroff')):
                button = Gtk.Button(label=t(key))
                if action == 'poweroff':
                    button.add_css_class('danger')
                button.connect('clicked', self._power, action, key)
                power_row.append(button)
                self.power_buttons[action] = button
            outer.add_overlay(power_row)
            power_row.set_halign(Gtk.Align.END)
            power_row.set_valign(Gtk.Align.END)

            self._remembered()
            self._tick()
            GLib.timeout_add_seconds(20, self._tick)
            if fullscreen:
                self.fullscreen()
            self.present()
            self._focus()
            GLib.idle_add(lambda: style.glitch(self.heading) or False)

        # --- what the screen starts with ---
        def _remembered(self):
            names = [u.name for u in self.users]
            last = memory.last_user()
            index = names.index(last) if last in names else 0
            self.user_drop.set_selected(index if names else 0)
            self._user_changed()

        def _tick(self):
            now = time.localtime()
            self.clock.set_label(time.strftime('%H:%M', now))
            self.date.set_label(time.strftime('%A %-d %B %Y', now).upper())
            return True

        def _focus(self):
            (self.name_entry if self._is_other() else self.password).grab_focus()

        def _is_other(self):
            return not self.users or self.user_drop.get_selected() >= len(self.users)

        def _username(self):
            if self._is_other():
                return self.name_entry.get_text().strip()
            return self.users[self.user_drop.get_selected()].name

        def _user_changed(self, *_):
            other = self._is_other()
            self.name_entry.set_visible(other)
            if not other:
                ident = memory.last_session(self._username())
                for i, session in enumerate(self.sessions):
                    if session.ident == ident:
                        self.session_drop.set_selected(i)
                        break
            self._set_status('', '')
            self._focus()

        # --- signing in ---
        def _submit(self, *_):
            if self.busy:
                if self.worker:
                    self.worker.reply(self.password.get_text())
                    self.password.set_text('')
                    self._set_status(t('greet.waiting'), '')
                return
            username = self._username()
            if not username or not self.sessions:
                return
            secret = self.password.get_text()
            self.password.set_text('')              # out of the widget before it is sent
            self.busy = True
            self._lock(True)
            self._set_status(t('greet.waiting'), '')
            session = self.sessions[self.session_drop.get_selected()]
            self.worker = LoginWorker(client_factory, _post, self)
            self.worker.start(username, secret, session)

        def _back(self, *_):
            if self.worker:
                self.worker.abort()
            self._reset()

        def _lock(self, locked):
            for widget in (self.user_drop, self.name_entry, self.session_drop, self.go):
                widget.set_sensitive(not locked)

        def _reset(self):
            self.busy = False
            self.worker = None
            self._lock(False)
            self.back_button.set_visible(False)
            self.prompt_label.set_label(t('greet.password').upper())
            self.password.set_text('')
            self._focus()

        # --- worker callbacks (run on the main loop) ---
        def message(self, kind, text):
            self._set_status(text, 'warn' if kind == 'error' else '')

        def prompt(self, text, visible):
            label = (text or '').strip().rstrip(':').strip() or t('greet.password')
            self.prompt_label.set_label(label.upper())
            self.back_button.set_visible(True)
            self.go.set_sensitive(True)
            self.password.grab_focus()
            self._set_status('', '')

        def failed(self, why, detail):
            if why == 'wrong':
                self._set_status(t('greet.wrong'), 'warn')
            elif why == 'no_daemon':
                self._set_status(t('greet.no_daemon'), 'warn')
            elif why == 'cancelled':
                self._set_status('', '')
            else:
                self._set_status(t('greet.failed', why=detail), 'warn')
            style.glitch(self.heading, self.status)
            self._reset()

        def succeeded(self, username, session):
            memory.remember(username, session.ident)
            self.password.set_text('')
            if on_done:
                on_done()

        def _power(self, _button, action, key):
            if not power(action):
                self._set_status(t('greet.power_failed', what=t(key).lower()), 'warn')
                style.glitch(self.status)

        def _set_status(self, text, kind):
            self.status.set_label(text)
            for name in ('warn', 'ok'):
                self.status.remove_css_class(name)
            if kind:
                self.status.add_css_class(kind)

    def _post(fn, *args):
        def run():
            fn(*args)
            return False
        GLib.idle_add(run)

    return Window()


def _micro(text):
    from gi.repository import Gtk
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class('micro')
    return label


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format='spark-greeter: %(message)s', stream=sys.stderr)
    if '--version' in argv:
        from . import VERSION
        print(f'spark-greeter {VERSION}')
        return 0
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    from . import style
    if not Gtk.init_check():
        print('spark-greeter: no display', file=sys.stderr)
        return 1
    if not os.environ.get('GREETD_SOCK'):
        print('spark-greeter: GREETD_SOCK is not set; greetd starts this program', file=sys.stderr)
        return 1
    style.install()
    loop = GLib.MainLoop()
    window = build_window(fullscreen='SPARK_GREETER_WINDOWED' not in os.environ,
                          on_done=lambda: GLib.timeout_add(300, loop.quit))
    window.connect('close-request', lambda *_: loop.quit())
    loop.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
