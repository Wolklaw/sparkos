"""Kernel anti-cheat warnings, from the public AreWeAntiCheatYet list (areweanticheatyet.com).

Online only, and optional (Settings). The list is downloaded at most once a week into
~/.cache/spark-games/anticheat.json. Offline with no copy, nothing is shown. Games are matched
by Steam appid, then by name. Only "Denied" (the developer blocks Linux) and "Broken" (the
anti-cheat doesn't work on Linux yet) are marked.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import APP_NAME, VERSION
from .core import Game, cache_dir, log, mtime, now, read_json, write_json

URL = 'https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/master/games.json'
SITE = 'areweanticheatyet.com'
MAX_AGE = 7 * 24 * 3600
MARKED = ('Denied', 'Broken')


def cache_path() -> str:
    return os.path.join(cache_dir(), 'anticheat.json')


def name_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', name.casefold().replace('&', 'and'))


def index(entries: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(steam appid -> status, name key -> status) for the marked statuses."""
    by_id: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    if not isinstance(entries, list):
        return by_id, by_name
    for e in entries:
        if not isinstance(e, dict) or e.get('status') not in MARKED:
            continue
        ids = e.get('storeIds') if isinstance(e.get('storeIds'), dict) else {}
        if ids.get('steam'):
            by_id[str(ids['steam'])] = e['status']
        if e.get('name'):
            by_name[name_key(str(e['name']))] = e['status']
    return by_id, by_name


def mark(games: List[Game], entries: Any) -> int:
    """Set game.anticheat from the list. Returns how many were marked."""
    by_id, by_name = index(entries)
    count = 0
    for game in games:
        status = ''
        if game.source == 'steam' and game.store_id in by_id:
            status = by_id[game.store_id]
        elif game.source != 'own':
            status = by_name.get(name_key(game.title), '')
        game.anticheat = status
        count += bool(status)
    return count


def cached() -> Optional[List[Any]]:
    data = read_json(cache_path())
    return data if isinstance(data, list) else None


def age() -> Optional[float]:
    stamp = mtime(cache_path())
    return None if stamp is None else now() - stamp


def fetch(timeout: float = 15.0) -> Optional[List[Any]]:
    """Download the list (run in a background thread). None when offline or on a bad answer."""
    request = urllib.request.Request(URL, headers={'User-Agent': f'{APP_NAME}/{VERSION}'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(8 * 1024 * 1024).decode('utf-8'))
    except (OSError, ValueError) as exc:
        log.info("anti-cheat list not downloaded: %s", exc)
        return None
    if not isinstance(data, list) or not data:
        log.warning("anti-cheat list has an unexpected shape - ignored")
        return None
    write_json(cache_path(), data)
    return data


def load(online: bool) -> Optional[List[Any]]:
    """The cached list, refreshed when older than a week and online is allowed."""
    current = cached()
    stale = current is None or (age() or 0) > MAX_AGE
    if online and stale:
        return fetch() or current
    return current
