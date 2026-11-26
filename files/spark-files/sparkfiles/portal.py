"""Spark Files as an XDG desktop portal backend: the file chooser and the "Open with" picker.

Apps that ask for a file through the portal (Flatpak apps, Firefox and Chrome, Electron apps,
anything with GTK_USE_PORTAL or Qt's xdgdesktopportal theme) reach xdg-desktop-portal, which
hands the job to a backend. In the Spark session spark-portals.conf points FileChooser and
AppChooser here (org.freedesktop.impl.portal.desktop.spark); everything else (screenshots,
screen sharing, shortcuts, settings) stays with the other portal backends.

The parsing and the answers are plain functions (tested without a bus or a screen); Service
runs in the GLib thread of gloop.Bridge and asks the Tk side for a window."""

import fnmatch
import os
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from .core import log

try:
    from gi.repository import Gio, GLib
except Exception:                                       # noqa: BLE001
    Gio = GLib = None

PORTAL_NAME = 'org.freedesktop.impl.portal.desktop.spark'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
FC_IFACE = 'org.freedesktop.impl.portal.FileChooser'
AC_IFACE = 'org.freedesktop.impl.portal.AppChooser'
REQUEST_IFACE = 'org.freedesktop.impl.portal.Request'

OK, CANCELLED, ENDED = 0, 1, 2           # the portal's response codes

PORTAL_XML = f"""
<node>
  <interface name="{FC_IFACE}">
    <property name="version" type="u" access="read"/>
    <method name="OpenFile">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/>
    </method>
    <method name="SaveFile">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/>
    </method>
    <method name="SaveFiles">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/>
    </method>
  </interface>
  <interface name="{AC_IFACE}">
    <property name="version" type="u" access="read"/>
    <method name="ChooseApplication">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="as" name="choices" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/>
    </method>
    <method name="UpdateChoices">
      <arg type="o" name="handle" direction="in"/>
      <arg type="as" name="choices" direction="in"/>
    </method>
  </interface>
</node>
"""

REQUEST_XML = f"""
<node>
  <interface name="{REQUEST_IFACE}">
    <method name="Close"/>
  </interface>
</node>
"""

VERSIONS = {FC_IFACE: 4, AC_IFACE: 2}


# ─── what the app asked for ──────────────────────────────────

class Filter:
    """One line of the "file type" menu: a name and its patterns, kept as the app sent them
    (they go back as current_filter)."""

    def __init__(self, name: str, patterns: List[Tuple[int, str]]):
        self.name = name
        self.patterns = [(int(kind), str(p)) for kind, p in patterns]

    def raw(self) -> Tuple[str, List[Tuple[int, str]]]:
        return (self.name, list(self.patterns))

    def matches(self, name: str, mime: Optional[str] = None) -> bool:
        """Glob patterns (kind 0) are matched without caring about case, as other file choosers'
        dialogs do in practice; MIME patterns (kind 1) may end in /*."""
        low = name.casefold()
        for kind, pattern in self.patterns:
            if kind == 0:
                if fnmatch.fnmatchcase(low, pattern.casefold()):
                    return True
            elif mime is not None and fnmatch.fnmatchcase(mime, pattern.casefold()):
                return True
        return False

    @property
    def uses_mime(self) -> bool:
        return any(kind == 1 for kind, _p in self.patterns)

    def __eq__(self, other) -> bool:
        return isinstance(other, Filter) and other.raw() == self.raw()

    def __repr__(self) -> str:
        return f'Filter({self.name!r}, {self.patterns!r})'


class Choice:
    """An extra the app adds under the file list: a checkbox (no options; 'true'/'false')
    or a menu of (id, label) options."""

    def __init__(self, cid: str, label: str, options: List[Tuple[str, str]], initial: str):
        self.id, self.label, self.options = cid, label, [(str(a), str(b)) for a, b in options]
        if self.options:
            ids = [o[0] for o in self.options]
            self.value = initial if initial in ids else ids[0]
        else:
            self.value = 'true' if initial == 'true' else 'false'

    @property
    def is_check(self) -> bool:
        return not self.options


