"""The command line. --version and --self-test never load Tk; `spark-files FOLDER` hands the
folder to the Spark Files already running in this session (over D-Bus) before Tk is loaded."""

import argparse
import os
import sys
import tempfile
import time
from typing import List, Optional

T0 = time.monotonic()

from . import APP_NAME, APP_SLUG, VERSION  # noqa: E402


def process_age() -> float:
    try:
        with open('/proc/self/stat', encoding='ascii') as f:
            stat = f.read()
        with open('/proc/uptime', encoding='ascii') as f:
            up = float(f.read().split()[0])
        start = int(stat[stat.rfind(')') + 2:].split()[19])
        return up - start / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, AttributeError, IndexError):
        return time.monotonic() - T0


def to_uri(arg: str) -> str:
    if '://' in arg or arg.startswith('trash:'):
        return arg
    from .app import path_to_uri
    return path_to_uri(os.path.abspath(os.path.expanduser(arg)))


def self_test() -> int:
    """Check what Spark Files needs, without a display."""
    from . import core, gloop, ops, servicemenus, thumbs, trash
    from .listing import filter_entries, list_dir, sort_entries
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
    for name, folder in (('settings', core.config_dir()), ('state', core.state_dir()),
                         ('cache', core.cache_dir())):
        ok = os.path.isdir(folder) and os.access(folder, os.W_OK)
        print(f"{name + ':':<10} {core.home_short(folder)} ({'writable' if ok else 'NOT writable'})")
        if not ok:
            failures.append(name)
    print("gio:       " + ("PyGObject with GIO: watching folders, D-Bus, default apps"
                            if gloop.available() else
                            "MISSING (python3-gobject): no watching, no D-Bus, opens with xdg-open"))
    if not gloop.available():
        failures.append("gio")
    print("pillow:    " + ("ok: thumbnails and icons" if thumbs.Image is not None else
                            "MISSING (python3-pillow): no thumbnails or file icons"))
    if thumbs.Image is None:
        failures.append("pillow")
    print("video:     " + ("GStreamer: video thumbnails" if thumbs.video_ok() else
                            "no GStreamer playbin: videos keep their icon"))

    # file operations in a temporary folder: copy, move, clash, rename, trash, restore
    bad = []
    saved_data = os.environ.get('XDG_DATA_HOME')
    with tempfile.TemporaryDirectory(prefix='spark-files-test-') as tmp:
        # the trash test uses a Trash inside the temporary folder, never the real one
        os.environ['XDG_DATA_HOME'] = os.path.join(tmp, 'data')
        try:
            src = os.path.join(tmp, 'src')
            os.makedirs(os.path.join(src, 'sub'))
            for i in range(50):
                with open(os.path.join(src, f'file{i}.txt'), 'w', encoding='utf-8') as f:
                    f.write('x' * i)
            with open(os.path.join(src, 'sub', 'deep.bin'), 'wb') as f:
                f.write(os.urandom(300_000))
            dest = os.path.join(tmp, 'dest')
            os.mkdir(dest)
            job = ops.Job('copy', [src], dest).start()
            job.thread.join(30)
            if job.errors or not os.path.isfile(os.path.join(dest, 'src', 'sub', 'deep.bin')):
                bad.append(f"copy: {job.errors}")
            job = ops.Job('copy', [os.path.join(src, 'file1.txt')], dest,
                          ask=lambda j, s, d: j.answer(ops.KEEP_BOTH)).start()
            job.thread.join(10)
            job = ops.Job('copy', [os.path.join(src, 'file1.txt')], dest,
                          ask=lambda j, s, d: j.answer(ops.KEEP_BOTH)).start()
            job.thread.join(10)
            if not os.path.isfile(os.path.join(dest, 'file1 (2).txt')):
                bad.append("keep both")
            entries = list_dir(os.path.join(dest, 'src'))
            names = [e.name for e in sort_entries(entries)]
            if names[:3] != ['sub', 'file0.txt', 'file1.txt'] or names[-1] != 'file49.txt':
                bad.append(f"sort: {names[:4]}")
            if len(filter_entries(entries, 'file4')) != 11:
                bad.append("filter")
            there = os.path.join(tmp, 'there')
            os.mkdir(there)
            moved = ops.Job('move', [os.path.join(dest, 'src')], there).start()
            moved.thread.join(30)
            if not os.path.isfile(os.path.join(there, 'src', 'sub', 'deep.bin')) or \
                    os.path.exists(os.path.join(dest, 'src')):
                bad.append(f"move: {moved.errors}")
            renamed = ops.rename(os.path.join(there, 'src'), 'renamed')
            gone = trash.trash(renamed)
            if os.path.exists(renamed) or not os.path.exists(gone):
                bad.append("trash")
            restore = ops.Job('restore', [gone]).start()
            restore.thread.join(30)
            if not os.path.isdir(renamed):
                bad.append(f"restore: {restore.errors}")
        except Exception as exc:          # noqa: BLE001
            bad.append(f"{type(exc).__name__}: {exc}")
        finally:
            if saved_data is None:
                os.environ.pop('XDG_DATA_HOME', None)
            else:
                os.environ['XDG_DATA_HOME'] = saved_data
    print("files:     " + ("copy, keep both, move, rename, sort, filter, trash and restore ok"
                           if not bad else "FAILED: " + "; ".join(bad)))
    if bad:
        failures.append("files")
    print(f"trash:     {core.home_short(trash.home_trash())} ({trash.count()} items in all trashes)")
    menus = servicemenus.load()
    actions = sum(len(m.actions) for m in menus)
    print(f"menus:     {actions} right-click actions from {len(menus)} service menus")
    from .app import terminal_command
    term = terminal_command(core.home())
    print(f"terminal:  {' '.join(term) if term else 'none found'}")
    if gloop.available():
        app = gloop.default_app('inode/directory')
        print(f"folders:   open with {app.id if app else 'nothing set'}")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS file manager.",
        epilog="A file instead of a folder opens its folder with the file selected.")
    parser.add_argument('paths', nargs='*', metavar='PATH', help="folders (or files) to show")
    parser.add_argument('--select', action='store_true',
                        help="show the paths selected in their folders")
    parser.add_argument('--tab', action='store_true',
                        help="open in a new tab of the open window instead of a new window")
    parser.add_argument('--new-process', action='store_true',
                        help="don't hand over to the Spark Files already running")
    parser.add_argument('--service', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--self-test', action='store_true',
                        help="check what Spark Files needs; no display needed")
    parser.add_argument('--bench', nargs='?', const='', metavar='FOLDER',
                        help="open FOLDER, report how long it took, then quit")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    uris = [to_uri(p) for p in args.paths]
    mode = 'show-items' if args.select else ('tab' if args.tab else 'open')
    if args.bench is None and not args.new_process and not args.service:
        from . import gloop
        if gloop.hand_over(uris, mode):
            return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App, bench
    try:
        if args.bench is not None:
            return bench(os.path.abspath(args.bench) if args.bench else None, process_age)
        app = App(service=args.service)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    if not args.service or uris:
        app.on_request(mode, uris)
    app.run()
    return 0
