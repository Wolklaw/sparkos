"""The replay buffer on disk (in RAM, on tmpfs): one-second MPEG-TS pieces named
piece-<number>.ts, written by splitmuxsink. Which pieces to keep, which cover the last N
seconds, and how much memory that takes. Pure functions over (number, mtime, size) records, so
the tests need no GStreamer."""

import os
import re
from typing import List, NamedTuple, Optional, Sequence

PIECE_SECONDS = 1.0
PATTERN = 'piece-%08d.ts'
_NAME = re.compile(r'^piece-(\d{8})\.ts$')
MARGIN = 4                       # seconds kept beyond the buffer, so a save never loses its start
AUDIO_KBPS = 128


class Piece(NamedTuple):
    number: int
    path: str
    mtime: float
    size: int


def list_pieces(folder: str) -> List[Piece]:
    """The pieces in the folder, oldest first."""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        m = _NAME.match(name)
        if not m:
            continue
        path = os.path.join(folder, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append(Piece(int(m.group(1)), path, st.st_mtime, st.st_size))
    out.sort(key=lambda p: p.number)
    return out


def to_prune(pieces: Sequence[Piece], seconds: int, now: float, margin: int = MARGIN) -> List[Piece]:
    """Pieces older than the buffer length (plus a margin). The newest piece is never in the
    list, whatever its age: it is the one being written."""
    if not pieces:
        return []
    newest = pieces[-1].number
    limit = now - seconds - margin
    return [p for p in pieces if p.number != newest and p.mtime < limit]


def prune(folder: str, seconds: int, now: float) -> int:
    """Delete the old pieces; returns how many."""
    gone = 0
    for p in to_prune(list_pieces(folder), seconds, now):
        try:
            os.remove(p.path)
            gone += 1
        except OSError:
            pass
    return gone


def clear(folder: str) -> None:
    for p in list_pieces(folder):
        try:
            os.remove(p.path)
        except OSError:
            pass


def cover(pieces: Sequence[Piece], seconds: int) -> List[Piece]:
    """The pieces that hold the last `seconds` seconds, oldest first: that many pieces
    counting the newest one, which is still being written while the recorder runs. Only
    pieces in an unbroken run of numbers count: a gap means the buffer was restarted, and
    what is before it is a different recording."""
    if not pieces or seconds <= 0:
        return []
    want = int(seconds + 0.999)
    run: List[Piece] = [pieces[-1]]
    for p in reversed(pieces[:-1]):
        if len(run) >= want:
            break
        if p.number != run[0].number - 1:
            break
        run.insert(0, p)
    return run


def seconds_held(pieces: Sequence[Piece]) -> float:
    """How much the buffer holds now (the unbroken run at the end), in seconds."""
    if not pieces:
        return 0.0
    n = 1
    for a, b in zip(reversed(pieces[:-1]), reversed(pieces)):
        if b.number - a.number != 1:
            break
        n += 1
    return n * PIECE_SECONDS


def estimate_bytes(seconds: int, video_mbps: float, audio_tracks: int = 1) -> int:
    """About how much RAM `seconds` of buffer takes: video at the bitrate cap, audio, the
    MPEG-TS wrapping (about 6 %), and the margin of extra pieces."""
    bits = (video_mbps * 1_000_000 + audio_tracks * AUDIO_KBPS * 1000) * (seconds + MARGIN)
    return int(bits / 8 * 1.06)


def free_bytes(folder: str) -> Optional[int]:
    """Free space on the filesystem holding the folder (RAM, for /dev/shm)."""
    path = folder
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return st.f_bavail * st.f_frsize


def too_big(estimate: int, free: Optional[int]) -> bool:
    """The brief's rule: refuse a buffer that would use more than a quarter of what's free."""
    return free is not None and estimate > free // 4


def used_bytes(pieces: Sequence[Piece]) -> int:
    return sum(p.size for p in pieces)
