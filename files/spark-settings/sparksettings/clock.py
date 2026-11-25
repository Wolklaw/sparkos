"""Date, time and language: systemd-timedated and systemd-localed over D-Bus for the zone, the
clock and the machine's language; your own language and formats in ~/.config/spark/locale.json
(the Spark shell reads it), also written to Plasma's plasma-localerc so Plasma follows today."""

import os
from typing import List, Optional

from . import core, dbus, plasma
from .core import out

LANGUAGES = [   # label, LANG, LANGUAGE list
    ("English (Canada)", 'en_CA.UTF-8', 'en_CA:en'),
    ("Français (Canada)", 'fr_CA.UTF-8', 'fr_CA:fr'),
    ("English (United States)", 'en_US.UTF-8', 'en_US:en'),
    ("English (United Kingdom)", 'en_GB.UTF-8', 'en_GB:en'),
    ("Français (France)", 'fr_FR.UTF-8', 'fr_FR:fr'),
]
# the formats (date, clock) follow a locale; these two write the clock as 24 or 12 hours
H24 = 'fr_CA.UTF-8'
H12 = 'en_US.UTF-8'


TD = (dbus.SYSTEM, 'org.freedesktop.timedate1', '/org/freedesktop/timedate1',
      'org.freedesktop.timedate1')
LC = (dbus.SYSTEM, 'org.freedesktop.locale1', '/org/freedesktop/locale1', 'org.freedesktop.locale1')


def zone() -> Optional[str]:
    v = dbus.get(*TD, 'Timezone')
    return v if isinstance(v, str) and v else None


def ntp() -> Optional[bool]:
    v = dbus.get(*TD, 'NTP')
    return v if isinstance(v, bool) else None


def can_ntp() -> bool:
    return dbus.get(*TD, 'CanNTP') is not False


def zones() -> List[str]:
    """timedated's own list (systemd 258 and later), else timedatectl's."""
    ok, data, _ = dbus.call(*TD, 'ListTimezones')
    if ok and isinstance(data, list) and data:
        return [z for z in data if isinstance(z, str)]
    return [z for z in out(['timedatectl', 'list-timezones']).splitlines() if z.strip()]


def set_zone(name: str) -> str:
    ok, _d, err = dbus.call(*TD, 'SetTimezone', 'sb', name, 'true', timeout=60)
    return '' if ok else (err or "could not set the time zone")


def set_ntp(on: bool) -> str:
    ok, _d, err = dbus.call(*TD, 'SetNTP', 'bb', 'true' if on else 'false', 'true', timeout=60)
    return '' if ok else (err or "could not change network time")


def set_time(year: int, month: int, day: int, hour: int, minute: int) -> str:
    """Set the clock by hand, in the current time zone (network time has to be off)."""
    from datetime import datetime
    try:
        when = datetime(year, month, day, hour, minute)
        z = zone()
        if z:
            from zoneinfo import ZoneInfo
            when = when.replace(tzinfo=ZoneInfo(z))
        usec = int(when.timestamp()) * 1_000_000
    except (ValueError, OSError, ImportError, KeyError) as exc:
        return str(exc)
    ok, _d, err = dbus.call(*TD, 'SetTime', 'xbb', str(usec), 'false', 'true', timeout=60)
    return '' if ok else (err or "could not set the time")


def system_language() -> str:
    """The language the whole machine (sign-in screen, other users) starts in, from localed."""
    v = dbus.get(*LC, 'Locale')
    for item in (v['data'] if isinstance(v, dict) and 'data' in v else v) or []:
        if isinstance(item, str) and item.startswith('LANG='):
            return item[5:]
    return ''


def set_system_language(lang: str) -> str:
    ok, _d, err = dbus.call(*LC, 'SetLocale', 'asb', '1', f'LANG={lang}', 'true', timeout=60)
    return '' if ok else (err or "could not change the system language")


def installed_locales() -> List[str]:
    text = out(['localectl', 'list-locales'])
    return [x.strip() for x in text.splitlines() if x.strip()]


def languages_available() -> list:
    have = set(installed_locales())
    if not have:
        return LANGUAGES
    return [l for l in LANGUAGES if l[1] in have or l[1].replace('UTF-8', 'utf8') in have]


def language_now() -> str:
    return core.spark_load('locale').get('lang') or plasma.localerc_read('LANG') or \
        os.environ.get('LANG', '')


def set_language(lang: str, language_list: str) -> bool:
    ok = core.spark_save('locale', lang=lang, language=language_list)
    return plasma.localerc_write(lang, language_list) and ok


def clock_24h() -> bool:
    saved = core.spark_load('locale').get('clock_24h')
    if isinstance(saved, bool):
        return saved
    return plasma.localerc_time(language_now()).startswith(('fr', 'en_GB', 'en_CA', 'de', 'es'))


def set_clock_24h(on: bool) -> bool:
    ok = core.spark_save('locale', clock_24h=on)
    return plasma.localerc_write_time(H24 if on else H12) and ok