class Ask:
    """One file chooser request, from its a{sv} options."""

    def __init__(self, method: str, title: str, options: dict):
        self.method = method                     # OpenFile, SaveFile or SaveFiles
        self.title = title or ''
        self.accept_label = _text(options.get('accept_label'))
        self.multiple = bool(options.get('multiple', False)) and method == 'OpenFile'
        self.directory = (bool(options.get('directory', False)) and method == 'OpenFile'
                          ) or method == 'SaveFiles'
        self.filters = [Filter(n, p) for n, p in options.get('filters') or []]
        current = options.get('current_filter')
        self.current_filter: Optional[Filter] = None
        if current:
            want = Filter(*current)
            self.current_filter = next((f for f in self.filters if f == want), want)
            if self.current_filter not in self.filters:
                self.filters.insert(0, self.current_filter)
        elif self.filters:
            self.current_filter = self.filters[0]
        self.choices = [Choice(*c) for c in options.get('choices') or []]
        self.current_name = _text(options.get('current_name'))
        self.current_folder = path_from_bytes(options.get('current_folder'))
        self.current_file = path_from_bytes(options.get('current_file'))
        self.files = [os.path.basename(p) for p in
                      (path_from_bytes(b) for b in options.get('files') or []) if p]
        if method == 'SaveFile' and self.current_file and not self.current_name:
            self.current_name = os.path.basename(self.current_file)

    @property
    def saving(self) -> bool:
        return self.method != 'OpenFile'

    def start_folder(self, fallback: str) -> str:
        for p in (self.current_folder,
                  os.path.dirname(self.current_file) if self.current_file else ''):
            if p and os.path.isdir(p):
                return p
        return fallback

    def shows(self, name: str, is_dir: bool, mime: Optional[str] = None,
              active: Optional[Filter] = None) -> bool:
        """Folders always show (you walk through them); files only when they match the chosen
        file type, and not at all when the app wants a folder."""
        if is_dir:
            return True
        if self.directory:
            return False
        f = active if active is not None else self.current_filter
        return f is None or f.matches(name, mime)


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (bytes, bytearray)):
        return path_from_bytes(value)
    return str(value)


def path_from_bytes(value) -> str:
    """The portal sends paths as NUL-terminated byte strings (ay)."""
    if not value:
        return ''
    if isinstance(value, str):
        return value
    raw = bytes(value).split(b'\0', 1)[0]
    return os.fsdecode(raw)


def file_uri(path: str) -> str:
    return 'file://' + quote(os.path.abspath(path), safe="/!$&'()*+,;=:@~-._")


def uri_path(uri: str) -> str:
    u = urlparse(uri)
    return unquote(u.path) if u.scheme in ('', 'file') else ''


def save_targets(folder: str, names: List[str]) -> List[str]:
    """SaveFiles: the app proposes names, the person picks a folder."""
    return [os.path.join(folder, n) for n in names]


# ─── the answers ─────────────────────────────────────────────

def file_results(ask: Ask, paths: List[str], active: Optional[Filter] = None,
                 choices: Optional[List[Choice]] = None):
    """(response, results) for the FileChooser methods, as Python values; to_variant()
    makes the a{sv}. An empty list of paths is a cancel."""
    if not paths:
        return CANCELLED, {}
    results: Dict[str, Tuple[str, object]] = {'uris': ('as', [file_uri(p) for p in paths])}
    f = active if active is not None else ask.current_filter
    if f is not None and ask.filters:
        results['current_filter'] = ('(sa(us))', f.raw())
    picked = choices if choices is not None else ask.choices
    if picked:
        results['choices'] = ('a(ss)', [(c.id, c.value) for c in picked])
    if ask.method == 'OpenFile':
        results['writable'] = ('b', True)
    return OK, results


def app_results(app_id: Optional[str], token: str = ''):
    if not app_id:
        return CANCELLED, {}
    results = {'choice': ('s', app_id[:-8] if app_id.endswith('.desktop') else app_id)}
    if token:
        results['activation_token'] = ('s', token)
    return OK, results


def to_variant(response: int, results: dict):
    return GLib.Variant('(ua{sv})', (response, {k: GLib.Variant(sig, v)
                                                for k, (sig, v) in results.items()}))


# ─── the bus side (GLib thread) ──────────────────────────────

