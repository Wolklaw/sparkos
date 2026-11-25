"""Notifications on screen: toast cards at the top right, and the bell with the history list."""

import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import layer  # noqa: E402
from .notifyd import DISMISSED, position  # noqa: E402
from .strings import tr  # noqa: E402
from .windows import match_app  # noqa: E402

_tracker = None     # the shell's window tracker, set by NotificationsUI


def _app_info(n):
    for name in (n.desktop_entry, (n.app or '').lower().replace(' ', '-')):
        if not name:
            continue
        name = name if name.endswith('.desktop') else name + '.desktop'
        try:
            info = Gio.DesktopAppInfo.new(name)
        except TypeError:
            info = None
        if info is not None:
            return info
    return None


def open_notification(n, server):
    """A click on a notification: let the app act on it, and bring the app to the front.
    The app's own window is raised if it has one; otherwise the app is started."""
    invoked = n.id in server.active and any(k == 'default' for k, _ in n.actions)
    if invoked:
        server.invoke(n.id, 'default')
    info = _app_info(n)
    keys = [k for k in (info.get_id() if info else '', n.desktop_entry, n.app) if k]
    wm_class = (info.get_startup_wm_class() or '') if info else ''
    windows = _tracker.windows if _tracker is not None else []
    for w in windows:
        if any(match_app(w, k, wm_class) for k in keys):
            _tracker.act('activate', w['id'])
            return
    if not invoked and info is not None:
        try:
            info.launch([], None)
        except GLib.Error:
            pass


def image_widget(n, size=48):
    """The notification's picture: inline image data, image-path, or its icon name."""
    image = Gtk.Image()
    image.set_pixel_size(size)
    if n.image:
        w, h, stride, alpha, bits, channels, data = n.image
        if bits == 8 and channels in (3, 4) and len(data) >= stride * (h - 1) + w * channels:
            fmt = Gdk.MemoryFormat.R8G8B8A8 if channels == 4 else Gdk.MemoryFormat.R8G8B8
            image.set_from_paintable(Gdk.MemoryTexture.new(
                w, h, fmt, GLib.Bytes.new(bytes(data)), stride))
            return image
    path = n.image_path
    if path.startswith('file://'):
        path = path[7:]
    if path.startswith('/'):
        image.set_from_file(path)
    elif path or n.icon:
        image.set_from_icon_name(path or n.icon)
    else:
        return None
    return image


def card(n, server, on_done):
    """One notification as a card with its action buttons."""
    box = Gtk.Box(spacing=10)
    box.add_css_class('spark-card')
    if n.critical:
        box.add_css_class('critical')
    box.set_size_request(340, -1)
    picture = image_widget(n)
    if picture is not None:
        picture.set_valign(Gtk.Align.START)
        box.append(picture)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    app = Gtk.Label(label=(n.app or '').upper(), xalign=0)
    app.add_css_class('app')
    title = Gtk.Label(label=n.summary, xalign=0, wrap=True, max_width_chars=40)
    title.add_css_class('title')
    text.append(app)
    text.append(title)
    if n.body:
        body = Gtk.Label(xalign=0, wrap=True, max_width_chars=44)
        try:
            body.set_markup(n.body)
        except Exception:
            body.set_text(n.body)
        if not body.get_text():
            body.set_text(n.body)
        body.add_css_class('body')
        text.append(body)
    labelled = [(k, v) for k, v in n.actions if k != 'default']
    if labelled:
        row = Gtk.Box(spacing=6)
        row.set_margin_top(4)
        for key, label in labelled:
            button = Gtk.Button(label=label)
            button.add_css_class('spark-btn')
            button.connect('clicked', lambda _b, k=key: (server.invoke(n.id, k), on_done(n.id)))
            row.append(button)
        text.append(row)
    box.append(text)
    close = Gtk.Button(label='x')
    close.add_css_class('spark-flat')
    close.set_valign(Gtk.Align.START)
    close.connect('clicked', lambda *_: (server.close(n.id), on_done(n.id)))
    box.append(close)
    click = Gtk.GestureClick()
    click.connect('released', lambda *_: (open_notification(n, server), on_done(n.id)))
    text.add_controller(click)
    text.set_cursor_from_name('pointer')
    return box


