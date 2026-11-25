"""The launcher: a full-screen scrim with a centred card. Search, sums, pinned and all apps, and
the power row. The ranking and the sum rules are launcher_logic.py, shared with the Plasma
applet."""

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import apps, layer  # noqa: E402
from .ending import SessionEnd  # noqa: E402
from .lang import ui_language  # noqa: E402
from .strings import tr  # noqa: E402

try:
    import launcher_logic as logic
except ImportError:                      # running from the source tree
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'spark-launcher'))
    import launcher_logic as logic       # noqa: E402

POWER = (
    ('lock', ['loginctl', 'lock-session'], False),
    ('sleep', ['systemctl', 'suspend'], False),
    ('sign_out', ['loginctl', 'terminate-session', ''], True),
    ('restart', ['systemctl', 'reboot'], True),
    ('shut_down', ['systemctl', 'poweroff'], True),
)


class Launcher(Gtk.Window):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.ending = SessionEnd(shell.tracker, apps.run, self._still_open)
        self._forcing = None
        self.set_decorated(False)
        self.add_css_class('spark-scrim')
        layer.setup(self, 'overlay', ('top', 'bottom', 'left', 'right'), 'spark-launcher',
                    exclusive=-1, keyboard='exclusive')
        self.set_default_size(1280, 800)
        self.french = ui_language() == 'fr'
        self.answer = ''
        self._sum_token = 0

        outer = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.set_child(outer)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class('spark-launcher')
        card.set_size_request(640, -1)
        outer.append(card)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(inner, 'set_margin_' + side)(14)
        card.append(inner)

        self.entry = Gtk.SearchEntry(placeholder_text=tr('search'))
        self.entry.connect('search-changed', self._changed)
        self.entry.connect('activate', self._enter)
        inner.append(self.entry)

        self.answer_label = Gtk.Label(xalign=0, visible=False)
        self.answer_label.add_css_class('spark-answer')
        inner.append(self.answer_label)
        self.hint = Gtk.Label(label=tr('sum_hint'), xalign=0, visible=False)
        self.hint.add_css_class('spark-dim')
        inner.append(self.hint)

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True)
        self.list.connect('row-activated', lambda _l, row: self._start(row.info))
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=460,
                                    min_content_height=120)
        scroll.set_child(self.list)
        inner.append(scroll)
        self.nothing = Gtk.Label(xalign=0, visible=False)
        self.nothing.add_css_class('spark-dim')
        inner.append(self.nothing)

        inner.append(Gtk.Separator())
        self.power_row = Gtk.Box(spacing=6)
        inner.append(self.power_row)
        self.confirm = Gtk.Label(xalign=0, visible=False, wrap=True)
        self.confirm.add_css_class('spark-text')
        inner.append(self.confirm)
        self._build_power()
        find = Gtk.Button(label=tr('find_more'))
        find.add_css_class('spark-btn')
        find.connect('clicked', lambda *_: (apps.run(['spark-store']), self.hide_launcher()))
        spacer = Gtk.Box(hexpand=True)
        self.power_row.append(spacer)
        self.power_row.append(find)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        self.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect('pressed', self._outside, card)
        self.add_controller(click)

    # showing ------------------------------------------------------------------------------
    def show_launcher(self):
        self._confirming = None
        self.shell.catalog.reload()
        self.entry.set_text('')
        self.confirm.set_visible(False)
        self._fill_default()
        self.present()
        self.entry.grab_focus()

    def hide_launcher(self):
        self.set_visible(False)

    def toggle(self):
        if self.get_visible():
            self.hide_launcher()
        else:
            self.show_launcher()

    def _outside(self, gesture, n, x, y, card):
        ok, rect = card.compute_bounds(self)
        if ok and rect.get_x() <= x <= rect.get_x() + rect.get_width() and \
                rect.get_y() <= y <= rect.get_y() + rect.get_height():
            return
        self.hide_launcher()

    def _key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.hide_launcher()
            return True
        if keyval == Gdk.KEY_Down and self.entry.has_focus():
            row = self.list.get_row_at_index(0)
            if row:
                row.grab_focus()
                return True
        return False

    # list ---------------------------------------------------------------------------------
    def _row(self, info):
        row = Gtk.ListBoxRow()
        row.info = info
        box = Gtk.Box(spacing=10)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(6)
        icon = info.get_icon()
        image = Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name(
            'application-x-executable')
        image.set_pixel_size(28)
        box.append(image)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(label=info.get_name() or '', xalign=0)
        name.add_css_class('spark-text')
        text.append(name)
        desc = info.get_generic_name() or info.get_description() or ''
        if desc:
            d = Gtk.Label(label=desc, xalign=0, ellipsize=3)
            d.add_css_class('spark-dim')
            text.append(d)
        box.append(text)
        row.set_child(box)
        return row

    def _set_rows(self, infos, heading=None):
        while True:
            row = self.list.get_row_at_index(0)
            if row is None:
                break
            self.list.remove(row)
        for info in infos:
            self.list.append(self._row(info))
        first = self.list.get_row_at_index(0)
        if first:
            self.list.select_row(first)

    def _fill_default(self):
        catalog = self.shell.catalog
        pinned = [catalog.find(p) for p in self.shell.config['pinned']]
        pinned = [p for p in pinned if p is not None]
        seen = {p.get_id() for p in pinned}
        rest = [a for a in catalog.apps if a.get_id() not in seen]
        self._set_rows(pinned + rest)
        self.answer_label.set_visible(False)
        self.hint.set_visible(False)
        self.nothing.set_visible(False)

    def _changed(self, entry):
        text = entry.get_text()
        if not text.strip():
            self._fill_default()
            return
        entries = self.shell.catalog.entries()
        hits = logic.filter_apps(entries, text)
        self._set_rows([h['info'] for h in hits])
        sum_text = logic.sum_from(text, self.french)
        self.answer = ''
        self.answer_label.set_visible(False)
        self.hint.set_visible(False)
        if sum_text and logic.sum_command(sum_text):
            self._ask(sum_text)
        self.nothing.set_visible(not hits and not sum_text)
        self.nothing.set_text(tr('nothing') % text)

    def _ask(self, sum_text):
        self._sum_token += 1
        token = self._sum_token
        try:
            proc = Gio.Subprocess.new(['timeout', '2', 'spark-calc', '--eval', sum_text],
                                      Gio.SubprocessFlags.STDOUT_PIPE |
                                      Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error:
            return

        def done(p, res):
            try:
                ok, out, _err = p.communicate_utf8_finish(res)
            except GLib.Error:
                return
            if token != self._sum_token or not ok or p.get_exit_status() != 0:
                return
            self.answer = out.strip()
            if self.answer:
                self.answer_label.set_text('= ' + logic.show_answer(self.answer, self.french))
                self.answer_label.set_visible(True)
                self.hint.set_visible(True)
        proc.communicate_utf8_async(None, None, done)

    def _enter(self, entry):
        if self.answer:
            self.get_clipboard().set(logic.show_answer(self.answer, self.french))
            self.hint.set_text(tr('copied'))
            return
        row = self.list.get_selected_row() or self.list.get_row_at_index(0)
        if row:
            self._start(row.info)

    def _start(self, info):
        self.hide_launcher()
        apps.launch(info, self.get_display())

    # power --------------------------------------------------------------------------------
    def _build_power(self):
        for key, command, ask in POWER:
            button = Gtk.Button(label=tr(key))
            button.add_css_class('spark-btn')
            if ask:
                button.add_css_class('spark-danger')
            button.connect('clicked', self._power, key, command, ask)
            self.power_row.append(button)

    def _power(self, _button, key, command, ask):
        if ask and not getattr(self, '_confirming', None) == key:
            self._confirming = key
            self.confirm.set_text(tr('confirm_' + key) + '  (' + tr(key) + ')')
            self.confirm.set_visible(True)
            return
        self._confirming = None
        self.confirm.set_visible(False)
        self.hide_launcher()
        if key == 'sign_out':
            import os
            command = ['loginctl', 'terminate-session', os.environ.get('XDG_SESSION_ID', '')]
        if not ask:
            apps.run(command)
            return
        # open apps are asked to close first; a second click after "still open" goes anyway
        force, self._forcing = self._forcing == key, None
        self.ending.start(command, force=force, label=key)

    def _still_open(self, _command, titles, key):
        self.show_launcher()
        shown = ', '.join(titles[:4]) + (' …' if len(titles) > 4 else '')
        self.confirm.set_text(tr('still_open') % shown + '  (' + tr(key) + ')')
        self.confirm.set_visible(True)
        self._confirming = key
        self._forcing = key
