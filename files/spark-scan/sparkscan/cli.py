"""The command line. --version, --self-test, --list and --scan-to never load Tk."""

import argparse
import os
import sys
import tempfile
import time
from typing import List, Optional

from . import APP_NAME, APP_SLUG, DPI_CHOICES, FORMATS, MODES, VERSION

T0 = time.monotonic()


def self_test(device: Optional[str] = None) -> int:
    """Check what Spark Scan needs and list the scanners. No display needed. A missing
    scanner is not a failure (CI has none); missing programs are."""
    from .core import Tesseract, scans_dir, short_path
    from .scanner import ScanError, list_devices, query_caps, scanimage, scanimage_version
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')     # a C locale can't print "×"
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
        from PIL import Image  # noqa: F401
        try:
            from PIL import ImageTk  # noqa: F401
            tk_note = "ImageTk yes"
        except ImportError:
            tk_note = "ImageTk no (pages are drawn through PNG data instead)"
        print(f"pillow:    {PIL.__version__}, {tk_note}")
    except ImportError as exc:
        print(f"pillow:    MISSING ({exc})")
        failures.append("pillow")
    cmd = scanimage()
    if cmd:
        print(f"scanimage: {' '.join(cmd)} (sane-backends {scanimage_version() or '?'})")
        try:
            devices = list_devices(timeout=30)
            if devices:
                for d in devices:
                    print(f"scanner:   {d.name}  ({d.label}, {d.kind or 'scanner'})")
            else:
                print("scanner:   none found (fine here; with a scanner on, it should be "
                      "listed)")
        except ScanError as exc:
            print(f"scanner:   could not list ({exc.kind}: {exc.detail})")
        if device:
            try:
                caps = query_caps(device)
                print(f"device:    {device}: modes {', '.join(caps.modes) or 'none'}; "
                      f"resolutions {caps.resolutions or caps.res_range}; area "
                      f"{'yes' if caps.area else 'no'} ({caps.area_unit}); sources "
                      f"{', '.join(caps.sources) or 'one'}")
            except ScanError as exc:
                print(f"device:    {device}: FAILED ({exc.kind}: {exc.detail})")
                failures.append("device")
    else:
        print("scanimage: MISSING (sane-backends)")
        failures.append("scanimage")
    tess = Tesseract()
    if tess.found:
        langs = tess.languages()
        print(f"tesseract: {tess.version()}, languages: {', '.join(langs) or 'none'}; "
              f"searchable PDF in: {', '.join(tess.language_choices()) or 'none'}")
    else:
        print("tesseract: not installed (searchable PDFs off; everything else works)")
    folder = scans_dir()
    print(f"saves to:  {short_path(folder)}")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def list_scanners() -> int:
    from .scanner import ScanError, list_devices
    try:
        for d in list_devices():
            print(f"{d.name}\t{d.label}\t{d.kind}")
    except ScanError as exc:
        print(f"{APP_SLUG}: {exc.kind}: {exc.detail}", file=sys.stderr)
        return 1
    return 0


def parse_area(text: str):
    parts = [float(p) for p in text.split(',')]
    if len(parts) != 4 or not (0 <= parts[0] < parts[2] <= 1 and 0 <= parts[1] < parts[3] <= 1):
        raise argparse.ArgumentTypeError("--area is x0,y0,x1,y1 as fractions of the glass, "
                                         "e.g. 0,0,0.5,0.5")
    return tuple(parts)


