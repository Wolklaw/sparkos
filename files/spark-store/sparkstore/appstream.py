"""The Flathub catalog that flatpak keeps on this PC, and what one app's entry says.

flatpak downloads the catalog with `flatpak update --appstream` (SparkOS does it at first boot)
into <installation>/appstream/flathub/<arch>/active/: appstream.xml.gz, plus the apps' icons
in icons/64x64 and icons/128x128. Nothing here goes to the network."""

import gzip
import os
import platform
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

from . import REMOTE
from .core import data_home

XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
KINDS = ('desktop-application', 'desktop')


@dataclass
class Source:
    """One catalog file: the user's installation's or the system's."""
    path: str
    scope: str                       # 'user' or 'system' (or 'file' for --appstream)
    mtime: float = 0.0
    size: int = 0

    @property
    def icons(self) -> str:
        return os.path.join(os.path.dirname(self.path), 'icons')

    def stat(self) -> bool:
        try:
            st = os.stat(self.path)
        except OSError:
            return False
        self.mtime, self.size = st.st_mtime, st.st_size
        return True


def flatpak_arch() -> str:
    machine = platform.machine().lower()
    return {'amd64': 'x86_64', 'x64': 'x86_64', 'arm64': 'aarch64'}.get(machine, machine)


def installation_dirs() -> List[Tuple[str, str]]:
    """(scope, folder) for the user's and the system's Flatpak installations."""
    user = os.environ.get('FLATPAK_USER_DIR') or os.path.join(data_home(), 'flatpak')
    system = os.environ.get('FLATPAK_SYSTEM_DIR') or '/var/lib/flatpak'
    return [('user', user), ('system', system)]


def find_sources(remote: str = REMOTE) -> List[Source]:
    """Every catalog file on this PC, newest first. SPARK_STORE_APPSTREAM names one file
    instead (tests, and trying a catalog by hand)."""
    forced = os.environ.get('SPARK_STORE_APPSTREAM')
    if forced:
        src = Source(forced, 'file')
        return [src] if src.stat() else []
    found = []
    arch = flatpak_arch()
    for scope, base in installation_dirs():
        folder = os.path.join(base, 'appstream', remote, arch, 'active')
        for name in ('appstream.xml.gz', 'appstream.xml'):
            src = Source(os.path.join(folder, name), scope)
            if src.stat():
                found.append(src)
                break
    found.sort(key=lambda s: s.mtime, reverse=True)
    return found


# ─── One app ──────────────────────────────────────────────────

@dataclass
class App:
    """What the lists need about an app. The long parts (description, screenshots) are in
    Details, read from the cache only when its page opens."""
    id: str
    name: str
    summary: str = ''
    developer: str = ''
    verified: bool = False
    license: str = ''
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    icon: str = ''                   # file name in the catalog's icons/<size>/ folders
    branch: str = 'stable'
    kind: str = 'flathub'            # 'flathub', or 'spark' for the Spark apps
    hay: Tuple[str, ...] = ()        # folded search fields, filled by fold_fields()

    @property
    def proprietary(self) -> bool:
        return is_proprietary(self.license)

    def to_row(self) -> list:
        return [self.id, self.name, self.summary, self.developer, int(self.verified),
                self.license, self.categories, self.keywords, self.icon, self.branch]

    @classmethod
    def from_row(cls, row: list) -> 'App':
        return cls(id=row[0], name=row[1], summary=row[2], developer=row[3],
                   verified=bool(row[4]), license=row[5], categories=list(row[6]),
                   keywords=list(row[7]), icon=row[8], branch=row[9])


@dataclass
class Shot:
    caption: str
    url: str                         # a thumbnail about 752 px wide
    width: int = 0
    height: int = 0
    full: str = ''                   # the original


@dataclass
class Details:
    description: List[Tuple[str, str]] = field(default_factory=list)   # ('p'|'li', text)
    screenshots: List[Shot] = field(default_factory=list)
    urls: Dict[str, str] = field(default_factory=dict)
    version: str = ''
    released: int = 0                # unix time of the newest release
    runtime: str = ''

    def to_json(self) -> dict:
        return {'d': self.description, 's': [[s.caption, s.url, s.width, s.height, s.full]
                                              for s in self.screenshots],
                'u': self.urls, 'v': self.version, 'r': self.released, 'rt': self.runtime}

    @classmethod
    def from_json(cls, data: dict) -> 'Details':
        return cls(description=[(k, v) for k, v in data.get('d', [])],
                   screenshots=[Shot(*s) for s in data.get('s', [])],
                   urls=dict(data.get('u', {})), version=data.get('v', ''),
                   released=int(data.get('r', 0) or 0), runtime=data.get('rt', ''))


def is_proprietary(license_text: str) -> bool:
    return 'proprietary' in (license_text or '').lower()


def licence_label(license_text: str) -> str:
    """'LicenseRef-proprietary=https://...' -> 'Proprietary'; SPDX names as they are."""
    text = (license_text or '').strip()
    if not text:
        return ''
    if is_proprietary(text):
        return 'Proprietary'
    return re.sub(r'LicenseRef-([\w.-]+)(=\S+)?', r'\1', text)


def fold(text: str) -> str:
    """Lower case without accents, so 'edition' finds 'Édition'."""
    text = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def fold_fields(app: App) -> None:
    app.hay = (fold(app.name), fold(app.id.rsplit('.', 1)[-1]),
               '\n'.join(fold(k) for k in app.keywords), fold(app.summary),
               fold(app.developer), ' '.join(c.lower() for c in app.categories), fold(app.id))


# ─── Reading the XML ──────────────────────────────────────────

