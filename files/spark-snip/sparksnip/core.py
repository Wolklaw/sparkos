"""Everything below the interface: settings, OCR, screen capture, monitors, clipboard."""

import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import APP_NAME, APP_SLUG, VERSION
from .lang import local_units
from .text import EN, t

DEFAULT_LANG = "eng+fra"
OCR_PSM = "6"
OCR_TIMEOUT = 30
CONF_ACCEPT = 80.0          # good enough; stop trying other preprocessing variants
CONF_WARN = 60.0            # below this the read is unreliable, so say so
VARIANT_BUDGET = 4.0        # seconds; stop trying more variants past this
UPSCALE_MAX = 3.0
UPSCALE_PIXEL_CAP = 12_000_000
CAPTURE_TIMEOUT = 15

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)    # Windows dev runs only
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

Box = Tuple[int, int, int, int]           # left, top, right, bottom

log = logging.getLogger(APP_SLUG)

LANGUAGE_NAMES = {
    'eng': "English", 'fra': "French", 'deu': "German", 'spa': "Spanish", 'ita': "Italian",
    'por': "Portuguese", 'nld': "Dutch", 'pol': "Polish", 'rus': "Russian", 'ukr': "Ukrainian",
    'tur': "Turkish", 'swe': "Swedish", 'dan': "Danish", 'nor': "Norwegian", 'fin': "Finnish",
    'ces': "Czech", 'ell': "Greek", 'ara': "Arabic", 'heb': "Hebrew", 'hin': "Hindi",
    'jpn': "Japanese", 'kor': "Korean", 'chi_sim': "Chinese (Simplified)",
    'chi_tra': "Chinese (Traditional)", 'vie': "Vietnamese",
}
LANGUAGE_SHORT = {
    'eng': "EN", 'fra': "FR", 'deu': "DE", 'spa': "ES", 'ita': "IT", 'por': "PT", 'nld': "NL",
    'pol': "PL", 'rus': "RU", 'ukr': "UK", 'tur': "TR", 'swe': "SV", 'dan': "DA", 'nor': "NO",
    'fin': "FI", 'ces': "CS", 'ell': "EL", 'ara': "AR", 'heb': "HE", 'hin': "HI", 'jpn': "JA",
    'kor': "KO", 'chi_sim': "ZH", 'chi_tra': "ZH-T", 'vie': "VI",
}


# ─── Paths, settings, logging ─────────────────────────────────

def _xdg_dir(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return tempfile.gettempdir()


def config_dir() -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config')


def cache_dir() -> str:
    return _xdg_dir('XDG_CACHE_HOME', '.cache')


def state_dir() -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def runtime_dir() -> str:
    return os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()


def user_dir(kind: str, fallback: str) -> str:
    """The user's Pictures or Videos folder, from xdg-user-dirs."""
    home = os.path.expanduser('~')
    found = ''
    try:
        found = subprocess.run(['xdg-user-dir', kind], capture_output=True, text=True,
                               timeout=3, creationflags=NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    # xdg-user-dir prints $HOME when the folder isn't configured
    if not found or os.path.normpath(found) == os.path.normpath(home):
        found = os.path.join(home, fallback)
    return found


LATEST_NAME = 'latest.png'


def latest_path() -> str:
    """The last screenshot, kept as a PNG so Spark Link's Send screenshot can pick it up."""
    return os.path.join(cache_dir(), LATEST_NAME)


def keep_latest(image: Image.Image, path: Optional[str] = None) -> Optional[str]:
    """Write the screenshot to latest_path() in one step (no half-written file for a reader).
    None on success, otherwise what went wrong."""
    path = path or latest_path()
    part = path + '.part'
    try:
        image.save(part, 'PNG')
        os.replace(part, path)
        return None
    except (OSError, ValueError) as exc:
        try:
            os.remove(part)
        except OSError:
            pass
        return str(exc)


def screenshots_dir() -> str:
    return os.path.join(user_dir('PICTURES', 'Pictures'), 'Screenshots')


def recordings_dir() -> str:
    return os.path.join(user_dir('VIDEOS', 'Videos'), 'Screencasts')


def short_path(path: str) -> str:
    home = os.path.expanduser('~')
    return '~' + path[len(home):] if path.startswith(home + os.sep) else path


def setup_logging() -> None:
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=512 * 1024, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s, %s session) ---", APP_NAME, VERSION,
             sys.version.split()[0], session())


