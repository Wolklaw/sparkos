"""The window's and the command line's side of the control socket: one JSON request per line,
one JSON reply per line, over $XDG_RUNTIME_DIR/spark-link/control.sock."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from . import APP_SLUG
from .config import control_path
from .text import t


class NotRunning(Exception):
    pass


class Control:
    def __init__(self, path: Optional[str] = None, timeout: float = 5.0):
        self.path = path or control_path()
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.buf = b''

    def _connect(self) -> None:
        if not hasattr(socket, 'AF_UNIX'):
            raise NotRunning(t('err.no_service'))
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.path)
        except OSError:
            sock.close()
            raise NotRunning(t('err.no_service')) from None
        self.sock, self.buf = sock, b''

    def request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in (0, 1):
            if self.sock is None:
                self._connect()
            try:
                self.sock.sendall((json.dumps(req) + '\n').encode('utf-8'))
                while b'\n' not in self.buf:
                    data = self.sock.recv(65536)
                    if not data:
                        raise ConnectionError('closed')
                    self.buf += data
                line, _, self.buf = self.buf.partition(b'\n')
                return json.loads(line)
            except (OSError, ConnectionError, ValueError):
                self.close()
                if attempt:
                    raise NotRunning(t('err.no_service')) from None
        raise NotRunning(t('err.no_service'))

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def running(self) -> bool:
        try:
            self.request({'cmd': 'status', 'peek': True})
            return True
        except NotRunning:
            return False


def start_service(wait: float = 5.0) -> str:
    """Start the background service: enable the systemd user unit so it also starts at every
    login, or (no systemd) run it detached. Returns '' or why it failed."""
    ctl = Control()
    if ctl.running():
        return ''
    why = ''
    systemctl = shutil.which('systemctl')
    started = False
    if systemctl and os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        done = subprocess.run([systemctl, '--user', 'enable', '--now', f'{APP_SLUG}.service'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        started = done.returncode == 0
        if not started:
            why = done.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] or ['']
            why = why[0]
    if not started:
        entry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'spark_link.py')
        try:
            subprocess.Popen([sys.executable, entry, '--service'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError as exc:
            return str(exc)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if ctl.running():
            ctl.close()
            return ''
        time.sleep(0.1)
    return why or t('err.no_service')
