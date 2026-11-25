"""The tray as GTK 4 widgets: one flat button per StatusNotifierItem, and dbusmenu menus as
popovers (sub-menus are pages of one popover, with a Back row)."""

import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .strings import tr  # noqa: E402

ICON_SIZE = 20


def item_paintable_or_name(item, display):
    """('name', icon name) or ('texture', Gdk.Texture) or (None, None) for an item's icon."""
    name = item.icon_name
    path = item.icon_theme_path
    theme = Gtk.IconTheme.get_for_display(display)
    if path and os.path.isdir(path) and path not in theme.get_search_path():
        theme.add_search_path(path)
    if name:
        if os.path.isabs(name) and os.path.isfile(name):
            try:
                return 'texture', Gdk.Texture.new_from_filename(name)
            except GLib.Error:
                pass
        elif theme.has_icon(name):
            return 'name', name
    pixmaps = item.pixmaps
    if pixmaps:
        # the one closest to our size, preferring bigger (they scale down cleanly)
        best = next((p for p in pixmaps if p[0] >= ICON_SIZE), pixmaps[-1])
        w, h, data = best
        bytes_ = GLib.Bytes.new(data[:w * h * 4])
        return 'texture', Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.A8R8G8B8, bytes_, w * 4)
    if name:
        return 'name', name
    return None, None


def set_item_icon(image: Gtk.Image, item, display):
    kind, value = item_paintable_or_name(item, display)
    if kind == 'texture':
        image.set_from_paintable(value)
    elif kind == 'name':
        image.set_from_icon_name(value)
    else:
        image.set_from_icon_name('application-x-executable')
    image.set_pixel_size(ICON_SIZE)


def _menu_button(label: str, enabled=True, check=None, has_sub=False, icon=''):
    button = Gtk.Button()
    button.add_css_class('spark-item')
    row = Gtk.Box(spacing=8)
    mark = Gtk.Label(label=('●' if check[1] else ' ') if check and check[0] == 'radio'
                     else ('✓' if check and check[1] else ' ') if check else '')
    mark.set_width_chars(1 if check else 0)
    row.append(mark)
    if icon:
        image = Gtk.Image.new_from_icon_name(icon)
        image.set_pixel_size(16)
        row.append(image)
    text = Gtk.Label(label=label, xalign=0, hexpand=True)
    text.add_css_class('spark-text')
    row.append(text)
    if has_sub:
        row.append(Gtk.Label(label='›'))
    button.set_child(row)
    button.set_sensitive(enabled)
    return button


def build_menu(menu, root, popover):
    """The popover's content for a dbusmenu layout: a Gtk.Stack of pages."""
    stack = Gtk.Stack()

    def page(node, name, back):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if back:
            b = _menu_button('‹ ' + tr('back'))
            b.connect('clicked', lambda *_: stack.set_visible_child_name(back))
            box.append(b)
            box.append(Gtk.Separator())
        shown = 0
        for child in node.children:
            if not child.visible:
                continue
            if child.separator:
                if shown:
                    box.append(Gtk.Separator())
                continue
            shown += 1
            if child.has_submenu and child.children:
                sub_name = str(child.id)
                button = _menu_button(child.label, child.enabled, has_sub=True,
                                      icon=child.icon_name)
                stack.add_named(page(child, sub_name, name), sub_name)
                button.connect('clicked', lambda *_a, n=sub_name: stack.set_visible_child_name(n))
            else:
                button = _menu_button(child.label, child.enabled, child.toggle,
                                      icon=child.icon_name)
                button.connect('clicked', lambda *_a, i=child.id: (
                    menu.event(i), popover.popdown()))
            box.append(button)
        return box

    stack.add_named(page(root, 'root', ''), 'root')
    stack.set_visible_child_name('root')
    stack.set_vhomogeneous(False)
    stack.set_hhomogeneous(False)
    return stack


def show_menu(parent: Gtk.Widget, menu):
    """Fetch the menu from the item and pop it up on `parent`."""
    def got(root):
        if root is None or not root.children:
            return
        popover = Gtk.Popover()
        popover.add_css_class('spark-pop')
        popover.set_parent(parent)
        popover.set_autohide(True)
        popover.set_has_arrow(False)
        popover.set_child(build_menu(menu, root, popover))
        popover.connect('closed', lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    menu.about_to_show(0, lambda _changed: menu.get_layout(got))


class TrayView(Gtk.Box):
    """The buttons for a TrayHost's visible items."""

    def __init__(self, host):
        super().__init__(spacing=2)
        self.host = host
        self.buttons = {}          # item key -> (button, image)
        host.on_added = self._added
        host.on_changed = self._changed
        host.on_removed = self._removed
        for item in host.visible_items():
            self._added(item)

    def _added(self, item):
        if item.key in self.buttons:
            return self._changed(item)
        button = Gtk.Button()
        button.add_css_class('spark-flat')
        image = Gtk.Image()
        button.set_child(image)
        # left click: the button's own "clicked". A GestureClick on a Gtk.Button never sees a
        # left release (the button's internal gesture claims it), so only middle/right go there.
        button.connect('clicked', lambda b, i=item: self._primary(i, b))
        click = Gtk.GestureClick(button=0)
        click.connect('released', self._clicked, item, button)
        button.add_controller(click)
        button.set_focusable(True)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', lambda _c, _dx, dy: (item.scroll(int(dy * 120)), True)[1])
        button.add_controller(scroll)
        self.buttons[item.key] = (button, image)
        self.append(button)
        self._changed(item)

    def _changed(self, item):
        entry = self.buttons.get(item.key)
        if entry is None:
            return
        button, image = entry
        set_item_icon(image, item, self.get_display())
        button.set_tooltip_text(item.title or item.id)
        button.set_visible(item.status != 'Passive')
        if item.status == 'NeedsAttention':
            button.add_css_class('attention')
        else:
            button.remove_css_class('attention')

    def _removed(self, item):
        entry = self.buttons.pop(item.key, None)
        if entry:
            self.remove(entry[0])

    @staticmethod
    def _primary(item, button):
        if item.item_is_menu and item.menu():
            show_menu(button, item.menu())
        else:
            item.activate(0, 0)

    def _clicked(self, gesture, n_press, x, y, item, button):
        which = gesture.get_current_button()
        if which == 2:
            item.secondary_activate(0, 0)
        elif which == 3:
            menu = item.menu()
            if menu:
                show_menu(button, menu)
            else:
                item.context_menu(0, 0)
