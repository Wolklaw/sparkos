"""The command line. --version and --self-test never open a window and never change anything;
--watch is the background watcher the systemd user service runs."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    """Reports what Spark Bench can use on this PC. Only a missing tkinter or module fails it:
    MangoHud, Flatpak and the sound players are optional and the window says what is missing."""
    from . import mangohud, watch
    from .text import t
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"{'python:':<13}{sys.version.split()[0]}")
    try:
        import tkinter
        print(f"{'tkinter:':<13}Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"{'tkinter:':<13}{t('cli.missing')} ({exc})")
        failures.append('tkinter')
    for name in ('mangohud', 'flatpak', 'notify-send'):
        print(f"{name + ':':<13}{shutil.which(name) or t('cli.missing')}")
    players = [p for p in ('pw-play', 'paplay', 'canberra-gtk-play') if shutil.which(p)]
    print(f"{'sound:':<13}{', '.join(players) or t('cli.missing')}")
    for kind, name in watch.SOUND_FOR.items():
        path = os.path.join(watch.SOUNDS, name)
        print(f"{'  ' + kind + ':':<13}{path if os.path.exists(path) else t('cli.missing')}")
    print(f"{'configs:':<13}{mangohud.steam_config()}")
    print(f"{'':<13}{mangohud.host_config()}")
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ('app.py', 'views.py', 'text.py', 'frames.py', 'library.py', 'mangohud.py',
                 'watch.py', 'widgets.py', 'dialogs.py', 'core.py', 'lang.py'):
        if not os.path.isfile(os.path.join(here, name)):
            print(f"{'module:':<13}{name} {t('cli.missing')}")
            failures.append(name)
    try:
        from . import frames
        if frames.low([10.0, 20.0, 30.0, 40.0], 0.25) != 25.0:
            raise ValueError("frames.low gives the wrong answer")
    except Exception as exc:                 # noqa: BLE001 - reported
        print(f"{'modules:':<13}{exc}")
        failures.append('modules')
    if failures:
        print(t('cli.test_failed') + " " + ", ".join(failures))
        return 1
    print(t('cli.test_ok'))
    return 0


def watch_folders():
    """The folders the background watcher lists (every folder MangoHud's configs name), and
    the settings."""
    from . import core, mangohud
    settings = core.load_settings()
    return mangohud.inspect(settings).output_folders, settings


def main(argv: Optional[List[str]] = None) -> int:
    from .text import t
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=t('cli.help'))
    parser.add_argument('--tab', choices=('setup', 'recordings', 'compare'),
                        default='recordings', help=t('cli.help_tab'))
    parser.add_argument('--watch', action='store_true', help=t('cli.help_watch'))
    parser.add_argument('--self-test', action='store_true', help=t('cli.help_self_test'))
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    from . import core
    core.setup_logging()
    if args.watch:
        from . import watch
        folders, settings = watch_folders()
        print(t('cli.watching', folders=', '.join(folders)), flush=True)
        return watch.run_watch(folders, int(settings.get('duration') or 90),
                               bool(settings.get('sound', True)))
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from .app import App
    try:
        app = App(tab=args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
