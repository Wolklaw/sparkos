"""Installs, updates and verifies, which run in a helper process (spark-games --job <spec>)
so the window can close and a download carries on.

The window starts a helper with spawn(), then reads its state file about once a second:

  ~/.local/share/spark-games/jobs/<id>.json    state, percent, speed, ETA, a message code
  ~/.local/share/spark-games/jobs/disk-<dev>.lock   one install per disk at a time

A job that finds its disk busy waits as "queued". Pause stops the store client with SIGSTOP and
carries on with SIGCONT; cancel ends it (a later install picks up the partial download). The
spec holds no secret: the helper reads tokens from the accounts folder like any other call.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from . import clients, registry, stores
from .core import data_dir, log, now, read_json, write_json

try:
    import fcntl
except ImportError:                       # Windows dev runs only
    fcntl = None  # type: ignore[assignment]

ENTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'spark_games.py')
ACTIVE = ('queued', 'running', 'paused')
KINDS = ('install', 'update', 'verify', 'launcher')
SPACE_WORDS = re.compile(r'no space left|not enough (disk|free)|disk full|insufficient', re.I)
NET_WORDS = re.compile(r'connection|timed out|name resolution|network|ssl|unreachable', re.I)
SIGN_WORDS = re.compile(r'not logged in|login|unauthori[sz]ed|expired|401|403', re.I)


def jobs_dir() -> str:
    path = os.path.join(data_dir(), 'jobs')
    os.makedirs(path, exist_ok=True)
    return path


def state_path(job_id: str) -> str:
    return os.path.join(jobs_dir(), f'{job_id}.json')


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                   # a zombie is not alive
        with open(f'/proc/{pid}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except (OSError, IndexError):
        return True


def read_job(job_id: str) -> Optional[Dict[str, Any]]:
    """The job's state. A job whose helper died without finishing is reported as failed."""
    data = read_json(state_path(job_id), None)
    if not isinstance(data, dict):
        return None
    if data.get('state') in ACTIVE and not pid_alive(int(data.get('pid') or 0)):
        data.update(state='failed', message='err_job_died', detail='')
        write_json(state_path(job_id), data)
    return data


def all_jobs() -> List[Dict[str, Any]]:
    found = []
    for name in sorted(os.listdir(jobs_dir())):
        if name.endswith('.json'):
            job = read_job(name[:-5])
            if job:
                found.append(job)
    return found


def job_for(key: str) -> Optional[Dict[str, Any]]:
    """The newest job for a game (running first), or None."""
    mine = [j for j in all_jobs() if j.get('key') == key]
    active = [j for j in mine if j.get('state') in ACTIVE]
    pool = active or mine
    return max(pool, key=lambda j: j.get('started', 0)) if pool else None


def forget(job_id: str) -> None:
    try:
        os.unlink(state_path(job_id))
    except OSError:
        pass


def prune(keep: int = 30) -> None:
    """Delete the state files of old finished jobs."""
    done = [j for j in all_jobs() if j.get('state') not in ACTIVE]
    for job in sorted(done, key=lambda j: j.get('started', 0))[:-keep]:
        forget(job['id'])


# ─── Window side ──────────────────────────────────────────────

