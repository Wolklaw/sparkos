"""The command line. --version and --self-test never load Tk."""

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
    from . import core, displays, network, sound
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
    from .pages import PAGES
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS settings.")
    parser.add_argument('--page', choices=sorted(PAGES), help="open this page")
    parser.add_argument('--self-test', action='store_true', help="check the tools the pages use; no display needed")
    parser.add_argument('--strict', action='store_true', help="with --self-test: fail when a tool is missing")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.strict)
    return run_app(args.page)
