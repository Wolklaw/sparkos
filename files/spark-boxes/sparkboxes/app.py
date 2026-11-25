"""Starting Spark Boxes: the command line, the self-test, and the GTK application. One window;
`spark-boxes NAME` opens that machine's screen from the same process."""

import os
import shutil
import sys
import tempfile
from typing import List, Optional

from . import APP_ID, APP_NAME, GTK_VERSION, VERSION, cli, core, isoinfo, usbdev, xmlgen
from .core import log
from .text import t


def make_application(manager: Optional[core.Manager] = None):
    import gi
    gi.require_version('Gtk', GTK_VERSION)
    gi.require_version('Gdk', GTK_VERSION)
    from gi.repository import Gio, GLib, Gtk
    from . import style
    from .console import ConsoleWindow
    from .window import BoxesWindow

    class Application(Gtk.Application):

        def __init__(self):
            super().__init__(application_id=APP_ID,
                             flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.manager = manager or core.Manager(glib_events=True)
            self.window: Optional[BoxesWindow] = None
            self.consoles = {}
            self.glitch = None

        def do_startup(self):
            Gtk.Application.do_startup(self)
            style.install()
            self.glitch = style.Glitch(True)

        def do_command_line(self, cmdline):
            try:
                opts = cli.parse(cmdline.get_arguments()[1:])
            except SystemExit:
                return 2
            self.show_window()
            if opts.machine:
                GLib.timeout_add(600, self._open_named, opts.machine)
            return 0

        def do_activate(self):
            self.show_window()

        def show_window(self):
            if self.window is None:
                self.window = BoxesWindow(self, self.manager, self.glitch, self.open_console)
                self.window.connect('destroy', self._gone)
            self.window.present()

        def _gone(self, _window):
            self.window = None

        def _open_named(self, name):
            if self.window is None:
                return False
            vm = next((v for v in self.window.vms if v.name == name), None)
            if vm is None:
                self.window.say(t('new.name_empty'), 'warn')
            elif vm.state == 'off':
                self.window.work(lambda: self.manager.start(name),
                                 lambda _r: GLib.timeout_add(1500, self._open_named, name))
            else:
                self.open_console(name)
            return False

        def open_console(self, name: str):
            existing = self.consoles.get(name)
            if existing is not None:
                existing.present()
                return
            win = ConsoleWindow(self, self.manager, name, self._send_keys, self.glitch)
            self.consoles[name] = win
            win.connect('destroy', lambda *_: self.consoles.pop(name, None))

        def _send_keys(self, name, keys):
            try:
                self.manager.send_keys(name, keys)
            except core.BoxesError as exc:
                log.warning("%s", exc)

    return Application()


def self_test() -> int:
    """Checks what Spark Boxes needs, without a window and without touching real machines. The
    libvirt part runs against libvirt's built-in test driver."""
    failures = 0

    def check(name: str, ok: bool, detail: str = '') -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)

    try:
        import libvirt
        check('python3-libvirt', True, f"libvirt {libvirt.getVersion() // 1000000}."
              f"{libvirt.getVersion() // 1000 % 1000}")
    except ImportError as exc:
        check('python3-libvirt', False, f"{exc} (on Fedora: sudo dnf install python3-libvirt)")
        return 1

    try:
        import gi
        gi.require_version('Gtk', GTK_VERSION)
        from gi.repository import Gtk
        check('GTK 3', True, f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}")
        gi.require_version('SpiceClientGLib', '2.0')
        gi.require_version('SpiceClientGtk', '3.0')
        from gi.repository import SpiceClientGLib, SpiceClientGtk  # noqa: F401
        check('spice-gtk', True, "the screen widget loads")
    except (ImportError, ValueError) as exc:
        check('GTK 3 and spice-gtk', False, f"{exc} (on Fedora: sudo dnf install gtk3 "
                                            "spice-gtk3 python3-gobject)")

    # the machine description, built and read back by libvirt's test driver
    manager = core.Manager('test:///default', glib_events=True)
    try:
        manager.connect()
        spec = xmlgen.VmSpec(name='selftest', preset='linux', cpus=1, memory_mb=1024, kvm=False,
                             disk_path='/var/lib/libvirt/images/selftest.qcow2')
        dom = manager.conn.defineXML(xmlgen.build_xml(spec))
        info = manager.info(dom)
        manager.conn.lookupByName('selftest').undefine()
        check('machine description', info.name == 'selftest' and info.cpus == 1
              and info.preset == 'linux', "libvirt accepts it and gives it back")
    except (core.BoxesError, Exception) as exc:   # noqa: BLE001
        check('machine description', False, str(exc))
    finally:
        manager.close()

    with tempfile.TemporaryDirectory() as tmp:
        iso = os.path.join(tmp, 'fedora.iso')
        with open(iso, 'wb') as f:
            f.write(b'\0' * isoinfo.PVD_OFFSET + b'\x01CD001\x01\0' + b'Fedora-Live'.ljust(32) * 1)
        check('ISO label', isoinfo.volume_label(iso) is not None, "read from a made-up image")
    check('USB list', isinstance(usbdev.list_devices(), list), "sysfs readable")

    for name, folder in (('state folder', core.state_dir()), ('cache folder', core.cache_dir())):
        check(name, os.access(folder, os.W_OK), folder)

    # information only: the build container has no KVM and no daemon
    print(f"info /dev/kvm: {'present' if os.path.exists('/dev/kvm') else 'missing (machines would run slowly)'}")
    for tool in ('qemu-img', 'swtpm', 'virtqemud'):
        print(f"info {tool}: {shutil.which(tool) or shutil.which(tool, path='/usr/sbin:/usr/libexec') or 'not found'}")
    try:
        real = core.Manager()
        real.connect()
        print(f"info {real.uri}: reachable, {len(real.list_vms())} machine(s)")
        real.close()
    except core.Unavailable as exc:
        print(f"info {core.uri()}: {exc.kind} ({exc.detail.splitlines()[0] if exc.detail else ''})")

    if failures:
        print(f"FAILED: {failures} check{'s' if failures > 1 else ''}")
        return 1
    print("self-test passed")
    return 0


def list_command() -> int:
    manager = core.Manager()
    try:
        manager.connect()
        vms = manager.list_vms()
    except core.Unavailable as exc:
        print(t('cli.unavailable', why=exc.detail or exc.kind), file=sys.stderr)
        return 1
    if not vms:
        print(t('cli.none'))
        return 0
    for vm in vms:
        print(f"{vm.name:<24} {t('state.' + vm.state):<10} {vm.cpus} CPU  {vm.memory_mb} MB")
    return 0


def power_command(name: str, start: bool) -> int:
    manager = core.Manager()
    try:
        manager.connect()
        (manager.start if start else manager.shutdown)(name)
    except core.BoxesError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{name}: {'starting' if start else 'shutting down'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        opts = cli.parse(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    if opts.version:
        print(cli.version_line())
        return 0
    if opts.self_test:
        return self_test()
    core.setup_logging()
    if opts.list:
        return list_command()
    if opts.start:
        return power_command(opts.start, True)
    if opts.shutdown:
        return power_command(opts.shutdown, False)
    try:
        app = make_application()
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} can't start: {exc}\nRun spark-boxes --self-test for details.",
              file=sys.stderr)
        return 1
    log.info("--- %s %s ---", APP_NAME, VERSION)
    return app.run([sys.argv[0]] + args)
