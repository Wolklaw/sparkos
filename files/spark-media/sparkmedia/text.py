"""Every word Spark Media shows, in English and in French (Quebec, with "vous").

The language comes from the computer's locale (LC_ALL, then LC_MESSAGES, then LANG): French
when it starts with "fr", English otherwise. SPARK_LANG=en or SPARK_LANG=fr overrides it."""

import os
from typing import Dict

EN: Dict[str, str] = {}
FR: Dict[str, str] = {}


def language() -> str:
    forced = os.environ.get('SPARK_LANG', '').strip().lower()[:2]
    if forced in ('en', 'fr'):
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


LANG = language()


def tr(key: str, **kw) -> str:
    """The text for key in the current language; English when French lacks it."""
    table = FR if LANG == 'fr' else EN
    text = table.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text


def set_language(lang: str) -> None:
    """For tests: switch language at run time."""
    global LANG
    LANG = lang if lang in ('en', 'fr') else 'en'


def plural(n: int, one: str, many: str) -> str:
    """'1 song' / '2 songs': keys for the singular and the plural, with {n}. French uses the
    singular for 0 too."""
    single = n == 1 or (LANG == 'fr' and n == 0)
    return tr(one if single else many, n=n)


from .strings import EN as _EN, FR as _FR   # noqa: E402  (tables live in their own file)
EN.update(_EN)
FR.update(_FR)
