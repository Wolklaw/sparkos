"""The look, in GTK 3 CSS: the BotWatch palette, mono type, sharp 3px corners, UPPERCASE
micro-labels, and the magenta and cyan channels slipping out of register as the only decoration
(headings, the selected machine, an error, a button hover). Glitch() plays the slip on a widget
for a moment, and does nothing when the desktop asks for no animation."""

import random

from gi.repository import Gdk, GLib, Gtk

CHROME = {
    'bg': '#04090b', 'panel': '#0a1517', 'panel2': '#0e1f22', 'hover': '#12292c',
    'line': '#143a3d', 'line2': '#1f6a66', 'text': '#d4f1ec', 'muted': '#6f9f98',
    'dim': '#3b6460', 'accent': '#3de8c8', 'on_accent': '#02130f', 'pink': '#ff4d8d',
    'ch_a': '#ff2e88', 'ch_b': '#22d8ff', 'gold': '#f4c95d',
}
C = CHROME
SPLIT = f"2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']}"
NAME = 'spark-boxes'

CSS = f"""
window.{NAME}, .{NAME} {{
  background: {C['bg']}; color: {C['text']}; font-family: monospace;
}}
.{NAME} label {{ color: {C['text']}; }}
.{NAME} label.micro {{ font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {C['muted']}; }}
.{NAME} label.heading {{
  font-size: 10pt; font-weight: 700; letter-spacing: 2px; color: {C['accent']};
  text-shadow: 1px 0 0 {C['ch_a']}, -1px 0 0 {C['ch_b']};
}}
.{NAME} label.big {{ font-size: 15pt; font-weight: 700; letter-spacing: 1px; }}
.{NAME} label.status {{ font-size: 9pt; color: {C['muted']}; }}
.{NAME} label.status.ok {{ color: {C['accent']}; }}
.{NAME} label.status.warn {{ color: {C['pink']}; }}
.{NAME} label.meta {{ font-size: 8pt; color: {C['dim']}; font-weight: 700; letter-spacing: 1px; }}
.{NAME} label.body {{ font-size: 10pt; color: {C['muted']}; }}
.{NAME} label.title {{ font-size: 10pt; font-weight: 700; }}
.{NAME} label.state {{ font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {C['muted']}; }}
.{NAME} label.state.running {{ color: {C['accent']}; }}
.{NAME} label.state.paused {{ color: {C['gold']}; }}
.{NAME} label.glyph {{
  font-size: 9pt; font-weight: 700; color: {C['accent']}; background: {C['panel2']};
  border: 1px solid {C['line2']}; border-radius: 3px; padding: 4px 0; min-width: 42px;
}}
.{NAME} .side {{ border-right: 1px solid {C['line']}; background: {C['panel']}; }}
.{NAME} .footer {{ border-top: 1px solid {C['line']}; }}
.{NAME} list, .{NAME} list.rows {{ background: transparent; }}
.{NAME} list.rows > row {{
  background: {C['panel']}; border: 1px solid {C['line']}; border-radius: 3px;
  margin: 0 0 3px 0; padding: 0;
}}
.{NAME} list.rows > row:hover {{ background: {C['hover']}; border-color: {C['line2']}; }}
.{NAME} list.rows > row:selected {{
  background: {C['panel2']}; border-color: {C['accent']}; box-shadow: {SPLIT};
}}
.{NAME} entry, .{NAME} spinbutton, .{NAME} spinbutton entry {{
  background: {C['panel']}; color: {C['text']}; caret-color: {C['accent']};
  border: 1px solid {C['line2']}; border-radius: 3px; box-shadow: none; min-height: 28px;
}}
.{NAME} entry:focus, .{NAME} spinbutton:focus {{ border-color: {C['accent']}; box-shadow: {SPLIT}; }}
.{NAME} spinbutton button {{ background: {C['panel2']}; border: none; border-radius: 0; box-shadow: none; }}
.{NAME} button {{
  min-height: 24px; padding: 2px 10px; border-radius: 3px; box-shadow: none;
  border: 1px solid {C['line2']}; background: transparent; color: {C['text']};
  font-size: 8pt; font-weight: 700; letter-spacing: 1px; text-shadow: none;
}}
.{NAME} button:hover {{ box-shadow: {SPLIT}; border-color: {C['accent']}; background: transparent; }}
.{NAME} button:disabled {{ color: {C['dim']}; border-color: {C['line']}; box-shadow: none; }}
.{NAME} button.primary {{ background: {C['accent']}; color: {C['on_accent']}; border-color: {C['accent']}; }}
.{NAME} button.primary label {{ color: {C['on_accent']}; }}
.{NAME} button.primary:disabled {{ background: {C['panel2']}; color: {C['dim']}; border-color: {C['line']}; }}
.{NAME} button.primary:disabled label {{ color: {C['dim']}; }}
.{NAME} button.danger {{ color: {C['pink']}; border-color: {C['pink']}; }}
.{NAME} button.danger label {{ color: {C['pink']}; }}
.{NAME} button.danger:disabled label {{ color: {C['dim']}; }}
.{NAME} button.choice:checked {{ border-color: {C['accent']}; color: {C['accent']}; box-shadow: {SPLIT}; }}
.{NAME} button.choice:checked label {{ color: {C['accent']}; }}
.{NAME} notebook {{ background: transparent; }}
.{NAME} notebook > header {{ background: transparent; border-bottom: 1px solid {C['line']}; }}
.{NAME} notebook > header > tabs > tab {{
  background: transparent; border: none; padding: 4px 14px; min-height: 22px;
}}
.{NAME} notebook > header > tabs > tab:checked {{ border-bottom: 2px solid {C['accent']}; }}
.{NAME} notebook > header > tabs > tab label {{
  font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {C['muted']};
}}
.{NAME} notebook > header > tabs > tab:checked label {{ color: {C['accent']}; }}
.{NAME} scrolledwindow {{ border: none; }}
.{NAME} scrollbar {{ background: transparent; border: none; }}
.{NAME} scrollbar slider {{ background: {C['line2']}; border-radius: 3px; min-width: 6px; border: none; }}
.{NAME} progressbar trough {{ background: {C['panel2']}; border: 1px solid {C['line']}; border-radius: 3px; min-height: 6px; }}
.{NAME} progressbar progress {{ background: {C['accent']}; border-radius: 3px; min-height: 6px; }}
.{NAME} .dropzone {{
  border: 1px dashed {C['line2']}; border-radius: 3px; background: {C['panel']}; padding: 12px;
}}
.{NAME} .dropzone.hot {{ border-color: {C['accent']}; box-shadow: {SPLIT}; }}
.{NAME} combobox button, .{NAME} switch {{ min-height: 24px; }}
.{NAME} switch {{ background: {C['panel2']}; border: 1px solid {C['line2']}; border-radius: 3px; }}
.{NAME} switch:checked {{ background: {C['accent']}; }}
.{NAME} switch slider {{ background: {C['text']}; border-radius: 3px; }}
.{NAME} checkbutton, .{NAME} radiobutton {{ color: {C['text']}; }}
.{NAME} .consolebar {{ background: {C['panel']}; border-bottom: 1px solid {C['line']}; padding: 4px 8px; }}

.burst {{
  box-shadow: 4px 0 0 {C['ch_a']}, -4px 0 0 {C['ch_b']};
  text-shadow: 3px 0 0 {C['ch_a']}, -3px 0 0 {C['ch_b']};
}}
.burst-2 {{
  box-shadow: -3px 0 0 {C['ch_a']}, 3px 0 0 {C['ch_b']};
  text-shadow: -2px 0 0 {C['ch_a']}, 2px 0 0 {C['ch_b']};
}}
"""

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    screen = Gdk.Screen.get_default()
    if screen is None:
        return
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property('gtk-application-prefer-dark-theme', True)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(screen, provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _installed = True


def animations_on() -> bool:
    settings = Gtk.Settings.get_default()
    return bool(settings.get_property('gtk-enable-animations')) if settings else False


def add_class(widget: Gtk.Widget, *names: str) -> None:
    ctx = widget.get_style_context()
    for name in names:
        ctx.add_class(name)


def label(text: str, *classes: str, xalign: float = 0.0, wrap: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=xalign)
    widget.set_line_wrap(wrap)
    if wrap:
        widget.set_max_width_chars(60)
    add_class(widget, *classes)
    return widget


class Glitch:
    """The house fault on a widget: two quick jolts of the channel split, then calm. Off when
    the user turned it off or the desktop asks for no animation (reduced motion)."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def now(self, *widgets: Gtk.Widget) -> None:
        if not self.enabled or not animations_on():
            return
        for widget in widgets:
            if widget is None or widget.get_style_context().has_class('burst'):
                continue
            widget.get_style_context().add_class('burst')
            GLib.timeout_add(90, self._second, widget)

    @staticmethod
    def _second(widget: Gtk.Widget) -> bool:
        ctx = widget.get_style_context()
        ctx.remove_class('burst')
        ctx.add_class('burst-2')
        GLib.timeout_add(70 + random.randint(0, 60), Glitch._clear, widget)
        return False

    @staticmethod
    def _clear(widget: Gtk.Widget) -> bool:
        widget.get_style_context().remove_class('burst-2')
        return False
