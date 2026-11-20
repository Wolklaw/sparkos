"""Spark Scan tests. Plain unittest:

    python -m unittest discover -s files/spark-scan/tests -v

- Parsers, the PDF writer, file names and the text tables run anywhere, Windows included.
- FakeScannerTests drive fake_scanimage.py (a stand-in for scanimage) and run anywhere.
- SaneTestBackendTests use SANE's own `test` scanner through the real scanimage: Linux with
  sane-backends installed (CI: Fedora, and the SparkOS image). They point SANE_CONFIG_DIR at
  a folder that enables only the test backend.
- OcrTests need tesseract with English and pdftotext.
- WindowTests need a display (CI: xvfb-run).
"""

import gc
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-scan-{var.lower()}-')
OUTPUT = tempfile.mkdtemp(prefix='spark-scan-output-')
os.environ['SPARK_SCAN_OUTPUT'] = OUTPUT
os.environ['SPARK_SCAN_REDUCED_MOTION'] = '1'
os.environ.pop('SPARK_SCAN_SCANIMAGE', None)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from sparkscan import VERSION  # noqa: E402
from sparkscan import adjust, core, document, scanner, text, work  # noqa: E402
from sparkscan.adjust import Edits  # noqa: E402
from sparkscan.document import Page, PdfWriter, save_images, save_pdf  # noqa: E402
from sparkscan.scanner import (Caps, Request, ScanError, area_args, classify_error,  # noqa: E402
                               command, parse_devices, parse_options)
from sparkscan.work import Session  # noqa: E402

LINUX = sys.platform.startswith('linux')
FAKE = f'"{sys.executable}" "{os.path.join(HERE, "fake_scanimage.py")}"'
REAL_SCANIMAGE = shutil.which('scanimage')
REAL_SANE_TEST = bool(REAL_SCANIMAGE and LINUX and any(
    os.path.exists(os.path.join(d, 'sane', 'libsane-test.so.1'))
    for d in ('/usr/lib64', '/usr/lib', '/usr/lib/x86_64-linux-gnu')))

# scanimage 1.4.0 -A for SANE's test scanner (trimmed), as Fedora 45 prints it
TEST_BACKEND_OPTIONS = """
All options specific to device `test:0':
  Scan Mode:
    --mode Gray|Color [Gray]
        Selects the scan mode (e.g., lineart, monochrome, or color).
    --depth 1|8|16 [8]
        Number of bits per sample, typical values are 1 for "line-art" and 8
    --hand-scanner[=(yes|no)] [no]
        Simulate a hand-scanner.
    --three-pass[=(yes|no)] [inactive]
    --three-pass-order RGB|RBG|GBR|GRB|BRG|BGR [inactive]
    --resolution 1..1200dpi (in steps of 1) [50]
        Sets the resolution of the scanned image.
    --source Flatbed|Automatic Document Feeder [Flatbed]
        If Automatic Document Feeder is selected, the feeder will be 'empty'
  Special Options:
    --test-picture Solid black|Solid white|Color pattern|Grid [Solid black]
    --read-return-value Default|SANE_STATUS_UNSUPPORTED|SANE_STATUS_JAMMED [Default]
    --ppl-loss 0..128pel (in steps of 1) [0]
    --print-options
        Print a list of all options.
  Geometry:
    -l 0..200mm (in steps of 1) [0]
        Top-left x position of scan area.
    -t 0..200mm (in steps of 1) [0]
    -x 0..200mm (in steps of 1) [80]
    -y 0..200mm (in steps of 1) [100]
  Int test options:
    --int <int> [inactive]
    --int-constraint-word-list -42|-8|0|17|42|256|65536|16777216|1073741824bit [inactive]
    --red-gamma-table 0..255,... (in steps of 1) [advanced]
"""

# what sane-airscan prints for an eSCL printer-scanner (the Canon TR4700 is one)
AIRSCAN_OPTIONS = """
All options specific to device `airscan:e0:Canon TR4700 series':
  Standard:
    --resolution 75|100|150|200|300|600dpi [300]
        Sets the resolution of the scanned image.
    --mode Color|Gray [Color]
        Selects the scan mode (e.g., lineart, monochrome, or color).
    --source Flatbed|ADF [Flatbed]
        Selects the scan source (such as a document-feeder).
  Geometry:
    -l 0..215.9mm [0]
        Top-left x position of scan area.
    -t 0..297.1mm [0]
        Top-left y position of scan area.
    -x 0..215.9mm [215.9]
        Width of scan-area.
    -y 0..297.1mm [297.1]
        Height of scan-area.
  Enhancement:
    --brightness -100..100% (in steps of 1) [0]
        Controls the brightness of the acquired image.
"""


def check_pdf(testcase, path, pages):
    """Our own reading of a PDF: header, every xref offset lands on its object, startxref
    is right, and the page count. Then pdfinfo, qpdf --check where installed."""
    with open(path, 'rb') as f:
        data = f.read()
    testcase.assertTrue(data.startswith(b'%PDF-1.'), data[:10])
    testcase.assertTrue(data.rstrip().endswith(b'%%EOF'))
    start = int(re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$', data).group(1))
    testcase.assertEqual(data[start:start + 4], b'xref')
    head = re.match(rb'xref\s+0 (\d+)\s+', data[start:])
    count = int(head.group(1))
    table = data[start + head.end():start + head.end() + 20 * count]
    for num in range(1, count):
        entry = table[20 * num:20 * num + 20]
        offset = int(entry[:10])
        testcase.assertTrue(data[offset:].startswith(b'%d 0 obj' % num),
                            f"object {num} not at {offset}")
    found = re.search(rb'/Type /Pages /Kids \[[^\]]*\] /Count (\d+)', data)
    testcase.assertEqual(int(found.group(1)), pages)
    if shutil.which('pdfinfo'):
        out = subprocess.run(['pdfinfo', path], capture_output=True, text=True)
        testcase.assertEqual(out.returncode, 0, out.stderr)
        testcase.assertRegex(out.stdout, rf'(?m)^Pages:\s+{pages}$')
        testcase.assertEqual(out.stderr.strip(), '', out.stderr)
    if shutil.which('qpdf'):
        out = subprocess.run(['qpdf', '--check', path], capture_output=True, text=True)
        testcase.assertEqual(out.returncode, 0, out.stdout + out.stderr)


def pdf_page_sizes(path):
    with open(path, 'rb') as f:
        data = f.read()
    return [(float(w), float(h)) for w, h in
            re.findall(rb'/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]', data)]


def make_page(folder, name, image, dpi, mode):
    path = os.path.join(folder, name + ('.png' if image.mode == '1' else '.pnm'))
    image.save(path)
    return Page(path, image.width, image.height, dpi, mode)


WORDS = ("the quick brown fox jumps over the lazy dog spark scan straightens pages "
         "scanned at a slant before saving them").split()


def text_page(skew=0.0, mode='gray', size=(2480, 3508), paper=236, seed=1, font_size=42,
              spacing=70, words=None):
    """An A4 page at 300 dpi with lines of text, tilted by skew degrees (counter-clockwise,
    as PIL's rotate), on slightly grey paper, as a scanner might return it."""
    import random
    rnd = random.Random(seed)
    image = Image.new('L', size, paper)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=font_size)
    y = int(size[1] * 0.08)
    lines = list(words) if words else None
    while y < size[1] * 0.9:
        if lines is not None:
            if not lines:
                break
            line = lines.pop(0)
        else:
            line = ' '.join(rnd.choice(WORDS) for _ in range(rnd.randint(6, 11)))
        draw.text((int(size[0] * 0.1), y), line, fill=25, font=font)
        y += spacing
    if skew:
        image = image.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=paper)
    if mode == 'color':
        # yellowish paper, dark blue ink
        image = Image.merge('RGB', (image, image, image.point(lambda v: int(v * 0.86))))
    elif mode == 'bw':
        image = image.point(lambda v: 255 if v > 128 else 0, mode='1')
    return image


