"""Everything that doesn't need a window: the emoji and symbol data, search, recently used,
settings, folders and the log."""

import json
import logging
import os
import sys
import unicodedata
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from . import APP_NAME, APP_SLUG, VERSION
from .lang import ui_language

log = logging.getLogger(APP_SLUG)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

CHROME = {
    'bg': '#0a0919', 'bg2': '#100f26', 'surface': '#141233', 'surface2': '#1b1948',
    'line': 'rgba(236,233,255,.14)', 'line_strong': 'rgba(236,233,255,.3)',
    'text': '#f1efff', 'muted': '#b3b0d2', 'accent': '#9be8b8', 'on_accent': '#0a0919',
    'pink': '#ff9ebb', 'ch_a': '#ff2e88', 'ch_b': '#22d8ff',
}

# ─── Folders and the log ────────────────────────────────────


def _xdg_dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config', create)


def state_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'), create)


def setup_logging() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=128 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


# ─── Data ───────────────────────────────────────────────────

TONES = ('\U0001F3FB', '\U0001F3FC', '\U0001F3FD', '\U0001F3FE', '\U0001F3FF')


class Entry(NamedTuple):
    char: str
    name_en: str
    name_fr: str
    words_en: str
    words_fr: str
    tones: Tuple[str, ...]      # five skin tone forms, or ()
    group: str                  # group id
    kind: str                   # 'emoji' or 'symbol'

    def name(self, language: Optional[str] = None) -> str:
        return self.name_fr if (language or ui_language()) == 'fr' else self.name_en

    def with_tone(self, tone: int) -> str:
        """The character in skin tone 0-4 (light to dark); as is for -1 or when it has none."""
        return self.tones[tone] if self.tones and 0 <= tone < 5 else self.char


class Group(NamedTuple):
    id: str
    en: str
    fr: str
    kind: str
    entries: Tuple[Entry, ...]

    def title(self, language: Optional[str] = None) -> str:
        return self.fr if (language or ui_language()) == 'fr' else self.en


def load_groups(data_dir: str = DATA_DIR) -> List[Group]:
    groups = []
    for filename, kind in (('emoji.json', 'emoji'), ('symbols.json', 'symbol')):
        with open(os.path.join(data_dir, filename), encoding='utf-8') as f:
            data = json.load(f)
        for g in data['groups']:
            entries = tuple(
                Entry(row[0], row[1], row[2], row[3], row[4],
                      tuple(row[5]) if len(row) > 5 else (), g['id'], kind)
                for row in g['items'])
            groups.append(Group(g['id'], g['en'], g['fr'], kind, entries))
    return groups


_cache: Dict[str, Any] = {}


def groups() -> List[Group]:
    if 'all' not in _cache:
        _cache['all'] = load_groups()
    return _cache['all']


def all_entries() -> List[Entry]:
    return [e for g in groups() for e in g.entries]


def find_entry(char: str) -> Optional[Entry]:
    """The entry for a character, also when it is one of an entry's skin tone forms."""
    if 'by_char' not in _cache:
        table = {}
        for e in all_entries():
            table.setdefault(e.char, e)
            for form in e.tones:
                table.setdefault(form, e)
        _cache['by_char'] = table
        _cache['by_bare'] = {c.replace('️', ''): e for c, e in reversed(list(table.items()))}
    return _cache['by_char'].get(char) or _cache['by_bare'].get(char.replace('️', ''))


# ─── Search ─────────────────────────────────────────────────


def fold(text: str) -> str:
    """Lower case without accents, so 'cœur', 'coeur' and 'COEUR' meet, and so do 'é' and 'e'."""
    text = text.casefold().replace('œ', 'oe').replace('æ', 'ae').replace('ß', 'ss')
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if not unicodedata.combining(c))


def _search_index():
    if 'index' not in _cache:
        _cache['index'] = [(e, fold(e.name_en), fold(e.name_fr),
                            fold(e.words_en + ' ' + e.words_fr))
                           for e in all_entries()]
    return _cache['index']


