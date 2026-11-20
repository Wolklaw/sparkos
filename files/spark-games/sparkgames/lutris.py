"""Lutris: installed games from Lutris's database, opened read only.

  ~/.local/share/lutris/pga.db                         the regular Lutris
  ~/.var/app/net.lutris.Lutris/data/lutris/pga.db      the Flatpak
  <data>/coverart/<slug>.jpg, <data>/banners/<slug>.jpg (also under ~/.cache/lutris/ in
  older versions)

Games Lutris runs through Steam are left out: Steam lists them already.
"""

import os
import sqlite3
from typing import Dict, List, Tuple

from . import LUTRIS_FLATPAK
from .core import Game, log

WANTED = ('id', 'name', 'slug', 'runner', 'directory', 'lastplayed', 'playtime', 'installed',
          'service')


def roots(home: str) -> List[Tuple[str, str, bool]]:
    """(data folder, cache folder, is the Flatpak)."""
    flat = os.path.join(home, '.var', 'app', LUTRIS_FLATPAK)
    found = []
    for data, cache, flatpak in (
            (os.path.join(flat, 'data', 'lutris'), os.path.join(flat, 'cache', 'lutris'), True),
            (os.path.join(home, '.local', 'share', 'lutris'),
             os.path.join(home, '.cache', 'lutris'), False)):
        if os.path.isfile(os.path.join(data, 'pga.db')):
            found.append((data, cache, flatpak))
    return found


def read_db(path: str) -> List[Dict]:
    """Installed games as dicts. Read-only, and it gives up after 2 s if Lutris holds a lock."""
    uri = 'file:' + path.replace('?', '%3F').replace('#', '%23') + '?mode=ro'
    con = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        columns = {row[1] for row in con.execute('PRAGMA table_info(games)')}
        missing = {'id', 'name', 'installed'} - columns
        if missing:
            raise sqlite3.DatabaseError(f"games table has no {', '.join(sorted(missing))}")
        cols = [c for c in WANTED if c in columns]
        rows = con.execute(f'SELECT {", ".join(cols)} FROM games WHERE installed = 1')
        return [dict(zip(cols, row)) for row in rows]
    finally:
        con.close()


def cover(data: str, cache: str, slug: str) -> str:
    if not slug:
        return ''
    for folder in (os.path.join(data, 'coverart'), os.path.join(cache, 'coverart'),
                   os.path.join(data, 'banners'), os.path.join(cache, 'banners')):
        for ext in ('jpg', 'png', 'jpeg', 'webp'):
            path = os.path.join(folder, f'{slug}.{ext}')
            if os.path.isfile(path):
                return path
    return ''


def scan(home: str, watch: List[str]) -> List[Game]:
    games: Dict[str, Game] = {}
    for data, cache, flatpak in roots(home):
        path = os.path.join(data, 'pga.db')
        watch.append(path)
        try:
            rows = read_db(path)
        except sqlite3.Error as exc:
            log.warning("lutris: %s could not be read, skipped: %s", path, exc)
            continue
        for row in rows:
            if (row.get('runner') or '') == 'steam' or (row.get('service') or '') == 'steam':
                continue
            key = f'lutris:{row["id"]}' if not flatpak else f'lutris-flatpak:{row["id"]}'
            try:
                minutes = int(round(float(row.get('playtime') or 0) * 60))   # stored in hours
            except (TypeError, ValueError):
                minutes = 0
            try:
                last = int(row.get('lastplayed') or 0)
            except (TypeError, ValueError):
                last = 0
            games[key] = Game(key=key, title=row.get('name') or row.get('slug') or key,
                              source='lutris', install_dir=row.get('directory') or '',
                              playtime=minutes, last_played=last,
                              cover=cover(data, cache, row.get('slug') or ''), flatpak=flatpak,
                              store_id=row.get('slug') or '',
                              launch={'id': row['id'], 'flatpak': flatpak})
    return list(games.values())
