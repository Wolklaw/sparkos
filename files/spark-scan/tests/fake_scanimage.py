#!/usr/bin/env python3
"""A stand-in for SANE's scanimage, for the tests and for working on the window without a
scanner (Windows included). It answers like scanimage 1.4 with a pixma-like scanner that has
a glass and a feeder, and "scans" a drawn page:

    SPARK_SCAN_SCANIMAGE="python tests/fake_scanimage.py" python spark_scan.py

FAKE_SCANNERS=0         no scanner found
FAKE_ERROR=jammed       the scan fails like a jammed scanner (also: busy, cover, io, open)
FAKE_DELAY=0.05         seconds between progress steps (to test Cancel)
FAKE_FEEDER_PAGES=3     sheets in the feeder
FAKE_CRASH=1            the scanner list crashes (as a backend needing D-Bus does)
"""

import os
import re
import signal
import sys
import time

from PIL import Image, ImageDraw

GLASS_MM = (216.07, 297.03)
OPTIONS = """
All options specific to device `{dev}':
  Scan mode:
    --resolution auto|75|150|300|600|1200dpi [75]
        Sets the resolution of the scanned image.
    --mode auto|Color|Gray|Lineart [Color]
        Selects the scan mode (e.g., lineart, monochrome, or color).
    --source Flatbed|Automatic Document Feeder [Flatbed]
        Selects the scan source (such as a document-feeder).
    --button-controlled[=(yes|no)] [no]
        When enabled, scan process will not start immediately.
  Gamma:
    --custom-gamma[=(auto|yes|no)] [yes]
        Determines whether a builtin or a custom gamma-table should be used.
    --gamma-table auto|0..255,... [inactive]
        Gamma-correction table.
  Geometry:
    -l auto|0..216.07mm [0]
        Top-left x position of scan area.
    -t auto|0..297.03mm [0]
        Top-left y position of scan area.
    -x auto|0..216.07mm [216.07]
        Width of scan-area.
    -y auto|0..297.03mm [297.03]
        Height of scan-area.
"""
ERRORS = {
    'jammed': "scanimage: sane_read: Document feeder jammed",
    'busy': "scanimage: sane_start: Device busy",
    'cover': "scanimage: sane_start: Scanner cover is open",
    'io': "scanimage: sane_read: Error during device I/O",
    'open': "scanimage: open of device fake:0 failed: Invalid argument",
}

stop = [False]


def on_term(_sig, _frame):
    stop[0] = True


def arg(args, *names, default=None):
    for i, a in enumerate(args):
        for n in names:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(n + '='):
                return a.split('=', 1)[1]
    return default


def page(dpi, mode, area_mm, number):
    w = max(1, round(area_mm[2] / 25.4 * dpi))
    h = max(1, round(area_mm[3] / 25.4 * dpi))
    image = Image.new('RGB', (w, h), 'white')
    draw = ImageDraw.Draw(image)
    s = dpi / 25.4                                  # px per mm
    ox, oy = area_mm[0] * s, area_mm[1] * s         # where this area sits on the glass
    draw.rectangle((20 * s - ox, 20 * s - oy, 120 * s - ox, 60 * s - oy), fill='#3de8c8')
    draw.rectangle((20 * s - ox, 80 * s - oy, 190 * s - ox, 84 * s - oy), fill='black')
    draw.text((20 * s - ox, 100 * s - oy), f"PAGE {number}", fill='black')
    if mode == 'Gray':
        image = image.convert('L')
    elif mode == 'Lineart':
        image = image.convert('1')
    return image


def main(args):
    if '--version' in args:
        print("scanimage (sane-backends) 1.4.0; backend version 1.4.0")
        return 0
    if '-f' in args or '-L' in args:
        if os.environ.get('FAKE_CRASH'):
            print("dbus[11]: arguments to dbus_connection_send() were incorrect",
                  file=sys.stderr)
            return 134
        if os.environ.get('FAKE_SCANNERS') == '0':
            return 0
        print("fake:0\tFake\tFlatbed 3000\tflatbed scanner")
        print("airscan:e0:Fake Network 3000\tFake\tFake Network 3000\teSCL network scanner")
        return 0
    dev = arg(args, '-d', '--device-name', default='fake:0')
    if '-A' in args:
        print(OPTIONS.format(dev=dev))
        return 0
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    dpi = float(arg(args, '--resolution', default='75'))
    mode = arg(args, '--mode', default='Color')
    area = [float(arg(args, k, default=d)) for k, d in
            (('-l', '0'), ('-t', '0'), ('-x', str(GLASS_MM[0])), ('-y', str(GLASS_MM[1])))]
    source = arg(args, '--source', default='Flatbed')
    batch = next((a.split('=', 1)[1] for a in args if a.startswith('--batch=')), None)
    out = arg(args, '-o', '--output-file')
    delay = float(os.environ.get('FAKE_DELAY', '0'))
    error = os.environ.get('FAKE_ERROR')
    if error == 'open':
        print(ERRORS['open'], file=sys.stderr)
        return 1
    sheets = int(os.environ.get('FAKE_FEEDER_PAGES', '3')) if 'Feeder' in source else 1
    if batch:
        area = [0, 0, GLASS_MM[0], GLASS_MM[1]]
    print("Output format is not set, using pnm as a default.", file=sys.stderr) \
        if '--format=pnm' not in args else None
    n = 0
    while True:
        n += 1
        if n > sheets:
            if batch and n > 1:
                print(f"Batch terminated, {n - 1} pages scanned", file=sys.stderr)
                return 0
            print("scanimage: sane_start: Document feeder out of documents", file=sys.stderr)
            return 7
        if batch:
            print(f"Scanning page {n}", file=sys.stderr, flush=True)
        for pct in range(0, 101, 10):
            if stop[0]:
                print("\nscanimage: received signal 15", file=sys.stderr)
                print("scanimage: sane_read: Operation was cancelled", file=sys.stderr)
                return 2
            print(f"Progress: {pct:.1f}%", end='\r', file=sys.stderr, flush=True)
            if error and pct == 50:
                print("", file=sys.stderr)
                print(ERRORS.get(error, error), file=sys.stderr)
                return 9
            time.sleep(delay)
        image = page(dpi, mode, area, n)
        target = (re.sub(r'%\d*d', lambda m: m.group(0) % n, batch) if batch else out)
        if target:
            image.save(target, format='PPM')
        else:
            image.save(sys.stdout.buffer, format='PPM')
        if batch:
            print(f"Scanned page {n}. (scanner status = 5)", file=sys.stderr)
            print(target, flush=True)
        else:
            return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
