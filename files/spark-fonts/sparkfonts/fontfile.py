"""Reading a font file itself: what kind of file it is by its first bytes, the names inside it
(designer, foundry, licence), the variable axes, and whether Pillow can draw it.

Plain struct reading, no fontTools. Nothing here writes."""

import struct
import zlib
from dataclasses import dataclass, field
from typing import BinaryIO, Dict, List, Optional, Tuple

# name table IDs (OpenType spec)
N_COPYRIGHT, N_FAMILY, N_STYLE, N_UNIQUE, N_FULL, N_VERSION, N_PS = 0, 1, 2, 3, 4, 5, 6
N_TRADEMARK, N_FOUNDRY, N_DESIGNER, N_DESCRIPTION, N_VENDOR_URL, N_DESIGNER_URL = 7, 8, 9, 10, 11, 12
N_LICENSE, N_LICENSE_URL, N_TYPO_FAMILY, N_TYPO_STYLE = 13, 14, 16, 17

MAX_TABLE = 4 * 1024 * 1024          # a name table bigger than this is not read

MAGIC = {
    b'\x00\x01\x00\x00': 'ttf', b'true': 'ttf', b'OTTO': 'otf', b'ttcf': 'ttc',
    b'wOFF': 'woff', b'wOF2': 'woff2',
}
INSTALLABLE = ('ttf', 'otf', 'ttc')
FONT_EXTENSIONS = ('.ttf', '.otf', '.ttc', '.otc', '.woff', '.woff2')


def sniff(path: str) -> Optional[str]:
    """'ttf', 'otf', 'ttc', 'woff' or 'woff2' by the file's first four bytes (never by its
    name), or None when it is not a font."""
    try:
        with open(path, 'rb') as f:
            return MAGIC.get(f.read(4))
    except OSError:
        return None


class FontError(ValueError):
    pass


@dataclass
class Axis:
    tag: str
    low: float
    default: float
    high: float


@dataclass
class Details:
    names: Dict[int, str] = field(default_factory=dict)
    axes: List[Axis] = field(default_factory=list)
    faces: int = 1                 # in a collection

    def get(self, name_id: int) -> str:
        return self.names.get(name_id, '')

    @property
    def family(self) -> str:
        return self.get(N_TYPO_FAMILY) or self.get(N_FAMILY)

    @property
    def style(self) -> str:
        return self.get(N_TYPO_STYLE) or self.get(N_STYLE)


def _tables(f: BinaryIO, offset: int) -> Dict[bytes, Tuple[int, int]]:
    """{tag: (offset, length)} of an sfnt starting at offset."""
    f.seek(offset)
    head = f.read(12)
    if len(head) < 12:
        raise FontError("truncated")
    count = struct.unpack('>H', head[4:6])[0]
    if count == 0 or count > 256:
        raise FontError("not a font table directory")
    raw = f.read(16 * count)
    if len(raw) < 16 * count:
        raise FontError("truncated")
    out = {}
    for i in range(count):
        tag, _crc, off, length = struct.unpack('>4sIII', raw[16 * i:16 * i + 16])
        out[tag] = (off, length)
    return out


def _decode(platform: int, encoding: int, raw: bytes) -> str:
    if platform in (0, 3):
        return raw.decode('utf-16-be', errors='replace')
    if platform == 1:
        return raw.decode('mac_roman', errors='replace')
    return raw.decode('latin-1', errors='replace')


def parse_names(table: bytes) -> Dict[int, str]:
    """name table -> {id: text}. Windows (3) English names win, then any Windows name, then
    Unicode (0), then Macintosh (1)."""
    if len(table) < 6:
        return {}
    _fmt, count, storage = struct.unpack('>HHH', table[:6])
    best: Dict[int, Tuple[int, str]] = {}
    for i in range(min(count, 2000)):
        rec = table[6 + 12 * i:18 + 12 * i]
        if len(rec) < 12:
            break
        platform, encoding, language, name_id, length, offset = struct.unpack('>HHHHHH', rec)
        raw = table[storage + offset:storage + offset + length]
        if len(raw) != length:
            continue
        text = _decode(platform, encoding, raw).replace('\x00', '').strip()
        if not text:
            continue
        rank = {3: 3, 0: 2, 1: 1}.get(platform, 0)
        if platform == 3 and language & 0xff == 0x09:       # English
            rank = 4
        if name_id not in best or rank > best[name_id][0]:
            best[name_id] = (rank, text)
    return {k: v[1] for k, v in best.items()}


