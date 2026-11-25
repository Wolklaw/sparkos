"""The shell's settings: ~/.config/spark/shell.json, written by Spark Settings, read here.

The file is the contract between the two:

    {
      "wallpaper": "/path/to/image.png",     # "" or missing: SparkOS's own wallpaper
      "wallpaper_mode": "fill",              # fill | fit | stretch | center
      "pinned": ["dev.wolklaw.SparkFiles.desktop", ...],   # desktop file ids, in order
      "panel_position": "bottom"             # bottom | top
    }

Any key may be missing; unknown keys are kept when the shell writes (it only writes "pinned").
The shell watches the file, so a change shows at once."""

import json
import os
import tempfile

DEFAULT_WALLPAPER = '/usr/share/wallpapers/SparkOS/contents/images/3840x2160.png'
MODES = ('fill', 'fit', 'stretch', 'center')
POSITIONS = ('bottom', 'top')
DEFAULT_PINNED = (
    'dev.wolklaw.SparkFiles.desktop', 'dev.wolklaw.SparkTerminal.desktop',
    'dev.wolklaw.SparkGames.desktop', 'dev.wolklaw.SparkSettings.desktop',
    'dev.wolklaw.SparkStore.desktop',
)


def config_dir() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'spark')


def config_path() -> str:
    return os.path.join(config_dir(), 'shell.json')


def state_dir() -> str:
    base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    return os.path.join(base, 'spark-shell')


def clean(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get('wallpaper_mode')
    position = raw.get('panel_position')
    pinned = raw.get('pinned')
    wallpaper = raw.get('wallpaper')
    return {
        'wallpaper': wallpaper if isinstance(wallpaper, str) else '',
        'wallpaper_mode': mode if mode in MODES else 'fill',
        'panel_position': position if position in POSITIONS else 'bottom',
        'pinned': [p for p in pinned if isinstance(p, str)] if isinstance(pinned, list)
        else list(DEFAULT_PINNED),
    }


def load(path=None) -> dict:
    try:
        with open(path or config_path(), encoding='utf-8') as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return clean({})


def wallpaper_file(cfg: dict) -> str:
    """The image to draw: the chosen one if it exists, else SparkOS's own, else ''."""
    for candidate in (os.path.expanduser(cfg.get('wallpaper') or ''), DEFAULT_WALLPAPER):
        if candidate and os.path.isfile(candidate):
            return candidate
    return ''


def save_pinned(pinned, path=None) -> None:
    """Write the pinned list, keeping every other key as it was."""
    path = path or config_path()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data['pinned'] = list(pinned)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.shell-')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, path)
