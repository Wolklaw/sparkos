"""Seeing and controlling a SparkOS desktop. Spark Connect asks `spark-share` on the target (over
SSH) to share the screen, reaches the one-time RDP server through an SSH -L forward on
127.0.0.1, and opens FreeRDP (Linux) or mstsc (Windows) on that forwarded port.

Nothing here opens a port on the network: the server listens on 127.0.0.1 on the target and our
end of the forward listens on 127.0.0.1 here. The password never goes into a command line on
this PC: FreeRDP reads its arguments from stdin, and mstsc gets it from the Credential Manager
for the length of the session and has it removed afterwards. See the README for what that still
leaves open."""

import getpass
import json
import os
import secrets
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .config import Machine
from .core import WINDOWS, log
from .transport import DONE, FAILED, NEEDS_PASSWORD, _NO_WINDOW

DENIED = 'denied'
REQUEST_WAIT_S = 75          # 30 s for the person to answer, then the server starts
FORWARD_WAIT_S = 10
HANDOFF_WAIT_S = 180         # time to type the sudo password in the terminal
LOCAL_HOST = '127.0.0.1'
REMOTE_TOOL = 'spark-share'
VIEWERS = ('sdl-freerdp', 'sdl-freerdp3', 'xfreerdp3', 'xfreerdp')


@dataclass
class ShareResult:
    outcome: str                 # DONE, DENIED, NEEDS_PASSWORD, FAILED
    reason: str = ''             # spark-share's reason (locked, no_session, denied, ...)
    message: str = ''


def new_token() -> str:
    return secrets.token_hex(8)


def free_port() -> int:
    with socket.socket() as s:
        s.bind((LOCAL_HOST, 0))
        return s.getsockname()[1]


def port_open(port: int) -> bool:
    try:
        with socket.create_connection((LOCAL_HOST, port), timeout=0.5):
            return True
    except OSError:
        return False


def request_remote(token: str, owner: str, pc: str, sudo: bool, handoff: bool = False) -> str:
    """The command run on the target, as one string for the remote shell."""
    parts = [REMOTE_TOOL, 'request', '--control', '--from', pc, '--owner', owner,
             '--token', token]
    if sudo:
        parts.append('--no-ask')
    if handoff:
        parts.append('--handoff')
    line = ' '.join(shlex.quote(p) for p in parts)
    return ('sudo ' + line) if sudo else line


def request_shown(machine_shown: str, sudo: bool) -> str:
    """What the confirmation prints: the command without our name or token."""
    return f"{machine_shown} {'sudo -n ' if sudo else ''}{REMOTE_TOOL} request --control" + \
        (" --no-ask" if sudo else "")


