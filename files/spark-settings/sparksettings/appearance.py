"""Appearance: colour scheme and accent, wallpaper, cursor, window animations and blur.
What you pick is saved in ~/.config/spark/appearance.json (the Spark shell reads it) and applied
to the Plasma session through plasma.py. Text size and fonts: Spark Fonts."""

import configparser
import glob
import os
from typing import Dict, List, Tuple

from . import core, plasma

ACCENTS: List[Tuple[str, str]] = [   # name, colour
    ("Mint", '#3de8c8'), ("Cyan", '#2ad4ff'), ("Magenta", '#ff3df0'), ("Gold", '#ffc247'),
    ("Blue", '#3d86ff'), ("Red", '#ff4d5e'),
]
CURSOR_SIZES = (24, 32, 36, 48, 64)


def _dirs(sub: str) -> List[str]:
    env = os.environ.get('SPARK_SETTINGS_SHARE_DIRS')
    if env:
        return [os.path.join(d, sub) for d in env.split(os.pathsep) if d]
    data = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return [os.path.join(data, sub), f'/usr/share/{sub}']


def color_schemes() -> List[Tuple[str, str]]:
    """(name, file id): the .colors files KDE and Spark ship, e.g. ("SparkOS", "SparkOS")."""
    found: Dict[str, str] = {}
    for d in _dirs('color-schemes'):
        for path in sorted(glob.glob(os.path.join(d, '*.colors'))):
            ident = os.path.basename(path)[:-7]
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.optionxform = str
            try:
                cp.read(path, encoding='utf-8')
                name = cp.get('General', 'Name', fallback=ident)
            except (configparser.Error, UnicodeDecodeError):
                name = ident
            found.setdefault(ident, name)
    return sorted(((n, i) for i, n in found.items()), key=lambda t: t[0].lower())


def wallpapers() -> List[Tuple[str, str]]:
    """(name, picture path) from /usr/share/wallpapers/<name>/contents/images/ (the largest)."""
    found = []
    for d in _dirs('wallpapers'):
        for folder in sorted(glob.glob(os.path.join(d, '*'))):
            pics = [p for p in glob.glob(os.path.join(folder, 'contents', 'images', '*'))
                    if p.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.svg'))]
            if pics:
                found.append((os.path.basename(folder), max(pics, key=_pixels)))
    return found


def _pixels(path: str) -> int:
    import re
    m = re.search(r'(\d+)x(\d+)', os.path.basename(path))
    return int(m.group(1)) * int(m.group(2)) if m else 0


def cursor_themes() -> List[str]:
    names = set()
    for d in _dirs('icons') + [os.path.join(os.path.expanduser('~'), '.icons')]:
        for p in glob.glob(os.path.join(d, '*', 'cursors')):
            names.add(os.path.basename(os.path.dirname(p)))
    return sorted(names, key=str.lower)


SPARKWL = 'sparkwl' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')


def get() -> Dict[str, object]:
    saved = core.spark_load('appearance')
    if SPARKWL:      # the shell draws the wallpaper from shell.json; no KDE files to fall back to
        return {'scheme': saved.get('scheme') or '', 'accent': saved.get('accent', ''),
                'wallpaper': core.spark_load('shell').get('wallpaper') or saved.get('wallpaper', ''),
                'cursor': saved.get('cursor') or os.environ.get('XCURSOR_THEME', ''),
                'cursor_size': int(saved.get('cursor_size') or os.environ.get('XCURSOR_SIZE') or 24),
                'animations': saved.get('animations', True), 'blur': saved.get('blur', True)}
    fx = plasma.kwin_effects_get()
    return {'scheme': saved.get('scheme') or plasma.colorscheme_now(),
            'accent': saved.get('accent', ''), 'wallpaper': saved.get('wallpaper', ''),
            'cursor': saved.get('cursor') or core.kread('kcminputrc', 'Mouse', 'cursorTheme', ''),
            'cursor_size': int(saved.get('cursor_size') or core.kread('kcminputrc', 'Mouse', 'cursorSize', '24') or 24),
            'animations': saved.get('animations', fx['animations']),
            'blur': saved.get('blur', fx['blur'])}


def set_scheme(scheme: str, accent: str = '') -> bool:
    ok = core.spark_save('appearance', scheme=scheme, accent=accent)
    return plasma.apply_colorscheme(scheme, accent) and ok


def set_wallpaper(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    ok = core.spark_save('appearance', wallpaper=path)
    if SPARKWL:      # the shell watches shell.json and redraws every screen at once
        return core.spark_save('shell', wallpaper=path) and ok
    return plasma.apply_wallpaper(path) and ok


def set_cursor(theme: str, size: int) -> bool:
    ok = core.spark_save('appearance', cursor=theme, cursor_size=size)
    if SPARKWL:      # the compositor draws the cursor: a cursor line in compositor.conf, then SIGHUP
        from . import inputdev
        return inputdev.compositor_cursor(theme, size) and ok
    return plasma.apply_cursor(theme, size) and ok


def set_effects(animations: bool = None, blur: bool = None) -> bool:
    values = {k: v for k, v in (('animations', animations), ('blur', blur)) if v is not None}
    ok = core.spark_save('appearance', **values)
    return plasma.kwin_effects_set(animations, blur) and ok
