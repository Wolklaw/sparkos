"""Which language the Spark apps speak. Every Spark app has this same file; keep the copies
identical.

SPARK_LANG=en or SPARK_LANG=fr wins (the tests use it). Otherwise the first of LC_ALL,
LC_MESSAGES and LANG that is set decides: French if it starts with "fr", English otherwise."""

import os

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
