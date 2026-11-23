"""The command line. --version, --self-test and --apply-rgb never load Tk."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    from . import config, liquid, sysinfo
    from .fwupd import Fwupd
    from .hwmon import Hwmon
    from .text import EN, FR

    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors="replace")      # a C locale can't print "°C"
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    hwmon = Hwmon(os.environ.get("SPARK_CONTROLLER_HWMON") or "/sys/class/hwmon")
    fans = hwmon.fans()
    print(f"hwmon:     {len(hwmon.chips())} chips, {len(fans)} fans, "
          f"{sum(1 for f in fans if f.controllable)} with power control, "
          f"temps {hwmon.source_temps()}")
    version = liquid.library_version()
    print(f"liquidctl: {version or 'not installed'}")
    print(f"openrgb:   {shutil.which('openrgb') or 'not installed'}")
    print(f"fwupd:     {Fwupd().path or 'not installed'}")
    print(f"bios:      {sysinfo.bios()}")
    try:
        config.load(config.config_path())
        print(f"config:    {config.config_path()} ok")
    except config.ConfigError as exc:
        print(f"config:    {config.config_path()} BROKEN: {exc}")
        failures.append("config")
    if set(EN) != set(FR):
        print("text:      English and French tables differ")
        failures.append("text")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def apply_rgb(use_usb: bool = True) -> int:
    """What runs at login: apply the saved lighting. Quiet when there is nothing saved."""
    from . import rgb
    from .liquid import LiquidHub
    from .log import setup_logging
    from .text import t

    setup_logging(to_file=True)
    saved = rgb.load_saved()
    if not saved:
        print(t("cli.rgb_none"))
        return 0
    manager = rgb.RgbManager(LiquidHub() if use_usb else None)
    results = rgb.apply_saved(manager, saved)
    for key, error in results.items():
        if error:
            print(f"{key}: {error}", file=sys.stderr)
    print(t("cli.rgb_applied", n=sum(1 for e in results.values() if not e)))
    return 1 if any(results.values()) else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: fans, lighting and "
                                     "firmware for this PC.")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-test", action="store_true", help="check what this PC offers")
    parser.add_argument("--apply-rgb", action="store_true",
                        help="apply the saved lighting and exit (runs at login)")
    parser.add_argument("--tab", choices=("overview", "fans", "rgb", "drivers"))
    parser.add_argument("--no-usb", action="store_true", help="don't scan USB controllers")
    args = parser.parse_args(argv)
    if args.version:
        print(f"{APP_SLUG} {VERSION}")
        return 0
    if args.self_test:
        return self_test()
    if args.apply_rgb:
        return apply_rgb(not args.no_usb)

    from .log import setup_logging
    setup_logging(to_file=True)
    from .app import App
    App(tab=args.tab, use_usb=not args.no_usb).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
