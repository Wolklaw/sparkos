"""When not to update or notify: a game is running, the connection is metered, or the
battery is low. Cheap reads of /proc, /sys and one D-Bus property; nothing stays running."""

import os
import re
import subprocess
from typing import Optional

from .core import Env

# A process whose command line holds one of these is a game (or Wine/Proton, which is how
# Windows games run): Steam starts every game under 'reaper SteamLaunch'; gamescope is the
# game compositor; wineserver runs for as long as any Wine or Proton program does.
GAME_MARKERS = (b'SteamLaunch', b'/gamescope', b'wineserver')
GAME_NAMES = {b'gamescope', b'wineserver', b'gamescope-wl'}


def game_running(env: Env) -> Optional[str]:
    """The name of a running game process, or None."""
    proc = env.path('/proc')
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, 'cmdline'), 'rb') as f:
                cmd = f.read(4096)
        except OSError:
            continue
        if not cmd:
            continue
        argv0 = os.path.basename(cmd.split(b'\0', 1)[0])
        if argv0 in GAME_NAMES or any(m in cmd for m in GAME_MARKERS):
            if argv0 == b'gamescope-session' or b'gamescope-session' in argv0:
                continue          # the Steam Deck style session itself is not a game
            return argv0.decode(errors='replace') or pid
    return None


def battery_low(env: Env, minimum: int = 20) -> Optional[int]:
    """The battery's charge when it is discharging below minimum %, else None."""
    base = env.path('/sys/class/power_supply')
    try:
        names = os.listdir(base)
    except OSError:
        return None
    for name in names:
        folder = os.path.join(base, name)

        def read(key):
            try:
                with open(os.path.join(folder, key), encoding='ascii', errors='replace') as f:
                    return f.read().strip()
            except OSError:
                return ''

        if read('type') != 'Battery' or read('scope') == 'Device':
            continue          # mice and controllers report batteries too
        if read('status') != 'Discharging':
            continue
        cap = read('capacity')
        if cap.isdigit() and int(cap) < minimum:
            return int(cap)
    return None


def metered(env: Env) -> bool:
    """NetworkManager says the connection is metered (1 = yes, 3 = guessed yes)."""
    if env.fake:
        return os.path.exists(env.path('/run/fake-metered'))
    try:
        proc = subprocess.run(
            ['gdbus', 'call', '--system', '--dest', 'org.freedesktop.NetworkManager',
             '--object-path', '/org/freedesktop/NetworkManager', '--method',
             'org.freedesktop.DBus.Properties.Get', 'org.freedesktop.NetworkManager',
             'Metered'], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    match = re.search(r'uint32 (\d+)', proc.stdout)
    return bool(match) and int(match.group(1)) in (1, 3)


def reason_to_wait(env: Env) -> Optional[str]:
    """Why a background run should wait for a later hour, or None to go ahead."""
    game = game_running(env)
    if game:
        return f"a game is running ({game})"
    if metered(env):
        return "the connection is metered"
    low = battery_low(env)
    if low is not None:
        return f"the battery is at {low}% and not charging"
    return None
