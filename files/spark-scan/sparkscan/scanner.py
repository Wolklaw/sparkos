"""SANE, through its scanimage program (sane-backends; in the SparkOS image). python-sane
isn't in the image, and scanimage is what every backend is tested with, so Spark Scan runs it:

  scanimage -f …        lists scanners (USB, and network ones through airscan and pixma)
  scanimage -d DEV -A   lists what that scanner offers: modes, resolutions, glass size, sources
  scanimage -d DEV …    scans one page to a PNM file (--batch for every sheet in the feeder)

Nothing here touches Tk: the app runs a Job in a thread and reads its progress."""

import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image

from .core import NO_WINDOW, log

LIST_TIMEOUT = 40        # network discovery (airscan, pixma) can take a while
OPTIONS_TIMEOUT = 40
CANCEL_GRACE = 6.0       # scanimage gets SIGTERM (it then cancels the scan), then SIGKILL

Area = Tuple[float, float, float, float]       # x0, y0, x1, y1 as fractions of the glass


class ScanError(Exception):
    """A scan that failed. .kind is one of the KINDS below, for a plain message."""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


# what scanimage's stderr says -> a kind the interface has a sentence for
KINDS = (
    ('no_docs', ('out of documents', 'no more documents', 'feeder empty', 'NO_DOCS')),
    ('jammed', ('jammed', 'JAMMED')),
    ('cover_open', ('cover is open', 'cover open', 'COVER_OPEN')),
    ('busy', ('device busy', 'DEVICE_BUSY')),
    ('denied', ('access to resource has been denied', 'ACCESS_DENIED')),
    ('open_failed', ('open of device',)),
    ('io', ('error during device i/o', 'IO_ERROR')),
    ('no_mem', ('out of memory', 'NO_MEM')),
)


def classify_error(stderr: str) -> str:
    low = stderr.lower()
    for kind, needles in KINDS:
        if any(n.lower() in low for n in needles):
            return kind
    return 'failed'


def last_error_line(stderr: str) -> str:
    lines = [ln.strip() for ln in re.split(r'[\r\n]+', stderr)
             if ln.strip() and not ln.strip().startswith(('Progress:', 'Scanning page',
                                                          'Output format', 'Scanned page',
                                                          'Batch terminated'))]
    return lines[-1] if lines else ''


def exit_reason(code: int, stderr: str) -> str:
    """Why scanimage stopped, in one line: its own 'scanimage: …' message if it gave one,
    else the first thing it printed (a crash in a backend prints its cause first)."""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    own = [ln for ln in lines if ln.startswith('scanimage:')]
    why = own[-1] if own else (lines[0] if lines else '')
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"signal {-code}"
        return f"scanimage crashed ({name})" + (f": {why}" if why else '')
    return why or f"scanimage exited with {code}"


def scanimage() -> Optional[List[str]]:
    """The scanimage command. SPARK_SCAN_SCANIMAGE replaces it (the tests' fake scanner)."""
    forced = os.environ.get('SPARK_SCAN_SCANIMAGE')
    if forced:
        if os.name == 'nt':                    # keep backslashes; drop the quotes
            return [part.strip('"') for part in shlex.split(forced, posix=False)]
        return shlex.split(forced)
    found = shutil.which('scanimage')
    return [found] if found else None


