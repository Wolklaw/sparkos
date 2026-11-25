"""Everything in Spark Settings that writes Plasma's or KWin's own files and tools, in one place.

Spark Settings keeps what it sets in ~/.config/spark/*.json, which the Spark shell reads. Plasma
(still the default session) and KWin (kept in the Spark session) don't read those files, so each
change is also written where they look, through the functions below. When the Spark shell
replaces plasmashell, delete the functions marked [plasmashell] and keep the [KWin] ones.

  [KWin]         stays after Plasma goes
    kwin_reconfigure           ask KWin to reread kwinrc / kcminputrc / kxkbrc
    kwin_effects_get/set       animation speed and window blur (kwinrc, kdeglobals)
    libinput_write             pointer and touchpad settings that survive a restart (kcminputrc)
    keyboard_write             layouts and key repeat (kxkbrc, kcminputrc)
    shortcuts live in shortcuts.py (kglobalaccel is KWin's)
  [kscreenlocker] stays after Plasma goes (the Spark session locks with it)
    lock_get/set               when the screen locks (kscreenlockerrc)
  [plasmashell]  Plasma only; the Spark shell reads ~/.config/spark instead
    apply_colorscheme, apply_wallpaper, apply_cursor    the look of the Plasma session
    powerdevil_get/set         screen-off, sleep and power button timers (powerdevilrc)
    notify_get/set             pop-up time and position (plasmanotifyrc)
    localerc_*                 your language and formats (plasma-localerc)
    baloo_*                    file indexing (baloofilerc, balooctl6)

Each function does nothing and says so when its tool is missing, so a machine without Plasma
still runs every page."""

import re
from typing import Dict, Optional

from . import core
from .core import have, kread, kwrite, run


# ── KWin ──
def kwin_reconfigure() -> bool:
    """Ask KWin to reread its config, over the session bus."""
    from . import dbus
    return dbus.call(dbus.SESSION, 'org.kde.KWin', '/KWin', 'org.kde.KWin', 'reconfigure')[0]


def kwin_effects_get() -> Dict[str, object]:
    factor = kread('kdeglobals', 'KDE', 'AnimationDurationFactor', '1')
    try:
        speed = float(factor)
    except ValueError:
        speed = 1.0
    return {'animations': speed > 0, 'blur': kread('kwinrc', 'Plugins', 'blurEnabled', 'true') != 'false'}


def kwin_effects_set(animations: Optional[bool] = None, blur: Optional[bool] = None) -> bool:
    ok = True
    if animations is not None:
        ok &= kwrite('kdeglobals', 'KDE', 'AnimationDurationFactor', '1' if animations else '0') == 0
    if blur is not None:
        ok &= kwrite('kwinrc', 'Plugins', 'blurEnabled', 'true' if blur else 'false') == 0
    return bool(ok) and kwin_reconfigure() or bool(ok)


def libinput_write(vendor: int, product: int, name: str, values: Dict[str, str]) -> bool:
    """One device's saved settings: [Libinput][vendor][product][name] in kcminputrc, the group
    KWin reads when the device appears."""
    group = f"Libinput/{vendor}/{product}/{name}"
    return all(kwrite('kcminputrc', group, k, v) == 0 for k, v in values.items())


def keyboard_write(layouts: str, variants: str, delay: int, rate: int) -> bool:
    ok = kwrite('kxkbrc', 'Layout', 'Use', 'true') == 0
    ok &= kwrite('kxkbrc', 'Layout', 'LayoutList', layouts) == 0
    ok &= kwrite('kxkbrc', 'Layout', 'VariantList', variants) == 0
    ok &= kwrite('kcminputrc', 'Keyboard', 'RepeatDelay', str(delay)) == 0
    ok &= kwrite('kcminputrc', 'Keyboard', 'RepeatRate', str(rate)) == 0
    kwin_reconfigure()
    return bool(ok)


