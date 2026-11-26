"""The desktop's ScreenCast portal: the only way a Wayland program may watch the screen. In
the Spark session it asks once which screen to share; the answer is remembered through a restore token
(portal.json), so later starts are silent.

Written after Spark Snip's client, kept here so the app stays self-contained. Blocking: run
start() on a worker thread. The stream stays open for as long as the session does, so keep
the ScreenCastPortal object until the recording ends and call close() then."""

import secrets
import time
from typing import Any, Callable, Dict, NamedTuple, Optional

from .core import log
from .text import t

PORTAL_BUS = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
SCREENCAST = 'org.freedesktop.portal.ScreenCast'
PORTAL_TIMEOUT = 180            # the user may take a while in the share dialog


class PortalError(Exception):
    pass


class PortalCancelled(PortalError):
    pass


class PortalStream(NamedTuple):
    fd: int
    node: int
    props: Dict[str, Any]
    session: str
    restore_token: Optional[str]


class ScreenCastPortal:
    """org.freedesktop.portal.ScreenCast over D-Bus, through PyGObject's Gio.

    Blocking: run start() on a worker thread. Each request answers with a Response signal
    on a Request object, so the thread iterates its own GLib main context while waiting.
    """

    def __init__(self):
        try:
            import gi
            gi.require_version('Gio', '2.0')
            from gi.repository import Gio, GLib
        except (ImportError, ValueError) as exc:
            raise PortalError(t('rec.no_gi')) from exc
        self.Gio, self.GLib = Gio, GLib
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as exc:                    # noqa: BLE001 - GLib.Error
            raise PortalError(t('rec.no_bus', error=exc)) from exc
        self.sender = self.bus.get_unique_name()[1:].replace('.', '_')
        self.session: Optional[str] = None
        self.cancelled = False

    def _call(self, method: str, params, reply: Optional[str] = None,
              interface: str = SCREENCAST, path: str = PORTAL_PATH):
        GLib = self.GLib
        return self.bus.call_sync(PORTAL_BUS, path, interface, method, params,
                                  GLib.VariantType(reply) if reply else None,
                                  self.Gio.DBusCallFlags.NONE, -1, None)

    def _property(self, name: str, default):
        try:
            value = self._call('Get', self.GLib.Variant('(ss)', (SCREENCAST, name)), '(v)',
                               interface='org.freedesktop.DBus.Properties')
            return value.unpack()[0]
        except Exception:                           # noqa: BLE001 - old portal
            return default

    def _request(self, method: str, build: Callable[[str], Any]) -> Dict[str, Any]:
        GLib, Gio = self.GLib, self.Gio
        token = 'sparkclips_' + secrets.token_hex(6)
        path = f'{PORTAL_PATH}/request/{self.sender}/{token}'
        context = GLib.MainContext.new()
        context.push_thread_default()
        box: Dict[str, Any] = {}

        def on_response(_conn, _sender, _path, _iface, _signal, params, *_):
            box['response'] = params.unpack()

        try:
            sub = self.bus.signal_subscribe(PORTAL_BUS, 'org.freedesktop.portal.Request',
                                            'Response', path, None,
                                            Gio.DBusSignalFlags.NONE, on_response)
            try:
                self._call(method, build(token))
                deadline = time.monotonic() + PORTAL_TIMEOUT
                while 'response' not in box:
                    if self.cancelled:
                        raise PortalCancelled("cancelled")
                    if time.monotonic() > deadline:
                        raise PortalError(t('rec.no_answer'))
                    if not context.iteration(False):
                        time.sleep(0.02)
            finally:
                self.bus.signal_unsubscribe(sub)
        except PortalError:
            raise
        except Exception as exc:                    # noqa: BLE001 - GLib.Error from D-Bus
            raise PortalError(t('rec.portal', error=exc)) from exc
        finally:
            context.pop_thread_default()
        code, results = box['response']
        if code == 1:
            raise PortalCancelled(t('rec.declined'))
        if code != 0:
            raise PortalError(t('rec.refused'))
        return results

    def start(self, restore_token: Optional[str]) -> PortalStream:
        GLib = self.GLib
        version = self._property('version', 1)
        cursors = self._property('AvailableCursorModes', 1)
        log.info("ScreenCast portal version=%s cursor modes=%s", version, cursors)

        def v(kind, value):
            return GLib.Variant(kind, value)

        session_token = 'sparkclips_' + secrets.token_hex(6)
        created = self._request('CreateSession', lambda t: v('(a{sv})', (
            {'handle_token': v('s', t), 'session_handle_token': v('s', session_token)},)))
        self.session = str(created['session_handle'])

        def select(token: str):
            options = {'handle_token': v('s', token), 'types': v('u', 1),       # monitors
                       'multiple': v('b', False)}
            if cursors & 2:
                options['cursor_mode'] = v('u', 2)                            # embedded
            if version >= 4:
                options['persist_mode'] = v('u', 2)                           # until revoked
                if restore_token:
                    options['restore_token'] = v('s', restore_token)
            return v('(oa{sv})', (self.session, options))

        self._request('SelectSources', select)
        started = self._request('Start', lambda t: v('(osa{sv})', (
            self.session, '', {'handle_token': v('s', t)})))
        streams = started.get('streams') or []
        if not streams:
            raise PortalError(t('rec.no_screen'))
        node, props = streams[0]
        result, fds = self.bus.call_with_unix_fd_list_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST, 'OpenPipeWireRemote',
            v('(oa{sv})', (self.session, {})), GLib.VariantType('(h)'),
            self.Gio.DBusCallFlags.NONE, -1, None, None)
        fd = fds.get(result.unpack()[0])
        log.info("portal stream node=%s props=%s", node, props)
        return PortalStream(fd, int(node), dict(props), self.session,
                            started.get('restore_token'))

    def close(self):
        self.cancelled = True
        if self.session:
            try:
                self._call('Close', None, interface='org.freedesktop.portal.Session',
                           path=self.session)
            except Exception:                       # noqa: BLE001 - already gone
                pass
            self.session = None
