"""Starting games, and the play sessions Spark Games records.

Every game starts through the program that owns it:

  Steam    steam steam://rungameid/<appid>
           flatpak run com.valvesoftware.Steam steam://rungameid/<appid>
  Heroic   xdg-open heroic://launch/<runner>/<appName>      (runner: legendary, gog, nile)
  Lutris   lutris lutris:rungameid/<id>
           flatpak run net.lutris.Lutris lutris:rungameid/<id>
  itch     ~/.itch/itch-setup --appname itch --run-game <game id>   (no prompt)
           xdg-open itch://install?game_id=<game id>&launch         (the app asks first)
  Bottles  bottles-cli run -b <bottle> -p <program>
           flatpak run --command=bottles-cli com.usebottles.bottles run -b <bottle> -p <program>
  Minecraft  minecraft-launcher, or flatpak run com.mojang.Minecraft
  Prism    prismlauncher --launch <instance>
           flatpak run org.prismlauncher.PrismLauncher --launch <instance>
  Own      the program itself; a Windows .exe through umu-run (Proton), with MangoHud and
           GameMode when the game's options ask for them

The window doesn't wait for the game. A small helper process (spark-games --track) starts it
and records the session in ~/.local/share/spark-games/playtime.json: for your own games it
waits for the program to exit; for launcher games it looks every 10 s for a process running
from the game's folder, and stops when that is gone. It reads /proc only; nothing is injected.
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from . import (BOTTLES_FLATPAK, LUTRIS_FLATPAK, MINECRAFT_FLATPAK, PRISM_FLATPAK,
               STEAM_FLATPAK)
from .core import Game, data_dir, log, read_json, write_json

try:
    import fcntl
except ImportError:                       # Windows dev runs only
    fcntl = None  # type: ignore[assignment]

ENTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'spark_games.py')
MIN_SESSION = 30          # seconds; shorter runs (a crash at start) aren't counted
POLL = 10.0               # seconds between looks at /proc while a launcher game runs
APPEAR = 600.0            # how long to wait for a launcher game to show up (Steam may update it)


class LaunchError(Exception):
    """code is a key in strings.py; detail is shown after it."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(code)
        self.code, self.detail = code, detail


@dataclass
class Plan:
    argv: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    cwd: str = ''
    wait: bool = False            # the game is this process: wait for it to exit
    watch_dir: str = ''           # a launcher starts it: look for processes in this folder


def steam_paste_line(mangohud: bool, gamemode: bool) -> str:
    """What to paste into Steam's launch options for these settings."""
    parts = (['MANGOHUD=1'] if mangohud else []) + (['gamemoderun'] if gamemode else [])
    return ' '.join(parts + ['%command%'])


def plan(game: Game, options: Optional[Dict[str, Any]] = None,
         which: Callable[[str], Optional[str]] = None) -> Plan:
    """The command that starts this game. Raises LaunchError when something needed is missing."""
    from .core import which as real_which
    which = which or real_which
    options = options or {}
    info = game.launch or {}
    flatpak_cmd = ['flatpak', 'run']

    if game.source == 'steam':
        url = f'steam://rungameid/{info.get("appid") or game.store_id}'
        if info.get('flatpak'):
            if not which('flatpak'):
                raise LaunchError('missing_program', 'flatpak')
            argv = flatpak_cmd + [STEAM_FLATPAK, url]
        elif which('steam'):
            argv = ['steam', url]
        elif which('xdg-open'):
            argv = ['xdg-open', url]
        else:
            raise LaunchError('missing_program', 'steam')
        return Plan(argv, watch_dir=game.install_dir)

    if game.launcher == 'heroic':
        if not which('xdg-open'):
            raise LaunchError('missing_program', 'xdg-open')
        url = f'heroic://launch/{info.get("runner", "legendary")}/{quote(str(info.get("app", "")), safe="")}'
        return Plan(['xdg-open', url], watch_dir=game.install_dir)

    if game.source == 'lutris':
        url = f'lutris:rungameid/{info.get("id")}'
        if info.get('flatpak'):
            if not which('flatpak'):
                raise LaunchError('missing_program', 'flatpak')
            argv = flatpak_cmd + [LUTRIS_FLATPAK, url]
        elif which('lutris'):
            argv = ['lutris', url]
        elif which('xdg-open'):
            argv = ['xdg-open', url]
        else:
            raise LaunchError('missing_program', 'lutris')
        return Plan(argv, watch_dir=game.install_dir)

    if game.source == 'itch':
        setup = str(info.get('setup') or '')
        if setup and os.access(setup, os.X_OK):
            return Plan([setup, '--appname', 'itch', '--run-game', str(info.get('game_id'))],
                        watch_dir=game.install_dir)
        if not which('xdg-open'):
            raise LaunchError('missing_program', 'xdg-open')
        url = f'itch://install?game_id={quote(str(info.get("game_id", "")), safe="")}&launch'
        return Plan(['xdg-open', url], watch_dir=game.install_dir)

    if game.source == 'bottles':
        run = ['run', '-b', str(info.get('bottle', '')), '-p', str(info.get('program', ''))]
        if info.get('flatpak'):
            if not which('flatpak'):
                raise LaunchError('missing_program', 'flatpak')
            argv = flatpak_cmd + ['--command=bottles-cli', BOTTLES_FLATPAK] + run
        elif which('bottles-cli'):
            argv = ['bottles-cli'] + run
        else:
            raise LaunchError('missing_program', 'bottles-cli')
        return Plan(argv, watch_dir=game.install_dir)

    if game.source in ('minecraft', 'prism'):
        flatpak_id, command = (MINECRAFT_FLATPAK, 'minecraft-launcher')             if game.source == 'minecraft' else (PRISM_FLATPAK, 'prismlauncher')
        args = [] if game.source == 'minecraft' else ['--launch', str(info.get('instance', ''))]
        if info.get('flatpak'):
            if not which('flatpak'):
                raise LaunchError('missing_program', 'flatpak')
            argv = flatpak_cmd + [flatpak_id] + args
        elif which(command):
            argv = [command] + args
        else:
            raise LaunchError('missing_program', command)
        return Plan(argv, watch_dir=game.install_dir)

    if game.source == 'own':
        exe = str(info.get('exe') or '')
        if not os.path.isfile(exe):
            raise LaunchError('missing_file', exe)
        args = [str(a) for a in info.get('args') or []]
        env: Dict[str, str] = {}
        if options.get('mangohud'):
            env['MANGOHUD'] = '1'
        prefix = ['gamemoderun'] if options.get('gamemode') and which('gamemoderun') else []
        if info.get('windows'):
            if not which('umu-run'):
                raise LaunchError('no_umu')
            env['WINEPREFIX'] = os.path.join(data_dir(), 'prefixes', str(info.get('id', 'default')))
            env.setdefault('GAMEID', 'umu-default')
            argv = prefix + ['umu-run', exe] + args
        else:
            if not os.access(exe, os.X_OK):
                raise LaunchError('not_executable', exe)
            argv = prefix + [exe] + args
        return Plan(argv, env=env, cwd=os.path.dirname(exe), wait=True)

    raise LaunchError('unknown_source', game.source)


