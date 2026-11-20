"""Heroic: installed Epic, GOG and Amazon games from Heroic's own files, read only.

Heroic's folder is ~/.config/heroic, or ~/.var/app/com.heroicgameslauncher.hgl/config/heroic
for the Flatpak. Inside it:

  legendaryConfig/legendary/installed.json   Epic:   {"<appName>": {title, install_path, ...}}
  gog_store/installed.json                   GOG:    {"installed": [{appName, install_path}]}
  nile_config/nile/installed.json            Amazon: [{"id", "path"}]
  store_cache/<store>_library.json           titles and art URLs for each store
  images-cache/<sha256 of the art URL>       art Heroic already downloaded
  store/timestamp.json                       playtime: {"<appName>": {lastPlayed, totalPlayed}}
"""

import hashlib
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from . import HEROIC_FLATPAK
from .core import Game, log, read_json

# store -> (runner Heroic's links use, installed.json under the Heroic folder, library caches)
STORES = {
    'epic': ('legendary', ('legendaryConfig', 'legendary', 'installed.json'),
             (('store_cache', 'legendary_library.json'),)),
    'gog': ('gog', ('gog_store', 'installed.json'),
            (('store_cache', 'gog_library.json'), ('gog_store', 'library.json'))),
    'amazon': ('nile', ('nile_config', 'nile', 'installed.json'),
               (('store_cache', 'nile_library.json'), ('nile_config', 'nile', 'library.json'))),
}


class FormatError(ValueError):
    pass


def roots(home: str) -> List[Tuple[str, bool]]:
    found = []
    for path, flatpak in ((os.path.join(home, '.var', 'app', HEROIC_FLATPAK, 'config', 'heroic'),
                           True),
                          (os.path.join(home, '.config', 'heroic'), False)):
        if os.path.isdir(path):
            found.append((path, flatpak))
    return found


def _installed(store: str, data: Any) -> List[Dict[str, str]]:
    """Normalise each store's installed.json to [{app, title, path, platform}]."""
    out = []
    if store == 'epic':
        if not isinstance(data, dict):
            raise FormatError("Epic installed.json is not an object")
        for app, info in data.items():
            if not isinstance(info, dict) or info.get('is_dlc'):
                continue
            out.append({'app': info.get('app_name') or app, 'title': info.get('title') or '',
                        'path': info.get('install_path') or '',
                        'platform': info.get('platform') or ''})
    elif store == 'gog':
        items = data.get('installed') if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise FormatError("GOG installed.json has no installed list")
        for info in items:
            if not isinstance(info, dict) or info.get('is_dlc') or not info.get('appName'):
                continue
            out.append({'app': str(info['appName']), 'title': info.get('title') or '',
                        'path': info.get('install_path') or '',
                        'platform': info.get('platform') or ''})
    else:
        if not isinstance(data, list):
            raise FormatError("Amazon installed.json is not a list")
        for info in data:
            if not isinstance(info, dict) or not info.get('id'):
                continue
            out.append({'app': str(info['id']), 'title': '', 'path': info.get('path') or '',
                        'platform': 'windows'})
    return out


def _library(root: str, caches) -> Dict[str, Dict[str, str]]:
    """app -> {title, art} from Heroic's library caches (several shapes across versions)."""
    out: Dict[str, Dict[str, str]] = {}
    for parts in caches:
        data = read_json(os.path.join(root, *parts))
        if isinstance(data, dict):
            items = data.get('library') or data.get('games') or []
        elif isinstance(data, list):
            items = data
        else:
            continue
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            app = item.get('app_name') or item.get('id')
            if not app or str(app) in out:
                continue
            product = item.get('product') if isinstance(item.get('product'), dict) else {}
            title = item.get('title') or product.get('title') or ''
            art = item.get('art_square') or item.get('art_cover') or ''
            out[str(app)] = {'title': title, 'art': art}
    return out


def cached_image(root: str, url: str) -> str:
    """Heroic names each downloaded image by the SHA-256 of its URL."""
    if not url:
        return ''
    if url.startswith('file://'):
        path = url[7:]
        return path if os.path.isfile(path) else ''
    path = os.path.join(root, 'images-cache', hashlib.sha256(url.encode('utf-8')).hexdigest())
    return path if os.path.isfile(path) else ''


def _time(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value / 1000 if value > 1e11 else value)
    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
        except ValueError:
            return 0
    return 0


def play_stats(root: str) -> Dict[str, Tuple[int, int]]:
    data = read_json(os.path.join(root, 'store', 'timestamp.json'), {})
    stats = {}
    if isinstance(data, dict):
        for app, info in data.items():
            if isinstance(info, dict):
                minutes = info.get('totalPlayed') or 0
                stats[app] = (int(minutes) if isinstance(minutes, (int, float)) else 0,
                              _time(info.get('lastPlayed')))
    return stats


def scan(home: str, watch: List[str]) -> List[Game]:
    games: Dict[str, Game] = {}
    for root, flatpak in roots(home):
        stats = play_stats(root)
        watch.append(os.path.join(root, 'store', 'timestamp.json'))
        for store, (runner, installed_parts, caches) in STORES.items():
            path = os.path.join(root, *installed_parts)
            watch.append(path)
            data = read_json(path)
            if data is None:
                continue
            try:
                installed = _installed(store, data)
            except FormatError as exc:
                log.warning("heroic: %s changed format, skipped: %s", path, exc)
                continue
            library = _library(root, caches) if installed else {}
            for item in installed:
                key = f'{store}:{item["app"]}'
                if key in games:
                    continue
                info = library.get(item['app'], {})
                title = item['title'] or info.get('title') or \
                    os.path.basename(item['path'].rstrip('/')) or item['app']
                minutes, last = stats.get(item['app'], (0, 0))
                games[key] = Game(key=key, title=title, source=store, install_dir=item['path'],
                                  playtime=minutes, last_played=last,
                                  cover=cached_image(root, info.get('art', '')), flatpak=flatpak,
                                  store_id=item['app'],
                                  launch={'runner': runner, 'app': item['app'],
                                          'flatpak': flatpak})
    return list(games.values())
