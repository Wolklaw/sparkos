"""The command line. --version, --self-test and --list never load Tk.

  spark-archive [ARCHIVE]                  the window (with that archive open)
  spark-archive --extract-here A [A...]    Dolphin: extract next to each archive
  spark-archive --extract-folder A [A...]  Dolphin: extract into a folder named after it
  spark-archive --compress zip F [F...]    Dolphin: make F.zip next to the files
  spark-archive --compress tar.zst F...    Dolphin: make F.tar.zst
  spark-archive --list ARCHIVE             print what's inside, no window
  spark-archive --self-test                check what it needs, with a round trip, no window
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION
from . import core, formats
from . import libarchive as la


def _print_listing(path: str, password: Optional[str]) -> int:
    from .jobs import ListJob
    job = ListJob(path, asker=lambda q, i: password if q == 'password' else None)
    res = job.run_here()
    if not res.ok or not job.listing:
        from .text import t
        print(t('error.' + (res.error or 'bug'), detail=res.detail), file=sys.stderr)
        return 1
    listing = job.listing
    print(f"{os.path.basename(path)}: {formats.describe(listing.kind)}, read with "
          f"{listing.backend}, {listing.file_count} files, {core.size(listing.total_size)}"
          + (", password-protected" if listing.encrypted else ""))
    from .safety import is_root
    for e in listing.entries:
        if e.kind == 'dir' and is_root(e.name):
            continue
        mark = '*' if e.encrypted else ' '
        shown = e.name + ('/' if e.kind == 'dir' and not e.name.endswith('/') else '')
        if e.kind in ('link', 'hardlink'):
            shown += f" -> {e.target}"
        if e.parts is None:
            shown += "   (left out: outside the folder)"
        size = '' if e.kind != 'file' else (str(e.size) if e.size >= 0 else '?')
        print(f"{mark}{e.kind:8} {size:>12}  {core.when(e.mtime):16}  {shown}")
    return 0


def self_test() -> int:
    """What it needs, then a real round trip in a temporary folder. No display needed."""
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:     {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:    Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:    MISSING ({exc})")
        failures.append("tkinter")
    zstd_info = 'no Python zstd'
    if formats.has_zstd():
        from compression import zstd
        zstd_info = 'Python, libzstd ' + '.'.join(map(str, zstd.zstd_version_info))
    command = shutil.which('zstd')
    print(f"zstd:       {zstd_info}" + (f", command {command}" if command else ''))
    lav = la.version()
    print(f"libarchive: {lav or 'MISSING (7z, rar and iso need it)'}")
    if not lav:
        failures.append("libarchive")
    from .readers import sevenzip, what_reads
    seven = sevenzip()
    print(f"7z command: {seven or 'not installed (only needed for password-protected 7z)'}")
    for kind in ('zip', 'tar.gz', 'tar.bz2', 'tar.xz', 'tar.zst', '7z', 'rar', 'iso'):
        readers = what_reads(kind)
        print(f"reads:      {kind:8} with {' then '.join(readers) or 'NOTHING'}")
        if not readers:
            failures.append(f"read {kind}")
    if os.name != 'posix':
        print("safe write: needs Linux")
        failures.append("linux")
    else:
        failures += _round_trip(seven)
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _round_trip(seven: Optional[str]) -> List[str]:
    from .jobs import TAR_ZST, ZIP, CompressJob, ExtractJob
    failures = []
    with tempfile.TemporaryDirectory(prefix='spark-archive-selftest-') as tmp:
        src = os.path.join(tmp, 'photos')
        os.makedirs(os.path.join(src, 'trip'))
        payload = os.urandom(200_000) + b'spark' * 10_000
        with open(os.path.join(src, 'trip', 'a.bin'), 'wb') as f:
            f.write(payload)
        with open(os.path.join(src, 'notes.txt'), 'w', encoding='utf-8') as f:
            f.write('été\n')
        os.symlink('trip/a.bin', os.path.join(src, 'link'))
        for fmt in (ZIP, TAR_ZST):
            started = time.monotonic()
            res = CompressJob([src], fmt).run_here()
            if not res.ok:
                print(f"round trip: compress {fmt} FAILED: {res.error} {res.detail}")
                failures.append(f"compress {fmt}")
                continue
            out = os.path.join(tmp, 'out-' + fmt)
            os.mkdir(out)
            got = ExtractJob(res.output, out, new_folder=True).run_here()
            ok = got.ok and _same(os.path.join(out, 'photos'), payload)
            print(f"round trip: {fmt:8} {'ok' if ok else 'FAILED ' + _why(got, out)} "
                  f"({(time.monotonic() - started) * 1000:.0f} ms)")
            if not ok:
                failures.append(f"round trip {fmt}")
            if fmt == TAR_ZST and la.load():
                from .readers import LibarchiveReader
                names = sorted(e.path for e in LibarchiveReader(res.output, 'tar.zst').list())
                ok = 'photos/trip/a.bin' in names
                print(f"libarchive: reads tar.zst {'ok' if ok else 'FAILED'}")
                if not ok:
                    failures.append("libarchive read")
            os.unlink(res.output)
        if seven:
            seven_path = os.path.join(tmp, 'photos.7z')
            proc = subprocess.run([seven, 'a', '-bd', '-y', '-snl', seven_path, 'photos'],
                                  cwd=tmp, capture_output=True, start_new_session=True)
            if proc.returncode == 0:
                out = os.path.join(tmp, 'out-7z')
                os.mkdir(out)
                got = ExtractJob(seven_path, out, new_folder=True).run_here()
                ok = got.ok and _same(os.path.join(out, 'photos'), payload)
                print(f"round trip: 7z       {'ok' if ok else 'FAILED ' + _why(got, out)} "
                      f"(made by 7z, read by {'libarchive' if la.load() else '7z'})")
                if not ok:
                    failures.append("7z")
            else:
                print(f"round trip: 7z       not tried (7z a failed: "
                      f"{proc.stderr.decode('utf-8', 'replace').strip()[-200:]})")
        # a hostile zip must stay inside its folder
        evil = os.path.join(tmp, 'evil.zip')
        with zipfile.ZipFile(evil, 'w') as zf:
            zf.writestr('../escaped.txt', 'no')
            zf.writestr('/abs.txt', 'inside')
        out = os.path.join(tmp, 'out-evil', 'here')
        os.makedirs(out)
        got = ExtractJob(evil, out).run_here()
        ok = (got.ok and not os.path.exists(os.path.join(tmp, 'out-evil', 'escaped.txt'))
              and os.path.isfile(os.path.join(out, 'abs.txt')) and len(got.problems) == 1)
        print(f"safety:     ../ and /abs in a zip {'contained' if ok else 'NOT CONTAINED'}")
        if not ok:
            failures.append("safety")
    return failures


def _why(res, out: str) -> str:
    found = []
    for top, dirs, files in os.walk(out):
        for name in dirs + files:
            full = os.path.join(top, name)
            found.append(os.path.relpath(full, out) + (' -> ' + os.readlink(full)
                                                       if os.path.islink(full) else ''))
    return (f"[{res.error or ''} {res.detail or ''} problems={res.problems} "
            f"found={sorted(found)}]")


def _same(folder: str, payload: bytes) -> bool:
    try:
        with open(os.path.join(folder, 'trip', 'a.bin'), 'rb') as f:
            if f.read() != payload:
                return False
        with open(os.path.join(folder, 'notes.txt'), encoding='utf-8') as f:
            if f.read() != 'été\n':
                return False
        return os.readlink(os.path.join(folder, 'link')) == 'trip/a.bin'
    except OSError:
        return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: open, extract "
                                     "and make archives.")
    parser.add_argument('paths', nargs='*', help="an archive to open, or the files for an "
                                                 "action below")
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--extract-here', action='store_true',
                        help="extract each archive into the folder it is in")
    action.add_argument('--extract-folder', action='store_true',
                        help="extract each archive into a new folder named after it")
    action.add_argument('--compress', choices=('zip', 'tar.zst'),
                        help="put the files and folders into one archive next to them")
    action.add_argument('--list', action='store_true', help="print what's inside, no window")
    action.add_argument('--self-test', action='store_true',
                        help="check what it needs and do a round trip; no display needed")
    action.add_argument('--bench', type=float, metavar='SECONDS',
                        help="open the window (and the archive), print the time to first "
                             "paint and to the listing, close")
    parser.add_argument('--password-stdin', action='store_true',
                        help="with --list: read the password from the first line of stdin")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.list:
        if len(args.paths) != 1:
            parser.error("--list takes one archive")
        password = sys.stdin.readline().rstrip('\n') if args.password_stdin else None
        return _print_listing(args.paths[0], password)
    if (args.extract_here or args.extract_folder or args.compress) and not args.paths:
        parser.error("give the files to work on")

    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    core.setup_logging()
    try:
        if args.bench is not None:
            from .app import bench
            return bench(args.paths[0] if args.paths else None, args.bench)
        if args.extract_here or args.extract_folder or args.compress:
            from .jobwindow import JobWindow
            action_name = ('extract-here' if args.extract_here else 'extract-folder'
                           if args.extract_folder else f'compress-{args.compress}')
            return JobWindow(action_name, args.paths).run()
        from .app import App
        App(args.paths[0] if args.paths else None).run()
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    return 0

