"""The window's look: GTK CSS in the SparkOS colours, sharp 3px corners, and the magenta and
cyan channels slipping out of register as the only decoration (the focused cell, a pick,
a refusal). Glitch() plays the slip on a widget for a moment."""

import random

from gi.repository import Gdk, GLib, Gtk

from .core import CHROME as C

CSS = f"""
window.spark-emoji {{
  background: {C['bg']};
  color: {C['text']};
  border: 1px solid {C['line_strong']};
  border-radius: 3px;
}}
.spark-emoji entry.search {{
  background: {C['bg2']};
  color: {C['text']};
  border: 1px solid {C['line_strong']};
  border-radius: 3px;
  box-shadow: none;
  min-height: 32px;
  font-family: monospace;
}}
.spark-emoji entry.search:focus-within {{
  border-color: {C['accent']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.spark-emoji .tabs {{ border-bottom: 1px solid {C['line']}; padding-bottom: 4px; }}
.spark-emoji button.tab, .spark-emoji menubutton.tab > button {{
  min-width: 30px; min-height: 28px; padding: 0 4px;
  border-radius: 3px; border: 1px solid transparent;
  background: transparent; box-shadow: none; color: {C['muted']};
  font-size: 13pt;
}}
.spark-emoji button.tab:hover, .spark-emoji menubutton.tab > button:hover {{
  border-color: {C['line_strong']}; color: {C['text']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.spark-emoji button.tab:checked {{
  border-color: {C['accent']}; color: {C['text']}; background: {C['surface']};
}}
.spark-emoji label.cell {{
  min-width: 36px; min-height: 36px; padding: 0;
  color: {C['text']}; font-size: 19pt;
}}
.spark-emoji label.cell.symbolcell {{ font-family: sans-serif; font-size: 16pt; }}
.spark-emoji flowboxchild.cellbox {{
  border-radius: 3px; border: 1px solid transparent; background: transparent;
}}
.spark-emoji flowboxchild.cellbox:hover, .spark-emoji flowboxchild.cellbox:focus-visible {{
  background: {C['surface']}; border-color: {C['line_strong']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.spark-emoji label.cell.first {{ outline: 1px solid {C['accent']}; outline-offset: -2px; }}
button.cell {{
  min-width: 36px; min-height: 36px; padding: 0; border-radius: 3px;
  border: 1px solid transparent; background: transparent; box-shadow: none;
  color: {C['text']}; font-size: 19pt;
}}
button.cell:hover {{
  background: {C['surface2']}; border-color: {C['line_strong']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.spark-emoji label.group-title {{
  font-family: monospace; font-size: 8pt; font-weight: 700; letter-spacing: 1px;
  color: {C['muted']};
}}
.spark-emoji label.status {{ font-family: monospace; font-size: 9pt; color: {C['muted']}; }}
.spark-emoji label.status.ok {{ color: {C['accent']}; }}
.spark-emoji label.status.warn {{ color: {C['pink']}; }}
.spark-emoji label.empty {{ color: {C['muted']}; }}
.spark-emoji .footer {{ border-top: 1px solid {C['line']}; padding-top: 4px; }}
.spark-emoji button.link {{
  min-height: 22px; padding: 0 8px; border-radius: 3px;
  border: 1px solid {C['line_strong']}; background: transparent; color: {C['text']};
  box-shadow: none; font-family: monospace; font-size: 9pt;
}}
.spark-emoji button.link:hover {{ box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']}; }}
.spark-emoji scrollbar {{ background: transparent; border: none; }}
.spark-emoji scrollbar slider {{
  background: {C['surface2']}; border-radius: 3px; min-width: 6px; border: none;
}}
.spark-emoji scrollbar slider:hover {{ background: {C['muted']}; }}
popover > contents {{
  background: {C['surface']}; color: {C['text']};
  border: 1px solid {C['line_strong']}; border-radius: 3px;
  box-shadow: 0 6px 18px rgba(0,0,0,.5);
}}
popover modelbutton:hover, popover modelbutton:selected {{ background: {C['surface2']}; }}

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
    display = Gdk.Display.get_default()
    if display is None:
        return
    settings = Gtk.Settings.get_for_display(display)
    if settings is not None:
        if settings.find_property('gtk-interface-color-scheme') is not None:
            settings.set_property('gtk-interface-color-scheme', Gtk.InterfaceColorScheme.DARK)
        else:
            settings.set_property('gtk-application-prefer-dark-theme', True)
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS) if hasattr(provider, 'load_from_string') \
        else provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(display, provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _installed = True


def animations_on() -> bool:
    display = Gdk.Display.get_default()
    settings = Gtk.Settings.get_for_display(display) if display else None
    return bool(settings.get_property('gtk-enable-animations')) if settings else False


class Glitch:
    """The house fault on a widget: two quick jolts of the channel split, then calm. Off when
    the user turned it off or the desktop asks for no animation."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def now(self, *widgets: Gtk.Widget) -> None:
        if not self.enabled or not animations_on():
            return
        for widget in widgets:
            if widget is None or widget.has_css_class('burst'):
                continue
            widget.add_css_class('burst')
            GLib.timeout_add(90, self._second, widget)

    @staticmethod
    def _second(widget: Gtk.Widget) -> bool:
        widget.remove_css_class('burst')
        widget.add_css_class('burst-2')
        GLib.timeout_add(70 + random.randint(0, 60), Glitch._clear, widget)
        return False

    @staticmethod
    def _clear(widget: Gtk.Widget) -> bool:
        widget.remove_css_class('burst-2')
        return False
