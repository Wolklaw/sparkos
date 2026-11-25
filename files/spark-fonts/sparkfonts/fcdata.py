"""What fontconfig knows about the fonts: the list, grouped by family, and the filters.

fc-list and fc-query print one line per face with a format we choose; parse() turns those lines
into Face objects and group() into Family objects. No window code here."""

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import core
from .core import log, run

FORMAT = ('%{file}\t%{index}\t%{family[0]}\t%{style[0]}\t%{fullname[0]}\t%{weight}\t%{slant}\t'
          '%{spacing}\t%{width}\t%{fontformat}\t%{variable}\t%{fontversion}\t'
          '%{postscriptname}\t%{lang}\n')
FIELDS = 14

CATEGORIES = ('sans', 'serif', 'mono', 'display', 'script')
# the languages the filter offers (fontconfig's tags); their names are in text.py
LANGUAGES = ('en', 'fr', 'es', 'de', 'pt', 'ja', 'zh-cn', 'ko', 'ru', 'ar')


@dataclass
class Face:
    path: str
    index: int = 0                 # fontconfig's: face number in the low 16 bits, named instance above
    family: str = ''
    style: str = ''
    fullname: str = ''
    weight: int = 80
    slant: int = 0                 # 0 roman, 100 italic, 110 oblique
    spacing: int = 0               # 100 mono, 90 dual, 0 proportional
    width: int = 100
    format: str = ''
    variable: bool = False
    version: int = 0               # fontconfig's: 16.16 fixed point
    psname: str = ''
    langs: frozenset = frozenset()

    @property
    def face_index(self) -> int:
        return self.index & 0xffff

    @property
    def instance(self) -> int:
        return self.index >> 16     # 0 = the font itself, n = named instance n-1

    @property
    def version_text(self) -> str:
        if not self.version:
            return ''
        return f"{self.version >> 16}.{(self.version & 0xffff) * 1000 // 65536:03d}"

    @property
    def italic(self) -> bool:
        return self.slant > 0

    @property
    def title(self) -> str:
        return self.fullname or f"{self.family} {self.style}".strip()

    @property
    def key(self) -> Tuple[str, str]:
        """What makes two faces the same font: family and style."""
        return (self.family.lower(), self.style.lower())


@dataclass
class Family:
    name: str
    faces: List[Face] = field(default_factory=list)

    @property
    def mine(self) -> bool:
        return any(is_user_font(f.path) for f in self.faces)

    @property
    def system(self) -> bool:
        return any(not is_user_font(f.path) for f in self.faces)

    @property
    def mono(self) -> bool:
        return any(f.spacing in (90, 100) for f in self.faces)

    @property
    def variable(self) -> bool:
        return any(f.variable for f in self.faces)

    @property
    def langs(self) -> Set[str]:
        out: Set[str] = set()
        for f in self.faces:
            out |= f.langs
        return out


def parse(text: str) -> List[Face]:
    """Faces from fc-list/fc-query output in FORMAT. Lines that don't parse are skipped."""
    faces = []
    for line in text.split('\n'):
        parts = line.rstrip('\r').split('\t')
        if len(parts) < FIELDS or not parts[0].startswith('/'):
            continue

        def num(i, default=0):
            try:
                return int(parts[i])
            except (ValueError, IndexError):
                return default
        faces.append(Face(
            path=parts[0], index=num(1), family=parts[2].strip(), style=parts[3].strip(),
            fullname=parts[4].strip(), weight=num(5, 80), slant=num(6), spacing=num(7),
            width=num(8, 100), format=parts[9].strip(), variable=parts[10].strip() == 'True',
            version=num(11), psname=parts[12].strip(),
            langs=frozenset(x for x in parts[13].strip().split('|') if x)))
    return faces


def list_faces() -> List[Face]:
    code, out, err = run(['fc-list', '--format', FORMAT], timeout=60)
    if code != 0:
        log.warning("fc-list failed (%s): %s", code, err.strip())
        return []
    return parse(out)


def query_file(path: str) -> List[Face]:
    """The faces fontconfig finds in one file, installed or not ([] when it can't read it)."""
    code, out, _err = run(['fc-query', '--format', FORMAT, path], timeout=30)
    return parse(out) if code == 0 else []


# ─── Who owns a file ──────────────────────────────────────────

def is_user_font(path: str) -> bool:
    return any(core.under(path, root) for root in core.user_font_roots())


def removal_refusal(path: str) -> Optional[str]:
    """None when the file can be removed here, else the reason: 'system' (comes with SparkOS,
    read-only), 'local' (/usr/local needs root), 'flatpak' or 'other'."""
    if is_user_font(path):
        return None
    if path.startswith('/usr/local/'):
        return 'local'
    if '/flatpak/' in path:
        return 'flatpak'
    if path.startswith(('/usr/', '/opt/')):
        return 'system'
    return 'other'


# ─── Styles: Sans, Serif, Mono, Display, Script ──────────────

