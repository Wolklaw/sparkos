"""The house style in GTK 3: dark teal-black panels, mono type, sharp 3 px corners, UPPERCASE
micro-labels, a mint accent, and one fault, the magenta and cyan channels slipping out of
register, on hover and focus, and as a short tear when something happens or fails.

Popup is the small window each tray icon opens. Prompter shows the questions the agents ask
(a Wi-Fi password, a pairing number) and the "are you sure" boxes."""

from typing import Callable, Dict, List, Optional, Tuple

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk   # noqa: E402

from .text import t   # noqa: E402

try:                                       # optional: where Wayland puts a popup (no x, y there)
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import GtkLayerShell
except (ImportError, ValueError):
    GtkLayerShell = None

CSS = """
.spark-popup { background-color: #04090b; color: #d4f1ec; border: 1px solid #1f6a66;
  border-radius: 3px; font-family: "Cascadia Mono", "Cascadia Code", "JetBrains Mono",
  "DejaVu Sans Mono", monospace; font-size: 10pt; }
.spark-popup label { color: #d4f1ec; }
.spark-popup .muted { color: #6f9f98; }
.spark-popup .micro { color: #6f9f98; font-weight: bold; font-size: 8pt; letter-spacing: 1px; }
.spark-popup .title { color: #d4f1ec; font-weight: bold; font-size: 11pt; letter-spacing: 1px;
  text-shadow: 2px 0 #ff2e88, -2px 0 #22d8ff; }
.spark-popup .ok { color: #3de8c8; }
.spark-popup .bad { color: #ff4d8d; }
.spark-popup .panel { background-color: #0a1517; border: 1px solid #143a3d; border-radius: 3px; }
.spark-popup .row { background-color: #0a1517; border: 1px solid #143a3d; border-radius: 3px;
  padding: 4px 8px; margin: 1px 0; }
.spark-popup .row:hover { background-color: #12292c; }
.spark-popup .row.active { border-color: #3de8c8; }
.spark-popup button { background-image: none; background-color: #0e1f22; color: #d4f1ec;
  border: 1px solid #1f6a66; border-radius: 3px; padding: 3px 10px; box-shadow: none;
  text-shadow: none; font-weight: bold; }
.spark-popup button:hover, .spark-popup button:focus { background-color: #12292c;
  box-shadow: 3px 0 0 #ff2e88, -3px 0 0 #22d8ff; }
.spark-popup button.primary { background-color: #3de8c8; color: #02130f; border-color: #3de8c8; }
.spark-popup button.primary label { color: #02130f; }
.spark-popup button.danger { color: #ff4d8d; border-color: #ff4d8d; }
.spark-popup button.danger label { color: #ff4d8d; }
.spark-popup button:disabled { color: #3b6460; border-color: #143a3d; box-shadow: none; }
.spark-popup entry { background-color: #0a1517; color: #d4f1ec; border: 1px solid #1f6a66;
  border-radius: 3px; padding: 3px 6px; box-shadow: none; }
.spark-popup entry:focus { border-color: #3de8c8; }
.spark-popup scale trough { background-color: #143a3d; min-height: 4px; border-radius: 0; }
.spark-popup scale highlight { background-color: #3de8c8; border-radius: 0; }
.spark-popup scale slider { background-color: #d4f1ec; min-width: 10px; min-height: 14px;
  border-radius: 2px; border: none; }
.spark-popup switch { background-color: #143a3d; border: 1px solid #1f6a66; border-radius: 3px; }
.spark-popup switch:checked { background-color: #3de8c8; }
.spark-popup switch slider { background-color: #d4f1ec; border-radius: 2px; }
.spark-popup separator { background-color: #143a3d; min-height: 1px; }
.spark-popup .glitch { text-shadow: 3px 0 #ff2e88, -3px 0 #22d8ff;
  box-shadow: 3px 0 0 #ff2e88, -3px 0 0 #22d8ff; }
"""

_css_ready = False


def apply_css() -> None:
    global _css_ready
    if _css_ready:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_ready = True


