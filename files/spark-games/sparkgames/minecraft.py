"""Minecraft: Java Edition, through the official launcher or Prism Launcher, read only.

Official launcher: one entry, "Minecraft: Java Edition", when its launcher_profiles.json exists.
  ~/.minecraft/launcher_profiles.json                              minecraft-launcher
  ~/.var/app/com.mojang.Minecraft/.minecraft/launcher_profiles.json  the Flatpak
Last played is the newest lastUsed of its profiles; the launcher keeps no playtime.

Prism Launcher: one entry per instance.
  ~/.local/share/PrismLauncher/instances/<id>/instance.cfg
  ~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/<id>/instance.cfg
instance.cfg gives name, lastLaunchTime (ms) and totalTimePlayed (s); prismlauncher.cfg may move
the instances folder (InstanceDir). Started with prismlauncher --launch <id>.
"""

import os
from datetime import datetime
from typing import Dict, List, Tuple

from . import MINECRAFT_FLATPAK, PRISM_FLATPAK
from .core import Game, log, read_json

JAVA_TITLE = "Minecraft: Java Edition"


# ─── The official launcher ────────────────────────────────────

def official_roots(home: str) -> List[Tuple[str, bool]]:
    found = []
    for path, flatpak in ((os.path.join(home, '.var', 'app', MINECRAFT_FLATPAK, '.minecraft'),
                           True),
                          (os.path.join(home, '.minecraft'), False)):
        if os.path.isfile(os.path.join(path, 'launcher_profiles.json')):
            found.append((path, flatpak))
    return found


def _iso(value) -> int:
    if not isinstance(value, str) or not value or value.startswith('1970'):
        return 0
    try:
        return max(0, int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()))
    except ValueError:
        return 0


def official(home: str, watch: List[str]) -> List[Game]:
    games = []
    for root, flatpak in official_roots(home):
        path = os.path.join(root, 'launcher_profiles.json')
        watch.append(path)
        data = read_json(path)
        if not isinstance(data, dict):
            log.warning("minecraft: %s isn't a launcher profile file, skipped", path)
            continue
        profiles = data.get('profiles') if isinstance(data.get('profiles'), dict) else {}
        last = max([_iso(p.get('lastUsed')) for p in profiles.values() if isinstance(p, dict)]
                   or [0])
        key = 'minecraft:java-flatpak' if flatpak else 'minecraft:java'
        games.append(Game(key=key, title=JAVA_TITLE, source='minecraft', install_dir=root,
                          last_played=last, flatpak=flatpak, launch={'flatpak': flatpak}))
    return games


# ─── Prism Launcher ───────────────────────────────────────────

def prism_roots(home: str) -> List[Tuple[str, bool]]:
    found = []
    for path, flatpak in ((os.path.join(home, '.var', 'app', PRISM_FLATPAK, 'data',
                                        'PrismLauncher'), True),
                          (os.path.join(home, '.local', 'share', 'PrismLauncher'), False)):
        if os.path.isdir(path):
            found.append((path, flatpak))
    return found


def read_cfg(path: str) -> Dict[str, str]:
    """Prism's .cfg files: key=value lines, maybe under a [General] header."""
    out: Dict[str, str] = {}
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in '[#;' or '=' not in line:
                continue
            key, _, value = line.partition('=')
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] == '"':
                value = value[1:-1]
            out[key.strip()] = value
    return out


def instances_dir(root: str) -> str:
    folder = 'instances'
    cfg = os.path.join(root, 'prismlauncher.cfg')
    if os.path.isfile(cfg):
        try:
            folder = read_cfg(cfg).get('InstanceDir') or folder
        except OSError:
            pass
    return folder if os.path.isabs(folder) else os.path.join(root, folder)


def _int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def prism(home: str, watch: List[str]) -> List[Game]:
    games = []
    for root, flatpak in prism_roots(home):
        folder = instances_dir(root)
        watch.append(folder)
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            cfg_path = os.path.join(folder, name, 'instance.cfg')
            if not os.path.isfile(cfg_path):
                continue
            try:
                cfg = read_cfg(cfg_path)
            except OSError as exc:
                log.warning("prism: skipping %s: %s", cfg_path, exc)
                continue
            icon = ''
            key = cfg.get('iconKey') or ''
            for ext in ('png', 'jpg', 'jpeg', 'webp'):
                candidate = os.path.join(root, 'icons', f'{key}.{ext}')
                if key and os.path.isfile(candidate):
                    icon = candidate
                    break
            last = _int(cfg.get('lastLaunchTime'))
            games.append(Game(key=f'prism{"-flatpak" if flatpak else ""}:{name}',
                              title=cfg.get('name') or name, source='prism',
                              install_dir=os.path.join(folder, name),
                              playtime=_int(cfg.get('totalTimePlayed')) // 60,
                              last_played=last // 1000 if last > 1e11 else last,
                              cover=icon, flatpak=flatpak,
                              launch={'instance': name, 'flatpak': flatpak}))
    return games


def roots(home: str) -> List[Tuple[str, bool]]:
    return official_roots(home) + prism_roots(home)


def scan(home: str, watch: List[str]) -> List[Game]:
    return official(home, watch) + prism(home, watch)
