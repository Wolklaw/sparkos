"""The install queue: installs, removals and updates run one at a time, in order, in one
background thread that exists only while there is work. The window reads each job's state
(progress, the last line flatpak printed, its error) when it is told something changed.

A failed job keeps flatpak's own error message, and can be retried."""

import queue
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, List, Optional

from . import flatpak
from .core import log

WAITING, RUNNING, DONE, FAILED, CANCELLED = 'waiting', 'running', 'done', 'failed', 'cancelled'
FINISHED = (DONE, FAILED, CANCELLED)

PERCENT = re.compile(r'(\d{1,3})\s?%')
STEP = re.compile(r'\b(\d{1,3})/(\d{1,3})\b')


@dataclass
class Job:
    kind: str                        # install, remove, update, update_all, install_ref,
                                     # spark_install, spark_remove, catalog
    app_id: str
    title: str                       # the app's name, for people
    steps: List[List[str]] = field(default_factory=list)
    flatpak: bool = True             # steps are flatpak arguments (else whole commands)
    func: Optional[Callable[[], str]] = None   # instead of steps: returns an error or ''
    needs_flathub: bool = False      # add the user's Flathub remote first if it's missing
    scope: str = 'user'
    id: int = 0
    state: str = WAITING
    progress: Optional[float] = None   # 0..1 when flatpak says, else None
    step_text: str = ''              # "2/3" when flatpak counts its steps
    line: str = ''                   # the last thing it printed
    error: str = ''
    output: Deque[str] = field(default_factory=lambda: deque(maxlen=80))
    started: float = 0.0
    ended: float = 0.0
    proc: Optional[subprocess.Popen] = None
    cancel_asked: bool = False

    @property
    def finished(self) -> bool:
        return self.state in FINISHED

    def copy(self) -> 'Job':
        return Job(kind=self.kind, app_id=self.app_id, title=self.title,
                   steps=[list(s) for s in self.steps], flatpak=self.flatpak, func=self.func,
                   needs_flathub=self.needs_flathub, scope=self.scope)


def error_text(lines: List[str]) -> str:
    """flatpak's own error lines ("error: ..."), else the last lines it printed. Its progress
    goes to stdout and its errors to stderr, so an error can land mid-line: cut it out."""
    errors = []
    for line in lines:
        at = line.lower().find('error:')
        if at >= 0:
            errors.append(line[at:].strip())
    if errors:
        return '\n'.join(dict.fromkeys(errors[-4:]))
    tail = [l for l in lines if l.strip()]
    return '\n'.join(tail[-5:])


