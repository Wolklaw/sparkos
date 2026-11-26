"""The Spark lock screen: ext-session-lock surfaces on every monitor (gtk4-layer-shell's
Gtk4SessionLock), the password checked by PAM through libpam with ctypes.

It runs as its own process (spark-shell --lock), started by the shell when logind asks the
session to lock. If it crashes the compositor keeps the screen locked and black, and the shell
starts it again; a new lock client takes over the lock.

Exit codes: 0 unlocked, 3 could not lock (no session-lock support, or another locker has it)."""

import ctypes
import ctypes.util
import logging
import os
import pwd
import threading
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk4SessionLock', '1.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4SessionLock as SessionLock  # noqa: E402

from . import theme  # noqa: E402
from .strings import tr  # noqa: E402

log = logging.getLogger('spark-lock')

EXIT_UNLOCKED, EXIT_NOT_LOCKED = 0, 3

# ── PAM ──
PAM_SUCCESS, PAM_AUTH_ERR = 0, 7
PAM_PROMPT_ECHO_OFF, PAM_PROMPT_ECHO_ON, PAM_ERROR_MSG, PAM_TEXT_INFO = 1, 2, 3, 4


class _PamMessage(ctypes.Structure):
    _fields_ = [('msg_style', ctypes.c_int), ('msg', ctypes.c_char_p)]


class _PamResponse(ctypes.Structure):
    _fields_ = [('resp', ctypes.c_void_p), ('resp_retcode', ctypes.c_int)]


_CONV = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.POINTER(_PamMessage)),
                         ctypes.POINTER(ctypes.POINTER(_PamResponse)), ctypes.c_void_p)


class _PamConv(ctypes.Structure):
    _fields_ = [('conv', _CONV), ('appdata_ptr', ctypes.c_void_p)]


def pam_service() -> str:
    """spark-lock when the image ships one, else login (system-auth's password check)."""
    return 'spark-lock' if os.path.exists('/etc/pam.d/spark-lock') else 'login'


def authenticate(user: str, password: str, service=None):
    """(ok, message). Blocks (pam_faildelay waits 2 s after a wrong password): run it in a thread."""
    libpam = ctypes.CDLL(ctypes.util.find_library('pam') or 'libpam.so.0')
    libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6')
    libc.calloc.restype = ctypes.c_void_p
    libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
    libc.strdup.restype = ctypes.c_void_p
    libc.strdup.argtypes = [ctypes.c_char_p]
    libpam.pam_start.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(_PamConv),
                                 ctypes.POINTER(ctypes.c_void_p)]
    libpam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libpam.pam_setcred.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libpam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libpam.pam_strerror.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libpam.pam_strerror.restype = ctypes.c_char_p
    secret = password.encode('utf-8')

    def conv(n, msgs, resp, _data):
        # PAM frees the array and each answer: they must come from malloc
        arr = libc.calloc(n, ctypes.sizeof(_PamResponse))
        if not arr:
            return 5   # PAM_BUF_ERR
        answers = ctypes.cast(arr, ctypes.POINTER(_PamResponse))
        for i in range(n):
            style = msgs[i].contents.msg_style
            if style in (PAM_PROMPT_ECHO_OFF, PAM_PROMPT_ECHO_ON):
                answers[i].resp = libc.strdup(secret)
        resp[0] = answers
        return PAM_SUCCESS

    callback = _CONV(conv)
    handle = ctypes.c_void_p()
    rc = libpam.pam_start((service or pam_service()).encode(), user.encode(),
                          ctypes.byref(_PamConv(callback, None)), ctypes.byref(handle))
    if rc != PAM_SUCCESS:
        return False, 'pam_start %d' % rc
    rc = libpam.pam_authenticate(handle, 0)
    message = '' if rc == PAM_SUCCESS else (libpam.pam_strerror(handle, rc) or b'').decode()
    if rc == PAM_SUCCESS:
        libpam.pam_setcred(handle, 0x0008)    # PAM_REINITIALIZE_CRED: renew Kerberos and the like
    libpam.pam_end(handle, rc)
    return rc == PAM_SUCCESS, message if rc != PAM_AUTH_ERR else ''