def parse_line(text: str) -> Optional[Dict[str, Any]]:
    """The one JSON line spark-share prints, or None for anything else (a login banner)."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and 'ok' in value:
                return value
    return None


def valid_info(info: Dict[str, Any]) -> bool:
    port = info.get('port')
    return (info.get('ok') is True and isinstance(port, int) and 0 < port < 65536
            and isinstance(info.get('user'), str) and isinstance(info.get('password'), str)
            and isinstance(info.get('fingerprint'), str)
            and info['fingerprint'].startswith('sha256:'))


# ─── the viewer ───────────────────────────────────────────────

def freerdp_binary() -> Optional[str]:
    for name in VIEWERS:
        path = shutil.which(name)
        if path:
            return path
    return None


def freerdp_args(machine_name: str, local_port: int, info: Dict[str, Any]) -> List[str]:
    """FreeRDP's arguments, one per line, for /args-from:stdin: the password is never in a
    command line. The certificate is the one spark-share made for this share, pinned."""
    return [f"/v:{LOCAL_HOST}:{local_port}", f"/u:{info['user']}", f"/p:{info['password']}",
            f"/cert:fingerprint:{info['fingerprint']},deny", f"/title:Spark Connect: {machine_name}",
            "/smart-sizing", "-wallpaper"]


def freerdp_argv(binary: str) -> List[str]:
    return [binary, '/args-from:stdin']


def rdp_file_text(local_port: int, user: str) -> str:
    return (f"full address:s:{LOCAL_HOST}:{local_port}\r\nusername:s:{user}\r\n"
            "prompt for credentials:i:0\r\nauthentication level:i:0\r\n"
            "screen mode id:i:1\r\nsmart sizing:i:1\r\n")


def cmdkey_add(user: str, password: str) -> List[str]:
    return ['cmdkey', f'/generic:TERMSRV/{LOCAL_HOST}', f'/user:{user}', f'/pass:{password}']


def cmdkey_delete() -> List[str]:
    return ['cmdkey', f'/delete:TERMSRV/{LOCAL_HOST}']


class Viewer:
    """A running FreeRDP or mstsc. poll() is None while it runs."""

    def __init__(self, proc: Optional[subprocess.Popen] = None, cleanup: Optional[Callable] = None):
        self.proc, self.cleanup = proc, cleanup

    def poll(self):
        return self.proc.poll() if self.proc else 0

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.cleanup:
            self.cleanup()
            self.cleanup = None


def launch_viewer(machine_name: str, local_port: int, info: Dict[str, Any]) -> Viewer:
    """Open the viewer. Raises OSError when there is none."""
    if WINDOWS:
        subprocess.run(cmdkey_add(info['user'], info['password']), check=True,
                       capture_output=True, creationflags=_NO_WINDOW)
        folder = tempfile.mkdtemp(prefix='spark-connect-')
        path = os.path.join(folder, 'screen.rdp')
        with open(path, 'w', encoding='ascii') as f:
            f.write(rdp_file_text(local_port, info['user']))

        def cleanup():
            subprocess.run(cmdkey_delete(), capture_output=True, creationflags=_NO_WINDOW)
            shutil.rmtree(folder, ignore_errors=True)
        try:
            return Viewer(subprocess.Popen(['mstsc', path]), cleanup)
        except OSError:
            cleanup()
            raise
    binary = freerdp_binary()
    if not binary:
        raise OSError("FreeRDP isn't installed (sdl-freerdp or xfreerdp)")
    proc = subprocess.Popen(freerdp_argv(binary), stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    try:
        assert proc.stdin is not None
        proc.stdin.write('\n'.join(freerdp_args(machine_name, local_port, info)) + '\n')
        proc.stdin.close()
    except OSError:
        pass
    return Viewer(proc)


# ─── one session ──────────────────────────────────────────────

class Share:
    """One screen share to one machine. connect() blocks until the viewer is open (or it
    failed) and is meant for a worker thread; alive(), elapsed() and stop() are quick."""

    def __init__(self, machine: Machine, transport, sudo: bool = False,
                 launcher: Optional[Callable] = None, terminal: Optional[Callable] = None,
                 owner: Optional[str] = None, pc: Optional[str] = None):
        self.machine, self.transport, self.sudo = machine, transport, sudo
        self.launcher = launcher or launch_viewer
        self.terminal = terminal
        self.owner = owner or _owner()
        self.pc = pc or socket.gethostname().split('.')[0]
        self.token = new_token()
        self.request: Optional[subprocess.Popen] = None
        self.forward: Optional[subprocess.Popen] = None
        self.viewer: Optional[Viewer] = None
        self.handoff = False
        self.started: Optional[float] = None
        self.ended: Optional[str] = None
        self.local_port = 0
        self._lock = threading.Lock()

    # — starting —
    def _spawn(self, argv: List[str], stdin=subprocess.PIPE) -> subprocess.Popen:
        log.info("share %s: starting %s", self.machine.name, os.path.basename(argv[0]))
        return subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                errors='replace', creationflags=_NO_WINDOW)

    def connect(self) -> ShareResult:
        try:
            first = self._ask_server()
            if isinstance(first, ShareResult):
                return first
            info = first
            return self._open(info)
        except Exception as exc:                  # the worker must always answer
            log.exception("share failed")
            self.stop()
            return ShareResult(FAILED, 'error', str(exc))

    def _ask_server(self):
        remote = request_remote(self.token, self.owner, self.pc, self.sudo)
        self.request = self._spawn(self.transport.base_argv(self.machine, mux=False) + [remote])
        lines: List[str] = []
        got = threading.Event()

        def read():
            assert self.request is not None and self.request.stdout is not None
            line = self.request.stdout.readline()
            lines.append(line)
            got.set()
        threading.Thread(target=read, daemon=True).start()
        if not got.wait(REQUEST_WAIT_S):
            self.stop()
            return ShareResult(FAILED, 'timeout', f"no answer in {REQUEST_WAIT_S} s")
        info = parse_line(lines[0]) if lines else None
        if info is None:
            err = ''
            try:
                self.request.wait(timeout=5)
                err = (self.request.stderr.read() or '').strip() if self.request.stderr else ''
            except subprocess.TimeoutExpired:
                pass
            self.stop()
            return self._failure(err)
        if not info.get('ok'):
            self.stop()
            reason = str(info.get('reason') or 'error')
            return ShareResult(DENIED if reason == 'denied' else FAILED, reason,
                               str(info.get('message') or ''))
        if not valid_info(info):
            self.stop()
            return ShareResult(FAILED, 'bad_reply', "spark-share's answer wasn't what Spark "
                               "Connect expects (an older or newer spark-share?)")
        return info

    def _failure(self, err: str) -> ShareResult:
        low = err.lower()
        if self.sudo and ('password is required' in low or 'terminal is required' in low
                          or 'askpass' in low):
            return ShareResult(NEEDS_PASSWORD, 'sudo_password', err)
        if 'command not found' in low or 'no such file' in low:
            return ShareResult(FAILED, 'no_tool', err)
        return ShareResult(FAILED, 'ssh', err.splitlines()[-1] if err else "no answer")

    def _open(self, info: Dict[str, Any]) -> ShareResult:
        self.local_port = free_port()
        forward = ['-N', '-o', 'ExitOnForwardFailure=yes',
                   '-L', f"{LOCAL_HOST}:{self.local_port}:{LOCAL_HOST}:{info['port']}"]
        self.forward = self._spawn(self.transport.base_argv(self.machine, mux=False,
                                                            opts=forward), stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + FORWARD_WAIT_S
        while time.monotonic() < deadline and not port_open(self.local_port):
            if self.forward.poll() is not None:
                break
            time.sleep(0.15)
        if not port_open(self.local_port):
            err = ''
            if self.forward.poll() is not None and self.forward.stderr:
                err = self.forward.stderr.read().strip()
            self.stop()
            return ShareResult(FAILED, 'forward', err.splitlines()[-1] if err else
                               "the forward to the screen didn't open")
        try:
            self.viewer = self.launcher(self.machine.name, self.local_port, info)
        except OSError as exc:
            self.stop()
            return ShareResult(FAILED, 'no_viewer', str(exc))
        self.started = time.monotonic()
        return ShareResult(DONE)

    # — the sudo-password path: a terminal runs the request, we collect its answer —
    def connect_handoff(self) -> ShareResult:
        """Used after sudo -n said it wants a password: the owner types it in a terminal that
        runs `sudo spark-share request ... --handoff`; we fetch the answer from a file there."""
        self.handoff = True
        remote = request_remote(self.token, self.owner, self.pc, True, handoff=True)
        if self.terminal is None or not self.terminal(self.machine, remote):
            return ShareResult(FAILED, 'no_terminal', '')
        deadline = time.monotonic() + HANDOFF_WAIT_S
        while time.monotonic() < deadline:
            done = subprocess.run(self.transport.base_argv(self.machine, mux=False) +
                                  [f"{REMOTE_TOOL} handoff {self.token}"], capture_output=True,
                                  text=True, encoding='utf-8', errors='replace', timeout=30,
                                  creationflags=_NO_WINDOW)
            info = parse_line(done.stdout) if done.returncode == 0 else None
            if info is not None:
                if not valid_info(info):
                    return ShareResult(FAILED, 'bad_reply', '')
                return self._open(info)
            time.sleep(2)
        return ShareResult(FAILED, 'timeout', "the password wasn't typed in time")

    # — running —
    def alive(self) -> bool:
        if self.ended or self.started is None:
            return False
        if self.viewer is not None and self.viewer.poll() is not None:
            return False
        if self.forward is not None and self.forward.poll() is not None:
            return False
        if self.request is not None and self.request.poll() is not None:
            return False
        return True

    def elapsed(self) -> float:
        return 0.0 if self.started is None else time.monotonic() - self.started

    def stop(self, why: str = 'stopped'):
        """End everything: the viewer, our forward, and the request (closing its stdin makes
        spark-share on the target close the server, the banner and the files)."""
        with self._lock:
            if self.ended:
                return
            self.ended = why
        if self.viewer is not None:
            self.viewer.stop()
        if self.request is not None:
            try:
                if self.request.stdin:
                    self.request.stdin.close()
            except OSError:
                pass
        if self.handoff:
            try:
                subprocess.run(self.transport.base_argv(self.machine, mux=False) +
                               [f"{REMOTE_TOOL} stop {self.token}"], capture_output=True,
                               timeout=20, creationflags=_NO_WINDOW)
            except (OSError, subprocess.SubprocessError):
                pass
        for proc in (self.forward, self.request):
            if proc is not None and proc.poll() is None:
                if proc is self.request:
                    try:
                        proc.wait(timeout=3)
                        continue
                    except subprocess.TimeoutExpired:
                        pass
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()


def _owner() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "someone"


def minutes(seconds: float) -> int:
    return int(seconds // 60)
