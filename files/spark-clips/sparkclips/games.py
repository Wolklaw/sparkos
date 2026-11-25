"""Is a game running, and which one? Everything that decides it is here, so it is easy to fix.

The process table is read into plain Proc records (read_procs) and detect() looks at them, so
the tests feed it made-up process trees. The rules, in order:

1. Spark Games: its --track helper holds the game's title in its arguments.
2. Steam: a `reaper SteamLaunch AppId=<n>` process with something running under it. The name
   comes from the game's appmanifest in the Steam library.
3. Proton, umu or Wine: a Windows .exe running under Wine's loader, other than the helpers
   every Wine prefix starts (explorer, services, launchers, installers).
4. GameMode: a program that asked for it (gamemoded lists the process ids).

Anything else is no game; the clip folder is then "Desktop".
"""

import json
import os
import re
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence

DESKTOP = "Desktop"

# programs that run under Wine without being a game: the prefix's own helpers, launchers,
# installers and runtimes
NOT_GAMES = {
    'explorer.exe', 'services.exe', 'winedevice.exe', 'plugplay.exe', 'svchost.exe', 'rpcss.exe',
    'conhost.exe', 'start.exe', 'steam.exe', 'wineboot.exe', 'cmd.exe', 'tabtip.exe',
    'winemenubuilder.exe', 'rundll32.exe', 'wineconsole.exe', 'crashpad_handler.exe',
    'epicgameslauncher.exe', 'epicwebhelper.exe', 'galaxyclient.exe', 'battle.net.exe',
    'agent.exe', 'eadesktop.exe', 'ealauncher.exe', 'upc.exe', 'ubisoftconnect.exe',
    'steamwebhelper.exe', 'unitycrashhandler64.exe', 'unitycrashhandler32.exe',
    'gamelaunchhelper.exe', 'iexplore.exe', 'notepad.exe', 'regedit.exe', 'taskmgr.exe',
    'winecfg.exe', 'msiexec.exe', 'dxsetup.exe', 'dotnetfx.exe',
}
NOT_GAME_WORDS = ('setup', 'unins', 'install', 'redist', 'vcredist', 'crashhandler',
                  'crashreport', 'webhelper')
# Steam tools that run under their own AppId
STEAM_TOOLS = {'0', '228980', '1070560', '1391110', '1493710', '1628350', '1887720', '2180100',
               '2805730', '1580130'}


class Proc(NamedTuple):
    pid: int
    ppid: int
    comm: str
    argv: Sequence[str]
    exe: str = ''


class Game(NamedTuple):
    name: str
    source: str            # 'spark-games', 'steam', 'proton', 'wine' or 'gamemode'
    pid: int


def read_procs(proc: str = '/proc') -> Dict[int, Proc]:
    """The running processes of this PC (kernel threads left out)."""
    out: Dict[int, Proc] = {}
    try:
        names = [n for n in os.listdir(proc) if n.isdigit()]
    except OSError:
        return out
    for name in names:
        base = os.path.join(proc, name)
        try:
            with open(os.path.join(base, 'cmdline'), 'rb') as f:
                raw = f.read(8192)
            if not raw:
                continue
            with open(os.path.join(base, 'stat'), 'rb') as f:
                stat = f.read()
        except OSError:
            continue
        head, _, tail = stat.partition(b'(')
        comm_raw, _, rest = tail.rpartition(b')')
        fields = rest.split()
        if len(fields) < 2:
            continue
        try:
            exe = os.readlink(os.path.join(base, 'exe'))
        except OSError:
            exe = ''
        argv = [a.decode('utf-8', 'replace') for a in raw.split(b'\0') if a]
        out[int(name)] = Proc(int(name), int(fields[1]), comm_raw.decode('utf-8', 'replace'),
                              argv, exe)
    return out


def _children(procs: Dict[int, Proc]) -> Dict[int, List[int]]:
    kids: Dict[int, List[int]] = {}
    for p in procs.values():
        kids.setdefault(p.ppid, []).append(p.pid)
    return kids


def _has_descendant(pid: int, kids: Dict[int, List[int]], procs: Dict[int, Proc]) -> bool:
    return any(k in procs and k != pid for k in kids.get(pid, ()))


def _ancestors(p: Proc, procs: Dict[int, Proc], limit: int = 40) -> Iterable[Proc]:
    seen = 0
    cur = procs.get(p.ppid)
    while cur is not None and seen < limit:
        yield cur
        cur = procs.get(cur.ppid) if cur.ppid != cur.pid else None
        seen += 1


# ─── Names ───

def steam_roots(home: Optional[str] = None) -> List[str]:
    home = home or os.path.expanduser('~')
    roots = [os.path.join(home, '.local/share/Steam/steamapps'),
             os.path.join(home, '.steam/steam/steamapps'),
             os.path.join(home, '.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps')]
    found: List[str] = []
    for root in roots:
        if os.path.isdir(root) and os.path.realpath(root) not in [os.path.realpath(f) for f in found]:
            found.append(root)
        try:
            with open(os.path.join(root, 'libraryfolders.vdf'), encoding='utf-8',
                      errors='replace') as f:
                for path in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                    lib = os.path.join(path.replace('\\\\', '\\'), 'steamapps')
                    if os.path.isdir(lib) and lib not in found:
                        found.append(lib)
        except OSError:
            continue
    return found


