"""Startup apps: XDG autostart entries and enabled systemd --user services.

Turning off an entry from /etc/xdg/autostart copies it to ~/.config/autostart with
Hidden=true, which the autostart spec says hides the system one. /etc is never written.
Services are switched with `systemctl --user enable|disable`."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .desktop import languages, localized, parse_desktop
from .source import Source, listdir, read_text
from .text import t

AUTOSTART, SERVICE = 'autostart', 'service'
MARK = 'X-Spark-Monitor-Override'
DESKTOP = 'Spark'
TARGETS_SKIPPED = ('sockets.target.wants', 'timers.target.wants', 'paths.target.wants')


@dataclass
class StartupItem:
    id: str                    # file name: "discord.desktop", "syncthing.service"
    kind: str                  # AUTOSTART or SERVICE
    name: str
    description: str
    enabled: bool
    origin: str                # "user" (yours) or "system" (set by the system)
    path: str = ""             # the file that decides it
    system_path: str = ""      # the /etc copy, if there is one
    can_toggle: bool = True
    note: str = ""


# ─── Autostart entries ────────────────────────────────────────

def _applies(keys: Dict[str, str], src: Source) -> bool:
    if keys.get('Type', 'Application') != 'Application':
        return False
    only = [d for d in keys.get('OnlyShowIn', '').split(';') if d]
    if only and DESKTOP not in only:
        return False
    if DESKTOP in keys.get('NotShowIn', '').split(';'):
        return False
    try_exec = keys.get('TryExec')
    if try_exec and not src.fake:
        if os.path.isabs(try_exec):
            return os.access(try_exec, os.X_OK)
        return shutil.which(try_exec) is not None
    return True


def _enabled(keys: Dict[str, str]) -> bool:
    return keys.get('Hidden', '').lower() != 'true' and \
        keys.get('X-GNOME-Autostart-enabled', '').lower() != 'false'


def user_autostart(src: Source) -> str:
    return os.path.join(src.config_home, 'autostart')


def autostart_items(src: Source) -> List[StartupItem]:
    system: Dict[str, str] = {}
    for d in src.config_dirs:
        folder = os.path.join(d, 'autostart')
        for name in sorted(listdir(folder)):
            if name.endswith('.desktop') and name not in system:
                system[name] = os.path.join(folder, name)
    user_dir = user_autostart(src)
    user = {n: os.path.join(user_dir, n) for n in listdir(user_dir) if n.endswith('.desktop')}
    langs = languages()
    items = []
    for name in sorted(set(system) | set(user)):
        path = user.get(name) or system[name]
        keys = parse_desktop(read_text(path) or '')
        sys_keys = parse_desktop(read_text(system[name]) or '') if name in system else {}
        if not keys or not _applies(sys_keys or keys, src):
            continue
        label = localized(keys, 'Name', langs) or localized(sys_keys, 'Name', langs) or name[:-8]
        about = localized(keys, 'Comment', langs) or localized(sys_keys, 'Comment', langs) \
            or localized(keys, 'GenericName', langs)
        items.append(StartupItem(
            id=name, kind=AUTOSTART, name=label, description=about, enabled=_enabled(keys),
            origin='system' if name in system else 'user', path=path,
            system_path=system.get(name, '')))
    return items


def set_key(text: str, key: str, value: Optional[str], group: str = 'Desktop Entry') -> str:
    """Set (or with value None, remove) a key in one group of a desktop file."""
    lines = text.splitlines()
    out, in_group, done = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if in_group and not done and value is not None:
                out.append(f'{key}={value}')
                done = True
            in_group = stripped[1:-1] == group
        elif in_group and re.match(rf'{re.escape(key)}\s*=', stripped):
            if value is not None and not done:
                out.append(f'{key}={value}')
                done = True
            continue
        out.append(line)
    if not done and value is not None:
        if not any(l.strip() == f'[{group}]' for l in lines):
            out = [f'[{group}]'] + out
            out.insert(1, f'{key}={value}')
        else:
            out.append(f'{key}={value}')
    return '\n'.join(out).rstrip('\n') + '\n'


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(path + '.tmp', path)


def set_autostart(src: Source, item: StartupItem, on: bool) -> None:
    """Switch an autostart entry on or off, writing only to the user's autostart folder."""
    user_path = os.path.join(user_autostart(src), item.id)
    if os.path.exists(user_path):
        text = read_text(user_path) or ''
        keys = parse_desktop(text)
        if on and keys.get(MARK) == 'true' and item.system_path:
            sys_keys = parse_desktop(read_text(item.system_path) or '')
            if _enabled(sys_keys):
                os.remove(user_path)      # our own override: removing it restores the system one
                return
        text = set_key(text, 'Hidden', 'false' if on else 'true')
        if on and keys.get('X-GNOME-Autostart-enabled', '').lower() == 'false':
            text = set_key(text, 'X-GNOME-Autostart-enabled', 'true')
        _write(user_path, text)
        return
    if not item.system_path:
        raise FileNotFoundError(item.path)
    text = read_text(item.system_path) or '[Desktop Entry]\n'
    text = set_key(text, 'Hidden', 'false' if on else 'true')
    if on:
        text = set_key(text, 'X-GNOME-Autostart-enabled', None)
    text = set_key(text, MARK, 'true')
    _write(user_path, text)


