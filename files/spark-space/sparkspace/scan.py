"""Scan a folder into a tree of sizes, in background threads.

- os.scandir with a few threads (lstat releases the GIL, so they overlap on a fast disk).
- Sizes are what the files take on the disk (st_blocks), not their length, so sparse files and
  tiny files count right. On btrfs this is the size before compression, and data shared
  between snapshots or reflinked copies counts in each copy: the total can differ from what the
  drive reports as used. The window says so.
- Never follows symlinks; a link counts as the link itself.
- A file with several hard links counts once, at the first place it's found.
- Doesn't cross into other mounts (another drive, /proc, a USB stick mounted inside) unless
  asked; those folders are listed, empty, with OTHER_FS set. Btrfs subvolumes that aren't
  mounted separately are part of the filesystem and are scanned.
- Folders it can't read are counted (and the first few hundred remembered), never fatal.
"""

import heapq
import os
import queue
import stat
import threading
import time
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from .kinds import KINDS, is_game_dir, kind_of

DIR = 1
UNREADABLE = 2      # the folder (or part of it) couldn't be read
OTHER_FS = 4        # a mount point of another filesystem: not scanned
LINK = 8            # a symbolic link (never followed)
SHARED = 16         # another hard link to a file already counted: size 0 here
SYSTEM = 32         # /proc, /sys, /dev, /run: not files on a disk

SYSTEM_DIRS = frozenset(('/proc', '/sys', '/dev', '/run'))
UNREADABLE_KEEP = 500


class Node:
    """A file or folder. size is bytes on disk for the whole subtree; count is the number of
    files in it (folders not counted)."""

    __slots__ = ('name', 'parent', 'size', 'count', 'children', 'flags', 'ordered')

    def __init__(self, name: str, parent: Optional['Node'], size: int = 0, flags: int = 0):
        self.name, self.parent, self.size, self.flags = name, parent, size, flags
        if flags & DIR:
            self.children: Optional[List['Node']] = []
            self.count = 0
        else:
            self.children = None
            self.count = 1
        self.ordered = False

    @property
    def is_dir(self) -> bool:
        return bool(self.flags & DIR)

    def path(self) -> str:
        parts = []
        node = self
        while node.parent is not None:
            parts.append(node.name)
            node = node.parent
        parts.append(node.name)          # the root's name is its full path
        return os.path.join(*reversed(parts))

    def sorted_children(self) -> List['Node']:
        """Biggest first (sorted once, on first use)."""
        if self.children is None:
            return []
        if not self.ordered:
            self.children.sort(key=lambda c: (-c.size, c.name))
            self.ordered = True
        return self.children

    def ancestors(self) -> List['Node']:
        """Root first, self last."""
        out = []
        node: Optional[Node] = self
        while node is not None:
            out.append(node)
            node = node.parent
        out.reverse()
        return out

    def __repr__(self) -> str:
        return f"Node({self.name!r}, {self.size}, dir={self.is_dir})"


class Scanner:
    """scanner = Scanner(path); scanner.start(); poll progress(); scanner.finished is set when
    it's done or cancelled; then scanner.root is the tree."""

    def __init__(self, root: str, threads: int = 4, one_filesystem: bool = True,
                 mount_targets: Optional[Set[str]] = None,
                 after: Optional[Callable[['Scanner'], None]] = None):
        self.root_path = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
        self.threads = max(1, threads)
        self.one_filesystem = one_filesystem
        if mount_targets is None:
            from .drives import mount_targets as read_targets
            mount_targets = read_targets()
        self.mounts = {os.path.normpath(m) for m in mount_targets} - {self.root_path}
        self.after = after
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.root: Optional[Node] = None
        self.unreadable: List[str] = []
        self.unreadable_count = 0
        self.skipped_mounts: List[str] = []
        self.current = ''
        self.started = self.elapsed = 0.0
        self._stats: List[List[int]] = [[0, 0, 0] for _ in range(self.threads)]
        self._queue: 'queue.Queue' = queue.Queue()
        self._pending = 0
        self._lock = threading.Lock()
        self._seen_links: Set[Tuple[int, int]] = set()
        self._dirs: List[Node] = []
        self._workers: List[threading.Thread] = []

    # ── control ──

    def start(self) -> 'Scanner':
        st = os.stat(self.root_path)                  # FileNotFoundError, PermissionError
        if not stat.S_ISDIR(st.st_mode):
            raise NotADirectoryError(self.root_path)
        self.root = Node(self.root_path, None, st.st_blocks * 512, DIR)
        self._dirs.append(self.root)
        self._pending = 1
        self._queue.put((self.root, self.root_path))
        self.started = time.monotonic()
        for i in range(self.threads):
            worker = threading.Thread(target=self._work, args=(i,), daemon=True,
                                      name=f'spark-space-scan-{i}')
            self._workers.append(worker)
            worker.start()
        return self

    def cancel(self) -> None:
        self.cancelled.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self.finished.wait(timeout)

    def progress(self) -> Tuple[int, int, int]:
        """(files, folders, bytes) so far; read without a lock, so approximate while running."""
        files = dirs = size = 0
        for f, d, s in self._stats:
            files += f
            dirs += d
            size += s
        return files, dirs, size

    # ── the work ──

    def _work(self, index: int) -> None:
        stats = self._stats[index]
        while True:
            item = self._queue.get()
            if item is None:
                return
            node, path = item
            if not self.cancelled.is_set():
                try:
                    self._scan_dir(node, path, stats)
                except Exception:              # noqa: BLE001  never leave the count hanging
                    node.flags |= UNREADABLE
            with self._lock:
                self._pending -= 1
                last = self._pending == 0
            if last:
                for _ in range(self.threads):
                    self._queue.put(None)
                self._finish()
                return

    def _note_unreadable(self, path: str) -> None:
        with self._lock:
            self.unreadable_count += 1
            if len(self.unreadable) < UNREADABLE_KEEP:
                self.unreadable.append(path)

    def _scan_dir(self, node: Node, path: str, stats: List[int]) -> None:
        try:
            it = os.scandir(path)
        except PermissionError:
            node.flags |= UNREADABLE
            self._note_unreadable(path)
            return
        except OSError:
            node.flags |= UNREADABLE
            self._note_unreadable(path)
            return
        self.current = path
        children = node.children
        mounts, one_fs = self.mounts, self.one_filesystem
        own = files = 0
        with it:
            while True:
                try:
                    entry = next(it)
                except StopIteration:
                    break
                except OSError:
                    node.flags |= UNREADABLE
                    self._note_unreadable(path)
                    break
                try:
                    st = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue                   # gone while we looked
                except OSError:
                    self._note_unreadable(entry.path)
                    continue
                mode = st.st_mode
                if stat.S_ISDIR(mode):
                    child_path = entry.path
                    if child_path in SYSTEM_DIRS:
                        children.append(Node(entry.name, node, 0, DIR | SYSTEM))
                        continue
                    if one_fs and child_path in mounts:
                        children.append(Node(entry.name, node, 0, DIR | OTHER_FS))
                        with self._lock:
                            self.skipped_mounts.append(child_path)
                        continue
                    child = Node(entry.name, node, st.st_blocks * 512, DIR)
                    children.append(child)
                    self._dirs.append(child)
                    with self._lock:
                        self._pending += 1
                    self._queue.put((child, child_path))
                    stats[1] += 1
                    continue
                size = st.st_blocks * 512
                flags = 0
                if stat.S_ISLNK(mode):
                    flags = LINK
                elif st.st_nlink > 1:
                    key = (st.st_dev, st.st_ino)
                    with self._lock:
                        if key in self._seen_links:
                            size, flags = 0, SHARED
                        else:
                            self._seen_links.add(key)
                children.append(Node(entry.name, node, size, flags))
                own += size
                files += 1
        node.size += own
        node.count += files
        stats[0] += files
        stats[2] += own

    def _finish(self) -> None:
        # every folder is after its parent in _dirs: add each one into its parent, last first
        for d in reversed(self._dirs):
            parent = d.parent
            if parent is not None:
                parent.size += d.size
                parent.count += d.count
        self._dirs = []
        self._seen_links = set()
        self.elapsed = time.monotonic() - self.started
        self.current = ''
        if self.after is not None and self.root is not None:
            try:
                self.after(self)
            except Exception:                  # noqa: BLE001
                pass
        self.finished.set()


