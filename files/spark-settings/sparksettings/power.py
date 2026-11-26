"""Power: the profile, through powerprofilesctl, or the same D-Bus service with busctl when the
CLI isn't there (Fedora's tuned-ppd answers net.hadess.PowerProfiles but has no powerprofilesctl).
Screen-off and sleep timers and the lock screen are saved in
~/.config/spark/power.json and lock.json (the compositor and Spark shell read them). logind says what this machine can do and what it does when idle."""

import re
from typing import List, Optional

from . import core, dbus
from .core import have, out, run

PROFILE_ORDER = ('power-saver', 'balanced', 'performance')
_BUS = ['busctl', '--system']
_OBJ = ['net.hadess.PowerProfiles', '/net/hadess/PowerProfiles', 'net.hadess.PowerProfiles']


def profiles() -> List[str]:
    if have('powerprofilesctl'):
        found = re.findall(r'^\*?\s*([a-z-]+):\s*$', out(['powerprofilesctl', 'list']), re.M)
    else:
        found = re.findall(r'"Profile"\s+s\s+"([a-z-]+)"', out([*_BUS, 'get-property', *_OBJ, 'Profiles']))
    return [p for p in PROFILE_ORDER if p in found]


def current() -> Optional[str]:
    if have('powerprofilesctl'):
        return out(['powerprofilesctl', 'get']).strip() or None
    m = re.search(r'"([a-z-]+)"', out([*_BUS, 'get-property', *_OBJ, 'ActiveProfile']))
    return m.group(1) if m else None


def set_profile(name: str) -> bool:
    if have('powerprofilesctl'):
        return run(['powerprofilesctl', 'set', name])[0] == 0
    return run([*_BUS, 'set-property', *_OBJ, 'ActiveProfile', 's', name])[0] == 0


# ── sleep, screen off, lock ──
LOGIND = (dbus.SYSTEM, 'org.freedesktop.login1', '/org/freedesktop/login1',
          'org.freedesktop.login1.Manager')
# minutes; 0 is never
SCREEN_OFF_MINUTES = (0, 1, 2, 5, 10, 15, 30, 60)
SLEEP_MINUTES = (0, 5, 10, 15, 30, 60, 120)
LOCK_MINUTES = (1, 2, 5, 10, 15, 30)


def can_sleep() -> bool:
    ok, data, _ = dbus.call(*LOGIND, 'CanSuspend')
    return ok and data in ('yes', 'challenge')


def logind_idle() -> str:
    """What logind itself does when idle ("ignore" unless the system sets it)."""
    v = dbus.get(*LOGIND, 'IdleAction')
    return v if isinstance(v, str) else ''


def timers() -> dict:
    """The saved timers, in minutes (0 is never)."""
    saved = core.spark_load('power')
    return {'screen_off': saved.get('screen_off', 10), 'sleep': saved.get('sleep', 0)}


def set_timers(screen_off: int, sleep: int) -> bool:
    ok = core.spark_save('power', screen_off=screen_off, sleep=sleep)
    return ok and _compositor()


def lock_get() -> dict:
    saved = core.spark_load('lock')
    return {'autolock': saved.get('autolock', True), 'minutes': saved.get('minutes', 5),
            'on_resume': saved.get('on_resume', True)}


def lock_set(autolock: bool, minutes: int, on_resume: bool) -> bool:
    ok = core.spark_save('lock', autolock=autolock, minutes=minutes, on_resume=on_resume)
    return ok and _compositor()


def _compositor() -> bool:
    """The compositor runs the idle timers; tell it to read them again."""
    from . import inputdev
    return inputdev._compositor_write()
