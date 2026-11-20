"""Archives in several parts. Opening any part opens the whole set; a missing part is named.

  photos.7z.001, .002, ...        one archive cut into pieces (7-Zip's -v, HJSplit); any
                                  archive type, .zip.001 and .tar.001 too
  photos.part1.rar, .part2.rar    RAR 3 and later (also part01, part001)
  photos.rar, .r00, .r01 ...      RAR's older naming (after .r99 come .s00 ...)
  photos.z01, .z02 ..., .zip      zip split by Info-ZIP's zip -s, WinZip and 7-Zip

The end of a set is read from the parts themselves where the format says it: a 7z archive
records its full size, every RAR volume says whether another follows, and a split zip's last
part says how many came before it. So "photos.part4.rar is missing" is found even when it was
the last one."""

import os
import re
import struct
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

SPLIT, RAR, ZIP = 'split', 'rar', 'zip'


@dataclass
class Volumes:
    style: str                      # SPLIT, RAR or ZIP
    stem: str                       # photos
    open_path: str                  # what a command-line tool is given: part 1, or the .zip
    parts: List[str] = field(default_factory=list)   # every part there, in order
    missing: Optional[str] = None   # the file name of the first part that isn't there

    @property
    def first(self) -> str:
        return self.parts[0] if self.parts else self.open_path


_SPLIT_RE = re.compile(r'^(?P<base>.+)\.(?P<num>\d{3})$')
_PART_RE = re.compile(r'^(?P<base>.+)\.part(?P<num>\d+)\.rar$', re.I)
_OLD_RAR_RE = re.compile(r'^(?P<base>.+)\.(?P<ext>rar|[rst]\d\d)$', re.I)
_ZIP_RE = re.compile(r'^(?P<base>.+)\.(?P<ext>zip|z\d\d+)$', re.I)


def find(path: str) -> Optional[Volumes]:
    """The set `path` belongs to, or None if it is a plain one-file archive."""
    folder, name = os.path.split(os.path.abspath(path))
    for finder in (_split, _rar_parts, _rar_old, _zip_split):
        found = finder(folder, name)
        if found:
            return found
    return None


def stem_of(name: str) -> Optional[str]:
    """The set's name without its part suffix (photos.part2.rar, photos.7z.001, photos.r00,
    photos.z01 -> photos), for naming the folder it extracts to; None if `name` doesn't look
    like a part."""
    m = _PART_RE.match(name)
    if m:
        return m.group('base')
    m = _SPLIT_RE.match(name)
    if m:
        return _strip_ext(m.group('base'))
    m = re.match(r'^(?P<base>.+)\.(?:[rst]\d\d|z\d\d+)$', name, re.I)
    if m:
        return m.group('base')
    return None


def _strip_ext(base: str) -> str:
    low = base.lower()
    for ext in ('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.7z', '.zip', '.tar', '.rar'):
        if low.endswith(ext) and len(base) > len(ext):
            return base[:-len(ext)]
    return base


def _exists(folder: str, name: str) -> bool:
    return os.path.isfile(os.path.join(folder, name))


def _siblings(folder: str, regex: 're.Pattern', base: str) -> List[Tuple[int, str]]:
    """(number, name) of every file in the folder that is a part of `base`."""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for other in names:
        m = regex.match(other)
        if m and m.group('base') == base:
            out.append((_number(m), other))
    return sorted(out)


def _number(m: 're.Match') -> int:
    """part3 -> 3, .002 -> 2; old RAR: .rar -> 0, .r00 -> 1, .s00 -> 101; zip: .zip -> 0,
    .z01 -> 1."""
    groups = m.groupdict()
    if groups.get('num') is not None:
        return int(groups['num'])
    ext = groups['ext'].lower()
    if ext in ('rar', 'zip'):
        return 0
    if m.re is _ZIP_RE:
        return int(ext[1:])
    return 1 + (ord(ext[0]) - ord('r')) * 100 + int(ext[1:])


def _gaps(numbers: List[int], first: int, last: int) -> Optional[int]:
    have = set(numbers)
    for n in range(first, last + 1):
        if n not in have:
            return n
    return None


# ─── 7z.001, zip.001 ...: one file cut into pieces ────────────

