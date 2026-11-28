"""spark-portal: the Spark session's xdg-desktop-portal backend, org.freedesktop.impl.portal.desktop.sparkos.

xdg-desktop-portal hands what apps ask for to backends. In the Spark session this one answers
settings (dark, the accent, fonts and themes), inhibit (suspend, idle, logout), notifications,
the access, account and email questions, launcher install, lockdown and printing. File choosers
are Spark Files', screen capture is xdg-desktop-portal-wlr's, secrets are Spark Secrets'.

  Settings       the values come from portal_logic.SettingsStore
  Inhibit        suspend and logout take a logind "delay" inhibitor (the file descriptor is kept
                 until the request is closed or the caller leaves the bus): the app gets a few
                 seconds to save before the PC sleeps or powers off, but the Start menu's Sleep,
                 Restart and Shut down still happen; idle asks the shell's
                 org.freedesktop.ScreenSaver, which the compositor's idle timer listens to;
                 logout and user switch are also written to $XDG_RUNTIME_DIR/spark-wl/portal-inhibit.json
  Notification   forwarded to org.freedesktop.Notifications (the shell), actions come back
  dialogs        portal_window.py, one window per request

Run by D-Bus activation as the user service spark-portal.service. The windows need the
session's display only when a dialog is shown."""

import logging
import os
import sys

log = logging.getLogger('spark-portal')

NAME = 'org.freedesktop.impl.portal.desktop.sparkos'
PATH = '/org/freedesktop/portal/desktop'
P = 'org.freedesktop.impl.portal.'
VERSIONS = {'Settings': 2, 'Inhibit': 3, 'Notification': 2, 'Access': 1, 'Account': 1,
            'Email': 3, 'DynamicLauncher': 1, 'Print': 3}
OK, DENIED, ENDED = 0, 1, 2          # the portal's response codes

XML = f"""
<node>
  <interface name="{P}Settings">
    <property name="version" type="u" access="read"/>
    <method name="ReadAll"><arg type="as" name="namespaces" direction="in"/>
      <arg type="a{{sa{{sv}}}}" name="value" direction="out"/></method>
    <method name="Read"><arg type="s" name="namespace" direction="in"/>
      <arg type="s" name="key" direction="in"/><arg type="v" name="value" direction="out"/></method>
    <signal name="SettingChanged"><arg type="s" name="namespace"/><arg type="s" name="key"/>
      <arg type="v" name="value"/></signal>
  </interface>
  <interface name="{P}Inhibit">
    <property name="version" type="u" access="read"/>
    <method name="Inhibit"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="window" direction="in"/>
      <arg type="u" name="flags" direction="in"/><arg type="a{{sv}}" name="options" direction="in"/></method>
    <method name="CreateMonitor"><arg type="o" name="handle" direction="in"/>
      <arg type="o" name="session_handle" direction="in"/><arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="window" direction="in"/><arg type="u" name="response" direction="out"/></method>
    <method name="QueryEndResponse"><arg type="o" name="session_handle" direction="in"/></method>
    <signal name="StateChanged"><arg type="o" name="session_handle"/><arg type="a{{sv}}" name="state"/></signal>
  </interface>
  <interface name="{P}Notification">
    <property name="version" type="u" access="read"/>
    <property name="SupportedOptions" type="a{{sv}}" access="read"/>
    <method name="AddNotification"><arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="id" direction="in"/><arg type="a{{sv}}" name="notification" direction="in"/></method>
    <method name="RemoveNotification"><arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="id" direction="in"/></method>
    <signal name="ActionInvoked"><arg type="s" name="app_id"/><arg type="s" name="id"/>
      <arg type="s" name="action"/><arg type="av" name="parameter"/></signal>
  </interface>
  <interface name="{P}Access">
    <property name="version" type="u" access="read"/>
    <method name="AccessDialog"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/><arg type="s" name="subtitle" direction="in"/>
      <arg type="s" name="body" direction="in"/><arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/><arg type="a{{sv}}" name="results" direction="out"/></method>
  </interface>
  <interface name="{P}Account">
    <property name="version" type="u" access="read"/>
    <method name="GetUserInformation"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="window" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/><arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/></method>
  </interface>
  <interface name="{P}Email">
    <property name="version" type="u" access="read"/>
    <method name="ComposeEmail"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="parent_window" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/><arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/></method>
  </interface>
  <interface name="{P}DynamicLauncher">
    <property name="version" type="u" access="read"/>
    <property name="SupportedLauncherTypes" type="u" access="read"/>
    <method name="PrepareInstall"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="name" direction="in"/><arg type="v" name="icon_v" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/><arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/></method>
    <method name="RequestInstallToken"><arg type="s" name="app_id" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/><arg type="u" name="response" direction="out"/></method>
  </interface>
  <interface name="{P}Lockdown">
    <property name="disable-printing" type="b" access="readwrite"/>
    <property name="disable-save-to-disk" type="b" access="readwrite"/>
    <property name="disable-application-handlers" type="b" access="readwrite"/>
    <property name="disable-location" type="b" access="readwrite"/>
    <property name="disable-camera" type="b" access="readwrite"/>
    <property name="disable-microphone" type="b" access="readwrite"/>
    <property name="disable-sound-output" type="b" access="readwrite"/>
  </interface>
  <interface name="{P}Print">
    <property name="version" type="u" access="read"/>
    <method name="PreparePrint"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/><arg type="a{{sv}}" name="settings" direction="in"/>
      <arg type="a{{sv}}" name="page_setup" direction="in"/><arg type="a{{sv}}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/><arg type="a{{sv}}" name="results" direction="out"/></method>
    <method name="Print"><arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/><arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/><arg type="h" name="fd" direction="in"/>
      <arg type="a{{sv}}" name="options" direction="in"/><arg type="u" name="response" direction="out"/>
      <arg type="a{{sv}}" name="results" direction="out"/></method>
  </interface>
</node>
"""

