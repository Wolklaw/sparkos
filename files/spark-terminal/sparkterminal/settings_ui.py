"""The settings window: the profile (shell, starting folder, font, scrollback) and how the
terminal behaves. Saving applies the look to open tabs at once; the shell and folder are for
new tabs."""

from typing import Callable, Dict, Any, List

from gi.repository import Gtk, PangoCairo

from . import core
from .text import t


def mono_families() -> List[str]:
    """Installed monospace font families, the house ones first."""
    try:
        families = PangoCairo.FontMap.get_default().list_families()
        names = sorted({f.get_name() for f in families if f.is_monospace()}, key=str.lower)
    except Exception:                       # no font map without a display
        names = []
    preferred = [n for n in core.MONO_FAMILIES if n in names]
    return preferred + [n for n in names if n not in preferred]


class SettingsWindow(Gtk.Window):

    def __init__(self, parent: Gtk.Window, settings: Dict[str, Any],
                 on_save: Callable[[Dict[str, Any]], bool], glitch=None):
        super().__init__(title=t('set.title'), transient_for=parent, modal=True)
        self.add_css_class('spark-terminal-dialog')
        self.set_default_size(520, -1)
        self.settings = dict(settings)
        self.on_save = on_save

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(18)
        heading = Gtk.Label(label=t('set.title').upper(), xalign=0)
        heading.add_css_class('heading')
        box.append(heading)

        grid = Gtk.Grid(column_spacing=14, row_spacing=10)
        self.row = 0

        self.shell = Gtk.Entry(text=settings['shell'], hexpand=True,
                               placeholder_text=core.login_shell())
        self._add(grid, t('set.shell'), self.shell, t('set.shell_hint', shell=core.login_shell()))
        self.start_dir = Gtk.Entry(text=settings['start_dir'], hexpand=True,
                                   placeholder_text='~')
        self._add(grid, t('set.start_dir'), self.start_dir, t('set.start_dir_hint'))

        fonts = mono_families() or [settings['font']]
        if settings['font'] not in fonts:
            fonts.insert(0, settings['font'])
        self.font_names = fonts
        self.font = Gtk.DropDown.new_from_strings(fonts)
        self.font.set_selected(fonts.index(settings['font']))
        self._add(grid, t('set.font'), self.font)

        self.font_size = Gtk.SpinButton.new_with_range(*core.FONT_SIZE_RANGE, 1)
        self.font_size.set_value(settings['font_size'])
        self._add(grid, t('set.font_size'), self.font_size)
        self.scrollback = Gtk.SpinButton.new_with_range(*core.SCROLLBACK_RANGE, 1000)
        self.scrollback.set_value(settings['scrollback'])
        self._add(grid, t('set.scrollback'), self.scrollback)

        self.cursor = Gtk.DropDown.new_from_strings([t(f'set.cursor.{c}') for c in core.CURSORS])
        self.cursor.set_selected(core.CURSORS.index(settings['cursor']))
        self._add(grid, t('set.cursor'), self.cursor)
        self.bell = Gtk.DropDown.new_from_strings([t(f'set.bell.{b}') for b in core.BELLS])
        self.bell.set_selected(core.BELLS.index(settings['bell']))
        self._add(grid, t('set.bell'), self.bell)

        self.switches = {}
        for key in ('copy_on_select', 'confirm_close', 'cursor_blink', 'glitch'):
            switch = Gtk.Switch(active=settings[key], halign=Gtk.Align.START,
                                valign=Gtk.Align.CENTER)
            self.switches[key] = switch
            self._add(grid, t(f'set.{key}'), switch)
        box.append(grid)

        self.message = Gtk.Label(xalign=0, wrap=True)
        self.message.add_css_class('hint')
        box.append(self.message)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=t('button.cancel'))
        cancel.add_css_class('spark')
        cancel.connect('clicked', lambda _b: self.close())
        done = Gtk.Button(label=t('button.done'))
        done.add_css_class('spark')
        done.add_css_class('primary')
        done.connect('clicked', lambda _b: self.save())
        buttons.append(cancel)
        buttons.append(done)
        box.append(buttons)
        self.set_child(box)
        self.glitch = glitch
        self.heading = heading

    def _add(self, grid: Gtk.Grid, label: str, widget: Gtk.Widget, hint: str = '') -> None:
        name = Gtk.Label(label=label.upper(), xalign=0, valign=Gtk.Align.CENTER)
        name.add_css_class('micro')
        grid.attach(name, 0, self.row, 1, 1)
        grid.attach(widget, 1, self.row, 1, 1)
        self.row += 1
        if hint:
            note = Gtk.Label(label=hint, xalign=0, wrap=True)
            note.add_css_class('hint')
            grid.attach(note, 1, self.row, 1, 1)
            self.row += 1

    def collect(self) -> Dict[str, Any]:
        data = dict(self.settings)
        data['shell'] = self.shell.get_text().strip()
        data['start_dir'] = self.start_dir.get_text().strip()
        data['font'] = self.font_names[self.font.get_selected()]
        data['font_size'] = int(self.font_size.get_value())
        data['scrollback'] = int(self.scrollback.get_value())
        data['cursor'] = core.CURSORS[self.cursor.get_selected()]
        data['bell'] = core.BELLS[self.bell.get_selected()]
        for key, switch in self.switches.items():
            data[key] = switch.get_active()
        return core.clean_settings(data)

    def save(self) -> None:
        data = self.collect()
        problems = core.check_settings(data)
        if problems:
            key, value = problems[0]
            self.message.set_label(t('set.bad_shell', shell=value) if key == 'shell'
                                   else t('set.bad_dir', path=value))
            self.message.add_css_class('error')
            if self.glitch is not None:
                self.glitch.now(self.message)
            return
        self.on_save(data)
        self.close()