def _split(folder: str, name: str) -> Optional[Volumes]:
    m = _SPLIT_RE.match(name)
    if not m:
        return None
    base = m.group('base')
    parts = _siblings(folder, _SPLIT_RE, base)
    numbers = [n for n, _ in parts]
    # "data.123" on its own is just a file with a number for an extension, unless part 001
    # is there or this file doesn't look like an archive by itself
    if 1 not in numbers and int(m.group('num')) != 1:
        from .formats import magic_kind
        try:
            with open(os.path.join(folder, name), 'rb') as f:
                if magic_kind(f.read(512)):
                    return None
        except OSError:
            return None
    vols = Volumes(SPLIT, _strip_ext(base), os.path.join(folder, f"{base}.001"))
    gap = _gaps(numbers, 1, max(numbers))
    if gap is not None:
        vols.missing = f"{base}.{gap:03d}"
        return vols
    vols.parts = [os.path.join(folder, n) for _, n in parts]
    total = _7z_total(vols.parts[0])
    if total is not None and sum(_size(p) for p in vols.parts) < total:
        vols.missing = f"{base}.{max(numbers) + 1:03d}"
    return vols


def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _7z_total(path: str) -> Optional[int]:
    """A 7z archive's full size, from its start header."""
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
    except OSError:
        return None
    if len(head) < 32 or not head.startswith(b'7z\xbc\xaf\x27\x1c'):
        return None
    offset, size = struct.unpack('<QQ', head[12:28])
    return 32 + offset + size


# ─── RAR: photos.part1.rar ... ────────────────────────────────

def _rar_parts(folder: str, name: str) -> Optional[Volumes]:
    m = _PART_RE.match(name)
    if not m:
        return None
    base = m.group('base')
    parts = _siblings(folder, _PART_RE, base)
    numbers = [n for n, _ in parts]
    if numbers == [1]:
        is_volume, _more = rar_volume_info(os.path.join(folder, name))
        if is_volume is False:
            return None                     # a single archive that happens to be "part1"
    width = len(m.group('num'))
    by_number = dict(parts)

    def part_name(n: int) -> str:
        return by_number.get(n) or f"{base}.part{n:0{width}d}.rar"

    vols = Volumes(RAR, base, os.path.join(folder, part_name(1)))
    return _rar_finish(vols, folder, parts, part_name)


