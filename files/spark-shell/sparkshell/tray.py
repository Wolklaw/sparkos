"""The tray, without any toolkit: StatusNotifierWatcher, StatusNotifierHost, the items and their
com.canonical.dbusmenu menus. The panel (trayui.py) only draws what this module holds.

The watcher is owned here when nobody else owns org.kde.StatusNotifierWatcher; if kded or
another shell already does, the host registers with that one instead, so it works either way."""

import logging
import os

from gi.repository import Gio, GLib

from .dbusutil import call, emit, export, get_all

log = logging.getLogger('spark-shell')

WATCHER_NAME = 'org.kde.StatusNotifierWatcher'
WATCHER_PATH = '/StatusNotifierWatcher'
ITEM_IFACE = 'org.kde.StatusNotifierItem'
MENU_IFACE = 'com.canonical.dbusmenu'

WATCHER_XML = """
<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem"><arg type="s" name="service" direction="in"/></method>
    <method name="RegisterStatusNotifierHost"><arg type="s" name="service" direction="in"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
    <signal name="StatusNotifierHostUnregistered"/>
  </interface>
</node>
"""


def split_service(service: str, sender: str):
    """What an item gave RegisterStatusNotifierItem -> (bus name, object path).
    'org.x.Item-1' -> (that, /StatusNotifierItem); '/Path' -> (sender, /Path);
    'name/Path' -> (name, /Path)."""
    if service.startswith('/'):
        return sender, service
    if '/' in service:
        name, rest = service.split('/', 1)
        return name, '/' + rest
    return service, '/StatusNotifierItem'


def clean_label(label: str) -> str:
    """dbusmenu labels mark the mnemonic with an underscore ('_Quit', '__' is a real one)."""
    out, i = [], 0
    while i < len(label):
        if label[i] == '_':
            if i + 1 < len(label) and label[i + 1] == '_':
                out.append('_')
                i += 1
        else:
            out.append(label[i])
        i += 1
    return ''.join(out)


class MenuNode:
    """One entry of a dbusmenu layout."""

    def __init__(self, ident, props, children):
        self.id = ident
        self.props = props
        self.children = children

    @property
    def label(self):
        return clean_label(str(self.props.get('label', '')))

    @property
    def visible(self):
        return bool(self.props.get('visible', True))

    @property
    def enabled(self):
        return bool(self.props.get('enabled', True))

    @property
    def separator(self):
        return self.props.get('type') == 'separator'

    @property
    def toggle(self):
        kind = self.props.get('toggle-type') or ''
        if kind in ('checkmark', 'radio'):
            return kind, int(self.props.get('toggle-state', 0)) == 1
        return None

    @property
    def has_submenu(self):
        return self.props.get('children-display') == 'submenu' or bool(self.children)

    @property
    def icon_name(self):
        return self.props.get('icon-name') or ''


def parse_layout(layout) -> MenuNode:
    """The (id, props, children) tuple GetLayout returns, with children nested the same way."""
    ident, props, children = layout
    kids = []
    for child in children:
        if isinstance(child, (tuple, list)) and len(child) == 3:
            kids.append(parse_layout(child))
    return MenuNode(int(ident), dict(props), kids)


