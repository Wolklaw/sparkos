"""One window at a time: opening the Store again (or a .flatpakref, or an appstream:// link)
brings the open window to the front, on that app's page, instead of starting a second copy.
A Unix socket in $XDG_RUNTIME_DIR carries the request. This runs before tkinter is imported,
so handing over costs a few milliseconds. (Copied from Spark Monitor, with a target added.)"""

import os
import socket
from typing import Callable, Optional

from . import APP_SLUG


def socket_path() -> Optional[str]:
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime or not hasattr(socket, 'AF_UNIX') or os.name != 'posix':
        return None
    return os.path.join(runtime, f'{APP_SLUG}.sock')


def ask_running_to_show(target: str = '') -> bool:
    """True if another Spark Store took the request (this one should then exit)."""
    path = socket_path()
    if not path or not os.path.exists(path):
        return False
    message = ('open\t' + target if target else 'show') + '\n'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(path)
            s.sendall(message.encode('utf-8')[:4096])
            return s.recv(16).startswith(b'ok')
    except OSError:
        return False


class Listener:
    """Waits for "show" and "open <target>" requests and calls on_message from Tk's loop."""

    def __init__(self, root, on_message: Callable[[str], None]):
        self.root, self.on_message = root, on_message
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
                data = conn.recv(4096).decode('utf-8', errors='replace').strip()
                if data == 'show' or data.startswith('open\t'):
                    conn.sendall(b'ok\n')
                    target = data[5:] if data.startswith('open\t') else ''
                    self.root.after_idle(lambda: self.on_message(target))
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
