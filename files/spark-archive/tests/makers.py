"""Writers for test archives this repo can't make with Python alone: RAR 5 and RAR 4 ('stored',
no compression), with a password, with encrypted names (RAR 5) or in several volumes; zip split
into .z01, .z02... parts; and plain ISO 9660. Written from the published format notes (RAR:
rarlab's technote, and unrar's own source for how RAR 4 and RAR 5 turn a password into a key;
split zip: PKWARE's APPNOTE; ISO: ECMA-119), only as far as the tests need, so the tests can
also craft hostile names no archiver would write. Not used by the app.

There is no free RAR writer (rarlab's `rar` may not be redistributed), so these are how the
tests get real RAR files: unrar, libarchive and 7-Zip all read them like ones RAR made."""

import hashlib
import hmac
import io
import os
import struct
import time
import zipfile
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

# ─── AES (encrypting only), for password-protected RAR ───────


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x11b) if a & 0x80 else a << 1


def _rotl8(x: int, s: int) -> int:
    return ((x << s) | (x >> (8 - s))) & 0xff


def _make_sbox() -> List[int]:
    box = [0] * 256
    p = q = 1
    while True:
        p ^= _xtime(p)                                   # p * 3
        q ^= q << 1                                      # q / 3
        q ^= q << 2
        q ^= q << 4
        q &= 0xff
        if q & 0x80:
            q ^= 0x09
        box[p] = q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4) ^ 0x63
        if p == 1:
            break
    box[0] = 0x63
    return box


SBOX = _make_sbox()


def _expand_key(key: bytes) -> List[List[int]]:
    nk = len(key) // 4
    rounds = nk + 6
    words = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (rounds + 1)):
        t = list(words[i - 1])
        if i % nk == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        words.append([a ^ b for a, b in zip(words[i - nk], t)])
    return [sum(words[4 * r:4 * r + 4], []) for r in range(rounds + 1)]


def _encrypt_block(keys: List[List[int]], block: bytes) -> bytes:
    s = [b ^ k for b, k in zip(block, keys[0])]
    last = len(keys) - 1
    for rnd in range(1, last + 1):
        s = [SBOX[b] for b in s]
        s = [s[(r + 4 * ((c + r) % 4))] for c in range(4) for r in range(4)]   # shift rows
        if rnd != last:                                                         # mix columns
            mixed = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                x = [_xtime(v) for v in a]
                mixed += [x[0] ^ x[1] ^ a[1] ^ a[2] ^ a[3],
                          a[0] ^ x[1] ^ x[2] ^ a[2] ^ a[3],
                          a[0] ^ a[1] ^ x[2] ^ x[3] ^ a[3],
                          x[0] ^ a[0] ^ a[1] ^ a[2] ^ x[3]]
            s = mixed
        s = [b ^ k for b, k in zip(s, keys[rnd])]
    return bytes(s)