# ─── Parsing what scanimage prints ────────────────────────────

class ParserTests(unittest.TestCase):
    def test_device_list(self):
        devices = parse_devices(
            "pixma:MF_TR4700_192.168.1.20\tCANON\tCanon TR4700 series\tmultifunction "
            "peripheral\n"
            "airscan:e0:Canon TR4700 series\tCanon\tCanon TR4700 series\teSCL network "
            "scanner\n"
            "No scanners were identified. If you were expecting something different,\n"
            "airscan:e0:Canon TR4700 series\tCanon\tdup\tx\n")
        self.assertEqual([d.name for d in devices], ['pixma:MF_TR4700_192.168.1.20',
                                                     'airscan:e0:Canon TR4700 series'])
        self.assertEqual(devices[0].label, 'Canon TR4700 series')
        self.assertEqual(devices[1].backend, 'airscan')
        self.assertEqual(parse_devices(''), [])

    def test_test_backend_options(self):
        opts = parse_options(TEST_BACKEND_OPTIONS)
        self.assertEqual(opts['mode'].values, ['Gray', 'Color'])
        self.assertEqual((opts['resolution'].low, opts['resolution'].high,
                          opts['resolution'].unit), (1.0, 1200.0, 'dpi'))
        self.assertEqual(opts['source'].values, ['Flatbed', 'Automatic Document Feeder'])
        self.assertEqual(opts['source'].default, 'Flatbed')
        self.assertEqual((opts['x'].low, opts['x'].high, opts['x'].unit), (0, 200, 'mm'))
        self.assertEqual(opts['x'].default, '80')
        self.assertTrue(opts['three-pass'].inactive)
        self.assertEqual(opts['hand-scanner'].values, ['yes', 'no'])
        self.assertEqual(opts['int-constraint-word-list'].unit, 'bit')
        self.assertNotIn('int', {k for k, v in opts.items() if v.values or v.low is not None})
        caps = Caps.from_options('test:0', opts)
        self.assertEqual(caps.modes, {'gray': 'Gray', 'color': 'Color'})
        self.assertEqual(caps.res_range, (1.0, 1200.0))
        self.assertEqual(caps.sources, {'glass': 'Flatbed', 'feeder': 'Automatic Document Feeder'})
        self.assertEqual(caps.source_default, 'glass')
        self.assertFalse(caps.depth8)
        self.assertEqual(caps.resolution(600), 600)
        self.assertEqual(caps.preview_resolution(75), 75)

    def test_airscan_options(self):
        caps = Caps.from_options('airscan:e0:x', parse_options(AIRSCAN_OPTIONS))
        self.assertEqual(caps.resolutions, [75, 100, 150, 200, 300, 600])
        self.assertEqual(caps.modes, {'color': 'Color', 'gray': 'Gray'})
        self.assertEqual(caps.sources, {'glass': 'Flatbed', 'feeder': 'ADF'})
        self.assertEqual(caps.area['y'], (0.0, 297.1))
        # black and white without a Lineart mode: scanned grey, made B&W here
        self.assertEqual(caps.device_mode('bw'), 'Gray')
        self.assertEqual(caps.resolution(600), 600)
        self.assertEqual(caps.resolution(1200), 600)
        self.assertEqual(caps.resolution(250), 300)    # a tie goes to the sharper one
        self.assertEqual(caps.preview_resolution(75), 75)

    def test_pixma_auto_prefix(self):
        with open(os.path.join(HERE, 'fake_scanimage.py'), encoding='utf-8') as f:
            body = f.read()
        block = body.split('OPTIONS = """', 1)[1].split('"""', 1)[0]
        caps = Caps.from_options('fake:0', parse_options(block.format(dev='fake:0')))
        self.assertEqual(caps.resolutions, [75, 150, 300, 600, 1200])
        self.assertEqual(caps.modes, {'color': 'Color', 'gray': 'Gray', 'lineart': 'Lineart'})
        self.assertEqual(caps.area['x'], (0.0, 216.07))
        self.assertEqual(caps.sources, {'glass': 'Flatbed', 'feeder': 'Automatic Document Feeder'})

    def test_sources(self):
        kind = scanner.source_kind
        self.assertEqual(kind('Flatbed'), 'glass')
        self.assertEqual(kind('Platen'), 'glass')
        self.assertEqual(kind('ADF'), 'feeder')
        self.assertEqual(kind('ADF Front'), 'feeder')
        self.assertEqual(kind('ADF Duplex'), 'duplex')
        self.assertEqual(kind('Automatic Document Feeder'), 'feeder')
        self.assertIsNone(kind('Transparency Unit'))

    def test_area_and_command(self):
        caps = Caps.from_options('airscan:e0:x', parse_options(AIRSCAN_OPTIONS))
        self.assertEqual(area_args(caps, None),
                         ['-l', '0', '-t', '0', '-x', '215.9', '-y', '297.1'])
        self.assertEqual(area_args(caps, (0.5, 0.5, 1.0, 1.0)),
                         ['-l', '107.95', '-t', '148.55', '-x', '107.95', '-y', '148.55'])
        cmd = command(caps, Request('airscan:e0:x', 300, 'bw', (0, 0, .5, .5), 'glass'),
                      out='/tmp/x.pnm')
        self.assertIn('--format=pnm', cmd)
        self.assertEqual(cmd[cmd.index('--mode') + 1], 'Gray')
        self.assertEqual(cmd[cmd.index('--resolution') + 1], '300')
        self.assertEqual(cmd[cmd.index('--source') + 1], 'Flatbed')
        self.assertEqual(cmd[-2:], ['-o', '/tmp/x.pnm'])
        feeder = command(caps, Request('airscan:e0:x', 150, 'color', (0, 0, .5, .5), 'feeder'),
                         batch='/tmp/p-%d.pnm')
        self.assertNotIn('-l', feeder)                      # no crop in the feeder
        self.assertIn('--batch=/tmp/p-%d.pnm', feeder)
        self.assertIn('--batch-print', feeder)
        self.assertEqual(feeder[feeder.index('--source') + 1], 'ADF')

    def test_errors(self):
        self.assertEqual(classify_error("scanimage: sane_read: Document feeder jammed"),
                         'jammed')
        self.assertEqual(classify_error("scanimage: sane_start: Device busy"), 'busy')
        self.assertEqual(classify_error("scanimage: sane_start: Scanner cover is open"),
                         'cover_open')
        self.assertEqual(classify_error(
            "scanimage: sane_start: Document feeder out of documents"), 'no_docs')
        self.assertEqual(classify_error(
            "scanimage: open of device x failed: Invalid argument"), 'open_failed')
        self.assertEqual(classify_error("something else"), 'failed')
        reason = scanner.exit_reason(-6, "dbus[44]: arguments to dbus_connection_send() were "
                                         "incorrect\n\n  D-Bus not built with -rdynamic\n")
        self.assertRegex(reason, r'^scanimage crashed \((SIGABRT|signal 6)\): dbus\[44\]')
        self.assertEqual(scanner.exit_reason(1, "x\nscanimage: open of device y failed\n"),
                         "scanimage: open of device y failed")
        self.assertEqual(scanner.last_error_line(
            "Progress: 50.0%\rProgress: 60.0%\nscanimage: sane_read: Error during device I/O\n"),
            "scanimage: sane_read: Error during device I/O")

    def test_black_and_white(self):
        image = Image.new('L', (100, 100), 235)
        ImageDraw.Draw(image).rectangle((10, 10, 40, 90), fill=30)
        bw = scanner.to_black_and_white(image)
        self.assertEqual(bw.mode, '1')
        self.assertEqual(bw.getpixel((20, 50)), 0)
        self.assertEqual(bw.getpixel((80, 50)), 255)
        # a blank page stays white
        self.assertEqual(scanner.to_black_and_white(Image.new('L', (20, 20), 240))
                         .getpixel((5, 5)), 255)


