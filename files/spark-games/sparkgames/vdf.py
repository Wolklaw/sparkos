"""Valve's text KeyValues format (VDF/ACF), as Steam writes libraryfolders.vdf,
appmanifest_<id>.acf and localconfig.vdf.

    "AppState"
    {
        "appid"     "620"
        "name"      "Portal 2"
    }

Keys are case-insensitive in Steam, so lookups go through get(). Read only; nothing here writes
Steam's files. The binary form Steam uses for shortcuts.vdf is at the end.
"""

import struct
from typing import Any, Dict, List, Optional, Tuple

BACKSLASH = chr(92)
ESCAPES = {'n': '\n', 't': '\t', BACKSLASH: BACKSLASH, '"': '"'}
SPACE = ' \t\r\n' + chr(0xFEFF)          # whitespace, and a byte-order mark at the start


class VDFError(ValueError):
    pass


def _tokens(text: str) -> List[Tuple[str, str]]:
    """('s', string) for keys and values, ('{', '') and ('}', '') for blocks."""
    out: List[Tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ' \t\r\n﻿':
            i += 1
        elif c == '/' and text.startswith('//', i):
            end = text.find('\n', i)
            i = n if end < 0 else end + 1
        elif c == '{' or c == '}':
            out.append((c, ''))
            i += 1
        elif c == '[':                       # a platform condition like [$WIN32]: ignored
            end = text.find(']', i)
            if end < 0:
                raise VDFError("unclosed [condition]")
            i = end + 1
        elif c == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise VDFError("unclosed string")
                c = text[i]
                if c == BACKSLASH and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append(ESCAPES.get(nxt, BACKSLASH + nxt))
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            out.append(('s', ''.join(buf)))
        else:                                # an unquoted word
            start = i
            while i < n and text[i] not in ' \t\r\n{}"':
                i += 1
            out.append(('s', text[start:i]))
    return out


def loads(text: str) -> Dict[str, Any]:
    """Parse VDF text into nested dicts of strings. A repeated key keeps its last value."""
    tokens = _tokens(text)
    root: Dict[str, Any] = {}
    stack: List[Dict[str, Any]] = [root]
    i = 0
    while i < len(tokens):
        kind, value = tokens[i]
        if kind == '}':
            if len(stack) == 1:
                raise VDFError("unexpected }")
            stack.pop()
            i += 1
            continue
        if kind == '{':
            raise VDFError("block without a key")
        if i + 1 >= len(tokens):
            raise VDFError(f"key {value!r} has no value")
        nkind, nvalue = tokens[i + 1]
        if nkind == '{':
            child: Dict[str, Any] = {}
            stack[-1][value] = child
            stack.append(child)
        elif nkind == 's':
            stack[-1][value] = nvalue
        else:
            raise VDFError(f"key {value!r} followed by }}")
        i += 2
    if len(stack) != 1:
        raise VDFError("unclosed {")
    return root


def load(path: str) -> Dict[str, Any]:
    with open(path, encoding='utf-8', errors='replace') as f:
        return loads(f.read())


def get(data: Any, *keys: str, default: Any = None) -> Any:
    """data[k1][k2]... matching keys without regard to case."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        if key in data:
            data = data[key]
            continue
        low = key.lower()
        for k, v in data.items():
            if k.lower() == low:
                data = v
                break
        else:
            return default
    return data


def to_int(value: Optional[Any], default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# ─── The binary form (shortcuts.vdf) ──────────────────────────
#
# Steam keeps non-Steam shortcuts in userdata/<id>/config/shortcuts.vdf as binary KeyValues:
# one type byte, the key as a NUL-terminated string, then the value. 0x00 opens a block, 0x08
# closes one; 0x01 is a string, 0x02 a 32-bit int, 0x03 a float, 0x07 a 64-bit int.

def loads_binary(data: bytes) -> Dict[str, Any]:
    pos = 0

    def cstring() -> str:
        nonlocal pos
        end = data.find(b'\x00', pos)
        if end < 0:
            raise VDFError("binary VDF: unterminated string")
        text = data[pos:end].decode('utf-8', errors='replace')
        pos = end + 1
        return text

    def block(top: bool = False) -> Dict[str, Any]:
        nonlocal pos
        out: Dict[str, Any] = {}
        while True:
            if pos >= len(data):
                if top:                  # some writers leave out the last 0x08
                    return out
                raise VDFError("binary VDF: ends inside a block")
            kind = data[pos]
            pos += 1
            if kind == 0x08:
                return out
            key = cstring()
            if kind == 0x00:
                out[key] = block()
            elif kind == 0x01:
                out[key] = cstring()
            elif kind in (0x02, 0x03, 0x07):
                size, fmt = {0x02: (4, '<i'), 0x03: (4, '<f'), 0x07: (8, '<Q')}[kind]
                if pos + size > len(data):
                    raise VDFError("binary VDF: ends inside a number")
                out[key] = struct.unpack_from(fmt, data, pos)[0]
                pos += size
            else:
                raise VDFError(f"binary VDF: unknown type {kind:#x} at byte {pos - 1}")

    return block(top=True)


def read_binary(data: bytes, pos: int, strings: Optional[List[str]] = None
                ) -> Tuple[Dict[str, Any], int]:
    """One binary KeyValues block starting at pos, as Steam's appinfo.vdf and packageinfo.vdf
    hold them: (the block, where it ends). Newer appinfo.vdf keeps its keys in a string table
    at the end of the file; strings is that table, and each key is then a 4-byte index."""
    out: Dict[str, Any] = {}
    try:
        while True:
            kind = data[pos]
            pos += 1
            if kind in (0x08, 0x0b):
                return out, pos
            if strings is not None:
                key = strings[struct.unpack_from('<I', data, pos)[0]]
                pos += 4
            else:
                end = data.index(b'\x00', pos)
                key = data[pos:end].decode('utf-8', errors='replace')
                pos = end + 1
            if kind == 0x00:
                out[key], pos = read_binary(data, pos, strings)
            elif kind == 0x01:
                end = data.index(b'\x00', pos)
                out[key] = data[pos:end].decode('utf-8', errors='replace')
                pos = end + 1
            elif kind in (0x02, 0x04, 0x06):            # int32, pointer, colour
                out[key] = struct.unpack_from('<i', data, pos)[0]
                pos += 4
            elif kind == 0x03:
                out[key] = struct.unpack_from('<f', data, pos)[0]
                pos += 4
            elif kind in (0x07, 0x0a):                  # uint64, int64
                out[key] = struct.unpack_from('<Q' if kind == 0x07 else '<q', data, pos)[0]
                pos += 8
            else:
                raise VDFError(f"binary VDF: unknown type {kind:#x} at byte {pos - 1}")
    except (IndexError, ValueError, struct.error) as exc:
        if isinstance(exc, VDFError):
            raise
        raise VDFError(f"binary VDF: cut short near byte {pos}") from exc


def load_binary(path: str) -> Dict[str, Any]:
    with open(path, 'rb') as f:
        return loads_binary(f.read())


def dumps_binary(data: Dict[str, Any]) -> bytes:
    """The reverse, for the tests' fixtures (Spark Games never writes Steam's files)."""
    out = bytearray()
    for key, value in data.items():
        name = key.encode('utf-8') + b'\x00'
        if isinstance(value, dict):
            out += b'\x00' + name + dumps_binary(value)
        elif isinstance(value, str):
            out += b'\x01' + name + value.encode('utf-8') + b'\x00'
        elif isinstance(value, int):
            out += b'\x02' + name + struct.pack('<i', value)
        else:
            raise TypeError(f"can't write {type(value).__name__} to binary VDF")
    return bytes(out) + b'\x08'