def spawn(spec: Dict[str, Any]) -> str:
    """Start the helper for a job. spec: kind, store, app, key, title, path, root."""
    if spec.get('kind') not in KINDS:
        raise ValueError(spec.get('kind'))
    spec = dict(spec, id=spec.get('id') or new_id())
    write_json(state_path(spec['id']), {
        'id': spec['id'], 'kind': spec['kind'], 'store': spec.get('store', ''),
        'key': spec.get('key', ''), 'title': spec.get('title', ''), 'state': 'queued',
        'percent': 0.0, 'speed': '', 'eta': '', 'message': '', 'detail': '', 'pid': 0,
        'started': now()})
    try:
        proc = subprocess.Popen([sys.executable, ENTRY, '--job', json.dumps(spec)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        write_json(state_path(spec['id']), dict(read_json(state_path(spec['id'])),
                                               state='failed', message='err_job_start',
                                               detail=str(exc)))
        return spec['id']
    job = read_json(state_path(spec['id']), {})
    if job.get('state') == 'queued' and not job.get('pid'):
        job['pid'] = proc.pid
        write_json(state_path(spec['id']), job)
    return spec['id']


def _signal(job_id: str, sig: int) -> bool:
    job = read_job(job_id)
    if not job or job.get('state') not in ACTIVE:
        return False
    try:
        os.kill(int(job['pid']), sig)
        return True
    except (OSError, ValueError):
        return False


def pause(job_id: str) -> bool:
    return _signal(job_id, signal.SIGUSR1)


def resume(job_id: str) -> bool:
    return _signal(job_id, signal.SIGUSR2)


def cancel(job_id: str) -> bool:
    return _signal(job_id, signal.SIGTERM)


# ─── Reading a client's progress ──────────────────────────────

PROGRESS = stores.PROGRESS
SPEED = stores.SPEED


def parse_line(line: str, state: Dict[str, Any]) -> bool:
    """Update state from one line of client output. True when something changed."""
    changed = False
    m = PROGRESS.search(line)
    if m:
        state['percent'] = min(100.0, float(m.group(1)))
        h, mi, s = int(m.group(2)), int(m.group(3)), int(m.group(4))
        state['eta'] = f'{h}:{mi:02d}:{s:02d}' if h else f'{mi}:{s:02d}'
        changed = True
    m = SPEED.search(line)
    if m:
        state['speed'] = f'{m.group(1)} {m.group(2)}/s'
        changed = True
    return changed


def failure_code(text: str) -> str:
    if SPACE_WORDS.search(text):
        return 'err_space'
    if SIGN_WORDS.search(text):
        return 'err_signin_again'
    if NET_WORDS.search(text):
        return 'err_network'
    return 'err_job_failed'


# ─── Helper side ──────────────────────────────────────────────

class Helper:
    def __init__(self, spec: Dict[str, Any], poll: float = 0.5):
        self.spec, self.poll = spec, poll
        self.path = state_path(spec['id'])
        self.state: Dict[str, Any] = read_json(self.path, {}) or {
            'id': spec['id'], 'kind': spec['kind'], 'store': spec.get('store', ''),
            'key': spec.get('key', ''), 'title': spec.get('title', ''), 'started': now(),
            'percent': 0.0, 'speed': '', 'eta': '', 'message': '', 'detail': ''}
        self.state['pid'] = os.getpid()
        self.cancelled = False
        self.paused = False
        self.proc: Optional[subprocess.Popen] = None
        self._last = 0.0

    def save(self, force: bool = True, **changes: Any) -> None:
        self.state.update(changes)
        if force or time.time() - self._last > 0.4:
            write_json(self.path, self.state)
            self._last = time.time()

    # signals
    def _group(self, sig: int) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, sig)
            except OSError:
                pass

    def on_pause(self, *_a: Any) -> None:
        if self.state.get('state') == 'running':
            self.paused = True
            self._group(signal.SIGSTOP)
            self.save(state='paused', speed='', eta='')

    def on_resume(self, *_a: Any) -> None:
        if self.state.get('state') == 'paused':
            self.paused = False
            self._group(signal.SIGCONT)
            self.save(state='running')

    def on_cancel(self, *_a: Any) -> None:
        self.cancelled = True
        self._group(signal.SIGCONT)
        self._group(signal.SIGTERM)

    def install_handlers(self) -> None:
        signal.signal(signal.SIGUSR1, self.on_pause)
        signal.signal(signal.SIGUSR2, self.on_resume)
        signal.signal(signal.SIGTERM, self.on_cancel)

    # one install per disk
    def disk_lock(self, folder: str):
        try:
            dev = os.stat(stores.nearest_existing(folder)).st_dev
        except OSError:
            dev = 0
        handle = open(os.path.join(jobs_dir(), f'disk-{dev}.lock'), 'w')
        while not self.cancelled:
            try:
                if fcntl:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except OSError:
                time.sleep(self.poll)
        handle.close()
        return None

    def run(self) -> str:
        """Do the job. Returns the final state."""
        spec = self.spec
        self.install_handlers()
        folder = spec.get('path') or data_dir()
        self.save(state='queued')
        lock = self.disk_lock(folder)
        if lock is None:
            return self.finish('cancelled')
        try:
            self.save(state='running', message='', detail='')
            if spec['kind'] == 'launcher':
                from . import launchers
                return launchers.perform(self, spec)
            return self.run_client(spec)
        finally:
            lock.close()

    def run_client(self, spec: Dict[str, Any]) -> str:
        store, app, kind = spec['store'], spec['app'], spec['kind']
        try:
            def got(done: int, total: int) -> None:
                self.save(False, percent=100.0 * done / max(total, 1), message='fetching_client')
            clients.ensure(clients.CLIENT_OF[store], progress=got)
            self.save(percent=0.0, message='')
        except clients.ClientError as exc:
            return self.finish('failed', {'network': 'err_network', 'space': 'err_space',
                                          'mismatch': 'err_mismatch'}.get(exc.kind,
                                                                          'err_job_failed'))
        if self.cancelled:
            return self.finish('cancelled')
        target = spec.get('path') or ''
        if kind == 'install':
            os.makedirs(os.path.dirname(target), exist_ok=True)
        previous = registry.load()['games'].get(spec.get('key', ''))
        if kind != 'install' and previous:
            target = previous.get('path') or target
        args = stores.job_args(kind, store, app, target)
        try:
            self.proc = clients.popen(store, args)
        except (OSError, clients.ClientError) as exc:
            return self.finish('failed', 'err_job_start', str(exc))
        tail: List[str] = []
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            tail = (tail + [line.strip()])[-12:]
            if parse_line(line, self.state):
                self.save(False)
        code = self.proc.wait()
        if self.cancelled:
            return self.finish('cancelled')
        if code != 0:
            text = '\n'.join(tail)
            last = stores.scrub(next((t for t in reversed(tail) if t), ''))[:160]
            log.warning("%s %s %s: exit %d", store, kind, app, code)
            return self.finish('failed', failure_code(text), last)
        stores.finish_install(store, app, spec.get('title', ''), target, spec.get('root', ''),
                              previous)
        if kind == 'update':
            self._clear_update(store, app)
        return self.finish('done')

    def _clear_update(self, store: str, app: str) -> None:
        cached = stores.load_owned(store)
        if app in cached.get('updates', []):
            cached['updates'] = [a for a in cached['updates'] if a != app]
            write_json(stores.owned_path(store), cached)

    def finish(self, state: str, message: str = '', detail: str = '') -> str:
        self.save(state=state, message=message, detail=detail, speed='', eta='',
                  percent=100.0 if state == 'done' else self.state.get('percent', 0.0))
        return state


def run_job(spec: Dict[str, Any]) -> int:
    """Entry point of `spark-games --job`. Returns the process exit code."""
    helper = Helper(spec)
    try:
        state = helper.run()
    except Exception as exc:                        # the state file must say it failed
        log.exception("job %s crashed", spec.get('id'))
        helper.finish('failed', 'err_job_failed', type(exc).__name__)
        return 1
    return 0 if state in ('done', 'cancelled') else 1
