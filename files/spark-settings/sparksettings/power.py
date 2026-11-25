"""Power: the profile, through powerprofilesctl, or the same D-Bus service with busctl when the
CLI isn't there (Fedora's tuned-ppd answers net.hadess.PowerProfiles but has no powerprofilesctl).
Screen-off and sleep timers, the power button and the lock screen are saved in
~/.config/spark/power.json and lock.json (the Spark shell reads them) and written where Plasma
looks (plasma.py). logind says what this machine can do and what it does when idle."""

import re
from typing import List, Optional

from . import core, dbus, plasma
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


# ── sleep, screen off, power button, lock ──
LOGIND = (dbus.SYSTEM, 'org.freedesktop.login1', '/org/freedesktop/login1',
          'org.freedesktop.login1.Manager')
# minutes; 0 is never
SCREEN_OFF_MINUTES = (0, 1, 2, 5, 10, 15, 30, 60)
SLEEP_MINUTES = (0, 5, 10, 15, 30, 60, 120)
LOCK_MINUTES = (1, 2, 5, 10, 15, 30)
# the power button actions, with Plasma's numbers
BUTTON_ACTIONS = (('Nothing', 0), ('Sleep', 1), ('Hibernate', 2), ('Shut down', 8),
                  ('Lock the screen', 32), ('Ask what to do', 16))


def can_sleep() -> bool:
    ok, data, _ = dbus.call(*LOGIND, 'CanSuspend')
    return ok and data in ('yes', 'challenge')


def logind_idle() -> str:
    """What logind itself does when idle ("ignore" unless the system sets it)."""
    v = dbus.get(*LOGIND, 'IdleAction')
    return v if isinstance(v, str) else ''


def timers() -> dict:
    """The saved timers (Spark's file first, Plasma's as the starting point), in minutes."""
    saved = core.spark_load('power')
    p = plasma.powerdevil_get('AC')
    return {'screen_off': saved.get('screen_off', p['screen_off_s'] // 60),
            'sleep': saved.get('sleep', p['sleep_s'] // 60 if p['sleep_action'] else 0),
            'power_button': saved.get('power_button', p['power_button'])}


def set_timers(screen_off: int, sleep: int, power_button: int) -> bool:
    ok = core.spark_save('power', screen_off=screen_off, sleep=sleep, power_button=power_button)
    for profile in plasma.POWER_PROFILES:
        ok &= plasma.powerdevil_set(profile, screen_off * 60, sleep * 60, power_button)
    return bool(ok) and _compositor()


def lock_get() -> dict:
    saved = core.spark_load('lock')
    now = plasma.lock_get()
    return {k: saved.get(k, now[k]) for k in now}


def lock_set(autolock: bool, minutes: int, on_resume: bool) -> bool:
    ok = core.spark_save('lock', autolock=autolock, minutes=minutes, on_resume=on_resume)
    return plasma.lock_set(autolock, minutes, on_resume) and ok and _compositor()


def _compositor() -> bool:
    """spark-wl: the compositor runs the idle timers (no PowerDevil, no KScreenLocker)."""
    from . import inputdev
    return inputdev._compositor_write() if inputdev.SPARKWL else True
