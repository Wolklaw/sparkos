"""Steam: installed games from Steam's own files, read only.

  <root>/steamapps/libraryfolders.vdf            the library folders (one per drive)
  <library>/steamapps/appmanifest_<appid>.acf    one per installed app
  <root>/appcache/librarycache/<appid>/...       cover art Steam already downloaded
  <root>/userdata/<id>/config/localconfig.vdf    playtime and last played, per Steam account
  <root>/userdata/<id>/config/shortcuts.vdf      non-Steam games added to Steam (binary VDF)
  <root>/userdata/<id>/config/grid/              their covers, if the user set any

<root> is ~/.local/share/Steam for the regular Steam, and
~/.var/app/com.valvesoftware.Steam/.local/share/Steam for the Flatpak (SparkOS's usual one).
"""

import glob
import os
import re
import zlib
from typing import Dict, List, Optional, Set, Tuple

from . import STEAM_FLATPAK, vdf
from .core import Game, log

# Apps that are tools, not games. Three checks, any one is enough: a known appid, a known
# name, or a toolmanifest.vdf in its folder (Proton and the runtimes have one, games don't).
TOOL_APPIDS = {
    '228980',                                   # Steamworks Common Redistributables
    '1070560', '1391110', '1628350',            # Steam Linux Runtime 1.0, 2.0, 3.0
    '1493710', '2180100',                       # Proton Experimental, Proton Hotfix
    '1826330', '1161040',                       # Proton EasyAntiCheat and BattlEye runtimes
    '250820',                                   # SteamVR
}
TOOL_NAME = re.compile(r'^(Proton\b|Steam Linux Runtime|Steamworks Common|SteamVR\b|'
                       r'Steam Audio|Steamworks SDK)', re.I)
INSTALLED = 4          # StateFlags bit: fully installed


def roots(home: str) -> List[Tuple[str, bool]]:
    """(Steam folder, is the Flatpak) for every Steam on this account, without duplicates."""
    candidates = [
        (os.path.join(home, '.var', 'app', STEAM_FLATPAK, '.local', 'share', 'Steam'), True),
        (os.path.join(home, '.var', 'app', STEAM_FLATPAK, 'data', 'Steam'), True),
        (os.path.join(home, '.local', 'share', 'Steam'), False),
        (os.path.join(home, '.steam', 'steam'), False),
        (os.path.join(home, '.steam', 'root'), False),
    ]
    seen: Set[str] = set()
    found = []
    for path, flatpak in candidates:
        if not os.path.isdir(os.path.join(path, 'steamapps')):
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        found.append((path, flatpak))
    return found


def library_folders(root: str) -> List[str]:
    """Every library folder Steam knows, the Steam folder itself first."""
    folders = [root]
    path = os.path.join(root, 'steamapps', 'libraryfolders.vdf')
    if os.path.isfile(path):
        data = vdf.load(path)
        block = vdf.get(data, 'libraryfolders') or vdf.get(data, 'LibraryFolders') or {}
        for key, value in block.items():
            if not key.isdigit():
                continue
            # new format: "0" { "path" "..." }; old format: "1" "/path"
            folder = vdf.get(value, 'path') if isinstance(value, dict) else value
            if isinstance(folder, str) and folder:
                folders.append(folder)
    unique, seen = [], set()
    for folder in folders:
        real = os.path.realpath(folder)
        if real not in seen and os.path.isdir(os.path.join(folder, 'steamapps')):
            seen.add(real)
            unique.append(folder)
    return unique


def is_tool(appid: str, name: str, install_dir: str) -> bool:
    if appid in TOOL_APPIDS or TOOL_NAME.match(name or ''):
        return True
    # Proton and the runtimes ship a toolmanifest.vdf; games don't
    return bool(install_dir) and os.path.isfile(os.path.join(install_dir, 'toolmanifest.vdf'))


def read_manifest(path: str, library: str) -> Optional[Tuple[str, str, str, int]]:
    """(appid, name, install folder, last played) of one appmanifest, None for tools and
    half-installed apps."""
    state = vdf.get(vdf.load(path), 'AppState')
    if not isinstance(state, dict):
        raise vdf.VDFError(f"{os.path.basename(path)} has no AppState")
    appid = str(vdf.get(state, 'appid', default='')).strip()
    name = str(vdf.get(state, 'name', default='')).strip()
    folder = str(vdf.get(state, 'installdir', default='')).strip()
    if not appid.isdigit():
        raise vdf.VDFError(f"{os.path.basename(path)} has no appid")
    flags = vdf.get(state, 'StateFlags')
    if flags is not None and not vdf.to_int(flags) & INSTALLED:
        return None
    install_dir = os.path.join(library, 'steamapps', 'common', folder) if folder else ''
    if is_tool(appid, name, install_dir):
        return None
    return appid, name or f"Steam app {appid}", install_dir, vdf.to_int(vdf.get(state, 'LastPlayed'))


def play_stats(root: str) -> Dict[str, Tuple[int, int]]:
    """appid -> (minutes played, last played) across this Steam's accounts."""
    stats: Dict[str, Tuple[int, int]] = {}
    for path in glob.glob(os.path.join(root, 'userdata', '*', 'config', 'localconfig.vdf')):
        try:
            data = vdf.load(path)
        except (OSError, vdf.VDFError) as exc:
            log.warning("steam: skipping %s: %s", path, exc)
            continue
        apps = vdf.get(data, 'UserLocalConfigStore', 'Software', 'Valve', 'Steam', 'apps') or {}
        if not isinstance(apps, dict):
            continue
        for appid, info in apps.items():
            if not isinstance(info, dict):
                continue
            minutes = vdf.to_int(vdf.get(info, 'Playtime'))
            last = vdf.to_int(vdf.get(info, 'LastPlayed'))
            old = stats.get(appid, (0, 0))
            stats[appid] = (max(old[0], minutes), max(old[1], last))
    return stats