# ─── Files, names, words ──────────────────────────────────────

class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-scan-files-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_names(self):
        from datetime import datetime
        stem = core.scan_name('Scan', datetime(2026, 11, 20, 14, 32))
        self.assertEqual(stem, 'Scan 2026-11-20 14.32')
        first = core.unique_path(self.dir, stem, 'pdf')
        open(first, 'w').close()
        self.assertTrue(core.unique_path(self.dir, stem, 'pdf').endswith('14.32 (2).pdf'))
        paths = core.page_paths(self.dir, stem, 'png', 2, 'page')
        self.assertTrue(paths[0].endswith('Scan 2026-11-20 14.32 - page 1.png'))
        open(paths[1], 'w').close()
        again = core.page_paths(self.dir, stem, 'png', 2, 'page')
        self.assertTrue(again[0].endswith('14.32 (2) - page 1.png'))
        self.assertEqual(core.page_paths(self.dir, 'x', 'png', 1, 'page'),
                         [os.path.join(self.dir, 'x.png')])

    def test_scans_folder(self):
        self.assertEqual(core.scans_dir(), OUTPUT)
        saved = os.environ.pop('SPARK_SCAN_OUTPUT')
        try:
            self.assertEqual(os.path.basename(core.scans_dir()), 'Scans')
        finally:
            os.environ['SPARK_SCAN_OUTPUT'] = saved

    def test_text_tables(self):
        def fields(s):
            return sorted(re.findall(r'\{(\w+)\}', s))
        self.assertEqual(set(text.EN), set(text.FR), set(text.EN) ^ set(text.FR))
        for key, en in text.EN.items():
            self.assertEqual(fields(en), fields(text.FR[key]), key)

    def test_pdf_writer(self):
        colour = Image.new('RGB', (850, 1100), '#3de8c8')
        grey = Image.new('L', (300, 200), 128)
        bw = Image.new('1', (1001, 33), 1)            # width not a multiple of 8
        ImageDraw.Draw(bw).line((0, 0, 1000, 32), fill=0)
        pages = [make_page(self.dir, 'a', colour, 100, 'color'),
                 make_page(self.dir, 'b', grey, 300, 'gray'),
                 make_page(self.dir, 'c', bw, 600, 'bw')]
        path = os.path.join(self.dir, 'Scan é (1).pdf')
        seen = []
        save_pdf(pages, path, 'Scan é', progress=lambda f, w: seen.append((f, w)))
        check_pdf(self, path, 3)
        sizes = pdf_page_sizes(path)
        self.assertAlmostEqual(sizes[0][0], 612.0, places=2)     # 8.5 in at 100 dpi
        self.assertAlmostEqual(sizes[0][1], 792.0, places=2)
        self.assertAlmostEqual(sizes[1][0], 72.0, places=2)
        self.assertAlmostEqual(sizes[2][0], 1001 * 72 / 600, places=2)
        self.assertEqual(seen[-1], (1.0, '3/3'))
        with open(path, 'rb') as f:
            data = f.read()
        self.assertIn(b'/DCTDecode', data)
        self.assertIn(b'/DeviceGray /BitsPerComponent 1 /Filter /FlateDecode', data)
        self.assertIn(document.pdf_text(f'Spark Scan {VERSION}'), data)
        # the black-and-white page's bits survive
        stream = data.split(b'/BitsPerComponent 1 /Filter /FlateDecode /Length ')[1]
        length = int(stream.split(b' ', 1)[0])
        raw = stream.split(b'stream\n', 1)[1][:length]
        self.assertEqual(zlib.decompress(raw), bw.tobytes())
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith('.part')])

    def test_pdf_cancel_leaves_nothing(self):
        pages = [make_page(self.dir, f'p{i}', Image.new('RGB', (50, 50)), 72, 'color')
                 for i in range(3)]
        cancel = threading.Event()
        path = os.path.join(self.dir, 'x.pdf')

        def progress(fraction, _which):
            if fraction > 0:
                cancel.set()
        with self.assertRaises(document.Cancelled):
            save_pdf(pages, path, progress=progress, cancel=cancel)
        self.assertEqual(sorted(os.listdir(self.dir)), ['p0.pnm', 'p1.pnm', 'p2.pnm'])

    def test_images(self):
        pages = [make_page(self.dir, 'a', Image.new('RGB', (60, 40), 'red'), 150, 'color'),
                 make_page(self.dir, 'b', Image.new('1', (60, 40), 1), 300, 'bw')]
        out = os.path.join(self.dir, 'out')
        os.makedirs(out)
        for fmt in ('png', 'jpg'):
            paths = core.page_paths(out, 'Scan', fmt, 2, 'page')
            save_images(pages, paths, fmt)
            for path, page in zip(paths, pages):
                with Image.open(path) as im:
                    self.assertEqual(im.size, (60, 40))
                    self.assertAlmostEqual(im.info['dpi'][0], page.dpi, delta=1)
        with Image.open(os.path.join(out, 'Scan - page 2.png')) as im:
            self.assertEqual(im.mode, '1')


# ─── The fake scanner ─────────────────────────────────────────

class FakeScannerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SPARK_SCAN_SCANIMAGE'] = FAKE
        for var in ('FAKE_ERROR', 'FAKE_DELAY', 'FAKE_SCANNERS', 'FAKE_CRASH',
                    'FAKE_FEEDER_PAGES'):
            os.environ.pop(var, None)
        self.session = Session(tempfile.mkdtemp(prefix='spark-scan-session-'))
        self.caps = scanner.query_caps('fake:0')

    def tearDown(self):
        os.environ.pop('SPARK_SCAN_SCANIMAGE', None)
        self.session.clear()

    def test_list(self):
        names = [d.name for d in scanner.list_devices()]
        self.assertEqual(names, ['fake:0', 'airscan:e0:Fake Network 3000'])
        os.environ['FAKE_SCANNERS'] = '0'
        self.assertEqual(scanner.list_devices(), [])
        os.environ['FAKE_CRASH'] = '1'
        with self.assertRaises(ScanError) as ctx:
            scanner.list_devices()
        self.assertEqual(ctx.exception.kind, 'list_failed')

    def test_scan_crop_modes(self):
        progress = []
        pages = self.session.scan(self.caps, Request('fake:0', 150, 'color', (0, 0, .5, .5),
                                                     'glass'),
                                  lambda f, p: progress.append(f))
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertAlmostEqual(page.width, 216.07 / 2 / 25.4 * 150, delta=2)
        self.assertEqual(page.dpi, 150)
        self.assertTrue(os.path.isfile(page.view_path))
        self.assertEqual(progress[-1], 1.0)
        with page.open() as im:
            self.assertEqual(im.mode, 'RGB')
            # the mint box the fake draws at 20-120 mm sits inside the crop
            self.assertEqual(im.getpixel((int(50 / 25.4 * 150), int(40 / 25.4 * 150))),
                             (0x3d, 0xe8, 0xc8))
        bw = self.session.scan(self.caps, Request('fake:0', 300, 'bw', None, 'glass'))[0]
        self.assertTrue(bw.path.endswith('.png'))
        with bw.open() as im:
            self.assertEqual(im.mode, '1')
        grey = self.session.scan(self.caps, Request('fake:0', 75, 'gray'))[0]
        with grey.open() as im:
            self.assertEqual(im.mode, 'L')

    def test_preview(self):
        image = self.session.preview(self.caps)
        self.assertEqual(image.mode, 'RGB')
        self.assertAlmostEqual(image.width, 216.07 / 25.4 * 75, delta=2)

    def test_feeder(self):
        os.environ['FAKE_FEEDER_PAGES'] = '3'
        got = []
        pages = self.session.scan(self.caps, Request('fake:0', 75, 'gray', (0, 0, .5, .5),
                                                     'feeder'), on_page=got.append)
        self.assertEqual(len(pages), 3)
        self.assertEqual(got, pages)
        self.assertAlmostEqual(pages[0].width, 216.07 / 25.4 * 75, delta=2)   # no crop

    def test_errors(self):
        for kind, expect in (('jammed', 'jammed'), ('busy', 'busy'), ('cover', 'cover_open'),
                             ('io', 'io'), ('open', 'open_failed')):
            os.environ['FAKE_ERROR'] = kind
            with self.assertRaises(ScanError) as ctx:
                self.session.scan(self.caps, Request('fake:0', 75, 'color'))
            self.assertEqual(ctx.exception.kind, expect, ctx.exception.detail)
        os.environ.pop('FAKE_ERROR')
        os.environ['FAKE_FEEDER_PAGES'] = '0'
        with self.assertRaises(ScanError) as ctx:
            self.session.scan(self.caps, Request('fake:0', 75, 'color', source='feeder'))
        self.assertEqual(ctx.exception.kind, 'no_docs')
        self.assertEqual([n for n in os.listdir(self.session.folder) if 'raw' in n], [])

    def test_cancel(self):
        os.environ['FAKE_DELAY'] = '0.3'
        threading.Timer(0.8, self.session.cancel).start()
        started = time.monotonic()
        pages = self.session.scan(self.caps, Request('fake:0', 75, 'color'))
        self.assertEqual(pages, [])
        self.assertLess(time.monotonic() - started, 3.5)

    def test_cli(self):
        out = os.path.join(OUTPUT, 'cli.pdf')
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--scan-to', out, '--device', 'fake:0', '--pages', '2',
                              '--dpi', '150', '--mode', 'gray'],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        check_pdf(self, out, 2)
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--self-test', '--device', 'fake:0'],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('self-test passed', res.stdout)
        self.assertIn('scanner:   fake:0', res.stdout)


# ─── SANE's own test scanner, through the real scanimage ──────

