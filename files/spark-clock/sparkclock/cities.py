"""The cities the world clock offers, with their time zone names (the system's tz database)
and their names in English and French. Any other zone from the database can be typed in the
"other zone" box; it is shown by its zone name."""

import datetime as dt
from typing import Optional, Tuple

from .lang import ui_language

HOME_ZONE = 'America/Toronto'          # Montréal's zone: Eastern time

CITIES = (
    ('America/Toronto', 'Montréal', 'Montréal'),
    ('America/Vancouver', 'Vancouver', 'Vancouver'),
    ('America/Edmonton', 'Edmonton', 'Edmonton'),
    ('America/Winnipeg', 'Winnipeg', 'Winnipeg'),
    ('America/Halifax', 'Halifax', 'Halifax'),
    ('America/St_Johns', "St. John's", 'Saint-Jean de Terre-Neuve'),
    ('America/New_York', 'New York', 'New York'),
    ('America/Chicago', 'Chicago', 'Chicago'),
    ('America/Denver', 'Denver', 'Denver'),
    ('America/Los_Angeles', 'Los Angeles', 'Los Angeles'),
    ('America/Mexico_City', 'Mexico City', 'Mexico'),
    ('America/Sao_Paulo', 'São Paulo', 'São Paulo'),
    ('America/Argentina/Buenos_Aires', 'Buenos Aires', 'Buenos Aires'),
    ('Atlantic/Reykjavik', 'Reykjavik', 'Reykjavik'),
    ('Europe/London', 'London', 'Londres'),
    ('Europe/Dublin', 'Dublin', 'Dublin'),
    ('Europe/Lisbon', 'Lisbon', 'Lisbonne'),
    ('Europe/Paris', 'Paris', 'Paris'),
    ('Europe/Brussels', 'Brussels', 'Bruxelles'),
    ('Europe/Berlin', 'Berlin', 'Berlin'),
    ('Europe/Madrid', 'Madrid', 'Madrid'),
    ('Europe/Rome', 'Rome', 'Rome'),
    ('Europe/Zurich', 'Zurich', 'Zurich'),
    ('Europe/Stockholm', 'Stockholm', 'Stockholm'),
    ('Europe/Athens', 'Athens', 'Athènes'),
    ('Europe/Istanbul', 'Istanbul', 'Istanbul'),
    ('Europe/Moscow', 'Moscow', 'Moscou'),
    ('Africa/Casablanca', 'Casablanca', 'Casablanca'),
    ('Africa/Algiers', 'Algiers', 'Alger'),
    ('Africa/Cairo', 'Cairo', 'Le Caire'),
    ('Africa/Lagos', 'Lagos', 'Lagos'),
    ('Africa/Nairobi', 'Nairobi', 'Nairobi'),
    ('Africa/Johannesburg', 'Johannesburg', 'Johannesburg'),
    ('Asia/Dubai', 'Dubai', 'Dubaï'),
    ('Asia/Tehran', 'Tehran', 'Téhéran'),
    ('Asia/Karachi', 'Karachi', 'Karachi'),
    ('Asia/Kolkata', 'Mumbai', 'Bombay'),
    ('Asia/Bangkok', 'Bangkok', 'Bangkok'),
    ('Asia/Singapore', 'Singapore', 'Singapour'),
    ('Asia/Shanghai', 'Shanghai', 'Shanghai'),
    ('Asia/Hong_Kong', 'Hong Kong', 'Hong Kong'),
    ('Asia/Seoul', 'Seoul', 'Séoul'),
    ('Asia/Tokyo', 'Tokyo', 'Tokyo'),
    ('Australia/Perth', 'Perth', 'Perth'),
    ('Australia/Sydney', 'Sydney', 'Sydney'),
    ('Pacific/Auckland', 'Auckland', 'Auckland'),
    ('Pacific/Honolulu', 'Honolulu', 'Honolulu'),
)
_BY_ZONE = {zone: (en, fr) for zone, en, fr in CITIES}


def city_name(zone: str, language: Optional[str] = None) -> str:
    names = _BY_ZONE.get(zone)
    if names is None:
        return zone.split('/')[-1].replace('_', ' ')
    return names[1] if (language or ui_language()) == 'fr' else names[0]


def zone_info(zone: str):
    """The tzinfo for a zone name, or None if the system doesn't know it."""
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(zone)
    except Exception:                      # unknown name, missing tz database
        return None


def time_in(zone: str, now: float) -> Optional[dt.datetime]:
    info = zone_info(zone)
    return dt.datetime.fromtimestamp(now, info) if info else None


def hours_from_home(zone: str, now: float) -> Optional[float]:
    """How many hours the zone is ahead of Montréal right now (negative: behind)."""
    there, home = time_in(zone, now), time_in(HOME_ZONE, now)
    if there is None or home is None:
        return None
    return (there.utcoffset() - home.utcoffset()).total_seconds() / 3600


def day_offset(zone: str, now: float) -> Optional[int]:
    """-1, 0 or 1: is it yesterday, the same day or tomorrow there, compared with Montréal?"""
    there, home = time_in(zone, now), time_in(HOME_ZONE, now)
    if there is None or home is None:
        return None
    return (there.date() - home.date()).days


def search(query: str, language: Optional[str] = None) -> Tuple[Tuple[str, str], ...]:
    """(zone, name) pairs whose name or zone contains the query, accents and case ignored."""
    import unicodedata

    def plain(text: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                       if unicodedata.category(c) != 'Mn')

    q = plain(query.strip())
    out = []
    for zone, en, fr in CITIES:
        if not q or q in plain(en) or q in plain(fr) or q in plain(zone):
            out.append((zone, city_name(zone, language)))
    return tuple(out)
