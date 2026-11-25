"""The password window of spark-polkit (GTK4, house style). It shows who is asking, the action id
and the program, an identity choice when polkit offers several admins, a password field and
Cancel. It implements the ui side of polkit_agent.AuthFlow."""

import os

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import style  # noqa: E402
from .polkit_agent import program_of  # noqa: E402
from .strings import t  # noqa: E402


def _micro(text):
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class('micro')
    return label


def _fact(text):
    label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=60)
    label.add_css_class('fact')
    return label


class AuthWindow(Gtk.Window):
    def __init__(self, request, flow):
        super().__init__()
        self.request, self.flow = request, flow
        self.add_css_class('spark-sec')
        self.set_title(t('auth.title'))
        self.set_default_size(460, -1)
        self.set_resizable(False)
        self.set_deletable(True)
        program, command = program_of(request.details)
        who = os.path.basename(program) if program else t('auth.unknown_program')

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(20)
        box.add_css_class('panel')
        self.set_child(box)

        heading = Gtk.Label(label=t('auth.title'), xalign=0)
        heading.add_css_class('heading')
        box.append(heading)
        self.heading = heading
        asking = Gtk.Label(label=t('auth.asking', who=who), xalign=0, wrap=True)
        asking.add_css_class('micro')
        box.append(asking)
        message = Gtk.Label(label=request.message or t('auth.no_message'), xalign=0, wrap=True)
        message.add_css_class('message')
        message.set_margin_top(6)
        message.set_margin_bottom(6)
        box.append(message)

        box.append(_micro(t('auth.action')))
        box.append(_fact(request.action_id))
        if program:
            box.append(_micro(t('auth.program')))
            box.append(_fact(program))
        if command and command != program:
            box.append(_micro(t('auth.command')))
            box.append(_fact(command))

        self.dropdown = None
        if len(request.choices) > 1:
            box.append(_micro(t('auth.as')))
            self.dropdown = Gtk.DropDown.new_from_strings([c.label for c in request.choices])
            self.dropdown.connect('notify::selected', self._picked)
            box.append(self.dropdown)

        self.prompt = _micro(t('auth.password').upper())
        box.append(self.prompt)
        self.entry = Gtk.PasswordEntry()
        self.entry.set_show_peek_icon(False)
        self.entry.set_property('activates-default', False)
        self.entry.connect('activate', self._submit)
        box.append(self.entry)

        self.status = Gtk.Label(label='', xalign=0, wrap=True)
        self.status.add_css_class('status')
        box.append(self.status)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.cancel_button = Gtk.Button(label=t('auth.cancel'))
        self.cancel_button.connect('clicked', lambda *_: self.flow.cancel())
        self.ok_button = Gtk.Button(label=t('auth.ok'))
        self.ok_button.add_css_class('primary')
        self.ok_button.connect('clicked', self._submit)
        buttons.append(self.cancel_button)
        buttons.append(self.ok_button)
        box.append(buttons)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        self.add_controller(keys)
        self.connect('close-request', self._closing)
        self.present()
        self.entry.grab_focus()
        GLib.idle_add(lambda: style.glitch(self.heading) or False)

    # --- what AuthFlow calls ---
    def ask(self, prompt, echo):
        """PAM's prompt, normally "Password:". Shown as the field's label when it is not that."""
        text = (prompt or '').strip().rstrip(':').strip()
        self.prompt.set_label((text or t('auth.password')).upper())
        self.entry.set_sensitive(True)
        self.ok_button.set_sensitive(True)
        self.entry.grab_focus()

    def info(self, text):
        self._status(text, '')

    def error(self, text):
        self._status(text, 'warn')
        style.glitch(self.status)

    def wrong(self):
        self._status(t('auth.wrong'), 'warn')
        style.glitch(self.heading, self.status)

    def checking(self):
        self.entry.set_sensitive(False)
        self.ok_button.set_sensitive(False)
        self._status(t('auth.checking'), '')

    def choices_changed(self):
        pass

    def close(self):
        self.entry.set_text('')
        self.destroy()

    # --- the window's own events ---
    def _status(self, text, kind):
        self.status.set_label(text)
        for name in ('warn', 'ok'):
            self.status.remove_css_class(name)
        if kind:
            self.status.add_css_class(kind)

    def _submit(self, *_):
        secret = self.entry.get_text()
        self.entry.set_text('')                       # gone from the widget before it is sent
        self.flow.answer(secret)

    def _picked(self, dropdown, _param):
        index = dropdown.get_selected()
        if 0 <= index < len(self.request.choices):
            self.entry.set_text('')
            self._status('', '')
            self.flow.choose(self.request.choices[index])

    def _key(self, _controller, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.flow.cancel()
            return True
        return False

    def _closing(self, *_):
        self.flow.cancel()
        return False
