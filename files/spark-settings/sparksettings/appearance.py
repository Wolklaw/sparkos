"""Appearance: wallpaper, cursor and window animations. The wallpaper goes to shell.json (the
Spark shell redraws it), the cursor to a line in compositor.conf (the compositor draws it), and
the animation switch stays in ~/.config/spark/appearance.json ("animations", a bool) where every
Spark app reads it. Text size and fonts: Spark Fonts."""

import glob
import os
from typing import Dict, List, Tuple

from . import core

CURSOR_SIZES = (24, 32, 36, 48, 64)


def _dirs(sub: str) -> List[str]:
    env = os.environ.get('SPARK_SETTINGS_SHARE_DIRS')
    if env:
        return [os.path.join(d, sub) for d in env.split(os.pathsep) if d]
    data = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return [os.path.join(data, sub), f'/usr/share/{sub}']


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


def get() -> Dict[str, object]:
    saved = core.spark_load('appearance')
    return {'wallpaper': core.spark_load('shell').get('wallpaper') or saved.get('wallpaper', ''),
            'cursor': saved.get('cursor') or os.environ.get('XCURSOR_THEME', ''),
            'cursor_size': int(saved.get('cursor_size') or os.environ.get('XCURSOR_SIZE') or 24),
            'animations': saved.get('animations', True)}


def set_wallpaper(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    ok = core.spark_save('appearance', wallpaper=path)
    return core.spark_save('shell', wallpaper=path) and ok      # the shell redraws every screen


def set_cursor(theme: str, size: int) -> bool:
    ok = core.spark_save('appearance', cursor=theme, cursor_size=size)
    from . import inputdev      # a cursor line in compositor.conf, then SIGHUP
    return inputdev.compositor_cursor(theme, size) and ok


def set_animations(on: bool) -> bool:
    return core.spark_save('appearance', animations=bool(on))
