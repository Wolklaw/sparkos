"""The command line. Double-clicking a file runs `spark-run FILE` (the chooser window); a menu
entry runs `spark-run --open SLUG`, which loads no Tk unless something goes wrong. Everything
else here is for scripts, tests and CI, and needs no display."""

import argparse
import json
import os
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, GUIDE_URL, VERSION, apps, sources
from . import wine as winemod
from .core import data_dir, log, setup_logging, size
from .errors import Problem
from .text import EN, t


def has_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def say_problem(problem: Problem, name: str, log_path: str = '', window: bool = True,
                install: bool = False) -> None:
    """A problem, in a window when there's a desktop, else on stderr."""
    message = t(problem.key, **problem.values)
    log.warning("%s: %s (%s)", name, problem.key, problem.values)
    if window and has_display():
        try:
            from .ui import show_error
            show_error(name, problem, log_path, install=install)
            return
        except Exception as exc:          # noqa: BLE001 - fall back to stderr
            log.warning("could not show the error window: %s", exc)
    print(f"{APP_SLUG}: {message}", file=sys.stderr)
    if log_path:
        print(f"{APP_SLUG}: details: {log_path}", file=sys.stderr)
    print(f"{APP_SLUG}: what runs on SparkOS: {GUIDE_URL}", file=sys.stderr)


def _printer(quiet: bool):
    last = {'key': None, 'pct': -1}

    def report(stage: str, **kw) -> None:
        if quiet:
            return
        if stage.startswith('progress.'):
            done, total = kw.get('done', 0), kw.get('total', 0) or 1
            pct = int(done * 100 / total)
            if stage != last['key'] or pct >= last['pct'] + 10 or done == total:
                last['key'], last['pct'] = stage, pct
                print(f"{stage[9:]}: {pct}%", flush=True)
            return
        key = 'step.' + stage
        print(t(key, **kw) if key in EN else stage, flush=True)

    return report