class JobQueue:
    def __init__(self):
        self.jobs: List[Job] = []
        self.changes: 'queue.Queue[Job]' = queue.Queue()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_id = 1

    # — from the window —
    def add(self, job: Job) -> Job:
        with self._lock:
            for other in self.jobs:
                if not other.finished and other.kind == job.kind and \
                        other.app_id == job.app_id and other.scope == job.scope:
                    return other
            job.id = self._next_id
            self._next_id += 1
            self.jobs.append(job)
            log.info("queued #%d %s %s", job.id, job.kind, job.app_id)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, name='spark-store-queue',
                                                daemon=True)
                self._thread.start()
            self._wake.set()
        self.changes.put(job)
        return job

    def retry(self, job: Job) -> Job:
        with self._lock:
            if job in self.jobs and job.finished:
                self.jobs.remove(job)
        return self.add(job.copy())

    def cancel(self, job: Job) -> None:
        with self._lock:
            if job.state == WAITING:
                job.state, job.ended = CANCELLED, time.time()
            elif job.state == RUNNING:
                job.cancel_asked = True
                if job.proc is not None and job.proc.poll() is None:
                    try:
                        job.proc.terminate()
                    except OSError:
                        pass
        self.changes.put(job)

    def clear_finished(self) -> None:
        with self._lock:
            self.jobs = [j for j in self.jobs if not j.finished]

    def active(self) -> List[Job]:
        with self._lock:
            return [j for j in self.jobs if not j.finished]

    def current(self) -> Optional[Job]:
        with self._lock:
            return next((j for j in self.jobs if j.state == RUNNING), None)

    def for_app(self, app_id: str) -> Optional[Job]:
        """The newest job about this app (running, waiting or failed)."""
        with self._lock:
            for job in reversed(self.jobs):
                if job.app_id == app_id and job.state in (RUNNING, WAITING, FAILED):
                    return job
        return None

    def busy(self) -> bool:
        return bool(self.active())

    def drain(self) -> List[Job]:
        """Jobs that changed since the last call."""
        out = []
        while True:
            try:
                job = self.changes.get_nowait()
            except queue.Empty:
                return out
            if job not in out:
                out.append(job)

    def wait(self, timeout: float = 30) -> bool:
        """Block until every job has finished (tests and --self-test)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.busy():
                return True
            time.sleep(0.02)
        return False

    # — the worker —
    def _take(self) -> Optional[Job]:
        with self._lock:
            for job in self.jobs:
                if job.state == WAITING:
                    job.state, job.started = RUNNING, time.time()
                    return job
            self._thread = None if not any(j.state == WAITING for j in self.jobs) else \
                self._thread
            return None

    def _work(self) -> None:
        while True:
            job = self._take()
            if job is None:
                return
            self.changes.put(job)
            try:
                self._run(job)
            except Exception as exc:     # noqa: BLE001 - a job must never kill the queue
                log.exception("job #%d failed", job.id)
                job.error = job.error or str(exc)
                job.state = FAILED
            job.ended = time.time()
            job.proc = None
            log.info("job #%d %s %s -> %s%s", job.id, job.kind, job.app_id, job.state,
                     f": {job.error}" if job.error else "")
            self.changes.put(job)

    def _run(self, job: Job) -> None:
        if job.func is not None:
            job.progress = None
            error = job.func()
            job.error = error or ''
            job.state = FAILED if error else DONE
            return
        steps = list(job.steps)
        if job.needs_flathub and flatpak.REMOTE not in flatpak.remotes().get('user', []):
            steps.insert(0, flatpak.cmd_add_flathub())
        for argv in steps:
            if job.cancel_asked:
                job.state = CANCELLED
                return
            code = self._run_step(job, argv)
            if job.cancel_asked:
                job.state = CANCELLED
                return
            if code != 0:
                job.error = error_text(list(job.output)) or f"exit code {code}"
                job.state = FAILED
                return
        job.progress = 1.0
        job.state = DONE

    def _run_step(self, job: Job, argv: List[str]) -> int:
        base = flatpak.command() if job.flatpak else []
        if job.flatpak and not base:
            job.output.append("error: flatpak is not installed")
            return 127
        try:      # in the user's language: its errors are shown as they are
            proc = subprocess.Popen(base + argv, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    close_fds=True)
        except OSError as exc:
            job.output.append(f"error: {exc}")
            return 127
        job.proc = proc
        pending = b''
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, 'read1') else \
                proc.stdout.read(4096)
            if not chunk:
                break
            pending += chunk
            parts = re.split(rb'[\r\n]', pending)
            pending = parts.pop()
            for raw in parts:
                self._line(job, raw.decode('utf-8', errors='replace'))
        if pending:
            self._line(job, pending.decode('utf-8', errors='replace'))
        proc.stdout.close()
        return proc.wait()

    def _line(self, job: Job, text: str) -> None:
        text = text.strip()
        if not text:
            return
        changed = False
        percents = PERCENT.findall(text)
        if percents:
            value = min(100, int(percents[-1])) / 100
            if value != job.progress:
                job.progress = value
                changed = True
        step = STEP.search(text)
        if step and int(step.group(2)) <= 50 and step.group(0) != job.step_text:
            job.step_text = step.group(0)
            changed = True
        # progress redraws repeat the same line with a new number: keep one copy
        stem = PERCENT.sub('', text)
        if job.output and PERCENT.sub('', job.output[-1]) == stem:
            job.output[-1] = text
        else:
            job.output.append(text)
        if text != job.line:
            job.line = text
            changed = True
        if changed:
            self.changes.put(job)
