"""The command line. --version and --self-test never load Tk."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION

HELPER = "/usr/libexec/spark-firewall-helper"


def self_test() -> int:
    from . import catalog, ops
    from .fw import Firewall
    from .text import EN, FR

    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    # Reads only: firewall-cmd queries and nmcli. A stopped firewalld, or none at all, is not a
    # failure: it is what the window shows.
    snap = Firewall().snapshot()
    if not snap.available:
        print("firewalld: firewall-cmd not found (the window says so)")
    elif not snap.running:
        print("firewalld: installed, not running")
    else:
        zone = snap.zone.get(snap.default_zone)
        print(f"firewalld: running, default zone {snap.default_zone}, {len(snap.zones)} zones, "
              f"{len(snap.services)} services")
        if zone is None:
            print("zone:      the default zone could not be read")
            failures.append("zone")
        else:
            print(f"zone:      {zone.name}: {len(zone.services)} services, "
                  f"{len(zone.ports)} ports")
        print(f"rules:     {len(catalog.available(snap.services))} of {len(catalog.RULES)} shown")
    nets = ", ".join(f"{n.device}={n.zone or '?'}" for n in snap.networks) or "none"
    print(f"networks:  {nets}")
    print(f"nmcli:     {shutil.which('nmcli') or 'not installed'}")
    print(f"helper:    {HELPER if os.path.exists(HELPER) else 'not installed here (a checkout)'}")
    try:
        ops.validate([{"op": "service", "zone": "public", "name": "ssh", "add": True}])
        refused = 0
        for bad in ({"op": "service", "zone": "--x", "name": "ssh", "add": True},
                    {"op": "port", "zone": "public", "port": "0/tcp", "add": True},
                    {"op": "shell", "cmd": "id"}):
            try:
                ops.validate([bad])
            except ops.OpError:
                refused += 1
        print(f"ops:       checks pass, {refused} of 3 bad operations refused")
        if refused != 3:
            failures.append("ops")
    except ops.OpError as exc:
        print(f"ops:       BROKEN ({exc})")
        failures.append("ops")
    if set(EN) != set(FR):
        print("text:      English and French tables differ")
        failures.append("text")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the firewall, in "
                                     "plain words.")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-test", action="store_true", help="read the firewall and check")
    parser.add_argument("--tab", choices=("overview", "rules", "ports"))
    args = parser.parse_args(argv)
    if args.version:
        print(f"{APP_SLUG} {VERSION}")
        return 0
    if args.self_test:
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        return self_test()

    from .log import setup_logging
    setup_logging(to_file=True)
    from .app import App
    App(tab=args.tab).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