def steam_name(appid: str, roots: Optional[Sequence[str]] = None) -> Optional[str]:
    """The game's name from Steam's appmanifest_<id>.acf."""
    for root in (steam_roots() if roots is None else roots):
        try:
            with open(os.path.join(root, f'appmanifest_{appid}.acf'), encoding='utf-8',
                      errors='replace') as f:
                match = re.search(r'"name"\s+"([^"]*)"', f.read())
            if match and match.group(1).strip():
                return match.group(1).strip()
        except OSError:
            continue
    return None


def pretty_exe(name: str) -> str:
    """'EldenRing.exe' -> 'EldenRing'; 'my_game-x64.exe' -> 'my game x64'."""
    stem = re.sub(r'\.exe$', '', name, flags=re.I)
    return re.sub(r'[_\-]+', ' ', stem).strip() or name


# ─── The rules ───

def _spark_games(procs: Dict[int, Proc]) -> Optional[Game]:
    for p in sorted(procs.values()):
        if '--track' not in p.argv:
            continue
        if not any(os.path.basename(a) == 'spark_games.py' for a in p.argv[:4]):
            continue
        try:
            spec = json.loads(p.argv[p.argv.index('--track') + 1])
            title = str(spec.get('title') or '').strip()
        except (ValueError, IndexError, AttributeError):
            continue
        if title:
            return Game(title, 'spark-games', p.pid)
    return None


def _steam(procs: Dict[int, Proc], kids, names: Callable[[str], Optional[str]]) -> Optional[Game]:
    for p in sorted(procs.values()):
        if 'SteamLaunch' not in p.argv:
            continue
        appid = next((a.split('=', 1)[1] for a in p.argv if a.startswith('AppId=')), '')
        if not appid.isdigit() or appid in STEAM_TOOLS:
            continue
        if not _has_descendant(p.pid, kids, procs):
            continue
        return Game(names(appid) or f"Steam {appid}", 'steam', p.pid)
    return None


def _is_wine_exe(p: Proc) -> Optional[str]:
    """The .exe name when this is a Windows program running under Wine's loader."""
    if not p.argv:
        return None
    first = p.argv[0].replace('\\', '/')
    base = first.rsplit('/', 1)[-1]
    if not base.lower().endswith('.exe'):
        return None
    loader = os.path.basename(p.exe).lower()
    if not (loader.startswith('wine') or 'wine' in p.comm.lower() or loader.endswith('preloader')
            or '/proton' in p.exe.lower() or '/proton' in first.lower()):
        return None
    low = base.lower()
    if low in NOT_GAMES or any(w in low for w in NOT_GAME_WORDS):
        return None
    return base


def _wine(procs: Dict[int, Proc]) -> Optional[Game]:
    for p in sorted(procs.values()):
        exe = _is_wine_exe(p)
        if not exe:
            continue
        via_proton = any(('umu-run' in ' '.join(a.argv[:3]) or 'proton' in ' '.join(a.argv[:3]).lower()
                          or '/umu' in a.exe) for a in _ancestors(p, procs))
        return Game(pretty_exe(exe), 'proton' if via_proton else 'wine', p.pid)
    return None


def _gamemode(procs: Dict[int, Proc], pids: Iterable[int]) -> Optional[Game]:
    for pid in sorted(pids):
        p = procs.get(pid)
        if p is None:
            continue
        name = os.path.basename(p.exe) if p.exe else (os.path.basename(p.argv[0]) if p.argv else p.comm)
        return Game(pretty_exe(name or p.comm), 'gamemode', pid)
    return None


def detect(procs: Dict[int, Proc], gamemode_pids: Iterable[int] = (),
           names: Optional[Callable[[str], Optional[str]]] = None) -> Optional[Game]:
    kids = _children(procs)
    names = names or steam_name
    return (_spark_games(procs) or _steam(procs, kids, names) or _wine(procs)
            or _gamemode(procs, gamemode_pids))


def gamemode_clients() -> List[int]:
    """Process ids GameMode's daemon knows about (empty when it isn't running)."""
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('com.feralinteractive.GameMode', '/com/feralinteractive/GameMode',
                              'com.feralinteractive.GameMode', 'ListGames', None,
                              GLib.VariantType('(a(io))'), Gio.DBusCallFlags.NO_AUTO_START,
                              1500, None)
        return [int(pid) for pid, _path in reply.unpack()[0]]
    except Exception:                               # noqa: BLE001 - not running, no bus, no gi
        return []


def current_game() -> Optional[Game]:
    return detect(read_procs(), gamemode_clients())
