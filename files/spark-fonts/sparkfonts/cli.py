"""The command line. --version and --self-test never load a window and never touch your fonts
(the self-test works in a temporary folder it makes and removes). --install needs no window."""

import argparse
import os
import shutil
import struct
import sys
import tempfile
import zipfile
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
    from . import core, fcdata, fontfile, preview, store, text, winfonts
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
    print(f"text:      {len(text.EN)} strings, French "
          f"{'complete' if not missing else 'missing ' + ', '.join(missing)}")
    if missing:
        failures.append("text")
    if preview.available():
        import PIL
        print(f"pillow:    {PIL.__version__}")
    else:
        print("pillow:    MISSING (previews need python3-pillow)")
        failures.append("pillow")
    code, _out, err = core.run(['fc-list', '--version'], timeout=10)
    print(f"fontconfig: {'found' if code == 0 else 'MISSING ' + err.strip()}")
    if code != 0:
        failures.append("fontconfig")
    faces = fcdata.list_faces()
    families = fcdata.group(faces)
    print(f"fonts:     {len(faces)} styles in {len(families)} families")
    if code == 0 and not faces:
        failures.append("fonts")

    # the pure parts, on bytes made here: a parsed name table, a hostile zip, a refused file
    names = fontfile.parse_names(_name_table({1: "Test Family", 2: "Bold", 13: "Free to use"}))
    ok = names.get(1) == "Test Family" and names.get(13) == "Free to use"
    print(f"name table: {'read' if ok else 'WRONG'}")
    if not ok:
        failures.append("names")
    with tempfile.TemporaryDirectory(prefix='spark-fonts-selftest-') as tmp:
        bad = os.path.join(tmp, 'hostile.zip')
        with zipfile.ZipFile(bad, 'w') as z:
            z.writestr('../escape.ttf', b'\x00\x01\x00\x00' + b'x' * 20)
            z.writestr('/abs.ttf', b'\x00\x01\x00\x00' + b'x' * 20)
            z.writestr('notes.txt', b'hello')
        out = os.path.join(tmp, 'out')
        os.makedirs(out)
        got, skipped = store.extract_zip(bad, out)
        clean = not got and not os.path.exists(os.path.join(tmp, 'escape.ttf')) \
            and len(skipped) == 3
        print(f"zip:       hostile zip {'refused' if clean else 'NOT REFUSED'}")
        if not clean:
            failures.append("zip")
        fake = os.path.join(tmp, 'fake.ttf')
        with open(fake, 'wb') as f:
            f.write(b'this is not a font at all')
        try:
            fontfile.check_installable(fake)
            refused = False
        except fontfile.FontError:
            refused = True
        print(f"check:     not-a-font file {'refused' if refused else 'NOT REFUSED'}")
        if not refused:
            failures.append("check")
    print(f"windows:   {len(winfonts.parse_lsblk('{}'))} partitions in an empty answer")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _name_table(entries) -> bytes:
    """A tiny 'name' table (Windows, English) for the self-test."""
    records, strings = b'', b''
    for name_id, value in sorted(entries.items()):
        raw = value.encode('utf-16-be')
        records += struct.pack('>HHHHHH', 3, 1, 0x409, name_id, len(raw), len(strings))
        strings += raw
    return struct.pack('>HHH', 0, len(entries), 6 + 12 * len(entries)) + records + strings


def install_command(paths: List[str], replace: bool) -> int:
    from . import core, store
    from .text import t
    core.setup_logging()
    work = tempfile.mkdtemp(prefix='spark-fonts-')
    try:
        cands, problems = store.plan(paths, work)
        notes = [t('cli.skipped', name=n, why=_why(r)) for n, r in problems]
        todo = []
        for c in cands:
            if c.status == store.REFUSED:
                notes.append(t('cli.skipped', name=c.name, why=_why(c.reason)))
            elif c.status == store.SYSTEM:
                notes.append(t('cli.skipped', name=c.name, why=t('why.system', family=c.family)))
            elif c.status == store.SAME:
                notes.append(t('cli.skipped', name=c.name, why=t('why.same', family=c.family)))
            elif c.status == store.DUPLICATE and not replace:
                notes.append(t('cli.exists', name=c.name, family=c.family))
            else:
                todo.append(c)
        out = store.install(todo, replace=replace)
        for path in out.installed:
            print(t('cli.installed', path=path))
        for name, why in out.failed:
            notes.append(t('cli.skipped', name=name, why=why))
        for line in notes:
            print(line, file=sys.stderr)
        if out.installed:
            print(t('cli.summary', n=len(out.installed)))
            return 0 if not out.failed else 1
        print(t('cli.nothing'), file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _why(reason: str) -> str:
    from .text import EN, t
    return t('why.' + reason) if 'why.' + reason in EN else t('why.unreadable')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: see, install and remove fonts.")
    parser.add_argument('files', nargs='*', metavar='FILE',
                        help="font files, zip files or folders: open them in a preview")
    parser.add_argument('--install', action='store_true',
                        help="install FILE... for you without opening the window")
    parser.add_argument('--replace', action='store_true',
                        help="with --install: replace a font that is already installed")
    parser.add_argument('--self-test', action='store_true',
                        help="check the install; needs no display and changes nothing")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.install:
        if not args.files:
            parser.error("--install needs at least one FILE")
        return install_command(args.files, args.replace)
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App
    try:
        app = App(files=[os.path.abspath(p) for p in args.files] or None)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
