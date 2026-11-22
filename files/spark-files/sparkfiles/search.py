"""Ctrl+F: find files by name below a folder, in a worker thread. Results arrive in batches
so the first ones show at once; links to folders aren't followed (no loops), and hidden
folders are searched only when hidden files are shown."""

import os
import threading
from typing import Callable, List, Optional

from .listing import Entry, name_matcher, read_entry

LIMIT = 20000
BATCH = 200


class Search:
    def __init__(self, folder: str, text: str, show_hidden: bool,
                 on_batch: Callable[['Search', List[Entry]], None],
                 on_done: Callable[['Search'], None]):
        self.folder, self.text, self.show_hidden = folder, text, show_hidden
        self.on_batch, self.on_done = on_batch, on_done
        self.found = 0
        self.scanned_dirs = 0
        self.limited = False
        self.cancelled = threading.Event()
        self.done = False
        self.thread = threading.Thread(target=self._run, name='search', daemon=True)

    def start(self) -> 'Search':
        self.thread.start()
        return self

    def cancel(self) -> None:
        self.cancelled.set()

    def _run(self) -> None:
        match = name_matcher(self.text)
        batch: List[Entry] = []
        stack = [self.folder]
        try:
            while stack and not self.cancelled.is_set():
                folder = stack.pop()
                self.scanned_dirs += 1
                try:
                    with os.scandir(folder) as it:
                        children = list(it)
                except OSError:
                    continue
                children.sort(key=lambda d: d.name.casefold(), reverse=True)
                for de in children:
                    if self.cancelled.is_set():
                        break
                    hidden = de.name.startswith('.')
                    if hidden and not self.show_hidden:
                        continue
                    try:
                        is_dir = de.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False
                    if is_dir:
                        stack.append(de.path)
                    if match(de.name):
                        entry = read_entry(de.path)
                        if entry is not None:
                            batch.append(entry)
                            self.found += 1
                            if len(batch) >= BATCH:
                                self.on_batch(self, batch)
                                batch = []
                            if self.found >= LIMIT:
                                self.limited = True
                                self.cancelled.set()
                                break
        finally:
            if batch:
                self.on_batch(self, batch)
            self.done = True
            self.on_done(self)


def relative_folder(root: str, path: str) -> Optional[str]:
    parent = os.path.dirname(path)
    rel = os.path.relpath(parent, root)
    return '' if rel == '.' else rel