# ── logind ──
def _logind_session(system):
    try:
        reply = system.call_sync('org.freedesktop.login1', '/org/freedesktop/login1',
                                 'org.freedesktop.login1.Manager', 'GetSessionByPID',
                                 GLib.Variant('(u)', (os.getpid(),)), GLib.VariantType('(o)'),
                                 Gio.DBusCallFlags.NONE, 2000, None)
        return reply.unpack()[0]
    except GLib.Error:
        return os.environ.get('XDG_SESSION_ID') and \
            '/org/freedesktop/login1/session/' + os.environ['XDG_SESSION_ID']


def set_locked_hint(locked: bool):
    """Tell logind, so `loginctl show-session` and other tools know the screen is locked."""
    try:
        system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        path = _logind_session(system)
        if path:
            system.call_sync('org.freedesktop.login1', path, 'org.freedesktop.login1.Session',
                             'SetLockedHint', GLib.Variant('(b)', (locked,)), None,
                             Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error as e:
        log.warning('SetLockedHint: %s', e.message)


# ── the screen ──
CSS = f"""
window.spark-lock {{ background: {theme.BG}; }}
.spark-lock-clock {{ font-size: 84pt; font-weight: bold; color: {theme.TEXT};
  text-shadow: 3px 0 {theme.CH_A}, -3px 0 {theme.CH_B}; }}
.spark-lock-date {{ font-size: 14pt; color: {theme.MUTED}; letter-spacing: 2px; }}
.spark-lock-card {{ background: {theme.PANEL}; border: 1px solid {theme.LINE2}; border-radius: 3px;
  padding: 22px 26px; }}
.spark-lock-card.error {{ border-color: {theme.PINK}; box-shadow: 5px 0 0 {theme.CH_A}, -5px 0 0 {theme.CH_B}; }}
.spark-lock-user {{ font-size: 14pt; font-weight: bold; color: {theme.TEXT}; }}
.spark-lock-state {{ font-size: 10pt; font-weight: bold; color: {theme.ACCENT}; letter-spacing: 2px; }}
.spark-lock-card entry {{ background: {theme.PANEL2}; color: {theme.TEXT}; border: 1px solid {theme.LINE};
  border-radius: 3px; min-height: 42px; padding: 0 12px; font-size: 12pt; caret-color: {theme.ACCENT}; }}
.spark-lock-card entry:focus-within {{ border-color: {theme.ACCENT}; }}
.spark-lock-msg {{ font-size: 11pt; color: {theme.MUTED}; }}
.spark-lock-msg.error {{ color: {theme.PINK}; }}
"""


def _user():
    entry = pwd.getpwuid(os.getuid())
    full = (entry.pw_gecos or '').split(',')[0].strip()
    return entry.pw_name, full or entry.pw_name


class LockScreen(Gtk.Application):
    def __init__(self, check=authenticate):
        super().__init__(application_id=None, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.check = check
        self.login, self.name = _user()
        self.views = []         # (window, clock, date, entry, message, card, monitor)
        self.busy = False
        self.exit_code = EXIT_NOT_LOCKED
        self.lock = None

    def do_activate(self):
        self.hold()
        display = Gdk.Display.get_default()
        for css in (theme.CSS, CSS):
            provider = Gtk.CssProvider()
            provider.load_from_string(css)
            Gtk.StyleContext.add_provider_for_display(display, provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if not SessionLock.is_supported():
            log.error('the compositor has no ext-session-lock')
            self.quit()
            return
        self.lock = SessionLock.Instance.new()
        self.lock.connect('monitor', self._on_monitor)
        self.lock.connect('locked', self._on_locked)
        self.lock.connect('failed', self._on_failed)
        self.lock.connect('unlocked', self._on_unlocked)
        if not self.lock.lock():
            log.error('could not lock')
            self.quit()
            return
        GLib.timeout_add_seconds(1, self._tick)
        # the shell passes on logind's Unlock (loginctl unlock-session) as SIGUSR1
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 10, self._unlock_signal)

    def _unlock_signal(self):
        log.info('unlock asked by logind')
        if self.lock is not None and self.lock.is_locked():
            self.lock.unlock()
        return True

    # lock events -------------------------------------------------------------------------
    def _on_monitor(self, lock, monitor):
        view = self._build(monitor)
        self.views.append(view)
        lock.assign_window_to_monitor(view[0], monitor)    # before the window is realized
        view[0].present()
        monitor.connect('invalidate', lambda *_: GLib.idle_add(self._place_card))
        self._place_card()
        self._tick()

    def _place_card(self):
        """The password box goes on the main monitor only (the first one, where the shell puts the
        tray); the others show the clock. If the main monitor is unplugged, the next one takes it."""
        live = [v for v in self.views if v[6].is_valid()]
        monitors = Gdk.Display.get_default().get_monitors()
        order = [monitors.get_item(i) for i in range(monitors.get_n_items())]
        live.sort(key=lambda v: order.index(v[6]) if v[6] in order else len(order))
        for i, v in enumerate(live):
            v[5].set_visible(i == 0)
        if live:
            live[0][3].grab_focus()
        return False

    def _on_locked(self, _lock):
        log.info('locked')
        set_locked_hint(True)

    def _on_failed(self, _lock):
        log.error('the compositor refused the lock (another locker?)')
        self.quit()

    def _on_unlocked(self, _lock):
        log.info('unlocked')
        self.exit_code = EXIT_UNLOCKED
        set_locked_hint(False)
        self.quit()

    # widgets -----------------------------------------------------------------------------
    def _build(self, monitor):
        win = Gtk.Window(application=self)
        win.add_css_class('spark-lock')
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        clock = Gtk.Label()
        clock.add_css_class('spark-lock-clock')
        date = Gtk.Label()
        date.add_css_class('spark-lock-date')
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class('spark-lock-card')
        card.set_margin_top(28)
        card.set_size_request(440, -1)
        state = Gtk.Label(label='● ' + tr('locked'), xalign=0)
        state.add_css_class('spark-lock-state')
        user = Gtk.Label(label=self.name, xalign=0)
        user.add_css_class('spark-lock-user')
        entry = Gtk.PasswordEntry()
        entry.set_property('placeholder-text', tr('password'))
        entry.connect('activate', lambda e: self._submit(e))
        message = Gtk.Label(label='', xalign=0, wrap=True, max_width_chars=40)
        message.add_css_class('spark-lock-msg')
        for w in (state, user, entry, message):
            card.append(w)
        outer.append(clock)
        outer.append(date)
        outer.append(card)
        win.set_child(outer)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key)
        win.add_controller(keys)
        return win, clock, date, entry, message, card, monitor

    def _key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape and not self.busy:
            for v in self.views:
                v[3].set_text('')
                self._say(v, '')
            return True
        return False

    def _tick(self):
        now = time.localtime()
        clock, date = time.strftime('%H:%M', now), time.strftime('%A %d %B', now).upper()
        for v in self.views:
            v[1].set_label(clock)
            v[2].set_label(date)
        return True

    def _say(self, view, text, error=False):
        view[4].set_label(text)
        for widget in (view[4], view[5]):
            (widget.add_css_class if error else widget.remove_css_class)('error')

    # the password ------------------------------------------------------------------------
    def _submit(self, entry):
        password = entry.get_text()
        if self.busy or not password:
            return
        self.busy = True
        view = next(v for v in self.views if v[3] is entry)
        for v in self.views:
            v[3].set_sensitive(False)
        self._say(view, tr('checking'))

        def work():
            try:
                ok, message = self.check(self.login, password)
            except Exception as e:      # noqa: BLE001 - a broken PAM must not freeze the lock
                ok, message = False, str(e)
            GLib.idle_add(self._checked, view, ok, message)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, view, ok, message):
        self.busy = False
        if ok:
            log.info('password accepted')
            self.lock.unlock()
            return False
        log.info('password refused%s', ': ' + message if message else '')
        for v in self.views:
            v[3].set_sensitive(True)
            v[3].set_text('')
        self._say(view, tr('auth_error') % message if message else tr('wrong_password'), True)
        GLib.timeout_add(450, lambda: view[5].remove_css_class('error') and False)
        view[3].grab_focus()
        return False


def run(check=authenticate) -> int:
    app = LockScreen(check)
    app.run([])
    return app.exit_code
