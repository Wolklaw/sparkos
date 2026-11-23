"""Apps that open at sign-in: the .desktop files in ~/.config/autostart and /etc/xdg/autostart.
Switching one off writes a copy in your own folder with Hidden=true, which is how every desktop
reads "off"; switching on removes that copy (or writes one without it if it was your own)."""

import configparser
import glob
import os
from typing import List

from .core import xdg_config_home


def system_dirs() -> List[str]:
    env = os.environ.get('SPARK_SETTINGS_AUTOSTART_DIRS')
    if env:
        return [d for d in env.split(os.pathsep) if d]
    return ['/etc/xdg/autostart', '/usr/share/autostart']


def user_dir() -> str:
    return os.path.join(xdg_config_home(), 'autostart')


class Item:
    def __init__(self, file: str, name: str, enabled: bool, comment: str):
        self.file, self.name, self.enabled, self.comment = file, name, enabled, comment


def _read(path: str):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read(path, encoding='utf-8')
        return cp['Desktop Entry']
    except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
        return None


def items() -> List[Item]:
    found = {}
    for folder in [*system_dirs(), user_dir()]:      # the user's copy wins
        for path in glob.glob(os.path.join(folder, '*.desktop')):
            e = _read(path)
            if e is None:
                continue
            file = os.path.basename(path)
            hidden = e.get('Hidden', '').lower() == 'true' or \
                e.get('X-GNOME-Autostart-enabled', '').lower() == 'false'
            shown = e.get('OnlyShowIn')
            if shown and 'KDE' not in shown.split(';'):
                continue
            found[file] = Item(file, e.get('Name[fr]') if os.environ.get('SPARK_LANG') == 'fr' and
                               e.get('Name[fr]') else e.get('Name', file[:-8]), not hidden,
                               e.get('Comment', ''))
    return sorted(found.values(), key=lambda i: i.name.lower())


def set_enabled(item: Item, on: bool) -> bool:
    os.makedirs(user_dir(), exist_ok=True)
    mine = os.path.join(user_dir(), item.file)
    source = mine if os.path.exists(mine) else next(
        (os.path.join(d, item.file) for d in system_dirs()
         if os.path.exists(os.path.join(d, item.file))), None)
    if source is None:
        return False
    try:
        with open(source, encoding='utf-8', errors='replace') as f:
            lines = [l for l in f.read().splitlines()
                     if not l.startswith(('Hidden=', 'X-GNOME-Autostart-enabled='))]
        if not on:
            at = next((i for i, l in enumerate(lines) if l.strip() == '[Desktop Entry]'), -1)
            lines.insert(at + 1, 'Hidden=true')
        with open(mine, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        item.enabled = on
        return True
    except OSError:
        return False
