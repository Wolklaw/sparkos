"""The command line. --version, --self-test and --update-spark-apps never load Tk. Opening the Store when it is
already open (or opening a .flatpakref or an appstream:// link) hands over to the open
window before Tk is even imported."""

import argparse
import os
import sys
import time
from typing import List, Optional

T0 = time.monotonic()

from . import APP_NAME, APP_SLUG, VERSION  # noqa: E402


def process_age() -> Optional[float]:
    """Seconds since this process started (Python's own start-up included), from /proc."""
    try:
        with open('/proc/self/stat', encoding='ascii') as f:
            stat = f.read()
        with open('/proc/uptime', encoding='ascii') as f:
            up = f.read()
        start = int(stat[stat.rfind(')') + 2:].split()[19])
        return float(up.split()[0]) - start / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, AttributeError, IndexError):
        return None


def self_test() -> int:
    """Check what the Store needs, read the catalog and the Spark apps, and say what was
    found. No display needed."""
    from . import flatpak, sparkapps
    from .appstream import find_sources
    from .catalog import Catalog
    from .core import cache_dir
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
    try:
        import sqlite3
        print(f"sqlite3:   {sqlite3.sqlite_version}")
    except ImportError as exc:
        print(f"sqlite3:   MISSING ({exc})")
        failures.append("sqlite3")
    try:
        from PIL import ImageTk
        import PIL
        print(f"pillow:    {PIL.__version__} (sharp icons and JPEG screenshots)"
              if ImageTk else "pillow:    no")
    except ImportError:
        print("pillow:    no (icons are scaled by Tk; JPEG screenshots won't show)")

    if flatpak.available():
        print(f"flatpak:   {flatpak.version() or 'found'}")
        remotes = flatpak.remotes()
        for scope in ('user', 'system'):
            names = remotes.get(scope) or []
            print(f"remotes:   {scope}: {', '.join(names) if names else 'none'}")
    else:
        print("flatpak:   not installed (only the Spark apps can be shown)")

    sources = find_sources()
    if not sources:
        print("catalog:   not on this PC yet. SparkOS downloads it at first boot "
              "(flatpak update --appstream); the Store offers to get it too.")
        if os.environ.get('SPARK_STORE_REQUIRE_CATALOG') == '1':
            failures.append("catalog")
    for src in sources:
        age_h = (time.time() - src.mtime) / 3600
        print(f"catalog:   {src.path} ({src.scope}, {src.size // 1024} KB, {age_h:.1f} h old)")
    if sources:
        cat = Catalog(sources).load()
        if cat.error:
            print(f"catalog:   UNREADABLE: {cat.error}")
            failures.append("catalog")
        else:
            apps = list(cat.apps.values())
            with_icons = sum(1 for a in apps if cat.icon_path(a))
            print(f"catalog:   {len(apps)} apps indexed in {cat.load_seconds:.2f} s "
                  f"({'read the XML' if cat.rebuilt else 'from the cache'}): "
                  f"{sum(a.verified for a in apps)} verified, "
                  f"{sum(a.proprietary for a in apps)} proprietary, {with_icons} with icons")
            again = Catalog(sources).load()
            print(f"catalog:   opened again from the cache in {again.load_seconds:.3f} s")
            started = time.perf_counter()
            hits, total = cat.search('music player')
            took = (time.perf_counter() - started) * 1000
            print(f"search:    'music player': {total} apps in {took:.1f} ms"
                  + (f", first: {hits[0].name}" if hits else ""))
            if not apps:
                failures.append("catalog empty")

    spark = sparkapps.discover()
    if not spark:
        failures.append("spark apps")
        print("spark:     NO Spark apps found (looked in: " +
              ", ".join(sparkapps.search_dirs()) + ")")
    for app in spark:
        where = {'system': 'in SparkOS', 'user': 'installed for you'}.get(app.installed or '',
                                                                          'not installed')
        extra = ", can install from " + app.source if app.source and not app.installed else ""
        if app.outdated:
            extra = ", outdated: " + app.source + " is newer"
        version = f" {app.version}" if app.version else ""
        print(f"spark:     {app.name}{version} ({where}{extra})")
    try:
        probe = os.path.join(cache_dir(), '.write-test')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        os.unlink(probe)
        print(f"cache:     {cache_dir()}")
    except OSError as exc:
        if os.path.isdir(os.path.expanduser('~')):
            print(f"cache:     NOT WRITABLE ({exc})")
            failures.append("cache")
        else:            # an image build: root's home is on /var, which is empty there
            print(f"cache:     none here: {os.path.expanduser('~')} doesn't exist "
                  "(fine while building an image)")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def update_spark_apps() -> int:
    """Reinstall the Spark apps installed for you whose source in the image has changed (a
    system update brought a newer one). Quiet when there is nothing to do."""
    from . import sparkapps
    apps = [a for a in sparkapps.discover() if a.outdated]
    failed = 0
    for app, err in sparkapps.update_outdated(apps):
        version = f" {app.version}" if app.version else ""
        if err:
            failed += 1
            print(f"{app.name}: couldn't update from {app.source}: {err}", file=sys.stderr)
        else:
            print(f"{app.name}{version}: updated from {app.source}")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS "
                                     "app store (Spark apps and Flathub).")
    parser.add_argument('target', nargs='?', help="an app ID, an appstream:// link or a "
                                                  ".flatpakref file to open on its page")
    parser.add_argument('--page', choices=('home', 'installed', 'updates', 'queue'),
                        help="open on this page")
    parser.add_argument('--self-test', action='store_true',
                        help="check what it needs and read the catalog; no display needed")
    parser.add_argument('--update-spark-apps', action='store_true',
                        help="reinstall the Spark apps installed for you whose copy in "
                             "SparkOS is newer; no display needed")
    parser.add_argument('--bench', type=float, metavar='SECONDS',
                        help="open, measure time to first paint and idle CPU, then close")
    parser.add_argument('--offline', action='store_true',
                        help="don't check for updates or a newer catalog")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.update_spark_apps:
        return update_spark_apps()
    target = args.target or ''
    if target and not target.startswith(('appstream:', 'https:', 'file:')) and \
            os.path.exists(target):
        target = os.path.abspath(target)
    if not args.bench:
        from .instance import ask_running_to_show
        if ask_running_to_show(target):
            return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from .core import setup_logging
    setup_logging()
    try:
        if args.bench:
            from .app import bench
            return bench(args.bench)
        from .app import Store
        store = Store(target=target or None, page=args.page, offline=args.offline)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    store.run()
    return 0