REQUEST_XML = f'<node><interface name="{P}Request"><method name="Close"/></interface></node>'
SESSION_XML = f"""<node><interface name="{P}Session"><method name="Close"/>
  <signal name="Closed"/><property name="version" type="u" access="read"/></interface></node>"""

LOCKDOWN_KEYS = ('disable-printing', 'disable-save-to-disk', 'disable-application-handlers',
                 'disable-location', 'disable-camera', 'disable-microphone',
                 'disable-sound-output')


def app_label(app_id: str) -> str:
    from .strings import t
    return app_id.removesuffix('.desktop') if app_id else t('portal.app')


# ─── dialog specs (plain data, tested without a window) ──────

def access_spec(title, subtitle, body, options, app_id=''):
    from .strings import t
    choices = []
    for cid, label, opts, initial in options.get('choices') or []:
        choices.append({'id': cid, 'label': label, 'options': [list(o) for o in opts],
                        'initial': initial})
    return {'kind': 'access', 'title': title, 'subtitle': subtitle, 'body': body,
            'grant': options.get('grant_label') or t('portal.allow'),
            'deny': options.get('deny_label') or t('portal.deny'),
            'choices': choices, 'app_id': app_id}


def account_spec(app_id, info, reason=''):
    from .strings import t
    lines = [t('portal.account.body', app=app_label(app_id)), f"{info['name']} ({info['id']})"]
    if reason:
        lines.append(t('portal.account.reason', reason=reason))
    return {'kind': 'account', 'title': t('portal.account.title'), 'subtitle': '',
            'body': '\n'.join(lines), 'grant': t('portal.allow'), 'deny': t('portal.deny'),
            'app_id': app_id}


def launcher_spec(app_id, name, icon, options):
    from .strings import t
    body = t('portal.launcher.body', app=app_label(app_id))
    if options.get('target'):
        body += '\n' + t('portal.launcher.site', target=options['target'])
    return {'kind': 'launcher', 'title': t('portal.launcher.title'), 'subtitle': '',
            'body': body, 'grant': t('portal.launcher.add'), 'deny': t('portal.cancel'),
            'name': {'value': name, 'editable': bool(options.get('editable_name', True))},
            'icon': icon, 'app_id': app_id}


def print_spec(title, printers, default, copies):
    from .strings import t
    return {'kind': 'print', 'title': t('portal.print.title'), 'subtitle': title, 'body': '',
            'grant': t('portal.print.go'), 'deny': t('portal.cancel'),
            'printers': [{'name': n, 'label': n if s == 'idle' else f'{n} ({s})'}
                         for n, s in printers],
            'default_printer': default, 'copies': copies}


