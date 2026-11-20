"""itch.io: games installed with the itch app, from its database, opened read only.

  ~/.config/itch/db/butler.db                        the regular itch app
  ~/.var/app/io.itch.itch/config/itch/db/butler.db   the Flatpak

In butler.db, each installed copy is a row in caves (game_id, install_location_id,
install_folder_name or custom_install_folder, last_touched_at, seconds_run), its game is a row
in games (title, classification), and install_locations gives the folder. Only games are
listed; tools, assets, comics and books are left out.

Started with the itch app's own launcher: ~/.itch/itch-setup --run-game <game id> when it is
there (no prompt), otherwise itch://install?game_id=<id>&launch, which asks to confirm first.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from . import ITCH_FLATPAK
from .core import Game, log

NOT_GAMES = {'tool', 'assets', 'game_mod', 'physical_game', 'soundtrack', 'other', 'comic',
             'book'}


def roots(home: str) -> List[Tuple[str, bool]]:
    """(itch's config folder, is the Flatpak) for each itch app with a database."""
    found = []
    for path, flatpak in ((os.path.join(home, '.var', 'app', ITCH_FLATPAK, 'config', 'itch'),
                           True),
                          (os.path.join(home, '.config', 'itch'), False)):
        if os.path.isfile(os.path.join(path, 'db', 'butler.db')):
            found.append((path, flatpak))
    return found


def _time(value) -> int:
    """butler stores times as text ("2024-03-01 18:22:05.123+00:00") or, rarely, numbers."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value:
        return 0
    text = value.strip().replace('Z', '+00:00').replace(' ', 'T', 1)
    if '.' in text:                          # fromisoformat wants at most 6 fraction digits
        head, _, rest = text.partition('.')
        digits = ''.join(c for c in rest if c.isdigit())
        text = head + '.' + digits[:6].ljust(6, '0') + rest[len(digits):]
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int(stamp.timestamp()))


def read_db(path: str) -> List[Dict]:
    uri = 'file:' + path.replace('?', '%3F').replace('#', '%23') + '?mode=ro'
    con = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        def columns(table: str) -> set:
            return {row[1] for row in con.execute(f'PRAGMA table_info({table})')}
        caves, games = columns('caves'), columns('games')
        missing = ({'id', 'game_id'} - caves) | ({'id', 'title'} - games)
        if missing:
            raise sqlite3.DatabaseError(f"no {', '.join(sorted(missing))} column")
        locations = columns('install_locations')
        pick = ['c.id', 'c.game_id', 'g.title']
        for col in ('install_folder_name', 'custom_install_folder', 'last_touched_at',
                    'seconds_run', 'install_location_id'):
            pick.append(f'c.{col}' if col in caves else f'NULL AS {col}')
        pick.append('g.classification' if 'classification' in games else 'NULL AS classification')
        pick.append('g.cover_url' if 'cover_url' in games else 'NULL AS cover_url')
        join = ''
        if {'id', 'path'} <= locations and 'install_location_id' in caves:
            pick.append('l.path AS location')
            join = ' LEFT JOIN install_locations l ON l.id = c.install_location_id'
        else:
            pick.append('NULL AS location')
        sql = (f'SELECT {", ".join(pick)} FROM caves c JOIN games g ON g.id = c.game_id{join}')
        cur = con.execute(sql)
        names = [d[0].split('.')[-1] for d in cur.description]
        return [dict(zip(names, row)) for row in cur]
    finally:
        con.close()


def scan(home: str, watch: List[str]) -> List[Game]:
    games: Dict[str, Game] = {}
    setup = os.path.join(home, '.itch', 'itch-setup')       # the regular itch app's launcher
    for root, flatpak in roots(home):
        path = os.path.join(root, 'db', 'butler.db')
        watch.append(path)
        try:
            rows = read_db(path)
        except sqlite3.Error as exc:
            log.warning("itch: %s could not be read, skipped: %s", path, exc)
            continue
        for row in rows:
            if (row.get('classification') or 'game') in NOT_GAMES:
                continue
            game_id = str(row.get('game_id') or '')
            key = f'itch:{game_id}'
            if not game_id or key in games:
                continue
            folder = row.get('custom_install_folder') or ''
            if not folder and row.get('location') and row.get('install_folder_name'):
                folder = os.path.join(row['location'], row['install_folder_name'])
            try:
                minutes = int(row.get('seconds_run') or 0) // 60
            except (TypeError, ValueError):
                minutes = 0
            games[key] = Game(key=key, title=row.get('title') or key, source='itch',
                              install_dir=folder, playtime=minutes,
                              last_played=_time(row.get('last_touched_at')), flatpak=flatpak,
                              store_id=game_id,
                              launch={'game_id': game_id, 'cave': str(row.get('id') or ''),
                                      'flatpak': flatpak,
                                      'setup': '' if flatpak or not os.path.isfile(setup)
                                      else setup})
    return list(games.values())
