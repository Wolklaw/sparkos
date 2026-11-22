"""Right-click actions other apps add, read from KDE's service menu files
(share/kio/servicemenus/*.desktop). That's how Spark Archive's Compress and Extract, Spark
Link's "Send to phone" and SparkOS's "Open Claude Code here" reach Spark Files too, without
Spark Files knowing about any of them."""

import fnmatch
import os
import shlex
import subprocess
from typing import Dict, List, Optional, Sequence

from .core import data_home, log
from .lang import ui_language


class Action:
    __slots__ = ('name', 'icon', 'exec', 'submenu', 'source', 'priority')

    def __init__(self, name: str, icon: str, exec_line: str, submenu: str, source: str,
                 priority: str):
        self.name, self.icon, self.exec, self.submenu = name, icon, exec_line, submenu
        self.source, self.priority = source, priority

    def __repr__(self) -> str:
        return f"Action({self.name!r})"


class Menu:
    __slots__ = ('path', 'mimetypes', 'actions', 'min_urls', 'max_urls', 'protocols')

    def __init__(self, path: str):
        self.path = path
        self.mimetypes: List[str] = []
        self.actions: List[Action] = []
        self.min_urls, self.max_urls = 0, 0
        self.protocols: List[str] = []


def search_dirs() -> List[str]:
    dirs = [data_home()]
    dirs += [d for d in (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share')
             .split(':') if d]
    out = []
    for d in dirs:
        for sub in ('kio/servicemenus', 'kservices5/ServiceMenus'):
            path = os.path.join(d, sub)
            if path not in out:
                out.append(path)
    return out


def _parse(path: str) -> Dict[str, Dict[str, str]]:
    groups: Dict[str, Dict[str, str]] = {}
    current: Optional[Dict[str, str]] = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                current = groups.setdefault(line[1:-1], {})
                continue
            if current is not None and '=' in line:
                key, value = line.split('=', 1)
                current[key.strip()] = value.strip()
    return groups


def _localized(group: Dict[str, str], key: str, lang: str) -> str:
    return group.get(f'{key}[{lang}]') or group.get(key, '')


def load(lang: Optional[str] = None) -> List[Menu]:
    lang = lang or ui_language()
    seen, menus = set(), []
    for folder in search_dirs():
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if not name.endswith('.desktop') or name in seen:
                continue                        # the user's own copy hides the system's
            seen.add(name)
            path = os.path.join(folder, name)
            try:
                groups = _parse(path)
            except OSError:
                continue
            entry = groups.get('Desktop Entry', {})
            if entry.get('Type', 'Service') != 'Service' or entry.get('Hidden') == 'true':
                continue
            menu = Menu(path)
            menu.mimetypes = [m for m in (entry.get('MimeType') or
                                          entry.get('ServiceTypes', '')).split(';') if m]
            menu.mimetypes = [m for m in menu.mimetypes if '/' in m]
            menu.protocols = [p for p in entry.get('X-KDE-Protocols', '').split(',') if p]
            try:
                menu.min_urls = int(entry.get('X-KDE-MinNumberOfUrls', '0'))
                menu.max_urls = int(entry.get('X-KDE-MaxNumberOfUrls', '0'))
            except ValueError:
                pass
            if entry.get('X-KDE-RequiredNumberOfUrls'):
                try:
                    n = int(entry['X-KDE-RequiredNumberOfUrls'].split(',')[0])
                    menu.min_urls = menu.max_urls = n
                except ValueError:
                    pass
            submenu = _localized(entry, 'X-KDE-Submenu', lang)
            priority = entry.get('X-KDE-Priority', '')
            for action_id in [a for a in entry.get('Actions', '').split(';') if a]:
                group = groups.get(f'Desktop Action {action_id}')
                if not group or not group.get('Exec'):
                    continue
                menu.actions.append(Action(_localized(group, 'Name', lang) or action_id,
                                           group.get('Icon', ''), group['Exec'], submenu,
                                           path, priority))
            if menu.actions and menu.mimetypes:
                menus.append(menu)
    return menus


def _mime_matches(patterns: Sequence[str], mime: str, is_dir: bool) -> bool:
    for pattern in patterns:
        if pattern == 'all/all':
            return True
        if pattern == 'all/allfiles' and not is_dir:
            return True
        if pattern == mime or (pattern.endswith('/*') and mime.startswith(pattern[:-1])):
            return True
        if '*' in pattern and fnmatch.fnmatchcase(mime, pattern):
            return True
    return False


def actions_for(menus: List[Menu], items: Sequence[tuple]) -> List[Action]:
    """items: (path, mime, is_dir). The actions that apply to all of them."""
    if not items:
        return []
    out = []
    for menu in menus:
        if menu.protocols and 'file' not in menu.protocols:
            continue
        if menu.min_urls and len(items) < menu.min_urls:
            continue
        if menu.max_urls and len(items) > menu.max_urls:
            continue
        if all(_mime_matches(menu.mimetypes, mime, is_dir) for _p, mime, is_dir in items):
            out.extend(menu.actions)
    return out


def expand(exec_line: str, paths: Sequence[str]) -> List[str]:
    """The command for an Exec= line, with %f %F %u %U filled in (the field codes the
    desktop entry spec defines; %i %c %k dropped)."""
    try:
        words = shlex.split(exec_line)
    except ValueError:
        words = exec_line.split()
    out: List[str] = []
    uris = ['file://' + p for p in paths]
    for word in words:
        if word in ('%F', '%U'):
            out.extend(paths if word == '%F' else uris)
            continue
        if word in ('%i', '%c', '%k', '%m', '%d', '%D', '%n', '%N', '%v'):
            continue
        word = word.replace('%f', paths[0] if paths else '')
        word = word.replace('%u', uris[0] if uris else '')
        word = word.replace('%%', '%')
        out.append(word)
    return out


def run(action: Action, paths: Sequence[str], cwd: Optional[str] = None) -> bool:
    argv = expand(action.exec, paths)
    if not argv:
        return False
    try:
        subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as exc:
        log.warning("service menu %s failed: %s", action.name, exc)
        return False
