"""KDE's settings modules (kcmshell6), kept only as the last resort in "More settings", for
what has no Spark page (drawing tablets, touchscreens, anything Plasma adds). open_module is the
one place Spark Settings starts a KDE module. Page routing: which KCMs a Spark page replaces,
used by the image's systemsettings and kcmshell6 stand-ins so Plasma's own links land here."""

import glob
import os
import re
from typing import Dict, List, Optional, Tuple

from . import core
from .core import kde_tool, out, spawn

# KDE module -> the Spark Settings page that owns it (used by the systemsettings and kcmshell6
# wrappers in the image, and so that "More settings" doesn't list what has its own page)
ROUTES: Dict[str, str] = {
    'kcm_kscreen': 'displays', 'kcm_kscreen_edid': 'displays', 'kcm_nightlight': 'displays',
    'kcm_pulseaudio': 'sound', 'kcm_pipewire': 'sound',
    'kcm_networkmanagement': 'network', 'kcm_wifi': 'network', 'kcm_vpn': 'network',
    'kcm_proxy': 'network', 'kcm_networkmanagement_wifi': 'network',
    'kcm_bluetooth': 'bluetooth', 'kcm_bluedevildevices': 'bluetooth',
    'kcm_powerdevilprofilesconfig': 'power', 'kcm_energyinfo': 'power',
    'kcm_componentchooser': 'defaultapps', 'kcm_filetypes': 'defaultapps',
    'kcm_clock': 'datetime', 'kcm_regionandlang': 'datetime', 'kcm_locale': 'datetime',
    'kcm_printer_manager': 'printers',
    'kcm_autostart': 'startup',
    'kcm_about-distro': 'about',
    'kcm_lookandfeel': 'appearance', 'kcm_colors': 'appearance', 'kcm_wallpaper': 'appearance',
    'kcm_cursortheme': 'appearance', 'kcm_kwin_effects': 'appearance',
    'kcm_animations': 'appearance', 'kcm_fonts': 'appearance',
    'kcm_mouse': 'input', 'kcm_keyboard': 'input', 'kcm_touchpad': 'input',
    'kcm_gamecontroller': 'input',
    'kcm_keys': 'shortcuts', 'kcm_notifications': 'notifications', 'kcm_users': 'users',
    'kcm_device_automounter': 'storage', 'kcm_baloofile': 'storage',
    'kcm_screenlocker': 'power',
}
def route_for(module: str) -> Optional[str]:
    return ROUTES.get(module.strip().replace('.desktop', ''))


class Kcm:
    def __init__(self, id_: str, name: str):
        self.id, self.name = id_, name


def parse_list(text: str) -> List[Kcm]:
    found = []
    for line in text.splitlines():
        m = re.match(r'^\s*(\S+)\s+-\s+(.*)$', line)
        if m and not m.group(1).startswith(('Usage', 'Options')):
            found.append(Kcm(m.group(1), m.group(2).strip()))
    return found


def desktop_scan() -> List[Kcm]:
    """Without kcmshell6 --list: the module entries in /usr/share/applications."""
    found = []
    for path in sorted(glob.glob('/usr/share/applications/kcm_*.desktop') +
                       glob.glob('/usr/share/applications/org.kde.kcm_*.desktop')):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                m = re.search(r'^Name=(.+)$', f.read(), re.M)
        except OSError:
            continue
        id_ = os.path.basename(path)[:-8]
        found.append(Kcm(id_.replace('org.kde.', ''), m.group(1) if m else id_))
    return found


def all_modules() -> List[Kcm]:
    tool = kde_tool('kcmshell6')
    found = parse_list(out([tool, '--list'], timeout=15)) if tool else []
    return sorted(found or desktop_scan(), key=lambda k: k.name.lower())


def more_settings() -> List[Kcm]:
    """Every module that doesn't have its own Spark page (none in the Spark compositor session)."""
    if 'sparkwl' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
        return []
    return [k for k in all_modules() if k.id not in ROUTES]


def open_module(module: str) -> bool:
    tool = kde_tool('kcmshell6')
    return bool(tool) and spawn([tool, module])


def open_kde() -> bool:
    tool = kde_tool('systemsettings')
    return bool(tool) and spawn([tool])
