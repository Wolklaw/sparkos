"""org.freedesktop.Notifications server (Desktop Notifications Specification 1.2), without a
toolkit. The model keeps the notifications and the history; the UI (notifyui.py) draws them.

Supported: actions (and the default action), urgency, replaces_id, expire timeouts, body
markup, icons by name or path, inline images (image-data / image-path / icon_data), the
resident and transient hints, CloseNotification, do-not-disturb. History is kept in
~/.local/state/spark-shell/notifications.json (the last 100)."""

import json
import logging
import os
import tempfile
import time

from gi.repository import GLib

from . import VERSION
from .config import state_dir
from .dbusutil import DBusFail, emit, export

log = logging.getLogger('spark-shell')

NAME = 'org.freedesktop.Notifications'
PATH = '/org/freedesktop/Notifications'
HISTORY_MAX = 100
DEFAULT_TIMEOUT_MS = 6000

# closed reasons
EXPIRED, DISMISSED, CLOSED_BY_CALL, UNDEFINED = 1, 2, 3, 4

XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="GetCapabilities"><arg type="as" direction="out"/></method>
    <method name="Notify">
      <arg type="s" name="app_name" direction="in"/>
      <arg type="u" name="replaces_id" direction="in"/>
      <arg type="s" name="app_icon" direction="in"/>
      <arg type="s" name="summary" direction="in"/>
      <arg type="s" name="body" direction="in"/>
      <arg type="as" name="actions" direction="in"/>
      <arg type="a{sv}" name="hints" direction="in"/>
      <arg type="i" name="expire_timeout" direction="in"/>
      <arg type="u" direction="out"/>
    </method>
    <method name="CloseNotification"><arg type="u" name="id" direction="in"/></method>
    <method name="GetServerInformation">
      <arg type="s" direction="out"/><arg type="s" direction="out"/>
      <arg type="s" direction="out"/><arg type="s" direction="out"/>
    </method>
    <signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
    <signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
  </interface>