def cover(root: str, appid: str) -> str:
    """The portrait cover (600x900) Steam already downloaded, or the wide header."""
    cache = os.path.join(root, 'appcache', 'librarycache')
    folder = os.path.join(cache, appid)
    if os.path.isdir(folder):
        # newer Steam: <appid>/library_600x900.jpg, sometimes one hashed folder deeper
        for name in ('library_600x900.jpg', 'library_capsule.jpg', 'header.jpg'):
            for found in (glob.glob(os.path.join(folder, name)) +
                          glob.glob(os.path.join(folder, '*', name))):
                return found
    for name in (f'{appid}_library_600x900.jpg', f'{appid}_header.jpg'):     # older Steam
        path = os.path.join(cache, name)
        if os.path.isfile(path):
            return path
    return ''


# A shortcut that only starts a game another launcher already lists (Heroic's, Lutris's and
# Bottles' "add to Steam", Prism instances) would show the same game twice.
OTHER_LAUNCHERS = re.compile(r'heroic://|lutris:rungame|bottles-cli|prismlauncher|itch://',
                             re.I)


def shortcut_id(info: dict) -> int:
    """The shortcut's 32-bit app ID: its own appid field, or (older Steam) a CRC of the
    program and the name with the top bit set."""
    appid = vdf.get(info, 'appid')
    if isinstance(appid, int) and appid:
        return appid & 0xFFFFFFFF
    text = (str(vdf.get(info, 'exe', default='')) + str(vdf.get(info, 'appname', default='')))
    return zlib.crc32(text.encode('utf-8')) | 0x80000000


def shortcut_cover(config: str, short: int) -> str:
    grid = os.path.join(config, 'grid')
    for name in (f'{short}p', f'{short}'):           # portrait first, then the wide one
        for ext in ('png', 'jpg', 'jpeg', 'webp'):
            path = os.path.join(grid, f'{name}.{ext}')
            if os.path.isfile(path):
                return path
    return ''


def shortcuts(root: str, flatpak: bool, watch: List[str]) -> List[Game]:
    """Non-Steam games added to Steam, from every account's shortcuts.vdf."""
    games = []
    for path in sorted(glob.glob(os.path.join(root, 'userdata', '*', 'config', 'shortcuts.vdf'))):
        watch.append(path)
        try:
            data = vdf.load_binary(path)
        except (OSError, vdf.VDFError) as exc:
            log.warning("steam: skipping %s: %s", path, exc)
            continue
        block = vdf.get(data, 'shortcuts')
        if not isinstance(block, dict):
            continue
        config = os.path.dirname(path)
        for info in block.values():
            if not isinstance(info, dict):
                continue
            name = str(vdf.get(info, 'appname', default='')).strip()
            exe = str(vdf.get(info, 'exe', default='')).strip().strip('"')
            options = str(vdf.get(info, 'LaunchOptions', default=''))
            if not name or vdf.get(info, 'IsHidden') == 1                     or OTHER_LAUNCHERS.search(exe + ' ' + options):
                continue
            short = shortcut_id(info)
            start = str(vdf.get(info, 'StartDir', default='')).strip().strip('"')
            last = vdf.get(info, 'LastPlayTime')
            games.append(Game(key=f'steam-shortcut:{short}', title=name, source='steam',
                              install_dir=start or os.path.dirname(exe),
                              last_played=last if isinstance(last, int) and last > 0 else 0,
                              cover=shortcut_cover(config, short), flatpak=flatpak,
                              launch={'appid': str((short << 32) | 0x02000000),
                                      'flatpak': flatpak, 'shortcut': True}))
    return games


def scan(home: str, watch: List[str]) -> List[Game]:
    games: Dict[str, Game] = {}
    for root, flatpak in roots(home):
        watch.append(os.path.join(root, 'steamapps', 'libraryfolders.vdf'))
        stats = play_stats(root)
        watch.extend(glob.glob(os.path.join(root, 'userdata', '*', 'config', 'localconfig.vdf')))
        for library in library_folders(root):
            watch.append(os.path.join(library, 'steamapps'))
            for path in sorted(glob.glob(os.path.join(library, 'steamapps', 'appmanifest_*.acf'))):
                try:
                    found = read_manifest(path, library)
                except (OSError, vdf.VDFError) as exc:
                    log.warning("steam: skipping %s: %s", path, exc)
                    continue
                if not found:
                    continue
                appid, name, install_dir, manifest_last = found
                key = f'steam:{appid}'
                if key in games:
                    continue
                minutes, last = stats.get(appid, (0, 0))
                games[key] = Game(key=key, title=name, source='steam', install_dir=install_dir,
                                  playtime=minutes, last_played=max(last, manifest_last),
                                  cover=cover(root, appid), flatpak=flatpak, store_id=appid,
                                  launch={'appid': appid, 'flatpak': flatpak})
        for game in shortcuts(root, flatpak, watch):
            games.setdefault(game.key, game)
    return list(games.values())
