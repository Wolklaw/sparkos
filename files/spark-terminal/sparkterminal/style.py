"""The window's look: GTK CSS in the SparkOS colours, sharp 3px corners, and the magenta and
cyan channels slipping out of register as the only decoration (the active tab, events,
errors). Glitch() plays the slip on a widget for a moment."""

import random

from gi.repository import Gdk, GLib, Gtk

from .core import CHROME as C

CSS = f"""
window.spark-terminal, window.spark-terminal-dialog {{
  background: {C['bg']};
  color: {C['text']};
}}
.spark-terminal headerbar {{
  background: {C['surface']};
  color: {C['text']};
  border-bottom: 1px solid {C['line']};
  box-shadow: none;
  min-height: 34px;
}}
.spark-terminal headerbar.inactive-window {{ background: {C['bg2']}; color: {C['muted']}; }}

/* tab strip */
notebook.tabs > header {{
  background: {C['bg2']};
  border-bottom: 1px solid {C['line']};
  padding: 0;
  box-shadow: none;
}}
notebook.tabs > header > tabs > tab {{
  min-height: 28px;
  padding: 0 4px 0 12px;
  margin: 4px 0 0 4px;
  border-radius: 3px 3px 0 0;
  border: 1px solid transparent;
  border-bottom: none;
  background: transparent;
  color: {C['muted']};
  box-shadow: none;
  outline: none;
}}
notebook.tabs > header > tabs > tab:hover {{ background: {C['surface']}; color: {C['text']}; }}
notebook.tabs > header > tabs > tab:checked {{
  background: {C['bg']};
  color: {C['text']};
  border-color: {C['line']};
  box-shadow: inset 0 2px 0 {C['accent']};
}}
notebook.tabs > header > tabs > tab:checked label.tab-title {{
  text-shadow: 1px 0 0 rgba(255,46,136,.55), -1px 0 0 rgba(34,216,255,.55);
}}
notebook.tabs > stack {{ background: {C['bg']}; }}
label.tab-title {{
  font-family: monospace;
  font-size: 9pt;
  font-weight: 600;
}}
label.tab-title.exited {{ color: {C['pink']}; }}

/* buttons */
button.spark {{
  min-width: 26px; min-height: 24px;
  padding: 0 6px;
  border-radius: 3px;
  border: 1px solid transparent;
  background: transparent;
  color: {C['muted']};
  box-shadow: none;
}}
button.spark:hover, button.spark:focus-visible {{
  color: {C['text']};
  border-color: {C['line_strong']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
menubutton.spark > button {{
  min-width: 26px; min-height: 24px; padding: 0 6px; border-radius: 3px;
  border: 1px solid transparent; background: transparent; color: {C['muted']}; box-shadow: none;
}}
menubutton.spark > button:hover, menubutton.spark > button:checked {{
  color: {C['text']}; border-color: {C['line_strong']};
  box-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.tab-actions button.spark, .tab-actions menubutton.spark > button {{ font-size: 13pt; }}
button.spark.tab-close {{ min-width: 18px; min-height: 18px; padding: 0; margin-left: 6px; }}
button.spark.primary {{
  background: {C['accent']};
  color: {C['on_accent']};
  font-weight: 700;
}}
button.spark.primary:hover {{ color: {C['on_accent']}; }}
togglebutton.spark:checked, button.spark:checked {{
  color: {C['accent']}; border-color: {C['accent']};
}}

/* panes */
.pane {{ background: #05040f; border: 1px solid transparent; }}
vte-terminal {{ padding: 4px 6px; }}
.pane.split.focused {{ border-color: rgba(155,232,184,.35); }}
.pane scrollbar {{ background: transparent; border: none; }}
.pane scrollbar slider {{
  background: {C['surface2']}; border-radius: 3px; min-width: 6px; border: none;
}}
.pane scrollbar slider:hover {{ background: {C['muted']}; }}
paned > separator {{ background: {C['line']}; min-width: 1px; min-height: 1px; }}

/* the slip */
.burst {{
  box-shadow: 4px 0 0 {C['ch_a']}, -4px 0 0 {C['ch_b']};
  text-shadow: 3px 0 0 {C['ch_a']}, -3px 0 0 {C['ch_b']};
}}
.burst-2 {{
  box-shadow: -3px 0 0 {C['ch_a']}, 3px 0 0 {C['ch_b']};
  text-shadow: -2px 0 0 {C['ch_a']}, 2px 0 0 {C['ch_b']};
}}
.pane.bell {{ border-color: {C['ch_a']}; }}

/* search bar */
.findbar {{
  background: {C['surface']};
  border-top: 1px solid {C['line']};
  padding: 4px 6px;
}}
.findbar entry, .spark-terminal-dialog entry, .spark-terminal-dialog spinbutton {{
  background: {C['bg']};
  color: {C['text']};
  border: 1px solid {C['line_strong']};
  border-radius: 3px;
  box-shadow: none;
  font-family: monospace;
  min-height: 26px;
}}
.findbar entry:focus-within, .spark-terminal-dialog entry:focus-within {{
  border-color: {C['accent']};
}}
.findbar entry.error {{ border-color: {C['ch_a']}; color: {C['pink']}; }}
label.find-status {{ color: {C['muted']}; font-family: monospace; font-size: 9pt; }}
label.find-status.error {{ color: {C['pink']}; }}

/* menus and dialogs */
popover > contents, popover.menu > contents {{
  background: {C['surface']};
  color: {C['text']};
  border: 1px solid {C['line_strong']};
  border-radius: 3px;
  box-shadow: 0 6px 18px rgba(0,0,0,.5);
}}
popover modelbutton:hover, popover modelbutton:selected {{
  background: {C['surface2']};
}}
popover modelbutton accelerator {{ color: {C['muted']}; }}
.spark-terminal-dialog label.micro {{
  font-family: monospace;
  font-size: 8pt;
  font-weight: 700;
  color: {C['muted']};
  letter-spacing: 1px;
}}
.spark-terminal-dialog label.heading {{
  font-family: monospace;
  font-size: 13pt;
  font-weight: 700;
  text-shadow: 2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']};
}}
.spark-terminal-dialog label.hint {{ color: {C['muted']}; font-size: 9pt; }}
.spark-terminal-dialog label.error {{ color: {C['pink']}; }}
.spark-terminal-dialog label.keys {{ font-family: monospace; }}
.spark-terminal-dialog switch {{ border-radius: 3px; background: {C['surface2']}; }}
.spark-terminal-dialog switch:checked {{ background: {C['accent']}; }}
.spark-terminal-dialog switch slider {{ border-radius: 2px; }}
.spark-terminal-dialog dropdown > button {{
  border-radius: 3px; background: {C['bg']}; border: 1px solid {C['line_strong']};
  color: {C['text']}; box-shadow: none;
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