# ─── the service ─────────────────────────────────────────────

class Request:
    """One portal request in flight: the Request object at its handle and the reply owed."""

    def __init__(self, backend, handle, invocation=None):
        self.backend, self.handle, self.invocation = backend, handle, invocation
        self.closer, self.on_close, self.rid, self.finished = None, None, None, False

    def reply(self, response, results):
        from gi.repository import GLib
        if self.finished:
            return
        self.finished = True
        self.backend.drop_request(self)
        if self.invocation is not None:
            self.invocation.return_value(GLib.Variant('(ua{sv})', (response, results)))

    def close(self):
        """The portal closed the request (Request.Close)."""
        if self.finished:
            return
        if self.closer:
            self.closer()
        if self.on_close:
            self.on_close()
        self.reply(ENDED, {})


class Backend:
    def __init__(self, conn, environ=None, dialogs=None):
        from gi.repository import Gio
        from . import portal_logic as logic
        from . import portal_window
        self.conn, self.logic = conn, logic
        self.environ = os.environ if environ is None else environ
        self.test = bool(self.environ.get('SPARK_PORTAL_TEST_DIALOG'))
        self.show = dialogs or portal_window.show
        self.info = Gio.DBusNodeInfo.new_for_xml(XML)
        self.request_info = Gio.DBusNodeInfo.new_for_xml(REQUEST_XML).interfaces[0]
        self.session_info = Gio.DBusNodeInfo.new_for_xml(SESSION_XML).interfaces[0]
        self.requests = {}            # handle -> Request
        self.holds = {}               # handle -> inhibit held by an app
        self.monitors = {}            # session handle -> {sender, rid}
        self.watched = {}             # bus name -> watch id
        self.lockdown = {k: False for k in LOCKDOWN_KEYS}
        self.notes = {}               # shell id -> (app_id, id, targets)
        self.note_ids = {}            # (app_id, id) -> shell id
        self.tokens, self.next_token = {}, 1
        self.system, self.locked, self.ending = None, False, False
        self.settings = logic.SettingsStore(self._setting_changed, self.environ)
        self.handlers = {
            ('Settings', 'ReadAll'): self.settings_read_all, ('Settings', 'Read'): self.settings_read,
            ('Inhibit', 'Inhibit'): self.inhibit, ('Inhibit', 'CreateMonitor'): self.create_monitor,
            ('Inhibit', 'QueryEndResponse'): self.query_end_response,
            ('Notification', 'AddNotification'): self.add_notification,
            ('Notification', 'RemoveNotification'): self.remove_notification,
            ('Access', 'AccessDialog'): self.access_dialog,
            ('Account', 'GetUserInformation'): self.get_user_information,
            ('Email', 'ComposeEmail'): self.compose_email,
            ('DynamicLauncher', 'PrepareInstall'): self.prepare_install,
            ('DynamicLauncher', 'RequestInstallToken'): self.request_install_token,
            ('Print', 'PreparePrint'): self.prepare_print, ('Print', 'Print'): self.print_file,
        }

    # ── plumbing ──

    def start(self):
        for iface in self.info.interfaces:
            self.conn.register_object(PATH, iface, self._on_call, self._on_get, self._on_set)
        self.settings.watch()
        self.conn.signal_subscribe('org.freedesktop.Notifications', 'org.freedesktop.Notifications',
                                   None, '/org/freedesktop/Notifications', None, 0, self._on_note_signal)
        self._watch_logind()

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        short = iface.rsplit('.', 1)[1]
        try:
            self.handlers[(short, method)](sender, params, invocation)
        except _Fail as e:
            invocation.return_dbus_error(e.name, str(e))
        except Exception as e:                                  # noqa: BLE001
            log.exception('%s.%s', iface, method)
            invocation.return_dbus_error('org.freedesktop.DBus.Error.Failed', str(e))

    def _on_get(self, conn, sender, path, iface, prop):
        from gi.repository import GLib
        short = iface.rsplit('.', 1)[1]
        if prop == 'version':
            return GLib.Variant('u', VERSIONS.get(short, 1))
        if short == 'Lockdown':
            return GLib.Variant('b', self.lockdown.get(prop, False))
        if prop == 'SupportedLauncherTypes':
            return GLib.Variant('u', 3)
        if prop == 'SupportedOptions':
            return GLib.Variant('a{sv}', {})
        return None

    def _on_set(self, conn, sender, path, iface, prop, value):
        if prop in self.lockdown:
            self.lockdown[prop] = bool(value.unpack())
            return True
        return False

    def new_request(self, handle, invocation=None):
        req = Request(self, handle, invocation)
        try:
            req.rid = self.conn.register_object(handle, self.request_info,
                                                lambda *a: self._request_call(req, *a), None, None)
        except Exception as e:                                  # noqa: BLE001
            log.debug('request object %s: %s', handle, e)
        self.requests[handle] = req
        return req

    def _request_call(self, req, _conn, _sender, _path, _iface, method, _params, invocation):
        invocation.return_value(None)
        if method == 'Close':
            req.close()

    def drop_request(self, req):
        self.requests.pop(req.handle, None)
        self._unregister(req)

    def _unregister(self, req):
        if req.rid is not None:
            try:
                self.conn.unregister_object(req.rid)
            except Exception:                                   # noqa: BLE001
                pass
            req.rid = None

    def ask(self, handle, invocation, spec, result):
        """Show a dialog for a request. result(accepted, values) gives (response, results)."""
        req = self.new_request(handle, invocation)

        def done(accepted, values):
            try:
                response, results = result(accepted, values)
            except Exception:                                   # noqa: BLE001
                log.exception('dialog answer')
                response, results = ENDED, {}
            req.reply(response, results)
        try:
            shown = self.show(spec, done)
            req.closer = shown.close
        except Exception:                                       # noqa: BLE001
            log.exception('could not show the %s dialog', spec.get('kind'))
            req.reply(ENDED, {})

    # ── Settings ──

    def settings_read_all(self, sender, params, invocation):
        from gi.repository import GLib
        got = self.settings.read_all(list(params.unpack()[0]))
        invocation.return_value(GLib.Variant('(a{sa{sv}})', (got,)))

    def settings_read(self, sender, params, invocation):
        from gi.repository import GLib
        ns, key = params.unpack()
        value = self.settings.read(ns, key)
        if value is None:
            raise _Fail('org.freedesktop.portal.Error.NotFound', f'{ns} {key}')
        invocation.return_value(GLib.Variant('(v)', (value,)))

    def _setting_changed(self, ns, key, value):
        from gi.repository import GLib
        self.conn.emit_signal(None, PATH, P + 'Settings', 'SettingChanged',
                              GLib.Variant('(ssv)', (ns, key, value)))

    # ── Inhibit ──

    def system_bus(self):
        from gi.repository import Gio
        if self.system is None:
            try:
                self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except Exception as e:                              # noqa: BLE001
                log.warning('no system bus: %s', e)
        return self.system

    def inhibit(self, sender, params, invocation):
        handle, app_id, _window, flags, options = params.unpack()
        reason = str(options.get('reason') or '')
        invocation.return_value(None)
        req = self.new_request(handle)
        hold = {'handle': handle, 'sender': sender, 'app_id': app_id, 'reason': reason,
                'flags': flags, 'fd': None, 'cookie': None, 'released': False}
        self.holds[handle] = hold
        req.on_close = lambda: self.release(handle)
        self._watch_sender(sender)
        self._write_registry()
        what = self.logic.logind_what(flags)
        if what and self.system_bus():
            self._logind_inhibit(hold, what)
        if flags & self.logic.INHIBIT_IDLE:
            self._screensaver_inhibit(hold)

    def _logind_inhibit(self, hold, what):
        from gi.repository import Gio, GLib

        def done(conn, res):
            try:
                reply, fds = conn.call_with_unix_fd_list_finish(res)
                fd = fds.get(reply.unpack()[0])
            except Exception as e:                              # noqa: BLE001
                log.warning('logind inhibit: %s', e)
                return
            if hold['released']:
                os.close(fd)
            else:
                hold['fd'] = fd
        who = app_label(hold['app_id'])
        self.system.call_with_unix_fd_list(
            'org.freedesktop.login1', '/org/freedesktop/login1', 'org.freedesktop.login1.Manager',
            'Inhibit', GLib.Variant('(ssss)', (what, who, hold['reason'] or who, 'delay')),
            GLib.VariantType('(h)'), Gio.DBusCallFlags.NONE, 3000, None, None, done)

    def _screensaver_inhibit(self, hold):
        from gi.repository import Gio, GLib

        def done(conn, res):
            try:
                cookie = conn.call_finish(res).unpack()[0]
            except Exception as e:                              # noqa: BLE001
                log.warning('screensaver inhibit: %s', e)
                return
            if hold['released']:
                self._screensaver_uninhibit(cookie)
            else:
                hold['cookie'] = cookie
        who = app_label(hold['app_id'])
        self.conn.call('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver',
                       'org.freedesktop.ScreenSaver', 'Inhibit',
                       GLib.Variant('(ss)', (who, hold['reason'] or who)),
                       GLib.VariantType('(u)'), Gio.DBusCallFlags.NONE, 3000, None, done)

    def _screensaver_uninhibit(self, cookie):
        from gi.repository import Gio, GLib
        self.conn.call('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver',
                       'org.freedesktop.ScreenSaver', 'UnInhibit', GLib.Variant('(u)', (cookie,)),
                       None, Gio.DBusCallFlags.NONE, 3000, None, None)

    def release(self, handle):
        hold = self.holds.pop(handle, None)
        if hold is None:
            return
        hold['released'] = True
        if hold['fd'] is not None:
            os.close(hold['fd'])
            hold['fd'] = None
        if hold['cookie'] is not None:
            self._screensaver_uninhibit(hold['cookie'])
            hold['cookie'] = None
        self._write_registry()
        self._unwatch_unused()

    def _write_registry(self):
        entries = [{'app_id': h['app_id'], 'reason': h['reason'], 'flags': h['flags']}
                   for h in self.holds.values()
                   if h['flags'] & (self.logic.INHIBIT_LOGOUT | self.logic.INHIBIT_USER_SWITCH)]
        try:
            self.logic.write_inhibit_registry(self.logic.inhibit_registry_path(self.environ), entries)
        except OSError as e:
            log.warning('inhibit list: %s', e)

    def _watch_sender(self, sender):
        from gi.repository import Gio
        if sender in self.watched:
            return
        self.watched[sender] = Gio.bus_watch_name_on_connection(
            self.conn, sender, Gio.BusNameWatcherFlags.NONE, None, lambda c, n: self._gone(n))

    def _unwatch_unused(self):
        from gi.repository import Gio
        used = {h['sender'] for h in self.holds.values()} | {m['sender'] for m in self.monitors.values()}
        for name in [n for n in self.watched if n not in used]:
            Gio.bus_unwatch_name(self.watched.pop(name))

    def _gone(self, name):
        """The caller left the bus: let go of what it held."""
        for handle in [h for h, v in self.holds.items() if v['sender'] == name]:
            req = self.requests.get(handle)
            if req:
                self._unregister(req)
                self.requests.pop(handle, None)
            self.release(handle)
        for session in [s for s, m in self.monitors.items() if m['sender'] == name]:
            self.close_monitor(session)
        self._unwatch_unused()

    def create_monitor(self, sender, params, invocation):
        from gi.repository import GLib
        handle, session, _app, _window = params.unpack()
        rid = self.conn.register_object(session, self.session_info,
                                        lambda *a: self._session_call(session, *a),
                                        lambda *a: GLib.Variant('u', 1), None)
        self.monitors[session] = {'sender': sender, 'rid': rid}
        self._watch_sender(sender)
        invocation.return_value(GLib.Variant('(u)', (OK,)))
        GLib.idle_add(self._send_state, session)

    def _session_call(self, session, _conn, _sender, _path, _iface, method, _params, invocation):
        invocation.return_value(None)
        if method == 'Close':
            self.close_monitor(session)

    def close_monitor(self, session):
        mon = self.monitors.pop(session, None)
        if mon is None:
            return
        try:
            self.conn.emit_signal(None, session, P + 'Session', 'Closed', None)
            self.conn.unregister_object(mon['rid'])
        except Exception:                                       # noqa: BLE001
            pass
        self._unwatch_unused()

    def query_end_response(self, sender, params, invocation):
        invocation.return_value(None)

    def state(self) -> dict:
        from gi.repository import GLib
        return {'screensaver-active': GLib.Variant('b', self.locked),
                'session-state': GLib.Variant('u', 3 if self.ending else 1)}

    def _send_state(self, only=None):
        from gi.repository import GLib
        for session in ([only] if only else list(self.monitors)):
            if session in self.monitors:
                self.conn.emit_signal(None, PATH, P + 'Inhibit', 'StateChanged',
                                      GLib.Variant('(oa{sv})', (session, self.state())))
        return False

    def _watch_logind(self):
        """Screensaver-active follows the session's LockedHint, Ending follows PrepareForShutdown."""
        from gi.repository import GLib
        bus = self.system_bus()
        if bus is None:
            return
        bus.signal_subscribe('org.freedesktop.login1', 'org.freedesktop.login1.Manager',
                             'PrepareForShutdown', '/org/freedesktop/login1', None, 0,
                             lambda c, s, p, i, n, params: self._set_state(ending=params.unpack()[0]))
        sid = self.environ.get('XDG_SESSION_ID') or ''

        def got_path(conn, res):
            try:
                path = conn.call_finish(res).unpack()[0]
            except Exception as e:                              # noqa: BLE001
                log.info('no logind session to watch: %s', e)
                return
            bus.signal_subscribe('org.freedesktop.login1', 'org.freedesktop.DBus.Properties',
                                 'PropertiesChanged', path, 'org.freedesktop.login1.Session', 0,
                                 self._session_props_changed)
            bus.call('org.freedesktop.login1', path, 'org.freedesktop.DBus.Properties', 'Get',
                     GLib.Variant('(ss)', ('org.freedesktop.login1.Session', 'LockedHint')),
                     GLib.VariantType('(v)'), 0, 3000, None,
                     lambda c, r: self._first_locked(c, r))
        from gi.repository import Gio
        if sid:
            bus.call('org.freedesktop.login1', '/org/freedesktop/login1',
                     'org.freedesktop.login1.Manager', 'GetSession', GLib.Variant('(s)', (sid,)),
                     GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, 3000, None, got_path)
        else:
            bus.call('org.freedesktop.login1', '/org/freedesktop/login1',
                     'org.freedesktop.login1.Manager', 'GetSessionByPID',
                     GLib.Variant('(u)', (os.getpid(),)), GLib.VariantType('(o)'),
                     Gio.DBusCallFlags.NONE, 3000, None, got_path)

    def _first_locked(self, conn, res):
        try:
            self._set_state(locked=bool(conn.call_finish(res).unpack()[0]))
        except Exception:                                       # noqa: BLE001
            pass

    def _session_props_changed(self, conn, sender, path, iface, name, params):
        changed = params.unpack()[1]
        if 'LockedHint' in changed:
            self._set_state(locked=bool(changed['LockedHint']))

    def _set_state(self, locked=None, ending=None):
        before = (self.locked, self.ending)
        if locked is not None:
            self.locked = locked
        if ending is not None:
            self.ending = ending
        if before != (self.locked, self.ending):
            self._send_state()

    # ── Notification ──

    def add_notification(self, sender, params, invocation):
        from gi.repository import Gio, GLib
        app_id, nid, vardict = params.get_child_value(0).unpack(), params.get_child_value(1).unpack(), \
            params.get_child_value(2)
        note = self.logic.parse_notification(app_id, nid, vardict)
        invocation.return_value(None)
        replaces = self.note_ids.get((app_id, nid), 0)
        args = GLib.Variant('(susssasa{sv}i)', (
            note['app_name'], replaces, note['icon'], note['summary'], note['body'],
            note['actions'], note['hints'], -1))

        def done(conn, res):
            try:
                shell_id = conn.call_finish(res).unpack()[0]
            except Exception as e:                              # noqa: BLE001
                log.warning('notification from %s: %s', app_id, e)
                return
            self.note_ids[(app_id, nid)] = shell_id
            self.notes[shell_id] = (app_id, nid, note['targets'])
        self.conn.call('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                       'org.freedesktop.Notifications', 'Notify', args, GLib.VariantType('(u)'),
                       Gio.DBusCallFlags.NONE, 3000, None, done)

    def remove_notification(self, sender, params, invocation):
        from gi.repository import Gio, GLib
        app_id, nid = params.unpack()
        invocation.return_value(None)
        shell_id = self.note_ids.pop((app_id, nid), None)
        if shell_id is None:
            return
        self.notes.pop(shell_id, None)
        self.conn.call('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                       'org.freedesktop.Notifications', 'CloseNotification',
                       GLib.Variant('(u)', (shell_id,)), None, Gio.DBusCallFlags.NONE, 3000,
                       None, None)

    def _on_note_signal(self, conn, sender, path, iface, name, params):
        from gi.repository import GLib
        if name == 'NotificationClosed':
            shell_id = params.unpack()[0]
            known = self.notes.pop(shell_id, None)
            if known:
                self.note_ids.pop((known[0], known[1]), None)
        elif name == 'ActionInvoked':
            shell_id, key = params.unpack()
            known = self.notes.get(shell_id)
            if not known or key not in known[2]:
                return
            app_id, nid, targets = known
            action, target = targets[key]
            extra = [target] if target is not None else []
            self.conn.emit_signal(None, PATH, P + 'Notification', 'ActionInvoked',
                                  GLib.Variant('(sssav)', (app_id, nid, action, extra)))

    # ── Access, Account, Email, DynamicLauncher ──

    def access_dialog(self, sender, params, invocation):
        from gi.repository import GLib
        handle, app_id, _parent, title, subtitle, body, options = params.unpack()
        spec = access_spec(title, subtitle, body, options, app_id)

        def result(accepted, values):
            if not accepted:
                return DENIED, {}
            out = {}
            if spec['choices']:
                got = values.get('choices') or {}
                out['choices'] = GLib.Variant('a(ss)', [
                    (c['id'], str(got.get(c['id'], c['initial']))) for c in spec['choices']])
            return OK, out
        self.ask(handle, invocation, spec, result)

    def get_user_information(self, sender, params, invocation):
        from gi.repository import GLib
        handle, app_id, _window, options = params.unpack()
        info = self.logic.user_information()
        spec = account_spec(app_id, info, str(options.get('reason') or ''))

        def result(accepted, values):
            if not accepted:
                return DENIED, {}
            out = {'id': GLib.Variant('s', info['id']), 'name': GLib.Variant('s', info['name'])}
            if info['image']:
                out['image'] = GLib.Variant('s', info['image'])
            return OK, out
        self.ask(handle, invocation, spec, result)

    def compose_email(self, sender, params, invocation):
        handle, _app_id, _parent, options = params.unpack()
        uri = self.logic.mailto_uri(options)
        req = self.new_request(handle, invocation)
        req.reply(OK if self.open_uri(uri) else ENDED, {})

    def open_uri(self, uri) -> bool:
        """Open a mailto: link with the default handler."""
        from gi.repository import Gio
        if self.test:
            log_path = self.environ.get('SPARK_PORTAL_TEST_LOG')
            if log_path:
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write('{"opened": %s}\n' % __import__('json').dumps(uri))
            return True
        try:
            return bool(Gio.AppInfo.launch_default_for_uri(uri, None))
        except Exception as e:                                  # noqa: BLE001
            log.warning('no mail program for %s: %s', uri, e)
            return False

    def prepare_install(self, sender, params, invocation):
        from gi.repository import GLib
        handle, app_id, _parent, name, _icon, options = params.unpack()
        icon_v = params.get_child_value(4)
        icon = icon_v.get_variant() if icon_v.get_type_string() == 'v' else icon_v
        spec = launcher_spec(app_id, name, icon, options)

        def result(accepted, values):
            if not accepted:
                return DENIED, {}
            chosen = (values.get('name') or name) if options.get('editable_name', True) else name
            return OK, {'name': GLib.Variant('s', chosen), 'icon': icon}
        self.ask(handle, invocation, spec, result)

    def request_install_token(self, sender, params, invocation):
        from gi.repository import GLib
        app_id, _options = params.unpack()
        ok = self.logic.trusted_launcher_app(app_id)
        invocation.return_value(GLib.Variant('(u)', (OK if ok else DENIED,)))

    # ── Print ──

    def prepare_print(self, sender, params, invocation):
        from gi.repository import GLib
        handle, _app, _parent, title, settings, page_setup, _options = params.unpack()
        printers, default = self.logic.list_printers()
        try:
            copies = int(settings.get('n-copies') or 1)
        except (TypeError, ValueError):
            copies = 1
        spec = print_spec(title, printers, settings.get('printer') or default, copies)

        def result(accepted, values):
            if not accepted:
                return DENIED, {}
            token, self.next_token = self.next_token, self.next_token + 1
            self.tokens[token] = (values.get('printer', ''), int(values.get('copies') or 1))
            merged = dict(settings)
            merged['printer'] = values.get('printer', '')
            merged['n-copies'] = str(self.tokens[token][1])
            return OK, {
                'settings': GLib.Variant('a{sv}', {k: GLib.Variant('s', str(v))
                                                   for k, v in merged.items()}),
                'page-setup': GLib.Variant('a{sv}', {k: GLib.Variant('s', str(v))
                                                     for k, v in page_setup.items()}),
                'token': GLib.Variant('u', token)}
        self.ask(handle, invocation, spec, result)

    def print_file(self, sender, params, invocation):
        from gi.repository import Gio
        handle, _app, _parent, title, fd_index, options = params.unpack()
        fds = invocation.get_message().get_unix_fd_list()
        fd = fds.get(fd_index) if fds is not None else -1
        token = options.get('token')
        printer, copies = self.tokens.get(token, ('', 1))
        req = self.new_request(handle, invocation)
        if fd < 0:
            req.reply(ENDED, {})
            return
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDERR_SILENCE)
        launcher.take_stdin_fd(fd)
        try:
            proc = launcher.spawnv(self.logic.lp_command(printer, copies, title))
        except Exception as e:                                  # noqa: BLE001
            log.warning('lp: %s', e)
            req.reply(ENDED, {})
            return

        def finished(p, res):
            try:
                p.wait_finish(res)
                ok = p.get_successful()
            except Exception:                                   # noqa: BLE001
                ok = False
            req.reply(OK if ok else ENDED, {})
        req.closer = proc.force_exit
        proc.wait_async(None, finished)


