"""Reading frame times from MangoHud and PresentMon CSVs, and the numbers worked out from them.

MangoHud (Linux): one or two lines about the system (os, cpu, gpu...), then a header with a
`frametime` column in milliseconds, one row per frame. It writes `<name>_summary.csv` next to it
when the recording ends.

PresentMon (Windows): a header with `MsBetweenPresents`, one row per present. A capture can hold
more than one program (a launcher, the overlay); only the program with the most frames counts.

The lows are the average of the slowest 1% (and 0.1%) frame times, turned into FPS. That is
lower than MangoHud's own "1% Min FPS" and PresentMon's percentile, which take a single frame
time at the 99th percentile; Spark Bench uses the same rule for every system, so the comparison
is fair either way."""

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MANGOHUD, PRESENTMON = 'mangohud', 'presentmon'
COLUMNS = {MANGOHUD: 'frametime', PRESENTMON: 'MsBetweenPresents'}
HEADER_LINES = 12            # how far down a header is looked for
MIN_FRAMES = 30              # fewer than this is not a recording


class FormatError(ValueError):
    pass


@dataclass
class Recording:
    path: str
    kind: str                            # MANGOHUD or PRESENTMON
    frametimes: List[float]              # milliseconds, one per frame, in order
    program: str = ''                    # the game's process name, as the recorder saw it
    info: Dict[str, str] = field(default_factory=dict)   # cpu, gpu, os... when the file has them


def _cells(line: str) -> List[str]:
    return [c.strip().strip('"') for c in line.rstrip('\r\n').split(',')]


def sniff(path: str) -> Optional[str]:
    """MANGOHUD, PRESENTMON or None, from the first lines only."""
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            for _ in range(HEADER_LINES):
                line = f.readline()
                if not line:
                    break
                cells = _cells(line)
                if COLUMNS[PRESENTMON] in cells:
                    return PRESENTMON
                if COLUMNS[MANGOHUD] in cells:
                    return MANGOHUD
    except OSError:
        return None
    return None


def _number(text: str) -> Optional[float]:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 and math.isfinite(value) else None


def read(path: str) -> Recording:
    """Every frame time in the file. Raises FormatError when it isn't a recording."""
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError as exc:
        raise FormatError(str(exc)) from exc
    kind, at = None, -1
    for i, line in enumerate(lines[:HEADER_LINES]):
        cells = _cells(line)
        for k in (PRESENTMON, MANGOHUD):
            if COLUMNS[k] in cells:
                kind, at = k, i
                break
        if kind:
            break
    if kind is None:
        raise FormatError("no frametime or MsBetweenPresents column")
    header = _cells(lines[at])
    col = header.index(COLUMNS[kind])
    info: Dict[str, str] = {}
    if kind == MANGOHUD and at >= 2:
        names, values = _cells(lines[at - 2]), _cells(lines[at - 1])
        info = {n: v for n, v in zip(names, values) if n and v}
    app_col = header.index('Application') if 'Application' in header else None
    rows = []
    for line in lines[at + 1:]:
        cells = _cells(line)
        if len(cells) <= col:
            continue
        value = _number(cells[col])
        if value is None:
            continue
        rows.append((cells[app_col] if app_col is not None and len(cells) > app_col else '',
                     value))
    program = ''
    if app_col is not None and rows:
        program = Counter(app for app, _ in rows).most_common(1)[0][0]
        rows = [r for r in rows if r[0] == program]
    if kind == MANGOHUD:
        program = program_from_name(os.path.basename(path))
    times = [v for _, v in rows]
    if len(times) < MIN_FRAMES:
        raise FormatError(f"only {len(times)} frames")
    return Recording(path=path, kind=kind, frametimes=times, program=program, info=info)


_STAMP = re.compile(r'_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})')


def program_from_name(name: str) -> str:
    """MangoHud names its logs <program>_YYYY-MM-DD_HH-MM-SS.csv."""
    base = os.path.splitext(name)[0]
    match = _STAMP.search(base)
    return base[:match.start()] if match else base


def stamp_from_name(name: str) -> Optional[str]:
    """'2026-11-22 05:03:31' from a MangoHud-style name, or None."""
    match = _STAMP.search(name)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4)}"


def game_key(program: str) -> str:
    """One key for one game on every system: 'Spider-Man2.exe' and 'Spider-Man2' are both
    'spiderman2'."""
    name = program.strip()
    if name.lower().endswith('.exe'):
        name = name[:-4]
    return re.sub(r'[^a-z0-9]', '', name.lower()) or 'unknown'


# ─── The numbers ──────────────────────────────────────────────

@dataclass
class Stats:
    seconds: float              # of the part that counts (after trimming)
    frames: int
    avg_fps: float
    low1: float                 # FPS from the average of the slowest 1% of frame times
    low01: float                # the same for the slowest 0.1%
    worst_ms: float             # the single slowest frame
    per_second: List[float]     # FPS in each second of the part that counts
    total_seconds: float        # the whole recording, before trimming


def low(frametimes: List[float], share: float) -> float:
    """FPS from the average of the slowest `share` of frame times (at least one frame)."""
    n = max(1, math.ceil(len(frametimes) * share))
    slowest = sorted(frametimes, reverse=True)[:n]
    return 1000.0 / (sum(slowest) / n)


def trimmed(frametimes: List[float], trim_start: float = 0.0,
            trim_end: float = 0.0) -> List[float]:
    """Frames that start at or after trim_start seconds and end by trim_end seconds before
    the end."""
    total = sum(frametimes) / 1000.0
    lo, hi = max(0.0, trim_start), total - max(0.0, trim_end)
    out, t = [], 0.0
    for ft in frametimes:
        start, t = t, t + ft / 1000.0
        if start >= lo - 1e-9 and t <= hi + 1e-9:
            out.append(ft)
    return out


def per_second(frametimes: List[float]) -> List[float]:
    """FPS in each whole second; a last part shorter than half a second is left out."""
    out: List[float] = []
    count, t, edge = 0, 0.0, 1.0
    for ft in frametimes:
        t += ft / 1000.0
        while t > edge + 1e-9:
            out.append(float(count))
            count, edge = 0, edge + 1.0
        count += 1
    rest = t - (edge - 1.0)
    if count and rest >= 0.5:
        out.append(count / rest)
    return out


def compute(frametimes: List[float], trim_start: float = 0.0,
            trim_end: float = 0.0) -> Stats:
    total = sum(frametimes) / 1000.0
    kept = trimmed(frametimes, trim_start, trim_end)
    if not kept:
        raise ValueError("the trim leaves no frames")
    seconds = sum(kept) / 1000.0
    return Stats(seconds=seconds, frames=len(kept), avg_fps=len(kept) / seconds,
                 low1=low(kept, 0.01), low01=low(kept, 0.001), worst_ms=max(kept),
                 per_second=per_second(kept), total_seconds=total)
