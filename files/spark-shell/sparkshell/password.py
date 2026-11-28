"""Change password (spark-shell --password), opened from the power row like Windows' Ctrl+Alt+Del
screen: current, new and again, then passwd does the change.

passwd runs on a pseudo-terminal and gets the answers to its prompts, so the whole PAM password
stack runs as it would in a terminal: pam_pwquality's rules. Spark Secrets does not change with it: at the
next sign-in it asks once for the old password, then keeps the new one.

change() needs no display and is tested in tests/test_units.py with a fake passwd."""

import os
import pty
import re
import select
import signal
import threading
import time

PROMPT_CURRENT = re.compile(rb'(current|\(current\) unix) password:\s*$', re.I)
PROMPT_NEW = re.compile(rb'new password:\s*$', re.I)
PROMPT_AGAIN = re.compile(rb'(retype|re-enter|repeat) new password:\s*$', re.I)
DONE = re.compile(rb'updated successfully', re.I)
BAD = re.compile(rb'BAD PASSWORD:\s*([^\r\n]+)')
FAIL = re.compile(rb'passwd:\s*([^\r\n]+)')


def check(current: str, new: str, again: str):
    """The checks done before passwd runs: an error key for strings.py, or None."""
    if not current:
        return 'pw_need_current'
    if not new:
        return 'pw_need_new'
    if new != again:
        return 'pw_mismatch'
    if new == current:
        return 'pw_same'
    return None


def change(current: str, new: str, command=('passwd',), timeout=30.0):
    """Run passwd and answer it. Returns (ok, message): message is passwd's own reason when it
    refuses (BAD PASSWORD: ..., or its error line), empty when it worked."""
    pid, fd = pty.fork()
    if pid == 0:                                    # child: passwd on the pty, in English
        try:
            env = dict(os.environ, LC_ALL='C', LANG='C', LANGUAGE='')
            os.execvpe(command[0], list(command), env)
        finally:
            os._exit(127)
    out, sent, end = b'', 0, time.monotonic() + timeout
    answers = []                                    # what was typed, in order (for the result)
    try:
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    pid = 0
                    break
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:                         # EIO: passwd closed the pty
                break
            if not chunk:
                break
            out += chunk
            tail = out[sent:]
            bad = BAD.search(tail)
            if bad:                                 # pwquality said no: stop, do not retry
                return False, bad.group(1).decode(errors='replace').strip()
            if PROMPT_AGAIN.search(tail):
                answer, what = new, 'again'
            elif PROMPT_NEW.search(tail):
                answer, what = new, 'new'
            elif PROMPT_CURRENT.search(tail):
                if 'current' in answers:            # asked twice: the first one was refused
                    return False, ''
                answer, what = current, 'current'
            else:
                continue
            answers.append(what)
            sent = len(out)
            os.write(fd, answer.encode() + b'\n')
        else:
            return False, 'timeout'
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        status = 0
        if pid:
            try:
                _, status = os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        os.close(fd)
    if DONE.search(out):
        return True, ''
    tail = out[sent:]
    errors = [m.group(1).decode(errors='replace').strip() for m in FAIL.finditer(tail)]
    errors = [e for e in errors if e and 'unchanged' not in e]
    if errors and 'manipulation' in errors[0] and answers == ['current']:
        return False, ''                            # Fedora's way of saying "wrong password"
    return False, errors[0] if errors else ''


