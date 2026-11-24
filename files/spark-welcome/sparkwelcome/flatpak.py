"""Installing apps from Flathub for this user, one at a time, in the background.

No window code: the window polls `Installer.poll()` while something is installing and stops
polling when the queue is empty, so an idle Spark Welcome uses no CPU."""

import os
import queue
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set

from .core import log, run
from .strings import t

REMOTE = 'flathub'
REMOTE_URL = 'https://dl.flathub.org/repo/flathub.flatpakrepo'

# Spark Run's known apps that Spark Welcome can offer (the keys of sparkrun/catalog.py)
RUN_KEYS = ('amazon-music',)

QUEUED, WORKING, DONE, FAILED, CANCELLED = 'queued', 'working', 'done', 'failed', 'cancelled'

_PERCENT = re.compile(r'(\d{1,3})\s*%')
_STEP = re.compile(r'\b(Installing|Updating|Downloading|Uninstalling)\b[^\d]*(\d+)\s*/\s*(\d+)', re.I)


# ─── Commands ─────────────────────────────────────────────────

def install_cmd(app_id: str, flatpak: Sequence[str] = ('flatpak',)) -> List[str]:
    return [*flatpak, 'install', '--user', '--noninteractive', REMOTE, app_id]


def remotes_cmd(flatpak: Sequence[str] = ('flatpak',)) -> List[str]:
    return [*flatpak, 'remotes', '--user', '--columns=name']


def remote_add_cmd(flatpak: Sequence[str] = ('flatpak',)) -> List[str]:
    return [*flatpak, 'remote-add', '--user', '--if-not-exists', REMOTE, REMOTE_URL]


def run_cmd(key: str, spark_run: Sequence[str] = ('spark-run',)) -> List[str]:
    """Spark Run installs one of its known Windows apps (and does nothing if it is there)."""
    return [*spark_run, '--get', key, '--no-window']


def spark_cmd(source: str) -> List[str]:
    """An optional Spark app installs itself for this user from its source folder on this PC,
    as Spark Store's Install button does: no download, no password."""
    return ['bash', os.path.join(source, 'install.sh'), '--user']


def list_cmd(flatpak: Sequence[str] = ('flatpak',)) -> List[str]:
    return [*flatpak, 'list', '--app', '--columns=application']


def has_remote(remotes_output: str, name: str = REMOTE) -> bool:
    return any(line.split()[0] == name for line in remotes_output.splitlines() if line.split())


def parse_list(output: str) -> Set[str]:
    """`flatpak list --app --columns=application`: one app id per line (system and user)."""
    return {line.strip() for line in output.splitlines()
            if line.strip() and not line.startswith('Application')}


def installed_ids(flatpak: Sequence[str] = ('flatpak',)) -> Set[str]:
    found = web_installed() | run_installed(RUN_KEYS)
    code, out, err = run(list_cmd(flatpak), timeout=20)
    if code != 0:
        log.warning("flatpak list failed: %s", err.strip())
        return found
    return parse_list(out) | found


# ─── Web apps (services with no Linux app: a menu entry that opens them in the browser) ──

def applications_dir() -> str:
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local',
                                                           'share')
    return os.path.join(base, 'applications')


def web_entry_path(app_id: str) -> str:
    """web.amazon-music -> ~/.local/share/applications/dev.wolklaw.SparkWelcome.web.amazon-music.desktop"""
    return os.path.join(applications_dir(), f'dev.wolklaw.SparkWelcome.{app_id}.desktop')


def web_installed() -> Set[str]:
    try:
        names = os.listdir(applications_dir())
    except OSError:
        return set()
    prefix, suffix = 'dev.wolklaw.SparkWelcome.web.', '.desktop'
    return {n[len('dev.wolklaw.SparkWelcome.'):-len(suffix)] for n in names
            if n.startswith(prefix) and n.endswith(suffix)}


def run_entry_path(key: str) -> str:
    """Spark Run's menu entry for the app it installed under this key."""
    return os.path.join(applications_dir(), f'dev.wolklaw.SparkRun.app-{key}.desktop')


