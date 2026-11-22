"""Make small Windows files for the tests, byte by byte: a PE (.exe) with an icon and a
version resource, a DOS program, a .lnk shortcut, a PNG. No compiler or Windows needed."""

import struct
import zlib
from typing import Dict, List, Optional

LANG = 0x409


def png(size: int = 16, rgba=(61, 232, 200, 255)) -> bytes:
    raw = b''.join(b'\0' + bytes(rgba) * size for _ in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + \
            struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0,
                                                               0, 0)) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def _pad4(b: bytes) -> bytes:
    return b + b'\0' * (-len(b) % 4)


def _node(key: str, value: bytes = b'', vtype: int = 0, children: List[bytes] = (),
          value_len: Optional[int] = None) -> bytes:
    body = key.encode('utf-16-le') + b'\0\0'
    head_len = 6
    data = _pad4(b'\0' * head_len + body)[head_len:]   # pad so the value starts aligned
    blob = data + value
    blob = _pad4(b'\0' * head_len + blob)[head_len:] if children else blob
    for child in children:
        blob = _pad4(b'\0' * head_len + blob)[head_len:] + child
    if value_len is None:
        value_len = len(value) // 2 if vtype == 1 else len(value)
    return struct.pack('<HHH', head_len + len(blob), value_len, vtype) + blob


def version_info(strings: Dict[str, str]) -> bytes:
    fixed = struct.pack('<13I', 0xFEEF04BD, 0x10000, 0x10000, 0, 0x10000, 0, 0x3f, 0, 0x40004,
                        1, 0, 0, 0)
    table = _node('040904b0', children=[
        _node(k, (v + '\0').encode('utf-16-le'), 1) for k, v in strings.items()])
    return _node('VS_VERSION_INFO', fixed, 0, [
        _node('StringFileInfo', children=[table]),
        _node('VarFileInfo', children=[_node('Translation', struct.pack('<HH', LANG, 1200))]),
    ])


def _resources(res: Dict[int, Dict[int, bytes]], va: int) -> bytes:
    types = sorted(res)
    dirs_size = 16 + 8 * len(types)
    for tid in types:
        dirs_size += 16 + 8 * len(res[tid])
        dirs_size += (16 + 8) * len(res[tid])
    leaves = [(tid, nid) for tid in types for nid in sorted(res[tid])]
    entries_at = dirs_size
    blobs_at = entries_at + 16 * len(leaves)
    blob_offsets, pos = {}, blobs_at
    for leaf in leaves:
        blob_offsets[leaf] = pos
        pos += len(res[leaf[0]][leaf[1]])
        pos += -pos % 4
    out = bytearray(pos)

    def directory(at: int, items: List[tuple]) -> None:
        struct.pack_into('<IIHHHH', out, at, 0, 0, 0, 0, 0, len(items))
        for i, (ident, target) in enumerate(items):
            struct.pack_into('<II', out, at + 16 + 8 * i, ident, target)

    cursor = 16 + 8 * len(types)
    type_items, leaf_index = [], 0
    for tid in types:
        type_dir = cursor
        cursor += 16 + 8 * len(res[tid])
        type_items.append((tid, 0x80000000 | type_dir))
        name_items = []
        for nid in sorted(res[tid]):
            lang_dir = cursor
            cursor += 16 + 8
            name_items.append((nid, 0x80000000 | lang_dir))
            entry = entries_at + 16 * leaf_index
            directory(lang_dir, [(LANG, entry)])
            data = res[tid][nid]
            struct.pack_into('<IIII', out, entry, va + blob_offsets[(tid, nid)], len(data), 0, 0)
            out[blob_offsets[(tid, nid)]:blob_offsets[(tid, nid)] + len(data)] = data
            leaf_index += 1
        directory(type_dir, name_items)
    directory(0, type_items)
    return bytes(out)


