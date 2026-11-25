"""A StatusNotifierItem and its dbusmenu, written straight on Gio so any tray that speaks the
protocol shows it: Plasma's today, the Spark shell's later. One bus name per item
(org.kde.StatusNotifierItem-<pid>-<n>), registered with the StatusNotifierWatcher whenever a
watcher is there. Hiding an item gives its name back, which removes it from the tray; showing
it takes the name again.

The icon is an icon-theme name, not pixels, so the tray draws it in the theme's colours."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from gi.repository import Gio, GLib

from .core import log

SNI_IFACE = 'org.kde.StatusNotifierItem'
WATCHER = 'org.kde.StatusNotifierWatcher'
WATCHER_PATH = '/StatusNotifierWatcher'
SNI_PATH = '/StatusNotifierItem'
MENU_PATH = '/MenuBar'
MENU_IFACE = 'com.canonical.dbusmenu'

SNI_XML = f"""
<node>
  <interface name="{SNI_IFACE}">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="ContextMenu"><arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/></method>
    <method name="Activate"><arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" name="x" direction="in"/><arg type="i" name="y" direction="in"/></method>
    <method name="Scroll"><arg type="i" name="delta" direction="in"/><arg type="s" name="orientation" direction="in"/></method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg type="s" name="status"/></signal>
  </interface>
</node>"""

MENU_XML = f"""
<node>
  <interface name="{MENU_IFACE}">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{{sv}}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{{sv}})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{{sv}})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
  </interface>
