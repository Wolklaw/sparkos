"""Starting Spark Emoji: the command line, the self-test, and the GTK application. The
application is unique: pressing Meta+. while the picker is open closes it, and the process
stays around for a minute after a pick so the copied text is handed to the clipboard manager
(Spark Notes) and a second pick starts at once."""

import os
import shutil
import subprocess
import sys
from typing import List, Optional

from . import APP_ID, APP_NAME, GTK_VERSION, cli, core
from .core import log
from .text import t

PASTE_DELAY_MS = 180        # time for the desktop to put the old window back in front
LINGER_SECONDS = 60


def _import_gtk():
    import gi
    gi.require_version('Gtk', GTK_VERSION)
    from gi.repository import Gtk
    return Gtk


def make_application():
    Gtk = _import_gtk()
    from gi.repository import Gdk, Gio, GLib
    from . import paste, style
    from .window import PickerWindow

    class Application(Gtk.Application):

        def __init__(self):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.settings = core.load_settings()
            self.window = None
            self.portal = None
            self.linger_id = 0
            self.holding = False

        def do_startup(self):
            Gtk.Application.do_startup(self)
            style.install()

        def do_activate(self):
            if self.window is not None and self.window.get_visible():
                self.window.close_picker()
                return
            self._cancel_linger()
            if self.window is None:
                self.window = PickerWindow(self, self.settings, self.pick,
                                           on_enable_paste=self.enable_paste,
                                           on_tone=self.save_tone,
                                           glitch=style.Glitch(self.settings.get('glitch', True)))
                self.window.connect('notify::visible', self._on_visible)
                self._start_portal()
            else:
                self.window.show_default()
            self.window.show_paste_button(not self._paste_ready_or_wanted())
            self.window.present()
            self.window.entry.grab_focus()

        # --- pasting ---

        def _paste_ready_or_wanted(self) -> bool:
            return bool(self.settings.get('paste'))

        def _start_portal(self):
            if not self.settings.get('paste'):
                return
            self.portal = paste.PortalKeyboard(self.settings.get('portal_token', ''))

            def done(ok, why):
                if ok:
                    self._remember_token()
                else:
                    log.warning("pasting is on in the settings but the portal said: %s", why)
                    if self.window:
                        self.window.set_status(t('paste.refused', why=why), 'warn')
                        self.window.show_paste_button(True)
            self.portal.start(done)

        def _remember_token(self):
            if self.portal and self.portal.token != self.settings.get('portal_token'):
                self.settings['portal_token'] = self.portal.token
                core.save_settings(self.settings)

        def enable_paste(self):
            """The button in the window: ask the desktop once, with its own question."""
            win = self.window
            win.keep_open = True
            win.set_status(t('paste.waiting'))
            self.portal = paste.PortalKeyboard(self.settings.get('portal_token', ''))

            def done(ok, why):
                win.keep_open = False
                if ok:
                    self.settings['paste'] = True
                    self._remember_token()
                    core.save_settings(self.settings)
                    win.set_status(t('paste.on'), 'ok')
                    win.show_paste_button(False)
                else:
                    win.set_status(t('paste.refused', why=why), 'warn')
                    if win.glitch:
                        win.glitch.now(win.status)
                win.present()
            self.portal.start(done)

        def save_tone(self, tone: int):
            self.settings['tone'] = tone
            core.save_settings(self.settings)

        def pick(self, char: str, entry):
            """Copy it, put the old window back in front, press Ctrl+V if allowed."""
            core.add_recent(char)
            display = Gdk.Display.get_default()
            clipboard = display.get_clipboard()
            if hasattr(clipboard, 'set_text'):
                clipboard.set_text(char)
            else:
                clipboard.set(char)
            log.info("picked %s (%s)", char, entry.name_en if entry else '?')
            pasting = bool(self.portal and self.portal.state == 'ready')
            self.window.close_picker()
            if pasting:
                GLib.timeout_add(PASTE_DELAY_MS, self._send_paste, char)
            else:
                self._notify_copied(char)

        def _send_paste(self, char: str) -> bool:
            if not (self.portal and self.portal.paste()):
                self._notify_copied(char)
            return False

        def _notify_copied(self, char: str):
            note = Gio.Notification.new(t('notify.title', char=char))
            note.set_body(t('notify.body'))
            self.send_notification('copied', note)
            GLib.timeout_add_seconds(4, lambda: self.withdraw_notification('copied') or False)

        # --- staying alive a minute, then leaving ---

        def _on_visible(self, window, _param):
            if not window.get_visible():
                self._linger()

        def _linger(self):
            self._cancel_linger()
            if not self.holding:
                self.hold()
                self.holding = True
            self.linger_id = GLib.timeout_add_seconds(LINGER_SECONDS, self._leave)

        def _cancel_linger(self):
            if self.linger_id:
                GLib.source_remove(self.linger_id)
                self.linger_id = 0

        def _leave(self) -> bool:
            self.linger_id = 0
            if self.window is None or not self.window.get_visible():
                if self.portal:
                    self.portal.close()
                if self.holding:
                    self.holding = False
                    self.release()
            return False

    return Application()