def glitch(widget: Gtk.Widget, millis: int = 450) -> None:
    """The channels slip for a moment: on an error, or a change worth noticing."""
    ctx = widget.get_style_context()
    ctx.add_class('glitch')
    GLib.timeout_add(millis, lambda: (ctx.remove_class('glitch'), False)[1])


def label(text: str, *classes: str, wrap: bool = False, xalign: float = 0.0) -> Gtk.Label:
    w = Gtk.Label(label=text, xalign=xalign)
    for c in classes:
        w.get_style_context().add_class(c)
    if wrap:
        w.set_line_wrap(True)
        w.set_max_width_chars(44)
    return w


def micro(text: str) -> Gtk.Label:
    return label(text.upper(), 'micro')


def button(text: str, callback: Callable[[], None], kind: str = '') -> Gtk.Button:
    b = Gtk.Button(label=text)
    if kind:
        b.get_style_context().add_class(kind)
    b.connect('clicked', lambda _b: callback())
    return b


def switch(on: bool, callback: Callable[[bool], None]) -> Gtk.Switch:
    s = Gtk.Switch(active=on, valign=Gtk.Align.CENTER)
    s.connect('state-set', lambda _s, state: (callback(state), False)[1])
    return s


def hbox(spacing: int = 8) -> Gtk.Box:
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def vbox(spacing: int = 6) -> Gtk.Box:
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def row_box(active: bool = False) -> Gtk.Box:
    box = hbox(8)
    ctx = box.get_style_context()
    ctx.add_class('row')
    if active:
        ctx.add_class('active')
    return box


def signal_bars(strength: int) -> str:
    """0-100 as four bars, drawn with block characters."""
    n = 0 if strength < 10 else 1 if strength < 35 else 2 if strength < 60 else 3 if strength < 80 \
        else 4
    return '▂▄▆█'[:n].ljust(4, '·') if n else '····'


def clear(container: Gtk.Container) -> None:
    for child in container.get_children():
        container.remove(child)