# ─── systemd --user services ──────────────────────────────────

def unit_dirs(src: Source) -> List[Tuple[str, str]]:
    """(folder, origin) in systemd's order of precedence."""
    return [(os.path.join(src.config_home, 'systemd', 'user'), 'user'),
            (src.path('etc/systemd/user'), 'system'),
            (src.path('usr/local/lib/systemd/user'), 'vendor'),
            (src.path('usr/lib/systemd/user'), 'vendor')]


def unit_description(src: Source, unit: str) -> str:
    names = [unit]
    if '@' in unit:
        names.append(re.sub(r'@[^.]*\.', '@.', unit))
    for folder, _origin in unit_dirs(src):
        for name in names:
            text = read_text(os.path.join(folder, name))
            if text:
                match = re.search(r'^Description\s*=\s*(.+)$', text, re.M)
                if match:
                    return match.group(1).strip()
    return ""


def service_items(src: Source, remembered: List[str]) -> List[StartupItem]:
    """Services enabled for your login (yours can be switched; the system's are shown), plus
    the ones you switched off here, so you can switch them back on."""
    found: Dict[str, StartupItem] = {}
    for folder, origin in unit_dirs(src)[:2]:
        for wants in sorted(listdir(folder)):
            if not wants.endswith('.wants') or wants in TARGETS_SKIPPED:
                continue
            for unit in sorted(listdir(os.path.join(folder, wants))):
                if not unit.endswith('.service') or unit in found:
                    continue
                desc = unit_description(src, unit)
                found[unit] = StartupItem(
                    id=unit, kind=SERVICE, name=re.sub(r'\.service$', '', unit),
                    description=desc, enabled=True, origin=origin,
                    path=os.path.join(folder, wants, unit),
                    can_toggle=origin == 'user',
                    note="" if origin == 'user' else t('startup.system_note'))
    for unit in remembered:
        if unit not in found:
            found[unit] = StartupItem(
                id=unit, kind=SERVICE, name=re.sub(r'\.service$', '', unit),
                description=unit_description(src, unit), enabled=False, origin='user')
    return sorted(found.values(), key=lambda i: i.name.lower())


Runner = Callable[[List[str]], Tuple[int, str]]


def run(cmd: List[str]) -> Tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return done.returncode, (done.stderr or done.stdout).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def set_service(item: StartupItem, on: bool, runner: Runner = run) -> Tuple[bool, str]:
    code, out = runner(['systemctl', '--user', 'enable' if on else 'disable', item.id])
    return code == 0, out


# ─── Remembering switched-off services ────────────────────────

def remembered_units(path: str) -> List[str]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        units = data.get('disabled_services', []) if isinstance(data, dict) else []
        return [u for u in units if isinstance(u, str) and re.fullmatch(r'[\w@.:-]+', u)]
    except (OSError, ValueError):
        return []


def remember_units(path: str, units: List[str]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump({'disabled_services': sorted(set(units))}, f, indent=2)
        os.replace(path + '.tmp', path)
    except OSError:
        pass


def all_items(src: Source, remembered: List[str]) -> List[StartupItem]:
    return autostart_items(src) + service_items(src, remembered)