# ── kscreenlocker ──
def lock_get() -> Dict[str, object]:
    timeout = kread('kscreenlockerrc', 'Daemon', 'Timeout', '5')
    return {'autolock': kread('kscreenlockerrc', 'Daemon', 'Autolock', 'true') != 'false',
            'minutes': int(timeout) if timeout.isdigit() else 5,
            'on_resume': kread('kscreenlockerrc', 'Daemon', 'LockOnResume', 'true') != 'false'}


def lock_set(autolock: bool, minutes: int, on_resume: bool) -> bool:
    ok = kwrite('kscreenlockerrc', 'Daemon', 'Autolock', 'true' if autolock else 'false') == 0
    ok &= kwrite('kscreenlockerrc', 'Daemon', 'Timeout', str(minutes)) == 0
    ok &= kwrite('kscreenlockerrc', 'Daemon', 'LockOnResume', 'true' if on_resume else 'false') == 0
    return bool(ok)


# ── plasmashell: the look ──
def apply_colorscheme(name: str, accent: str = '') -> bool:
    if have('plasma-apply-colorscheme'):
        cmd = ['plasma-apply-colorscheme', name]
        if accent:
            cmd += ['--accent-color', accent]
        if run(cmd)[0] == 0:
            return True
    ok = kwrite('kdeglobals', 'General', 'ColorScheme', name) == 0
    if accent and re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
        rgb = ','.join(str(int(accent[i:i + 2], 16)) for i in (1, 3, 5))
        ok &= kwrite('kdeglobals', 'General', 'AccentColor', rgb) == 0
    return bool(ok)


def apply_wallpaper(path: str) -> bool:
    return have('plasma-apply-wallpaperimage') and run(['plasma-apply-wallpaperimage', path])[0] == 0


def apply_cursor(theme: str, size: int) -> bool:
    if have('plasma-apply-cursortheme'):
        cmd = ['plasma-apply-cursortheme', theme]
        if size:
            cmd += ['--size', str(size)]
        if run(cmd)[0] == 0:
            return True
    ok = kwrite('kcminputrc', 'Mouse', 'cursorTheme', theme) == 0
    if size:
        ok &= kwrite('kcminputrc', 'Mouse', 'cursorSize', str(size)) == 0
    return bool(ok)


def colorscheme_now() -> str:
    return kread('kdeglobals', 'General', 'ColorScheme', '')


# ── plasmashell: power, notifications, language, indexing ──
POWER_PROFILES = ('AC', 'Battery')


def powerdevil_get(profile: str = 'AC') -> Dict[str, int]:
    def num(group: str, key: str, default: int) -> int:
        v = kread('powerdevilrc', f'{profile}/{group}', key, str(default))
        return int(v) if re.fullmatch(r'-?\d+', v or '') else default
    return {'screen_off_s': num('Display', 'TurnOffDisplayIdleTimeoutSec', 600),
            'sleep_s': num('SuspendAndShutdown', 'AutoSuspendIdleTimeoutSec', 1800),
            'sleep_action': num('SuspendAndShutdown', 'AutoSuspendAction', 1),
            'power_button': num('SuspendAndShutdown', 'PowerButtonAction', 8)}


def powerdevil_set(profile: str, screen_off_s: Optional[int] = None, sleep_s: Optional[int] = None,
                   power_button: Optional[int] = None) -> bool:
    ok = True
    if screen_off_s is not None:
        ok &= kwrite('powerdevilrc', f'{profile}/Display', 'TurnOffDisplayIdleTimeoutSec',
                     str(screen_off_s)) == 0
    if sleep_s is not None:
        ok &= kwrite('powerdevilrc', f'{profile}/SuspendAndShutdown', 'AutoSuspendIdleTimeoutSec',
                     str(sleep_s)) == 0
        ok &= kwrite('powerdevilrc', f'{profile}/SuspendAndShutdown', 'AutoSuspendAction',
                     '1' if sleep_s else '0') == 0
    if power_button is not None:
        ok &= kwrite('powerdevilrc', f'{profile}/SuspendAndShutdown', 'PowerButtonAction',
                     str(power_button)) == 0
    if ok:
        from . import dbus      # powerdevil rereads its config on this signal
        dbus.call(dbus.SESSION, 'org.kde.Solid.PowerManagement', '/org/kde/Solid/PowerManagement',
                  'org.kde.Solid.PowerManagement', 'refreshStatus')
    return bool(ok)