def _clean(text: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _pick(parent: ET.Element, tag: str, langs: List[str]) -> Optional[ET.Element]:
    """The child in the first of the user's languages, else the untranslated one."""
    plain, by_lang = None, {}
    for child in parent.findall(tag):
        lang = child.get(XML_LANG)
        if lang is None:
            if plain is None:
                plain = child
        else:
            by_lang.setdefault(lang, child)
    for lang in langs:
        if lang in by_lang:
            return by_lang[lang]
        if lang.replace('_', '-') in by_lang:
            return by_lang[lang.replace('_', '-')]
    return plain


def _text(parent: ET.Element, tag: str, langs: List[str]) -> str:
    el = _pick(parent, tag, langs)
    return _clean(''.join(el.itertext())) if el is not None else ''


def description(el: Optional[ET.Element]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if el is None:
        return out
    for child in el:
        if child.tag == 'p':
            text = _clean(''.join(child.itertext()))
            if text:
                out.append(('p', text))
        elif child.tag in ('ul', 'ol'):
            for li in child.findall('li'):
                text = _clean(''.join(li.itertext()))
                if text:
                    out.append(('li', text))
    return out


def _custom(component: ET.Element) -> Dict[str, str]:
    values = {}
    for holder in ('custom', 'metadata'):
        for block in component.findall(holder):
            for value in block.findall('value'):
                key = value.get('key')
                if key:
                    values[key] = (value.text or '').strip()
    return values


def _cached_icon(component: ET.Element) -> str:
    best, best_w = '', 0
    for icon in component.findall('icon'):
        if icon.get('type') != 'cached' or icon.get('scale') not in (None, '1'):
            continue
        try:
            width = int(icon.get('width') or 0)
        except ValueError:
            width = 0
        if (icon.text or '').strip() and (not best or (width == 64) or
                                          (best_w != 64 and width > best_w)):
            best, best_w = icon.text.strip(), width
    return best


def _screenshots(component: ET.Element, langs: List[str]) -> List[Shot]:
    shots = []
    block = component.find('screenshots')
    if block is None:
        return shots
    ordered = sorted(block.findall('screenshot'), key=lambda s: s.get('type') != 'default')
    for shot in ordered:
        caption = _text(shot, 'caption', langs)
        thumbs, source = [], ''
        for image in shot.findall('image'):
            url = (image.text or '').strip()
            if not url.startswith('https://'):
                continue
            try:
                w, h = int(image.get('width') or 0), int(image.get('height') or 0)
            except ValueError:
                w = h = 0
            if image.get('type') == 'source':
                source = url
                thumbs.append((w, h, url, True))
            else:
                thumbs.append((w, h, url, False))
        if not thumbs:
            continue
        # a thumbnail near 752 px wide: sharp on the page, small to download
        pick = min(thumbs, key=lambda t: (abs((t[0] or 2000) - 752) + (400 if t[3] else 0)))
        shots.append(Shot(caption, pick[2], pick[0], pick[1], source or pick[2]))
        if len(shots) >= 8:
            break
    return shots


def parse_component(c: ET.Element, langs: List[str]) -> Optional[Tuple[App, Details]]:
    if c.get('type') not in KINDS:
        return None
    app_id = (c.findtext('id') or '').strip()
    if app_id.endswith('.desktop'):
        app_id = app_id[:-8]
    bundle = c.find('bundle')
    ref = (bundle.text or '').strip() if bundle is not None else ''
    if bundle is not None and bundle.get('type') not in (None, 'flatpak'):
        return None
    if not app_id or (ref and not ref.startswith('app/')):
        return None
    name = _text(c, 'name', langs)
    if not name:
        return None
    custom = _custom(c)
    developer = ''
    dev = c.find('developer')
    if dev is not None:
        developer = _text(dev, 'name', langs)
    if not developer:
        developer = _text(c, 'developer_name', langs)
    keywords: List[str] = []
    for block in c.findall('keywords'):
        lang = block.get(XML_LANG)
        if lang is None or lang in langs:
            keywords.extend(_clean(k.text) for k in block.findall('keyword') if k.text)
    parts = ref.split('/')
    branch = parts[3] if len(parts) == 4 and parts[3] else 'stable'
    app = App(id=app_id, name=name, summary=_text(c, 'summary', langs), developer=developer,
              verified=custom.get('flathub::verification::verified', '').lower() == 'true',
              license=_clean(c.findtext('project_license')),
              categories=[_clean(x.text) for x in c.findall('categories/category') if x.text],
              keywords=list(dict.fromkeys(k for k in keywords if k)),
              icon=_cached_icon(c), branch=branch)
    details = Details(description=description(_pick(c, 'description', langs)),
                      screenshots=_screenshots(c, langs),
                      runtime=bundle.get('runtime', '') if bundle is not None else '')
    for url in c.findall('url'):
        kind, value = url.get('type') or 'homepage', (url.text or '').strip()
        if value.startswith(('https://', 'http://')) and kind not in details.urls:
            details.urls[kind] = value
    releases = c.find('releases')
    if releases is not None:
        newest = None
        for rel in releases.findall('release'):
            try:
                stamp = int(rel.get('timestamp') or 0)
            except ValueError:
                stamp = 0
            if newest is None or stamp > newest[0]:
                newest = (stamp, rel.get('version') or '')
        if newest:
            details.released, details.version = newest
    return app, details


def parse(path: str, langs: List[str]) -> Iterator[Tuple[App, Details]]:
    """Every desktop app in a catalog file (.xml or .xml.gz), one at a time."""
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rb') as f:
        root = None
        for event, el in ET.iterparse(f, events=('start', 'end')):
            if event == 'start':
                if root is None:
                    root = el
                continue
            if el.tag != 'component':
                continue
            result = parse_component(el, langs)
            if root is not None:
                root.clear()
            if result:
                yield result