def self_test() -> int:
    """What Spark Run needs, and what it found. No display or network needed."""
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
        import PIL
        print(f"pillow:    {PIL.__version__} (program icons as PNG)")
    except ImportError:
        print("pillow:    not found (program icons stay .ico files)")
    for item in sources.ALL:
        print(f"pinned:    {item.name}, {size(item.size)}, sha256 {item.sha256[:16]}..., "
              f"from {item.url.split('/')[2]}")
    found = winemod.installed()
    if found is None:
        print("wine:      not downloaded yet (first use downloads "
              f"{size(sum(d.size for d in winemod.needs_download()))})")
    else:
        mono = "with Wine Mono" if found.has_mono else "without Wine Mono"
        print(f"wine:      {found.version} at {found.root}, {mono}")
        import subprocess
        try:
            out = subprocess.run([found.wine, '--version'], capture_output=True, text=True,
                                 timeout=30).stdout.strip()
            print(f"wine says: {out or '(nothing)'}")
            if not out.startswith('wine-'):
                failures.append("wine --version")
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"wine says: FAILED ({exc})")
            failures.append("wine --version")
    missing = winemod.missing_libs()
    for soname, what, needed in missing:
        print(f"library:   {soname} MISSING ({what}){'' if needed else ', optional'}")
        if needed:
            failures.append(soname)
    if not missing:
        print(f"libraries: all {len(winemod.HOST_LIBS)} that Wine loads were found")
    folder = data_dir()
    probe = folder
    while not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    writable = os.access(probe, os.W_OK)
    print(f"folder:    {folder} ({'writable' if writable else 'NOT WRITABLE'})")
    if not writable:
        failures.append("data folder")
    installed = apps.all_apps()
    print(f"apps:      {len(installed)} installed")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: Windows programs on SparkOS, on Wine.",
        epilog="With a file and no option: the window that asks Run once or Install as an "
               "app. With nothing: the list of installed Windows apps.")
    parser.add_argument('file', nargs='?', help=".exe or .msi file")
    parser.add_argument('extra', nargs='*', help=argparse.SUPPRESS)
    do = parser.add_mutually_exclusive_group()
    do.add_argument('--run-once', action='store_true', help="run FILE in the run-once folder")
    do.add_argument('--install', action='store_true', help="install FILE as an app")
    do.add_argument('--open', metavar='APP', help="open an installed app (extra arguments: "
                                                  "files to open with it)")
    do.add_argument('--folder', metavar='APP', help="open an app's C: folder")
    do.add_argument('--in', dest='run_in', metavar='APP',
                    help="run FILE (for example a runtime installer) inside an app's folder")
    do.add_argument('--list', action='store_true', help="list installed apps")
    do.add_argument('--uninstall', metavar='APP', help="remove an app and its folder")
    do.add_argument('--set', metavar='APP', help="change an app's options (with --windows, "
                                                 "--dxvk, --name)")
    do.add_argument('--setup', action='store_true', help="download Wine now")
    do.add_argument('--self-test', action='store_true',
                    help="report what Spark Run needs and found; no display needed")
    parser.add_argument('--name', help="with --install or --set: the name in the menu")
    parser.add_argument('--portable', action='store_true',
                        help="with --install: FILE is the program itself; copy it in")
    parser.add_argument('--installer', action='store_true',
                        help="with --install: FILE is an installer; run it")
    parser.add_argument('--silent', action='store_true',
                        help="with --install: ask the installer to skip its wizard (.msi, "
                             "NSIS, Inno Setup, WiX, Squirrel, InstallShield)")
    parser.add_argument('--windows', choices=winemod.WINDOWS_VERSIONS,
                        help="with --set: the Windows version the app sees")
    parser.add_argument('--dxvk', choices=('on', 'off'), help="with --set: DXVK on or off")
    parser.add_argument('--wait', action='store_true',
                        help="wait until the program closes; exit with its exit code")
    parser.add_argument('--json', action='store_true', help="with --list: JSON")
    parser.add_argument('--no-window', action='store_true',
                        help="never open a window; say problems on stderr")
    parser.add_argument('--quiet', action='store_true', help="print only problems")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    setup_logging()
    window = not args.no_window
    report = _printer(args.quiet)

    if args.list:
        found = apps.all_apps()
        if args.json:
            print(json.dumps([dict(slug=a.slug, **a.to_json()) for a in found], indent=2,
                             ensure_ascii=False))
        else:
            for a in found:
                print(f"{a.slug}\t{a.name}\t{a.program}")
        return 0

    if args.setup:
        try:
            wine = apps.ensure_wine(report)
        except apps.RunError as exc:
            say_problem(exc.problem, "Wine", window=False)
            return 1
        print(f"Wine {wine.version} ready at {wine.root}"
              f"{' with Wine Mono' if wine.has_mono else ''}")
        return 0

    slug = args.open or args.folder or args.uninstall or args.set or args.run_in
    app = None
    if slug:
        app = apps.load(slug)
        if app is None:
            print(f"{APP_SLUG}: no installed app called {slug!r} (see --list)", file=sys.stderr)
            return 2

    try:
        if args.folder:
            return 0 if apps.open_folder(app.drive_c) else 1

        if args.uninstall:
            apps.uninstall(app)
            if not args.quiet:
                print(t('rm.done', name=app.name))
            return 0

        if args.set:
            if args.name:
                apps.rename(app, args.name)
            if args.windows:
                apps.set_windows(app, args.windows)
            if args.dxvk:
                apps.set_dxvk(app, args.dxvk == 'on', report)
            print(json.dumps(dict(slug=app.slug, **app.to_json()), indent=2,
                             ensure_ascii=False))
            return 0

        if args.open:
            launch = apps.open_app(app, [args.file] + args.extra if args.file else [], report)
            return _follow(launch, app.name, args.wait, window)

        if args.run_in:
            if not args.file:
                parser.error("--in needs a FILE")
            apps.check_file(args.file)
            wine = apps.ensure_wine(report)
            proc = wine.start(app.prefix, os.path.abspath(args.file), args.extra,
                              log_path=winemod.app_log(app.slug))
            launch = apps.Launch(proc, winemod.app_log(app.slug), wine.has_mono,
                                 os.path.basename(args.file))
            return _follow(launch, os.path.basename(args.file), args.wait, window)

        if args.run_once:
            if not args.file:
                parser.error("--run-once needs a FILE")
            launch = apps.run_once(args.file, args.extra, report)
            return _follow(launch, os.path.basename(args.file), args.wait, window)

        if args.install:
            if not args.file:
                parser.error("--install needs a FILE")
            mode = 'portable' if args.portable else 'installer' if args.installer else 'auto'
            app = apps.install(args.file, report, name=args.name, mode=mode,
                               silent=args.silent)
            print(t('done.installed', name=app.name))
            print(json.dumps(dict(slug=app.slug, **app.to_json()), indent=2,
                             ensure_ascii=False))
            return 0
    except apps.RunError as exc:
        name = (app.name if app else os.path.basename(args.file or '')) or APP_NAME
        log_path = winemod.app_log(app.slug) if app else ''
        say_problem(exc.problem, name, log_path, window, install=args.install)
        return 1
    except KeyboardInterrupt:
        return 130

    # windows
    if not has_display():
        print(f"{APP_SLUG}: {t('error.no_display')}", file=sys.stderr)
        return 1
    try:
        from .ui import run_window
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    return run_window(args.file)


def _follow(launch: 'apps.Launch', name: str, wait: bool, window: bool) -> int:
    """Watch the start; explain an early failure. With --wait, until the program closes."""
    problem = launch.watch()
    if problem:
        say_problem(problem, name, launch.log_path, window)
        return 1
    if not wait:
        if launch.proc.poll() is None and window and has_display():
            # stay (lightly) to explain a crash later; Tk is only loaded if one happens
            code = launch.wait()
            problem = launch.problem(quick=False)
            if problem and code != 0:
                say_problem(problem, name, launch.log_path, window)
        return 0
    code = launch.wait()
    problem = launch.problem(quick=False)
    if problem and code != 0:
        say_problem(problem, name, launch.log_path, window)
    return code
