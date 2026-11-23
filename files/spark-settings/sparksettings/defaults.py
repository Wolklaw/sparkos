"""Default apps with xdg-mime: which app opens what."""

import configparser
import glob
import os
from typing import Dict, List, Tuple

from .core import out, run, xdg_config_home

# key, English label, MIME types set together (the first one is what's asked)
CATEGORIES: List[Tuple[str, str, List[str]]] = [
    ('browser', "Web browser", ['x-scheme-handler/http', 'x-scheme-handler/https', 'text/html']),
    ('mail', "Email", ['x-scheme-handler/mailto']),
    ('files', "Folders", ['inode/directory']),
    ('text', "Text files", ['text/plain']),
    ('images', "Pictures", ['image/png', 'image/jpeg', 'image/gif', 'image/webp']),
    ('video', "Videos", ['video/mp4', 'video/x-matroska', 'video/webm']),
    ('music', "Music", ['audio/mpeg', 'audio/flac', 'audio/ogg']),
    ('archives', "Archives", ['application/zip', 'application/x-7z-compressed',
                              'application/x-tar']),
]


def app_dirs() -> List[str]:
    env = os.environ.get('SPARK_SETTINGS_APPDIRS')
    if env:
        return [d for d in env.split(os.pathsep) if d]
    data = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return [os.path.join(data, 'applications'), '/usr/local/share/applications',
            '/usr/share/applications', '/var/lib/flatpak/exports/share/applications',
            os.path.expanduser('~/.local/share/flatpak/exports/share/applications')]


class App:
    def __init__(self, id_: str, name: str, mimes: List[str]):
        self.id, self.name, self.mimes = id_, name, mimes


def installed_apps() -> Dict[str, App]:
    apps: Dict[str, App] = {}
    for folder in app_dirs():
        for path in sorted(glob.glob(os.path.join(folder, '*.desktop'))):
            id_ = os.path.basename(path)
            if id_ in apps:
                continue
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.optionxform = str
            try:
                cp.read(path, encoding='utf-8')
                e = cp['Desktop Entry']
            except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
                continue
            if e.get('Type') != 'Application' or e.get('Hidden') == 'true':
                continue
            apps[id_] = App(id_, e.get('Name', id_[:-8]),
                            [m for m in e.get('MimeType', '').split(';') if m])
    return apps


def candidates(mimes: List[str], apps: Dict[str, App]) -> List[App]:
    """The apps that handle the category's first type and are visible in the menu."""
    want = mimes[0]
    found = [a for a in apps.values() if want in a.mimes]
    return sorted(found, key=lambda a: a.name.lower())


def current(mime: str) -> str:
    return out(['xdg-mime', 'query', 'default', mime]).strip()


def set_default(app_id: str, mimes: List[str]) -> bool:
    return run(['xdg-mime', 'default', app_id, *mimes])[0] == 0


# the terminal is not a MIME type: Plasma and xdg-terminal-exec read these
def terminal_get() -> str:
    from . import core
    return core.kread('kdeglobals', 'General', 'TerminalService')


def terminal_set(app_id: str, command: str) -> bool:
    from . import core
    ok = core.kwrite('kdeglobals', 'General', 'TerminalService', app_id) == 0
    return ok and core.kwrite('kdeglobals', 'General', 'TerminalApplication', command) == 0


def terminal_candidates(apps: Dict[str, App]) -> List[App]:
    cats = {}
    for folder in app_dirs():
        for path in glob.glob(os.path.join(folder, '*.desktop')):
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    if 'TerminalEmulator' in f.read():
                        cats[os.path.basename(path)] = True
            except OSError:
                pass
    return sorted((apps[i] for i in cats if i in apps), key=lambda a: a.name.lower())
