"""One Spark Media per person. The open window listens on a socket in $XDG_RUNTIME_DIR; a
second `spark-media FILE` (a double-click in a file manager) hands its files to it and exits, before
it has even made a window.

A socket left behind by a crash answers nobody: the next start finds it dead, removes it and
listens in its place. Linux only (Tk's file handlers); on Windows every start is its own."""

import json
import os
import socket
import stat
import tempfile
from typing import Callable, List, Optional

from .core import log

NAME = 'instance.sock'
CONNECT_TIMEOUT = 1.0
REPLY_TIMEOUT = 5.0


def socket_path() -> str:
    base = os.environ.get('XDG_RUNTIME_DIR')
    if base and os.path.isdir(base):
        folder = os.path.join(base, 'spark-media')
    else:
        # no runtime dir (a container, ssh without a session): a private folder in /tmp
        folder = os.path.join(tempfile.gettempdir(), f'spark-media-{os.getuid()}')
    os.makedirs(folder, mode=0o700, exist_ok=True)
    st = os.stat(folder)
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        os.chmod(folder, 0o700)
    return os.path.join(folder, NAME)


def supported() -> bool:
    return os.name != 'nt' and hasattr(socket, 'AF_UNIX') and \
        not os.environ.get('SPARK_MEDIA_NEW_INSTANCE')


def hand_off(paths: List[str], kind: Optional[str] = None) -> bool:
    """Give the files to the Spark Media that's already open. True if it took them (this
    process can exit); False if none is open, or it didn't answer."""
    if not supported():
        return False
    try:
        path = socket_path()
    except OSError:
        return False
    if not os.path.exists(path):
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect(path)
        sock.settimeout(REPLY_TIMEOUT)
        message = json.dumps({'paths': paths, 'kind': kind}).encode('utf-8') + b'\n'
        sock.sendall(message)
        reply = sock.recv(16)
        return reply.startswith(b'ok')
    except OSError as exc:
        log.info("no open Spark Media took the files (%s)", exc)
        return False
    finally:
        sock.close()


class Listener:
    """The open window's end. on_open(paths, kind) runs in Tk's thread."""

    def __init__(self, root, on_open: Callable[[List[str], Optional[str]], None]):
        self.root = root
        self.on_open = on_open
        self.sock: Optional[socket.socket] = None
        self.path: Optional[str] = None
        self._inode: Optional[int] = None

    def start(self) -> bool:
        if not supported():
            return False
        try:
            path = socket_path()
        except OSError as exc:
            log.warning("no place for the instance socket: %s", exc)
            return False
        if os.path.exists(path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(CONNECT_TIMEOUT)
            try:
                probe.connect(path)
                log.warning("another Spark Media is listening on %s; not taking over", path)
                return False
            except OSError:
                log.info("removing a stale socket left by a crash: %s", path)
                try:
                    os.unlink(path)
                except OSError:
                    pass
            finally:
                probe.close()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(path)
            os.chmod(path, 0o600)
            sock.listen(8)
            sock.setblocking(False)
        except OSError as exc:
            log.warning("could not listen on %s: %s", path, exc)
            sock.close()
            return False
        import tkinter
        self.root.tk.createfilehandler(sock, tkinter.READABLE, self._ready)
        self.sock, self.path = sock, path
        self._inode = os.stat(path).st_ino
        log.info("listening for files on %s", path)
        return True

    def _ready(self, _sock, _mask) -> None:
        try:
            conn, _addr = self.sock.accept()
        except OSError:
            return
        data = b''
        try:
            conn.settimeout(2.0)
            while not data.endswith(b'\n') and len(data) < 1_000_000:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            message = json.loads(data.decode('utf-8'))
            paths = [p for p in message.get('paths') or [] if isinstance(p, str)]
            kind = message.get('kind') if message.get('kind') in ('photo', 'video', 'music') \
                else None
            conn.sendall(b'ok\n')
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("a second start sent something unreadable: %s", exc)
            return
        finally:
            conn.close()
        log.info("handed over by a second start: %s", paths)
        self.on_open(paths, kind)

    def stop(self) -> None:
        if self.sock is None:
            return
        try:
            self.root.tk.deletefilehandler(self.sock)
        except Exception:      # noqa: BLE001 - the window may be gone already
            pass
        self.sock.close()
        self.sock = None
        try:
            # only our own socket: a newer Spark Media may have taken the name since
            if self.path and os.stat(self.path).st_ino == self._inode:
                os.unlink(self.path)
        except OSError:
            pass
