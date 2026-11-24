"""The look: GTK CSS in the BotWatch palette, mono type, sharp 3px corners, UPPERCASE micro-labels,
and the magenta and cyan channels slipping out of register as the only decoration (headings,
the focused row, a copy, an error). Glitch() plays the slip on a widget for a moment, and does
nothing when the desktop asks for no animation."""

import random

from gi.repository import Gdk, GLib, Gtk

from .core import CHROME as C

SPLIT = f"2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']}"

CSS = f"""
window.spark-notes {{
  background: {C['bg']}; color: {C['text']};
  font-family: monospace;
}}
window.spark-notes.popup {{ border: 1px solid {C['line2']}; border-radius: 3px; }}
.spark-notes entry.search {{
  background: {C['panel']}; color: {C['text']};
  border: 1px solid {C['line2']}; border-radius: 3px; box-shadow: none; min-height: 30px;
}}
.spark-notes entry.search:focus-within {{
  border-color: {C['accent']}; box-shadow: {SPLIT};
}}
.spark-notes label.micro {{
  font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {C['muted']};
}}
.spark-notes label.heading {{
  font-size: 9pt; font-weight: 700; letter-spacing: 2px; color: {C['accent']};
  text-shadow: 1px 0 0 {C['ch_a']}, -1px 0 0 {C['ch_b']};
}}
.spark-notes label.status {{ font-size: 9pt; color: {C['muted']}; }}
.spark-notes label.status.ok {{ color: {C['accent']}; }}
.spark-notes label.status.warn {{ color: {C['pink']}; }}
.spark-notes label.empty {{ color: {C['muted']}; }}
.spark-notes label.preview {{ font-size: 10pt; color: {C['text']}; }}
.spark-notes label.meta {{ font-size: 8pt; color: {C['dim']}; font-weight: 700; letter-spacing: 1px; }}
.spark-notes label.title {{ font-size: 10pt; font-weight: 700; color: {C['text']}; }}
.spark-notes label.snippet {{ font-size: 9pt; color: {C['muted']}; }}
.spark-notes list.rows {{ background: transparent; }}
.spark-notes list.rows > row {{
  background: {C['panel']}; border: 1px solid {C['line']}; border-radius: 3px;
  margin: 0 0 3px 0; padding: 0;
}}
.spark-notes list.rows > row:hover {{ background: {C['hover']}; border-color: {C['line2']}; }}
.spark-notes list.rows > row:selected {{
  background: {C['panel2']}; border-color: {C['accent']}; box-shadow: {SPLIT};
}}
.spark-notes list.rows > row.pinned {{ border-left: 3px solid {C['gold']}; }}
.spark-notes button.mini, .spark-notes button.action {{
  min-height: 22px; padding: 0 8px; border-radius: 3px; box-shadow: none;
  border: 1px solid {C['line2']}; background: transparent; color: {C['text']};
  font-size: 8pt; font-weight: 700; letter-spacing: 1px;
}}
.spark-notes button.mini:hover, .spark-notes button.action:hover {{
  box-shadow: {SPLIT}; border-color: {C['accent']};
}}
.spark-notes button.mini:checked, .spark-notes button.mini.on {{
  color: {C['gold']}; border-color: {C['gold']};
}}
.spark-notes button.action.primary {{
  background: {C['accent']}; color: {C['on_accent']}; border-color: {C['accent']};
}}
.spark-notes button.action.paused, .spark-notes button.action.danger {{
  color: {C['pink']}; border-color: {C['pink']};
}}
.spark-notes .footer {{ border-top: 1px solid {C['line']}; padding-top: 4px; }}
.spark-notes .side {{ border-right: 1px solid {C['line']}; }}
.spark-notes textview.editor, .spark-notes textview.editor text {{
  background: {C['panel']}; color: {C['text']}; font-size: 11pt;
  caret-color: {C['accent']};
}}
.spark-notes scrolledwindow.editorbox {{ border: 1px solid {C['line']}; border-radius: 3px; }}
.spark-notes scrollbar {{ background: transparent; border: none; }}
.spark-notes scrollbar slider {{ background: {C['line2']}; border-radius: 3px; min-width: 6px; border: none; }}
.spark-notes scrollbar slider:hover {{ background: {C['muted']}; }}
.spark-notes picture.thumb {{ border: 1px solid {C['line']}; border-radius: 3px; }}

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
    the user turned it off or the desktop asks for no animation (reduced motion)."""

    def __init__(self, enabled: bool = True):
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
