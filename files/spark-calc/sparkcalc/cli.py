"""The command line. --version, --self-test and --eval never load Tk."""

import argparse
import os
import sys
import time
from typing import List, Optional

T0 = time.monotonic()

from . import APP_NAME, APP_SLUG, MODES, VERSION  # noqa: E402


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


# (expression, options, expected answer) for --self-test
CHECKS = (
    ('0.1 + 0.2', {}, '0.3'),
    ('1/3 * 3', {}, '1'),
    ('2^64', {}, '18446744073709551616'),
    ('200 + 10%', {}, '220'),
    ('sin(30) + cos(60)', {'angle': 'deg'}, '1'),
    ('sin(pi/6)', {'angle': 'rad'}, '0.5'),
    ('sqrt(2)^2', {}, '2'),
    ('ln(e)', {}, '1'),
    ('100!', {}, '9.3326215443944152682e+157'),
    ('0x7F + 1', {'programmer': True, 'base': 16, 'bits': 8}, '80'),
    ('-1 >>> 1', {'programmer': True, 'base': 10, 'bits': 8}, '127'),
)
ERRORS = (
    ('1/0', {}, 'div_zero'),
    ('sqrt(-1)', {}, 'sqrt_neg'),
    ('2^2^2^2^2', {}, 'too_big'),
    ('(1+2))', {}, 'unbalanced'),
    ('1.5', {'programmer': True}, 'whole'),
)


def run(expr: str, opts: dict):
    from . import engine, programmer
    if opts.get('programmer'):
        return programmer.evaluate(expr, opts.get('base', 10), opts.get('bits', 64))
    return engine.evaluate(expr, opts.get('angle', 'deg'))


def self_test() -> int:
    """Check Python, Tk and the arithmetic. No display needed."""
    from . import engine
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
    import decimal
    fast = getattr(decimal, '__libmpdec_version__', None)
    print(f"decimal:   {'libmpdec ' + fast if fast else 'pure Python (slower, still exact)'}")
    start = time.perf_counter()
    bad = 0
    for expr, opts, want in CHECKS:
        try:
            got = run(expr, opts).text
        except engine.CalcError as exc:
            got = f"error {exc.key}"
        if got != want:
            print(f"check:     {expr} gave {got}, expected {want}")
            bad += 1
    for expr, opts, key in ERRORS:
        try:
            got = f"answer {run(expr, opts).text}"
        except engine.CalcError as exc:
            got = exc.key
            if exc.message().startswith('err.'):
                got += " (no sentence for it)"
        if got != key:
            print(f"check:     {expr} gave {got}, expected error {key}")
            bad += 1
    ms = 1000 * (time.perf_counter() - start)
    total = len(CHECKS) + len(ERRORS)
    print(f"sums:      {total - bad} of {total} right ({ms:.0f} ms)")
    if bad:
        failures.append("arithmetic")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def evaluate_cli(args) -> int:
    from .engine import CalcError
    opts = {'angle': args.angle, 'programmer': args.mode == 'programmer',
            'base': {'hex': 16, 'dec': 10, 'oct': 8, 'bin': 2}[args.base], 'bits': args.bits}
    try:
        print(run(args.eval, opts).text)
    except CalcError as exc:
        print(f"{APP_SLUG}: {exc.message()}", file=sys.stderr)
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS "
                                     "calculator. Exact sums, scientific and programmer modes.")
    parser.add_argument('--mode', choices=MODES, help="open in this mode")
    parser.add_argument('--eval', metavar='SUM', help="print the answer and exit "
                        "(no window), e.g. --eval '0.1+0.2'")
    parser.add_argument('--angle', choices=('deg', 'rad'), default='deg',
                        help="with --eval: angles in degrees (default) or radians")
    parser.add_argument('--base', choices=('hex', 'dec', 'oct', 'bin'), default='dec',
                        help="with --eval --mode programmer: read and print in this base")
    parser.add_argument('--bits', type=int, choices=(8, 16, 32, 64), default=64,
                        help="with --eval --mode programmer: word size (default 64)")
    parser.add_argument('--self-test', action='store_true',
                        help="check Python, Tk and the arithmetic; no display needed")
    parser.add_argument('--bench', action='store_true',
                        help="open, measure time to first paint and a few sums, then close")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.eval is not None:
        return evaluate_cli(args)
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    from .app import App, bench
    core.setup_logging()
    try:
        if args.bench:
            return bench(args.mode or 'standard')
        app = App(args.mode)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
