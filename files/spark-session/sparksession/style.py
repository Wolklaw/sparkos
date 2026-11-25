"""The look, shared by the polkit window and the greeter: GTK CSS in the BotWatch palette, mono
type, sharp 3px corners, UPPERCASE micro-labels, and the magenta and cyan channels slipping out
of register as the only decoration. `.spark-sec` is the CSS class on every window of this
package. glitch() plays the slip on a widget (an error, a heading); it does nothing when the
desktop asks for no animation."""

import random

CHROME = {
    'bg': '#04090b', 'panel': '#0a1517', 'panel2': '#0e1f22', 'hover': '#12292c',
    'line': '#143a3d', 'line2': '#1f6a66', 'text': '#d4f1ec', 'muted': '#6f9f98',
    'dim': '#3b6460', 'accent': '#3de8c8', 'on_accent': '#02130f', 'pink': '#ff4d8d',
    'ch_a': '#ff2e88', 'ch_b': '#22d8ff', 'gold': '#f4c95d',
}
C = CHROME
SPLIT = f"2px 0 0 {C['ch_a']}, -2px 0 0 {C['ch_b']}"

CSS = f"""
window.spark-sec {{ background: {C['bg']}; color: {C['text']}; font-family: monospace; }}
.spark-sec .panel {{
  background: {C['panel']}; border: 1px solid {C['line2']}; border-radius: 3px; padding: 18px;
}}
.spark-sec label.micro {{ font-size: 8pt; font-weight: 700; letter-spacing: 1px; color: {C['muted']}; }}
.spark-sec label.heading {{
  font-size: 12pt; font-weight: 700; letter-spacing: 2px; color: {C['accent']};
  text-shadow: 1px 0 0 {C['ch_a']}, -1px 0 0 {C['ch_b']};
}}
.spark-sec label.big {{ font-size: 40pt; font-weight: 700; color: {C['text']}; }}
.spark-sec label.message {{ font-size: 11pt; color: {C['text']}; }}
.spark-sec label.fact {{ font-size: 9pt; color: {C['text']}; }}
.spark-sec label.status {{ font-size: 9pt; color: {C['muted']}; }}
.spark-sec label.status.warn {{ color: {C['pink']}; }}
.spark-sec label.status.ok {{ color: {C['accent']}; }}
.spark-sec entry, .spark-sec passwordentry {{
  background: {C['bg']}; color: {C['text']}; border: 1px solid {C['line2']};
  border-radius: 3px; box-shadow: none; min-height: 32px; caret-color: {C['accent']};
}}
.spark-sec entry:focus-within, .spark-sec passwordentry:focus-within {{
  border-color: {C['accent']}; box-shadow: {SPLIT};
}}
.spark-sec button {{
  min-height: 26px; padding: 0 12px; border-radius: 3px; box-shadow: none;
  border: 1px solid {C['line2']}; background: transparent; color: {C['text']};
  font-size: 9pt; font-weight: 700; letter-spacing: 1px;
}}
.spark-sec button:hover, .spark-sec button:focus {{ box-shadow: {SPLIT}; border-color: {C['accent']}; }}
.spark-sec button.primary {{ background: {C['accent']}; color: {C['on_accent']}; border-color: {C['accent']}; }}
.spark-sec button.danger {{ color: {C['pink']}; border-color: {C['pink']}; }}
.spark-sec button.user {{
  background: {C['panel']}; border: 1px solid {C['line']}; border-radius: 3px; padding: 8px 14px;
}}
.spark-sec button.user:hover {{ background: {C['hover']}; }}
.spark-sec button.user.chosen {{
  background: {C['panel2']}; border-color: {C['accent']}; box-shadow: {SPLIT};
}}
.spark-sec dropdown > button {{ min-height: 32px; }}
.spark-sec popover > contents {{
  background: {C['panel']}; border: 1px solid {C['line2']}; border-radius: 3px; color: {C['text']};
}}
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
    """Load the CSS and ask for the dark scheme. Safe to call twice."""
    global _installed
    from gi.repository import Gdk, Gtk
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
    if hasattr(provider, 'load_from_string'):
        provider.load_from_string(CSS)
    else:
        provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(display, provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _installed = True


def animations_on() -> bool:
    from gi.repository import Gdk, Gtk
    display = Gdk.Display.get_default()
    settings = Gtk.Settings.get_for_display(display) if display else None
    return bool(settings.get_property('gtk-enable-animations')) if settings else False


def glitch(*widgets) -> None:
    """Two quick jolts of the channel split, then calm (nothing when animations are off)."""
    from gi.repository import GLib
    if not animations_on():
        return
    for widget in widgets:
        if widget is None or widget.has_css_class('burst'):
            continue
        widget.add_css_class('burst')

        def second(w=widget):
            w.remove_css_class('burst')
            w.add_css_class('burst-2')

            def clear():
                w.remove_css_class('burst-2')
                return False
            GLib.timeout_add(70 + random.randint(0, 60), clear)
            return False
        GLib.timeout_add(90, second)
