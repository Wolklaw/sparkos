"""Valve's text KeyValues format (VDF/ACF), as Steam writes libraryfolders.vdf,
appmanifest_<id>.acf and localconfig.vdf.

    "AppState"
    {
        "appid"     "620"
        "name"      "Portal 2"
    }

Keys are case-insensitive in Steam, so lookups go through get(). Read only; nothing here writes.
"""

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