class Popup(Gtk.Window):
    """A small undecorated window a tray icon opens. It closes on Escape, on losing focus,
    and when its icon is clicked again."""

    def __init__(self, title: str, corner: str = 'bottom-right'):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        apply_css()
        self.corner = corner
        self.set_title(title)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_default_size(340, -1)
        self.get_style_context().add_class('spark-popup')
        self.body = vbox(8)
        self.body.set_border_width(12)
        self.add(self.body)
        self.auto_hide = True
        self.connect('key-press-event', self._key)
        self.connect('focus-out-event', self._focus_out)
        self.connect('delete-event', lambda *_: (self.hide(), True)[1])
        self._layer = False

    def _key(self, _w, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _focus_out(self, *_args) -> bool:
        if self.auto_hide and self.get_visible():
            GLib.idle_add(self._hide_if_unfocused)
        return False

    def _hide_if_unfocused(self) -> bool:
        if self.get_visible() and not self.is_active() and self.auto_hide:
            self.hide()
        return False

    def toggle(self, x: int = 0, y: int = 0) -> None:
        if self.get_visible():
            self.hide()
        else:
            self.open_at(x, y)

    def open_at(self, x: int = 0, y: int = 0) -> None:
        self.show_all()
        display = Gdk.Display.get_default()
        on_wayland = 'Wayland' in type(display).__name__
        if on_wayland and GtkLayerShell is not None and GtkLayerShell.is_supported():
            self._layer_place()
        elif not on_wayland and (x or y):
            self.show_all()
            w, h = self.get_size()
            mon = display.get_monitor_at_point(x, y).get_workarea()
            px = min(max(mon.x, x - w // 2), mon.x + mon.width - w)
            py = y - h - 8 if y > mon.y + mon.height // 2 else y + 8
            self.move(px, min(max(mon.y, py), mon.y + mon.height - h))
        self.present()

    def _layer_place(self) -> None:
        if not self._layer:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
            vert = GtkLayerShell.Edge.TOP if 'top' in self.corner else GtkLayerShell.Edge.BOTTOM
            horiz = GtkLayerShell.Edge.LEFT if 'left' in self.corner else GtkLayerShell.Edge.RIGHT
            for edge in (vert, horiz):
                GtkLayerShell.set_anchor(self, edge, True)
                GtkLayerShell.set_margin(self, edge, 8)
            self._layer = True


class Ask(Gtk.Window):
    """A question window: text, optional entry fields, OK and Cancel. answer(values) and
    cancel() are what the buttons do, so tests can press them."""

    def __init__(self, title: str, text: str, fields: List[Tuple[str, str, bool]],
                 done: Callable[[Optional[Dict[str, str]]], None], yes_no: bool = False,
                 danger: bool = False, ok_label: str = ''):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        apply_css()
        self.done_cb, self.finished = done, False
        self.set_title(title)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class('spark-popup')
        box = vbox(10)
        box.set_border_width(14)
        self.add(box)
        box.pack_start(label(title.upper() if not text else title, 'title', wrap=True), False,
                       False, 0)
        if text:
            box.pack_start(label(text, wrap=True), False, False, 0)
        self.entries: Dict[str, Gtk.Entry] = {}
        for key, name, secret in fields:
            box.pack_start(micro(name), False, False, 0)
            entry = Gtk.Entry(visibility=not secret, activates_default=True)
            entry.connect('activate', lambda _e: self.answer())
            self.entries[key] = entry
            box.pack_start(entry, False, False, 0)
        buttons = hbox(8)
        buttons.set_halign(Gtk.Align.END)
        buttons.pack_start(button(t('common.cancel'), self.cancel), False, False, 0)
        buttons.pack_start(button(ok_label or t('common.ok'), self.answer,
                                  'danger' if danger else 'primary'), False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.connect('key-press-event', lambda _w, e: (self.cancel(), True)[1]
                     if e.keyval == Gdk.KEY_Escape else False)
        self.connect('delete-event', lambda *_: (self.cancel(), True)[1])
        self.yes_no = yes_no

    def answer(self) -> None:
        if self.finished:
            return
        values = {k: e.get_text() for k, e in self.entries.items()}
        if self.entries and not all(values.values()):
            return                                       # an empty password isn't an answer
        self._finish(values if not self.yes_no else {'yes': '1'})

    def cancel(self) -> None:
        self._finish(None)

    def _finish(self, values: Optional[Dict[str, str]]) -> None:
        if self.finished:
            return
        self.finished = True
        self.hide()
        self.destroy()
        self.done_cb(values)

    def close_quietly(self) -> None:
        """NM or BlueZ withdrew the question: close it without answering."""
        if not self.finished:
            self.finished = True
            self.hide()
            self.destroy()


class Prompter:
    """What the agents and the buttons ask the person. `open` lists the windows still up."""

    def __init__(self):
        self.open: List[Ask] = []

    def _show(self, win: Ask) -> Callable[[], None]:
        self.open.append(win)
        win.connect('destroy', lambda w: self.open.remove(w) if w in self.open else None)
        win.show_all()
        win.present()
        return win.close_quietly

    def ask_secrets(self, name: str, fields: List[Tuple[str, str]],
                    done: Callable[[Optional[Dict[str, str]]], None]) -> Callable[[], None]:
        win = Ask(t('net.secret_title', name=name), '', [(k, lab, True) for k, lab in fields],
                  done)
        return self._show(win)

    def ask_password(self, ssid: str, done: Callable[[Optional[str]], None]) -> Callable[[], None]:
        win = Ask(t('net.password_title', ssid=ssid), '', [('password', t('net.password'), True)],
                  lambda v: done(v['password'] if v else None))
        return self._show(win)

    def ask(self, text: str, numeric: bool, done: Callable[[Optional[str]], None]):
        win = Ask(text, '', [('value', 'PIN' if not numeric else '#', False)],
                  lambda v: done(v['value'] if v else None))
        return self._show(win)

    def confirm(self, text: str, done: Callable[[bool], None], danger: bool = False,
                ok_label: str = ''):
        win = Ask(text.split('\n')[0], '\n'.join(text.split('\n')[1:]).strip(), [],
                  lambda v: done(bool(v)), yes_no=True, danger=danger, ok_label=ok_label)
        return self._show(win)

    def notify(self, text: str) -> None:
        win = Ask(text, '', [], lambda _v: None, yes_no=True)
        self._show(win)
