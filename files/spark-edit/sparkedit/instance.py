"""One window: `spark-edit FILE` while Spark Edit is open opens FILE as a tab in that window
instead of starting a second copy (which would also fight over the session and the
autosaves). A Unix socket in $XDG_RUNTIME_DIR carries the request. This runs before tkinter
is imported, so handing over costs a few milliseconds."""

import os
import socket
from typing import Callable, List, Optional, Tuple

from . import APP_SLUG

Item = Tuple[str, int, int]


def socket_path() -> Optional[str]:
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime or not hasattr(socket, 'AF_UNIX') or os.name != 'posix':
        return None
    return os.path.join(runtime, f'{APP_SLUG}.sock')


def encode(items: List[Item]) -> bytes:
    lines = ['show'] + [f'open\t{path}\t{line}\t{col}' for path, line, col in items]
    return ('\n'.join(lines) + '\n\n').encode('utf-8', 'surrogateescape')


def decode(data: bytes) -> Tuple[bool, List[Item]]:
    show, items = False, []
    for line in data.decode('utf-8', 'surrogateescape').split('\n'):
        if line == 'show':
            show = True
        elif line.startswith('open\t'):
            parts = line.split('\t')
            if len(parts) == 4 and parts[1]:
                try:
                    items.append((parts[1], int(parts[2]), int(parts[3])))
                except ValueError:
                    pass
    return show, items


def hand_over(items: List[Item]) -> bool:
    """True if a running Spark Edit took the files (this one should then exit)."""
    path = socket_path()
    if not path or not os.path.exists(path):
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(path)
            s.sendall(encode(items))
            return s.recv(16).startswith(b'ok')
    except OSError:
        return False


class Listener:
    """Waits for requests and calls on_open (or on_show) from Tk's event loop."""

    def __init__(self, root, on_show: Callable[[], None],
                 on_open: Callable[[List[Item]], None]):
        self.root, self.on_show, self.on_open = root, on_show, on_open
        self.sock: Optional[socket.socket] = None
        self.path = socket_path()
        if not self.path:
            return
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)      # stale: hand_over() found no one there
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(self.path)
            os.chmod(self.path, 0o600)
            self.sock.listen(4)
            self.sock.setblocking(False)
            import tkinter
            root.tk.createfilehandler(self.sock, tkinter.READABLE, self._ready)
        except (OSError, AttributeError):
            self.close()

    def _ready(self, _sock, _mask):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            try:
                conn.settimeout(1.0)
                data = b''
                while not data.endswith(b'\n\n') and len(data) < 1 << 20:
                    more = conn.recv(65536)
                    if not more:
                        break
                    data += more
                show, items = decode(data)
                if show or items:
                    conn.sendall(b'ok\n')
                    if items:
                        self.root.after_idle(lambda: self.on_open(items))
                    else:
                        self.root.after_idle(self.on_show)
            except OSError:
                pass

    def close(self):
        if self.sock is not None:
            try:
                self.root.tk.deletefilehandler(self.sock)
            except Exception:     # noqa: BLE001
                pass
            self.sock.close()
            self.sock = None
            try:
                if self.path:
                    os.unlink(self.path)
            except OSError:
                pass
