"""KDE's settings modules, listed through kcmshell6 --list and opened with kcmshell6, for what
Spark Settings doesn't cover yet. Page routing: which KCMs a Spark page replaces."""

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
}
# page key -> a short note for the "opens in KDE's settings" pages
KDE_PAGES: List[Tuple[str, str, List[str]]] = [
    ('appearance', "Appearance", ['kcm_lookandfeel', 'kcm_colors', 'kcm_wallpaper',
                                   'kcm_cursortheme', 'kcm_fonts', 'kcm_icons', 'kcm_desktoptheme',
                                   'kcm_kwin_effects', 'kcm_animations']),
    ('input', "Mouse, keyboard and controllers", ['kcm_mouse', 'kcm_keyboard', 'kcm_touchpad',
                                                   'kcm_keys', 'kcm_gamecontroller',
                                                   'kcm_tablet']),
    ('users', "Users", ['kcm_users']),
    ('storage', "Storage and games drive", ['kcm_device_automounter', 'kcm_baloofile']),
]


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
    """Every module that doesn't have its own Spark page."""
    return [k for k in all_modules() if k.id not in ROUTES]


def open_module(module: str) -> bool:
    tool = kde_tool('kcmshell6')
    return bool(tool) and spawn([tool, module])


def open_kde() -> bool:
    tool = kde_tool('systemsettings')
    return bool(tool) and spawn([tool])