def scanimage_version() -> str:
    cmd = scanimage()
    if not cmd:
        return ''
    try:
        out = subprocess.run(cmd + ['--version'], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
        match = re.search(r'sane-backends\)?\s*([\d.]+)', out)
        return match.group(1) if match else out.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


# ─── Scanners ─────────────────────────────────────────────────

@dataclass
class Device:
    name: str                  # what scanimage -d takes: 'pixma:…', 'airscan:e0:…', 'test:0'
    vendor: str = ''
    model: str = ''
    kind: str = ''             # 'flatbed scanner', 'eSCL network scanner', …

    @property
    def backend(self) -> str:
        return self.name.split(':', 1)[0]

    @property
    def label(self) -> str:
        text = ' '.join(p for p in (self.vendor, self.model) if p and p.lower() != 'noname')
        if self.model and self.vendor and self.model.lower().startswith(self.vendor.lower()):
            text = self.model                     # airscan: vendor 'Canon', model 'Canon TR…'
        return text or self.name


LIST_FORMAT = '%d\t%v\t%m\t%t%n'


def parse_devices(text: str) -> List[Device]:
    found, seen = [], set()
    for line in text.splitlines():
        parts = line.split('\t')
        if len(parts) < 4 or not parts[0].strip() or parts[0] in seen:
            continue
        seen.add(parts[0])
        found.append(Device(parts[0].strip(), parts[1].strip(), parts[2].strip(),
                            parts[3].strip()))
    return found


def list_devices(timeout: float = LIST_TIMEOUT) -> List[Device]:
    """Every scanner SANE finds. Raises ScanError('no_scanimage') if SANE isn't installed."""
    cmd = scanimage()
    if not cmd:
        raise ScanError('no_scanimage')
    try:
        out = subprocess.run(cmd + ['-f', LIST_FORMAT], capture_output=True, text=True,
                             timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ScanError('list_timeout') from exc
    except OSError as exc:
        raise ScanError('failed', str(exc)) from exc
    devices = parse_devices(out.stdout)
    if not devices and out.returncode != 0:
        # e.g. a backend that needs D-Bus crashing scanimage; say so rather than "none found"
        log.warning("scanimage -f exited %s: %s", out.returncode, out.stderr[-600:])
        raise ScanError('list_failed', exit_reason(out.returncode, out.stderr))
    log.info("scanners: %s", ', '.join(d.name for d in devices) or 'none')
    return devices


# ─── What a scanner offers ────────────────────────────────────

@dataclass
class Option:
    name: str                          # 'mode', 'resolution', 'l', 'x', 'source', …
    values: List[str] = field(default_factory=list)       # a list constraint
    low: Optional[float] = None                           # a range constraint
    high: Optional[float] = None
    unit: str = ''
    default: str = ''
    inactive: bool = False

    def numbers(self) -> List[float]:
        out = []
        for v in self.values:
            try:
                out.append(float(v))
            except ValueError:
                pass
        return out


_OPTION = re.compile(r'^\s{2,}(-{1,2}[A-Za-z][\w-]*)(\[=\(.*?\)\])?(?:\s+(.*?))?\s*'
                     r'\[([^\]]*)\]\s*$')
_RANGE = re.compile(r'^(-?[\d.]+)\.\.(-?[\d.]+)([a-z%]*)(?:,\.\.\.)?(?: \(in steps of [\d.]+\))?$')
UNITS = ('dpi', 'mm', 'pel', 'bit', 'us', '%')


def parse_options(text: str) -> Dict[str, Option]:
    """scanimage -A output -> {name: Option}. Lines look like
         --mode Lineart|Gray|Color [Color]
         --resolution 75|150|300|600|1200dpi [75]
         --resolution 1..1200dpi (in steps of 1) [50]
         -x 0..215.9mm [215.9]"""
    options: Dict[str, Option] = {}
    for line in text.splitlines():
        m = _OPTION.match(line)
        if not m:
            continue
        name = m.group(1).lstrip('-')
        constraint = (m.group(3) or '').strip()
        default = m.group(4).strip()
        opt = Option(name, default=default, inactive=default == 'inactive')
        if m.group(2):                                  # a yes/no switch
            opt.values = m.group(2)[3:-2].split('|')
        elif constraint and not constraint.startswith('<'):
            if constraint.startswith('auto|'):           # the backend can also choose
                constraint = constraint[5:]
            r = _RANGE.match(constraint)
            if r:
                opt.low, opt.high, opt.unit = float(r.group(1)), float(r.group(2)), r.group(3)
            else:
                values = constraint.split('|')
                for unit in UNITS:                       # '75|150|300dpi'
                    if values[-1].endswith(unit) and re.match(r'^-?[\d.]+$',
                                                              values[-1][:-len(unit)]):
                        values[-1], opt.unit = values[-1][:-len(unit)], unit
                        break
                opt.values = values
        options[name] = opt
    return options


MODE_WORDS = {
    'color': ('color', 'colour', 'rgb', '24bit color', 'true gray'),
    'gray': ('gray', 'grey', 'grayscale', 'greyscale', '8bit gray', 'gray8'),
    'lineart': ('lineart', 'binary', 'black & white', 'black and white', 'monochrome'),
}


@dataclass
class Caps:
    """What one scanner offers, from parse_options, in the terms the app uses."""
    device: str
    modes: Dict[str, str] = field(default_factory=dict)     # 'color' -> 'Color'
    resolutions: List[int] = field(default_factory=list)    # a list, or …
    res_range: Optional[Tuple[float, float]] = None         # … a range
    area: Optional[Dict[str, Tuple[float, float]]] = None   # 'l','t','x','y' -> (low, high)
    area_unit: str = 'mm'
    sources: Dict[str, str] = field(default_factory=dict)   # 'glass'/'feeder'/'duplex' -> name
    source_default: str = ''
    depth8: bool = False                                     # pass --depth 8

    @classmethod
    def from_options(cls, device: str, options: Dict[str, Option]) -> 'Caps':
        caps = cls(device)
        mode = options.get('mode')
        if mode and mode.values:
            for value in mode.values:
                low = value.strip().lower()
                for ours, words in MODE_WORDS.items():
                    if low in words and ours not in caps.modes:
                        caps.modes[ours] = value
        res = options.get('resolution')
        if res:
            if res.values:
                caps.resolutions = sorted({int(round(n)) for n in res.numbers() if n > 0})
            elif res.low is not None and res.high is not None:
                caps.res_range = (res.low, res.high)
        if all(k in options and options[k].low is not None for k in 'ltxy'):
            caps.area = {k: (options[k].low, options[k].high) for k in 'ltxy'}   # type: ignore
            caps.area_unit = options['x'].unit or 'mm'
        src = options.get('source')
        if src and src.values and not src.inactive:
            for value in src.values:
                kind = source_kind(value)
                if kind and kind not in caps.sources:
                    caps.sources[kind] = value
            caps.source_default = source_kind(src.default) or ''
        depth = options.get('depth')
        if depth and not depth.inactive and '8' in depth.values and depth.default != '8':
            caps.depth8 = True
        return caps

    def resolution(self, wanted: float) -> float:
        """The scanner's resolution nearest to the one asked for."""
        if self.resolutions:
            return min(self.resolutions, key=lambda r: (abs(r - wanted), -r))
        if self.res_range:
            return max(self.res_range[0], min(self.res_range[1], wanted))
        return wanted

    def preview_resolution(self, wanted: float) -> float:
        """Low and quick, but no lower than the scanner goes."""
        if self.resolutions:
            above = [r for r in self.resolutions if r >= wanted]
            return min(above) if above else max(self.resolutions)
        return self.resolution(wanted)

    def device_mode(self, mode: str) -> Optional[str]:
        """What to ask the scanner for. Black and white is scanned in grey and turned into
        black and white here, so it looks the same on every scanner."""
        order = {'color': ('color', 'gray'), 'gray': ('gray', 'color'),
                 'bw': ('gray', 'color', 'lineart')}[mode]
        for ours in order:
            if ours in self.modes:
                return self.modes[ours]
        return None

    def crops_on_scanner(self) -> bool:
        return self.area is not None


def source_kind(name: str) -> Optional[str]:
    low = name.lower()
    if any(w in low for w in ('flatbed', 'platen', 'glass', 'normal')):
        return 'glass'
    if any(w in low for w in ('adf', 'feeder', 'document')):
        return 'duplex' if any(w in low for w in ('duplex', 'both', 'back')) else 'feeder'
    return None


def query_caps(device: str, timeout: float = OPTIONS_TIMEOUT) -> Caps:
    cmd = scanimage()
    if not cmd:
        raise ScanError('no_scanimage')
    try:
        out = subprocess.run(cmd + ['-d', device, '-A'], capture_output=True, text=True,
                             timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ScanError('options_timeout') from exc
    except OSError as exc:
        raise ScanError('failed', str(exc)) from exc
    options = parse_options(out.stdout)
    if not options:
        raise ScanError(classify_error(out.stderr), last_error_line(out.stderr))
    caps = Caps.from_options(device, options)
    log.info("%s: modes %s, resolutions %s, area %s %s, sources %s", device,
             caps.modes, caps.resolutions or caps.res_range, caps.area, caps.area_unit,
             caps.sources)
    return caps


# ─── One scan ─────────────────────────────────────────────────

@dataclass
class Request:
    device: str
    dpi: float                      # what the scanner will be asked for
    mode: str                       # ours: 'color', 'gray', 'bw'
    area: Optional[Area] = None     # fractions of the glass; None = all of it
    source: str = ''                # ours: 'glass', 'feeder', 'duplex'; '' = don't set
    extra: Sequence[str] = ()       # more scanimage arguments (--sane-option, tests)


def area_args(caps: Caps, area: Optional[Area]) -> List[str]:
    """-l -t -x -y for the part of the glass to scan (scanimage's -x and -y are the width and
    height of the area, up to the glass size)."""
    if not caps.area:
        return []
    (l0, l1), (t0, t1) = caps.area['l'], caps.area['t']
    width, height = caps.area['x'][1], caps.area['y'][1]
    a = area or (0.0, 0.0, 1.0, 1.0)
    left, top = min(l1, l0 + a[0] * width), min(t1, t0 + a[1] * height)
    w = min(width, max(1.0, (a[2] - a[0]) * width))
    h = min(height, max(1.0, (a[3] - a[1]) * height))
    if caps.area_unit == 'pel':
        def fmt(v: float) -> str:
            return str(int(round(v)))
    else:
        def fmt(v: float) -> str:
            return f"{v:.2f}".rstrip('0').rstrip('.')
    return ['-l', fmt(left), '-t', fmt(top), '-x', fmt(w), '-y', fmt(h)]


def command(caps: Caps, req: Request, out: Optional[str] = None,
            batch: Optional[str] = None) -> List[str]:
    """The scanimage command line for one request. out: -o file; batch: --batch pattern."""
    cmd = (scanimage() or ['scanimage']) + ['-d', req.device, '--format=pnm', '-p']
    mode = caps.device_mode(req.mode)
    if mode:
        cmd += ['--mode', mode]
    if caps.depth8:
        cmd += ['--depth', '8']
    if caps.resolutions or caps.res_range:
        res = caps.resolution(req.dpi)
        cmd += ['--resolution', f"{res:g}"]
    if req.source and req.source in caps.sources:
        cmd += ['--source', caps.sources[req.source]]
    if req.source in ('', 'glass'):
        cmd += area_args(caps, req.area)
    cmd += list(req.extra)
    if batch:
        cmd += [f'--batch={batch}', '--batch-print']
    elif out:
        cmd += ['-o', out]
    return cmd


def otsu(gray: Image.Image) -> int:
    """The grey level that best splits ink from paper (Otsu's method)."""
    hist = gray.histogram()[:256]
    total = sum(hist)
    if not total:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w_b, sum_b = -1.0, 128, 0, 0.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def to_black_and_white(image: Image.Image) -> Image.Image:
    gray = image.convert('L')
    # a page of only paper (or only ink) has no real split; keep the threshold sensible
    level = max(90, min(200, otsu(gray)))
    return gray.point(lambda v: 255 if v > level else 0, mode='1')


def finish_page(raw: str, req: Request, caps: Caps, dest_stem: str) -> Tuple[str, int, int]:
    """Turn scanimage's PNM into the page we keep: black and white made here, the crop done
    here if the scanner can't crop. Returns (path, width, height). When nothing needs
    changing the PNM is kept as it is (only its header is read), so a 600 dpi page isn't
    decoded and encoded again."""
    soft_crop = bool(req.area and not caps.crops_on_scanner() and req.source in ('', 'glass'))
    with Image.open(raw) as im:
        mode, (width, height) = im.mode, im.size
    convert = (req.mode == 'bw' or (req.mode == 'gray' and mode not in ('L', '1'))
               or (req.mode == 'color' and mode == '1'))
    if not convert and not soft_crop:
        path = dest_stem + '.pnm'
        os.replace(raw, path)
        return path, width, height
    with open(raw, 'rb') as f:              # not mapped, so the file can be removed after
        image = Image.open(f)
        image.load()
    if req.mode == 'bw':
        image = to_black_and_white(image)
    elif req.mode == 'gray' and image.mode not in ('L', '1'):
        image = image.convert('L')
    elif req.mode == 'color' and image.mode == '1':
        image = image.convert('L')
    if soft_crop and req.area:
        x0, y0, x1, y1 = req.area
        w, h = image.size
        image = image.crop((int(x0 * w), int(y0 * h), max(int(x0 * w) + 1, int(x1 * w)),
                            max(int(y0 * h) + 1, int(y1 * h))))
    width, height = image.size
    path = dest_stem + ('.png' if image.mode == '1' else '.pnm')
    image.save(path, **({'compress_level': 1} if image.mode == '1' else {}))
    del image
    try:
        os.remove(raw)
    except OSError:
        log.warning("could not remove %s", raw)
    return path, width, height


ProgressFn = Callable[[float, int], None]      # fraction of this page, page number (1-based)


class Job:
    """One run of scanimage, cancellable from another thread. run() blocks; call it in a
    worker thread. Each finished page is passed to on_page(raw_pnm_path, number)."""

    def __init__(self, cmd: List[str], on_progress: Optional[ProgressFn] = None):
        self.cmd = cmd
        self.on_progress = on_progress
        self.proc: Optional[subprocess.Popen] = None
        self.cancelled = threading.Event()
        self.stderr = ''

    def cancel(self) -> None:
        self.cancelled.set()
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                # scanimage cancels the scan on SIGTERM, and exits on a second one
                proc.send_signal(signal.SIGTERM) if os.name != 'nt' else proc.terminate()
            except (OSError, ValueError):
                pass
            threading.Thread(target=self._kill_later, args=(proc,), daemon=True).start()

    @staticmethod
    def _kill_later(proc: subprocess.Popen) -> None:
        deadline = time.monotonic() + CANCEL_GRACE
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            proc.kill()
        except OSError:
            pass

    def run(self, on_page: Optional[Callable[[str, int], None]] = None) -> int:
        """Returns scanimage's exit code; raises ScanError on failure (not on cancel)."""
        if self.cancelled.is_set():
            return -1
        log.info("run: %s", ' '.join(self.cmd))
        env = dict(os.environ, LC_ALL='C')      # parse English messages
        try:
            self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=env,
                                         creationflags=NO_WINDOW)
        except OSError as exc:
            raise ScanError('failed', str(exc)) from exc
        if self.cancelled.is_set():
            self.cancel()
        page = [1]
        out_lines: List[str] = []
        failed: List[BaseException] = []

        def read_stdout():
            assert self.proc and self.proc.stdout
            for raw in iter(self.proc.stdout.readline, b''):
                line = raw.decode('utf-8', 'replace').strip()
                if line:
                    out_lines.append(line)
                    if on_page and os.path.isfile(line) and not failed:
                        try:
                            on_page(line, len(out_lines))
                        except BaseException as exc:     # raised again in run()
                            failed.append(exc)
                            self.cancel()

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        err, buf = [], b''
        assert self.proc.stderr
        fd = self.proc.stderr.fileno()
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb'[\r\n]', buf)
            buf = parts.pop()
            for part in parts:
                text = part.decode('utf-8', 'replace').strip()
                if not text:
                    continue
                m = re.match(r'Progress:\s*([\d.]+)%', text)
                if m:
                    if self.on_progress:
                        self.on_progress(min(1.0, float(m.group(1)) / 100), page[0])
                    continue
                m = re.match(r'Scanning page (\d+)', text)
                if m:
                    page[0] = int(m.group(1))
                    if self.on_progress:
                        self.on_progress(0.0, page[0])
                    continue
                err.append(text)
        code = self.proc.wait()
        reader.join()      # the last page may still be being finished by on_page
        for pipe in (self.proc.stdout, self.proc.stderr):
            if pipe:
                pipe.close()
        if failed:
            raise failed[0]
        self.stderr = '\n'.join(err + ([buf.decode('utf-8', 'replace')] if buf else []))
        if self.stderr:
            log.info("scanimage said: %s", self.stderr[-600:])
        if self.cancelled.is_set():
            return -1
        if code != 0:
            kind = classify_error(self.stderr)
            # a feeder scan ends when the feeder is empty; that's the normal end
            if kind == 'no_docs' and out_lines:
                return 0
            raise ScanError(kind, last_error_line(self.stderr))
        return code