def pe(machine: str = 'x64', gui: bool = True, strings: Optional[Dict[str, str]] = None,
       icon: bool = True, manifest: bytes = b'', dotnet: bool = False,
       trailer: bytes = b'') -> bytes:
    """A PE file whose only section is .rsrc (it can't run; it only has to be read)."""
    va, raw_at = 0x1000, 0x400
    res: Dict[int, Dict[int, bytes]] = {}
    if icon:
        image = png(16)
        res[3] = {1: image}
        res[14] = {101: struct.pack('<HHH', 0, 1, 1) +
                   struct.pack('<BBBBHHIH', 16, 16, 0, 0, 1, 32, len(image), 1)}
    if strings:
        res[16] = {1: version_info(strings)}
    if manifest:
        res[24] = {1: manifest}
    rsrc = _resources(res, va) if res else b''
    machine_id = {'x64': 0x8664, 'x86': 0x14c, 'arm64': 0xaa64}[machine]
    plus = machine in ('x64', 'arm64')
    opt_size = 240 if plus else 224
    dd_at = 112 if plus else 96
    opt = bytearray(opt_size)
    struct.pack_into('<H', opt, 0, 0x20b if plus else 0x10b)
    struct.pack_into('<H', opt, 68, 2 if gui else 3)
    struct.pack_into('<I', opt, dd_at - 4, 16)
    if rsrc:
        struct.pack_into('<II', opt, dd_at + 8 * 2, va, len(rsrc))
    if dotnet:
        struct.pack_into('<II', opt, dd_at + 8 * 14, va, 72)
    head = bytearray(0x80)
    head[0:2] = b'MZ'
    struct.pack_into('<I', head, 0x3c, 0x80)
    coff = struct.pack('<HHIIIHH', machine_id, 1, 0, 0, 0, opt_size, 0x22)
    raw_size = len(rsrc) + (-len(rsrc) % 0x200)
    section = struct.pack('<8sIIIIIIHHI', b'.rsrc', max(len(rsrc), 1), va, raw_size, raw_at,
                          0, 0, 0, 0, 0x40000040)
    out = bytes(head) + b'PE\0\0' + coff + bytes(opt) + section
    out += b'\0' * (raw_at - len(out))
    return out + rsrc + b'\0' * (raw_size - len(rsrc)) + trailer


def dos_program() -> bytes:
    data = bytearray(512)
    data[0:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0)          # no PE header
    return bytes(data)


def lnk(target: str, name: str = '', arguments: str = '', idlist_only: bool = False) -> bytes:
    """A Unicode .lnk to `target` (C:\\...), with LinkInfo, or with only an ID list."""
    flags = 0x80 | (0x4 if name else 0) | (0x20 if arguments else 0)
    flags |= 0x1 if idlist_only else 0x2
    header = struct.pack('<I16sII', 0x4c, bytes.fromhex('0114020000000000c000000000000046'),
                         flags, 0x20) + b'\0' * 24 + struct.pack('<IiIH', 0, 0, 1, 0) + b'\0' * 10
    body = b''
    if idlist_only:
        items = [struct.pack('<HBB16s', 20, 0x1f, 0x50, b'\x20\xd0\x4f\xe0\x3a\xea\x10\x69'
                             b'\xa2\xd8\x08\x00\x2b\x30\x30\x9d')]
        drive = target[:3].encode('ascii') + b'\0' * 20
        items.append(struct.pack('<HB', 3 + len(drive), 0x2f) + drive)
        parts = [p for p in target[3:].split('\\') if p]
        for i, part in enumerate(parts):
            short = (part[:8].upper().replace(' ', '') + '\0').encode('ascii')
            short += b'\0' * (len(short) % 2)
            longname = (part + '\0').encode('utf-16-le')
            ext = struct.pack('<HHI', 0, 9, 0xBEEF0004) + b'\0' * 8 + b'\x2e\x00' + \
                b'\0' * 18 + longname + b'\0\0'
            ext = struct.pack('<H', len(ext)) + ext[2:]
            kind = 0x32 if i == len(parts) - 1 else 0x31
            item = struct.pack('<BBIIH', kind, 0, 0, 0, 0x10 if kind == 0x31 else 0x20) + \
                short + ext
            items.append(struct.pack('<H', 2 + len(item)) + item)
        idlist = b''.join(items) + b'\0\0'
        body += struct.pack('<H', len(idlist)) + idlist
    else:
        volume = struct.pack('<IIII', 0x11, 3, 0, 0x10) + b'\0'
        base = target.encode('cp1252') + b'\0'
        header_size = 0x1c
        volume_at = header_size
        base_at = volume_at + len(volume)
        suffix_at = base_at + len(base)
        info = struct.pack('<IIIIIII', 0, header_size, 1, volume_at, base_at, 0, suffix_at)
        info += volume + base + b'\0'
        info = struct.pack('<I', len(info)) + info[4:]
        body += info
    for text in (name, arguments):
        if text:
            body += struct.pack('<H', len(text)) + text.encode('utf-16-le')
    return header + body + b'\0\0\0\0'