class DBusMenu:
    """Client for one item's menu."""

    def __init__(self, conn, bus_name, path):
        self.conn, self.bus_name, self.path = conn, bus_name, path

    def get_layout(self, callback, parent=0, depth=-1):
        """callback(MenuNode or None)."""
        def done(result, error):
            if error or not result:
                log.warning('menu %s%s: %s', self.bus_name, self.path, error)
                callback(None)
                return
            try:
                callback(parse_layout(result[1]))
            except Exception:
                log.exception('menu layout of %s', self.bus_name)
                callback(None)
        call(self.conn, self.bus_name, self.path, MENU_IFACE, 'GetLayout', 'iias',
             (parent, depth, []), done, '(u(ia{sv}av))')

    def about_to_show(self, ident, callback=None):
        call(self.conn, self.bus_name, self.path, MENU_IFACE, 'AboutToShow', 'i', (ident,),
             (lambda r, e: callback(r[0] if r else False)) if callback else None, '(b)')

    def event(self, ident, name='clicked'):
        params = GLib.Variant('(isvu)', (ident, name, GLib.Variant('i', 0),
                                         GLib.get_real_time() // 1000 & 0xFFFFFFFF))
        self.conn.call(self.bus_name, self.path, MENU_IFACE, 'Event', params, None,
                       Gio.DBusCallFlags.NONE, 3000, None, None)


class TrayItem:
    """One StatusNotifierItem, with its properties kept up to date."""

    def __init__(self, host, key, bus_name, path):
        self.host, self.key, self.bus_name, self.path = host, key, bus_name, path
        self.props = {}
        self.ready = False
        self._subs = []
        conn = host.conn
        self._subs.append(conn.signal_subscribe(
            bus_name, ITEM_IFACE, None, path, None, Gio.DBusSignalFlags.NONE, self._on_signal))
        self.reload()

    # properties --------------------------------------------------------------------------
    def reload(self):
        get_all(self.host.conn, self.bus_name, self.path, ITEM_IFACE, self._loaded)

    def _loaded(self, props, error):
        if error:
            log.warning('tray item %s: %s', self.key, error.message)
            if not self.ready:
                self.host.drop(self.key)
            return
        self.props = props
        first = not self.ready
        self.ready = True
        self.host.item_changed(self, first)

    def _on_signal(self, conn, sender, path, iface, signal, params):
        if signal.startswith('New'):
            self.reload()

    @property
    def id(self):
        return str(self.props.get('Id') or self.key)

    @property
    def title(self):
        tip = self.tooltip_title
        return str(self.props.get('Title') or tip or self.props.get('Id') or '')

    @property
    def status(self):
        return str(self.props.get('Status') or 'Active')

    @property
    def category(self):
        return str(self.props.get('Category') or 'ApplicationStatus')

    @property
    def icon_name(self):
        if self.status == 'NeedsAttention' and self.props.get('AttentionIconName'):
            return str(self.props['AttentionIconName'])
        return str(self.props.get('IconName') or '')

    @property
    def icon_theme_path(self):
        return str(self.props.get('IconThemePath') or '')

    @property
    def pixmaps(self):
        """[(width, height, argb32 bytes)], the largest last."""
        raw = self.props.get('AttentionIconPixmap') if self.status == 'NeedsAttention' \
            and self.props.get('AttentionIconPixmap') else self.props.get('IconPixmap')
        out = []
        for entry in raw or []:
            try:
                w, h, data = entry
                if w > 0 and h > 0 and len(data) >= w * h * 4:
                    out.append((int(w), int(h), bytes(data)))
            except (TypeError, ValueError):
                continue
        return sorted(out, key=lambda p: p[0] * p[1])

    @property
    def tooltip_title(self):
        tip = self.props.get('ToolTip')
        try:
            return str(tip[2] or '')
        except (TypeError, IndexError):
            return ''

    @property
    def menu_path(self):
        menu = self.props.get('Menu')
        return str(menu) if menu and str(menu) != '/' else ''

    @property
    def item_is_menu(self):
        return bool(self.props.get('ItemIsMenu'))

    def menu(self):
        return DBusMenu(self.host.conn, self.bus_name, self.menu_path) if self.menu_path else None

    # actions -----------------------------------------------------------------------------
    def _act(self, method, x=0, y=0):
        params = GLib.Variant('(ii)', (int(x), int(y)))
        self.host.conn.call(self.bus_name, self.path, ITEM_IFACE, method, params, None,
                            Gio.DBusCallFlags.NONE, 3000, None, None)

    def activate(self, x=0, y=0):
        self._act('Activate', x, y)

    def secondary_activate(self, x=0, y=0):
        self._act('SecondaryActivate', x, y)

    def context_menu(self, x=0, y=0):
        self._act('ContextMenu', x, y)

    def scroll(self, delta, orientation='vertical'):
        params = GLib.Variant('(is)', (int(delta), orientation))
        self.host.conn.call(self.bus_name, self.path, ITEM_IFACE, 'Scroll', params, None,
                            Gio.DBusCallFlags.NONE, 3000, None, None)

    def close(self):
        for sub in self._subs:
            self.host.conn.signal_unsubscribe(sub)
        self._subs = []


class TrayHost:
    """Watcher (if free) and host. Callbacks, set by the panel:
    on_added(item), on_removed(item), on_changed(item)."""

    def __init__(self, conn, own_watcher=True):
        self.conn = conn
        self.items = {}              # key -> TrayItem
        self.order = []              # keys, registration order
        self.registered = []         # watcher's own list (owner mode)
        self.owns_watcher = False
        self.on_added = self.on_removed = self.on_changed = lambda item: None
        self._watches = {}
        self._own_watcher = own_watcher
        self._host_id = 0
        self._watcher_sub = 0

    # start-up ----------------------------------------------------------------------------
    def start(self):
        if self._own_watcher:
            Gio.bus_own_name_on_connection(
                self.conn, WATCHER_NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                self._got_watcher, self._no_watcher)
        else:
            self._use_existing_watcher()

    def _got_watcher(self, conn, name):
        self.owns_watcher = True
        export(conn, WATCHER_PATH, WATCHER_XML, self._watcher_call, {
            ('org.kde.StatusNotifierWatcher', 'RegisteredStatusNotifierItems'):
                lambda: list(self.registered),
            ('org.kde.StatusNotifierWatcher', 'IsStatusNotifierHostRegistered'): True,
            ('org.kde.StatusNotifierWatcher', 'ProtocolVersion'): 0,
        })
        emit(conn, WATCHER_PATH, WATCHER_NAME, 'StatusNotifierHostRegistered', '')
        log.info('tray: owns %s', WATCHER_NAME)

    def _no_watcher(self, conn, name):
        if not self.owns_watcher:
            log.info('tray: %s is taken, using that watcher', WATCHER_NAME)
            self._use_existing_watcher()

    def _watcher_call(self, interface, method, args, sender):
        if method == 'RegisterStatusNotifierItem':
            self.register(args[0], sender)
        elif method == 'RegisterStatusNotifierHost':
            pass    # we are the only host that matters; the flag is always true
        return None

    def _use_existing_watcher(self):
        name = 'org.kde.StatusNotifierHost-%d-1' % os.getpid()
        Gio.bus_own_name_on_connection(self.conn, name, Gio.BusNameOwnerFlags.NONE, None, None)
        call(self.conn, WATCHER_NAME, WATCHER_PATH, WATCHER_NAME, 'RegisterStatusNotifierHost',
             's', (name,))
        self._watcher_sub = self.conn.signal_subscribe(
            WATCHER_NAME, WATCHER_NAME, 'StatusNotifierItemRegistered', WATCHER_PATH, None,
            Gio.DBusSignalFlags.NONE,
            lambda c, s, p, i, sig, params: self._adopt(params.unpack()[0]))
        self.conn.signal_subscribe(
            WATCHER_NAME, WATCHER_NAME, 'StatusNotifierItemUnregistered', WATCHER_PATH, None,
            Gio.DBusSignalFlags.NONE,
            lambda c, s, p, i, sig, params: self.drop(self._key_of(params.unpack()[0])))

        def listed(props, error):
            for service in (props or {}).get('RegisteredStatusNotifierItems') or []:
                self._adopt(service)
        get_all(self.conn, WATCHER_NAME, WATCHER_PATH, WATCHER_NAME, listed)

    @staticmethod
    def _key_of(service):
        name, path = split_service(service, '')
        return name + path

    def _adopt(self, service):
        name, path = split_service(service, '')
        if name:
            self._add(name, path)

    # items -------------------------------------------------------------------------------
    def register(self, service, sender):
        name, path = split_service(service, sender)
        key = self._add(name, path)
        if self.owns_watcher and key not in self.registered:
            self.registered.append(key)
            emit(self.conn, WATCHER_PATH, WATCHER_NAME, 'StatusNotifierItemRegistered', 's', key)
            self.conn.emit_signal(None, WATCHER_PATH, 'org.freedesktop.DBus.Properties',
                                  'PropertiesChanged', GLib.Variant('(sa{sv}as)', (
                                      WATCHER_NAME, {'RegisteredStatusNotifierItems':
                                                     GLib.Variant('as', list(self.registered))},
                                      [])))

    def _add(self, name, path):
        key = name + path
        if key in self.items:
            return key
        item = TrayItem(self, key, name, path)
        self.items[key] = item
        self.order.append(key)
        self._watches[key] = Gio.bus_watch_name_on_connection(
            self.conn, name, Gio.BusNameWatcherFlags.NONE, None,
            lambda c, n, k=key: self.drop(k))
        return key

    def item_changed(self, item, first):
        if first:
            self.on_added(item)
        else:
            self.on_changed(item)

    def drop(self, key):
        item = self.items.pop(key, None)
        if key in self.order:
            self.order.remove(key)
        watch = self._watches.pop(key, None)
        if watch:
            Gio.bus_unwatch_name(watch)
        if item is None:
            return
        item.close()
        if key in self.registered:
            self.registered.remove(key)
            emit(self.conn, WATCHER_PATH, WATCHER_NAME, 'StatusNotifierItemUnregistered', 's',
                 key)
        if item.ready:
            self.on_removed(item)

    def visible_items(self):
        """Items to show now: ready, and not Passive."""
        return [self.items[k] for k in self.order
                if k in self.items and self.items[k].ready and self.items[k].status != 'Passive']
