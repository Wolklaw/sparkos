"""The command line. --version and --self-test never load Tk and never connect to anything."""

import argparse
import os
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test(config_path: Optional[str] = None) -> int:
    """Checks ssh is on the path, the machine list parses and the probe is present. Connects
    to nothing."""
    from . import config, core
    from .probe import PROBE_FILE
    from .transport import ssh_path
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')
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
    if config.tomllib is None:
        print("tomllib:   MISSING (needs Python 3.11 or newer to read machines.toml)")
        failures.append("tomllib")
    ssh = ssh_path()
    print(f"ssh:       {ssh or 'NOT FOUND on the path'}")
    if not ssh:
        failures.append("ssh")
    if os.path.isfile(PROBE_FILE):
        with open(PROBE_FILE, encoding='utf-8') as f:
            size = len(f.read())
        print(f"probe:     {PROBE_FILE} ({size} bytes)")
    else:
        print(f"probe:     MISSING at {PROBE_FILE}")
        failures.append("probe")
    path = config_path or core.config_path()
    try:
        cfg = config.load(path)
        if cfg.found:
            print(f"config:    {path}: {len(cfg.machines)} machines, {len(cfg.sites)} websites")
        else:
            print(f"config:    {path} doesn't exist yet (no machines; not an error)")
    except config.ConfigError as exc:
        print(f"config:    ERROR in {path}: {exc}")
        failures.append("config")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: see and fix "
                                     "your home servers over SSH.")
    parser.add_argument('--config', metavar='FILE',
                        help="read this machine list instead of the usual machines.toml")
    parser.add_argument('--self-test', action='store_true',
                        help="check ssh, the machine list and the probe; connects to nothing")
    parser.add_argument('--status', action='store_true',
                        help="check every machine and website once and print the result as "
                        "JSON (what a status widget would show); no window")
    parser.add_argument('--json', action='store_true',
                        help="with --status: the short form Spark Shell's tray reads "
                        "(summary ok|warn|down|empty; exit 2 when there is nothing to check)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.config)
    if args.status:
        from . import status
        if args.json:
            return status.json_main(args.config)
        return status.main(args.config)   # no log: the widget runs it every minute
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    from .app import App
    core.setup_logging()
    try:
        app = App(config_path=args.config)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