class Toasts(Gtk.Window):
    """A window that holds the live cards and hides when there are none."""

    def __init__(self, server):
        super().__init__()
        self.server = server
        self.set_decorated(False)
        self.add_css_class('spark-transparent')
        self.where = position()
        anchors = tuple(e for e in ('top', 'bottom', 'left', 'right')
                        if e in self.where.lower().replace('center', ''))
        layer.setup(self, 'overlay', anchors, 'spark-notifications',
                    margins={e: 12 for e in anchors})
        self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_child(self.stack)
        self.cards = {}
        server.on_show = self.show_card
        server.on_close = self.close_card

    def place(self):
        """Follow the position chosen in Spark Settings (checked when a card shows)."""
        where = position()
        if where == self.where:
            return
        self.where = where
        anchors = tuple(e for e in ('top', 'bottom', 'left', 'right')
                        if e in where.lower().replace('center', ''))
        for e, edge in (('top', layer.LS.Edge.TOP), ('bottom', layer.LS.Edge.BOTTOM),
                        ('left', layer.LS.Edge.LEFT), ('right', layer.LS.Edge.RIGHT)):
            layer.LS.set_anchor(self, edge, e in anchors)
            layer.LS.set_margin(self, edge, 12 if e in anchors else 0)

    def show_card(self, n):
        if layer.is_available():
            self.place()
        old = self.cards.pop(n.id, None)
        widget = card(n, self.server, self.close_card_quietly)
        if old is not None:
            self.stack.insert_child_after(widget, old)
            self.stack.remove(old)
        else:
            self.stack.prepend(widget)
        self.cards[n.id] = widget
        self.present()

    def close_card_quietly(self, ident):
        self.close_card(ident, DISMISSED)

    def close_card(self, ident, reason=DISMISSED):
        widget = self.cards.pop(ident, None)
        if widget is not None:
            self.stack.remove(widget)
        if not self.cards:
            self.set_visible(False)


class Bell:
    """The panel's bell buttons (one per panel) and the history popover."""

    def __init__(self, server):
        self.server = server
        self.buttons = []
        server.on_history_changed = self.refresh

    def make(self):
        button = Gtk.Button(label='!')
        button.add_css_class('spark-flat')
        button.set_tooltip_text(tr('notifications'))
        button.connect('clicked', self._open)
        self.buttons.append(button)
        self.refresh()
        return button

    def refresh(self):
        count = len(self.server.history)
        for button in self.buttons:
            if self.server.dnd:
                button.set_label('z')
            elif count:
                button.set_label('! %d' % count)
            else:
                button.set_label('!')

    def _open(self, button):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(360, -1)
        head = Gtk.Box(spacing=8)
        title = Gtk.Label(label=tr('notifications').upper(), xalign=0, hexpand=True)
        title.add_css_class('spark-label')
        head.append(title)
        dnd = Gtk.Switch(active=self.server.dnd, valign=Gtk.Align.CENTER)
        dnd.connect('notify::active', lambda s, _p: (self.server.set_dnd(s.get_active()),
                                                      self.refresh()))
        label = Gtk.Label(label=tr('dnd'))
        label.add_css_class('spark-dim')
        head.append(label)
        head.append(dnd)
        box.append(head)
        pop = Gtk.Popover()
        pop.add_css_class('spark-pop')
        pop.set_parent(button)
        pop.set_has_arrow(False)
        history = list(reversed(self.server.history))
        if not history:
            empty = Gtk.Label(label=tr('no_notifications'), xalign=0)
            empty.add_css_class('spark-dim')
            box.append(empty)
        else:
            lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for n in history[:30]:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                row.add_css_class('spark-card')
                when = Gtk.Label(label='%s  %s' % (time.strftime('%H:%M', time.localtime(n.when)),
                                                    (n.app or '').upper()), xalign=0)
                when.add_css_class('app')
                summary = Gtk.Label(label=n.summary, xalign=0, wrap=True, max_width_chars=44)
                summary.add_css_class('title')
                row.append(when)
                row.append(summary)
                if n.body:
                    body = Gtk.Label(label=n.body[:200], xalign=0, wrap=True, max_width_chars=44)
                    body.add_css_class('body')
                    row.append(body)
                row.set_cursor_from_name('pointer')
                click = Gtk.GestureClick()
                click.connect('released', lambda *_, n=n: self._clicked(n, pop))
                row.add_controller(click)
                lst.append(row)
            scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=420)
            scroll.set_child(lst)
            box.append(scroll)
            clear = Gtk.Button(label=tr('clear'))
            clear.add_css_class('spark-btn')
            clear.connect('clicked', lambda *_: (self.server.clear_history(), pop.popdown()))
            box.append(clear)
        pop.set_child(box)
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _clicked(self, n, pop):
        pop.popdown()
        open_notification(n, self.server)
        self.server.remove_from_history(n.id)


class NotificationsUI:
    def __init__(self, server, tracker=None):
        global _tracker
        _tracker = tracker
        self.toasts = Toasts(server)
        self._bell = Bell(server)

    def bell(self):
        return self._bell.make()