def aes_cbc(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128 or AES-256 in CBC mode; `data` is padded with zeros to 16 bytes, as RAR does."""
    keys = _expand_key(key)
    data += b'\0' * (-len(data) % 16)
    out, prev = bytearray(), iv
    for i in range(0, len(data), 16):
        prev = _encrypt_block(keys, bytes(a ^ b for a, b in zip(data[i:i + 16], prev)))
        out += prev
    return bytes(out)


# ─── RAR 5 ────────────────────────────────────────────────────

RAR5_SIG = b'Rar!\x1a\x07\x01\x00'
RAR5_LG2 = 15                     # PBKDF2 rounds = 2^15, what RAR itself uses


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


def rar5_key(password: str, salt: bytes, lg2: int = RAR5_LG2) -> Tuple[bytes, bytes]:
    """(AES-256 key, 12-byte password check) the way unrar's crypt5.cpp makes them: PBKDF2
    with HMAC-SHA256, then 16 and 16 more rounds for two extra values; the second, folded to 8
    bytes, is the password check, followed by 4 bytes of its SHA-256."""
    pwd = password.encode('utf-8')

    def prf(data: bytes) -> bytes:
        return hmac.new(pwd, data, hashlib.sha256).digest()

    u = prf(salt + b'\0\0\0\1')
    fn = int.from_bytes(u, 'big')
    values = []
    for count in ((1 << lg2) - 1, 16, 16):
        for _ in range(count):
            u = prf(u)
            fn ^= int.from_bytes(u, 'big')
        values.append(fn.to_bytes(32, 'big'))
    key, _hash_key, check_value = values
    check = bytearray(8)
    for i, b in enumerate(check_value):
        check[i % 8] ^= b
    return key, bytes(check) + hashlib.sha256(bytes(check)).digest()[:4]


class _Rar5Crypto:
    def __init__(self, password: str):
        self.salt = os.urandom(16)
        self.key, self.check = rar5_key(password, self.salt)

    def file_record(self, iv: bytes) -> bytes:
        """The file encryption record of a file header's extra area (type 1)."""
        body = (vint(1) + vint(0) + vint(0x0001) + bytes([RAR5_LG2]) + self.salt + iv
                + self.check)
        return vint(len(body)) + body

    def archive_header(self) -> bytes:
        """Archive encryption header (type 4): everything after it is encrypted."""
        return _rar5_block(4, 0, vint(0) + vint(0x0001) + bytes([RAR5_LG2]) + self.salt
                           + self.check)


def _rar5_block(htype: int, flags: int, body: bytes, extra: bytes = b'',
                data: Optional[bytes] = None, hkey: Optional[bytes] = None) -> bytes:
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
    block = struct.pack('<I', zlib.crc32(header) & 0xffffffff) + header
    if hkey is not None:                   # encrypted names: each header behind its own IV
        iv = os.urandom(16)
        block = iv + aes_cbc(hkey, iv, block)
    return block + (data or b'')


def _plan(members: Sequence[Tuple], volume_size: Optional[int]):
    """Members spread over volumes: one list per volume of (member, piece of its data,
    continues from the previous volume, continues in the next)."""
    if not volume_size:
        return [[(m, m[2] if m[0] == 'file' else None, False, False) for m in members]]
    vols: List[list] = [[]]
    room = volume_size
    for m in members:
        if m[0] != 'file':
            vols[-1].append((m, None, False, False))
            continue
        data, pos = m[2], 0
        while True:
            if room <= 0:
                vols.append([])
                room = volume_size
            piece = data[pos:pos + room]
            end = pos + len(piece)
            vols[-1].append((m, piece, pos > 0, end < len(data)))
            room -= len(piece)
            pos = end
            if pos >= len(data):
                break
    return vols


MTIME = int(time.mktime((2024, 3, 5, 10, 20, 0, 0, 0, -1)))


def _rar5_file(m, piece, before, after, crypto, hkey) -> bytes:
    kind, name = m[0], m[1].encode('utf-8')
    extra, data = b'', None
    if kind == 'file':
        full = m[2]
        file_flags, attrs = 0x0002 | 0x0004, 0o100644
        # a part that goes on in the next volume carries the CRC of its own bytes; the last
        # part (or the whole file) the CRC of the whole file
        crc = zlib.crc32(piece if after else full) & 0xffffffff
        tail = struct.pack('<I', MTIME) + struct.pack('<I', crc)
        size, data = len(full), piece
        if crypto:
            iv = os.urandom(16)
            data = aes_cbc(crypto.key, iv, piece)
            extra = crypto.file_record(iv)
    elif kind == 'dir':
        file_flags, attrs, size = 0x0001 | 0x0002, 0o040755, 0
        tail = struct.pack('<I', MTIME)
    else:                                                       # unix symlink
        data = b''
        file_flags, attrs, size = 0x0002, 0o120777, 0
        tail = struct.pack('<I', MTIME)
        target = m[2].encode('utf-8')
        record = vint(5) + vint(1) + vint(0) + vint(len(target)) + target
        extra = vint(len(record)) + record
    body = (vint(file_flags) + vint(size) + vint(attrs) + tail + vint(0)   # stored
            + vint(1) + vint(len(name)) + name)                             # host: unix
    flags = (0x0008 if before else 0) | (0x0010 if after else 0)
    return _rar5_block(2, flags, body, extra, data, hkey)


def _rar5_write(paths: List[str], members, password, encrypt_names, volume_size) -> List[str]:
    crypto = _Rar5Crypto(password) if password is not None else None
    hkey = crypto.key if crypto and encrypt_names else None
    vols = _plan(members, volume_size)
    assert len(vols) <= len(paths), f"{len(vols)} volumes, {len(paths)} names"
    for i, entries in enumerate(vols):
        out = bytearray(RAR5_SIG)
        if hkey:
            out += crypto.archive_header()
        arc_flags = 0
        main = b''
        if volume_size:
            arc_flags = 0x0001 | (0x0002 if i else 0)
            main = vint(i) if i else b''
        out += _rar5_block(1, 0, vint(arc_flags) + main, hkey=hkey)
        for m, piece, before, after in entries:
            out += _rar5_file(m, piece, before, after, crypto, hkey)
        more = i < len(vols) - 1
        out += _rar5_block(5, 0, vint(0x0001 if more else 0), hkey=hkey)
        with open(paths[i], 'wb') as f:
            f.write(out)
    return paths[:len(vols)]


def rar5(path: str, members: List[Tuple], password: Optional[str] = None,
         encrypt_names: bool = False) -> None:
    """members: ('file', name, bytes), ('dir', name), ('symlink', name, target). With a
    password the files' data is AES-256 encrypted (with a password check, as RAR does);
    encrypt_names encrypts every header too, so even the listing needs the password."""
    _rar5_write([path], members, password, encrypt_names, None)


def rar5_volumes(base: str, members: List[Tuple], volume_size: int,
                 digits: int = 1) -> List[str]:
    """base.part1.rar, base.part2.rar... (part01 with digits=2); file data split so each
    volume holds at most volume_size bytes of it. Returns the volumes written."""
    names = [f"{base}.part{n:0{digits}d}.rar" for n in range(1, 100)]
    return _rar5_write(names, members, None, False, volume_size)


# ─── RAR 4 ────────────────────────────────────────────────────

RAR4_SIG = b'Rar!\x1a\x07\x00'


def _dos_time(t: time.struct_time) -> int:
    return ((t.tm_year - 1980) << 25) | (t.tm_mon << 21) | (t.tm_mday << 16) | \
        (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)


def rar4_key(password: str, salt: bytes) -> Tuple[bytes, bytes]:
    """(AES-128 key, IV) the way unrar's crypt3.cpp makes them for RAR 3.x and 4.x: 2^18
    rounds of SHA-1 over the UTF-16 password, the salt and the round number. (unrar's SHA-1
    changes its input for passwords of 28 characters and more; keep test passwords short.)"""
    assert len(password) < 28
    raw = password.encode('utf-16-le') + salt
    h = hashlib.sha1()
    iv = bytearray(16)
    rounds = 0x40000
    for i in range(rounds):
        h.update(raw)
        h.update(bytes((i & 0xff, (i >> 8) & 0xff, (i >> 16) & 0xff)))
        if i % (rounds // 16) == 0:
            iv[i // (rounds // 16)] = h.copy().digest()[19]
    d = h.digest()
    key = b''.join(d[4 * w:4 * w + 4][::-1] for w in range(4))
    return key, bytes(iv)


def _rar4_block(fields: bytes) -> bytes:
    return struct.pack('<H', zlib.crc32(fields) & 0xffff) + fields


def _rar4_write(paths: List[str], members, password, volume_size, new_numbering) -> List[str]:
    dos = _dos_time(time.localtime(MTIME))
    vols = _plan(members, volume_size)
    assert len(vols) <= len(paths)
    if password is not None:
        salt = os.urandom(8)
        key, iv = rar4_key(password, salt)
    for i, entries in enumerate(vols):
        out = bytearray(RAR4_SIG)
        main_flags = 0
        if volume_size:
            main_flags = 0x0001 | (0x0100 if i == 0 else 0) | (0x0010 if new_numbering else 0)
        out += _rar4_block(struct.pack('<BHHHI', 0x73, main_flags, 13, 0, 0))
        for m, piece, before, after in entries:
            kind, name = m[0], m[1].encode('ascii')
            flags = 0x8000 | (0x0001 if before else 0) | (0x0002 if after else 0)
            version = 20
            tail = b''
            if kind == 'file':
                full, attr = m[2], 0o100644
                crc = zlib.crc32(piece if after else full) & 0xffffffff
                data, unpacked = piece, len(full)
                if password is not None:
                    flags |= 0x0004 | 0x0400                  # encrypted, with a salt
                    version = 29                              # AES: RAR 2.9 and later
                    data = aes_cbc(key, iv, piece)            # one file: the IV is the key's
                    tail = salt
            elif kind == 'dir':
                data, attr, unpacked = b'', 0o040755, 0
                flags |= 0x00e0
                crc = 0
            else:
                data, attr = m[2].encode('ascii'), 0o120777
                unpacked, crc = len(data), zlib.crc32(data) & 0xffffffff
            size = 7 + 25 + len(name) + len(tail)
            fields = struct.pack('<BHHIIBIIBBHI', 0x74, flags, size, len(data), unpacked, 3,
                                 crc, dos, version, 0x30, len(name), attr)
            out += _rar4_block(fields + name + tail) + data
        more = i < len(vols) - 1
        out += _rar4_block(struct.pack('<BHH', 0x7b, 0x4000 | (0x0001 if more else 0), 7))
        with open(paths[i], 'wb') as f:
            f.write(out)
    return paths[:len(vols)]


def rar4(path: str, members: List[Tuple], password: Optional[str] = None) -> None:
    """members: ('file', name, bytes), ('dir', name), ('symlink', name, target). ASCII names.
    With a password the files' data is AES-128 encrypted (RAR 4 has no password check: a
    wrong password shows as a checksum error). Only one file may be encrypted per archive
    here, since every file would need its own salt."""
    if password is not None:
        assert sum(1 for m in members if m[0] == 'file') == 1
    _rar4_write([path], members, password, None, False)


def rar4_volumes(base: str, members: List[Tuple], volume_size: int,
                 old_names: bool = True) -> List[str]:
    """base.rar, base.r00, base.r01... (old_names) or base.part1.rar, base.part2.rar..."""
    if old_names:
        names = [base + '.rar'] + [f"{base}.r{n:02d}" for n in range(100)]
    else:
        names = [f"{base}.part{n}.rar" for n in range(1, 100)]
    return _rar4_write(names, members, None, volume_size, not old_names)


# ─── zip split into parts: base.z01, base.z02, ..., base.zip ──

def split_zip(base: str, files: Dict[str, bytes], part_size: int) -> List[str]:
    """A zip split the way Info-ZIP's `zip -s` and WinZip do it: the first part starts with
    the spanning signature, offsets in the central directory are per part, and the central
    directory and its end record sit whole in the last part, base.zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, (2024, 3, 5, 10, 20, 0))
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    raw = buf.getvalue()
    at = raw.rindex(b'PK\x05\x06')
    (_sig, _d, _cd, _n1, count, cd_size, cd_off, _clen) = struct.unpack('<IHHHHIIH',
                                                                       raw[at:at + 22])
    stream = b'PK\x07\x08' + raw[:cd_off]
    pieces = [stream[i:i + part_size] for i in range(0, len(stream), part_size)]
    last = len(pieces) - 1
    cd = bytearray(raw[cd_off:cd_off + cd_size])
    pos = 0
    for _ in range(count):
        name_len, extra_len, comment_len = struct.unpack('<HHH', cd[pos + 28:pos + 34])
        offset = struct.unpack('<I', cd[pos + 42:pos + 46])[0] + 4
        disk = min(offset // part_size, last)
        struct.pack_into('<H', cd, pos + 34, disk)
        struct.pack_into('<I', cd, pos + 42, offset - disk * part_size)
        pos += 46 + name_len + extra_len + comment_len
    end = struct.pack('<IHHHHIIH', 0x06054b50, last, last, count, count, cd_size,
                      len(pieces[last]), 0)
    pieces[last] += bytes(cd) + end
    paths = [f"{base}.z{n + 1:02d}" for n in range(last)] + [base + '.zip']
    for path, data in zip(paths, pieces):
        with open(path, 'wb') as f:
            f.write(data)
    return paths


def split_bytes(path: str, part_size: int) -> List[str]:
    """path.001, path.002...: the file cut into pieces, the way 7-Zip's -v switch does."""
    with open(path, 'rb') as f:
        data = f.read()
    paths = []
    for n, i in enumerate(range(0, len(data), part_size), 1):
        paths.append(f"{path}.{n:03d}")
        with open(paths[-1], 'wb') as f:
            f.write(data[i:i + part_size])
    return paths


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
    if (len(body) + 1) % 2:                     # records are even-sized; the length counts the pad
        body += b'\0'
    return bytes([len(body) + 1]) + body


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
