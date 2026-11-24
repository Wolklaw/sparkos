"""Starting Spark Notes: the command line, the self-test, and the GTK application.

The application is unique. `spark-notes` opens the notes window; `spark-notes --clipboard`
(Meta+V) opens the clipboard popup, or closes it when it is already open. After the popup
closes the process stays for a minute so the next Meta+V opens at once, then leaves. The
clipboard history is not kept by this process but by the background watcher (capture.py)."""

import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from . import APP_ID, APP_NAME, GTK_VERSION, VERSION, cli, core
from .capture import copy_item, have_wl_clipboard
from .core import log
from .text import t

LINGER_SECONDS = 60
WATCHER_PATTERN = r'wl-paste --watch .*spark_notes\.py --capture'


def watcher_running() -> bool:
    """True when a clipboard watcher is running for this user."""
    try:
        r = subprocess.run(['pgrep', '-u', str(os.getuid()), '-f', WATCHER_PATTERN],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return True      # can't tell; don't warn


def make_application():
    import gi
    gi.require_version('Gtk', GTK_VERSION)
    gi.require_version('Gdk', GTK_VERSION)
    from gi.repository import Gdk, Gio, GLib, Gtk
    from . import style
    from .clip_window import ClipWindow
    from .notes_window import NotesWindow

    class Application(Gtk.Application):

        def __init__(self):
            super().__init__(application_id=APP_ID,
                             flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.settings = core.load_settings()
            self.history = core.History()
            self.store = core.NoteStore()
            self.clip: Optional[ClipWindow] = None
            self.notes: Optional[NotesWindow] = None
            self.linger_id = 0
            self.holding = False
            self.glitch = None

        def do_startup(self):
            Gtk.Application.do_startup(self)
            style.install()
            self.glitch = style.Glitch(self.settings.get('glitch', True))

        def do_command_line(self, cmdline):
            args = cmdline.get_arguments()[1:]
            try:
                opts = cli.parse(args)
            except SystemExit:
                return 2
            if opts.clipboard:
                self.toggle_clipboard()
            else:
                self.show_notes()
            return 0

        def do_activate(self):
            self.show_notes()

        # --- the two windows ---

        def toggle_clipboard(self):
            if self.clip is not None and self.clip.get_visible():
                self.clip.close_popup()
                return
            self._cancel_linger()
            self.settings = core.load_settings()
            if self.clip is None:
                self.clip = ClipWindow(self, self.settings, self.history, self.copy,
                                       self.set_paused, self.show_notes, glitch=self.glitch)
                self.clip.connect('notify::visible', self._on_visible)
            else:
                self.clip.settings = self.settings
                self.clip.refresh()
            self.clip.present()
            self.clip.entry.grab_focus()
            GLib.idle_add(self._check_watcher)

        def show_notes(self):
            self._cancel_linger()
            if self.notes is None:
                self.notes = NotesWindow(self, self.store, self.settings,
                                         on_open_clipboard=self.toggle_clipboard,
                                         glitch=self.glitch)
                self.notes.connect('destroy', self._notes_gone)
            self.notes.present()

        def _notes_gone(self, _window):
            self.notes = None
            if self.clip is None or not self.clip.get_visible():
                self._linger()

        def _check_watcher(self) -> bool:
            if self.clip is None or not self.clip.get_visible():
                return False
            if not have_wl_clipboard():
                self.clip.set_status(t('clip.no_wl'), 'warn')
            elif not watcher_running():
                self.clip.set_status(t('clip.no_watcher'), 'warn')
                if self.glitch:
                    self.glitch.now(self.clip.status)
            return False

        # --- actions the windows ask for ---

        def copy(self, item) -> Tuple[bool, str]:
            if copy_item(item, self.history):
                log.info("copied an item again (%s)", item.kind)
                return True, ''
            if item.kind == 'text':        # wl-copy missing: this process holds it for a while
                display = Gdk.Display.get_default()
                clipboard = display.get_clipboard()
                clipboard.set(item.text) if not hasattr(clipboard, 'set_text') \
                    else clipboard.set_text(item.text)
                return True, ''
            return False, 'wl-copy is missing'

        def set_paused(self, paused: bool) -> None:
            self.settings['paused'] = paused
            core.save_settings(self.settings)
            log.info("keeping the clipboard: %s", 'paused' if paused else 'on')

        # --- staying alive a minute, then leaving ---

        def _on_visible(self, window, _param):
            if not window.get_visible() and self.notes is None:
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
            popup_open = self.clip is not None and self.clip.get_visible()
            if not popup_open and self.notes is None and self.holding:
                self.holding = False
                self.release()
            return False

    return Application()


# --- self-test --------------------------------------------------


def self_test() -> int:
    """Checks what Spark Notes needs, without a window. Files go in a temporary folder."""
    import tempfile
    failures = 0

    def check(name: str, ok: bool, detail: str = '') -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)

    # notes and history round trip, in a temporary folder (never the person's own)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            store = core.NoteStore(tmp)
            nid = store.new_id()
            store.save(nid, "# Shopping\nmilk\n")
            note = store.load(nid)
            check('notes', bool(note) and note.title == 'Shopping' and
                  [n.id for n in store.list('MILK')] == [nid], "write, read, search")
            hist = core.History(tmp)
            hist.add_text("one")
            hist.add_text("two")
            hist.add_text("one")
            items = hist.items()
            check('clipboard history', [i.text for i in items] == ['one', 'two'],
                  "newest first, a repeat moves up")
        except (OSError, ValueError) as exc:
            check('notes and history', False, str(exc))

    for name, folder in (('data folder', core.data_dir()), ('settings folder', core.config_dir()),
                         ('log folder', core.state_dir())):
        check(name, os.access(folder, os.W_OK), folder)

    try:
        import gi
        gi.require_version('Gtk', GTK_VERSION)
        from gi.repository import Gtk
        check('GTK 4', True, f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}."
                             f"{Gtk.get_micro_version()}")
    except (ImportError, ValueError) as exc:
        check('GTK 4', False, f"{exc} (on Fedora: sudo dnf install gtk4 python3-gobject)")
        return 1

    wl = have_wl_clipboard()
    check('wl-clipboard', wl, shutil.which('wl-paste') or
          "wl-paste and wl-copy are missing (on Fedora: sudo dnf install wl-clipboard)")

    # does the compositor offer data-control? Optional: a build container has no desktop
    if wl and os.environ.get('WAYLAND_DISPLAY'):
        try:
            r = subprocess.run(['wl-paste', '--list-types'], capture_output=True, text=True,
                               timeout=5)
            msg = (r.stderr or '').lower()
            if 'protocol' in msg or 'compositor' in msg or 'support' in msg:
                check('clipboard access (data-control)', False, r.stderr.strip())
            else:
                print("ok   clipboard access (data-control): the compositor accepts it")
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"info clipboard access: not checked ({exc})")
    else:
        print("info clipboard access: not checked (no Wayland session here)")

    state = 'running' if watcher_running() else 'not running'
    print(f"info clipboard watcher: {state}")

    if failures:
        print(f"FAILED: {failures} check{'s' if failures > 1 else ''}")
        return 1
    print("self-test passed")
    return 0


def list_command(query: str) -> int:
    items = core.History().search(query)
    if not items:
        print(t('cli.list_empty'))
        return 1
    for i in items:
        flat = i.preview(100).replace('\n', ' / ') if i.kind == 'text' else f"[{i.mime}]"
        print(f"{'*' if i.pinned else ' '} {core.ago(i.time):>8}  {flat}")
    return 0


def pause_command(paused: bool) -> int:
    settings = core.load_settings()
    settings['paused'] = paused
    ok = core.save_settings(settings)
    print(t('cli.paused' if paused else 'cli.resumed'))
    return 0 if ok else 1


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
    if opts.capture:
        from . import capture
        return capture.capture_main()
    if opts.watch:
        from . import capture
        core.setup_logging()
        core.log.info("--- %s %s watching the clipboard ---", APP_NAME, VERSION)
        return capture.watch()
    if opts.pause or opts.resume:
        return pause_command(opts.pause)
    if opts.list is not None:
        return list_command(opts.list)
    core.setup_logging()
    try:
        app = make_application()
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} can't start: {exc}\nRun spark-notes --self-test for details.",
              file=sys.stderr)
        return 1
    return app.run([sys.argv[0]] + (sys.argv[1:] if argv is None else argv))