def run_installed(keys: Sequence[str]) -> Set[str]:
    return {f'run.{k}' for k in keys if os.path.isfile(run_entry_path(k))}


def web_entry(name: str, url: str) -> str:
    clean = lambda s: re.sub(r'[\r\n]+', ' ', s).strip()      # noqa: E731
    return '\n'.join([
        '[Desktop Entry]', 'Type=Application', f'Name={clean(name)}',
        f'Comment={clean(t("web.comment", name=name))}',
        f'Exec=xdg-open {url}', 'Icon=internet-web-browser', 'Terminal=false',
        'Categories=Network;AudioVideo;', f'X-SparkWelcome-Web={url}']) + '\n'


def install_web(app_id: str, name: str, url: str) -> str:
    """Write the menu entry. '' when done, else what went wrong."""
    if not re.match(r'^https://[^\s"\'\\]+$', url):
        return t('web.bad_address')
    path = web_entry_path(app_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
            f.write(web_entry(name, url))
        os.chmod(path + '.tmp', 0o644)
        os.replace(path + '.tmp', path)
    except OSError as exc:
        return str(exc)
    log.info("added the web app %s (%s)", app_id, url)
    return ''


def parse_progress(line: str):
    """(percent or None, (step, of) or None) from one line of flatpak's output."""
    percent = None
    found = _PERCENT.findall(line)
    if found:
        percent = max(0, min(100, int(found[-1])))
    step = _STEP.search(line)
    return percent, ((int(step.group(2)), int(step.group(3))) if step else None)


def error_from(lines: List[str]) -> str:
    """The line that explains a failed install: flatpak's 'error:' line, else the last line."""
    for line in reversed(lines):
        if line.lower().startswith('error:'):
            return line[6:].strip() or line
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return t('flatpak.no_reason')


# ─── The queue ────────────────────────────────────────────────

@dataclass
class Job:
    app_id: str
    name: str
    state: str = QUEUED
    percent: Optional[int] = None
    step: str = ''
    error: str = ''
    url: str = ''        # a web app: its address (no Flathub install)
    run: str = ''        # a Windows app: its key in Spark Run's catalogue
    source: str = ''     # an optional Spark app: its source folder (install.sh --user)


class Installer:
    """One background thread works through the queue. Thread-safe: the window calls
    add/retry/cancel and poll() from the Tk thread; the worker reports through a queue."""

    def __init__(self, flatpak: Sequence[str] = ('flatpak',),
                 on_change: Optional[Callable[[Job], None]] = None,
                 spark_run: Sequence[str] = ('spark-run',)):
        self.flatpak = list(flatpak)
        self.spark_run = list(spark_run)
        self.on_change = on_change
        self.jobs: Dict[str, Job] = {}
        self._todo: 'queue.Queue[str]' = queue.Queue()
        self._events: 'queue.Queue[Job]' = queue.Queue()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._remote_ok = False
        self._stop = False

    # called from the window
    def add(self, app_id: str, name: str, url: str = '', run: str = '',
            source: str = '') -> Job:
        with self._lock:
            job = self.jobs.get(app_id)
            if job and job.state in (QUEUED, WORKING, DONE):
                return job
            job = Job(app_id, name, url=url, run=run, source=source)
            self.jobs[app_id] = job
        self._todo.put(app_id)
        self._events.put(Job(**job.__dict__))
        self._start()
        return job

    def retry(self, app_id: str) -> Optional[Job]:
        job = self.jobs.get(app_id)
        if job and job.state in (FAILED, CANCELLED):
            return self.add(app_id, job.name, job.url, job.run, job.source)
        return job

    def busy(self) -> bool:
        with self._lock:
            return any(j.state in (QUEUED, WORKING) for j in self.jobs.values())

    def counts(self):
        """(finished, total) for the jobs in this round, for '2 of 5'."""
        with self._lock:
            total = len(self.jobs)
            finished = sum(1 for j in self.jobs.values() if j.state in (DONE, FAILED, CANCELLED))
        return finished, total

    def current(self) -> Optional[Job]:
        with self._lock:
            return next((j for j in self.jobs.values() if j.state == WORKING), None)

    def poll(self) -> List[Job]:
        """Changes since the last call, oldest first (copies, safe to keep)."""
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
        if self.on_change:
            for job in out:
                self.on_change(job)
        return out

    def stop(self) -> None:
        """Cancel what's queued and stop the running install (closing the window)."""
        self._stop = True
        with self._lock:
            for job in self.jobs.values():
                if job.state == QUEUED:
                    job.state = CANCELLED
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def wait(self, timeout: float = 60) -> bool:
        thread = self._thread
        if thread:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    # the worker
    def _start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._stop = False
            self._thread = threading.Thread(target=self._work, name='flatpak', daemon=True)
            self._thread.start()

    def _set(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            snapshot = Job(**job.__dict__)
        self._events.put(snapshot)

    def _work(self) -> None:
        while not self._stop:
            try:
                app_id = self._todo.get(timeout=0.5)
            except queue.Empty:
                with self._lock:
                    if self._todo.empty():
                        self._thread = None      # add() starts a new worker after this
                        return
                continue
            job = self.jobs.get(app_id)
            if job is None or job.state != QUEUED:
                continue
            self._set(job, state=WORKING, percent=None, step='', error='')
            if job.url:                          # a web app: a menu entry, nothing to download
                problem = install_web(job.app_id, job.name, job.url)
                self._set(job, state=FAILED if problem else DONE, error=problem,
                          percent=None if problem else 100)
                continue
            problem = '' if (job.run or job.source) else self._ensure_remote()
            if problem:
                self._set(job, state=FAILED, error=problem)
                continue
            self._install(job)
        with self._lock:
            self._thread = None

    def _ensure_remote(self) -> str:
        if self._remote_ok:
            return ''
        code, out, err = run(remotes_cmd(self.flatpak), timeout=30)
        if code == 0 and has_remote(out):
            self._remote_ok = True
            return ''
        log.info("adding the Flathub user remote")
        code, out, err = run(remote_add_cmd(self.flatpak), timeout=120)
        if code != 0:
            return t('flatpak.remote_failed', error=error_from((err + out).splitlines()))
        self._remote_ok = True
        return ''

    def _install(self, job: Job) -> None:
        if job.source:
            cmd = spark_cmd(job.source)
        elif job.run:
            cmd = run_cmd(job.run, self.spark_run)
        else:
            cmd = install_cmd(job.app_id, self.flatpak)
        log.info("running %s", ' '.join(cmd))
        lines: List[str] = []
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except OSError as exc:
            self._set(job, state=FAILED, error=t('flatpak.cant_run', error=exc))
            return
        self._proc = proc
        buf = b''
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, 'read1') else \
                os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb'[\r\n]', buf)
            buf = parts.pop()
            for raw in parts:
                self._line(job, raw, lines)
        if buf:
            self._line(job, buf, lines)
        code = proc.wait()
        proc.stdout.close()
        self._proc = None
        if self._stop and code != 0:
            self._set(job, state=CANCELLED, error=t('flatpak.stopped'))
        elif code == 0:
            self._set(job, state=DONE, percent=100, step='')
            log.info("installed %s", job.app_id)
        else:
            self._set(job, state=FAILED, error=error_from(lines))
            log.warning("installing %s failed: %s", job.app_id, job.error)

    def _line(self, job: Job, raw: bytes, lines: List[str]) -> None:
        line = raw.decode('utf-8', 'replace').strip()
        if not line:
            return
        lines.append(line)
        del lines[:-40]
        percent, step = parse_progress(line)
        changes = {}
        if percent is not None and percent != job.percent:
            changes['percent'] = percent
        if step:
            text = f"{step[0]}/{step[1]}"
            if text != job.step:
                changes['step'] = text
        if changes:
            self._set(job, **changes)