@unittest.skipUnless(REAL_SANE_TEST, "needs scanimage and SANE's test backend (Linux)")
class SaneTestBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = tempfile.mkdtemp(prefix='spark-scan-sane-')
        with open(os.path.join(cls.conf, 'dll.conf'), 'w') as f:
            f.write('test\n')
        with open(os.path.join(cls.conf, 'test.conf'), 'w') as f:
            f.write('number_of_devices 2\ntest-picture "Color pattern"\n')
        cls.saved = os.environ.get('SANE_CONFIG_DIR')
        os.environ['SANE_CONFIG_DIR'] = cls.conf
        os.environ.pop('SPARK_SCAN_SCANIMAGE', None)
        cls.caps = scanner.query_caps('test:0')

    @classmethod
    def tearDownClass(cls):
        if cls.saved is None:
            os.environ.pop('SANE_CONFIG_DIR', None)
        else:
            os.environ['SANE_CONFIG_DIR'] = cls.saved
        shutil.rmtree(cls.conf, ignore_errors=True)

    def setUp(self):
        self.session = Session(tempfile.mkdtemp(prefix='spark-scan-session-'))

    def tearDown(self):
        self.session.clear()

    def test_finds_test_scanners(self):
        names = [d.name for d in scanner.list_devices()]
        self.assertIn('test:0', names)
        self.assertIn('test:1', names)

    def test_caps(self):
        caps = self.caps
        self.assertEqual(set(caps.modes), {'color', 'gray'})
        self.assertEqual(caps.res_range, (1.0, 1200.0))
        self.assertEqual(caps.area['x'], (0.0, 200.0))
        self.assertEqual(set(caps.sources), {'glass', 'feeder'})

    def test_scan_colour_crop(self):
        progress = []
        pages = self.session.scan(self.caps, Request('test:0', 150, 'color',
                                                     (0.0, 0.0, 0.5, 0.25), 'glass'),
                                  lambda f, p: progress.append(f))
        self.assertEqual(len(pages), 1)
        page = pages[0]
        # 100 x 50 mm at 150 dpi
        self.assertAlmostEqual(page.width, 100 / 25.4 * 150, delta=3)
        self.assertAlmostEqual(page.height, 50 / 25.4 * 150, delta=3)
        with page.open() as im:
            self.assertEqual(im.mode, 'RGB')
            self.assertGreater(len(im.resize((40, 20)).getcolors(800)), 3)   # a pattern
        self.assertTrue(progress and max(progress) >= 0.99, progress[-5:])

    def test_scan_grey_and_bw(self):
        grey = self.session.scan(self.caps, Request('test:0', 100, 'gray', (0, 0, .3, .3)))[0]
        with grey.open() as im:
            self.assertEqual(im.mode, 'L')
        bw = self.session.scan(self.caps, Request('test:0', 300, 'bw', (0, 0, .3, .3)))[0]
        with bw.open() as im:
            self.assertEqual(im.mode, '1')
        self.assertAlmostEqual(bw.width, 60 / 25.4 * 300, delta=3)

    def test_turn_and_straighten_a_scan(self):
        """A page from the test scanner's Grid picture: already straight; tilted by a known
        angle it is measured within 0.5 degrees; turned, it saves turned."""
        req = Request('test:0', 150, 'gray', (0, 0, .5, .6), 'glass',
                      extra=['--test-picture=Grid'])
        page = self.session.scan(self.caps, req)[0]
        self.assertEqual(work.straighten(page), 0.0)
        with page.open() as im:
            lo, hi = im.getextrema()
            self.assertLess(lo, hi)                              # lines on it
            tilted = im.rotate(-4.5, resample=Image.Resampling.BICUBIC, fillcolor=255)
        self.assertAlmostEqual(adjust.detect_skew(tilted), 4.5, delta=0.5)
        page.edits.turn = 1
        out = os.path.join(self.session.folder, 'test-scanner-turned.png')
        save_images([page], [out], 'png')
        with Image.open(out) as im:
            self.assertEqual(im.size, (page.height, page.width))

    def test_cli_turn_straighten_whiten(self):
        out = os.path.join(self.session.folder, 'cli-turned.pdf')
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--scan-to', out, '--device', 'test:0', '--dpi', '150',
                              '--mode', 'color', '--area', '0,0,0.5,0.25', '--rotate', '90',
                              '--straighten', '--whiten', '--sane-option',
                              'test-picture=Grid'], capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('turned 90', res.stdout)
        self.assertIn('already straight', res.stdout)       # the Grid is square on
        check_pdf(self, out, 1)
        (w, h), = pdf_page_sizes(out)
        self.assertGreater(h, w)            # 100 x 50 mm, turned: 50 wide, 100 tall
        self.assertAlmostEqual(w, 50 / 25.4 * 72, delta=2)

    def test_600_dpi(self):
        page = self.session.scan(self.caps, Request('test:0', 600, 'color',
                                                    (0, 0, .2, .2)))[0]
        self.assertEqual(page.dpi, 600)
        self.assertAlmostEqual(page.width, 40 / 25.4 * 600, delta=3)

    def test_preview(self):
        image = self.session.preview(self.caps)
        self.assertAlmostEqual(image.width, 200 / 25.4 * 75, delta=3)

    def test_feeder_empties_after_ten(self):
        got = []
        pages = self.session.scan(self.caps, Request('test:0', 50, 'gray', None, 'feeder'),
                                  on_page=got.append)
        self.assertEqual(len(pages), 10)
        self.assertEqual(len(got), 10)

    def test_device_errors(self):
        for status, kind in (('SANE_STATUS_JAMMED', 'jammed'),
                             ('SANE_STATUS_COVER_OPEN', 'cover_open'),
                             ('SANE_STATUS_DEVICE_BUSY', 'busy'),
                             ('SANE_STATUS_IO_ERROR', 'io'),
                             ('SANE_STATUS_NO_DOCS', 'no_docs')):
            req = Request('test:0', 50, 'gray', extra=[f'--read-return-value={status}'])
            with self.assertRaises(ScanError, msg=status) as ctx:
                self.session.scan(self.caps, req)
            self.assertEqual(ctx.exception.kind, kind, ctx.exception.detail)
        with self.assertRaises(ScanError) as ctx:
            scanner.query_caps('test:9')
        self.assertIn(ctx.exception.kind, ('open_failed', 'failed'))

    def test_cancel(self):
        req = Request('test:0', 300, 'color', None, 'glass',
                      extra=['--read-delay=yes', '--read-delay-duration=100000'])
        threading.Timer(1.5, self.session.cancel).start()
        started = time.monotonic()
        pages = self.session.scan(self.caps, req)
        self.assertEqual(pages, [])
        self.assertLess(time.monotonic() - started, scanner.CANCEL_GRACE + 4)
        self.assertEqual([n for n in os.listdir(self.session.folder) if n.endswith('.pnm')],
                         [])

    def test_cli_pdf(self):
        out = os.path.join(OUTPUT, 'sane.pdf')
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--scan-to', out, '--device', 'test:0', '--pages', '2',
                              '--dpi', '150', '--area', '0,0,0.5,0.5',
                              '--sane-option', 'test-picture=Grid'],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        check_pdf(self, out, 2)
        for w, h in pdf_page_sizes(out):
            self.assertAlmostEqual(w, 100 / 25.4 * 72, delta=1.5)    # 100 mm
            self.assertAlmostEqual(h, 100 / 25.4 * 72, delta=1.5)

    def test_cli_feeder_png(self):
        out = os.path.join(OUTPUT, 'feeder')
        os.makedirs(out, exist_ok=True)
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--scan-to', out, '--device', 'test:0', '--source', 'feeder',
                              '--dpi', '150', '--mode', 'bw', '--format', 'png'],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(len([n for n in os.listdir(out) if n.endswith('.png')]), 10)

    def test_self_test(self):
        res = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_scan.py'),
                              '--self-test', '--device', 'test:0'],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('scanner:   test:0', res.stdout)
        self.assertIn('device:    test:0: modes color, gray', res.stdout.replace(
            'gray, color', 'color, gray'))


# ─── Changing pages after the scan ────────────────────────────

