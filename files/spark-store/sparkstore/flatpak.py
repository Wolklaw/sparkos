"""Talking to flatpak: what is installed, what has updates, an app's size and permissions,
and the commands the install queue runs. Everything goes through the flatpak command, the
same one a person would type; SPARK_STORE_FLATPAK replaces it (the tests use a fake one).

Links: .flatpakref files and appstream:// addresses are read here too."""

import configparser
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from . import FLATHUB_REPO, REMOTE
from .core import log, parse_size

APP_ID_RE = re.compile(r'^[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*){2,}$')


def command() -> List[str]:
    forced = os.environ.get('SPARK_STORE_FLATPAK')
    if forced:             # a command line, or a JSON list (paths with spaces, on any OS)
        if forced.startswith('['):
            return [str(part) for part in json.loads(forced)]
        return shlex.split(forced)
    path = shutil.which('flatpak')
    return [path] if path else []


def available() -> bool:
    return bool(command())


def run(args: List[str], timeout: float = 30, env: Optional[Dict[str, str]] = None
        ) -> Tuple[int, str, str]:
    """(exit code, stdout, stderr). Output in the C locale, so it parses the same on every
    PC; error messages shown to people come from the queue, which keeps their language."""
    base = command()
    if not base:
        return 127, '', 'flatpak is not installed'
    full_env = dict(os.environ, LC_ALL='C.UTF-8', LANG='C.UTF-8')
    full_env.update(env or {})
    # Output goes to files, not pipes: a helper flatpak starts (a D-Bus session daemon, say)
    # may keep a pipe open long after flatpak itself has finished. Its own process group, so
    # a timeout ends everything it started.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(base + args, stdout=out, stderr=err,
                                    stdin=subprocess.DEVNULL, env=full_env, close_fds=True,
                                    start_new_session=os.name == 'posix')
        except OSError as exc:
            return 1, '', str(exc)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            return 124, '', f'flatpak took longer than {timeout:.0f} s'
        out.seek(0)
        err.seek(0)
        return (code, out.read().decode('utf-8', errors='replace'),
                err.read().decode('utf-8', errors='replace'))


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == 'posix':
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def version() -> str:
    code, out, err = run(['--version'], timeout=10)
    return out.strip() if code == 0 else ''


# ─── What is installed ────────────────────────────────────────

@dataclass
class Installed:
    id: str
    name: str
    version: str = ''
    branch: str = ''
    origin: str = ''
    scope: str = 'user'              # 'user' or 'system'
    size: Optional[int] = None


def installed() -> Dict[str, Installed]:
    """Installed apps by ID. When an app is installed both for you and for everyone, the one
    for you is kept: that is the one `flatpak run` starts."""
    code, out, err = run(['list', '--app',
                          '--columns=application,name,version,branch,origin,installation,size'])
    if code != 0:
        log.warning("flatpak list: %s", err.strip())
        return {}
    apps: Dict[str, Installed] = {}
    for line in out.splitlines():
        cols = line.split('\t')
        if len(cols) < 6 or not cols[0]:
            continue
        scope = 'user' if cols[5].strip() == 'user' else 'system'
        item = Installed(id=cols[0].strip(), name=cols[1].strip() or cols[0].strip(),
                         version=cols[2].strip(), branch=cols[3].strip(),
                         origin=cols[4].strip(), scope=scope,
                         size=parse_size(cols[6]) if len(cols) > 6 else None)
        if item.id not in apps or scope == 'user':
            apps[item.id] = item
    return apps


def installed_runtimes() -> Dict[str, str]:
    """Installed runtimes and add-ons (extensions): ID -> 'user' or 'system' (yours wins)."""
    code, out, err = run(['list', '--runtime', '--columns=application,installation'])
    if code != 0:
        log.warning("flatpak list --runtime: %s", err.strip())
        return {}
    found: Dict[str, str] = {}
    for line in out.splitlines():
        cols = line.split('\t')
        if len(cols) < 2 or not cols[0].strip():
            continue
        scope = 'user' if cols[1].strip() == 'user' else 'system'
        if found.get(cols[0].strip()) != 'user':
            found[cols[0].strip()] = scope
    return found


@dataclass
class Update:
    id: str
    scope: str
    version: str = ''
    branch: str = ''


