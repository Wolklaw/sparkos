"""spark-polkit: the polkit authentication agent of the Spark session.

polkitd asks the session's agent for a password whenever a program needs admin rights (pkexec,
Spark Settings, Spark Update...). This module registers as that agent (PolkitAgent.Listener, in
PyGObject: the typelibs are enough, no C helper is needed) and shows one window per request.

The password never leaves this process except through PolkitAgent.Session.response(), which
hands it to polkit-agent-helper-1 (setuid root, runs PAM with the "polkit-1" service). Nothing
here writes the password, or anything typed, to a log; the tests check that.

The code is split so it can be tested without a screen:
  describe_identities / program_of    plain data for the window
  AuthFlow                            the state machine (sessions, retries, cancel), no GTK
  Agent                               the D-Bus object polkitd talks to
  AuthWindow (polkit_window.py)       the GTK4 window, one implementation of the AuthFlow UI
"""

import grp
import logging
import os
import pwd
import sys

log = logging.getLogger('spark-polkit')

OBJECT_PATH = '/dev/wolklaw/SparkPolkit/AuthenticationAgent'


class Choice:
    """One identity the user can authenticate as."""

    def __init__(self, identity, uid, name, label):
        self.identity, self.uid, self.name, self.label = identity, uid, name, label


def _user_label(uid: int, you: int, language=None):
    from .strings import t
    try:
        entry = pwd.getpwuid(uid)
    except KeyError:
        return str(uid), f'uid {uid}'
    real = (entry.pw_gecos or '').split(',')[0].strip()
    name = entry.pw_name
    shown = f'{real} ({name})' if real and real != name else name
    if uid == you:
        shown = t('auth.you', language, name=shown)
    return name, shown


def describe_identities(identities, you=None, language=None):
    """The identities polkitd offers, as Choices: users as they are, groups expanded into their
    members, duplicates dropped. The current user comes first (then others, root last)."""
    from gi.repository import Polkit
    you = os.getuid() if you is None else you
    seen, out = set(), []

    def add(identity, uid):
        if uid in seen:
            return
        seen.add(uid)
        name, label = _user_label(uid, you, language)
        out.append(Choice(identity, uid, name, label))

    for identity in identities or []:
        if isinstance(identity, Polkit.UnixUser):
            add(identity, identity.get_uid())
        elif isinstance(identity, Polkit.UnixGroup):
            try:
                members = grp.getgrgid(identity.get_gid()).gr_mem
            except KeyError:
                members = []
            for member in members:
                try:
                    uid = pwd.getpwnam(member).pw_uid
                except KeyError:
                    continue
                add(Polkit.UnixUser.new(uid), uid)
    out.sort(key=lambda c: (c.uid != you, c.uid == 0, c.uid))
    return out


def program_of(details: dict):
    """(program, command line) of whoever asked, from what polkitd and pkexec put in the
    details. The program comes from the requester's pid when that can be read."""
    command = details.get('command_line') or ''
    program = details.get('program') or ''
    pid = details.get('polkit.caller-pid') or details.get('polkit.subject-pid') or ''
    if not program and str(pid).isdigit():
        try:
            program = os.readlink(f'/proc/{int(pid)}/exe')
        except OSError:
            program = ''
    return program, command


def details_dict(details) -> dict:
    """Polkit.Details to a plain dict (a missing key stays out)."""
    out = {}
    if details is None:
        return out
    for key in (details.get_keys() or []):
        out[key] = details.lookup(key)
    return out


class Request:
    """Everything one polkitd request carries."""

    def __init__(self, action_id, message, icon_name, details, cookie, identities):
        self.action_id, self.message, self.icon_name = action_id, message, icon_name
        self.details, self.cookie = details, cookie
        self.choices = describe_identities(identities)