def start(game: Game, options: Optional[Dict[str, Any]] = None) -> None:
    """Start the game through the helper process, which records the session."""
    p = plan(game, options)
    if p.env.get('WINEPREFIX'):
        os.makedirs(p.env['WINEPREFIX'], exist_ok=True)
    spec = {'key': game.key, 'title': game.title, 'argv': p.argv, 'env': p.env, 'cwd': p.cwd,
            'wait': p.wait, 'watch_dir': p.watch_dir}
    log.info("starting %s: %s", game.key, ' '.join(p.argv))
    try:
        subprocess.Popen([sys.executable, ENTRY, '--track', json.dumps(spec)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        raise LaunchError('start_failed', str(exc)) from exc


# ─── Watching a game (the --track helper) ─────────────────────

def running_from(folder: str, proc: str = '/proc', skip: Optional[set] = None) -> bool:
    """Whether any process's command line points into this folder."""
    if not folder or not os.path.isdir(proc):
        return False
    needle = os.path.normpath(folder).encode('utf-8', 'surrogateescape')
    skip = skip or set()
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit() and p not in skip]
    except OSError:
        return False
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, 'cmdline'), 'rb') as f:
                if needle in f.read():
                    return True
        except OSError:
            continue
    return False


def track(spec: Dict[str, Any], proc: str = '/proc', poll: float = POLL, appear: float = APPEAR,
          clock: Callable[[], float] = time.time,
          sleep: Callable[[float], None] = time.sleep) -> Optional[Dict[str, Any]]:
    """Start the game, wait for it to end, and record the session. Returns the session."""
    env = dict(os.environ)
    env.update(spec.get('env') or {})
    start_time = clock()
    try:
        child = subprocess.Popen(spec['argv'], env=env, cwd=spec.get('cwd') or None,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("could not start %s: %s", spec.get('key'), exc)
        return None
    if spec.get('wait'):
        child.wait()
        end = clock()
    else:
        skip = {str(os.getpid()), str(child.pid)}
        folder = spec.get('watch_dir') or ''
        seen_at = None
        while seen_at is None and clock() - start_time < appear:
            sleep(poll)
            child.poll()                         # reap the launcher command when it returns
            if running_from(folder, proc, skip):
                seen_at = clock()
        if seen_at is None:
            return None                          # never started, or nothing to watch
        start_time = seen_at                     # loading and updates don't count
        end = seen_at
        misses = 0
        while misses < 2:                         # two empty looks in a row: it has ended
            sleep(poll)
            child.poll()
            if running_from(folder, proc, skip):
                end, misses = clock(), 0
            else:
                misses += 1
    if end - start_time < MIN_SESSION:
        return None
    return record(spec['key'], spec.get('title', ''), int(start_time), int(end))


# ─── Play sessions ────────────────────────────────────────────

def playtime_path() -> str:
    return os.path.join(data_dir(), 'playtime.json')


def load_sessions() -> List[Dict[str, Any]]:
    data = read_json(playtime_path(), {})
    items = data.get('sessions') if isinstance(data, dict) else None
    return [s for s in items if isinstance(s, dict)] if isinstance(items, list) else []


def record(key: str, title: str, start_time: int, end: int) -> Dict[str, Any]:
    """Append one session. A lock file keeps two helpers from writing at once."""
    session = {'game': key, 'title': title, 'start': start_time, 'end': end}
    lock_path = playtime_path() + '.lock'
    lock = None
    try:
        lock = open(lock_path, 'w')
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        lock = None
    try:
        sessions = load_sessions()
        sessions.append(session)
        write_json(playtime_path(), {'sessions': sessions})
    finally:
        if lock:
            lock.close()
    log.info("recorded %s: %d min", key, (end - start_time) // 60)
    return session


def totals(sessions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, int]]:
    """game key -> {minutes, last} from the recorded sessions."""
    out: Dict[str, Dict[str, int]] = {}
    for s in load_sessions() if sessions is None else sessions:
        try:
            start_time, end = int(s['start']), int(s['end'])
        except (KeyError, TypeError, ValueError):
            continue
        t = out.setdefault(str(s.get('game')), {'minutes': 0, 'last': 0})
        t['minutes'] += max(0, end - start_time) // 60
        t['last'] = max(t['last'], end)
    return out
