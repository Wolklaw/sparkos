"""The store clients Spark Games runs: legendary (Epic), gogdl (GOG) and nile (Amazon).

They are other people's programs, all GPL-3.0, and Spark Games only ever starts them as
separate processes and reads what they print; it never imports their code (see THIRD-PARTY.md).
Each is a single pinned build, downloaded the first time it is needed into
~/.local/share/spark-games/runners/<name>-<version>/, checked against the SHA-256 below (the
way Spark Run downloads Wine), and never trusted before that check passes. A build in
/usr/lib/spark-games/runners/<name> (put there by an image build) is used when it is there, and
SPARK_GAMES_LEGENDARY, SPARK_GAMES_GOGDL and SPARK_GAMES_NILE point at another build (the tests
point them at fake clients).

Tokens live in ~/.config/spark-games/accounts/ (see accounts.py). The clients are told to keep
theirs there, and nothing that holds a code or a token is ever written to the log.
"""

import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import APP_SLUG, VERSION
from .core import accounts_dir, data_dir, log, private_dir

IMAGE_DIR = '/usr/lib/spark-games/runners'
CHUNK = 256 * 1024


@dataclass(frozen=True)
class Runner:
    name: str
    version: str
    url: str
    sha256: str
    size: int
    store: str
    licence: str = 'GPL-3.0'


# Pinned 2026-11-22. Checked against each release's published digest and by downloading the file.
RUNNERS: Dict[str, Runner] = {
    'legendary': Runner(
        'legendary', '0.21.1',
        'https://github.com/legendary-gl/legendary/releases/download/0.21.1/legendary_linux_x64',
        'dbed33bbe96031e65858233e4badf0a1d401bb6cb0cc995d1237cf3a0c826a45', 3093622, 'epic'),
    'gogdl': Runner(
        'gogdl', '1.4.0',
        'https://github.com/Heroic-Games-Launcher/heroic-gogdl/releases/download/v1.4.0/'
        'gogdl_linux_x86_64',
        '2aa2b59c83d3bfbe7b60ead91c6297b263b5d1e6c233a04b7409bafe26738f02', 983218, 'gog'),
    'nile': Runner(
        'nile', '1.2.0',
        'https://github.com/imLinguin/nile/releases/download/v1.2.0/nile_linux_x86_64',
        'd73519514df9d52c50c6feec629373cc3a0d9504e087b6c7372a8ca8a95e7bfe', 11113264, 'amazon'),
}
CLIENT_OF = {r.store: r.name for r in RUNNERS.values()}      # epic -> legendary...


class ClientError(Exception):
    """kind: 'network', 'mismatch', 'space', 'unsupported', 'cancelled', 'missing'"""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail = kind, detail


def runners_dir() -> str:
    return os.path.join(data_dir(), 'runners')


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def pinned_path(name: str) -> str:
    runner = RUNNERS[name]
    return os.path.join(runners_dir(), f'{name}-{runner.version}', name)


def find(name: str) -> Optional[str]:
    """The client's program: an override, a downloaded one, or the image's. None if none yet."""
    override = os.environ.get(f'SPARK_GAMES_{name.upper()}')
    if override:
        return override if os.access(override, os.X_OK) else None
    for path in (pinned_path(name), os.path.join(IMAGE_DIR, name)):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def ensure(name: str, progress: Optional[Callable[[int, int], None]] = None,
           cancel: Optional[threading.Event] = None) -> str:
    """The client's program, downloading and checking it first if it isn't here yet."""
    found = find(name)
    if found:
        return found
    runner = RUNNERS[name]
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise ClientError('unsupported', platform.machine())
    target = pinned_path(name)
    folder = os.path.dirname(target)
    private_dir(folder)
    try:
        if shutil.disk_usage(folder).free < runner.size * 3:
            raise ClientError('space', folder)
    except OSError:
        pass
    fd, part = tempfile.mkstemp(prefix=f'.{name}.', suffix='.part', dir=folder)
    h, done = hashlib.sha256(), 0
    request = urllib.request.Request(runner.url, headers={'User-Agent': f'{APP_SLUG}/{VERSION}'})
    log.info("downloading %s %s", name, runner.version)
    try:
        with os.fdopen(fd, 'wb') as out, urllib.request.urlopen(request, timeout=30) as response:
            while True:
                if cancel is not None and cancel.is_set():
                    raise ClientError('cancelled')
                block = response.read(CHUNK)
                if not block:
                    break
                done += len(block)
                if done > runner.size:
                    raise ClientError('mismatch', f"{name} is larger than {runner.size} bytes")
                h.update(block)
                out.write(block)
                if progress:
                    progress(done, runner.size)
        if done != runner.size or h.hexdigest() != runner.sha256:
            log.error("%s: expected sha256 %s, got %s; deleted", name, runner.sha256,
                      h.hexdigest())
            raise ClientError('mismatch', f"{name}: SHA-256 {h.hexdigest()}")
        os.chmod(part, 0o755)
        os.replace(part, target)
    except ClientError:
        _unlink(part)
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _unlink(part)
        raise ClientError('network', str(getattr(exc, 'reason', exc))) from exc
    log.info("%s %s verified (sha256 %s)", name, runner.version, runner.sha256)
    return target


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def version_of(path: str) -> str:
    """What the program says for --version (it is run, so only call this for a checked build)."""
    try:
        done = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=20,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    match = re.search(r'\d+(?:\.\d+)+(?:\.post\d+)?', (done.stdout or '') + (done.stderr or ''))
    return match.group(0) if match else ''


