"""The command line. --version and --self-test never load Tk. --route is how the image's
stand-ins for systemsettings and kcmshell6 send a page Spark Settings owns here, and every other
module to KDE's own."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION

# the tools each page uses: (command, what for, needed in the image)
TOOLS = [
    ('wlr-randr', "Displays", True), ('wpctl', "Sound", True), ('pw-play', "Sound test tone", True),
    ('nmcli', "Network", True), ('bluetoothctl', "Bluetooth", True),
    ('busctl', "Time, users, power, input and shortcuts (D-Bus)", True), ('xdg-mime', "Default apps", True),
    ('timedatectl', "Date and time", True), ('localectl', "Language", True),
    ('lsblk', "Storage", False),
    ('lpstat', "Printers", True), ('lpadmin', "Printers (add)", True), ('lpinfo', "Printers (find)", True),
    ('lp', "Printers (test page)", True), ('rpm-ostree', "About (image)", True),
    ('pw-metadata', "Sound sample rate", False), ('pactl', "Live sound updates", False), ('lspci', "About (graphics)", False),
    ('dbus-monitor', "Live Bluetooth updates", False),
]


def self_test(strict: bool = False) -> int:
    from . import clock, core, displays, i18n, kcms, network, sound
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    failures: List[str] = []
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    for name, folder in (('settings', core.config_dir()), ('state', core.state_dir())):
        ok = os.path.isdir(folder) and os.access(folder, os.W_OK)
        print(f"{name + ':':<10} {folder} ({'writable' if ok else 'NOT writable'})")
        if not ok:
            failures.append(name)
    missing = []
    for tool, what, needed in TOOLS:
        path = shutil.which(tool)
        print(f"{tool + ':':<18} {path or 'MISSING'}  ({what})")
        if not path and needed:
            missing.append(tool)
    kde = core.kde_tool('systemsettings')
    print(f"{'systemsettings:':<18} {kde or 'not installed'}  (--kde)")
    if missing:
        print("missing tools: " + ', '.join(missing) +
              ("" if strict else "  (those pages say so; use --strict to fail on this)"))
        if strict:
            failures.append("tools")
    # the parsers and the French text, without a display or any real setting
    bad = []
    if network.split_terse(r'yes:My\:Wifi:80:WPA2') != ['yes', 'My:Wifi', '80', 'WPA2']:
        bad.append("nmcli")
    if sound.parse_status("Audio\n ├─ Sinks:\n │  *   52. Speakers [vol: 0.40]\n").sinks[0].id != 52:
        bad.append("wpctl")
    if displays.parse('[]') != [] or displays.parse('not json') != []:
        bad.append("wlr-randr")
    if kcms.route_for('kcm_kscreen') != 'displays':
        bad.append("routes")
    if bad:
        print("parsers:   FAILED: " + ', '.join(bad))
        failures.append("parsers")
    else:
        print("parsers:   ok")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def route(tool: str, args: List[str]) -> int:
    """systemsettings / kcmshell6 as Plasma calls them."""
    from . import core, kcms
    plain = [a for a in args if not a.startswith('-')]
    page = None
    if tool == 'systemsettings' and not args and not os.environ.get('SPARK_SETTINGS_KDE'):
        return run_app(None)
    if len(plain) == 1 and len(args) == 1:
        page = kcms.route_for(plain[0].split('/')[0])
    if page:
        return run_app(page)
    real = core.kde_tool(tool)
    if not real:
        print(f"{tool} isn't installed", file=sys.stderr)
        return 1
    os.execv(real, [real, *args])
    return 1


def run_app(page: Optional[str]) -> int:
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App
    try:
        app = App(page)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--route']:                    # --route TOOL [--] ARGS...
        tool = argv[1] if len(argv) > 1 else 'systemsettings'
        rest = argv[2:]
        if rest[:1] == ['--']:
            rest = rest[1:]
        return route(tool, rest)
    from .pages import PAGES
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS settings.",
        epilog="MODULE: a KDE settings module such as kcm_kscreen; Spark Settings opens its own "
               "page for it when it has one, else KDE's module.")
    parser.add_argument('module', nargs='?', help="a KDE settings module to open")
    parser.add_argument('--page', choices=sorted(PAGES), help="open this page")
    parser.add_argument('--kde', action='store_true', help="open KDE's System Settings instead")
    parser.add_argument('--self-test', action='store_true', help="check the tools the pages use; no display needed")
    parser.add_argument('--strict', action='store_true', help="with --self-test: fail when a tool is missing")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.strict)
    if args.kde:
        from . import core
        real = core.kde_tool('systemsettings')
        if not real:
            print("KDE's System Settings isn't installed", file=sys.stderr)
            return 1
        os.execv(real, [real, *([args.module] if args.module else [])])
    if args.module:
        return route('kcmshell6', [args.module])
    return run_app(args.page)
