"""Which language the Spark apps speak. Every Spark app has this same file; keep the copies
identical.

SPARK_LANG=en or SPARK_LANG=fr wins (the tests use it). Otherwise the first of LC_ALL,
LC_MESSAGES and LANG that is set decides: French if it starts with "fr", English otherwise."""

import os
import re

LANGUAGES = ('en', 'fr')


def ui_language(environ=None) -> str:
    env = os.environ if environ is None else environ
    forced = (env.get('SPARK_LANG') or '').strip().lower()
    if forced in LANGUAGES:
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = env.get(var) or ''
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


# French writes a decimal comma, octets and a space before %: 1,5 Go, 12 Mo/s, 3,2 %
_FR_UNITS = {'B': 'o', 'KB': 'Ko', 'MB': 'Mo', 'GB': 'Go', 'TB': 'To', 'KiB': 'Kio',
             'MiB': 'Mio', 'GiB': 'Gio', 'TiB': 'Tio', 'bps': 'bit/s', 'Kbps': 'Kbit/s',
             'Mbps': 'Mbit/s', 'Gbps': 'Gbit/s'}
_AMOUNT = re.compile(r'(\d+(?:\.\d+)?)( ?)(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB|bps|Kbps|Mbps|Gbps|'
                     r'GHz|MHz|°C|W|V|RPM|%)(?![A-Za-z])')


def local_units(text: str, language=None) -> str:
    """A number with its unit, as the PC's language writes it: '1.5 GB' stays in English and
    becomes '1,5 Go' in French ('12 MB/s' -> '12 Mo/s', '3.2%' -> '3,2 %')."""
    if (language or ui_language()) != 'fr':
        return text

    def french(m):
        unit = _FR_UNITS.get(m.group(3), m.group(3))
        space = ' ' if m.group(2) or m.group(3) == '%' else ''
        return m.group(1).replace('.', ',') + space + unit
    return _AMOUNT.sub(french, text)
