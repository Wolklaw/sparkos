"""Known places where space can usually be won back, found in a finished scan. Spark Space
only points at them and explains; it never cleans anything by itself."""

import os
from typing import List, Optional

from .core import data_home, home
from .scan import DIR, Node

MIN_SIZE = 1024 * 1024           # under a megabyte isn't worth a line


class Hint:
    __slots__ = ('key', 'node', 'command')

    def __init__(self, key: str, node: Node, command: str = ''):
        self.key, self.node, self.command = key, node, command

    def __repr__(self) -> str:
        return f"Hint({self.key!r}, {self.node.path()!r})"


# fixed places: (path, key, command)
def _fixed() -> List[tuple]:
    h = home()
    data = data_home()
    return [
        (os.path.join(h, '.cache'), 'cache', ''),
        (os.path.join(data, 'Trash'), 'trash', ''),
        (os.path.join(data, 'flatpak'), 'flatpak', 'flatpak uninstall --user --unused'),
        ('/var/lib/flatpak', 'flatpak', 'flatpak uninstall --unused'),
        (os.path.join(data, 'containers'), 'containers', 'podman system prune'),
        ('/var/log/journal', 'journal', 'sudo journalctl --vacuum-size=500M'),
    ]


def _match(node: Node, path: str, fixed: dict) -> Optional[Hint]:
    if path in fixed:
        key, command = fixed[path]
        return Hint(key, node, command)
    parent = node.parent
    if parent is None:
        return None
    name, pname = node.name, parent.name
    if pname.lower() == 'steamapps':
        if name == 'shadercache':
            return Hint('shadercache', node)
        if name in ('downloading', 'temp'):
            return Hint('steam_downloading', node)
    # ~/.var/app/<app id>/cache: a Flatpak app's own cache
    if name == 'cache' and parent.parent is not None and parent.parent.name == 'app' and \
            parent.parent.parent is not None and parent.parent.parent.name == '.var':
        return Hint('app_cache', node)
    return None


def find_hints(root: Node) -> List[Hint]:
    """Walks the folders (not the files) of a finished tree."""
    fixed = {os.path.realpath(p): (k, c) for p, k, c in _fixed()}
    out: List[Hint] = []
    stack = [(root, root.name)]
    while stack:
        node, path = stack.pop()
        hint = _match(node, path, fixed)
        if hint is not None:
            if node.size >= MIN_SIZE:
                out.append(hint)
            continue                    # nothing inside a hint is a second hint
        for child in node.children or ():
            if child.flags & DIR:
                stack.append((child, os.path.join(path, child.name)))
    out.sort(key=lambda h: -h.node.size)
    return out