class AdjustTests(unittest.TestCase):
    """Turning, straightening, brightness, contrast and Whiten paper (adjust.py, work.py)."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='spark-scan-adjust-')

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_straighten_known_angles(self):
        """Generated pages tilted by a known angle are measured within 0.5 degrees."""
        level = text_page()
        for skew in (-9.6, -6.0, -3.3, -1.2, -0.6, 0.8, 2.5, 4.4, 7.7, 10.0):
            tilted = level.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=236)
            got = adjust.detect_skew(tilted)
            self.assertIsNotNone(got, skew)
            self.assertAlmostEqual(got, -skew, delta=0.5, msg=f"tilted {skew}")
        self.assertEqual(adjust.detect_skew(level), 0.0)

    def test_straighten_every_mode_and_sideways(self):
        for mode, skew in (('color', 5.2), ('gray', -3.7), ('bw', 2.1)):
            got = adjust.detect_skew(text_page(skew, mode, seed=4))
            self.assertAlmostEqual(got, -skew, delta=0.5, msg=mode)
        # scanned sideways: the lines run down the page; the angle is the same
        sideways = text_page(-4.0, seed=5).transpose(Image.Transpose.ROTATE_90)
        self.assertAlmostEqual(adjust.detect_skew(sideways), 4.0, delta=0.5)
        # fewer, wider-spaced lines (a letter, not a dense page)
        sparse = text_page(6.0, spacing=200, seed=6)
        self.assertAlmostEqual(adjust.detect_skew(sparse), -6.0, delta=0.5)

    def test_straighten_page_through_its_view(self):
        """What the window does: measure on the screen-sized copy, apply to the full page,
        and the saved page measures straight."""
        page = make_page(self.folder, 'tilted', text_page(-6.4, 'color', seed=7), 300, 'color')
        work.make_view(page)
        angle = work.straighten(page)
        self.assertAlmostEqual(angle, 6.4, delta=0.5)
        self.assertTrue(page.edits.straighten)
        with page.open() as saved:
            self.assertEqual(saved.size, (2480, 3508))      # same size; corners white
            self.assertEqual(saved.getpixel((0, 0)), (255, 255, 255))
            self.assertAlmostEqual(adjust.detect_skew(saved) or 0.0, 0.0, delta=0.5)
        work.straighten(page, False)
        self.assertFalse(page.edits.any())
        with page.open() as raw:
            self.assertAlmostEqual(adjust.detect_skew(raw), 6.4, delta=0.5)

    def test_straighten_a_grid(self):
        """SANE's test scanner draws a 10 mm checkerboard. Row by row its ink is the same at
        every angle, so straightening goes by its edges."""
        for dpi in (75, 150, 300):
            square = 10 / 25.4 * dpi
            grid = Image.new('L', (round(100 / 25.4 * dpi), round(120 / 25.4 * dpi)), 255)
            draw = ImageDraw.Draw(grid)
            for row in range(12):
                for col in range(10):
                    if (row + col) % 2 == 0:
                        draw.rectangle((col * square, row * square, (col + 1) * square - 1,
                                        (row + 1) * square - 1), fill=0)
            self.assertEqual(adjust.detect_skew(grid), 0.0, dpi)
            tilted = grid.rotate(4.5, resample=Image.Resampling.BICUBIC, fillcolor=255)
            self.assertAlmostEqual(adjust.detect_skew(tilted), -4.5, delta=0.5, msg=dpi)

    def test_nothing_to_straighten_by(self):
        blank = Image.new('L', (1240, 1754), 240)
        self.assertIsNone(adjust.detect_skew(blank))
        self.assertIsNone(adjust.detect_skew(Image.effect_noise((1240, 1754), 60)))
        page = make_page(self.folder, 'blank', blank, 150, 'gray')
        self.assertIsNone(work.straighten(page))
        self.assertTrue(page.measured)
        self.assertFalse(page.edits.any())          # left as it is

    def test_turns(self):
        image = Image.new('RGB', (300, 200), 'white')
        image.paste((0, 0, 0), (0, 0, 30, 30))       # a mark in the top-left corner
        page = make_page(self.folder, 'mark', image, 100, 'color')
        for turn, corner in ((1, (195, 5)), (2, (294, 194)), (3, (5, 294))):
            page.edits = Edits(turn=turn)
            with page.open() as turned:
                self.assertEqual(turned.size, (200, 300) if turn % 2 else (300, 200))
                self.assertEqual(page.size, turned.size)
                self.assertEqual(turned.getpixel(corner), (0, 0, 0), f"turn {turn}")
        page.edits = Edits(turn=1)           # right: the top-left corner goes top-right
        with page.open() as turned:
            self.assertEqual(turned.getpixel((195, 5)), (0, 0, 0))
            self.assertEqual(turned.getpixel((5, 5)), (255, 255, 255))
        w_mm, h_mm = page.size_mm
        self.assertGreater(h_mm, w_mm)
        # black and white pages turn and straighten and stay black and white
        bw = make_page(self.folder, 'bw', text_page(3.0, 'bw', (1240, 1754), font_size=21,
                                                    spacing=35), 150, 'bw')
        work.straighten(bw)
        bw.edits.turn = 2
        with bw.open() as im:
            self.assertEqual(im.mode, '1')
            self.assertEqual(im.size, (1240, 1754))

    def test_unchanged_page_is_the_scan(self):
        image = text_page(size=(620, 877), font_size=11, spacing=18)
        page = make_page(self.folder, 'plain', image, 75, 'gray')
        with page.open() as im:
            self.assertEqual(im.tobytes(), image.tobytes())

    def test_brightness_contrast_whiten(self):
        image = text_page(0, 'color', (1240, 1754), font_size=21, spacing=35)
        page = make_page(self.folder, 'tone', image, 150, 'color')
        paper = image.getpixel((5, 5))
        self.assertLess(paper[2], 210)                       # yellowish
        page.edits = Edits(brightness=40)
        with page.open() as im:
            self.assertGreater(im.convert('L').getpixel((600, 2)), 236)
        page.edits = Edits(brightness=-40)
        with page.open() as im:
            self.assertLess(im.convert('L').getpixel((5, 5)), 200)
        page.edits = Edits(contrast=60)
        with page.open() as im:
            lo, hi = im.convert('L').getextrema()
            self.assertEqual((lo, hi), (0, 255))
        page.edits = Edits()
        work.make_view(page)
        work.whiten(page)
        self.assertIsNotNone(page.edits.levels)
        with page.open() as im:
            self.assertEqual(im.getpixel((5, 5)), (255, 255, 255))   # paper white
            ink = im.convert('L').getextrema()[0]
            self.assertLess(ink, 20)                                 # ink dark
        work.whiten(page, False)
        self.assertFalse(page.edits.any())
        # black and white pages have no tone
        bw = make_page(self.folder, 'bwt', Image.new('1', (100, 100), 1), 100, 'bw')
        work.whiten(bw)
        self.assertIsNone(bw.edits.levels)

    def test_live_view_under_100_ms(self):
        """Moving a slider, or turning or straightening a 300 dpi A4 page, redraws the view
        from its screen-sized copy in under 100 ms."""
        page = make_page(self.folder, 'a4', text_page(4.0, 'color'), 300, 'color')
        work.make_view(page)
        view = work.view_image(page)
        work.straighten(page)
        work.whiten(page)
        page.edits.turn, page.edits.brightness, page.edits.contrast = 1, 15, 20
        box = (900, 900)
        times = []
        for _ in range(5):
            started = time.perf_counter()
            shown = adjust.preview(view, page.edits, box)
            times.append(time.perf_counter() - started)
        fitted = adjust.fit(adjust.apply_geometry(view, page.edits, fast=True), box)
        tones = []
        for value in range(-50, 51, 20):
            page.edits.brightness = value
            started = time.perf_counter()
            adjust.apply_tone(fitted, page.edits)
            tones.append(time.perf_counter() - started)
        full_started = time.perf_counter()
        with page.open():
            pass
        full = time.perf_counter() - full_started
        print(f"\n  view redraw {min(times) * 1000:.0f}-{max(times) * 1000:.0f} ms, slider "
              f"{max(tones) * 1000:.1f} ms, whole page for saving {full * 1000:.0f} ms",
              file=sys.stderr)
        self.assertEqual(max(shown.size), 900)
        self.assertLess(sorted(times)[2], 0.100)
        self.assertLess(max(tones), 0.100)

    def test_saved_with_edits(self):
        tall = make_page(self.folder, 'tall', Image.new('RGB', (850, 1100), '#d8d2c0'), 100,
                         'color')
        wide = make_page(self.folder, 'wide', Image.new('L', (850, 1100), 200), 100, 'gray')
        wide.edits.turn = 3
        out = os.path.join(self.folder, 'edited.pdf')
        save_pdf([tall, wide], out)
        check_pdf(self, out, 2)
        self.assertEqual(pdf_page_sizes(out), [(612.0, 792.0), (792.0, 612.0)])
        paths = [os.path.join(self.folder, f'edited-{i}.png') for i in (1, 2)]
        save_images([tall, wide], paths, 'png')
        with Image.open(paths[1]) as im:
            self.assertEqual(im.size, (1100, 850))
        save_images([wide], [os.path.join(self.folder, 'edited.jpg')], 'jpg')
        with Image.open(os.path.join(self.folder, 'edited.jpg')) as im:
            self.assertEqual(im.size, (1100, 850))


class LanguageTests(unittest.TestCase):
    """French for a French desktop, SPARK_LANG to choose."""

    def run_t(self, env, key):
        clean = {k: v for k, v in os.environ.items()
                 if k not in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE', 'SPARK_LANG')}
        clean.update(env)
        out = subprocess.run([sys.executable, '-c', 'import sys; from sparkscan.text import t;'
                              f' sys.stdout.buffer.write(t({key!r}).encode("utf-8"))'],
                             cwd=APP_DIR, env=clean, capture_output=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.decode('utf-8')

    def test_language(self):
        saved = {k: os.environ.get(k) for k in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'SPARK_LANG')}
        try:
            for env, want in (({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'fr_FR'}, 'fr'),
                              ({'LANG': 'fr'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                              ({'LANG': 'de_DE.UTF-8'}, 'en'), ({}, 'en'),
                              ({'LC_ALL': 'C', 'LANG': 'fr_CA.UTF-8'}, 'en'),
                              ({'LC_MESSAGES': 'fr_CA.UTF-8', 'LANG': 'en_US'}, 'fr'),
                              ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                              ({'LANG': 'en_US.UTF-8', 'SPARK_LANG': 'fr'}, 'fr'),
                              ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'xx'}, 'fr')):
                for k in saved:
                    os.environ.pop(k, None)
                os.environ.update(env)
                self.assertEqual(text.language(), want, env)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_window_text_follows_the_desktop(self):
        self.assertEqual(self.run_t({'LANG': 'fr_CA.UTF-8'}, 'edit.straighten'), "Redresser")
        self.assertEqual(self.run_t({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'},
                                    'edit.straighten'), "Straighten")
        self.assertEqual(self.run_t({'LANG': 'C.UTF-8', 'SPARK_LANG': 'fr'}, 'edit.whiten'),
                         "Blanchir le fond")

    def test_french_is_complete(self):
        """Every sentence has its French, with the same blanks; only words that are the
        same in both languages are left alone. Quebec usage: numériseur, not scanner; vous."""
        same = {'label.source', 'label.pages', 'area.part', 'pages.count', 'pages.one',
                'scanner.usb', 'file.page'}
        for key, en in text.EN.items():
            fr = text.FR[key]
            if key not in same:
                self.assertNotEqual(fr, en, f"{key} is not translated")
            self.assertNotRegex(fr.lower(), r'\bscanner\b', key)
            self.assertNotRegex(fr.lower(), r'\b(tu|ton|ta|tes)\b', key)
        self.assertEqual(text.decimal(3.25), '3.2' if text._T is text.EN else '3,2')


# ─── Searchable PDF ───────────────────────────────────────────

def ocr_ready():
    tess = core.Tesseract()
    return tess.found and 'eng' in tess.languages() and shutil.which('pdftotext')


@unittest.skipUnless(ocr_ready(), "needs tesseract with English, and pdftotext")
class OcrTests(unittest.TestCase):
    def test_searchable_pdf(self):
        folder = tempfile.mkdtemp(prefix='spark-scan-ocr-')
        try:
            pages = []
            for i, (words, mode) in enumerate((("SPARK SCAN WORKS", 'color'),
                                               ("SECOND PAGE HERE", 'bw'))):
                image = Image.new('RGB', (2480, 1200), 'white')
                font = ImageFont.load_default(size=110)
                ImageDraw.Draw(image).text((150, 400), words, fill='black', font=font)
                if mode == 'bw':
                    image = image.convert('1')
                pages.append(make_page(folder, f'p{i}', image, 300, mode))
            out = os.path.join(OUTPUT, 'searchable.pdf')
            tess = core.Tesseract()
            lang = 'eng+fra' if 'fra' in tess.languages() else 'eng'
            document.save_ocr_pdf(pages, out, lang, tess, folder)
            self.assertTrue(os.path.isfile(out))
            info = subprocess.run(['pdfinfo', out], capture_output=True, text=True).stdout
            self.assertRegex(info, r'(?m)^Pages:\s+2$')
            found = subprocess.run(['pdftotext', out, '-'], capture_output=True,
                                   text=True).stdout
            self.assertIn('SPARK SCAN WORKS', found)
            self.assertIn('SECOND PAGE', found)
            self.assertEqual([n for n in os.listdir(folder) if n.startswith('ocr-')], [])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_straightened_page_is_read(self):
        """A page scanned 7 degrees off and straightened: tesseract gets the straightened
        page, and reads it."""
        folder = tempfile.mkdtemp(prefix='spark-scan-ocr-')
        try:
            lines = ["INVOICE NUMBER 4471", "PAID IN FULL ON NOVEMBER 20",
                     "SPARK SCAN STRAIGHTENS PAGES"] * 4
            image = text_page(7.0, 'color', font_size=80, spacing=180, words=lines)
            page = make_page(folder, 'tilted', image, 300, 'color')
            work.make_view(page)
            self.assertAlmostEqual(work.straighten(page), -7.0, delta=0.5)
            work.whiten(page)
            with page.open() as fed:
                self.assertAlmostEqual(adjust.detect_skew(fed) or 0.0, 0.0, delta=0.5)
            out = os.path.join(folder, 'straightened.pdf')
            tess = core.Tesseract()
            document.save_ocr_pdf([page], out, 'eng', tess, folder)
            found = subprocess.run(['pdftotext', out, '-'], capture_output=True,
                                   text=True).stdout
            self.assertIn('INVOICE NUMBER 4471', found)
            self.assertIn('PAID IN FULL', found)
            self.assertIn('STRAIGHTENS PAGES', found)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


# ─── The window ───────────────────────────────────────────────

def have_display():
    if os.name == 'nt':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


@unittest.skipUnless(have_display(), "needs a display (xvfb-run)")
class WindowTests(unittest.TestCase):
    def setUp(self):
        os.environ['SPARK_SCAN_SCANIMAGE'] = FAKE
        for var in ('FAKE_ERROR', 'FAKE_DELAY', 'FAKE_SCANNERS', 'FAKE_CRASH'):
            os.environ.pop(var, None)
        os.environ['FAKE_FEEDER_PAGES'] = '3'
        for name in os.listdir(OUTPUT):
            path = os.path.join(OUTPUT, name)
            if os.path.isfile(path) and name.startswith('Scan'):
                os.remove(path)
        from sparkscan.app import App
        started = time.monotonic()
        self.app = App()
        self.app.root.update()
        self.first_paint = time.monotonic() - started

    def tearDown(self):
        try:
            self.app.dirty = False
            self.app.close()
        except Exception:      # noqa: BLE001 - already closed
            pass
        # collect the closed window here, on the Tk thread, not in some later worker thread
        gc.collect()
        os.environ.pop('SPARK_SCAN_SCANIMAGE', None)

    def wait(self, cond, timeout=30.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.root.update()
            if cond():
                return
            time.sleep(0.02)
        self.fail("timed out waiting")

    def ready(self):
        self.wait(lambda: self.app.current_caps() is not None and not self.app.listing)

    def test_opens_fast(self):
        print(f"\n  first paint: {self.first_paint * 1000:.0f} ms", file=sys.stderr)
        self.assertLess(self.first_paint, 3.0)
        self.ready()
        self.assertEqual(self.app.device, 'fake:0')
        self.assertIn('Fake Flatbed 3000', self.app.device_button.cget('text'))
        self.assertIsNotNone(self.app.source_switch)       # glass and feeder offered

    def test_preview_crop_scan_save(self):
        app = self.app
        self.ready()
        app.start_preview()
        self.wait(lambda: app.preview is not None and not app.busy)
        app.root.update()
        x0, y0, w, h = app._img_box
        self.assertGreater(w, 50)
        app._press(Ev(x0 + 2, y0 + 2))
        app._motion(Ev(x0 + w // 2, y0 + h // 2))
        app._release(Ev(x0 + w // 2, y0 + h // 2))
        self.assertIsNotNone(app.crop)
        self.assertAlmostEqual(app.crop[2], 0.5, delta=0.02)
        self.assertIn('×', app.area_label.cget('text'))
        # move the crop by dragging inside it
        app._press(Ev(x0 + w // 4, y0 + h // 4))
        app._motion(Ev(x0 + w // 4 + 10, y0 + h // 4))
        app._release(Ev(x0 + w // 4 + 10, y0 + h // 4))
        self.assertGreater(app.crop[0], 0.0)
        app._set_dpi('150')
        app.start_scan()
        self.wait(lambda: len(app.pages) == 1 and not app.busy)
        page = app.pages[0]
        self.assertAlmostEqual(page.width, (app.crop[2] - app.crop[0]) * 216.07 / 25.4 * 150,
                               delta=3)
        self.assertEqual(app.showing, 'page')
        self.assertTrue(app.dirty)

        # the feeder: crop doesn't apply, three sheets
        app._set_source('feeder')
        self.assertFalse(app.preview_button.enabled)
        app.start_scan()
        self.wait(lambda: len(app.pages) == 4 and not app.busy)
        self.assertIn('4', app.pages_label.cget('text'))

        # reorder and delete
        first, last = app.pages[0], app.pages[3]
        app.select_page(0)
        app.move_page(1)
        self.assertIs(app.pages[1], first)
        app.select_page(3)
        app.delete_page()
        self.assertEqual(len(app.pages), 3)
        self.assertNotIn(last, app.pages)
        self.assertFalse(os.path.exists(last.path))

        # save one PDF
        app._set_format('pdf')
        app.start_save()
        self.wait(lambda: not app.busy and app.last_saved)
        self.assertFalse(app.dirty)
        saved = app.last_saved
        self.assertTrue(os.path.basename(saved).startswith('Scan '))
        check_pdf(self, saved, 3)
        # and one PNG per page
        app._set_format('png')
        app.last_saved = None
        app.start_save()
        self.wait(lambda: not app.busy and app.last_saved)
        self.assertEqual(len([n for n in os.listdir(OUTPUT) if n.endswith('.png')]), 3)

    def test_page_edits(self):
        """Turn, straighten, whiten, brightness and contrast on a scanned page, rotate all,
        then save: the PDF has the edits."""
        app = self.app
        self.ready()
        app._set_dpi('150')
        app.start_scan()
        self.wait(lambda: len(app.pages) == 1 and not app.busy)
        page = app.pages[0]
        self.assertTrue(app.edit_bar.winfo_ismapped())
        w, h = page.size
        thumb = app.thumbs[page.path]
        app.turn(1)
        self.assertEqual(page.size, (h, w))
        self.assertIsNot(app.thumbs[page.path], thumb)          # thumbnail redrawn
        self.assertIn(f"{round(page.size_mm[0])} ×", app.caption.cget('text'))
        app.turn(-1)
        app.turn(2)
        self.assertEqual(page.edits.turn, 2)

        # brightness: the view follows the slider in well under 100 ms
        slider = app.sliders['brightness']
        before = app._scaled.convert('L').getpixel((app._scaled.width // 2, 2))
        times = []
        for value in (10, 25, 40, -20, 30):
            started = time.perf_counter()
            slider.set(value, fire=True)
            app.root.update_idletasks()
            times.append(time.perf_counter() - started)
        print(f"\n  slider redraw: {max(times) * 1000:.1f} ms at most", file=sys.stderr)
        self.assertLess(max(times), 0.100)
        self.assertEqual(page.edits.brightness, 30)
        self.assertGreaterEqual(app._scaled.convert('L').getpixel((app._scaled.width // 2, 2)),
                                before)
        app.sliders['contrast'].set(20, fire=True)
        self.assertEqual(page.edits.contrast, 20)

        app.whiten_toggle.set(True, fire=True)
        self.assertIsNotNone(page.edits.levels)
        app.straighten_toggle.set(True, fire=True)
        self.wait(lambda: page.measured and not app._measuring)
        self.assertTrue(app.straighten_new and app.whiten_new)
        self.assertNotEqual(app.edit_note.cget('text'), text.t('edit.measuring'))

        # new pages get Straighten and Whiten paper too
        app.start_scan()
        self.wait(lambda: len(app.pages) == 2 and not app.busy)
        second = app.pages[1]
        self.assertTrue(second.measured)
        self.assertIsNotNone(second.edits.levels)
        self.assertTrue(app.whiten_toggle.value)

        # reset brings the shown page back to the scan
        app.reset_edits()
        self.assertFalse(second.edits.any())
        app.whiten_toggle.set(False, fire=True)
        app.straighten_toggle.set(False, fire=True)

        # rotate all: every page a quarter turn right
        app.turn_all()
        self.assertEqual([p.edits.turn for p in app.pages], [3, 1])
        self.assertIn(text.pages_word(2), app.message.cget('text'))

        app._set_format('pdf')
        app.start_save()
        self.wait(lambda: not app.busy and app.last_saved)
        check_pdf(self, app.last_saved, 2)
        sizes = pdf_page_sizes(app.last_saved)
        self.assertTrue(all(ph > pw for pw, ph in sizes) or all(pw > ph for pw, ph in sizes),
                        sizes)
        self.assertEqual(sizes[0], sizes[1])
        self.assertAlmostEqual(sizes[0][0], page.size[0] / page.dpi * 72, delta=1)
        self.assertAlmostEqual(sizes[1][1], second.size[1] / second.dpi * 72, delta=1)
        # the settings remember the toggles
        self.assertIs(app._settings()['straighten'], False)

    def test_error_and_cancel(self):
        app = self.app
        self.ready()
        os.environ['FAKE_ERROR'] = 'jammed'
        app.start_scan()
        self.wait(lambda: not app.busy)
        self.assertEqual(app.pages, [])
        self.assertIn(text.t('error.jammed'), app.message.cget('text'))
        os.environ.pop('FAKE_ERROR')
        os.environ['FAKE_DELAY'] = '0.3'
        app.start_scan()
        self.wait(lambda: app.busy == 'scan')
        app.root.after(500, app.cancel)
        self.wait(lambda: not app.busy, timeout=15)
        self.assertEqual(app.pages, [])
        self.assertEqual(app.message.cget('text'), text.t('done.cancelled'))
        self.assertTrue(app.scan_button.enabled)

    def test_no_scanner(self):
        self.app.dirty = False
        self.app.close()
        gc.collect()          # see tearDown
        os.environ['FAKE_SCANNERS'] = '0'
        from sparkscan import core as c
        c.save_config({})
        from sparkscan.app import App
        self.app = App()
        self.wait(lambda: not self.app.listing and self.app._threads == 0)
        self.assertIn(text.t('scanner.none')[:20], self.app.device_note.cget('text'))
        self.assertFalse(self.app.scan_button.enabled)


if __name__ == '__main__':
    unittest.main()