def scan(path: str, **kw) -> Scanner:
    """Scan and wait (tests, --bench, --self-test)."""
    scanner = Scanner(path, **kw).start()
    scanner.wait()
    return scanner


# ── walking a finished tree ──

def iter_files(node: Node) -> Iterator[Tuple[Node, bool]]:
    """Every file below node, with whether it's inside a game library."""
    in_games = any(is_game_dir(a.name) for a in node.ancestors()[1:]) or \
        (node.parent is None and is_game_dir(os.path.basename(node.name)))
    stack = [(node, in_games)]
    while stack:
        current, games = stack.pop()
        if current.children is None:
            yield current, games
            continue
        for child in current.children:
            if child.children is None:
                yield child, games
            else:
                stack.append((child, games or is_game_dir(child.name)))


class Summary:
    __slots__ = ('kinds', 'largest', 'kind')

    def __init__(self):
        self.kinds: Dict[str, List[int]] = {k: [0, 0] for k in KINDS}   # kind -> [bytes, files]
        self.largest: List[Tuple[Node, str]] = []
        self.kind: Optional[str] = None


def summarize(node: Node, top: int = 300, kind: Optional[str] = None,
              cancelled: Optional[threading.Event] = None) -> Summary:
    """Totals by kind of file, and the `top` largest files (of `kind` if given), below node."""
    out = Summary()
    out.kind = kind
    heap: List[Tuple[int, int, Node, str]] = []
    n = 0
    for f, games in iter_files(node):
        n += 1
        if cancelled is not None and n % 20000 == 0 and cancelled.is_set():
            break
        k = kind_of(f.name, games)
        slot = out.kinds[k]
        slot[0] += f.size
        slot[1] += 1
        if kind is not None and k != kind:
            continue
        if len(heap) < top:
            heapq.heappush(heap, (f.size, id(f), f, k))
        elif f.size > heap[0][0]:
            heapq.heapreplace(heap, (f.size, id(f), f, k))
    out.largest = [(f, k) for _s, _i, f, k in sorted(heap, key=lambda x: -x[0])]
    return out


def find(root: Node, path: str) -> Optional[Node]:
    """The node for path, or None when it isn't in the tree."""
    path = os.path.normpath(path)
    base = root.name.rstrip(os.sep) or os.sep
    if path == base:
        return root
    if not path.startswith(base.rstrip(os.sep) + os.sep):
        return None
    node = root
    for part in path[len(base.rstrip(os.sep)) + 1:].split(os.sep):
        if node.children is None:
            return None
        node = next((c for c in node.children if c.name == part), None)
        if node is None:
            return None
    return node


def remove(node: Node) -> None:
    """Take node out of the tree (after it was moved to the Trash) and shrink its folders."""
    parent = node.parent
    if parent is None or parent.children is None:
        return
    try:
        parent.children.remove(node)
    except ValueError:
        return
    p: Optional[Node] = parent
    while p is not None:
        p.size -= node.size
        p.count -= node.count
        p = p.parent
    node.parent = None
