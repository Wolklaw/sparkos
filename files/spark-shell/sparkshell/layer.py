"""gtk4-layer-shell, behind one small module so the rest of the shell reads plainly and the
tests can run without it (`is_available()` is False and the helpers do nothing)."""

import gi

try:
    gi.require_version('Gtk4LayerShell', '1.0')
    from gi.repository import Gtk4LayerShell as LS
except (ValueError, ImportError):       # the typelib isn't installed
    LS = None


def is_available() -> bool:
    """True on a compositor with layer-shell. Asks the display, so call it after Gtk started."""
    return LS is not None and bool(LS.is_supported())

EDGES = ('top', 'bottom', 'left', 'right')


def setup(window, layer='top', anchors=(), namespace='spark-shell', monitor=None,
          exclusive=0, keyboard='none', margins=None):
    """Turn a Gtk.Window into a layer-shell surface.

    layer: background | bottom | top | overlay. anchors: edge names. exclusive: pixels of
    screen the surface reserves (-1: ignore other surfaces' zones, 0: none). keyboard: none |
    on_demand | exclusive."""
    if not is_available():
        return False
    LS.init_for_window(window)
    LS.set_namespace(window, namespace)
    LS.set_layer(window, {'background': LS.Layer.BACKGROUND, 'bottom': LS.Layer.BOTTOM,
                          'top': LS.Layer.TOP, 'overlay': LS.Layer.OVERLAY}[layer])
    for name in EDGES:
        LS.set_anchor(window, {'top': LS.Edge.TOP, 'bottom': LS.Edge.BOTTOM,
                               'left': LS.Edge.LEFT, 'right': LS.Edge.RIGHT}[name],
                      name in anchors)
    for name, value in (margins or {}).items():
        LS.set_margin(window, {'top': LS.Edge.TOP, 'bottom': LS.Edge.BOTTOM,
                               'left': LS.Edge.LEFT, 'right': LS.Edge.RIGHT}[name], value)
    if exclusive > 0:
        LS.set_exclusive_zone(window, exclusive)
    elif exclusive < 0:
        LS.set_exclusive_zone(window, -1)
    LS.set_keyboard_mode(window, {'none': LS.KeyboardMode.NONE,
                                  'on_demand': LS.KeyboardMode.ON_DEMAND,
                                  'exclusive': LS.KeyboardMode.EXCLUSIVE}[keyboard])
    if monitor is not None:
        LS.set_monitor(window, monitor)
    return True


def set_keyboard(window, keyboard):
    if is_available():
        LS.set_keyboard_mode(window, {'none': LS.KeyboardMode.NONE,
                                      'on_demand': LS.KeyboardMode.ON_DEMAND,
                                      'exclusive': LS.KeyboardMode.EXCLUSIVE}[keyboard])