def notify_get() -> Dict[str, object]:
    t = kread('plasmanotifyrc', 'Notifications', 'PopupTimeout', '5000')
    return {'timeout_ms': int(t) if t.isdigit() else 5000,
            'position': kread('plasmanotifyrc', 'Notifications', 'PopupPosition', ''),
            'sounds_muted': kread('plasmanotifyrc', 'DoNotDisturb', 'NotificationSoundsMuted',
                                  'false') == 'true'}


def notify_set(timeout_ms: Optional[int] = None, position: Optional[str] = None,
               sounds_muted: Optional[bool] = None) -> bool:
    ok = True
    if timeout_ms is not None:
        ok &= kwrite('plasmanotifyrc', 'Notifications', 'PopupTimeout', str(timeout_ms)) == 0
    if position is not None:
        ok &= kwrite('plasmanotifyrc', 'Notifications', 'PopupPosition', position) == 0
    if sounds_muted is not None:
        ok &= kwrite('plasmanotifyrc', 'DoNotDisturb', 'NotificationSoundsMuted',
                     'true' if sounds_muted else 'false') == 0
    return bool(ok)


def localerc_read(key: str) -> str:
    return kread('plasma-localerc', 'Formats', key) or kread('plasma-localerc', 'Translations', key)


def localerc_time(default: str) -> str:
    return kread('plasma-localerc', 'Formats', 'LC_TIME', default)


def localerc_write(lang: str, language_list: str) -> bool:
    return kwrite('plasma-localerc', 'Formats', 'LANG', lang) == 0 and \
        kwrite('plasma-localerc', 'Translations', 'LANGUAGE', language_list) == 0


def localerc_write_time(value: str) -> bool:
    return kwrite('plasma-localerc', 'Formats', 'LC_TIME', value) == 0


def baloo_enabled() -> Optional[bool]:
    v = kread('baloofilerc', 'Basic Settings', 'Indexing-Enabled', '')
    return None if v == '' else v != 'false'


def baloo_set(on: bool) -> bool:
    ok = kwrite('baloofilerc', 'Basic Settings', 'Indexing-Enabled', 'true' if on else 'false') == 0
    tool = next((t for t in ('balooctl6', 'balooctl') if have(t)), None)
    if tool:
        run([tool, 'enable' if on else 'disable'], timeout=30)
    return bool(ok)


# ── spark-wl: no KWin, Plasma or KDE daemons in that session ──
# Every function above turns into a no-op that reports success, and the readers give the
# defaults, so pages save only to ~/.config/spark (and the compositor / shell read from there).
# Nothing in the spark-wl session reads a KDE rc file, and writing them would only leave stale
# state behind for the Plasma session.
import os as _os
if 'sparkwl' in _os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
    def _ok(*_a, **_k) -> bool:
        return True
    kwin_reconfigure = libinput_write = keyboard_write = lock_set = apply_colorscheme = _ok
    apply_wallpaper = apply_cursor = powerdevil_set = notify_set = kwin_effects_set = _ok
    localerc_write = localerc_write_time = baloo_set = _ok
    kwin_effects_get = lambda: {'animations': True, 'blur': True}       # noqa: E731
    lock_get = lambda: {'autolock': True, 'minutes': 5, 'on_resume': True}  # noqa: E731
    colorscheme_now = lambda: ''                                        # noqa: E731
    # a desktop that games: screens off after 10 minutes, no sleep unless asked for
    powerdevil_get = lambda profile='AC': {'screen_off_s': 600, 'sleep_s': 0,  # noqa: E731
                                           'sleep_action': 0, 'power_button': 8}
    notify_get = lambda: {'timeout_ms': 5000, 'position': '', 'sounds_muted': False}  # noqa: E731
    localerc_read = lambda key: ''                                      # noqa: E731
    localerc_time = lambda default: default                             # noqa: E731
    baloo_enabled = lambda: None                                        # noqa: E731