def _tokens(text: str) -> List[str]:
    for sep in '-:,()’\'':
        text = text.replace(sep, ' ')
    return text.split()


def search(query: str, limit: int = 150) -> List[Entry]:
    """Entries matching every word of the query, best first: whole-word matches in a name,
    then name prefixes, then other name matches, then keywords. English and French are
    searched together, and accents and case don't matter. 'U+1F600' finds that character,
    and a typed character finds itself."""
    q = query.strip()
    if not q:
        return []
    hit = _by_codepoint(q) or (find_entry(q) if len(q) <= 8 and not q.isascii() else None)
    if hit:
        return [hit]
    whole = fold(q)
    words = whole.split()
    scored = []
    for order, (e, n_en, n_fr, kw) in enumerate(_search_index()):
        total = 0.0
        for w in words:
            best = 0.0
            for name in (n_en, n_fr):
                tokens = _tokens(name)
                if w in tokens:
                    best = max(best, 4)
                elif any(t.startswith(w) for t in tokens):
                    best = max(best, 3)
                elif w in name:
                    best = max(best, 2)
            if not best:
                ktokens = kw.split()
                if w in ktokens:
                    best = 1.5
                elif any(t.startswith(w) for t in ktokens):
                    best = 1
            if not best:
                total = 0
                break
            total += best
        if total:
            if whole in (n_en, n_fr):
                total += 6                 # the name is exactly what was typed
            scored.append((-total, min(len(n_en), len(n_fr)), order, e))
    scored.sort(key=lambda x: x[:3])       # best score, then the shorter name, then data order
    return [x[3] for x in scored[:limit]]


def _by_codepoint(q: str) -> Optional[Entry]:
    text = q.lower()
    if text.startswith('u+') or text.startswith('0x'):
        try:
            cp = int(text[2:], 16)
        except ValueError:
            return None
        if 0x20 <= cp <= 0x10FFFF:
            return find_entry(chr(cp))
    return None


# ─── Recently used ──────────────────────────────────────────

RECENT_MAX = 32


def recents_path() -> str:
    return os.path.join(state_dir(), 'recent.json')


def load_recents(path: Optional[str] = None) -> List[str]:
    try:
        with open(path or recents_path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [c for c in data if isinstance(c, str) and 0 < len(c) <= 24][:RECENT_MAX]


def add_recent(char: str, path: Optional[str] = None) -> List[str]:
    items = [char] + [c for c in load_recents(path) if c != char]
    items = items[:RECENT_MAX]
    try:
        with open(path or recents_path(), 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
    except OSError as exc:
        log.warning("couldn't save recents: %s", exc)
    return items


# ─── Settings ───────────────────────────────────────────────

SETTINGS_FILE = 'settings.json'
DEFAULTS: Dict[str, Any] = {
    "tone": -1,            # -1 default yellow, 0..4 light to dark
    "paste": False,        # paste into the window that was in front (needs the desktop's OK)
    "portal_token": "",    # lets the desktop remember that OK
    "glitch": True,
}


def clean_settings(data: Any) -> Dict[str, Any]:
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out
    tone = data.get('tone')
    if isinstance(tone, int) and not isinstance(tone, bool) and -1 <= tone <= 4:
        out['tone'] = tone
    for key in ('paste', 'glitch'):
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    token = data.get('portal_token')
    if isinstance(token, str) and len(token) < 200:
        out['portal_token'] = token
    return out


def settings_path() -> str:
    return os.path.join(config_dir(), SETTINGS_FILE)


def load_settings(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or settings_path(), encoding='utf-8') as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: Dict[str, Any], path: Optional[str] = None) -> bool:
    target = path or settings_path()
    try:
        tmp = target + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(clean_settings(settings), f, indent=2)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
        return True
    except OSError as exc:
        log.warning("couldn't save settings: %s", exc)
        return False