def load_config() -> Dict[str, Any]:
    try:
        with open(os.path.join(config_dir(), 'config.json'), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        log.warning("config is a %s, not an object - ignoring", type(data).__name__)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read config: %s", exc)
    return {}


def save_config(data: Dict[str, Any]) -> None:
    """Write a temp file and swap it in, so an interrupted save keeps the old settings."""
    path = os.path.join(config_dir(), 'config.json')
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(path + '.tmp', path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write config: %s", exc)


def session() -> str:
    if os.name == 'nt':
        return 'windows'
    if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        return 'wayland'
    if os.environ.get('DISPLAY'):
        return 'x11'
    return 'none'


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_SNIP_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        # Spark Settings keeps its own copy of the switch (Appearance > Animations)
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            saved = json.load(f)
        if 'animations' in saved:
            return not saved['animations']
    except (OSError, ValueError, AttributeError):
        pass
    if 'sparkwl' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
        return False
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def open_folder(path: str) -> Optional[str]:
    """Open a folder in the file manager. None on success, otherwise what went wrong."""
    opener = shutil.which('xdg-open') or (shutil.which('explorer') if os.name == 'nt' else None)
    if not opener:
        return t('open.no_xdg')
    try:
        subprocess.Popen([opener, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=os.name != 'nt')
        return None
    except OSError as exc:
        return str(exc)


def language_label(lang: str) -> str:
    """'eng+fra' -> 'English + French' ('Anglais + Français' in French); unknown codes are
    shown as they are."""
    return " + ".join(t(f'ocr.{part}') if f'ocr.{part}' in EN else LANGUAGE_NAMES.get(part, part)
                      for part in lang.split('+'))


def language_short(lang: str) -> str:
    """'eng+fra' -> 'EN + FR', for the compact language switch."""
    return " + ".join(LANGUAGE_SHORT.get(part, part.upper()) for part in lang.split('+'))


def _human_size(size: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} B"


def human_size(size: int) -> str:
    return local_units(_human_size(size))


def clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return (f"{hours}:" if hours else "") + f"{rest // 60:02d}:{rest % 60:02d}"


# ─── OCR ──────────────────────────────────────────────────────

class OCRError(Exception):
    pass


class OCRResult(NamedTuple):
    text: str
    confidence: float
    variant: str


def parse_tsv(tsv: str) -> Tuple[str, float]:
    """Tesseract TSV -> (text with one line per detected line, mean word confidence)."""
    lines: Dict[Tuple[int, int, int], List[str]] = {}
    confidences: List[float] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split('\t')
        if len(cols) < 12:
            continue
        word = cols[11].strip()
        if not word:
            continue
        try:
            key = (int(cols[2]), int(cols[3]), int(cols[4]))
            confidence = float(cols[10])
        except ValueError:
            continue
        lines.setdefault(key, []).append(word)
        if confidence >= 0:
            confidences.append(confidence)
    text = '\n'.join(' '.join(words) for _, words in sorted(lines.items()))
    return text, (sum(confidences) / len(confidences) if confidences else 0.0)


class Tesseract:
    """The tesseract command line program, called directly. Fedora ships it as a plain
    package, so no Python OCR binding is needed."""

    def __init__(self):
        self.cmd = self._find()
        self.tessdata = os.environ.get('SPARK_SNIP_TESSDATA') or self._bundled_tessdata()

    @staticmethod
    def _find() -> Optional[str]:
        # the last candidate is only for running from a Windows checkout next to QuickOCR
        candidates = (os.environ.get('SPARK_SNIP_TESSERACT'), shutil.which('tesseract'),
                      os.path.join(ROOT, os.pardir, os.pardir, os.pardir, 'QuickOCR',
                                   'Tesseract-OCR', 'tesseract.exe'))
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    def _bundled_tessdata(self) -> Optional[str]:
        if os.name == 'nt' and self.cmd:
            folder = os.path.join(os.path.dirname(self.cmd), 'tessdata')
            if os.path.isdir(folder):
                return folder
        return None

    def _args(self, *args: str) -> List[str]:
        if not self.cmd:
            raise OCRError(t('ocr.missing'))
        extra = ['--tessdata-dir', self.tessdata] if self.tessdata else []
        return [self.cmd, *args[:2], *extra, *args[2:]]

    def version(self) -> str:
        if not self.cmd:
            return ''
        try:
            # --version is only recognised as the sole argument
            out = subprocess.run([self.cmd, '--version'], capture_output=True, text=True,
                                 timeout=10, creationflags=NO_WINDOW)
            match = re.search(r'tesseract v?(\d+(?:\.\d+){0,2})', out.stdout + out.stderr)
            return match.group(1) if match else '?'
        except (OSError, subprocess.SubprocessError):
            return ''

    def languages(self) -> List[str]:
        # Reading the tessdata folder is instant; tesseract --list-langs is a process start
        # on every Snip launch. Fall back to asking tesseract when the folder isn't found.
        for d in (os.environ.get('TESSDATA_PREFIX'), '/usr/share/tesseract/tessdata',
                  '/usr/share/tessdata', '/usr/share/tesseract-ocr/5/tessdata'):
            try:
                names = [n[:-12] for n in os.listdir(d) if n.endswith('.traineddata')] if d else []
            except OSError:
                continue
            if names:
                return sorted(n for n in names if n not in ('osd', 'equ'))
        try:
            out = subprocess.run(self._args('--list-langs'), capture_output=True, text=True,
                                 timeout=10, creationflags=NO_WINDOW)
        except (OCRError, OSError, subprocess.SubprocessError):
            log.exception("could not list Tesseract languages")
            return []
        names = [line.strip() for line in out.stdout.splitlines()[1:]]
        return sorted(name for name in names if name and name not in ('osd', 'equ'))

    def tsv(self, image: Image.Image, lang: str) -> str:
        fd, path = tempfile.mkstemp(prefix=f'{APP_SLUG}-', suffix='.png')
        os.close(fd)
        try:
            image.save(path)
            proc = subprocess.run(self._args(path, 'stdout', '-l', lang, '--psm', OCR_PSM, 'tsv'),
                                  capture_output=True, timeout=OCR_TIMEOUT,
                                  creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise OCRError(t('ocr.slow', secs=OCR_TIMEOUT)) from exc
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if proc.returncode != 0:
            detail = proc.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise OCRError(detail[-1] if detail else t('ocr.exit', code=proc.returncode))
        return proc.stdout.decode('utf-8', 'replace')


class OCREngine:
    """Reads text from an image, trying several preprocessing variants.

    No single binarization wins everywhere: a fixed threshold erases low-contrast grey
    text, while Otsu misfires when the text covers only a few percent of the pixels.
    So each variant is scored with Tesseract's own confidence and the best one wins.
    """

    def __init__(self, tesseract: Tesseract, lang: str = DEFAULT_LANG):
        self.tesseract = tesseract
        self.available = tesseract.languages()
        if self.supports(DEFAULT_LANG):
            fallback = DEFAULT_LANG
        else:
            fallback = self.available[0] if self.available else 'eng'
        self.lang = lang if self.supports(lang) else fallback
        log.info("languages available=%s using=%s", ','.join(self.available) or 'none', self.lang)

    def supports(self, lang: str) -> bool:
        return bool(lang) and all(part in self.available for part in lang.split('+'))

    def language_choices(self) -> List[str]:
        """The default combination first, then each installed language on its own."""
        choices = [DEFAULT_LANG] if self.supports(DEFAULT_LANG) else []
        return choices + [name for name in self.available if name not in choices]

    @staticmethod
    def _upscaled_gray(img: Image.Image) -> Image.Image:
        """Upscale small snips for legibility, capped so a full-screen grab stays quick."""
        w, h = img.size
        factor = max(1.0, min(UPSCALE_MAX, math.sqrt(UPSCALE_PIXEL_CAP / max(1, w * h))))
        if factor > 1.01:
            img = img.resize((max(1, int(w * factor)), max(1, int(h * factor))),
                             Image.Resampling.LANCZOS)
        return img.convert('L')

    @staticmethod
    def _otsu_threshold(gray: Image.Image) -> int:
        hist = gray.histogram()
        total = sum(hist)
        total_sum = sum(i * hist[i] for i in range(256))
        weight_bg = sum_bg = 0
        best_variance, threshold = -1.0, 128
        for i in range(256):
            weight_bg += hist[i]
            if weight_bg == 0:
                continue
            weight_fg = total - weight_bg
            if weight_fg == 0:
                break
            sum_bg += i * hist[i]
            variance = ((sum_bg / weight_bg - (total_sum - sum_bg) / weight_fg) ** 2
                        * weight_bg * weight_fg)
            if variance > best_variance:
                best_variance, threshold = variance, i
        return threshold

    @staticmethod
    def _ink_on_white(mono: Image.Image) -> Image.Image:
        """Tesseract prefers dark text on light; text is normally the minority of pixels."""
        hist = mono.histogram()
        if hist[0] > hist[255]:
            mono = ImageOps.invert(mono)
        return mono.convert('1', dither=Image.Dither.NONE)

    @classmethod
    def _prep_otsu(cls, img: Image.Image) -> Image.Image:
        gray = cls._upscaled_gray(img)
        threshold = cls._otsu_threshold(gray)
        return cls._ink_on_white(gray.point(lambda x: 0 if x < threshold else 255, 'L'))

    @classmethod
    def _prep_fixed(cls, img: Image.Image) -> Image.Image:
        gray = cls._upscaled_gray(img)
        return cls._ink_on_white(gray.point(lambda x: 0 if x > 115 else 255, 'L'))

    @classmethod
    def _prep_gray(cls, img: Image.Image) -> Image.Image:
        return ImageOps.autocontrast(cls._upscaled_gray(img), cutoff=2)

    def _run(self, prepared: Image.Image, variant: str) -> OCRResult:
        text, confidence = parse_tsv(self.tesseract.tsv(prepared, self.lang))
        return OCRResult(text, confidence, variant)

    def extract_text(self, img: Image.Image) -> OCRResult:
        """Raises the last error if every variant failed: a missing tesseract or language
        file must not be reported as "No text found"."""
        best = OCRResult('', 0.0, 'none')
        started = time.monotonic()
        last_took = 0.0
        last_error: Optional[Exception] = None
        succeeded = False
        for variant, prepare in (('otsu', self._prep_otsu),
                                 ('fixed', self._prep_fixed),
                                 ('gray', self._prep_gray)):
            elapsed = time.monotonic() - started
            if elapsed + last_took > VARIANT_BUDGET:
                log.info("stopping after %.2fs, another variant would overrun the budget", elapsed)
                break
            attempt = time.monotonic()
            try:
                result = self._run(prepare(img), variant)
            except (OCRError, OSError, ValueError) as exc:
                log.exception("variant %s failed", variant)
                last_error = exc
                continue
            finally:
                last_took = time.monotonic() - attempt
            succeeded = True
            log.info("variant=%s conf=%.1f chars=%d in %.2fs",
                     variant, result.confidence, len(result.text), last_took)
            if ((result.confidence, bool(result.text.strip()))
                    > (best.confidence, bool(best.text.strip()))):
                best = result
            if best.confidence >= CONF_ACCEPT:
                break
        if not succeeded and last_error is not None:
            raise last_error
        log.info("best variant=%s conf=%.1f in %.2fs", best.variant, best.confidence,
                 time.monotonic() - started)
        return best


# ─── Screen capture and monitors ──────────────────────────────

class CaptureError(Exception):
    pass


class Monitor(NamedTuple):
    name: str
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    @property
    def box(self) -> Box:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


# Built in (sparksnip/capture.py): 'kwin' is KWin's ScreenShot2 D-Bus interface, 'portal'
# the XDG Desktop Portal's Screenshot call, 'pil' Pillow on X11 and Windows. The helper
# programs below are for other Wayland desktops, and Spectacle is only a fallback on Plasma
# for as long as it is still installed: Spark Snip never needs it.
BUILT_IN_CAPTURE = ('kwin', 'portal', 'pil')
CAPTURE_TOOLS: Dict[str, Callable[[str], List[str]]] = {
    'spectacle': lambda path: ['spectacle', '--background', '--nonotify', '--fullscreen',
                               '--output', path],
    # PPM: no PNG compression, a 3-screen desktop takes 0.1 s instead of 0.35 s
    'grim': lambda path: ['grim', '-t', 'ppm', path],          # Sway, Hyprland, wlroots
    'gnome-screenshot': lambda path: ['gnome-screenshot', '--file', path],
}


def capture_order() -> List[str]:
    forced = os.environ.get('SPARK_SNIP_CAPTURE')
    if forced:
        return [forced]
    kind = session()
    if kind == 'windows':
        return ['pil']
    if kind == 'x11':
        return ['pil', 'portal']
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    if 'gnome' in desktop:
        return ['gnome-screenshot', 'portal']
    if 'sparkwl' in desktop.split(':'):
        # the Spark compositor speaks wlr-screencopy: grim, no KWin probe, no portal dialog
        return ['grim', 'portal']
    if 'kde' in desktop or not desktop:
        # Spectacle before the portal: the portal may show a dialog, Spectacle never does
        return ['kwin', 'spectacle', 'portal']
    # Any other name (the Spark session runs KWin without plasmashell and calls itself
    # something else): go by what is on the bus, not by the name.
    if kwin_offers_screenshots():
        return ['kwin', 'portal']
    return ['grim', 'portal']


def kwin_offers_screenshots() -> bool:
    """True when KWin's ScreenShot2 interface is on the session bus. SPARK_SNIP_KWIN=1|0
    forces the answer (tests, --self-test)."""
    forced = os.environ.get('SPARK_SNIP_KWIN')
    if forced in ('0', '1'):
        return forced == '1'
    try:
        from . import capture
        return capture.kwin_screenshot_offered()
    except Exception as exc:            # noqa: BLE001 - no bus, no PyGObject: not KWin
        log.info("could not ask the bus about KWin: %s", exc)
        return False


def _tool_screenshot(name: str) -> Image.Image:
    fd, path = tempfile.mkstemp(prefix=f'{APP_SLUG}-shot-',
                                suffix='.ppm' if name == 'grim' else '.png')
    os.close(fd)
    try:
        proc = subprocess.run(CAPTURE_TOOLS[name](path), stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              timeout=CAPTURE_TIMEOUT)
        if proc.returncode != 0 or os.path.getsize(path) == 0:
            detail = proc.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise CaptureError(f"{name}: " + (detail[-1] if detail else f"exit {proc.returncode}"))
        with Image.open(path) as img:
            img.load()
            return img.convert('RGB')
    except subprocess.TimeoutExpired as exc:
        raise CaptureError(f"{name}: no screenshot after {CAPTURE_TIMEOUT}s") from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _built_in_screenshot(name: str) -> Image.Image:
    from . import capture
    if name == 'pil':
        from PIL import ImageGrab
        return ImageGrab.grab().convert('RGB')
    if name == 'kwin':
        with capture.KWinScreenShot() as kwin:
            return kwin.workspace().convert('RGB')
    return capture.portal_screenshot()


def close_spark_menu() -> None:
    """On the Spark compositor, close the Spark menu before the screenshot: it is open when
    Win+Shift+S is pressed from it, and would end up in the picture and cover the overlay."""
    if 'sparkwl' not in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
        return
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('dev.wolklaw.SparkShell', '/Shell', 'dev.wolklaw.SparkShell',
                              'HideLauncher', None, GLib.VariantType('(b)'),
                              Gio.DBusCallFlags.NO_AUTO_START, 500, None)
        if reply.unpack()[0]:
            time.sleep(0.12)        # let the compositor take it off screen
    except Exception as exc:        # noqa: BLE001 - no shell, older shell: capture anyway
        log.info("could not ask the shell to close its menu: %s", exc)


def grab_screen() -> Tuple[Image.Image, str]:
    """The whole desktop as one image, and the tool that took it."""
    from .capture import ScreenReadError
    close_spark_menu()
    problems = []
    for tool in capture_order():
        if tool in BUILT_IN_CAPTURE:
            try:
                shot = _built_in_screenshot(tool)
                log.info("captured %sx%s with %s", shot.width, shot.height, tool)
                return shot, tool
            except ScreenReadError as exc:
                log.warning("capture with %s failed: %s", tool, exc)
                problems.append(str(exc))
            except Exception as exc:                    # noqa: BLE001 - try the next one
                log.exception("capture with %s failed", tool)
                problems.append(f"{tool}: {exc}")
            continue
        if tool not in CAPTURE_TOOLS:
            problems.append(f"{tool}: not a capture method Spark Snip knows")
            continue
        if not shutil.which(tool):
            problems.append(f"{tool}: not installed")
            continue
        try:
            shot = _tool_screenshot(tool)
            log.info("captured %sx%s with %s", shot.width, shot.height, tool)
            return shot, tool
        except (CaptureError, OSError, subprocess.SubprocessError) as exc:
            log.warning("capture with %s failed: %s", tool, exc)
            problems.append(str(exc))
    raise CaptureError(t('cap.failed', why='; '.join(problems)))


MONITOR_RE = re.compile(r'(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)\s+(\S+)')


def parse_monitors(xrandr_output: str) -> List[Monitor]:
    """`xrandr --listmonitors` -> monitors, named after their connector (DP-1, HDMI-A-1)."""
    return [Monitor(name, int(x), int(y), int(w), int(h))
            for w, h, x, y, name in MONITOR_RE.findall(xrandr_output)]


def monitors(screen_size: Tuple[int, int]) -> List[Monitor]:
    if session() in ('wayland', 'x11') and shutil.which('xrandr'):
        try:
            out = subprocess.run(['xrandr', '--listmonitors'], capture_output=True, text=True,
                                 timeout=3).stdout
            found = parse_monitors(out)
            if found:
                return found
        except (OSError, subprocess.SubprocessError):
            log.exception("xrandr failed")
    return [Monitor('screen', 0, 0, *screen_size)]


def bounding_box(screens: Sequence[Monitor]) -> Box:
    return (min(m.x for m in screens), min(m.y for m in screens),
            max(m.x + m.w for m in screens), max(m.y + m.h for m in screens))


def screen_to_image(box: Box, desktop: Box, image_size: Tuple[int, int]) -> Box:
    """Map a box in screen coordinates to the screenshot's pixels.

    They differ by a scale factor when the compositor captures at a higher resolution than
    the X server under it reports (XWayland scaled by the system, for example).
    """
    sx = image_size[0] / max(1, desktop[2] - desktop[0])
    sy = image_size[1] / max(1, desktop[3] - desktop[1])

    def clamp(value: float, limit: int) -> int:
        return max(0, min(limit, round(value)))

    return (clamp((box[0] - desktop[0]) * sx, image_size[0]),
            clamp((box[1] - desktop[1]) * sy, image_size[1]),
            clamp((box[2] - desktop[0]) * sx, image_size[0]),
            clamp((box[3] - desktop[1]) * sy, image_size[1]))


def place_on_desktop(image: Image.Image, desktop: Box, background: str) -> Image.Image:
    """For --from: centre a small picture on a desktop-sized field, so it shows 1:1."""
    width, height = desktop[2] - desktop[0], desktop[3] - desktop[1]
    if image.width > width or image.height > height:
        return image
    field = Image.new('RGB', (width, height), background)
    field.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return field


# ─── Clipboard ────────────────────────────────────────────────

def _pipe_to(cmd: List[str], data: bytes) -> bool:
    """wl-copy and xclip fork a helper that keeps serving the clipboard after we exit. It
    inherits our pipes, so never capture its output: run() would wait on it forever."""
    try:
        return subprocess.run(cmd, input=data, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("%s failed: %s", cmd[0], exc)
        return False


class Clipboard:
    """Text, images and files, through wl-copy (Wayland) or xclip (X11). Tk's own
    clipboard is the last resort for text: on Linux it empties when the app quits."""

    def __init__(self, tk_root):
        self.root = tk_root
        self.kind = session()

    def _tools(self, mime: str) -> List[List[str]]:
        tools = []
        if self.kind == 'wayland' and shutil.which('wl-copy'):
            tools.append(['wl-copy', '--type', mime])
        if self.kind in ('wayland', 'x11') and shutil.which('xclip'):
            tools.append(['xclip', '-selection', 'clipboard', '-target', mime, '-in'])
        return tools

    def _send(self, mime: str, data: bytes) -> bool:
        for cmd in self._tools(mime):
            if _pipe_to(cmd, data):
                log.info("copied %d bytes of %s with %s", len(data), mime, cmd[0])
                return True
        return False

    def copy_text(self, text: str) -> Optional[str]:
        """None on success, otherwise what went wrong."""
        if self._send('text/plain;charset=utf-8', text.encode('utf-8')):
            return None
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            if self.kind != 'windows':
                log.warning("copied with Tk only; install wl-clipboard so it outlives the app")
            return None
        except Exception as exc:                    # noqa: BLE001 - TclError, mostly
            return str(exc)

    def can_copy_binary(self) -> bool:
        return bool(self._tools('image/png'))

    def copy_image(self, image: Image.Image) -> Optional[str]:
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        if self._send('image/png', buffer.getvalue()):
            return None
        return t('clip.no_image_tool')

    def copy_file(self, path: str) -> Optional[str]:
        """Put a file on the clipboard, so it pastes into a file manager or a chat app."""
        uri = 'file://' + quote(os.path.abspath(path))
        if self._send('text/uri-list', (uri + '\r\n').encode('utf-8')):
            return None
        return t('clip.no_file_tool')


# ─── Self-test samples ────────────────────────────────────────

def system_font_file() -> Optional[str]:
    """A TrueType font with accented letters; Pillow's built-in one has none."""
    if shutil.which('fc-match'):
        for pattern in ('sans:lang=fr', 'monospace:lang=fr'):
            try:
                path = subprocess.run(['fc-match', '-f', '%{file}', pattern], capture_output=True,
                                      text=True, timeout=5).stdout.strip()
                if path.lower().endswith(('.ttf', '.otf')) and os.path.isfile(path):
                    return path
            except (OSError, subprocess.SubprocessError):
                pass
    windir = os.environ.get('WINDIR')
    if windir and os.path.isfile(os.path.join(windir, 'Fonts', 'arial.ttf')):
        return os.path.join(windir, 'Fonts', 'arial.ttf')
    return None


def sample_image(text: str, size: int = 44, font_file: Optional[str] = None) -> Image.Image:
    try:
        font = (ImageFont.truetype(font_file, size) if font_file
                else ImageFont.load_default(size=size))
    except (TypeError, OSError):            # Pillow without FreeType: tiny bitmap font
        font = ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    image = Image.new('RGB', (right - left + 60, bottom - top + 50), 'white')
    ImageDraw.Draw(image).text((30 - left, 25 - top), text, fill='black', font=font)
    return image