</node>"""


@dataclass
class MenuEntry:
    label: str = ''
    callback: Optional[Callable[[], None]] = None
    enabled: bool = True
    checked: Optional[bool] = None       # None: a plain entry; True/False: a check mark
    separator: bool = False


class Appearance:
    """What an item tells the tray. The tray app gives these as functions so they stay current."""

    def __init__(self, id_: str, category: str, title: Callable[[], str],
                 icon: Callable[[], str], tooltip: Callable[[], str],
                 menu: Callable[[], List[MenuEntry]],
                 activate: Callable[[int, int], None],
                 secondary: Callable[[], None] = lambda: None,
                 scroll: Callable[[int, str], None] = lambda d, o: None):
        self.id, self.category, self.title, self.icon = id_, category, title, icon
        self.tooltip, self.menu, self.activate = tooltip, menu, activate
        self.secondary, self.scroll = secondary, scroll


class StatusNotifierItem:
    _counter = 0

    def __init__(self, bus_conn: Gio.DBusConnection, look: Appearance):
        StatusNotifierItem._counter += 1
        self.conn, self.look = bus_conn, look
        self.name = f"org.kde.StatusNotifierItem-{_pid()}-{StatusNotifierItem._counter}"
        self.shown = False
        self.registered_with_watcher = False
        self._registering = False
        self.entries: List[MenuEntry] = []
        self._sent: Dict[str, Any] = {}           # what the panel was last told
        self.revision = 1
        self._own_id = 0
        self._objects: List[int] = []
        self._watch_id = 0
        self._sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        self._menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]

    # — showing and hiding —
    def show(self) -> None:
        if self.shown:
            return
        self.shown = True
        self._sent = {}
        self._objects = [
            self.conn.register_object(SNI_PATH, self._sni_info, self._sni_call, self._sni_get,
                                      None),
            self.conn.register_object(MENU_PATH, self._menu_info, self._menu_call,
                                      self._menu_get, None)]
        self.rebuild_menu()
        self._own_id = Gio.bus_own_name_on_connection(
            self.conn, self.name, Gio.BusNameOwnerFlags.NONE, self._acquired, None)
        self._watch_id = Gio.bus_watch_name_on_connection(
            self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE, self._watcher_up, self._watcher_down)

    def hide(self) -> None:
        if not self.shown:
            return
        self.shown = False
        if self._watch_id:
            Gio.bus_unwatch_name(self._watch_id)
        if self._own_id:
            Gio.bus_unown_name(self._own_id)
        for obj in self._objects:
            self.conn.unregister_object(obj)
        self._watch_id = self._own_id = 0
        self._objects = []
        self.registered_with_watcher = False

    def _acquired(self, *_args) -> None:
        self._register()

    def _watcher_up(self, *_args) -> None:
        self.registered_with_watcher = False
        self._register()

    def _watcher_down(self, *_args) -> None:
        self.registered_with_watcher = False

    def _register(self) -> None:
        if self.registered_with_watcher or self._registering or not self.shown:
            return
        self._registering = True

        def done(conn, res):
            self._registering = False
            try:
                conn.call_finish(res)
                self.registered_with_watcher = True
            except GLib.Error as exc:
                log.info("no StatusNotifierWatcher yet (%s)", exc.message)
        self.conn.call(WATCHER, WATCHER_PATH, WATCHER, 'RegisterStatusNotifierItem',
                       GLib.Variant('(s)', (self.name,)), None, Gio.DBusCallFlags.NONE, 2000,
                       None, done)

    # — telling the tray something changed —
    def _emit(self, iface: str, path: str, signal: str, params: Optional[GLib.Variant] = None):
        if not self.shown:
            return
        try:
            self.conn.emit_signal(None, path, iface, signal, params)
        except GLib.Error as exc:
            log.warning("could not emit %s: %s", signal, exc.message)

    def refresh(self) -> None:
        """Signal only what changed: each signal makes the panel read the properties back,
        and the tray rechecks every few seconds."""
        look = self.look
        icon, title = look.icon(), look.title()
        tip = (title, look.tooltip())
        if icon != self._sent.get('icon'):
            self._emit(SNI_IFACE, SNI_PATH, 'NewIcon')
        if tip != self._sent.get('tip'):
            self._emit(SNI_IFACE, SNI_PATH, 'NewToolTip')
        if title != self._sent.get('title'):
            self._emit(SNI_IFACE, SNI_PATH, 'NewTitle')
        self._sent.update(icon=icon, tip=tip, title=title)
        self.rebuild_menu()

    def rebuild_menu(self) -> None:
        self.entries = list(self.look.menu())       # always: the callbacks are new
        shape = [(e.label, e.enabled, e.checked, e.separator) for e in self.entries]
        if shape == self._sent.get('menu'):
            return
        self._sent['menu'] = shape
        self.revision += 1
        self._emit(MENU_IFACE, MENU_PATH, 'LayoutUpdated',
                   GLib.Variant('(ui)', (self.revision, 0)))

    # — org.kde.StatusNotifierItem —
    def _sni_get(self, _conn, _sender, _path, _iface, prop):
        look = self.look
        values = {
            'Category': GLib.Variant('s', look.category), 'Id': GLib.Variant('s', look.id),
            'Title': GLib.Variant('s', look.title()), 'Status': GLib.Variant('s', 'Active'),
            'WindowId': GLib.Variant('i', 0), 'IconName': GLib.Variant('s', look.icon()),
            'IconPixmap': GLib.Variant('a(iiay)', []),
            'OverlayIconName': GLib.Variant('s', ''),
            'OverlayIconPixmap': GLib.Variant('a(iiay)', []),
            'AttentionIconName': GLib.Variant('s', ''),
            'AttentionIconPixmap': GLib.Variant('a(iiay)', []),
            'AttentionMovieName': GLib.Variant('s', ''),
            'ToolTip': GLib.Variant('(sa(iiay)ss)', (look.icon(), [], look.title(),
                                                     look.tooltip())),
            'ItemIsMenu': GLib.Variant('b', False),
            'Menu': GLib.Variant('o', MENU_PATH),
        }
        return values.get(prop)

    def _sni_call(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        args = params.unpack()
        try:
            if method in ('Activate', 'ContextMenu'):
                # ContextMenu is only asked for by trays that don't read the Menu property
                (self.look.activate if method == 'Activate' else self._context)(*args)
            elif method == 'SecondaryActivate':
                self.look.secondary()
            elif method == 'Scroll':
                self.look.scroll(*args)
        except Exception:                                # noqa: BLE001 - a bad click mustn't kill the tray
            log.exception("%s failed", method)
        invocation.return_value(None)

    def _context(self, x: int, y: int) -> None:
        self.look.activate(x, y)

    # — com.canonical.dbusmenu —
    def _props(self, i: int) -> Dict[str, GLib.Variant]:
        e = self.entries[i - 1]
        if e.separator:
            return {'type': GLib.Variant('s', 'separator')}
        props = {'label': GLib.Variant('s', e.label),
                 'enabled': GLib.Variant('b', e.enabled)}
        if e.checked is not None:
            props['toggle-type'] = GLib.Variant('s', 'checkmark')
            props['toggle-state'] = GLib.Variant('i', 1 if e.checked else 0)
        return props

    def _layout(self) -> tuple:
        kids = [GLib.Variant('(ia{sv}av)', (i, self._props(i), []))
                for i in range(1, len(self.entries) + 1)]
        return (0, {'children-display': GLib.Variant('s', 'submenu')}, kids)

    def _menu_get(self, _conn, _sender, _path, _iface, prop):
        return {'Version': GLib.Variant('u', 3), 'TextDirection': GLib.Variant('s', 'ltr'),
                'Status': GLib.Variant('s', 'normal'),
                'IconThemePath': GLib.Variant('as', [])}.get(prop)

    def _menu_call(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        args = params.unpack()
        if method == 'GetLayout':
            invocation.return_value(GLib.Variant('(u(ia{sv}av))',
                                                 (self.revision, self._layout())))
        elif method == 'GetGroupProperties':
            ids = [i for i in (args[0] or range(1, len(self.entries) + 1))
                   if 1 <= i <= len(self.entries)]
            invocation.return_value(GLib.Variant('(a(ia{sv}))', ([(i, self._props(i))
                                                                  for i in ids],)))
        elif method == 'GetProperty':
            i, name = args
            props = self._props(i) if 1 <= i <= len(self.entries) else {}
            if name in props:
                invocation.return_value(GLib.Variant('(v)', (props[name],)))
            else:
                invocation.return_dbus_error('org.freedesktop.DBus.Error.InvalidArgs', name)
        elif method == 'Event':
            self._event(*args[:2])
            invocation.return_value(None)
        elif method == 'EventGroup':
            for i, kind, _data, _ts in args[0]:
                self._event(i, kind)
            invocation.return_value(GLib.Variant('(ai)', ([],)))
        elif method == 'AboutToShow':
            self.rebuild_menu()
            invocation.return_value(GLib.Variant('(b)', (True,)))
        elif method == 'AboutToShowGroup':
            self.rebuild_menu()
            invocation.return_value(GLib.Variant('(aiai)', ([0], [])))
        else:
            invocation.return_value(None)

    def _event(self, i: int, kind: str) -> None:
        if kind != 'clicked' or not 1 <= i <= len(self.entries):
            return
        entry = self.entries[i - 1]
        if entry.callback and entry.enabled and not entry.separator:
            try:
                entry.callback()
            except Exception:                            # noqa: BLE001
                log.exception("menu entry %r failed", entry.label)


def _pid() -> int:
    import os
    return os.getpid()