_generic: Optional[Dict[str, str]] = None
_CONF_DIRS = ('/etc/fonts/conf.d', '/usr/share/fontconfig/conf.avail')
_GENERIC_NAMES = {'sans-serif': 'sans', 'serif': 'serif', 'monospace': 'mono',
                  'fantasy': 'display', 'cursive': 'script'}


def generic_families() -> Dict[str, str]:
    """{family name in lower case: category} from fontconfig's own lists (45-latin.conf and
    friends) of which family is serif, sans-serif, monospace, fantasy (Display) or cursive
    (Script)."""
    global _generic
    if _generic is not None:
        return _generic
    found: Dict[str, str] = {}
    seen = set()
    for folder in _CONF_DIRS:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if not (re.match(r'(45|60)-', name) and name.endswith('.conf')) or name in seen:
                continue
            seen.add(name)
            try:
                root = ET.parse(os.path.join(folder, name)).getroot()
            except (ET.ParseError, OSError):
                continue
            for alias in root.iter('alias'):
                fam = (alias.findtext('family') or '').strip().lower()
                target = alias.find('default')
                if target is None:
                    target = alias.find('prefer')
                if not fam or target is None or fam in _GENERIC_NAMES:
                    continue
                generic = (target.findtext('family') or '').strip().lower()
                if generic in _GENERIC_NAMES:
                    found.setdefault(fam, _GENERIC_NAMES[generic])
    _generic = found
    return found


_SCRIPT = ('script', 'handwriting', 'handwritten', 'brush', 'calligraphy', 'cursive', 'hand')
_DISPLAY = ('display', 'poster', 'stencil', 'headline', 'decorative', 'fantasy')
_MONO = ('mono', 'code', 'console', 'courier', 'typewriter')


def category(family: Family) -> Optional[str]:
    """One of CATEGORIES, or None when neither fontconfig's lists nor the name say."""
    if family.mono:
        return 'mono'
    name = family.name.lower()
    lists = generic_families()
    if name in lists:
        return lists[name]
    words = re.findall(r'[a-z]+', name)
    for i in range(len(words), 0, -1):                 # "Noto Sans CJK JP" -> "Noto Sans CJK"
        known = lists.get(' '.join(words[:i]))
        if known:
            return known
    if 'sans' in words:
        return 'sans'
    if 'serif' in words:
        return 'serif'
    if any(w in words or w in name for w in _MONO):
        return 'mono'
    if any(w in words for w in _SCRIPT):
        return 'script'
    if any(w in words for w in _DISPLAY):
        return 'display'
    return None


# ─── Families ────────────────────────────────────────────────

def sort_key(face: Face) -> Tuple:
    # Regular first by width, then weight, with italics after their upright twin
    return (face.width != 100, face.weight, face.slant, face.style.lower(), face.index)


def group(faces: Iterable[Face]) -> List[Family]:
    """Families sorted by name; each family's faces in a sensible order. A variable font's
    named instances are listed (they are real styles); the variable face itself stays only
    when the file has no instances listed."""
    by: Dict[str, Family] = {}
    for face in faces:
        if not face.family:
            continue
        by.setdefault(face.family.lower(), Family(face.family)).faces.append(face)
    out = []
    for fam in by.values():
        with_instances = {f.path for f in fam.faces if f.instance}
        seen: Set[Tuple[str, int, str]] = set()
        unique = []
        for f in sorted(fam.faces, key=sort_key):
            if not f.instance and f.path in with_instances:
                continue
            key = (f.path, f.index, f.style)
            if key not in seen:
                seen.add(key)
                unique.append(f)
        fam.faces = unique
        out.append(fam)
    out.sort(key=lambda fam: fam.name.lower())
    return out


@dataclass
class Filter:
    text: str = ''
    scope: str = 'all'            # all, mine, system
    category: str = ''            # one of CATEGORIES or ''
    lang: str = ''                # a fontconfig language tag or ''

    def matches(self, fam: Family) -> bool:
        if self.scope == 'mine' and not fam.mine:
            return False
        if self.scope == 'system' and not fam.system:
            return False
        if self.category and category(fam) != self.category:
            return False
        if self.lang and self.lang not in fam.langs:
            return False
        needle = self.text.strip().lower()
        if needle:
            hay = fam.name.lower() + ' ' + ' '.join(f.style.lower() for f in fam.faces)
            return all(word in hay for word in needle.split())
        return True


def apply(families: Sequence[Family], flt: Filter) -> List[Family]:
    return [fam for fam in families if flt.matches(fam)]


_IGNORED = ('fonts.dir', 'fonts.scale', 'fonts.cache-1', '.uuid')


def find_broken(faces: Iterable[Face]) -> List[str]:
    """Files in your font folders that fontconfig doesn't list: damaged, or not fonts."""
    known = {os.path.realpath(f.path) for f in faces}
    broken = []
    for root in core.user_font_roots():
        for base, dirs, names in os.walk(root, followlinks=False):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(base, name)
                if name.startswith('.') or name in _IGNORED:
                    continue
                if os.path.isfile(path) and os.path.realpath(path) not in known:
                    broken.append(path)
    return broken
