"""The sidebar's places: your folders, the Windows drives SparkOS mounts at /var/mnt/<letter>,
removable drives, the Trash and the folders you pinned."""

import os
import re
import shutil
from typing import Dict, List, Optional

from .core import home

TRASH = 'trash:///'                 # the Trash isn't a real folder; the view lists it itself


class Place:
    __slots__ = ('key', 'label', 'path', 'icon', 'removable', 'device', 'unmounted', 'uuid')

    def __init__(self, key: str, label: str, path: str, icon: str = 'folder',
                 removable: bool = False, device: str = '', unmounted: bool = False,
                 uuid: str = ''):
        self.key, self.label, self.path, self.icon = key, label, path, icon
        self.removable, self.device, self.unmounted, self.uuid = \
            removable, device, unmounted, uuid

    def __repr__(self) -> str:
        return f"Place({self.key!r}, {self.path!r})"


def user_dirs() -> Dict[str, str]:
    """XDG_*_DIR from ~/.config/user-dirs.dirs (the names change with the language: a French
    desktop has ~/Bureau and ~/Téléchargements)."""
    h = home()
    out = {'DESKTOP': os.path.join(h, 'Desktop'), 'DOCUMENTS': os.path.join(h, 'Documents'),
           'DOWNLOAD': os.path.join(h, 'Downloads'), 'PICTURES': os.path.join(h, 'Pictures'),
           'MUSIC': os.path.join(h, 'Music'), 'VIDEOS': os.path.join(h, 'Videos')}
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(h, '.config')
    try:
        with open(os.path.join(base, 'user-dirs.dirs'), encoding='utf-8') as f:
            for line in f:
                m = re.match(r'^\s*XDG_([A-Z]+)_DIR\s*=\s*"(.*)"\s*$', line)
                if m:
                    value = m.group(2).replace('$HOME', h)
                    if os.path.isabs(value) and os.path.normpath(value) != os.path.normpath(h):
                        out[m.group(1)] = value
    except OSError:
        pass
    return out


def home_places(t) -> List[Place]:
    dirs = user_dirs()
    places = [Place('home', t('place.home'), home(), 'home')]
    for key, name, icon in (('DESKTOP', 'place.desktop', 'desktop'),
                            ('DOCUMENTS', 'place.documents', 'document'),
                            ('DOWNLOAD', 'place.downloads', 'download'),
                            ('PICTURES', 'place.pictures', 'image'),
                            ('MUSIC', 'place.music', 'audio'),
                            ('VIDEOS', 'place.videos', 'video')):
        path = dirs.get(key)
        if path and os.path.isdir(path):
            places.append(Place(key.lower(), t(name), path, icon))
    games = os.path.join(home(), 'Games')
    if os.path.isdir(games):
        places.append(Place('games', t('place.games'), games, 'game'))
    return places


def _mounts() -> List[List[str]]:
    out = []
    try:
        with open('/proc/self/mounts', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    out.append([p.replace('\\040', ' ').replace('\\011', '\t')
                                for p in parts[:4]])
    except OSError:
        pass
    return out


def _labels() -> Dict[str, str]:
    """/dev/sdb1 -> 'Games', from /dev/disk/by-label."""
    out = {}
    folder = '/dev/disk/by-label'
    try:
        for name in os.listdir(folder):
            target = os.path.realpath(os.path.join(folder, name))
            label = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), name)
            out[target] = label
    except OSError:
        pass
    return out


def windows_drives(t, mounts_root: str = '/var/mnt') -> List[Place]:
    """C:, D:... : one-letter folders in /var/mnt (SparkOS mounts every Windows partition
    there at boot). Shown while mounted."""
    out = []
    try:
        names = sorted(os.listdir(mounts_root))
    except OSError:
        return out
    mounted = {m[1]: m[0] for m in _mounts()}
    labels = _labels()
    for name in names:
        if not re.fullmatch(r'[a-z]', name):
            continue
        path = os.path.join(mounts_root, name)
        if path not in mounted and not os.path.ismount(path):
            continue
        device = mounted.get(path, '')
        label = labels.get(os.path.realpath(device), '') if device else ''
        text = t('place.drive', letter=name.upper())
        if label:
            text = f"{text} {label}"
        out.append(Place(f'drive-{name}', text, path, 'drive', device=device))
    return out


def removable_drives(t) -> List[Place]:
    """USB sticks, SD cards and other drives the desktop mounted for you
    (/run/media/<you>/<label>)."""
    out = []
    user = os.environ.get('USER') or os.path.basename(home())
    roots = (f'/run/media/{user}/', '/media/')
    for device, target, _fstype, *_rest in _mounts():
        if target.startswith(roots) and target.count('/') >= 3:
            label = os.path.basename(target)
            out.append(Place(f'mount-{target}', label, target, 'usb', removable=True,
                             device=device))
    return out


def pinned_places(paths: List[str]) -> List[Place]:
    out = []
    for path in paths:
        label = os.path.basename(path.rstrip('/')) or path
        out.append(Place(f'pin-{path}', label, path, 'pin'))
    return out


def free_space(path: str) -> Optional[tuple]:
    """(free, total) bytes, or None."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free, usage.total
    except OSError:
        return None


def mount_point(path: str) -> str:
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path
