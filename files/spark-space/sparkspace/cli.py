"""The command line. --version and --self-test never load a window and never touch your files
(the self-test scans a temporary folder it makes and removes)."""

import argparse
import os
import sys
import tempfile
import time
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    from . import drives, safety, scan, text, treemap
    from .core import human_size
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
    missing = [k for k in text.EN if k not in text.FR]
    print(f"text:      {len(text.EN)} strings, French {'complete' if not missing else 'missing ' + ', '.join(missing)}")
    if missing:
        failures.append("text")

    # a scan of a small folder made for the test: sizes add up, a hard link counts once
    with tempfile.TemporaryDirectory(prefix='spark-space-selftest-') as tmp:
        os.makedirs(os.path.join(tmp, 'a', 'b'))
        with open(os.path.join(tmp, 'a', 'b', 'big.bin'), 'wb') as f:
            f.write(b'\1' * 200_000)
        with open(os.path.join(tmp, 'small.txt'), 'wb') as f:
            f.write(b'x' * 10)
        try:
            os.link(os.path.join(tmp, 'a', 'b', 'big.bin'), os.path.join(tmp, 'twin.bin'))
        except OSError:
            pass
        started = time.monotonic()
        s = scan.scan(tmp, threads=2)
        took = time.monotonic() - started
        files, dirs, _ = s.progress()
        ok = s.root is not None and files >= 2 and dirs >= 2 and \
            200_000 <= s.root.size < 400_000
        print(f"scan:      {files} files, {dirs} folders, {human_size(s.root.size)} in "
              f"{took * 1000:.0f} ms{'' if ok else '  (WRONG)'}")
        if not ok:
            failures.append("scan")
        refused = safety.trash_refusal('/var/mnt/d/anything')
        print(f"safety:    D: drive refused ({refused})" if refused == 'd_drive'
              else f"safety:    D: drive NOT refused ({refused})")
        if refused != 'd_drive':
            failures.append("safety")

    rects = treemap.squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 600, 400)
    area = sum(w * h for _x, _y, w, h in rects)
    ok = abs(area - 600 * 400) < 1
    print(f"treemap:   {len(rects)} blocks{'' if ok else '  (WRONG AREA)'}")
    if not ok:
        failures.append("treemap")
    try:
        found = drives.list_drives()
        print(f"drives:    {len(found)} found: " + ", ".join(
            (d.letter + ':' if d.letter else d.path) for d in found))
    except OSError as exc:
        print(f"drives:    couldn't read the mount table ({exc})")
        failures.append("drives")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: see what takes "
                                     "the space on your drives.")
    parser.add_argument('path', nargs='?', help="scan this folder right away")
    parser.add_argument('--threads', type=int, default=4, help="scan threads (default 4)")
    parser.add_argument('--self-test', action='store_true',
                        help="check the install with a tiny scan of a temporary folder; "
                             "needs no display")
    parser.add_argument('--bench', metavar='PATH',
                        help="open the window, scan PATH, print the times and quit")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App, bench
    try:
        if args.bench:
            return bench(args.bench, threads=args.threads,
                         started=time.monotonic() - started)
        app = App(start=args.path, threads=args.threads)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
