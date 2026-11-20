"""Find and replace over a buffer's text, with Python's own regular expressions (so the
syntax is the one people look up), and conversion between text offsets and Tk's line.column
indices. No Tk in here."""

import re
from bisect import bisect_right
from dataclasses import dataclass
from itertools import accumulate
from typing import List, Optional, Tuple

COUNT_LIMIT = 100000             # "100000+ matches" past this; counting stops there


@dataclass(frozen=True)
class Query:
    text: str
    case: bool = False           # match case
    word: bool = False           # whole words only
    regex: bool = False

    def compile(self) -> Optional['re.Pattern']:
        """The pattern, or None for an empty query. Raises re.error for a bad regex."""
        if not self.text:
            return None
        body = self.text if self.regex else re.escape(self.text)
        if self.word:
            body = rf'(?<!\w)(?:{body})(?!\w)'
        flags = re.MULTILINE | (0 if self.case else re.IGNORECASE)
        return re.compile(body, flags)

    def expand(self, match: 're.Match', replacement: str) -> str:
        """The replacement for one match: \\1 and \\g<name> work in regex mode."""
        return match.expand(replacement) if self.regex else replacement


class Lines:
    """Offsets in a string <-> (line, column), lines counted from 1 like Tk."""

    def __init__(self, text: str):
        self.starts: List[int] = [0]
        self.starts.extend(accumulate(len(line) + 1 for line in text.split('\n')))
        self.starts.pop()

    def to_pos(self, offset: int) -> Tuple[int, int]:
        line = bisect_right(self.starts, offset)
        return line, offset - self.starts[line - 1]

    def to_index(self, offset: int) -> str:
        line, col = self.to_pos(offset)
        return f'{line}.{col}'

    def to_offset(self, line: int, col: int) -> int:
        line = max(1, min(line, len(self.starts)))
        return self.starts[line - 1] + col


def find_next(pattern: 're.Pattern', text: str, offset: int,
              wrap: bool = True) -> Optional[Tuple[int, int]]:
    """The first match at or after offset (a match that starts at offset and is empty is
    skipped, so repeated Find next moves on), wrapping to the top."""
    m = pattern.search(text, offset)
    if m and m.end() == m.start() == offset:
        m = pattern.search(text, offset + 1) if offset < len(text) else None
    if not m and wrap:
        m = pattern.search(text, 0)
    return m.span() if m else None


def find_prev(pattern: 're.Pattern', text: str, offset: int,
              wrap: bool = True) -> Optional[Tuple[int, int]]:
    """The last match that ends before offset (or starts before it), wrapping to the end."""
    best = None
    for m in pattern.finditer(text, 0, offset):
        if m.start() < offset:
            best = m.span()
    if best is None and wrap:
        for m in pattern.finditer(text, offset):
            best = m.span()
    return best


def count(pattern: 're.Pattern', text: str, limit: int = COUNT_LIMIT) -> Tuple[int, bool]:
    """(number of matches, stopped at the limit?)"""
    n = 0
    for _ in pattern.finditer(text):
        n += 1
        if n >= limit:
            return n, True
    return n, False


def index_of(pattern: 're.Pattern', text: str, span: Tuple[int, int],
             limit: int = COUNT_LIMIT) -> int:
    """Which match (from 1) this span is."""
    n = 0
    for m in pattern.finditer(text, 0, span[0] + max(1, span[1] - span[0])):
        n += 1
        if m.start() >= span[0] or n >= limit:
            break
    return n


def replacements(query: Query, pattern: 're.Pattern', text: str,
                 replacement: str) -> List[Tuple[int, int, str]]:
    """Every (start, end, new text) for Replace all, first to last."""
    out = []
    for m in pattern.finditer(text):
        out.append((m.start(), m.end(), query.expand(m, replacement)))
    return out
