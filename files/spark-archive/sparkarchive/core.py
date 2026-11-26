"""Settings, log, numbers and names for people, and the desktop's file dialogs."""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)


def _xdg_dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
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


def setup_logging() -> None:
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=256 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


def load_json(name: str) -> Dict[str, Any]:
    try:
        with open(os.path.join(config_dir(), name), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", name, exc)
    return {}


def save_json(name: str, data: Dict[str, Any]) -> None:
    """Write a settings file whole (a temporary file moved into place); failures are logged,
    never raised: a setting not saved is not worth an error."""
    path = os.path.join(config_dir(), name)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("could not save %s: %s", name, exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def reduced_motion() -> bool:
    """True when animations are turned off in Spark Settings (appearance.json) or by env."""
    if os.environ.get('SPARK_ARCHIVE_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'spark', 'appearance.json'), encoding='utf-8') as f:
            return json.load(f).get('animations', True) is False
    except (OSError, ValueError, AttributeError):
        return False


def language() -> str:
    """'fr' or 'en'. SPARK_LANG=en|fr decides if set; otherwise the first of LC_ALL,
    LC_MESSAGES and LANG that is set: French if it starts with 'fr' (fr_CA.UTF-8, fr_FR...),
    English for anything else. The same rule as the other Spark apps."""
    forced = os.environ.get('SPARK_LANG', '').strip().lower()
    if forced in ('en', 'fr'):
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


# ─── Numbers and names for people ─────────────────────────────

SIZE_UNITS = {'en': ("B", "KB", "MB", "GB", "TB"), 'fr': ("o", "Ko", "Mo", "Go", "To")}


def size(n: Optional[float], digits: int = 1) -> str:
    """Bytes, in the units Windows and most file managers use (1 KB = 1024 bytes); in French
    '392,6 Ko'."""
    if n is None or n < 0:
        return "—"
    lang = language()
    units = SIZE_UNITS[lang]
    for unit in units:
        if abs(n) < 1024 or unit == units[-1]:
            if unit == units[0]:
                return f"{int(n)} {unit}"
            text = f"{n:.{digits}f} {unit}"
            return text.replace('.', ',') if lang == 'fr' else text
        n /= 1024
    return "—"


def when(ts: Optional[float]) -> str:
    if ts is None or ts <= 0:
        return "—"
    try:
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return "—"


# longest first, so .tar.gz wins over .gz
ARCHIVE_SUFFIXES = ('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.zstd', '.tgz', '.tbz2',
                    '.tbz', '.txz', '.tzst', '.tar', '.zip', '.7z', '.rar', '.iso', '.gz', '.bz2',
                    '.xz', '.zst', '.zstd')


def stem(path: str) -> str:
    """photos.tar.gz -> photos; a part of a set (photos.part2.rar, photos.7z.001, photos.r00,
    photos.z01) -> photos. Falls back to the name without its last extension."""
    name = os.path.basename(path.rstrip('/'))
    from .volumes import stem_of
    of_set = stem_of(name)
    if of_set:
        return of_set
    low = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if low.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    base, _ext = os.path.splitext(name)
    return base or name


def unique_path(folder: str, name: str, ext: str = '') -> str:
    """folder/name+ext, or folder/name (2)+ext and so on if that is taken."""
    candidate = os.path.join(folder, name + ext)
    n = 2
    while os.path.lexists(candidate):
        candidate = os.path.join(folder, f"{name} ({n}){ext}")
        n += 1
    return candidate


def keep_both_name(name: str, taken) -> str:
    """report.pdf -> report (2).pdf, the first one `taken(name)` says is free."""
    base, ext = os.path.splitext(name)
    if base.startswith('.') and not ext:          # .bashrc has no extension
        base, ext = name, ''
    n = 2
    while True:
        candidate = f"{base} ({n}){ext}"
        if not taken(candidate):
            return candidate
        n += 1


# ─── The desktop ──────────────────────────────────────────────

def pick_archive(start: str) -> Optional[str]:
    """The desktop's own file dialog (spark-pick: Spark Files through the desktop portal), Tk's as a fallback."""
    from .text import t
    # first parts of multi-part sets too: photos.7z.001, photos.r00, photos.z01
    pattern = ' '.join(f'*{s}' for s in ARCHIVE_SUFFIXES + ('.001', '.r00', '.z01'))
    if picker() and os.name != 'nt':
        try:
            result = subprocess.run([picker(), '--getopenfilename', start,
                                     f"{pattern}|{t('dialog.archives')}", '--title', APP_NAME],
                                    capture_output=True, text=True)
            return result.stdout.strip() or None
        except OSError:
            pass
    from tkinter import filedialog
    return filedialog.askopenfilename(title=APP_NAME, initialdir=start,
                                      filetypes=[(t('dialog.archives'), pattern),
                                                 (t('dialog.all_files'), "*")]) or None


def pick_files(start: str) -> List[str]:
    if picker() and os.name != 'nt':
        try:
            result = subprocess.run([picker(), '--getopenfilename', start, '--multiple',
                                     '--separate-output', '--title', APP_NAME],
                                    capture_output=True, text=True)
            return [line for line in result.stdout.splitlines() if line.strip()]
        except OSError:
            pass
    from tkinter import filedialog
    return list(filedialog.askopenfilenames(title=APP_NAME, initialdir=start))


def pick_folder(start: str) -> Optional[str]:
    if picker() and os.name != 'nt':
        try:
            result = subprocess.run([picker(), '--getexistingdirectory', start,
                                     '--title', APP_NAME], capture_output=True, text=True)
            return result.stdout.strip() or None
        except OSError:
            pass
    from tkinter import filedialog
    return filedialog.askdirectory(title=APP_NAME, initialdir=start) or None


def show_in_file_manager(path: str) -> None:
    """Open a folder (or a file's folder) in the default file manager."""
    try:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if shutil.which('xdg-open'):
            subprocess.Popen(['xdg-open', folder], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("could not open %s: %s", path, exc)


def picker():
    """The file dialog to run: spark-pick (Spark Files' picker, through the desktop portal).
    None: use Tk's own dialog."""
    return shutil.which('spark-pick')
