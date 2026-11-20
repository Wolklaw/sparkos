"""The library: every source scanned together, cached, and checked for changes.

The window shows ~/.cache/spark-games/library.json at once, then scans in a background thread.
A source that fails is logged and skipped; the rest still show. On window focus, a cheap look
at the launchers' files (their modification times) decides whether to scan again; nothing polls.
"""

import os
from typing import Dict, List, Optional, Set, Tuple

from . import heroic, lutris, owngames, steam
from .core import Game, cache_dir, home, log, mtime, now, read_json, write_json

CACHE_VERSION = 1
SCANNERS = (('steam', steam.scan), ('heroic', heroic.scan), ('lutris', lutris.scan),
            ('own', owngames.scan))


class Scan:
    def __init__(self, games: List[Game], watch: List[str], launchers: Set[str],
                 problems: List[str]):
        self.games, self.watch, self.launchers, self.problems = games, watch, launchers, problems


def candidate_roots(base: str) -> List[str]:
    """Folders whose appearance means a launcher was installed since the last scan."""
    return [os.path.join(base, '.var', 'app'), os.path.join(base, '.local', 'share', 'Steam'),
            os.path.join(base, '.config', 'heroic'), os.path.join(base, '.local', 'share', 'lutris')]


def scan_all(base: Optional[str] = None) -> Scan:
    base = base or home()
    games: List[Game] = []
    watch: List[str] = candidate_roots(base)
    launchers: Set[str] = set()
    problems: List[str] = []
    for name, scanner in SCANNERS:
        try:
            found = scanner(base, watch)
        except Exception as exc:          # noqa: BLE001 - one broken source never stops the rest
            log.warning("%s: skipped, its files could not be read: %s", name, exc)
            problems.append(name)
            continue
        if name == 'steam' and steam.roots(base) or name == 'heroic' and heroic.roots(base) \
                or name == 'lutris' and lutris.roots(base):
            launchers.add(name)
        games.extend(found)
    seen, unique = set(), []
    for game in games:
        if game.key not in seen:
            seen.add(game.key)
            unique.append(game)
    return Scan(unique, watch, launchers, problems)


def signature(watch: List[str]) -> List[Tuple[str, Optional[float]]]:
    return [(path, mtime(path)) for path in watch]


def cache_path() -> str:
    return os.path.join(cache_dir(), 'library.json')


def load_cache() -> Optional[Scan]:
    data = read_json(cache_path())
    if not isinstance(data, dict) or data.get('version') != CACHE_VERSION:
        return None
    try:
        games = [Game.from_json(g) for g in data.get('games', []) if isinstance(g, dict)]
    except TypeError as exc:
        log.warning("library cache unreadable, scanning again: %s", exc)
        return None
    return Scan(games, list(data.get('watch') or []), set(data.get('launchers') or []), [])


def save_cache(result: Scan) -> None:
    write_json(cache_path(), {'version': CACHE_VERSION, 'scanned': now(),
                              'games': [g.to_json() for g in result.games],
                              'watch': result.watch, 'launchers': sorted(result.launchers)})


def merge_sessions(games: List[Game], totals: Dict[str, Dict[str, int]]) -> None:
    """Fill in playtime from Spark Games' own sessions where the launcher has none, and the
    last played time where ours is newer."""
    for game in games:
        mine = totals.get(game.key)
        if not mine:
            continue
        if not game.playtime:
            game.playtime = mine['minutes']
        game.last_played = max(game.last_played or 0, mine['last'])