class AuthFlow:
    """One authentication, from polkitd's request to success, cancel or failure.

    ui must have: ask(prompt, echo), info(text), error(text), wrong(), checking(),
    choices_changed(), close(). session_factory(identity, cookie) returns an object with
    initiate(), response(secret), cancel() and connect(name, callback); the real one is
    PolkitAgent.Session.new. done(ok) is called once at the end."""

    def __init__(self, request, ui, done, session_factory=None):
        self.request, self.ui, self._done = request, ui, done
        self.session_factory = session_factory or _real_session
        self.session = None
        self.current = None
        self.finished = False
        self.attempts = 0

    def start(self):
        if not self.request.choices:
            log.warning('no usable identity for %s', self.request.action_id)
            self._finish(False)
            return
        self.begin(self.request.choices[0])

    def begin(self, choice):
        self._drop_session()
        self.current = choice
        self.session = self.session_factory(choice.identity, self.request.cookie)
        session = self.session
        session.connect('request', lambda s, p, echo: self._on(session, self.ui.ask, p, echo))
        session.connect('show-info', lambda s, text: self._on(session, self.ui.info, text))
        session.connect('show-error', lambda s, text: self._on(session, self.ui.error, text))
        session.connect('completed', lambda s, ok: self._completed(session, ok))
        session.initiate()

    def _on(self, session, call, *args):
        if session is self.session and not self.finished:
            call(*args)

    def answer(self, secret: str):
        """The user submitted the password. It goes to the helper and nowhere else."""
        if self.session is None or self.finished:
            return
        self.ui.checking()
        self.session.response(secret)

    def choose(self, choice):
        if not self.finished and choice is not self.current:
            self.begin(choice)

    def cancel(self):
        if self.finished:
            return
        self._drop_session()
        self._finish(False)

    def _completed(self, session, ok):
        if session is not self.session or self.finished:
            return
        if ok:
            self._finish(True)
            return
        self.attempts += 1
        log.info('authentication failed for %s (attempt %d)', self.request.action_id, self.attempts)
        self.ui.wrong()
        self.begin(self.current)       # a Session works once; start a new one for the retry

    def _drop_session(self):
        session, self.session = self.session, None
        if session is not None:
            try:
                session.cancel()
            except Exception:
                pass

    def _finish(self, ok):
        if self.finished:
            return
        self.finished = True
        self.session = None
        self.ui.close()
        self._done(ok)


def _real_session(identity, cookie):
    import gi
    gi.require_version('PolkitAgent', '1.0')
    from gi.repository import PolkitAgent
    return PolkitAgent.Session.new(identity, cookie)


AGENT_XML = '''<node><interface name="org.freedesktop.PolicyKit1.AuthenticationAgent">
  <method name="BeginAuthentication">
    <arg type="s" name="action_id" direction="in"/><arg type="s" name="message" direction="in"/>
    <arg type="s" name="icon_name" direction="in"/><arg type="a{ss}" name="details" direction="in"/>
    <arg type="s" name="cookie" direction="in"/><arg type="a(sa{sv})" name="identities" direction="in"/>
  </method>
  <method name="CancelAuthentication"><arg type="s" name="cookie" direction="in"/></method>
</interface></node>'''
CANCELLED = 'org.freedesktop.PolicyKit1.Error.Cancelled'
FAILED = 'org.freedesktop.PolicyKit1.Error.Failed'


