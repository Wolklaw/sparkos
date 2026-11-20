"""Read a Windows shortcut (.lnk): which program it opens, with which arguments. Installers
put these in the Start Menu, which is the best clue to which installed .exe is "the program".

Follows Microsoft's [MS-SHLLINK] layout: header, optional ID list, optional LinkInfo (the
local path), then counted strings (name, relative path, working folder, arguments, icon).
"""

import ntpath
import os
import struct
from dataclasses import dataclass
from typing import List, Optional

HAS_IDLIST, HAS_LINKINFO, HAS_NAME, HAS_RELPATH = 0x1, 0x2, 0x4, 0x8
HAS_WORKDIR, HAS_ARGS, HAS_ICON, IS_UNICODE = 0x10, 0x20, 0x40, 0x80
LNK_CLSID = bytes.fromhex('0114020000000000c000000000000046')


@dataclass
class Shortcut:
    target: str = ''          # Windows path, e.g. C:\Program Files\App\app.exe
    arguments: str = ''
    workdir: str = ''
    relative: str = ''
    icon: str = ''
    icon_index: int = 0


def read(path: str) -> Optional[Shortcut]:
    try:
        with open(path, 'rb') as f:
            data = f.read(1 << 20)
        return parse(data)
    except (OSError, struct.error, IndexError, ValueError):
        return None


def parse(data: bytes) -> Optional[Shortcut]:
    if len(data) < 0x4c or struct.unpack_from('<I', data, 0)[0] != 0x4c or \
            data[4:20] != LNK_CLSID:
        return None
    flags = struct.unpack_from('<I', data, 0x14)[0]
    out = Shortcut(icon_index=struct.unpack_from('<i', data, 0x38)[0])
    pos = 0x4c
    id_parts: List[str] = []
    if flags & HAS_IDLIST:
        size = struct.unpack_from('<H', data, pos)[0]
        id_parts = _idlist_path(data[pos + 2:pos + 2 + size])
        pos += 2 + size
    if flags & HAS_LINKINFO:
        size = struct.unpack_from('<I', data, pos)[0]
        out.target = _linkinfo_path(data[pos:pos + size])
        pos += size
    unicode = bool(flags & IS_UNICODE)
    strings = {}
    for flag, key in ((HAS_NAME, 'name'), (HAS_RELPATH, 'relative'), (HAS_WORKDIR, 'workdir'),
                      (HAS_ARGS, 'arguments'), (HAS_ICON, 'icon')):
        if flags & flag:
            count = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            width = 2 if unicode else 1
            raw = data[pos:pos + count * width]
            pos += count * width
            text = raw.decode('utf-16-le' if unicode else 'cp1252', 'replace')
            strings[key] = text.split(chr(0), 1)[0]       # Wine counts the terminator
    out.arguments = strings.get('arguments', '')
    out.workdir = strings.get('workdir', '')
    out.relative = strings.get('relative', '')
    out.icon = strings.get('icon', '')
    if not out.target and len(id_parts) >= 2:
        out.target = ntpath.join(*id_parts)
    return out


def _cstr(data: bytes, at: int, wide: bool) -> str:
    if wide:
        end = at
        while end + 1 < len(data) and data[end:end + 2] != b'\0\0':
            end += 2
        return data[at:end].decode('utf-16-le', 'replace')
    end = data.find(b'\0', at)
    return data[at:end if end >= 0 else len(data)].decode('cp1252', 'replace')


def _linkinfo_path(info: bytes) -> str:
    if len(info) < 0x1c:
        return ''
    header_size, link_flags = struct.unpack_from('<II', info, 4)
    _, base_off, _, suffix_off = struct.unpack_from('<IIII', info, 12)
    if not link_flags & 1:                 # no VolumeIDAndLocalBasePath
        return ''
    if header_size >= 0x24:
        base_u, suffix_u = struct.unpack_from('<II', info, 0x1c)
        base = _cstr(info, base_u, True) if base_u else ''
        suffix = _cstr(info, suffix_u, True) if suffix_u else ''
        if base:
            return base + suffix if base.endswith('\\') or not suffix else base + '\\' + suffix
    base = _cstr(info, base_off, False)
    suffix = _cstr(info, suffix_off, False) if suffix_off else ''
    if suffix and not base.endswith('\\'):
        base += '\\'
    return base + suffix


def _idlist_path(idlist: bytes) -> List[str]:
    """Best effort: the drive ('C:\\') and each folder/file item's long name."""
    parts: List[str] = []
    pos = 0
    while pos + 2 <= len(idlist):
        size = struct.unpack_from('<H', idlist, pos)[0]
        if size == 0:
            break
        item = idlist[pos:pos + size]
        pos += size
        if len(item) < 3:
            continue
        kind = item[2]
        if kind & 0x70 == 0x20 and len(item) > 4:         # a drive: "C:\"
            text = item[3:].split(b'\0', 1)[0].decode('ascii', 'replace')
            if len(text) >= 2 and text[1] == ':':
                parts = [text[:2] + '\\']
        elif kind & 0x70 == 0x30 and len(item) > 14:      # a file or folder
            short = item[14:].split(b'\0', 1)[0].decode('cp1252', 'replace')
            parts.append(_long_name(item) or short)
    return parts


def _long_name(item: bytes) -> str:
    """The long name in a file item's 0xBEEF0004 extension block."""
    at = item.find(b'\x04\x00\xef\xbe')
    if at < 4:
        return ''
    block = item[at - 4:]
    best = ''
    i = 8
    while i + 2 <= len(block):
        end = i
        while end + 1 < len(block) and block[end:end + 2] != b'\0\0':
            end += 2
        try:
            text = block[i:end].decode('utf-16-le')
        except UnicodeDecodeError:
            text = ''
        if len(text) > max(2, len(best)) and text.isprintable():
            best = text
        i = end + 2 if end > i else i + 2
    return best


def windows_to_unix(prefix: str, windows_path: str) -> Optional[str]:
    """'C:\\Program Files\\App\\app.exe' -> the real file inside the prefix, matching case
    the way Windows does (case-insensitively). None if it isn't there."""
    path = windows_path.strip().strip('"')
    if len(path) < 3 or path[1] != ':':
        return None
    # joined by hand: os.path.join would treat 'c:' as a drive on Windows (dev runs)
    drive = os.path.join(prefix, 'dosdevices') + os.sep + path[0].lower() + ':'
    if not os.path.exists(drive):
        if path[0].lower() != 'c':
            return None
        drive = os.path.join(prefix, 'drive_c')
    current = os.path.realpath(drive)
    for part in [p for p in path[2:].replace('/', '\\').split('\\') if p]:
        exact = os.path.join(current, part)
        if os.path.exists(exact):
            current = exact
            continue
        try:
            match = next((n for n in os.listdir(current) if n.lower() == part.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        current = os.path.join(current, match)
    return current


def unix_to_windows(prefix: str, unix_path: str) -> str:
    """A file inside the prefix's C: drive -> 'C:\\...'; anything else -> 'Z:\\...' (Wine
    maps Z: to the Linux root)."""
    real = os.path.realpath(unix_path)
    drive_c = os.path.realpath(os.path.join(prefix, 'drive_c'))
    if real == drive_c or real.startswith(drive_c + os.sep):
        rest = os.path.relpath(real, drive_c)
        return 'C:\\' + ('' if rest == '.' else rest.replace('/', '\\'))
    return 'Z:' + real.replace('/', '\\')
