"""Drag and drop for the panel: a string payload "kind:name" (kind is task, tray or connect), a
source for a button and a target that tells before/after by which half the pointer is over.
Drags between two panels work because the panels are surfaces of the same client."""

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

MOVE = Gdk.DragAction.MOVE


def split_payload(value):
    """('task', 'a.desktop') from 'task:a.desktop'; (None, None) for anything else."""
    if isinstance(value, str) and ':' in value:
        kind, name = value.split(':', 1)
        if kind and name != '':
            return kind, name
    return None, None


def is_after(x: float, width: float) -> bool:
    """The pointer is over the right half: the dragged item goes after this one."""
    return x >= width / 2


def attach_source(widget, kind, name, on_begin=None, on_end=None):
    """Make `widget` draggable. A click that does not move still reaches the widget: GTK only
    starts the drag after the pointer has moved a few pixels."""
    source = Gtk.DragSource()
    source.set_actions(MOVE)
    source.connect('prepare', lambda *_: Gdk.ContentProvider.new_for_value(
        GObject.Value(str, '%s:%s' % (kind, name))))
    if on_begin:
        source.connect('drag-begin', lambda *_: on_begin())
    source.connect('drag-end', lambda *_: on_end() if on_end else None)
    widget.add_controller(source)
    return source


def attach_target(widget, kind, on_drop, mark=True):
    """Accept `kind` drops on `widget`. on_drop(name, after) returns True when it took the drop;
    with `mark` the widget shows a line on the side the item would land."""
    target = Gtk.DropTarget.new(GObject.TYPE_STRING, MOVE)

    def clear():
        widget.remove_css_class('drop-before')
        widget.remove_css_class('drop-after')

    def wanted():
        value = target.get_value()
        return value is None or split_payload(value)[0] == kind     # unknown until dropped

    def motion(_t, x, _y):
        if not wanted():
            clear()
            return Gdk.DragAction(0)
        if mark:
            after = is_after(x, widget.get_width())
            widget.add_css_class('drop-after' if after else 'drop-before')
            widget.remove_css_class('drop-before' if after else 'drop-after')
        return MOVE

    def drop(_t, value, x, _y):
        clear()
        got, name = split_payload(value)
        if got != kind:
            return False
        return bool(on_drop(name, is_after(x, widget.get_width())))

    target.connect('motion', motion)
    target.connect('leave', lambda *_: clear())
    target.connect('drop', drop)
    widget.add_controller(target)
    return target
