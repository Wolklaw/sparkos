"""Date, time and language: timedatectl for the zone and network time; the language and
formats of your account in KDE's plasma-localerc (read at the next sign-in)."""

import os
from typing import List, Optional

from . import core
from .core import out, run

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


def zone() -> Optional[str]:
    for line in out(['timedatectl', 'show', '-p', 'Timezone']).splitlines():
        if line.startswith('Timezone='):
            return line.split('=', 1)[1].strip()
    return None


def ntp() -> Optional[bool]:
    for line in out(['timedatectl', 'show', '-p', 'NTP']).splitlines():
        if line.startswith('NTP='):
            return line.split('=', 1)[1].strip() == 'yes'
    return None


def zones() -> List[str]:
    return [z for z in out(['timedatectl', 'list-timezones']).splitlines() if z.strip()]


def set_zone(name: str) -> str:
    rc, _, err = run(['timedatectl', 'set-timezone', name], timeout=60)
    return '' if rc == 0 else (err.strip() or "could not set the time zone")


def set_ntp(on: bool) -> str:
    rc, _, err = run(['timedatectl', 'set-ntp', 'true' if on else 'false'], timeout=60)
    return '' if rc == 0 else (err.strip() or "could not change network time")


def installed_locales() -> List[str]:
    text = out(['localectl', 'list-locales'])
    return [x.strip() for x in text.splitlines() if x.strip()]


def languages_available() -> list:
    have = set(installed_locales())
    if not have:
        return LANGUAGES
    return [l for l in LANGUAGES if l[1] in have or l[1].replace('UTF-8', 'utf8') in have]


def language_now() -> str:
    return core.kread('plasma-localerc', 'Formats', 'LANG') or \
        core.kread('plasma-localerc', 'Translations', 'LANG') or os.environ.get('LANG', '')


def set_language(lang: str, language_list: str) -> bool:
    ok = core.kwrite('plasma-localerc', 'Formats', 'LANG', lang) == 0
    ok = ok and core.kwrite('plasma-localerc', 'Translations', 'LANGUAGE', language_list) == 0
    return ok


def clock_24h() -> bool:
    return core.kread('plasma-localerc', 'Formats', 'LC_TIME', language_now()).startswith(
        ('fr', 'en_GB', 'en_CA', 'de', 'es'))


def set_clock_24h(on: bool) -> bool:
    if on:
        return core.kwrite('plasma-localerc', 'Formats', 'LC_TIME', H24) == 0
    return core.kwrite('plasma-localerc', 'Formats', 'LC_TIME', H12) == 0
