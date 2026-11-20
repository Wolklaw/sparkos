"""Folders, the log, small file helpers, and numbers for people."""

import json
import locale
import logging
import os
import re
import shutil
import sys
import unicodedata
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)


# ─── Folders (XDG) ───────────────────────────────────────────

def _base(variable: str, fallback: str) -> str:
    return os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)


def data_home() -> str:
    return _base('XDG_DATA_HOME', os.path.join('.local', 'share'))


def data_dir() -> str:
    """~/.local/share/spark-run: Wine, the prefixes, the run-once folder."""
    return os.path.join(data_home(), APP_SLUG)


def runtime_dir() -> str:
    """Where downloaded Wine, Wine Mono and DXVK are unpacked."""
    return os.path.join(data_dir(), 'runtime')


def prefixes_dir() -> str:
    """One Wine prefix (a Windows C: drive and registry) per installed app."""
    return os.path.join(data_dir(), 'prefixes')


def run_once_prefix() -> str:
    """The shared prefix "Run once" uses, so a quick run doesn't wait for a new one."""
    return os.path.join(data_dir(), 'run-once')


def applications_dir() -> str:
    return os.path.join(data_home(), 'applications')


def config_dir() -> str:
    return os.path.join(_base('XDG_CONFIG_HOME', '.config'), APP_SLUG)


def state_dir() -> str:
    """Logs: Spark Run's own and one per installed app."""
    return os.path.join(_base('XDG_STATE_HOME', os.path.join('.local', 'state')), APP_SLUG)


def cache_dir() -> str:
    """Downloads in progress."""
    return os.path.join(_base('XDG_CACHE_HOME', '.cache'), APP_SLUG)


def ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def setup_logging(verbose: bool = False) -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(ensure(state_dir()), f'{APP_SLUG}.log'),
                                      maxBytes=512 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    if verbose:
        err = logging.StreamHandler(sys.stderr)
        err.setFormatter(logging.Formatter('spark-run: %(message)s'))
        log.addHandler(err)
    log.info("--- %s %s (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


def read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return {}


def write_json(path: str, data: Dict[str, Any]) -> None:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    ensure(os.path.dirname(path))
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(path + '.tmp', path)


def write_text(path: str, text: str, mode: int = 0o644) -> None:
    ensure(os.path.dirname(path))
    with open(path + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.chmod(path + '.tmp', mode)
    os.replace(path + '.tmp', path)


def folder_size(path: str) -> int:
    """Bytes on disk under path, not following links (a prefix's Z: drive links to /)."""
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
                total += st.st_blocks * 512 if hasattr(st, 'st_blocks') else st.st_size
            except OSError:
                pass
    return total


def remove_tree(path: str) -> None:
    """Delete a folder without following symlinks out of it (prefixes link to / and ~)."""
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_RUN_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    try:
        with open(os.path.join(_base('XDG_CONFIG_HOME', '.config'), 'kdeglobals'),
                  encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']"""
    lang = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or \
        os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


# ─── Names ───────────────────────────────────────────────────

def slugify(name: str) -> str:
    """'Notepad++ 8.6 (64-bit)' -> 'notepad-8-6-64-bit'; folder and menu-entry safe."""
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return text[:48].strip('-') or 'app'


_NOISE = re.compile(
    r'(?i)([ ._-]*(setup|installer|install|x64|x86|amd64|win64|win32|64[ -]?bit|32[ -]?bit|'
    r'portable|full|offline|web|windows|win|release|final|v?\d+(?:[._]\d+)+[a-z]?|\([^)]*\)))+$')


def name_from_file(filename: str) -> str:
    """'NotepadPlusPlus-8.6.2-Setup-x64.exe' -> 'NotepadPlusPlus'; a guess, used last."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    previous = None
    while previous != stem:
        previous = stem
        stem = _NOISE.sub('', stem)
    stem = re.sub(r'[_]+', ' ', stem).strip(' .-')
    return stem or os.path.splitext(os.path.basename(filename))[0]


# ─── Numbers for people ──────────────────────────────────────

def size(n: Optional[float], digits: int = 0) -> str:
    """Bytes, in the units Windows and Dolphin show (1 MB = 1024 KB)."""
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.{digits}f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
