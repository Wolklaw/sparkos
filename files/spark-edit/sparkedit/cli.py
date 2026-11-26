"""The command line. --version and --self-test never load Tk, and `spark-edit FILE` hands
the file to an open window before Tk is even imported."""

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from typing import List, Optional, Tuple

T0 = time.monotonic()

from . import APP_NAME, APP_SLUG, VERSION  # noqa: E402


def process_age() -> float:
    """Seconds since this process started (Python's own start-up included), from /proc;
    elsewhere, since this module was imported."""
    try:
        with open('/proc/self/stat', encoding='ascii') as f:
            stat = f.read()
        with open('/proc/uptime', encoding='ascii') as f:
            up = float(f.read().split()[0])
        start = int(stat[stat.rfind(')') + 2:].split()[19])
        return up - start / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, AttributeError, IndexError):
        return time.monotonic() - T0


def parse_target(arg: str) -> Tuple[str, int, int]:
    """FILE, FILE:LINE or FILE:LINE:COLUMN (what compilers and grep -n print). A file whose
    own name ends in :digits is taken as it is when it exists."""
    if arg.startswith('file://'):
        from urllib.parse import unquote, urlparse
        arg = unquote(urlparse(arg).path)
    if os.path.exists(arg):
        return os.path.abspath(arg), 0, 0
    m = re.fullmatch(r'(.+?):(\d+)(?::(\d+))?:?', arg)
    if m and (os.path.exists(m.group(1)) or not os.path.exists(arg)):
        return os.path.abspath(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return os.path.abspath(arg), 0, 0


def self_test() -> int:
    """Check what Spark Edit needs, without a display."""
    from . import core, fileio, search, session, syntax
    from .fileio import Format
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
                         ('autosave', session.autosave_dir()), ('cache', core.cache_dir())):
        ok = os.path.isdir(folder) and os.access(folder, os.W_OK)
        print(f"{name + ':':<10} {core.home_short(folder)} ({'writable' if ok else 'NOT writable'})")
        if not ok:
            failures.append(name)

    # files: write and read back each kind of file it keeps as it was
    cases = [
        ('utf-8.txt', Format('utf-8'), "héllo\nwörld\n"),
        ('utf-8-bom.txt', Format('utf-8', True), "BOM\n"),
        ('crlf.txt', Format('utf-8', False, '\r\n'), "windows\nline endings\n"),
        ('utf-16.txt', Format('utf-16-le', True, '\r\n'), "UTF-16 « ok »\n"),
        ('latin-1.txt', Format('latin-1'), "café à Québec\n"),
        ('cp1252.txt', Format('cp1252'), "“quotes” — €\n"),
    ]
    bad = []
    with tempfile.TemporaryDirectory(prefix='spark-edit-test-') as tmp:
        for name, fmt, text in cases:
            path = os.path.join(tmp, name)
            try:
                fileio.write_file(path, fileio.encode(text, fmt))
                back, got, _st = fileio.read_file(path)
                if back != text or (got.encoding, got.bom, got.newline) != \
                        (fmt.encoding, fmt.bom, fmt.newline):
                    bad.append(f"{name} came back as {got.label()} {got.newline_label()}")
            except Exception as exc:     # noqa: BLE001
                bad.append(f"{name}: {exc}")
        try:
            fileio.read_file(_write(os.path.join(tmp, 'bin'), b'\x7fELF\x00\x01\x00\x00'))
            bad.append("a binary file was taken for text")
        except fileio.BinaryFile:
            pass
    print(f"files:     " + ("UTF-8, UTF-8 BOM, CRLF, UTF-16 LE, Latin-1, Windows-1252 read "
                            "and written back unchanged; binary files recognised" if not bad
                            else "FAILED: " + "; ".join(bad)))
    if bad:
        failures.append("files")

    sample = {
        'python': 'def f(x):\n    """doc\n    """\n    return x  # c\n',
        'javascript': 'const a = `x\n${y}`; /* c\n */ f(1);\n',
        'typescript': 'interface A { b: string }\n', 'json': '{"a": [1, true, null]}\n',
        'yaml': 'a: 1\n- b: "c"  # d\n', 'toml': '[t]\nk = """\nx\n"""\n',
        'ini': '[S]\nKey=value ; c\n', 'shell': 'f() { echo "$HOME" # c\n}\n',
        'markdown': '# T\n```\ncode\n```\n*a* `b`\n', 'html': '<a href="x">&amp;<!-- c\n-->\n',
        'css': '.a { color: #fff; } /* c\n */\n', 'c': '#include <a.h>\nint main() {}\n',
        'cpp': 'class A { public: A(); };\n', 'rust': "fn main() { println!(\"x\"); }\n",
        'go': 'func main() { s := `raw\n` }\n',
    }
    broken = []
    for lang in syntax.FACTORIES:
        try:
            lexer = syntax.lexer_for(lang)
            rows = syntax.lex_lines(lexer, sample[lang].split('\n'))
            if not any(toks for toks, _ in rows):
                broken.append(f"{lang} found nothing")
        except Exception as exc:     # noqa: BLE001
            broken.append(f"{lang}: {exc}")
    print(f"syntax:    {len(syntax.FACTORIES)} languages" +
          (" ok" if not broken else " FAILED: " + "; ".join(broken)))
    if broken:
        failures.append("syntax")

    q = search.Query('a.c', regex=True)
    found = search.find_next(q.compile(), 'xx abc', 0)
    if found != (3, 6):
        failures.append("search")
    print(f"search:    {'ok' if found == (3, 6) else 'FAILED'}")

    pk = fileio.pkexec_path()
    print(f"admin:     " + (f"pkexec at {pk} (Save as administrator works)" if pk else
                            "no pkexec: Save as administrator is unavailable"))
    pick = shutil.which('spark-pick')
    print(f"dialogs:   " + (f"{os.path.basename(pick)} (the desktop's own file dialogs)" if pick
                            else "Tk's own file dialogs (spark-pick not found)"))
    from .instance import socket_path
    sock = socket_path()
    print(f"window:    " + (f"one window, files handed over through {sock}" if sock else
                            "no XDG_RUNTIME_DIR: each spark-edit starts its own window"))
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _write(path: str, data: bytes) -> str:
    with open(path, 'wb') as f:
        f.write(data)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS text and code editor.",
        epilog="FILE may end in :LINE or :LINE:COLUMN, as compilers and grep -n print it.")
    parser.add_argument('files', nargs='*', metavar='FILE', help="files to open")
    parser.add_argument('--new-window', action='store_true',
                        help="start a separate window instead of using the open one")
    parser.add_argument('--self-test', action='store_true',
                        help="check what Spark Edit needs; no display needed")
    parser.add_argument('--bench', nargs='?', const='', metavar='FILE',
                        help="open (FILE), report how long it took, then close")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    targets = [parse_target(a) for a in args.files]
    if args.bench is None and not args.new_window:
        from .instance import hand_over
        if hand_over(targets):
            return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    from .app import App, bench
    core.setup_logging()
    try:
        if args.bench is not None:
            return bench(os.path.abspath(args.bench) if args.bench else None, process_age)
        app = App(targets, restore=not args.new_window)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
