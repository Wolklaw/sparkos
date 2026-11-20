"""Writers for test archives this repo can't make with Python alone: RAR 5, RAR 4 (both
'stored', no compression) and plain ISO 9660. Written from the published format notes (RAR:
rarlab's technote; ISO: ECMA-119), only as far as the tests need, so the tests can also craft
hostile names no archiver would write. Not used by the app."""

import struct
import time
import zlib
from typing import Dict, List, Optional, Tuple

# ─── RAR 5 ────────────────────────────────────────────────────

RAR5_SIG = b'Rar!\x1a\x07\x01\x00'


def vint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7f
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _rar5_block(htype: int, flags: int, body: bytes, extra: bytes = b'',
                data: Optional[bytes] = None) -> bytes:
    if extra:
        flags |= 0x0001
    if data is not None:
        flags |= 0x0002
    fields = vint(htype) + vint(flags)
    if extra:
        fields += vint(len(extra))
    if data is not None:
        fields += vint(len(data))
    fields += body + extra
    header = vint(len(fields)) + fields
    return struct.pack('<I', zlib.crc32(header) & 0xffffffff) + header + (data or b'')


def rar5(path: str, members: List[Tuple]) -> None:
    """members: ('file', name, bytes), ('dir', name), ('symlink', name, target)."""
    mtime = int(time.mktime((2024, 3, 5, 10, 20, 0, 0, 0, -1)))
    out = bytearray(RAR5_SIG)
    out += _rar5_block(1, 0, vint(0))                          # main header, flags 0
    for m in members:
        kind, name = m[0], m[1].encode('utf-8')
        extra = b''
        if kind == 'file':
            data = m[2]
            file_flags, attrs = 0x0002 | 0x0004, 0o100644
            tail = struct.pack('<I', mtime) + struct.pack('<I', zlib.crc32(data) & 0xffffffff)
            size = len(data)
        elif kind == 'dir':
            data = None
            file_flags, attrs, size = 0x0001 | 0x0002, 0o040755, 0
            tail = struct.pack('<I', mtime)
        else:                                                   # unix symlink
            data = b''
            file_flags, attrs, size = 0x0002, 0o120777, 0
            tail = struct.pack('<I', mtime)
            target = m[2].encode('utf-8')
            record = vint(5) + vint(1) + vint(0) + vint(len(target)) + target
            extra = vint(len(record)) + record
        body = (vint(file_flags) + vint(size) + vint(attrs) + tail + vint(0)   # stored
                + vint(1) + vint(len(name)) + name)                             # host: unix
        out += _rar5_block(2, 0, body, extra, data)
    out += _rar5_block(5, 0, vint(0))                          # end of archive
    with open(path, 'wb') as f:
        f.write(out)


# ─── RAR 4 ────────────────────────────────────────────────────

RAR4_SIG = b'Rar!\x1a\x07\x00'


def _dos_time(t: time.struct_time) -> int:
    return ((t.tm_year - 1980) << 25) | (t.tm_mon << 21) | (t.tm_mday << 16) | \
        (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)


def rar4(path: str, members: List[Tuple]) -> None:
    """members: ('file', name, bytes), ('dir', name), ('symlink', name, target). ASCII names."""
    dos = _dos_time(time.localtime(time.mktime((2024, 3, 5, 10, 20, 0, 0, 0, -1))))
    out = bytearray(RAR4_SIG)
    main = struct.pack('<BHHHI', 0x73, 0, 13, 0, 0)
    out += struct.pack('<H', zlib.crc32(main) & 0xffff) + main
    for m in members:
        kind, name = m[0], m[1].encode('ascii')
        flags = 0x8000
        if kind == 'file':
            data, attr = m[2], 0o100644
        elif kind == 'dir':
            data, attr = b'', 0o040755
            flags |= 0x00e0
        else:
            data, attr = m[2].encode('ascii'), 0o120777
        size = 7 + 25 + len(name)
        fields = struct.pack('<BHHIIBIIBBHI', 0x74, flags, size, len(data), len(data), 3,
                             zlib.crc32(data) & 0xffffffff, dos, 20, 0x30, len(name), attr)
        fields += name
        out += struct.pack('<H', zlib.crc32(fields) & 0xffff) + fields + data
    end = struct.pack('<BHH', 0x7b, 0x4000, 7)
    out += struct.pack('<H', zlib.crc32(end) & 0xffff) + end
    with open(path, 'wb') as f:
        f.write(out)


