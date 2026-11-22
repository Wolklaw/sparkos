"""Games the user adds by hand: a native program or a Windows .exe, kept in
~/.config/spark-games/games.json as {"games": [{id, title, exe, args, windows, added}]}."""

import os
import uuid
from typing import Any, Dict, List, Optional

from .core import Game, config_dir, is_windows_program, log, now, read_json, write_json


def path() -> str:
    return os.path.join(config_dir(), 'games.json')


def load() -> List[Dict[str, Any]]:
    data = read_json(path(), {})
    items = data.get('games') if isinstance(data, dict) else None
    if items is None:
        return []
    if not isinstance(items, list):
        log.warning("games.json: games is not a list - ignoring")
        return []
    return [g for g in items if isinstance(g, dict) and g.get('id') and g.get('exe')]


def save(items: List[Dict[str, Any]]) -> bool:
    return write_json(path(), {'games': items})


def add(title: str, exe: str, args: Optional[List[str]] = None,
        windows: Optional[bool] = None) -> Dict[str, Any]:
    item = {'id': uuid.uuid4().hex[:12], 'title': title.strip() or os.path.basename(exe),
            'exe': exe, 'args': list(args or []),
            'windows': is_windows_program(exe) if windows is None else bool(windows),
            'added': now()}
    items = load()
    items.append(item)
    save(items)
    return item


def remove(game_id: str) -> None:
    save([g for g in load() if g.get('id') != game_id])


def scan(_home: str, watch: List[str]) -> List[Game]:
    watch.append(path())
    games = []
    for item in load():
        exe = str(item['exe'])
        args = item.get('args') if isinstance(item.get('args'), list) else []
        games.append(Game(key=f'own:{item["id"]}', title=str(item.get('title') or exe),
                          source='own', install_dir=os.path.dirname(exe),
                          cover=str(item.get('cover') or ''),
                          launch={'id': item['id'], 'exe': exe, 'args': [str(a) for a in args],
                                  'windows': bool(item.get('windows'))}))
    return games