def updates() -> Tuple[List[Update], int, str]:
    """(app updates, how many runtimes also have one, error). Asks Flathub, so it needs the
    network; run it from a thread."""
    apps: List[Update] = []
    runtimes = 0
    errors = []
    for scope in ('user', 'system'):
        code, out, err = run([f'--{scope}', 'remote-ls', '--updates',
                              '--columns=application,version,branch,ref'], timeout=120)
        if code != 0:
            if err.strip() and 'No remote' not in err:
                errors.append(err.strip().splitlines()[-1])
            continue
        for line in out.splitlines():
            cols = line.split('\t')
            if len(cols) < 4 or not cols[0].strip():
                continue
            if cols[3].startswith('app/'):
                apps.append(Update(cols[0].strip(), scope, cols[1].strip(), cols[2].strip()))
            else:
                runtimes += 1
    return apps, runtimes, '; '.join(errors)


def remotes() -> Dict[str, List[str]]:
    """{'user': [...], 'system': [...]}: the remotes each installation has."""
    found: Dict[str, List[str]] = {'user': [], 'system': []}
    for scope in ('user', 'system'):
        code, out, _err = run([f'--{scope}', 'remotes', '--columns=name'], timeout=15)
        if code == 0:
            found[scope] = [line.strip() for line in out.splitlines() if line.strip()]
    return found


# ─── One app, from Flathub's data that flatpak keeps ──────────

@dataclass
class RemoteInfo:
    download: Optional[int] = None
    installed: Optional[int] = None
    version: str = ''
    metadata: str = ''
    error: str = ''


def remote_info(app_id: str, branch: str = 'stable', scope: str = 'user',
                remote: str = REMOTE) -> RemoteInfo:
    """Sizes and permissions of an app on Flathub. flatpak reads them from Flathub's index,
    which it keeps up to date itself; nothing else is asked."""
    info = RemoteInfo()
    ref = f'app/{app_id}//{branch}' if branch else f'app/{app_id}'
    scopes = [scope] + [s for s in ('user', 'system') if s != scope]
    for sc in scopes:
        code, out, err = run([f'--{sc}', 'remote-info', remote, ref], timeout=60)
        if code != 0:
            info.error = (err.strip().splitlines() or [''])[-1]
            continue
        info.error = ''
        for line in out.splitlines():
            key, _, value = line.strip().partition(':')
            key = key.strip().lower()
            if key in ('download', 'download size'):      # flatpak 1.18 says "Size"
                info.download = parse_size(value)
            elif key in ('installed', 'installed size'):
                info.installed = parse_size(value)
            elif key == 'version':
                info.version = value.strip()
        code, out, err = run([f'--{sc}', 'remote-info', '--show-metadata', remote, ref],
                             timeout=60)
        if code == 0:
            info.metadata = out
        break
    return info


def installed_metadata(app_id: str, scope: str) -> str:
    code, out, _err = run([f'--{scope}', 'info', '--show-metadata', app_id], timeout=20)
    return out if code == 0 else ''


# ─── Commands for the queue ───────────────────────────────────
# -y answers yes to flatpak's questions (a runtime to add, say), and stdin is empty, so any
# other question ends the step instead of waiting. Not --noninteractive: that also hides the
# progress bar.

def cmd_install(app_id: str, branch: str = 'stable', remote: str = REMOTE) -> List[str]:
    ref = f'app/{app_id}//{branch}' if branch else app_id
    return ['--user', 'install', '-y', remote, ref]


def cmd_install_addon(addon_id: str, branch: str = 'stable', remote: str = REMOTE) -> List[str]:
    return ['--user', 'install', '-y', remote,
            f'runtime/{addon_id}//{branch}' if branch else f'runtime/{addon_id}']


def cmd_remove_addon(addon_id: str, scope: str, branch: str = '') -> List[str]:
    ref = f'runtime/{addon_id}//{branch}' if branch else f'runtime/{addon_id}'
    return [f'--{scope}', 'uninstall', '-y', ref]


def cmd_install_ref(path: str) -> List[str]:
    return ['--user', 'install', '-y', '--from', path]


def cmd_add_flathub() -> List[str]:
    return ['--user', 'remote-add', '--if-not-exists', REMOTE, FLATHUB_REPO]


def cmd_remove(app_id: str, scope: str, delete_data: bool = False) -> List[str]:
    args = [f'--{scope}', 'uninstall', '-y']
    if delete_data:
        args.append('--delete-data')
    return args + [app_id]


def cmd_update(app_id: Optional[str], scope: str) -> List[str]:
    args = [f'--{scope}', 'update', '-y']
    return args + ([app_id] if app_id else [])