class _Fail(Exception):
    def __init__(self, name, message):
        super().__init__(message)
        self.name = name


# ─── start and self-test ─────────────────────────────────────

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format='spark-portal: %(message)s', stream=sys.stderr)
    if '--version' in argv:
        from . import VERSION
        print(f'spark-portal {VERSION}')
        return 0
    if '--self-test' in argv:
        return self_test()
    from gi.repository import Gio, GLib
    loop = GLib.MainLoop()
    holder = {}

    def acquired(conn, _name):
        holder['backend'] = Backend(conn)
        holder['backend'].start()

    def lost(_conn, _name):
        log.info('%s is taken or the bus is gone', NAME)
        loop.quit()
    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, acquired,
                     lambda *_: log.info('own %s', NAME), lost)
    loop.run()
    return 0


def self_test() -> int:
    """No bus, no display: the plain parts."""
    from gi.repository import GLib
    from . import portal_logic as logic
    problems = []

    def check(ok, what):
        if not ok:
            problems.append(what)
    r, g, b = logic.accent_rgb()
    check(abs(r - 0x3d / 255) < 1e-9 and abs(g - 0xe8 / 255) < 1e-9 and abs(b - 0xc8 / 255) < 1e-9,
          'accent')
    check(logic.namespace_matches('org.gnome.desktop.interface', ['org.gnome.*']), 'glob')
    check(not logic.namespace_matches('org.freedesktop.appearance', ['org.gnome.*']), 'glob miss')
    check(logic.namespace_matches('x', []), 'empty filter')
    check(logic.appearance_values({'XDG_CONFIG_HOME': '/nonexistent'})['color-scheme'].unpack() == 1,
          'dark')
    check(logic.mailto_uri({'addresses': ['a@b.c'], 'subject': 'Hi there'}) ==
          'mailto:a@b.c?subject=Hi%20there', 'mailto')
    check(logic.parse_lpstat('printer A is idle.  enabled since x\nsystem default destination: A\n')
          == ([('A', 'idle')], 'A'), 'lpstat')
    check(logic.inhibit_kinds(5) == ['logout', 'suspend'], 'inhibit flags')
    check(logic.logind_what(4) == 'sleep' and logic.logind_what(1) == 'shutdown', 'logind what')
    note = logic.parse_notification('a.b', '1', GLib.Variant('a{sv}', {
        'title': GLib.Variant('s', 'T'), 'priority': GLib.Variant('s', 'urgent')}))
    check(note['hints']['urgency'].unpack() == 2 and note['summary'] == 'T', 'notification')
    for what in problems:
        print(f'spark-portal self-test failed: {what}', file=sys.stderr)
    if not problems:
        print('spark-portal self-test ok')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
