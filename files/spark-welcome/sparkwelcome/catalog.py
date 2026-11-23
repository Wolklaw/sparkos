"""The list of launchers and apps Spark Welcome offers, read from apps.json next to this file.
No window code here, so the Spark Portal can reuse it."""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps.json')
ANTICHEAT_URL = 'https://areweanticheatyet.com'

# Flathub ids are reverse-DNS: at least three dot-separated parts.
FLATPAK_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+){2,}$')
# A web app (a service with no Linux app, such as Amazon Music): "web.<name>" and its https address.
# Installing one adds a menu entry that opens the address in the browser.
WEB_ID = re.compile(r'^web\.[a-z0-9][a-z0-9-]*$')


# A Windows app that Spark Run installs ("run.<name>"): `spark-run --get <name>` downloads the
# vendor's installer and adds the app to the menu. <name> is Spark Run's own app key.
RUN_ID = re.compile(r'^run\.[a-z0-9][a-z0-9-]*$')


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    id: str          # Flathub app id
    name: str
    by: str          # whose app it is
    blurb: str
    name_fr: str = ''
    blurb_fr: str = ''
    by_fr: str = ''
    web: str = ''    # a web app: the address its menu entry opens (empty for a Flathub app)
    run: str = ''    # a Windows app: its key in Spark Run's catalogue (spark-run --get KEY)

    def label(self, lang: str = 'en') -> str:
        return (self.name_fr if lang == 'fr' and self.name_fr else self.name)

    def text(self, lang: str = 'en') -> str:
        return (self.blurb_fr if lang == 'fr' and self.blurb_fr else self.blurb)

    def who(self, lang: str = 'en') -> str:
        return (self.by_fr if lang == 'fr' and self.by_fr else self.by)


@dataclass
class Category:
    name: str
    apps: List[Entry]
    name_fr: str = ''

    def label(self, lang: str = 'en') -> str:
        return self.name_fr if lang == 'fr' and self.name_fr else self.name


@dataclass
class Catalog:
    launchers: List[Entry]
    categories: List[Category] = field(default_factory=list)

    def all(self) -> List[Entry]:
        return self.launchers + [app for cat in self.categories for app in cat.apps]

    def find(self, app_id: str) -> Optional[Entry]:
        return next((e for e in self.all() if e.id == app_id), None)


def _entry(raw: Any, where: str) -> Entry:
    if not isinstance(raw, dict):
        raise CatalogError(f"{where}: not an object")
    for key in ('id', 'name', 'by', 'blurb'):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise CatalogError(f"{where}: missing '{key}'")
    web = str(raw.get('web') or '')
    run = str(raw.get('run') or '')
    if run:
        if raw['id'] != f'run.{run}' or not RUN_ID.match(raw['id']) or web:
            raise CatalogError(f"{where}: a Spark Run app needs an id like run.name and a "
                               f"matching 'run' key")
    elif web:
        if not WEB_ID.match(raw['id']) or not re.match(r'^https://[^\s"\'\\]+$', web):
            raise CatalogError(f"{where}: a web app needs an id like web.name and an https address")
    elif not FLATPAK_ID.match(raw['id']):
        raise CatalogError(f"{where}: '{raw['id']}' isn't a Flathub app id")
    return Entry(raw['id'], raw['name'], raw['by'], raw['blurb'],
                 str(raw.get('name_fr', '')), str(raw.get('blurb_fr', '')),
                 str(raw.get('by_fr', '')), web, run)


def parse(data: Dict[str, Any]) -> Catalog:
    if not isinstance(data, dict):
        raise CatalogError("the catalog is not an object")
    launchers = [_entry(r, f"launchers[{i}]") for i, r in enumerate(data.get('launchers') or [])]
    categories = []
    for i, cat in enumerate(data.get('categories') or []):
        if not isinstance(cat, dict) or not isinstance(cat.get('name'), str):
            raise CatalogError(f"categories[{i}]: needs a name")
        apps = [_entry(r, f"{cat['name']}[{j}]") for j, r in enumerate(cat.get('apps') or [])]
        categories.append(Category(cat['name'], apps, str(cat.get('name_fr', ''))))
    catalog = Catalog(launchers, categories)
    seen = set()
    for entry in catalog.all():
        if entry.id in seen:
            raise CatalogError(f"{entry.id} is listed twice")
        seen.add(entry.id)
    if not catalog.launchers:
        raise CatalogError("no launchers")
    return catalog


def load(path: str = CATALOG_FILE) -> Catalog:
    try:
        with open(path, encoding='utf-8') as f:
            return parse(json.load(f))
    except (OSError, ValueError) as exc:
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError(f"can't read {os.path.basename(path)}: {exc}") from exc