def _rar_old(folder: str, name: str) -> Optional[Volumes]:
    m = _OLD_RAR_RE.match(name)
    if not m or _PART_RE.match(name):
        return None
    base = m.group('base')
    parts = _siblings(folder, _OLD_RAR_RE, base)
    if [n for n, _ in parts] == [0]:
        is_volume, _more = rar_volume_info(os.path.join(folder, name))
        if not is_volume:
            return None                     # an ordinary .rar

    def part_name(n: int) -> str:
        if n == 0:
            return base + '.rar'
        letter = chr(ord('r') + (n - 1) // 100)
        return f"{base}.{letter}{(n - 1) % 100:02d}"

    vols = Volumes(RAR, base, os.path.join(folder, part_name(0)))
    return _rar_finish(vols, folder, parts, part_name, first=0)


def _rar_finish(vols: Volumes, folder: str, parts: List[Tuple[int, str]],
                part_name: Callable[[int], str], first: int = 1) -> Volumes:
    numbers = [n for n, _ in parts]
    gap = _gaps(numbers, first, max(numbers))
    if gap is not None:
        vols.missing = part_name(gap)
        return vols
    vols.parts = [os.path.join(folder, n) for _, n in parts]
    _is_volume, more = rar_volume_info(vols.parts[-1])
    if more:
        vols.missing = part_name(max(numbers) + 1)
    return vols


def rar_volume_info(path: str) -> Tuple[Optional[bool], Optional[bool]]:
    """(is a volume, another volume follows) from a RAR file's own headers; None where they
    don't say (encrypted headers, or not RAR at all)."""
    try:
        with open(path, 'rb') as f:
            sig = f.read(8)
            if sig.startswith(b'Rar!\x1a\x07\x01\x00'):
                return _rar5_info(f)
            if sig.startswith(b'Rar!\x1a\x07\x00'):
                f.seek(7)
                return _rar4_info(f)
    except (OSError, struct.error, ValueError):
        pass
    return None, None


def _read_vint(data: bytes, pos: int) -> Tuple[int, int]:
    value, shift = 0, 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ValueError("bad vint")
        b = data[pos]
        value |= (b & 0x7f) << shift
        pos += 1
        if not b & 0x80:
            return value, pos
        shift += 7


def _rar5_info(f) -> Tuple[Optional[bool], Optional[bool]]:
    is_volume = None
    for _ in range(200000):
        start = f.read(7)                       # CRC32 + at most 3 bytes of header size
        if len(start) < 5:
            return is_volume, None
        size, pos = _read_vint(start, 4)
        f.seek(f.tell() - len(start) + pos)
        header = f.read(size)
        if len(header) < size:
            return is_volume, None
        htype, p = _read_vint(header, 0)
        flags, p = _read_vint(header, p)
        data_size = 0
        if flags & 0x0001:
            _extra, p = _read_vint(header, p)
        if flags & 0x0002:
            data_size, p = _read_vint(header, p)
        if htype == 4:                          # encrypted headers: nothing more to read
            return None, None
        if htype == 1:
            arc_flags, _ = _read_vint(header, p)
            is_volume = bool(arc_flags & 0x0001)
        if htype == 5:
            end_flags, _ = _read_vint(header, p)
            return is_volume, bool(end_flags & 0x0001)
        f.seek(data_size, os.SEEK_CUR)
    return is_volume, None


def _rar4_info(f) -> Tuple[Optional[bool], Optional[bool]]:
    is_volume = None
    for _ in range(200000):
        head = f.read(7)
        if len(head) < 7:
            return is_volume, None              # RAR before 3.0 may end without an end block
        _crc, htype, flags, size = struct.unpack('<HBHH', head)
        if size < 7:
            return is_volume, None
        rest = f.read(size - 7)
        add = 0
        if flags & 0x8000 and len(rest) >= 4:
            add = struct.unpack('<I', rest[:4])[0]
            if htype in (0x74, 0x7a) and flags & 0x0100 and len(rest) >= 29:
                add |= struct.unpack('<I', rest[25:29])[0] << 32
        if htype == 0x73:
            is_volume = bool(flags & 0x0001)
            if flags & 0x0080:                  # encrypted headers
                return is_volume, None
        elif htype == 0x7b:
            return is_volume, bool(flags & 0x0001)
        f.seek(add, os.SEEK_CUR)
    return is_volume, None


# ─── photos.z01, .z02 ..., photos.zip ─────────────────────────

def _zip_split(folder: str, name: str) -> Optional[Volumes]:
    m = _ZIP_RE.match(name)
    if not m:
        return None
    base = m.group('base')
    parts = _siblings(folder, _ZIP_RE, base)
    numbers = [n for n, _ in parts]
    last_disk = None
    if 0 in numbers:
        last_disk = _zip_disk(os.path.join(folder, base + '.zip'))
    if numbers == [0] and not last_disk:
        return None                             # an ordinary zip
    vols = Volumes(ZIP, base, os.path.join(folder, base + '.zip'))
    split = sorted(n for n in numbers if n)
    expected = last_disk if last_disk else (max(split) if split else 0)
    width = max([len(n) - len(base) - 2 for _, n in parts if not n.lower().endswith('.zip')]
                or [2])

    def part_name(n: int) -> str:
        return f"{base}.z{n:0{width}d}"

    gap = _gaps(split, 1, max([expected] + split))
    if gap is not None:
        vols.missing = part_name(gap)
        return vols
    if 0 not in numbers:
        vols.missing = base + '.zip'
        return vols
    vols.parts = [os.path.join(folder, n) for _, n in sorted(parts, key=lambda p: p[0] or 1e9)]
    return vols


def _zip_disk(path: str) -> Optional[int]:
    """The 'number of this disk' in a zip's end record: how many parts come before it."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 66000))
            tail = f.read()
    except OSError:
        return None
    at = tail.rfind(b'PK\x05\x06')
    if at < 0 or len(tail) - at < 22:
        return None
    disk = struct.unpack('<H', tail[at + 4:at + 6])[0]
    if disk == 0xffff:                          # zip64: the real number is elsewhere
        loc = tail.rfind(b'PK\x06\x07', 0, at)
        if loc >= 0 and len(tail) - loc >= 20:
            return struct.unpack('<I', tail[loc + 16:loc + 20])[0] - 1
        return None
    return disk
