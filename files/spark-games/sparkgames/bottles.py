"""Bottles: the programs added to each bottle, from the bottles' own files, read only.

  ~/.var/app/com.usebottles.bottles/data/bottles/bottles/<bottle>/bottle.yml   the Flatpak
  ~/.local/share/bottles/bottles/<bottle>/bottle.yml                          a regular install

Each bottle.yml has an External_Programs block: one entry per program the user added, with
name, executable, path and folder. Started with Bottles' own command line:

  flatpak run --command=bottles-cli com.usebottles.bottles run -b <bottle> -p <program>

bottle.yml is YAML written by PyYAML in block style. PyYAML isn't something Spark Games can
count on, so the small reader below handles what Bottles writes: nested mappings by indent,
plain and quoted scalars. Lists and anything fancier are skipped, not guessed at.
"""

import os
import re
from typing import Any, Dict, List, Tuple

from . import BOTTLES_FLATPAK
from .core import Game, log

ESCAPE = re.compile(r'\\(.)')
ESCAPES = {'n': '\n', 't': '\t', '"': '"', '\\': '\\', '/': '/', '0': '\0'}


class YAMLError(ValueError):
    pass


def _scalar(text: str) -> Any:
    text = text.strip()
    if not text or text in ('~', 'null'):
        return None
    if text[0] == "'" and text.endswith("'") and len(text) > 1:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text.endswith('"') and len(text) > 1:
        return ESCAPE.sub(lambda m: ESCAPES.get(m.group(1), m.group(1)), text[1:-1])
    if text in ('true', 'True'):
        return True
    if text in ('false', 'False'):
        return False
    if text.lstrip('-').isdigit():
        return int(text)
    if text in ('{}', '[]'):
        return {} if text == '{}' else []
    return text


def _split_key(line: str) -> Tuple[str, str]:
    """'key: value' -> (key, value); the key may be quoted."""
    if line[0] in '"\'':
        quote = line[0]
        end = line.find(quote, 1)
        while end > 0 and quote == "'" and line[end:end + 2] == "''":
            end = line.find(quote, end + 2)
        if end < 0 or line[end + 1:end + 2] != ':':
            raise YAMLError(f"bad key: {line!r}")
        return str(_scalar(line[:end + 1])), line[end + 2:]
    colon = line.find(': ')
    if colon < 0:
        if line.endswith(':'):
            return line[:-1], ''
        raise YAMLError(f"not a mapping line: {line!r}")
    return line[:colon], line[colon + 2:]


def loads(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(-1, root)]
    pending = None                       # (indent, parent, key) waiting for a nested block
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#') or stripped == '---':
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        if stripped.startswith('- '):    # list items: skipped (Bottles keeps none we need)
            continue
        if pending is not None:
            p_indent, parent, key = pending
            pending = None
            if indent > p_indent:
                child: Dict[str, Any] = {}
                parent[key] = child
                stack.append((p_indent, child))
            else:
                parent[key] = None
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        key, value = _split_key(stripped)
        mapping = stack[-1][1]
        if value.strip() == '' or value.strip().startswith('#'):
            pending = (indent, mapping, key)
        else:
            quoted = value.lstrip()[:1] in ('"', "'")
            mapping[key] = _scalar(value if quoted else value.split(' #')[0])
    if pending is not None:
        pending[1][pending[2]] = None
    return root


def roots(home: str) -> List[Tuple[str, bool]]:
    """(the folder holding the bottles, is the Flatpak)."""
    found = []
    for path, flatpak in ((os.path.join(home, '.var', 'app', BOTTLES_FLATPAK, 'data', 'bottles',
                                        'bottles'), True),
                          (os.path.join(home, '.local', 'share', 'bottles', 'bottles'), False)):
        if os.path.isdir(path):
            found.append((path, flatpak))
    return found


def read_bottle(path: str) -> Tuple[str, List[Dict[str, str]]]:
    """(bottle name, [{id, name, executable, path, folder}]) from one bottle.yml."""
    with open(path, encoding='utf-8', errors='replace') as f:
        data = loads(f.read())
    name = data.get('Name') or os.path.basename(os.path.dirname(path))
    block = data.get('External_Programs')
    programs = []
    if isinstance(block, dict):
        for pid, info in block.items():
            if not isinstance(info, dict) or not info.get('name') or info.get('removed'):
                continue
            programs.append({'id': str(info.get('id') or pid), 'name': str(info['name']),
                             'executable': str(info.get('executable') or ''),
                             'path': str(info.get('path') or ''),
                             'folder': str(info.get('folder') or '')})
    return str(name), programs


def scan(home: str, watch: List[str]) -> List[Game]:
    games: Dict[str, Game] = {}
    for root, flatpak in roots(home):
        watch.append(root)
        try:
            bottles = sorted(os.listdir(root))
        except OSError:
            continue
        for folder in bottles:
            path = os.path.join(root, folder, 'bottle.yml')
            if not os.path.isfile(path):
                continue
            watch.append(path)
            try:
                bottle, programs = read_bottle(path)
            except (OSError, YAMLError) as exc:
                log.warning("bottles: skipping %s: %s", path, exc)
                continue
            for program in programs:
                key = f'bottles:{folder}:{program["id"]}'
                if key in games:
                    continue
                install = program['folder'] or os.path.dirname(program['path'])
                games[key] = Game(key=key, title=program['name'], source='bottles',
                                  install_dir=install, flatpak=flatpak,
                                  launch={'bottle': bottle, 'program': program['name'],
                                          'flatpak': flatpak})
    return list(games.values())