def cmd_remove_unused(scope: str = 'user') -> List[str]:
    return [f'--{scope}', 'uninstall', '--unused', '-y']


def cmd_refresh_catalog(scope: str = 'user', remote: str = REMOTE) -> List[str]:
    return [f'--{scope}', 'update', '--appstream', remote]


def launch(app_id: str) -> bool:
    base = command()
    if not base:
        return False
    try:
        subprocess.Popen(base + ['run', app_id], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=os.name == 'posix', close_fds=True)
        return True
    except OSError as exc:
        log.warning("could not start %s: %s", app_id, exc)
        return False


# ─── Links ────────────────────────────────────────────────────

@dataclass
class Ref:
    """What a .flatpakref file says."""
    id: str
    title: str = ''
    branch: str = ''
    url: str = ''
    is_runtime: bool = False
    path: str = ''
    homepage: str = ''
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def from_flathub(self) -> bool:
        host = urlparse(self.url).hostname or ''
        return host in ('dl.flathub.org', 'flathub.org')

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or self.url


def read_flatpakref(path: str) -> Optional[Ref]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read(64 * 1024)
        parser.read_string(text)
    except (OSError, configparser.Error) as exc:
        log.warning("could not read %s: %s", path, exc)
        return None
    if not parser.has_section('Flatpak Ref'):
        return None
    sec = dict(parser.items('Flatpak Ref'))
    app_id = sec.get('Name', '').strip()
    if not APP_ID_RE.match(app_id):
        return None
    return Ref(id=app_id, title=sec.get('Title', '').strip(), branch=sec.get('Branch', '').strip(),
               url=sec.get('Url', '').strip(), path=os.path.abspath(path),
               is_runtime=sec.get('IsRuntime', '').strip().lower() == 'true',
               homepage=sec.get('Homepage', '').strip(), fields=sec)


def app_id_from_link(target: str) -> Optional[str]:
    """appstream://org.gimp.GIMP, appstream:org.gimp.GIMP.desktop, flathub.org/apps/<id>,
    or a plain app ID -> the app ID."""
    text = unquote(target.strip())
    if text.startswith('appstream:'):
        text = text[len('appstream:'):].lstrip('/')
    else:
        match = re.match(r'^https://(?:www\.)?flathub\.org/(?:[a-z]{2}(?:-[A-Za-z]+)?/)?'
                         r'apps/(?:details/)?([^/?#]+)', text)
        if match:
            text = match.group(1)
    text = text.split('?')[0].split('#')[0].rstrip('/')
    if text.endswith('.desktop'):
        text = text[:-8]
    return text if APP_ID_RE.match(text) else None


@dataclass
class Repo:
    """What a .flatpakrepo file says: a whole app source to add, not one app."""
    name: str                        # the remote's name, from the file's name
    title: str = ''
    url: str = ''
    homepage: str = ''
    comment: str = ''
    description: str = ''
    path: str = ''

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or self.url

    @property
    def is_flathub(self) -> bool:
        return self.host in ('dl.flathub.org', 'flathub.org')


def read_flatpakrepo(path: str) -> Optional[Repo]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            parser.read_string(f.read(64 * 1024))
    except (OSError, configparser.Error) as exc:
        log.warning("could not read %s: %s", path, exc)
        return None
    if not parser.has_section('Flatpak Repo'):
        return None
    sec = dict(parser.items('Flatpak Repo'))
    url = sec.get('Url', '').strip()
    if not url.startswith(('https://', 'http://', 'oci+https://')):
        return None
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    name = re.sub(r'[^a-z0-9_-]+', '-', stem).strip('-')[:40] or 'apps'
    return Repo(name=name, title=sec.get('Title', '').strip(), url=url,
                homepage=sec.get('Homepage', '').strip(), comment=sec.get('Comment', '').strip(),
                description=sec.get('Description', '').strip(), path=os.path.abspath(path))


def is_flatpakrepo(target: str) -> bool:
    return local_path(target).lower().endswith('.flatpakrepo')


def cmd_add_remote(name: str, path: str) -> List[str]:
    return ['--user', 'remote-add', '--if-not-exists', '--from', name, path]


def is_flatpakref(target: str) -> bool:
    return target.lower().endswith('.flatpakref') or target.startswith('file://') and \
        target.lower().endswith('.flatpakref')


def local_path(target: str) -> str:
    if target.startswith('file://'):
        return unquote(urlparse(target).path)
    return target

