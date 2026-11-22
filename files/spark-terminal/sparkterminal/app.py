"""Starting Spark Terminal: the command line, the self-test, and the GTK application that owns
the windows. Each spark-terminal runs in its own process and returns when its last window
closes, so scripts can wait for the command they started (Konsole's --nofork)."""

import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from . import APP_ID, APP_NAME, GTK_VERSION, VTE_VERSION, cli, core
from .core import log

ACCELS = {
    'win.new-tab': ['<Control><Shift>t'],
    'win.new-window': ['<Control><Shift>n'],
    'win.close-pane': ['<Control><Shift>w'],
    'win.split-right': ['<Control><Shift>r'],
    'win.split-down': ['<Control><Shift>d'],
    'win.copy': ['<Control><Shift>c'],
    'win.paste': ['<Control><Shift>v', '<Shift>Insert'],
    'win.select-all': ['<Control><Shift>a'],
    'win.find': ['<Control><Shift>f'],
    'win.zoom-in': ['<Control>plus', '<Control>equal', '<Control>KP_Add'],
    'win.zoom-out': ['<Control>minus', '<Control>KP_Subtract'],
    'win.zoom-reset': ['<Control>0', '<Control>KP_0'],
    'win.reset': ['<Control><Shift>k'],
    'win.settings': ['<Control><Shift>comma'],
    'win.next-tab': ['<Control>Page_Down'],
    'win.prev-tab': ['<Control>Page_Up'],
    'win.focus-left': ['<Alt>Left'],
    'win.focus-right': ['<Alt>Right'],
    'win.focus-up': ['<Alt>Up'],
    'win.focus-down': ['<Alt>Down'],
}


def _import_gtk():
    import gi
    gi.require_version('Gtk', GTK_VERSION)
    gi.require_version('Vte', VTE_VERSION)
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Gtk, Vte   # noqa: F401
    return Gtk


def make_application(opts: cli.Options):
    Gtk = _import_gtk()
    from gi.repository import Gio
    from . import style
    from .window import Window

    class Application(Gtk.Application):

        def __init__(self):
            super().__init__(application_id=APP_ID,
                             flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.opts = opts
            self.settings = core.load_settings()
            self.started = time.monotonic()

        def do_startup(self):
            Gtk.Application.do_startup(self)
            style.install()
            for action, keys in ACCELS.items():
                self.set_accels_for_action(action, keys)
            for n in range(1, 10):
                self.set_accels_for_action(f'win.goto-tab({n})', [f'<Alt>{n}'])

        def do_activate(self):
            o = self.opts
            cwd = core.start_folder(o.workdir, self.settings)
            window = self.new_window(cwd=cwd, argv=o.command or None, hold=o.hold,
                                     title=o.title)
            if o.bench:
                self._bench_wait(window)

        def new_window(self, cwd: Optional[str] = None, argv: Optional[List[str]] = None,
                       hold: bool = False, title: Optional[str] = None):
            window = Window(self, title=title)
            window.new_tab(argv=argv, cwd=cwd or core.start_folder(None, self.settings),
                           hold=hold)
            window.present()
            return window

        def show_settings(self, parent):
            from .settings_ui import SettingsWindow
            SettingsWindow(parent, self.settings, self.save_settings, parent.glitch).present()

        def save_settings(self, data) -> bool:
            self.settings = core.clean_settings(data)
            ok = core.save_settings(self.settings)
            for window in self.get_windows():
                if hasattr(window, 'apply_settings'):
                    window.apply_settings(self.settings)
            return ok

        def _bench_wait(self, window):
            """--bench: print how long the window took to appear with a shell in it, then
            close it."""
            from gi.repository import GLib

            def check():
                pane = window.active_pane()
                if window.get_mapped() and pane is not None and pane.pid > 0:
                    print(f"bench: window with a shell {1000 * (time.monotonic() - BOOT):.0f} ms "
                          f"after the process started", flush=True)
                    window.force_close()
                    return False
                if time.monotonic() - BOOT > 20:
                    print("bench: no window after 20 s", flush=True)
                    window.force_close()
                    return False
                return True
            GLib.timeout_add(5, check)

    return Application()


# ─── self-test ──────────────────────────────────────────────


def self_test() -> int:
    """Checks what Spark Terminal needs without opening a window: GTK 4, VTE, a pty with a
    shell in it, the font, the settings folder. Prints one line per check."""
    failures = 0

    def check(name: str, ok: bool, detail: str = '') -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)

    try:
        import gi
        gi.require_version('Gtk', GTK_VERSION)
        gi.require_version('Vte', VTE_VERSION)
        from gi.repository import GLib, Vte
        check('GTK 4 and VTE (GTK 4)', True,
              f"VTE {Vte.get_major_version()}.{Vte.get_minor_version()}."
              f"{Vte.get_micro_version()}")
    except (ImportError, ValueError) as exc:
        check('GTK 4 and VTE (GTK 4)', False,
              f"{exc} (on Fedora: sudo dnf install gtk4 vte291-gtk4 python3-gobject)")
        return 1

    # a real pty from VTE, a shell in it, and its output read back
    try:
        pty = Vte.Pty.new_sync(Vte.PtyFlags.DEFAULT, None)
        loop = GLib.MainLoop()
        result = {}

        def spawned(p, res, _data=None):
            try:
                ok, pid = p.spawn_finish(res)
                result['pid'] = pid
            except GLib.Error as exc:
                result['error'] = exc.message
            loop.quit()
        shell = core.login_shell()
        pty.spawn_async(None, ['/bin/sh', '-c', 'printf "spark-%s\\n" terminal'], None,
                        GLib.SpawnFlags.DEFAULT, None, None, -1, None, spawned, None)
        GLib.timeout_add(5000, loop.quit)
        loop.run()
        if 'pid' not in result:
            check('pty and shell', False, result.get('error', 'timed out'))
        else:
            out, deadline = b'', time.monotonic() + 5
            fd = pty.get_fd()
            import select
            while b'spark-terminal' not in out and time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.2)
                if ready:
                    try:
                        out += os.read(fd, 4096)
                    except OSError:
                        break
            try:
                os.waitpid(result['pid'], 0)
            except ChildProcessError:
                pass
            check('pty and shell', b'spark-terminal' in out,
                  f"VTE pty ran /bin/sh; your shell is {shell}")
    except GLib.Error as exc:
        check('pty and shell', False, exc.message)

    fc = shutil.which('fc-list')
    if fc:
        fonts = subprocess.run([fc, ':spacing=mono', 'family'], capture_output=True,
                               text=True).stdout
        have = 'Cascadia Mono' in fonts or 'Cascadia Code' in fonts
        check('Cascadia Mono font', True,
              'installed' if have else 'not installed; another mono font is used')
    for name, folder in (('settings folder', core.config_dir()), ('log folder', core.state_dir())):
        check(name, os.access(folder, os.W_OK), folder)
    settings = core.load_settings()
    check('settings', True, f"shell {core.shell_argv(settings)[0]}, "
                            f"scrollback {settings['scrollback']} lines")
    if failures:
        print(f"FAILED: {failures} check{'s' if failures > 1 else ''}")
        return 1
    print("self-test passed")
    return 0


BOOT = time.monotonic()


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
    core.setup_logging()
    try:
        app = make_application(opts)
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} can't start: {exc}\nRun spark-terminal --self-test for details.",
              file=sys.stderr)
        return 1
    log.info("command line: %s", sys.argv[1:] if argv is None else argv)
    return app.run([sys.argv[0]])