# ─── ISO 9660 ─────────────────────────────────────────────────

SECTOR = 2048


def _both16(n: int) -> bytes:
    return struct.pack('<H', n) + struct.pack('>H', n)


def _both32(n: int) -> bytes:
    return struct.pack('<I', n) + struct.pack('>I', n)


def _record(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
    stamp = bytes([124, 3, 5, 10, 20, 0, 0])                    # 2024-03-05 10:20:00 UTC
    body = (bytes([0]) + _both32(lba) + _both32(size) + stamp + bytes([2 if is_dir else 0, 0, 0])
            + _both16(1) + bytes([len(name)]) + name)
    rec = bytes([len(body) + 1]) + body
    if len(rec) % 2:
        rec += b'\0'
    return rec


def _pad(text: str, n: int) -> bytes:
    return text.encode('ascii').ljust(n, b' ')[:n]


def iso9660(path: str, root_files: Dict[str, bytes], subdir: str,
            sub_files: Dict[str, bytes], volume: str = 'SPARKTEST') -> None:
    """Root files, one subfolder with files. Names in ISO 9660 level 1 style (NAME.EXT)."""
    root_lba, sub_lba, data_lba = 20, 21, 22
    layout: List[Tuple[str, bytes, int]] = []           # (where, content, lba)
    lba = data_lba
    for name, content in sorted(root_files.items()):
        layout.append(('/' + name, content, lba))
        lba += max(1, -(-len(content) // SECTOR))
    for name, content in sorted(sub_files.items()):
        layout.append((subdir + '/' + name, content, lba))
        lba += max(1, -(-len(content) // SECTOR))
    total = lba

    def directory(self_lba: int, parent_lba: int, entries: List[Tuple[bytes, int, int, bool]]):
        recs = _record(b'\0', self_lba, SECTOR, True) + _record(b'\1', parent_lba, SECTOR, True)
        for name, at, size, is_dir in sorted(entries):
            recs += _record(name, at, size, is_dir)
        assert len(recs) <= SECTOR
        return recs.ljust(SECTOR, b'\0')

    root_entries = [(subdir.encode('ascii'), sub_lba, SECTOR, True)]
    sub_entries = []
    for where, content, at in layout:
        folder, _, name = where.rpartition('/')
        rec = ((name + ';1').encode('ascii'), at, len(content), False)
        (sub_entries if folder == subdir else root_entries).append(rec)

    def path_table(fmt: str) -> bytes:
        def entry(name: bytes, at: int, parent: int) -> bytes:
            e = bytes([len(name), 0]) + struct.pack(fmt + 'I', at) + \
                struct.pack(fmt + 'H', parent) + name
            return e + (b'\0' if len(name) % 2 else b'')
        return entry(b'\0', root_lba, 1) + entry(subdir.encode('ascii'), sub_lba, 1)

    l_table, m_table = path_table('<'), path_table('>')
    date = b'2024030510200000\0'
    pvd = (bytes([1]) + b'CD001' + bytes([1, 0]) + _pad('LINUX', 32) + _pad(volume, 32)
           + bytes(8) + _both32(total) + bytes(32) + _both16(1) + _both16(1) + _both16(SECTOR)
           + _both32(len(l_table)) + struct.pack('<I', 18) + struct.pack('<I', 0)
           + struct.pack('>I', 19) + struct.pack('>I', 0)
           + _record(b'\0', root_lba, SECTOR, True)
           + _pad('', 128) * 4 + _pad('', 37) * 3 + date + date + b'0000000000000000\0' + date
           + bytes([1, 0]))
    pvd = pvd.ljust(SECTOR, b'\0')
    terminator = (bytes([255]) + b'CD001' + bytes([1])).ljust(SECTOR, b'\0')
    image = bytearray(SECTOR * 16) + pvd + terminator
    image += l_table.ljust(SECTOR, b'\0') + m_table.ljust(SECTOR, b'\0')
    image += directory(root_lba, root_lba, root_entries)
    image += directory(sub_lba, root_lba, sub_entries)
    for _where, content, at in layout:
        assert len(image) == at * SECTOR
        image += content.ljust(max(1, -(-len(content) // SECTOR)) * SECTOR, b'\0')
    with open(path, 'wb') as f:
        f.write(image)
