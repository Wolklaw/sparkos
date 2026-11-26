"""Everything below the interface that every part shares: the Game record, folders, settings,
logging, and starting other programs."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, LAUNCHER_OF, VERSION

log = logging.getLogger(APP_SLUG)


# ─── The game record ──────────────────────────────────────────

@dataclass
class Game:
    key: str                    # unique: "steam:620", "epic:Fortnite", "lutris:3", "own:ab12"
    title: str
    source: str                 # steam, epic, gog, amazon, lutris, own (see SOURCES)
    install_dir: str = ''
    playtime: int = 0           # minutes, as the launcher counts them
    last_played: int = 0        # unix seconds, as the launcher records it
    cover: str = ''             # the launcher's own cover image, full size
    launch: Dict[str, Any] = field(default_factory=dict)   # what launch.command() needs
    flatpak: bool = False       # the launcher is the Flatpak one
    store_id: str = ''          # the store's own ID (Steam appid...), for the anti-cheat list
    anticheat: str = ''         # "Denied" or "Broken" when AreWeAntiCheatYet lists it so
    installed: bool = True      # False: owned in a store but not installed yet

    @property
    def launcher(self) -> str:
        if (self.launch or {}).get('spark'):      # Spark Games itself installs and starts it
            return 'spark'
        return LAUNCHER_OF.get(self.source, self.source)

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'Game':
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


def sort_recent(games: List[Game]) -> List[Game]:
    """Most recently played first; never-played games after, by title."""
    return sorted(games, key=lambda g: (-(g.last_played or 0), g.title.casefold()))


def sort_title(games: List[Game]) -> List[Game]:
    return sorted(games, key=lambda g: (sort_name(g.title), g.key))


def sort_name(title: str) -> str:
    t = title.casefold()
    return t[4:] if t.startswith('the ') else t


def search_key(text: str) -> str:
    """Lower case, letters and digits only: "Baldur's Gate 3" -> "baldursgate3"."""
    return re.sub(r'[\W_]+', '', text.casefold())


def matches(game: Game, query: str) -> bool:
    if not query:
        return True
    words = [search_key(w) for w in query.split()]
    hay = search_key(game.title)
    return all(w in hay for w in words if w)


# ─── Folders, settings, logging ───────────────────────────────

def home() -> str:
    return os.path.expanduser('~')


def _xdg_dir(variable: str, fallback: str) -> str:
    base = os.environ.get(variable) or os.path.join(home(), fallback)
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


def data_dir() -> str:
    return _xdg_dir('XDG_DATA_HOME', os.path.join('.local', 'share'))


def private_dir(path: str) -> str:
    """A folder only this user can open (mode 0700), made if it isn't there."""
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def accounts_dir() -> str:
    """Store sign-ins (tokens). Mode 0700; the files in it are 0600. Never logged."""
    return private_dir(os.path.join(config_dir(), 'accounts'))


def pick_folder(start: str) -> Optional[str]:
    """The desktop's folder dialog (spark-pick: Spark Files through the desktop portal), Tk's as a fallback."""
    if picker() and os.name != 'nt':
        try:
            result = subprocess.run([picker(), '--getexistingdirectory', start, '--title',
                                     APP_NAME], capture_output=True, text=True)
            return result.stdout.strip() or None
        except OSError:
            pass
    from tkinter import filedialog
    return filedialog.askdirectory(title=APP_NAME, initialdir=start) or None


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


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return default


def write_json(path: str, data: Any) -> bool:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write %s: %s", path, exc)
        return False


def load_settings() -> Dict[str, Any]:
    data = read_json(os.path.join(config_dir(), 'config.json'), {})
    return data if isinstance(data, dict) else {}


def save_settings(data: Dict[str, Any]) -> None:
    write_json(os.path.join(config_dir(), 'config.json'), data)


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_GAMES_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def mtime(path: str) -> Optional[float]:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


# ─── Other programs ───────────────────────────────────────────

def which(name: str) -> Optional[str]:
    return shutil.which(name)


def spawn(argv: List[str], env: Optional[Dict[str, str]] = None,
          cwd: Optional[str] = None) -> Optional[str]:
    """Start a program detached from this one. Returns an error message, or None."""
    try:
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        subprocess.Popen(argv, env=full_env, cwd=cwd or None, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return None
    except OSError as exc:
        log.warning("could not start %s: %s", argv[0], exc)
        return str(exc)


def open_uri(target: str) -> Optional[str]:
    """Open a folder or a link with the desktop's handler (Dolphin for folders)."""
    if os.name == 'nt':                      # Windows dev runs only
        try:
            os.startfile(target)             # type: ignore[attr-defined]
            return None
        except OSError as exc:
            return str(exc)
    opener = which('xdg-open')
    if not opener:
        return "xdg-open is not installed"
    return spawn([opener, target])


def flatpak_installed(app_id: str) -> bool:
    """Whether a Flatpak app is installed, for this user or system-wide (no flatpak call)."""
    for base in (os.path.join(home(), '.local', 'share', 'flatpak'), '/var/lib/flatpak'):
        if os.path.isdir(os.path.join(base, 'app', app_id)):
            return True
    return False


def pick_program(start: str) -> Optional[str]:
    """The desktop's file dialog (spark-pick: Spark Files through the desktop portal), Tk's as a fallback."""
    if picker() and os.name != 'nt':
        try:
            result = subprocess.run([picker(), '--getopenfilename', start, '--title', APP_NAME],
                                    capture_output=True, text=True)
            return result.stdout.strip() or None
        except OSError:
            pass
    from tkinter import filedialog
    return filedialog.askopenfilename(title=APP_NAME, initialdir=start) or None


def is_windows_program(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in ('.exe', '.msi', '.bat', '.lnk')


# ─── Time ─────────────────────────────────────────────────────

def now() -> int:
    return int(time.time())


def picker():
    """The file dialog to run: spark-pick (Spark Files' picker, through the desktop portal), or
    kdialog on a Plasma machine that doesn't have spark-pick. None: use Tk's own dialog."""
    return shutil.which('spark-pick') or shutil.which('kdialog')
