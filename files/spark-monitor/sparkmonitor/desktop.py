"""Desktop entries: an app's name and icon from its .desktop file, found by its ID."""

import locale
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .source import Source, read_text


def parse_desktop(text: str, group: str = 'Desktop Entry') -> Dict[str, str]:
    """The keys of one group of a desktop file (keys with [locale] are kept as written)."""
    out: Dict[str, str] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line[1:-1]
            continue
        if current != group or '=' not in line:
            continue
        key, _, value = line.partition('=')
        out.setdefault(key.strip(), value.strip())
    return out


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']: which Name[..] of a desktop entry to show. SPARK_LANG
    (lang.py) wins, so app names follow the window's language."""
    forced = (os.environ.get('SPARK_LANG') or '').strip().lower()
    if forced in ('en', 'fr'):
        return [forced]
    lang = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


def localized(keys: Dict[str, str], key: str, langs: List[str]) -> str:
    for lang in langs:
        if f'{key}[{lang}]' in keys:
            return keys[f'{key}[{lang}]']
    return keys.get(key, '')


@dataclass
class Entry:
    id: str
    path: str
    name: str
    icon: Optional[str]
    no_display: bool
    keys: Dict[str, str]


class DesktopIndex:
    """Finds desktop entries by ID and remembers the answer (including "not found")."""

    def __init__(self, src: Source):
        self.src = src
        self.dirs = [os.path.join(d, 'applications') for d in [src.data_home] + src.data_dirs]
        self.langs = languages()
        self._cache: Dict[str, Optional[Entry]] = {}

    def lookup(self, desktop_id: Optional[str]) -> Optional[Entry]:
        if not desktop_id:
            return None
        if desktop_id in self._cache:
            return self._cache[desktop_id]
        found = None
        candidates = [desktop_id]
        if '-' in desktop_id:      # app-<launcher>-<id>: drop a launcher prefix
            candidates.append(desktop_id.split('-', 1)[1])
        for cand in candidates:
            for d in self.dirs:
                path = os.path.join(d, cand + '.desktop')
                if not os.path.isfile(path):
                    # desktop IDs map '-' to subfolders: kde-foo.desktop may be kde/foo.desktop
                    path = os.path.join(d, cand.replace('-', '/', 1) + '.desktop')
                    if '-' not in cand or not os.path.isfile(path):
                        continue
                keys = parse_desktop(read_text(path) or '')
                if not keys:
                    continue
                found = Entry(id=cand, path=path,
                              name=localized(keys, 'Name', self.langs) or cand,
                              icon=keys.get('Icon') or None,
                              no_display=keys.get('NoDisplay', '').lower() == 'true'
                              or keys.get('Hidden', '').lower() == 'true',
                              keys=keys)
                break
            if found:
                break
        self._cache[desktop_id] = found
        return found


ICON_SIZES = (32, 24, 48, 22, 64, 16, 128, 256)


def find_icon(src: Source, icon: Optional[str]) -> Optional[str]:
    """A PNG for an icon name (Tk can't draw SVG): hicolor, the Flatpak exports, pixmaps."""
    if not icon:
        return None
    if os.path.isabs(icon):
        path = src.host_path(icon)
        return path if path.lower().endswith('.png') and os.path.isfile(path) else None
    if not re.fullmatch(r'[\w.+-]+', icon):
        return None
    bases = [os.path.join(src.data_home, 'icons')] + \
        [os.path.join(d, 'icons') for d in src.data_dirs] + \
        [os.path.join(src.home, '.icons')]
    for size in ICON_SIZES:
        for base in bases:
            path = os.path.join(base, 'hicolor', f'{size}x{size}', 'apps', icon + '.png')
            if os.path.isfile(path):
                return path
    for d in src.data_dirs:
        path = os.path.join(d, 'pixmaps', icon + '.png')
        if os.path.isfile(path):
            return path
    return None
