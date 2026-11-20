"""The catalog index: the Flathub catalog read once into a small SQLite file in
~/.cache/spark-store, and read again only when flatpak replaces the catalog. Loading the index
takes a few tens of milliseconds, so the window opens at once with thousands of apps.

Search runs over the apps in memory as you type."""

import json
import os
import sqlite3
import time
from contextlib import closing
from typing import Dict, List, Optional, Sequence, Tuple

from . import INDEX_VERSION
from .appstream import Addon, App, Details, Source, find_sources, fold, fold_fields, parse
from .core import cache_dir, languages, log

# Curated rows on the home page: well-known apps first, in this order, then more from the
# row's Flathub categories (verified apps first) until the row is full.
ROWS: List[Tuple[str, List[str], List[str]]] = [
    ('games', ['com.valvesoftware.Steam', 'com.heroicgameslauncher.hgl', 'net.lutris.Lutris',
               'org.prismlauncher.PrismLauncher', 'net.davidotek.pupgui2',
               'org.libretro.RetroArch', 'com.usebottles.bottles', 'net.veloren.airshipper'],
     ['Game']),
    ('chat', ['com.discordapp.Discord', 'org.signal.Signal', 'org.telegram.desktop',
              'im.riot.Riot', 'us.zoom.Zoom', 'com.slack.Slack', 'dev.vencord.Vesktop'],
     ['InstantMessaging', 'Chat', 'VideoConference']),
    ('music', ['com.spotify.Client', 'org.audacityteam.Audacity', 'io.lmms.LMMS',
               'org.strawberrymusicplayer.strawberry', 'io.bassi.Amberol',
               'org.musescore.MuseScore'],
     ['Music', 'Audio']),
    ('creative', ['org.gimp.GIMP', 'org.kde.krita', 'org.inkscape.Inkscape',
                  'org.blender.Blender', 'org.kde.kdenlive', 'com.obsproject.Studio',
                  'org.darktable.Darktable'],
     ['Graphics', 'VideoEditing', '2DGraphics', '3DGraphics']),
    ('office', ['org.libreoffice.LibreOffice', 'org.onlyoffice.desktopeditors',
                'org.mozilla.Thunderbird', 'org.kde.okular', 'net.cozic.joplin_desktop',
                'md.obsidian.Obsidian', 'com.bitwarden.desktop'],
     ['Office', 'WordProcessor', 'Spreadsheet']),
]
ROW_SIZE = 6

# Browse by category: freedesktop's main categories, the way app menus group apps
CATEGORIES: List[Tuple[str, List[str]]] = [
    ('games', ['Game']),
    ('audio_video', ['AudioVideo', 'Audio', 'Video']),
    ('graphics', ['Graphics']),
    ('internet', ['Network']),
    ('office', ['Office']),
    ('development', ['Development']),
    ('education', ['Education', 'Science']),
    ('utilities', ['Utility']),
    ('system', ['System', 'Settings']),
]


def cache_path() -> str:
    return os.path.join(cache_dir(), 'catalog.sqlite')


def _key(sources: Sequence[Source], langs: List[str]) -> str:
    return json.dumps({'v': INDEX_VERSION, 'langs': langs,
                       'src': [[s.path, int(s.mtime), s.size] for s in sources]})