def report() -> List[Tuple[str, Optional[str], str]]:
    """(name, path or None, version) for each client, for --self-test."""
    out = []
    for name in RUNNERS:
        path = find(name)
        out.append((name, path, version_of(path) if path else ''))
    return out


# ─── Running a client ─────────────────────────────────────────

def client_env(store: str) -> Dict[str, str]:
    """Where each client keeps its tokens: inside ~/.config/spark-games/accounts/."""
    base = accounts_dir()
    if store == 'epic':
        return {'LEGENDARY_CONFIG_PATH': private_dir(os.path.join(base, 'epic'))}
    if store == 'amazon':
        return {'NILE_CONFIG_PATH': private_dir(os.path.join(base, 'amazon'))}
    return {'GOGDL_CONFIG_PATH': private_dir(os.path.join(base, 'gogdl'))}


def gog_auth_file() -> str:
    return os.path.join(accounts_dir(), 'gog.json')


def command(store: str, args: List[str], program: Optional[str] = None) -> List[str]:
    """argv for a client call. gogdl takes its token file as an option before the command."""
    name = CLIENT_OF[store]
    program = program or find(name)
    if not program:
        raise ClientError('missing', name)
    prefix = ['--auth-config-path', gog_auth_file()] if store == 'gog' else []
    return [program] + prefix + list(args)


def tighten() -> None:
    """Make every account file readable by this user only."""
    base = accounts_dir()
    for folder, dirs, files in os.walk(base):
        try:
            os.chmod(folder, 0o700)
            for name in files:
                os.chmod(os.path.join(folder, name), 0o600)
        except OSError:
            pass


def _umask() -> None:
    os.umask(0o077)


def run(store: str, args: List[str], timeout: float = 120.0,
        extra_env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """Run a client to completion: (exit code, stdout, stderr). The arguments are never logged,
    since a sign-in code can be among them."""
    argv = command(store, args)
    env = dict(os.environ)
    env.update(client_env(store))
    if extra_env:
        env.update(extra_env)
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env,
                              stdin=subprocess.DEVNULL, preexec_fn=_umask)
    except subprocess.TimeoutExpired:
        log.warning("%s %s: timed out", CLIENT_OF[store], args[0] if args else '')
        return 124, '', 'timed out'
    except OSError as exc:
        log.warning("%s could not start: %s", CLIENT_OF[store], exc)
        return 127, '', str(exc)
    tighten()
    log.info("%s %s: exit %d", CLIENT_OF[store], args[0] if args else '', done.returncode)
    return done.returncode, done.stdout or '', done.stderr or ''


def popen(store: str, args: List[str], extra_env: Optional[Dict[str, str]] = None
          ) -> subprocess.Popen:
    """Start a client for the install helper: output merged into one pipe, its own process group."""
    env = dict(os.environ)
    env.update(client_env(store))
    env.update(extra_env or {})
    env['PYTHONUNBUFFERED'] = '1'
    return subprocess.Popen(command(store, args), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors='replace', start_new_session=True, preexec_fn=_umask)