def parse_fvar(table: bytes) -> List[Axis]:
    if len(table) < 16:
        return []
    off, _res, axis_count, axis_size = struct.unpack('>HHHH', table[4:12])
    axes = []
    for i in range(min(axis_count, 32)):
        rec = table[off + axis_size * i:off + axis_size * i + 20]
        if len(rec) < 20:
            break
        tag, low, default, high = struct.unpack('>4siii', rec[:16])
        axes.append(Axis(tag.decode('latin-1'), low / 65536, default / 65536, high / 65536))
    return axes


def _read_table(f: BinaryIO, tables: Dict[bytes, Tuple[int, int]], tag: bytes) -> bytes:
    if tag not in tables:
        return b''
    off, length = tables[tag]
    if length > MAX_TABLE:
        return b''
    f.seek(off)
    return f.read(length)


def _woff_tables(f: BinaryIO) -> Dict[bytes, bytes]:
    head = f.read(44)
    if len(head) < 44:
        raise FontError("truncated")
    count = struct.unpack('>H', head[12:14])[0]
    out = {}
    entries = []
    for _ in range(min(count, 256)):
        tag, off, comp, orig = struct.unpack('>4sIII4x', f.read(20))
        entries.append((tag, off, comp, orig))
    for tag, off, comp, orig in entries:
        if tag not in (b'name', b'fvar') or orig > MAX_TABLE:
            continue
        f.seek(off)
        data = f.read(comp)
        if comp != orig:
            try:
                data = zlib.decompressobj().decompress(data, MAX_TABLE)
            except zlib.error:
                continue
        out[tag] = data
    return out


def read_details(path: str, face: int = 0) -> Details:
    """Names, axes and the collection size of a TrueType, OpenType, collection or WOFF file.
    WOFF2 (Brotli) isn't read here; its details come from fontconfig. Raises FontError."""
    kind = sniff(path)
    if kind is None:
        raise FontError("not a font")
    if kind == 'woff2':
        raise FontError("WOFF2 is not read here")
    out = Details()
    try:
        with open(path, 'rb') as f:
            if kind == 'woff':
                f.seek(0)
                tables = _woff_tables(f)
                name_raw, fvar_raw = tables.get(b'name', b''), tables.get(b'fvar', b'')
            else:
                offset = 0
                if kind == 'ttc':
                    f.seek(8)
                    n = struct.unpack('>I', f.read(4))[0]
                    out.faces = n
                    if not 0 <= face < n or n > 1024:
                        raise FontError("no such face")
                    f.seek(12 + 4 * face)
                    offset = struct.unpack('>I', f.read(4))[0]
                tables = _tables(f, offset)
                name_raw = _read_table(f, tables, b'name')
                fvar_raw = _read_table(f, tables, b'fvar')
    except (OSError, struct.error) as exc:
        raise FontError(str(exc)) from exc
    out.names = parse_names(name_raw)
    out.axes = parse_fvar(fvar_raw)
    return out


def license_text(path: str, face: int = 0) -> Tuple[str, str]:
    """(licence text, licence URL) from the font's name table, or ('', '')."""
    try:
        d = read_details(path, face)
    except FontError:
        return '', ''
    return d.get(N_LICENSE), d.get(N_LICENSE_URL)


# ─── Pillow: can it draw this font? ──────────────────────────

def open_with_pillow(path: str, size: int = 20, index: int = 0):
    """An ImageFont for the file, or raises FontError."""
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise FontError("Pillow is not installed") from exc
    try:
        return ImageFont.truetype(path, size, index=index)
    except (OSError, ValueError, MemoryError) as exc:
        raise FontError(str(exc)) from exc


def check_installable(path: str) -> Tuple[str, int]:
    """(kind, faces) for a file that may be installed: a font by its content, in a format
    worth installing (not WOFF), and one Pillow can open (every face of a collection).
    Raises FontError with the reason in words."""
    kind = sniff(path)
    if kind is None:
        raise FontError('not_font')
    if kind in ('woff', 'woff2'):
        raise FontError('web_font')
    faces = 1
    if kind == 'ttc':
        faces = read_details(path).faces
    for i in range(faces):
        open_with_pillow(path, 12, i)
    return kind, faces