# ── the window ──
def run() -> int:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gdk, Gio, GLib, Gtk

    from . import layer, theme
    from .lockscreen import _user
    from .strings import tr

    css = f"""
window.spark-password {{ background: rgba(4,9,11,0.86); }}
.spark-pw-card {{ background: {theme.PANEL}; border: 1px solid {theme.LINE2}; border-radius: 3px;
  padding: 22px 26px; box-shadow: 3px 0 0 {theme.CH_A}, -3px 0 0 {theme.CH_B}; }}
.spark-pw-card.error {{ border-color: {theme.PINK}; box-shadow: 5px 0 0 {theme.CH_A}, -5px 0 0 {theme.CH_B}; }}
.spark-pw-title {{ font-size: 10pt; font-weight: bold; color: {theme.ACCENT}; letter-spacing: 2px; }}
.spark-pw-user {{ font-size: 14pt; font-weight: bold; color: {theme.TEXT}; }}
.spark-pw-card entry {{ background: {theme.PANEL2}; color: {theme.TEXT}; border: 1px solid {theme.LINE};
  border-radius: 3px; min-height: 38px; padding: 0 12px; font-size: 11pt; caret-color: {theme.ACCENT}; }}
.spark-pw-card entry:focus-within {{ border-color: {theme.ACCENT}; }}
.spark-pw-msg {{ font-size: 10pt; color: {theme.MUTED}; }}
.spark-pw-msg.error {{ color: {theme.PINK}; }}
.spark-pw-msg.ok {{ color: {theme.ACCENT}; }}
"""

    class PasswordWindow(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='dev.wolklaw.SparkPassword',
                             flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.win = None
            self.busy = False
            self.code = 1

        def do_activate(self):
            if self.win is not None:                # opened again while open: bring it up
                self.win.present()
                return
            display = Gdk.Display.get_default()
            if display is None:
                return
            for text in (theme.CSS, css):
                provider = Gtk.CssProvider()
                provider.load_from_string(text)
                Gtk.StyleContext.add_provider_for_display(
                    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            win = self.win = Gtk.Window(application=self, title=tr('pw_title'))
            win.add_css_class('spark-password')
            win.set_decorated(False)
            if not layer.setup(win, 'overlay', ('top', 'bottom', 'left', 'right'),
                               'spark-password', exclusive=-1, keyboard='exclusive'):
                win.set_default_size(520, 420)

            outer = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            card = self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class('spark-pw-card')
            card.set_size_request(440, -1)
            title = Gtk.Label(label='● ' + tr('pw_title'), xalign=0)
            title.add_css_class('spark-pw-title')
            user = Gtk.Label(label=_user()[1], xalign=0)
            user.add_css_class('spark-pw-user')
            card.append(title)
            card.append(user)
            self.entries = []
            for key in ('pw_current', 'pw_new', 'pw_again'):
                entry = Gtk.PasswordEntry(show_peek_icon=True)
                entry.set_property('placeholder-text', tr(key))
                entry.connect('activate', self._next)
                card.append(entry)
                self.entries.append(entry)
            self.message = Gtk.Label(label=tr('pw_keyring'), xalign=0, wrap=True,
                                     max_width_chars=44)
            self.message.add_css_class('spark-pw-msg')
            card.append(self.message)
            row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
            row.set_margin_top(6)
            self.cancel = Gtk.Button(label=tr('cancel'))
            self.cancel.add_css_class('spark-btn')
            self.cancel.connect('clicked', lambda *_: self.quit())
            self.ok = Gtk.Button(label=tr('pw_change'))
            self.ok.add_css_class('spark-btn')
            self.ok.add_css_class('spark-primary')
            self.ok.connect('clicked', lambda *_: self._submit())
            row.append(self.cancel)
            row.append(self.ok)
            card.append(row)
            outer.append(card)
            win.set_child(outer)

            keys = Gtk.EventControllerKey()
            keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keys.connect('key-pressed', self._key)
            outer.add_controller(keys)      # a layer-shell window's own controller never fires
            win.present()
            self.entries[0].grab_focus()

        def _key(self, _ctl, keyval, _code, _state):
            if keyval == Gdk.KEY_Escape and not self.busy:
                self.quit()
                return True
            return False

        def _next(self, entry):
            i = self.entries.index(entry)
            if i < 2 and not self.entries[i + 1].get_text():
                self.entries[i + 1].grab_focus()
            else:
                self._submit()

        def _say(self, text, kind=''):
            self.message.set_label(text)
            for c in ('error', 'ok'):
                (self.message.add_css_class if c == kind else self.message.remove_css_class)(c)
            if kind == 'error':
                self.card.add_css_class('error')
                GLib.timeout_add(450, lambda: self.card.remove_css_class('error') and False)

        def _submit(self):
            if self.busy:
                return
            current, new, again = (e.get_text() for e in self.entries)
            problem = check(current, new, again)
            if problem:
                self._say(tr(problem), 'error')
                focus = {'pw_need_current': 0, 'pw_same': 1, 'pw_need_new': 1}.get(problem, 2)
                self.entries[focus].grab_focus()
                return
            self.busy = True
            for w in self.entries + [self.ok, self.cancel]:
                w.set_sensitive(False)
            self._say(tr('pw_working'))

            def work():
                try:
                    ok, message = change(current, new)
                except Exception as e:      # noqa: BLE001 - shown, never a frozen window
                    ok, message = False, str(e)
                GLib.idle_add(self._done, ok, message)
            threading.Thread(target=work, daemon=True).start()

        def _done(self, ok, message):
            self.busy = False
            if ok:
                self.code = 0
                self._say(tr('pw_done'), 'ok')
                GLib.timeout_add(1400, lambda: self.quit() or False)
                return False
            for w in self.entries + [self.ok, self.cancel]:
                w.set_sensitive(True)
            if message:
                self._say(tr('pw_refused') % message, 'error')
                self.entries[1].set_text('')
                self.entries[2].set_text('')
                self.entries[1].grab_focus()
            else:
                self._say(tr('wrong_password'), 'error')
                self.entries[0].set_text('')
                self.entries[0].grab_focus()
            return False

    app = PasswordWindow()
    app.run([])
    return app.code