class Catalog:
    """The apps from the newest catalog on this PC. load() is safe to call from a thread."""

    def __init__(self, sources: Optional[List[Source]] = None, path: Optional[str] = None,
                 langs: Optional[List[str]] = None):
        self.sources = find_sources() if sources is None else sources
        self.source: Optional[Source] = self.sources[0] if self.sources else None
        self.path = path or cache_path()
        self.langs = languages() if langs is None else langs
        self.apps: Dict[str, App] = {}
        self.order: List[App] = []
        self.addons: Dict[str, List[Addon]] = {}      # by the ID of the app they extend
        self.loaded = False
        self.rebuilt = False             # True when this load had to read the XML
        self.load_seconds = 0.0
        self.error = ''

    @property
    def icon_dir(self) -> str:
        return self.source.icons if self.source else ''

    def icon_path(self, app: App, size: int = 64) -> Optional[str]:
        if not app.icon or not self.source:
            return None
        for sz in ((128, 64) if size > 64 else (64, 128)):
            path = os.path.join(self.source.icons, f'{sz}x{sz}', app.icon)
            if os.path.isfile(path):
                return path
        return None

    # — loading —
    def load(self) -> 'Catalog':
        started = time.monotonic()
        self.error = ''
        if self.source is None:
            self.loaded = True
            return self
        key = _key([self.source], self.langs)
        cached = self._read_cache(key)
        if cached is None:
            try:
                cached = self._rebuild(key)
                self.rebuilt = True
            except (OSError, EOFError, ValueError, SyntaxError) as exc:   # broken catalog file
                log.warning("could not read the catalog %s: %s", self.source.path, exc)
                self.error = str(exc)
                cached = ([], [])
        rows, addon_rows = cached
        for row in addon_rows:
            addon = Addon.from_row(row)
            for target in addon.extends:
                self.addons.setdefault(target, []).append(addon)
        for found in self.addons.values():
            found.sort(key=lambda a: fold(a.name))
        apps = [App.from_row(r) for r in rows]
        for app in apps:
            fold_fields(app)
        self.order = sorted(apps, key=lambda a: fold(a.name))
        self.apps = {a.id: a for a in apps}
        self.loaded = True
        self.load_seconds = time.monotonic() - started
        log.info("catalog: %d apps from %s in %.2f s%s", len(apps), self.source.path,
                 self.load_seconds, " (rebuilt)" if self.rebuilt else "")
        return self

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def _read_cache(self, key: str) -> Optional[Tuple[list, list]]:
        if not os.path.isfile(self.path):
            return None
        try:
            with closing(self._connect()) as db:
                row = db.execute("SELECT value FROM meta WHERE key='key'").fetchone()
                if not row or row[0] != key:
                    return None
                blob = db.execute("SELECT value FROM meta WHERE key='list'").fetchone()
                extra = db.execute("SELECT value FROM meta WHERE key='addons'").fetchone()
            if not blob or not extra:
                return None
            return json.loads(blob[0]), json.loads(extra[0])
        except (sqlite3.Error, ValueError) as exc:
            log.warning("catalog cache unreadable, rebuilding: %s", exc)
            return None

    def _rebuild(self, key: str) -> Tuple[list, list]:
        """Read the catalog XML into a new index file, then swap it in."""
        tmp = self.path + '.new'
        try:
            os.unlink(tmp)
        except OSError:
            pass
        rows, details = [], []
        addons: List[Addon] = []
        seen = set()
        for app, det in parse(self.source.path, self.langs, addons):
            if app.id in seen:
                continue
            seen.add(app.id)
            rows.append(app.to_row())
            details.append((app.id, json.dumps(det.to_json(), separators=(',', ':'))))
        db = sqlite3.connect(tmp)
        try:
            db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            db.execute("CREATE TABLE details (id TEXT PRIMARY KEY, value TEXT)")
            db.executemany("INSERT INTO details VALUES (?, ?)", details)
            db.execute("INSERT INTO meta VALUES ('list', ?)",
                       (json.dumps(rows, separators=(',', ':')),))
            addon_rows = [a.to_row() for a in addons]
            db.execute("INSERT INTO meta VALUES ('addons', ?)",
                       (json.dumps(addon_rows, separators=(',', ':')),))
            db.execute("INSERT INTO meta VALUES ('key', ?)", (key,))
            db.commit()
        finally:
            db.close()
        os.replace(tmp, self.path)
        return rows, addon_rows

    def details(self, app_id: str) -> Details:
        try:
            with closing(self._connect()) as db:
                row = db.execute("SELECT value FROM details WHERE id=?", (app_id,)).fetchone()
            if row:
                return Details.from_json(json.loads(row[0]))
        except (sqlite3.Error, ValueError) as exc:
            log.warning("details for %s: %s", app_id, exc)
        return Details()

    # — finding apps —
    def search(self, query: str, limit: int = 60,
               extra: Sequence[App] = ()) -> Tuple[List[App], int]:
        """(best matches, how many matched in all). Every word must match somewhere."""
        tokens = [t for t in fold(query).replace(',', ' ').split() if t]
        if not tokens:
            return [], 0
        phrase = ' '.join(tokens)
        scored = []
        for app in list(extra) + self.order:
            if not app.hay:
                fold_fields(app)
            total = score(app, tokens, phrase)
            if total > 0:
                scored.append((-total, len(app.name), app.hay[0], app))
        scored.sort(key=lambda s: s[:3])
        seen, out = set(), []
        for item in scored:
            app = item[3]
            if app.id not in seen:
                seen.add(app.id)
                out.append(app)
        return out[:limit], len(out)

    def category(self, key: str) -> List[App]:
        """Every app in one of the CATEGORIES, verified ones first, then by name."""
        wanted = dict(CATEGORIES).get(key, [])
        found = [a for a in self.order if any(c in wanted for c in a.categories)]
        found.sort(key=lambda a: (not a.verified, a.hay[0] if a.hay else fold(a.name)))
        return found

    def row(self, key: str, exclude: Sequence[str] = ()) -> List[App]:
        for name, ids, cats in ROWS:
            if name != key:
                continue
            out = [self.apps[i] for i in ids if i in self.apps and i not in exclude]
            if len(out) < ROW_SIZE:
                taken = {a.id for a in out} | set(exclude)
                more = [a for a in self.order if a.id not in taken and
                        any(c in cats for c in a.categories)]
                more.sort(key=lambda a: (not a.verified, a.proprietary, a.hay[0]))
                out.extend(more[:ROW_SIZE - len(out)])
            return out[:ROW_SIZE]
        return []


def score(app: App, tokens: List[str], phrase: str) -> int:
    """How well an app matches the words typed; 0 means it doesn't."""
    name, short_id, keywords, summary, developer, categories, full_id = app.hay
    total = 0
    if name == phrase:
        total += 200
    elif name.startswith(phrase):
        total += 80
    if full_id == phrase:
        total += 200
    name_words = name.replace('-', ' ').split()
    kw_list = keywords.split('\n') if keywords else []
    for tok in tokens:
        best = 0
        if name == tok:
            best = 100
        elif name.startswith(tok):
            best = 70
        elif any(w.startswith(tok) for w in name_words):
            best = 50
        elif tok in name:
            best = 30
        if tok in kw_list:
            best = max(best, 25)
        elif any(k.startswith(tok) or f' {tok}' in k for k in kw_list):
            best = max(best, 18)
        if tok in short_id:
            best = max(best, 15)
        if best < 10:
            if any(w.startswith(tok) for w in summary.split()):
                best = max(best, 10)
            elif tok in summary:
                best = max(best, 6)
            elif tok in developer:
                best = max(best, 5)
            elif len(tok) > 3 and tok in categories:
                best = max(best, 4)
            elif tok in full_id:
                best = max(best, 3)
        if best == 0:
            return 0
        total += best
    if app.kind == 'spark':
        total += 20
    if app.verified:
        total += 3
    return total
