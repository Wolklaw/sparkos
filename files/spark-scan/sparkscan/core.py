"""Everything below the interface that isn't SANE or the PDF: folders, settings, the log,
file names, and the tesseract program."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, SCANS_FOLDER, VERSION

log = logging.getLogger(APP_SLUG)
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)    # Windows dev runs only


# ─── Folders, settings, logging ───────────────────────────────

def _xdg_dir(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def config_dir() -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir() -> str:
    return _xdg_dir('XDG_CACHE_HOME', '.cache')


def documents_dir() -> str:
    """The Documents folder as xdg-user-dirs names it (it is translated: Documents, ...)."""
    home = os.path.expanduser('~')
    if shutil.which('xdg-user-dir'):
        try:
            out = subprocess.run(['xdg-user-dir', 'DOCUMENTS'], capture_output=True, text=True,
                                 timeout=3, creationflags=NO_WINDOW).stdout.strip()
            # xdg-user-dir prints $HOME when the folder isn't set
            if out and os.path.normpath(out) != os.path.normpath(home):
                return out
        except (OSError, subprocess.SubprocessError):
            pass
    return os.path.join(home, 'Documents')


def scans_dir() -> str:
    """Where scans are saved: Documents/Scans, or SPARK_SCAN_OUTPUT (tests)."""
    return os.environ.get('SPARK_SCAN_OUTPUT') or os.path.join(documents_dir(), SCANS_FOLDER)


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
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


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


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_SCAN_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def open_folder(path: str) -> Optional[str]:
    """Open a folder in the file manager. None on success, otherwise what went wrong."""
    if os.name == 'nt':
        try:
            os.startfile(path)      # type: ignore[attr-defined]
            return None
        except OSError as exc:
            return str(exc)
    opener = shutil.which('xdg-open')
    if not opener:
        return "xdg-open is not installed"
    try:
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return None
    except OSError as exc:
        return str(exc)


# ─── File names ───────────────────────────────────────────────

def scan_name(word: str, when: Optional[datetime] = None) -> str:
    """'Scan 2026-11-20 14.32': sorts by date, and has no ':' (FAT, NTFS, SMB can't)."""
    when = when or datetime.now()
    return f"{word} {when:%Y-%m-%d %H.%M}"


def unique_path(folder: str, stem: str, ext: str) -> str:
    """folder/stem.ext, or 'stem (2).ext' and so on if that is taken."""
    path = os.path.join(folder, f"{stem}.{ext}")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem} ({n}).{ext}")
        n += 1
    return path


def page_paths(folder: str, stem: str, ext: str, count: int, page_word: str) -> List[str]:
    """Names for one image per page. One page: 'Scan ….png'. Several: 'Scan … - page 1.png',
    with the whole set moved to 'Scan … (2) - page 1.png' if any name is taken, so the
    pages of one document always share a stem."""
    if count == 1:
        return [unique_path(folder, stem, ext)]
    n = 1
    while True:
        base = stem if n == 1 else f"{stem} ({n})"
        paths = [os.path.join(folder, f"{base} - {page_word} {i}.{ext}")
                 for i in range(1, count + 1)]
        if not any(os.path.exists(p) for p in paths):
            return paths
        n += 1


def new_session_dir() -> str:
    """A folder in ~/.cache/spark-scan for this window's pages. Old ones (a crash) older
    than a day are removed."""
    root = cache_dir()
    now = time.time()
    try:
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if name.startswith('session-') and os.path.isdir(path):
                try:
                    if now - os.path.getmtime(path) > 86400:
                        shutil.rmtree(path, ignore_errors=True)
                except OSError:
                    pass
    except OSError:
        pass
    try:
        return tempfile.mkdtemp(prefix='session-', dir=root)
    except OSError:
        return tempfile.mkdtemp(prefix=f'{APP_SLUG}-')


# ─── Tesseract ────────────────────────────────────────────────

class Tesseract:
    """The tesseract program, called directly (it is in the SparkOS image for Spark Snip)."""

    def __init__(self, cmd: Optional[str] = None):
        self.cmd = cmd or os.environ.get('SPARK_SCAN_TESSERACT') or shutil.which('tesseract')
        self._langs: Optional[List[str]] = None

    @property
    def found(self) -> bool:
        return bool(self.cmd)

    def version(self) -> str:
        if not self.cmd:
            return ''
        try:
            out = subprocess.run([self.cmd, '--version'], capture_output=True, text=True,
                                 timeout=10, creationflags=NO_WINDOW)
            match = re.search(r'tesseract v?(\d+(?:\.\d+){0,2})', out.stdout + out.stderr)
            return match.group(1) if match else '?'
        except (OSError, subprocess.SubprocessError):
            return ''

    def languages(self) -> List[str]:
        if self._langs is None:
            self._langs = []
            if self.cmd:
                try:
                    out = subprocess.run([self.cmd, '--list-langs'], capture_output=True,
                                         text=True, timeout=10, creationflags=NO_WINDOW)
                    names = [line.strip() for line in out.stdout.splitlines()[1:]]
                    self._langs = sorted(n for n in names if n and n not in ('osd', 'equ'))
                except (OSError, subprocess.SubprocessError):
                    log.exception("could not list Tesseract languages")
        return self._langs

    def language_choices(self) -> List[str]:
        """What the OCR switch offers: English and French, each if installed, and both."""
        have = [code for code in ('eng', 'fra') if code in self.languages()]
        return (['eng+fra'] if len(have) == 2 else []) + have


def language_label(code: str) -> str:
    return '+'.join({'eng': 'EN', 'fra': 'FR'}.get(c, c.upper()) for c in code.split('+'))