</node>
"""

CAPABILITIES = ['actions', 'body', 'body-markup', 'body-hyperlinks', 'icon-static',
                'persistence']


class Notification:
    def __init__(self, ident, app, icon, summary, body, actions, hints, timeout_ms, when=None):
        self.id = ident
        self.app = app
        self.icon = icon
        self.summary = summary
        self.body = body
        self.actions = actions          # [(key, label)]
        self.hints = hints
        self.timeout_ms = timeout_ms
        self.when = when or time.time()
        self.image = None               # (w, h, rowstride, has_alpha, bits, channels, bytes)

    @property
    def urgency(self):
        value = self.hints.get('urgency', 1)
        return value if value in (0, 1, 2) else 1

    @property
    def critical(self):
        return self.urgency == 2

    @property
    def transient(self):
        return bool(self.hints.get('transient'))

    @property
    def resident(self):
        return bool(self.hints.get('resident'))

    @property
    def desktop_entry(self):
        return str(self.hints.get('desktop-entry') or '')

    @property
    def image_path(self):
        return str(self.hints.get('image-path') or self.hints.get('image_path') or '')

    @property
    def effective_timeout(self):
        """Milliseconds until the pop-up goes away; 0 means it stays."""
        if self.critical:
            return 0
        if self.timeout_ms < 0:
            return DEFAULT_TIMEOUT_MS
        return self.timeout_ms

    def to_json(self):
        return {'id': self.id, 'app': self.app, 'icon': self.icon, 'summary': self.summary,
                'body': self.body, 'urgency': self.urgency, 'when': self.when,
                'desktop_entry': self.desktop_entry}


def parse_actions(flat):
    """['default', 'Open', 'reply', 'Reply'] -> [('default', 'Open'), ('reply', 'Reply')]."""
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]


class NotificationServer:
    """Callbacks, set by the UI: on_show(n) (pop it up), on_close(id, reason) (take it down)."""

    def __init__(self, conn, history_path=None):
        self.conn = conn
        self.next_id = 1
        self.active = {}               # id -> Notification, shown or waiting
        self.history = []              # Notification, newest last
        self.dnd = False
        self.on_show = lambda n: None
        self.on_close = lambda ident, reason: None
        self.on_history_changed = lambda: None
        self.history_path = history_path or os.path.join(state_dir(), 'notifications.json')
        self._timers = {}
        self._load_history()

    def start(self):
        export(self.conn, PATH, XML, self._call)

    # D-Bus -------------------------------------------------------------------------------
    def _call(self, interface, method, args, sender):
        if method == 'GetCapabilities':
            return (CAPABILITIES,)
        if method == 'GetServerInformation':
            return ('Spark Shell', 'Wolklaw', VERSION, '1.2')
        if method == 'CloseNotification':
            self.close(args[0], CLOSED_BY_CALL)
            return None
        if method == 'Notify':
            return (self.notify(*args),)
        raise DBusFail('unknown method ' + method, 'org.freedesktop.DBus.Error.UnknownMethod')

    def notify(self, app, replaces_id, icon, summary, body, actions, hints, timeout_ms):
        hints = dict(hints or {})
        if replaces_id and replaces_id in self.active:
            ident = replaces_id
        elif replaces_id and any(h.id == replaces_id for h in self.history):
            ident = replaces_id
        else:
            ident = self.next_id
            self.next_id += 1
            if self.next_id >= 0xFFFFFFFF:
                self.next_id = 1
        n = Notification(ident, app, icon or '', summary, body, parse_actions(actions), hints,
                         timeout_ms)
        data = hints.get('image-data') or hints.get('image_data') or hints.get('icon_data')
        if isinstance(data, (tuple, list)) and len(data) == 7:
            n.image = tuple(data)
        self.active[ident] = n
        self.history = [h for h in self.history if h.id != ident]
        if not n.transient:
            self.history.append(n)
            del self.history[:-HISTORY_MAX]
            self._save_history()
            self.on_history_changed()
        self._cancel_timer(ident)
        if self.dnd and not n.critical:
            self.active.pop(ident, None)       # kept in history only
            self.on_close(ident, UNDEFINED)
        else:
            self.on_show(n)
            timeout = n.effective_timeout
            if timeout > 0:
                self._timers[ident] = GLib.timeout_add(timeout, self._expire, ident)
        return ident

    def _expire(self, ident):
        self._timers.pop(ident, None)
        self.close(ident, EXPIRED)
        return False

    def _cancel_timer(self, ident):
        source = self._timers.pop(ident, None)
        if source:
            GLib.source_remove(source)

    # from the UI -------------------------------------------------------------------------
    def close(self, ident, reason=DISMISSED):
        """Take the pop-up down (it stays in history unless the sender asked for a close)."""
        self._cancel_timer(ident)
        n = self.active.pop(ident, None)
        if reason == CLOSED_BY_CALL:
            self.history = [h for h in self.history if h.id != ident]
            self._save_history()
            self.on_history_changed()
        if n is None and reason != CLOSED_BY_CALL:
            return
        self.on_close(ident, reason)
        emit(self.conn, PATH, NAME, 'NotificationClosed', 'uu', ident, reason)

    def invoke(self, ident, key):
        n = self.active.get(ident) or next((h for h in self.history if h.id == ident), None)
        emit(self.conn, PATH, NAME, 'ActionInvoked', 'us', ident, key)
        if n is not None and not n.resident:
            self.close(ident, DISMISSED)

    def remove_from_history(self, ident):
        self.history = [h for h in self.history if h.id != ident]
        self._save_history()
        self.on_history_changed()

    def clear_history(self):
        for ident in list(self.active):
            self.close(ident, DISMISSED)
        self.history = []
        self._save_history()
        self.on_history_changed()

    def set_dnd(self, on):
        self.dnd = bool(on)

    # history file ------------------------------------------------------------------------
    def _load_history(self):
        try:
            with open(self.history_path, encoding='utf-8') as f:
                rows = json.load(f)
        except (OSError, ValueError):
            return
        for row in rows[-HISTORY_MAX:] if isinstance(rows, list) else []:
            try:
                n = Notification(int(row['id']), str(row.get('app', '')), str(row.get('icon', '')),
                                 str(row.get('summary', '')), str(row.get('body', '')), [],
                                 {'urgency': int(row.get('urgency', 1)),
                                  'desktop-entry': str(row.get('desktop_entry', ''))}, -1,
                                 float(row.get('when', 0)))
            except (KeyError, TypeError, ValueError):
                continue
            self.history.append(n)
            self.next_id = max(self.next_id, n.id + 1)

    def _save_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.history_path), prefix='.n-')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump([h.to_json() for h in self.history], f)
            os.replace(tmp, self.history_path)
        except OSError as e:
            log.warning('notification history not saved: %s', e)
