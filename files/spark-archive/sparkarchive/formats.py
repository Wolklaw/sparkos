"""What kind of archive a file is, from its first bytes (never from its name alone)."""

import bz2
import gzip
import lzma
import os
import zipfile
from typing import Optional

try:                                    # Python 3.14+: zstd in the standard library
    from compression import zstd as _zstd
except ImportError:
    _zstd = None

ZIP, TAR, SEVENZIP, RAR, ISO = 'zip', 'tar', '7z', 'rar', 'iso'
OTHER = 'other'            # anything else libarchive reads: tar.lz, tar.lz4, tar.Z, cpio, cab...
GZ, BZ2, XZ, ZST = 'gz', 'bz2', 'xz', 'zst'
COMPRESSED = (GZ, BZ2, XZ, ZST)

# what the interface calls each kind
LABELS = {ZIP: 'zip', TAR: 'tar', SEVENZIP: '7z', RAR: 'rar', ISO: 'iso',
          'tar.gz': 'tar.gz', 'tar.bz2': 'tar.bz2', 'tar.xz': 'tar.xz', 'tar.zst': 'tar.zst',
          GZ: 'gz', BZ2: 'bz2', XZ: 'xz', ZST: 'zst', OTHER: 'archive'}


def has_zstd() -> bool:
    return _zstd is not None


def open_compressed(path: str, kind: str):
    """A file object that reads the decompressed bytes of a gz, bz2, xz or zst file."""
    if kind == GZ:
        return gzip.open(path, 'rb')
    if kind == BZ2:
        return bz2.open(path, 'rb')
    if kind == XZ:
        return lzma.open(path, 'rb')
    if kind == ZST:
        if _zstd is None:
            raise OSError("this Python has no zstd support")
        return _zstd.open(path, 'rb')
    raise ValueError(kind)


def tar_header_ok(block: bytes) -> bool:
    """A 512-byte tar header: 'ustar' magic, or an old-style header whose checksum adds up."""
    if len(block) < 512:
        return False
    if block[257:262] == b'ustar':
        return True
    if not block[:100].strip(b'\0'):
        return False
    try:
        stored = int(block[148:156].replace(b'\0', b' ').strip() or b'-1', 8)
    except ValueError:
        return False
    total = sum(block[:148]) + 8 * 32 + sum(block[156:512])
    return stored == total


def magic_kind(head: bytes) -> Optional[str]:
    if head.startswith(b'7z\xbc\xaf\x27\x1c'):
        return SEVENZIP
    if head.startswith(b'Rar!\x1a\x07'):
        return RAR
    if head[:4] in (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'):
        return ZIP
    if head.startswith(b'\x1f\x8b'):
        return GZ
    if head.startswith(b'BZh') and head[3:4].isdigit():
        return BZ2
    if head.startswith(b'\xfd7zXZ\x00'):
        return XZ
    if head.startswith(b'\x28\xb5\x2f\xfd'):
        return ZST
    if tar_header_ok(head[:512]):
        return TAR
    return None


def detect(path: str) -> Optional[str]:
    """'zip', '7z', 'rar', 'iso', 'tar', 'tar.gz' (and .bz2 .xz .zst), or a bare 'gz', 'bz2',
    'xz', 'zst' for a single compressed file; 'other' for anything else libarchive reads.
    None if it isn't an archive this app reads."""
    try:
        with open(path, 'rb') as f:
            head = f.read(512)
            iso = False
            for offset in (0x8001, 0x8801, 0x9001):
                f.seek(offset)
                if f.read(5) == b'CD001':
                    iso = True
                    break
    except OSError:
        return None
    kind = magic_kind(head)
    if kind in COMPRESSED:
        try:
            with open_compressed(path, kind) as inner:
                block = inner.read(512)
        except (OSError, EOFError, ValueError, lzma.LZMAError):
            return kind
        if tar_header_ok(block):
            return 'tar.' + kind
        return kind
    if kind:
        return kind
    if iso:
        return ISO
    try:
        if zipfile.is_zipfile(path):           # self-extracting, or data before the zip
            return ZIP
    except OSError:
        pass
    from . import libarchive
    if libarchive.load():
        name, _err = libarchive.first_header(path)
        if name and 'raw' not in name.lower():
            return OTHER
    return None


def describe(kind: Optional[str]) -> str:
    return LABELS.get(kind or '', kind or '?')


def is_archive(path: str) -> bool:
    return os.path.isfile(path) and detect(path) is not None
