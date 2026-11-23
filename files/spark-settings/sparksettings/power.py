"""Power: the profile, through powerprofilesctl, or the same D-Bus service with busctl when the
CLI isn't there (Fedora's tuned-ppd answers net.hadess.PowerProfiles but has no powerprofilesctl).
Screen-off and sleep timers and the power button stay in KDE's module
(kcm_powerdevilprofilesconfig) for now."""

import re
from typing import List, Optional

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
