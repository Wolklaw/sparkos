"""The control socket between the service and everything else (the window, `--save`,
`--status`): one JSON object per line in, one back, over a Unix socket in the runtime folder."""

import json
import os
import socket
import threading
from typing import Any, Callable, Dict, Optional

from .core import log, socket_path

MAX_LINE = 65536


def ask(command: str, timeout: float = 5.0, path: Optional[str] = None,
        **args) -> Optional[Dict[str, Any]]:
    """Send a command, return the reply; None when nothing is listening."""
    path = path or socket_path()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(path)
        client.sendall((json.dumps({'cmd': command, **args}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n') and len(data) < MAX_LINE:
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
        reply = json.loads(data.decode('utf-8'))
        return reply if isinstance(reply, dict) else None
    except (OSError, ValueError):
        return None
    finally:
        client.close()


class Server:
    """handler(command, args) -> dict, called on a thread per connection."""

    def __init__(self, handler: Callable[[str, Dict[str, Any]], Dict[str, Any]],
                 path: Optional[str] = None):
        self.handler = handler
        self.path = path or socket_path()
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        try:
            os.unlink(self.path)               # a leftover from a crash; the lock is the real guard
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(8)
        self.thread = threading.Thread(target=self._accept, daemon=True, name='clips-socket')
        self.thread.start()

    def _accept(self) -> None:
        while self.sock is not None:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        conn.settimeout(10)
        try:
            data = b''
            while not data.endswith(b'\n') and len(data) < MAX_LINE:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            try:
                request = json.loads(data.decode('utf-8'))
                command = str(request.pop('cmd'))
                reply = self.handler(command, request)
            except (ValueError, KeyError, AttributeError):
                reply = {'ok': False, 'error': 'bad request'}
            except Exception as exc:                # noqa: BLE001 - never kill the service
                log.exception("command failed")
                reply = {'ok': False, 'error': str(exc)}
            conn.sendall((json.dumps(reply) + '\n').encode())
        except OSError:
            pass
        finally:
            conn.close()

    def stop(self) -> None:
        sock, self.sock = self.sock, None
        if sock is not None:
            sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