class Service:
    """Owns org.freedesktop.impl.portal.desktop.spark. on_file(ask, parent, reply) and
    on_app(choices, options, reply) run in Tk's thread and must call reply(response,
    results) exactly once (a second call is ignored); they return a close() callable for
    when the portal gives up on the request, or None."""

    def __init__(self, bridge, on_file: Callable, on_app: Callable,
                 on_app_update: Optional[Callable] = None):
        self.bridge = bridge
        self.on_file, self.on_app, self.on_app_update = on_file, on_app, on_app_update
        self.owns = False
        self._node = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
        self._req_node = Gio.DBusNodeInfo.new_for_xml(REQUEST_XML)
        self._open: Dict[str, dict] = {}                # handle → request state

    def start(self) -> int:
        """Call in the GLib thread. Returns the bus_own_name id."""
        def bus_acquired(conn, _name):
            for iface in self._node.interfaces:
                try:
                    rid = conn.register_object(PORTAL_PATH, iface, self._call,
                                               self._get_property, None)
                    self.bridge._exported.append((conn, rid))
                except Exception as exc:                # noqa: BLE001
                    log.warning("could not register the portal: %s", exc)

        def acquired(_conn, _name):
            self.owns = True
            log.info("own %s", PORTAL_NAME)

        def lost(_conn, _name):
            self.owns = False
            log.info("don't own %s (another program has it)", PORTAL_NAME)

        return Gio.bus_own_name(Gio.BusType.SESSION, PORTAL_NAME,
                                Gio.BusNameOwnerFlags.NONE, bus_acquired, acquired, lost)

    def _get_property(self, _conn, _sender, _path, iface, prop):
        if prop == 'version':
            return GLib.Variant('u', VERSIONS.get(iface, 1))
        return None

    def _call(self, conn, _sender, _path, iface, method, params, invocation):
        args = params.unpack()
        if iface == AC_IFACE and method == 'UpdateChoices':
            handle, choices = args
            invocation.return_value(None)
            if self.on_app_update and handle in self._open:
                self.bridge.post(lambda: self.on_app_update(handle, list(choices)))
            return
        handle = args[0]
        state = {'invocation': invocation, 'conn': conn, 'rid': None, 'close': None}
        self._open[handle] = state
        try:
            state['rid'] = conn.register_object(handle, self._req_node.interfaces[0],
                                                self._request_call, None, None)
        except Exception as exc:                        # noqa: BLE001
            log.debug("request object %s: %s", handle, exc)

        def reply(response, results):
            self.bridge.in_glib(lambda: self._finish(handle, response, results))

        if iface == FC_IFACE:
            _h, app_id, parent, title, options = args
            try:
                ask = Ask(method, title, options)
            except Exception as exc:                    # noqa: BLE001
                log.warning("file chooser options from %s: %s", app_id, exc)
                self._finish(handle, ENDED, {})
                return
            ask.app_id = app_id

            def show():
                state['close'] = self.on_file(ask, parent, reply)
            self.bridge.post(show)
        else:
            _h, app_id, parent, choices, options = args

            def show():
                state['close'] = self.on_app(handle, list(choices), dict(options), parent,
                                             reply)
            self.bridge.post(show)

    def _request_call(self, _conn, _sender, _path, _iface, method, _params, invocation):
        handle = _path
        invocation.return_value(None)
        if method != 'Close':
            return
        state = self._open.get(handle)
        if state is None:
            return
        close = state.get('close')
        if close:
            self.bridge.post(close)
        self._finish(handle, ENDED, {})

    def _finish(self, handle: str, response: int, results: dict) -> None:
        state = self._open.pop(handle, None)
        if state is None:
            return                                      # answered already
        if state['rid'] is not None:
            try:
                state['conn'].unregister_object(state['rid'])
            except Exception:                           # noqa: BLE001
                pass
        try:
            state['invocation'].return_value(to_variant(response, results))
            state['conn'].flush_sync(None)      # the process may quit right after this
        except Exception as exc:                        # noqa: BLE001
            log.warning("portal reply: %s", exc)


class AppChooserAnswer:
    """The list AppChooser shows: the portal's choices, the last app used picked first."""

    def __init__(self, choices: List[str], last_choice: str = ''):
        self.choices = list(choices)
        self.last_choice = last_choice[:-8] if last_choice.endswith('.desktop') else last_choice

    def first_index(self, shown_ids: List[str]) -> int:
        for i, app_id in enumerate(shown_ids):
            bare = app_id[:-8] if app_id.endswith('.desktop') else app_id
            if self.last_choice and bare == self.last_choice:
                return i
        return 0
