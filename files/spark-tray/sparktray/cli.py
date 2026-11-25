"""The command line. --version, --self-test and the settings flags never open a window."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test(fake_dir: str = '') -> int:
    """Check the pieces without a display: GTK loads, both languages have the same sentences,
    and say which services this PC has. Missing services are notes, not failures, so this
    also runs in a build container."""
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        print(f"gtk:       {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}")
    except (ImportError, ValueError) as exc:
        print(f"gtk:       MISSING ({exc})")
        failures.append("gtk")
        print("FAILED: " + ", ".join(failures))
        return 1
    try:
        gi.require_version('GtkLayerShell', '0.1')
        print("layer:     gtk-layer-shell present (popups sit in a corner on Wayland)")
    except ValueError:
        print("layer:     gtk-layer-shell not installed (popups open under the pointer)")

    from . import audio, text
    problems = text.check_tables()
    print(f"text:      {len(text.EN)} sentences in English and French"
          + ("" if not problems else f"; PROBLEMS: {problems}"))
    if problems:
        failures.append("text")

    from .dbusutil import Bus, BusError
    for label, bus_kind in (("system bus", Bus.system), ("session bus", Bus.session)):
        try:
            bus = bus_kind()
        except Exception as exc:                      # noqa: BLE001
            print(f"{label}: not reachable ({exc})")
            continue
        names = {'system bus': (('NetworkManager', 'org.freedesktop.NetworkManager'),
                                ('BlueZ', 'org.bluez'), ('UPower', 'org.freedesktop.UPower'),
                                ('logind', 'org.freedesktop.login1'),
                                ('power profiles', 'net.hadess.PowerProfiles')),
                 'session bus': (('tray watcher', 'org.kde.StatusNotifierWatcher'),)}[label]
        for name, owner in names:
            try:
                print(f"{label}: {name}: {'running' if bus.has_owner(owner) else 'not running'}")
            except BusError as exc:
                print(f"{label}: {name}: {exc}")
    print(f"printing:  {'lpstat found' if shutil.which('lpstat') else 'lpstat not found (cups-client)'}")
    folder = audio.find_spark_audio()
    print(f"volume:    Spark Audio {'in ' + folder if folder else 'not installed (no volume icon)'}")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _onoff(value: str) -> bool:
    return value.lower() in ('on', 'yes', 'true', '1')


def settings(args) -> Optional[int]:
    """The flags that change what is saved. Returns an exit code, or None to run the tray."""
    from . import autostart, core
    done = False
    if args.enable:
        autostart.enable()
        print("Spark Tray will start at login.")
        done = True
    if args.disable:
        autostart.disable()
        print("Spark Tray will not start at login.")
        done = True
    if args.reset:
        autostart.reset()
        print("Autostart is back to the default: on in the Spark session, off in Plasma.")
        done = True
    if args.item:
        name, state = args.item
        if name not in core.ITEMS:
            print(f"unknown item {name!r}; the items are: {', '.join(core.ITEMS)}", file=sys.stderr)
            return 2
        if state.lower() not in ('on', 'off', 'yes', 'no', 'true', 'false', '1', '0'):
            print("say on or off", file=sys.stderr)
            return 2
        core.set_item_enabled(name, _onoff(state))
        print(f"{name}: {'on' if _onoff(state) else 'off'}")
        done = True
    if args.power_without_battery:
        cfg = core.load_config()
        cfg['power_show_without_battery'] = _onoff(args.power_without_battery)
        core.save_config(cfg)
        print(f"power icon without a battery: {args.power_without_battery}")
        done = True
    if args.status:
        st = autostart.status()
        cfg = core.load_config()
        print(f"autostart: {st['mode']} ({'starts' if st['effective'] else 'does not start'} "
              f"at login in this session)")
        for name in core.ITEMS:
            print(f"item:      {name}: {'on' if cfg['items'][name] else 'off'}")
        print(f"power icon without a battery: {'on' if cfg['power_show_without_battery'] else 'off'}")
        done = True
    return 0 if done else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: network, Bluetooth, power, printer and volume "
        "icons for the tray.")
    parser.add_argument('--enable', action='store_true', help="start at login (also in Plasma)")
    parser.add_argument('--disable', action='store_true', help="never start at login")
    parser.add_argument('--reset', action='store_true',
                        help="autostart back to the default: on in the Spark session only")
    parser.add_argument('--item', nargs=2, metavar=('NAME', 'on|off'),
                        help="turn one icon on or off: network, bluetooth, power, printers, volume")
    parser.add_argument('--power-without-battery', metavar='on|off',
                        help="show the power icon on a PC with no battery (default off)")
    parser.add_argument('--status', action='store_true', help="show what is on")
    parser.add_argument('--self-test', action='store_true',
                        help="check the pieces and the services; no display needed")
    parser.add_argument('--fake', metavar='DIR',
                        help="use Spark Audio's test data in DIR for the volume icon (tests)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.fake or '')
    code = settings(args)
    if code is not None:
        return code
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        print(f"{APP_NAME} needs a graphical session (no DISPLAY or WAYLAND_DISPLAY).",
              file=sys.stderr)
        return 1
    try:
        from .app import run
    except (ImportError, ValueError) as exc:
        print(f"{APP_NAME} needs GTK 3 with PyGObject: {exc}", file=sys.stderr)
        return 1
    return run(args.fake or '')
