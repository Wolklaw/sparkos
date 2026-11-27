"""The shell's settings: ~/.config/spark/shell.json, written by Spark Settings, read here.

The file is the contract between the two:

    {
      "wallpaper": "/path/to/image.png",     # "" or missing: SparkOS's own wallpaper
      "wallpaper_mode": "fill",              # fill | fit | stretch | center
      "pinned": ["dev.wolklaw.SparkFiles.desktop", ...],   # desktop file ids, in order
      "panel_position": "bottom",            # bottom | top
      "tray_order": ["nm-applet", ...],      # tray item ids, in order; unknown ids go last
      "connect_widget": {"enabled": false,   # Spark Connect status in the tray (off by default)
                         "monitor": ""}      # connector name of the screen; "" = the tray's screen
    }

Any key may be missing; unknown keys are kept when the shell writes (it writes "pinned",
"tray_order" and "connect_widget"). The shell watches the file, so a change shows at once."""

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
    order = raw.get('tray_order')
    return {
        'wallpaper': wallpaper if isinstance(wallpaper, str) else '',
        'wallpaper_mode': mode if mode in MODES else 'fill',
        'panel_position': position if position in POSITIONS else 'bottom',
        'pinned': [p for p in pinned if isinstance(p, str)] if isinstance(pinned, list)
        else list(DEFAULT_PINNED),
        'tray_order': _strings(order),
        'connect_widget': clean_connect_widget(raw.get('connect_widget')),
    }


def _strings(value) -> list:
    """The strings of a list, without repeats; anything else is an empty list."""
    out = []
    for v in value if isinstance(value, list) else []:
        if isinstance(v, str) and v and v not in out:
            out.append(v)
    return out


def clean_connect_widget(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    monitor = raw.get('monitor')
    return {'enabled': raw.get('enabled') is True,
            'monitor': monitor.strip() if isinstance(monitor, str) else ''}


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


def save_keys(values: dict, path=None) -> None:
    """Merge `values` into the file, keeping every other key as it was."""
    path = path or config_path()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data.update(values)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.shell-')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, path)


def save_pinned(pinned, path=None) -> None:
    """Write the pinned list, keeping every other key as it was."""
    save_keys({'pinned': list(pinned)}, path)


def save_tray_order(order, path=None) -> None:
    """Write the tray order (item ids), keeping every other key as it was."""
    save_keys({'tray_order': _strings(list(order))}, path)


def save_connect_widget(enabled=None, monitor=None, path=None) -> dict:
    """Change the Spark Connect widget's settings (only the ones given), keeping every other key
    and the other widget setting as the file has them. Returns what was written."""
    path = path or config_path()
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    now = clean_connect_widget(raw.get('connect_widget') if isinstance(raw, dict) else None)
    if enabled is not None:
        now['enabled'] = bool(enabled)
    if monitor is not None:
        now['monitor'] = str(monitor)
    save_keys({'connect_widget': now}, path)
    return now