def scan_to(args) -> int:
    """Scan without a window: --pages pages from the glass (or the whole feeder), then save
    them like the window does. For scripts, and for CI with SANE's test scanner."""
    from .core import Tesseract, page_paths, scan_name, setup_logging, unique_path
    from .document import save_images, save_ocr_pdf, save_pdf
    from .scanner import Request, ScanError, list_devices, query_caps
    from .text import t
    from .work import Session
    setup_logging()
    try:
        device = args.device
        if not device:
            found = list_devices()
            if not found:
                print(f"{APP_SLUG}: no scanner found", file=sys.stderr)
                return 1
            device = found[0].name
        caps = query_caps(device)
    except ScanError as exc:
        print(f"{APP_SLUG}: {exc.kind}: {exc.detail}", file=sys.stderr)
        return 1
    target = os.path.abspath(args.scan_to)
    fmt = args.format or (os.path.splitext(target)[1][1:].lower() if not os.path.isdir(target)
                          else 'pdf')
    if fmt == 'jpeg':
        fmt = 'jpg'
    if fmt not in FORMATS:
        print(f"{APP_SLUG}: can't save .{fmt}; use {', '.join(FORMATS)}", file=sys.stderr)
        return 2
    session = Session(tempfile.mkdtemp(prefix=f'{APP_SLUG}-cli-'))
    try:
        req = Request(device, args.dpi, args.mode, area=args.area, source=args.source or '',
                      extra=[f"--{o}" for o in args.sane_option])
        pages = []
        rounds = 1 if req.source in ('feeder', 'duplex') else args.pages
        for n in range(rounds):
            def progress(fraction, page, n=n):
                print(f"\rscanning page {len(pages) + (page if req.source in ('feeder', 'duplex') else 1)}"
                      f" {int(fraction * 100):3d}%", end='', file=sys.stderr, flush=True)
            got = session.scan(caps, req, progress, views=False)
            print(file=sys.stderr)
            pages += got
        if not pages:
            print(f"{APP_SLUG}: nothing scanned", file=sys.stderr)
            return 1
        for i, p in enumerate(pages, 1):
            print(f"page {i}: {p.width}x{p.height} px at {p.dpi:g} dpi, {p.mode}")
        if os.path.isdir(target):
            stem = scan_name(t('file.scan'))
            paths = [unique_path(target, stem, fmt)] if fmt == 'pdf' else \
                page_paths(target, stem, fmt, len(pages), t('file.page'))
        elif fmt == 'pdf' or len(pages) == 1:
            paths = [target]
        else:
            base = os.path.splitext(target)[0]
            paths = [f"{base}-{i}.{fmt}" for i in range(1, len(pages) + 1)]
        if fmt == 'pdf' and args.ocr:
            tess = Tesseract()
            lang = args.ocr_lang or (tess.language_choices() or ['eng'])[0]
            save_ocr_pdf(pages, paths[0], lang, tess, session.folder)
        elif fmt == 'pdf':
            save_pdf(pages, paths[0], os.path.splitext(os.path.basename(paths[0]))[0])
        else:
            save_images(pages, paths, fmt)
        for path in (paths[:1] if fmt == 'pdf' else paths):
            print(f"saved {path}")
        return 0
    except ScanError as exc:
        print(file=sys.stderr)
        print(f"{APP_SLUG}: {exc.kind}: {exc.detail}", file=sys.stderr)
        return 1
    finally:
        session.clear()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: scanning for "
                                     "SparkOS, through SANE.")
    parser.add_argument('--device', metavar='NAME',
                        help="use this scanner (a name from --list, e.g. airscan:e0:Canon…)")
    parser.add_argument('--list', action='store_true', help="list the scanners and exit")
    parser.add_argument('--self-test', action='store_true',
                        help="check scanimage, Pillow, Tk and tesseract, and list scanners; "
                             "no display needed")
    parser.add_argument('--scan-to', metavar='PATH',
                        help="scan without a window and save to this file or folder")
    parser.add_argument('--pages', type=int, default=1, help="with --scan-to: pages from the "
                        "glass, one after another")
    parser.add_argument('--dpi', type=int, default=300, choices=DPI_CHOICES)
    parser.add_argument('--mode', default='color', choices=MODES)
    parser.add_argument('--source', choices=('glass', 'feeder', 'duplex'))
    parser.add_argument('--area', type=parse_area, help="with --scan-to: x0,y0,x1,y1 as "
                        "fractions of the glass")
    parser.add_argument('--format', choices=FORMATS + ('jpeg',))
    parser.add_argument('--ocr', action='store_true', help="with --scan-to: searchable PDF")
    parser.add_argument('--ocr-lang', help="tesseract languages, e.g. eng+fra")
    parser.add_argument('--sane-option', action='append', default=[], metavar='NAME=VALUE',
                        help="with --scan-to: pass --NAME=VALUE to scanimage (repeatable)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.device)
    if args.list:
        return list_scanners()
    if args.scan_to:
        return scan_to(args)
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from .core import setup_logging
    setup_logging()
    from .app import App
    try:
        app = App(args.device)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
