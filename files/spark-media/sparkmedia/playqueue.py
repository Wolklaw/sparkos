"""The play queue: what plays next, in what order, with shuffle and repeat. No GStreamer and
no Tk here, so it's tested on its own."""

import random
from typing import List, Optional, Sequence


class PlayQueue:
    def __init__(self):
        self.items: List[str] = []
        self.order: List[int] = []         # indexes into items, in play order
        self.pos = -1                      # where we are in order
        self.shuffle = False
        self.repeat = False

    # ── what's playing ──
    def __len__(self) -> int:
        return len(self.items)

    @property
    def index(self) -> Optional[int]:
        """Index into items of the current song."""
        return self.order[self.pos] if 0 <= self.pos < len(self.order) else None

    @property
    def current(self) -> Optional[str]:
        i = self.index
        return self.items[i] if i is not None else None

    def upcoming(self) -> List[int]:
        """Item indexes still to play after the current one, in order."""
        return self.order[self.pos + 1:] if self.pos >= 0 else list(self.order)

    def is_last(self) -> bool:
        return self.pos >= len(self.order) - 1

    # ── filling it ──
    def set(self, items: Sequence[str], start: int = 0) -> None:
        """Replace everything and start at items[start]."""
        self.items = list(items)
        start = max(0, min(start, len(self.items) - 1)) if self.items else -1
        if self.shuffle and self.items:
            rest = [i for i in range(len(self.items)) if i != start]
            random.shuffle(rest)
            self.order = [start] + rest
            self.pos = 0
        else:
            self.order = list(range(len(self.items)))
            self.pos = start

    def add(self, items: Sequence[str]) -> None:
        """At the end of the queue."""
        first = len(self.items)
        self.items.extend(items)
        new = list(range(first, len(self.items)))
        if self.shuffle:
            random.shuffle(new)
        self.order.extend(new)
        if self.pos < 0 and self.items:
            self.pos = 0

    def play_next(self, items: Sequence[str]) -> None:
        """Right after the current song, in the given order."""
        first = len(self.items)
        self.items.extend(items)
        new = list(range(first, len(self.items)))
        at = self.pos + 1 if self.pos >= 0 else 0
        self.order[at:at] = new
        if self.pos < 0 and self.items:
            self.pos = 0

    def remove(self, item_index: int) -> None:
        """Take one song out (by its index in items). Removing the current one leaves the
        position on the song that followed it."""
        if not 0 <= item_index < len(self.items):
            return
        where = self.order.index(item_index)
        del self.items[item_index]
        del self.order[where]
        self.order = [i - 1 if i > item_index else i for i in self.order]
        if where < self.pos:
            self.pos -= 1
        if self.pos >= len(self.order):
            self.pos = len(self.order) - 1

    def move(self, item_index: int, delta: int) -> None:
        """Move a song up (-1) or down (+1) in play order."""
        if item_index not in self.order:
            return
        where = self.order.index(item_index)
        to = max(0, min(len(self.order) - 1, where + delta))
        if to == where:
            return
        current = self.index
        self.order.insert(to, self.order.pop(where))
        if current is not None:
            self.pos = self.order.index(current)

    def clear(self) -> None:
        self.items, self.order, self.pos = [], [], -1

    def clear_upcoming(self) -> None:
        """Keep the current song, drop the rest."""
        current = self.current
        if current is None:
            self.clear()
        else:
            self.set([current])

    # ── moving through it ──
    def jump(self, item_index: int) -> Optional[str]:
        if item_index in self.order:
            self.pos = self.order.index(item_index)
        return self.current

    def next(self, wrap: Optional[bool] = None) -> Optional[str]:
        """The next song, or None at the end (wraps round with repeat)."""
        if not self.order:
            return None
        wrap = self.repeat if wrap is None else wrap
        if self.pos + 1 < len(self.order):
            self.pos += 1
        elif wrap:
            if self.shuffle and len(self.order) > 1:
                last = self.order[-1]
                random.shuffle(self.order)
                if self.order[0] == last:                  # don't play the same song twice
                    self.order[0], self.order[-1] = self.order[-1], self.order[0]
            self.pos = 0
        else:
            return None
        return self.current

    def prev(self) -> Optional[str]:
        if not self.order:
            return None
        self.pos = (self.pos - 1) % len(self.order) if self.repeat else max(0, self.pos - 1)
        return self.current

    def set_shuffle(self, on: bool) -> None:
        self.shuffle = on
        current = self.index
        if on:
            rest = [i for i in self.upcoming()]
            random.shuffle(rest)
            played = self.order[:self.pos + 1] if self.pos >= 0 else []
            self.order = played + rest
        else:
            self.order = list(range(len(self.items)))
            if current is not None:
                self.pos = current