class Agent:
    """The org.freedesktop.PolicyKit1.AuthenticationAgent object polkitd calls.

    It is plain D-Bus (Gio) and not a PolkitAgent.Listener subclass on purpose: Listener's
    initiate_authentication vfunc hands its callback and user_data to the override, and
    PyGObject cannot pass that user_data back (libpolkit-agent segfaults on the NULL). The
    authority is still reached through the Polkit typelib, and PolkitAgent.Session still runs
    the setuid helper, so no password handling is reimplemented.
    make_ui(request, flow) returns the window for one request."""

    def __init__(self, make_ui, session_factory=None):
        self.make_ui, self.session_factory = make_ui, session_factory
        self.active = {}                 # cookie -> AuthFlow
        self.connection = None
        self.registration_id = 0
        self.subject = None

    def export(self, connection, object_path=OBJECT_PATH):
        from gi.repository import Gio
        node = Gio.DBusNodeInfo.new_for_xml(AGENT_XML)
        self.connection = connection
        self.registration_id = connection.register_object(
            object_path, node.interfaces[0], self._call, None, None)

    def _call(self, connection, sender, path, interface, method, params, invocation):
        try:
            if method == 'BeginAuthentication':
                self.begin(*params.unpack(), invocation)
            elif method == 'CancelAuthentication':
                flow = self.active.get(params.unpack()[0])
                if flow is not None:
                    flow.cancel()
                invocation.return_value(None)
        except Exception:
            log.exception('request failed')      # the traceback never holds a password
            invocation.return_dbus_error(FAILED, 'The agent failed')

    def begin(self, action_id, message, icon_name, details, cookie, identities, invocation):
        from gi.repository import Polkit
        found = []
        for kind, values in identities:
            if kind == 'unix-user' and 'uid' in values:
                found.append(Polkit.UnixUser.new(values['uid']))
            elif kind == 'unix-group' and 'gid' in values:
                found.append(Polkit.UnixGroup.new(values['gid']))
            else:
                log.warning('an identity of kind %s was skipped', kind)
        request = Request(action_id, message, icon_name, dict(details), cookie, found)
        log.info('request for %s', action_id)

        def done(ok):
            self.active.pop(cookie, None)
            if ok:
                invocation.return_value(None)
            else:
                invocation.return_dbus_error(CANCELLED, 'Authentication cancelled')
        flow = AuthFlow(request, None, done, self.session_factory)
        flow.ui = self.make_ui(request, flow)
        self.active[cookie] = flow
        flow.start()

    def register(self, subject=None):
        """Tell polkitd this process answers for the session. RuntimeError if it refuses
        (another agent already holds the session)."""
        import gi
        gi.require_version('Polkit', '1.0')
        from gi.repository import GLib, Polkit
        if subject is None:
            session_id = os.environ.get('XDG_SESSION_ID')
            subject = (Polkit.UnixSession.new(session_id) if session_id
                       else Polkit.UnixProcess.new(os.getpid()))
        self.subject = subject
        try:
            authority = Polkit.Authority.get_sync(None)
            authority.register_authentication_agent_sync(
                subject, os.environ.get('LANG', 'en_US.UTF-8'), OBJECT_PATH, None)
        except GLib.Error as exc:
            raise RuntimeError(f'cannot register as the polkit agent: {exc.message}') from exc


def register(make_ui, session_factory=None):
    """Export the agent object on the system bus and register it with polkitd."""
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio
    agent = Agent(make_ui, session_factory)
    agent.export(Gio.bus_get_sync(Gio.BusType.SYSTEM, None))
    agent.register()
    return agent, None



def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format='spark-polkit: %(message)s', stream=sys.stderr)
    if '--version' in argv:
        from . import VERSION
        print(f'spark-polkit {VERSION}')
        return 0
    if '--self-test' in argv:
        return self_test()
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    from . import style
    from .polkit_window import AuthWindow
    if not Gtk.init_check():
        print('spark-polkit: no display', file=sys.stderr)
        return 1
    style.install()
    try:
        agent, handle = register(lambda request, flow: AuthWindow(request, flow))
    except RuntimeError as exc:
        print(f'spark-polkit: {exc}', file=sys.stderr)
        return 1
    log.info('registered, waiting for requests')
    GLib.MainLoop().run()
    return 0


def self_test() -> int:
    """No display, no bus: the identity and program helpers and the flow with a fake session."""
    class Fake:
        def __init__(self):
            self.cb, self.sent = {}, []

        def connect(self, name, callback):
            self.cb[name] = callback

        def initiate(self):
            self.cb['request'](self, 'Password:', False)

        def response(self, secret):
            self.sent.append(secret)

        def cancel(self):
            pass

    class Ui:
        def __getattr__(self, name):
            return lambda *a: None

    sessions = []

    def factory(identity, cookie):
        sessions.append(Fake())
        return sessions[-1]

    class Req:
        action_id, cookie, details, choices = 'x', 'c', {}, [Choice(None, 1000, 'u', 'u')]
    results = []
    flow = AuthFlow(Req(), Ui(), results.append, factory)
    flow.start()
    flow.answer('pw')
    assert sessions[0].sent == ['pw']
    sessions[0].cb['completed'](sessions[0], True)
    assert results == [True]
    print('self-test passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
