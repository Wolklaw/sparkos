"""One window at a time: pressing the volume applet again brings the open window to the front
instead of starting a second copy. A Unix socket in $XDG_RUNTIME_DIR carries the request.
This runs before tkinter is imported, so the second press costs a few milliseconds."""

import os
import socket
from typing import Callable, Optional

from . import APP_SLUG


def socket_path() -> Optional[str]:
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime or not hasattr(socket, 'AF_UNIX') or os.name != 'posix':
        return None
    return os.path.join(runtime, f'{APP_SLUG}.sock')


def ask_running_to_show() -> bool:
    """True if another Spark Audio took the request (this one should then exit)."""
    path = socket_path()
    if not path or not os.path.exists(path):
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(path)
            s.sendall(b'show\n')
            return s.recv(16).startswith(b'ok')
    except OSError:
        return False


class Listener:
    """Waits for "show" requests and calls on_show from Tk's event loop."""

    def __init__(self, root, on_show: Callable[[], None]):
        self.root, self.on_show = root, on_show
        self.sock: Optional[socket.socket] = None
        self.path = socket_path()
        if not self.path:
            return
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)      # stale: ask_running_to_show() found no one there
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(self.path)
            os.chmod(self.path, 0o600)
            self.sock.listen(4)
            self.sock.setblocking(False)
            import tkinter  # only in the first copy, once its window exists
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
                conn.settimeout(0.5)
                if conn.recv(16).startswith(b'show'):
                    conn.sendall(b'ok\n')
                    self.root.after_idle(self.on_show)
            except OSError:
                pass

    def close(self):
        if self.sock is not None:
            try:
                self.root.tk.deletefilehandler(self.sock)
            except (AttributeError, Exception):     # noqa: BLE001
                pass
            self.sock.close()
            self.sock = None
            try:
                if self.path:
                    os.unlink(self.path)
            except OSError:
                pass
