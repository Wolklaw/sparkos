"""Where the numbers come from: /proc and /sys, or a fake copy of them for tests and for
working on the interface away from Linux (SPARK_MONITOR_ROOT or --root).

Files are read with os.open/os.read: no buffered file objects, no text decoding until needed.
This app reads a few hundred small files a second, so that matters."""

import os
import signal
from typing import List, Optional

O_FLAGS = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)


def read_bytes(path: str, limit: int = 0) -> Optional[bytes]:
    """The whole file (or its first `limit` bytes), or None if it can't be read."""
    try:
        fd = os.open(path, O_FLAGS)
    except OSError:
        return None
    try:
        # /proc and /sys hand over everything they have in one read; a short read is the end
        size = min(limit, 65536) if limit else 65536
        data = os.read(fd, size)
        if len(data) < size:
            return data
        parts, total = [data], len(data)
        while not limit or total < limit:
            more = os.read(fd, 65536)
            if not more:
                break
            parts.append(more)
            total += len(more)
        data = b''.join(parts)
        return data[:limit] if limit else data
    except OSError:
        return None
    finally:
        os.close(fd)


def read_text(path: str) -> Optional[str]:
    data = read_bytes(path)
    return None if data is None else data.decode('utf-8', 'replace')


def read_line(path: str) -> Optional[str]:
    """The first line, stripped: for sysfs files that hold one value."""
    data = read_bytes(path, 4096)
    if data is None:
        return None
    return data.split(b'\n', 1)[0].decode('utf-8', 'replace').strip()


def read_int(path: str) -> Optional[int]:
    line = read_line(path)
    if not line:
        return None
    try:
        return int(line.split()[0], 0)
    except ValueError:
        return None


def listdir(path: str) -> List[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []


class Source:
    """Paths to /proc, /sys and the user's folders, under a root that is "/" on a real system."""

    def __init__(self, root: Optional[str] = None):
        root = root or os.environ.get('SPARK_MONITOR_ROOT') or '/'
        self.root = os.path.abspath(root) if root != '/' else '/'
        self.fake = self.root != '/'
        self.proc = os.path.join(self.root, 'proc')
        self.sys = os.path.join(self.root, 'sys')
        if self.fake:
            self.home = os.path.join(self.root, 'home')
            self.config_home = os.path.join(self.home, '.config')
            self.data_home = os.path.join(self.home, '.local', 'share')
            self.config_dirs = [self.path('etc/xdg')]
            self.data_dirs = [self.path('usr/local/share'), self.path('usr/share')]
            self.uid = 1000
        else:
            self.home = os.path.expanduser('~')
            self.config_home = os.environ.get('XDG_CONFIG_HOME') or \
                os.path.join(self.home, '.config')
            self.data_home = os.environ.get('XDG_DATA_HOME') or \
                os.path.join(self.home, '.local', 'share')
            self.config_dirs = [d for d in (os.environ.get('XDG_CONFIG_DIRS') or
                                            '/etc/xdg').split(':') if d]
            self.data_dirs = [d for d in (os.environ.get('XDG_DATA_DIRS') or
                                          '/usr/local/share:/usr/share').split(':') if d]
            self.uid = os.getuid() if hasattr(os, 'getuid') else 1000
        # Flatpak apps put their desktop entries and icons here
        for flat in (os.path.join(self.data_home, 'flatpak', 'exports', 'share'),
                     self.path('var/lib/flatpak/exports/share')):
            if flat not in self.data_dirs:
                self.data_dirs.append(flat)

    def path(self, rel: str) -> str:
        """A system path such as 'etc/xdg/autostart', under the root."""
        return os.path.join(self.root, rel.lstrip('/'))

    def host_path(self, path: str) -> str:
        """A path read from the data (a mount point, a unit file) mapped under the root."""
        return self.path(path) if self.fake else path

    def can_signal(self) -> bool:
        """Never send signals to the numbers in a fake tree: they're real PIDs on this PC."""
        return not self.fake and hasattr(signal, 'SIGKILL')
