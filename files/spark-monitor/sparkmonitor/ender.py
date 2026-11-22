"""End task: ask politely (SIGTERM), wait, then force it (SIGKILL) if it's still running.

pidfds (Linux 5.3+) pin each process, so a PID that is reused by a new process while we wait
is never signalled by mistake. Without them, the start time from /proc/<pid>/stat does it."""

import errno
import os
import select
import signal
import time
from typing import Callable, Dict, Iterable, List, Optional

from .source import Source, read_bytes

RUNNING, ENDED, FORCED, FAILED, PARTLY = 'running', 'ended', 'forced', 'failed', 'partly'


def _start_time(src: Source, pid: int) -> Optional[int]:
    data = read_bytes(f'{src.proc}/{pid}/stat')
    if not data:
        return None
    fields = data[data.rfind(b')') + 2:].split()
    if fields[0] == b'Z':
        return None                       # a zombie has exited; it only waits to be reaped
    return int(fields[19])


class Ender:
    """Ends a set of processes without blocking: call poll() every few hundred ms until it
    returns something other than RUNNING."""

    def __init__(self, src: Source, pids: Iterable[int], grace: float = 5.0,
                 more: Optional[Callable[[], List[int]]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.src, self.grace, self.more, self.clock = src, grace, more, clock
        self.pids = [p for p in dict.fromkeys(pids) if p != os.getpid()]
        self.handles: Dict[int, object] = {}    # pid -> pidfd, or start time
        self.denied: List[int] = []
        self.deadline = 0.0
        self.killed = False
        self.result = RUNNING

    def _open(self, pid: int) -> bool:
        if pid in self.handles:
            return True
        if hasattr(os, 'pidfd_open'):
            try:
                self.handles[pid] = ('fd', os.pidfd_open(pid))
                return True
            except OSError as exc:
                if exc.errno == errno.ESRCH:
                    return False
        start = _start_time(self.src, pid)
        if start is None:
            return False
        self.handles[pid] = ('start', start)
        return True

    def _send(self, pid: int, sig: int) -> None:
        kind, handle = self.handles[pid]
        try:
            if kind == 'fd':
                signal.pidfd_send_signal(handle, sig)
            elif kind == 'start' and _start_time(self.src, pid) == handle:
                os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            if pid not in self.denied:
                self.denied.append(pid)

    def _alive(self, pid: int) -> bool:
        kind, handle = self.handles[pid]
        if kind == 'fd':
            # a pidfd becomes readable when the process exits
            ready, _, _ = select.select([handle], [], [], 0)
            return not ready
        if kind == 'start':
            return _start_time(self.src, pid) == handle
        return False

    def start(self) -> str:
        if not self.src.can_signal():
            self.result = FAILED
            return self.result
        for pid in self.pids:
            if self._open(pid):
                self._send(pid, signal.SIGTERM)
        self.deadline = self.clock() + self.grace
        return self.poll()

    def alive(self) -> List[int]:
        return [p for p in self.handles if p not in self.denied and self._alive(p)]

    def poll(self) -> str:
        if self.result != RUNNING:
            return self.result
        living = self.alive()
        if living and not self.killed and self.clock() >= self.deadline:
            # still here after the grace period: force it, and anything it started meanwhile
            self.killed = True
            for pid in (self.more() if self.more else []):
                if pid != os.getpid() and self._open(pid):
                    living.append(pid)
            for pid in dict.fromkeys(living):
                self._send(pid, signal.SIGKILL)
            living = self.alive()
            if living:
                return RUNNING           # SIGKILL takes a moment to land
        if living:
            if self.killed and self.clock() >= self.deadline + 3:
                self.result = PARTLY     # stuck in the kernel (state D); nothing more to do
                self.close()
            return self.result
        if self.denied and len(self.denied) == len(self.handles):
            self.result = FAILED
        elif self.denied:
            self.result = PARTLY
        else:
            self.result = FORCED if self.killed else ENDED
        self.close()
        return self.result

    def close(self) -> None:
        for kind, handle in self.handles.values():
            if kind == 'fd':
                try:
                    os.close(handle)
                except OSError:
                    pass
        self.handles = {pid: ('gone', None) for pid in self.handles}

    def __del__(self):
        try:
            self.close()
        except Exception:     # noqa: BLE001
            pass