# ─── self-test ──────────────────────────────────────────────


def self_test() -> int:
    """Checks the data, the search and what the window and pasting need, without a window."""
    failures = 0

    def check(name: str, ok: bool, detail: str = '') -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)

    try:
        groups = core.groups()
        emoji = sum(len(g.entries) for g in groups if g.kind == 'emoji')
        symbols = sum(len(g.entries) for g in groups if g.kind == 'symbol')
        check('data', emoji > 1500 and symbols > 200,
              f"{emoji} emoji, {symbols} symbols")
    except (OSError, ValueError, KeyError) as exc:
        check('data', False, str(exc))
        return 1

    probes = [("sourire", '\U0001F600'), ("grinning", '\U0001F600'), ("coeur", '❤️'),
              ("heart", '❤️'), ("euro", '€'), ("fleche droite", '→'),
              ("e accent aigu", 'é'), ("U+1F44D", '\U0001F44D'), ("pouce", '\U0001F44D'),
              ("drapeau canada", '\U0001F1E8\U0001F1E6')]
    for query, want in probes:
        found = core.search(query, limit=10)
        got = [e.char for e in found]
        check(f"search {query!r}", want in got,
              f"{want} {'is' if want in got else 'is not'} in the first {len(got)}")

    en_only = [e for e in core.all_entries() if not e.name_fr]
    check('names in both languages', not en_only, f"{len(en_only)} without a French name")

    fc = shutil.which('fc-list')
    if fc:
        out = subprocess.run([fc, ':charset=1f600', 'family'], capture_output=True,
                             text=True).stdout.strip()
        check('a font with emoji', bool(out), out.splitlines()[0] if out else
              "no font has U+1F600; emoji show as boxes")

    try:
        import gi
        gi.require_version('Gtk', GTK_VERSION)
        from gi.repository import Gtk
        check('GTK 4', True, f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}."
                             f"{Gtk.get_micro_version()}")
    except (ImportError, ValueError) as exc:
        check('GTK 4', False, f"{exc} (on Fedora: sudo dnf install gtk4 python3-gobject)")
        return 1

    for name, folder in (('settings folder', core.config_dir()), ('log folder', core.state_dir())):
        check(name, os.access(folder, os.W_OK), folder)

    # pasting is optional: report, never fail
    try:
        from . import paste
        have = paste.portal_available()
        print(f"info pasting: the desktop {'offers' if have else 'does not offer (here)'} "
              f"a remote-keyboard portal; without it Spark Emoji copies and you press Ctrl+V")
    except Exception as exc:   # no session bus in a build container
        print(f"info pasting: not checked ({exc})")

    if failures:
        print(f"FAILED: {failures} check{'s' if failures > 1 else ''}")
        return 1
    print("self-test passed")
    return 0


def search_command(query: str, limit: int) -> int:
    found = core.search(query, limit=limit)
    for e in found:
        print(f"{e.char}\t{e.name_en}\t{e.name_fr}")
    return 0 if found else 1


def main(argv: Optional[List[str]] = None) -> int:
    try:
        opts = cli.parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if opts.version:
        print(cli.version_line())
        return 0
    if opts.self_test:
        return self_test()
    if opts.search is not None:
        return search_command(opts.search, opts.limit)
    core.setup_logging()
    try:
        app = make_application()
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} can't start: {exc}\nRun spark-emoji --self-test for details.",
              file=sys.stderr)
        return 1
    return app.run([sys.argv[0]])
