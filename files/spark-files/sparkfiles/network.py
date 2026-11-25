"""Network places and online accounts: sftp:// and smb:// servers, and Google Drive.

How it works: each place is mounted as an ordinary folder under $XDG_RUNTIME_DIR/spark-net/,
with user-space FUSE mounts and no KDE part: sshfs for sftp, `rclone mount` for smb and for
Google Drive. From there every feature of the app (listing, open, copy to and from with
progress and cancel, drag and drop) works on that path like on any folder, so nothing here
touches the file operations. Everything that can wait on a network runs in a thread; the
window only ever hears back through the bridge.

Passwords: never in settings.json and never in a bookmark. They go to the Secret Service
(KWallet or GNOME Keyring) through `secret-tool`, with the password on its standard input
(never on a command line).
"""

import configparser
import logging
import os
import re
import shutil
import subprocess
import threading
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlsplit

from .core import home

log = logging.getLogger('spark-files')

SCHEMES = ('sftp', 'smb')
DEFAULT_PORT = {'sftp': 22}
GDRIVE_URL = 'gdrive:///'
CONNECT_TIMEOUT = 30                  # seconds before "didn't answer"
KEYRING_APP = 'spark-files'
MOUNT_DIR = 'spark-net'           # $XDG_RUNTIME_DIR/spark-net/<scheme>/<server>


class NetworkError(Exception):
    """code: timeout | failed | missing (detail: the tool) | no_account | address; detail is
    the system's own words."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


# ─── where the mounts are ────────────────────────────────────

def runtime_dir() -> str:
    return os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'


def mount_root() -> str:
    return os.path.join(runtime_dir(), MOUNT_DIR)


def split_remote(path: str) -> Optional[Tuple[str, str]]:
    """('/run/user/1000/spark-net/sftp/me@host', 'sftp://me@host') for a path inside one of
    the mounts, or None. The first folder below spark-net is the scheme and the second the
    server (Google Drive has none)."""
    root = mount_root()
    if not path.startswith(root + '/'):
        return None
    parts = path[len(root) + 1:].split('/')
    scheme = parts[0]
    if not scheme:
        return None
    if scheme == 'gdrive':
        return os.path.join(root, 'gdrive'), 'Google Drive'
    if len(parts) < 2 or not parts[1]:
        return os.path.join(root, scheme), scheme + '://'
    return os.path.join(root, scheme, parts[1]), f"{scheme}://{unquote(parts[1])}"


def is_remote(path: str) -> bool:
    return bool(path) and path.startswith(mount_root() + '/')


# ─── addresses ───────────────────────────────────────────────

class Server:
    """sftp://user@host:port/path or smb://user@host/share. Never holds a password."""
    __slots__ = ('scheme', 'host', 'port', 'user', 'path')

    def __init__(self, scheme: str, host: str, port: Optional[int] = None, user: str = '',
                 path: str = '/'):
        self.scheme, self.host, self.port, self.user = scheme, host, port, user
        self.path = path if path.startswith('/') else '/' + path

    def netloc(self, password: Optional[str] = None) -> str:
        host = f'[{self.host}]' if ':' in self.host else self.host
        out = host + (f':{self.port}' if self.port and self.port != DEFAULT_PORT.get(
            self.scheme) else '')
        if self.user:
            cred = quote(self.user, safe='')
            if password:
                cred += ':' + quote(password, safe='')
            out = cred + '@' + out
        return out

    def display(self) -> str:
        """For the screen and for bookmarks: no password, ever."""
        return f"{self.scheme}://{self.netloc()}{self.path if self.path != '/' else '/'}"

    def url(self, password: Optional[str] = None) -> str:
        """Carries the password when there is one: only for scrubbing it out of error text."""
        return f"{self.scheme}://{self.netloc(password)}{quote(self.path, safe='/')}"

    def key(self) -> str:
        """The keyring's name for this server: scheme, user, host, port; no path."""
        return f"{self.scheme}://{self.netloc()}"

    def __eq__(self, other) -> bool:
        return isinstance(other, Server) and self.display() == other.display()

    def __hash__(self) -> int:
        return hash(self.display())

    def __repr__(self) -> str:
        return f"Server({self.display()!r})"


def parse_address(text: str, user: str = '') -> Tuple[Server, Optional[str]]:
    """(server, password typed into the address or None). `ssh://` counts as sftp. A user
    given in the address wins over the `user` argument. Raises NetworkError('address')."""
    text = text.strip()
    m = re.match(r'^([A-Za-z][A-Za-z0-9+.-]*)://(.*)$', text)
    if not m:
        raise NetworkError('address', 'scheme')
    scheme = m.group(1).lower()
    if scheme == 'ssh':
        scheme = 'sftp'
    if scheme not in SCHEMES:
        raise NetworkError('address', 'scheme')
    try:
        parts = urlsplit(f"{scheme}://{m.group(2)}")
        host = parts.hostname or ''
        port = parts.port
    except ValueError:
        raise NetworkError('address', 'host')
    if not host or any(c in host for c in ' \t\n\\'):
        raise NetworkError('address', 'host')
    path = unquote(parts.path) or '/'
    typed_user = unquote(parts.username) if parts.username else ''
    password = unquote(parts.password) if parts.password is not None else None
    return Server(scheme, host, port, typed_user or user.strip(), path), password


class RawUrl:
    """A place that isn't a server (gdrive:///), shaped like Server for connect_blocking."""

    def __init__(self, url: str):
        self.raw = url

    def url(self, password: Optional[str] = None) -> str:
        return self.raw

    def display(self) -> str:
        return self.raw


def bookmarks(settings: Dict) -> List[Dict[str, str]]:
    """The saved servers: [{'name': ..., 'url': ...}]. Anything with a password is dropped
    from the url, whatever put it there."""
    out = []
    for item in settings.get('servers', []):
        if not isinstance(item, dict) or not isinstance(item.get('url'), str):
            continue
        try:
            server, _pw = parse_address(item['url'])
        except NetworkError:
            continue
        name = item.get('name') if isinstance(item.get('name'), str) and item['name'].strip() \
            else server.display()
        out.append({'name': name.strip(), 'url': server.display()})
    return out


def add_bookmark(settings: Dict, name: str, server: Server) -> None:
    items = [b for b in bookmarks(settings) if b['url'] != server.display()]
    items.append({'name': name.strip() or server.display(), 'url': server.display()})
    settings['servers'] = items


def remove_bookmark(settings: Dict, url: str) -> None:
    settings['servers'] = [b for b in bookmarks(settings) if b['url'] != url]


# ─── the keyring ─────────────────────────────────────────────

class Keyring:
    """Passwords in the Secret Service through `secret-tool`. run is subprocess.run, so tests
    can swap in a fake. Every method can block on an unlock prompt: call from a thread."""

    def __init__(self, run: Callable = subprocess.run, tool: Optional[str] = None):
        self.run = run
        self.tool = tool if tool is not None else shutil.which('secret-tool')

    @property
    def available(self) -> bool:
        return bool(self.tool)

    def _attrs(self, key: str) -> List[str]:
        return ['application', KEYRING_APP, 'server', key]

    def lookup(self, key: str) -> Optional[str]:
        if not self.tool:
            return None
        try:
            r = self.run([self.tool, 'lookup'] + self._attrs(key), capture_output=True,
                         text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 and r.stdout else None

    def store(self, key: str, password: str, label: str = '') -> bool:
        if not self.tool or not password:
            return False
        try:
            r = self.run([self.tool, 'store', f'--label={label or "Spark Files " + key}']
                         + self._attrs(key), input=password, capture_output=True, text=True,
                         timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0

    def clear(self, key: str) -> bool:
        if not self.tool:
            return False
        try:
            r = self.run([self.tool, 'clear'] + self._attrs(key), capture_output=True,
                         text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0


# ─── ssh host keys ───────────────────────────────────────────

def known_hosts_path() -> str:
    return os.path.join(home(), '.ssh', 'known_hosts')


def _host_pattern(server: Server) -> str:
    port = server.port or 22
    return server.host if port == 22 else f'[{server.host}]:{port}'


def host_key_known(server: Server, known_hosts: Optional[str] = None,
                   run: Callable = subprocess.run) -> Optional[bool]:
    """True when ~/.ssh/known_hosts already has the server; False when it hasn't; None
    when this PC has no ssh-keygen to ask."""
    tool = shutil.which('ssh-keygen')
    if not tool:
        return None
    path = known_hosts or known_hosts_path()
    if not os.path.exists(path):
        return False
    try:
        r = run([tool, '-F', _host_pattern(server), '-f', path], capture_output=True,
                text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0


def scan_host_key(server: Server, run: Callable = subprocess.run) -> Tuple[str, str]:
    """(known_hosts line, 'SHA256:... (ED25519)') the server offers. Raises NetworkError."""
    scan, keygen = shutil.which('ssh-keyscan'), shutil.which('ssh-keygen')
    if not scan or not keygen:
        raise NetworkError('failed', 'ssh-keyscan')
    try:
        r = run([scan, '-T', '8', '-p', str(server.port or 22), '-t', 'ed25519,ecdsa,rsa',
                 server.host], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        raise NetworkError('timeout')
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError('failed', str(exc))
    lines = [ln for ln in r.stdout.splitlines() if ln and not ln.startswith('#')]
    if not lines:
        raise NetworkError('failed', (r.stderr or '').strip().splitlines()[-1]
                           if r.stderr.strip() else 'no key')
    line = lines[0]
    fields = line.split()
    # ssh-keyscan names the host as "host" or "[host]:port"; keep it that way
    entry = f"{_host_pattern(server)} {fields[1]} {fields[2]}" if len(fields) >= 3 else line
    try:
        out = run([keygen, '-lf', '-'], input=entry + '\n', capture_output=True, text=True,
                  timeout=10).stdout.split()
    except (OSError, subprocess.SubprocessError):
        out = []
    shown = f"{out[1]} {out[-1]}" if len(out) >= 4 else entry.split()[-1][:40]
    return entry, shown


def accept_host_key(line: str, known_hosts: Optional[str] = None) -> None:
    path = known_hosts or known_hosts_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as f:
        f.write(line.rstrip('\n') + '\n')


# ─── mounting: sshfs for sftp, rclone for smb and Google Drive ─────

GDRIVE_REMOTE = 'gdrive'          # the remote's name in rclone_conf()


def _fusermount() -> Optional[str]:
    return shutil.which('fusermount3') or shutil.which('fusermount')


def _unmount(point: str) -> None:
    tool = _fusermount()
    if tool and os.path.ismount(point):
        subprocess.run([tool, '-u', '-z', point], capture_output=True, timeout=10)


def unmount_all() -> None:
    """At exit: let go of the mounts this app made (only real mounts are touched)."""
    root = mount_root()
    for scheme in SCHEMES:
        try:
            names = os.listdir(os.path.join(root, scheme))
        except OSError:
            continue
        for name in names:
            _unmount(os.path.join(root, scheme, name))
    _unmount(os.path.join(root, 'gdrive'))


def _last_line(text: str) -> str:
    lines = [ln for ln in (text or '').strip().splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ''


class SshFs:
    """sftp:// through sshfs. Mounts the server's root at spark-net/sftp/<user@host[:port]>
    and returns that folder plus the address's path. A password goes to sshfs on its standard
    input (password_stdin), never on a command line; without one it uses keys and the agent
    and never asks (BatchMode). The ssh host key rules are ssh's own."""
    TOOL = 'sshfs'

    def __init__(self, runner: Optional[Callable] = None):
        self.runner = runner or subprocess.run

    @staticmethod
    def available() -> bool:
        return bool(shutil.which('sshfs'))

    def mountpoint(self, server) -> str:
        return os.path.join(mount_root(), 'sftp', server.netloc())

    def argv(self, server, mountpoint: str, password: Optional[str]) -> List[str]:
        cmd = ['sshfs', f"{server.user + '@' if server.user else ''}"
                        f"{'[' + server.host + ']' if ':' in server.host else server.host}:/",
               mountpoint, '-o', 'reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,'
               'follow_symlinks,idmap=user']
        if server.port:
            cmd += ['-p', str(server.port)]
        cmd += ['-o', 'password_stdin,NumberOfPasswordPrompts=1' if password
                else 'BatchMode=yes']
        return cmd

    def mount(self, server, password: Optional[str] = None,
              timeout: float = CONNECT_TIMEOUT) -> str:
        if getattr(server, 'scheme', '') != 'sftp':
            raise NetworkError('failed', 'sshfs only does sftp')
        point = self.mountpoint(server)
        os.makedirs(point, mode=0o700, exist_ok=True)
        if not os.path.ismount(point):
            try:
                done = self.runner(self.argv(server, point, password),
                                   input=(password + '\n') if password else None,
                                   capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise NetworkError('timeout')
            except FileNotFoundError:
                raise NetworkError('missing', 'sshfs')
            except OSError as exc:
                raise NetworkError('failed', str(exc))
            if done.returncode != 0:
                raise NetworkError('failed', _scrub(_last_line(done.stderr), server.url(password)))
        return point + (server.path if server.path != '/' else '')


def rclone_conf() -> str:
    """Spark Files' own rclone config (only the Google account lives there; 0600)."""
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    return os.path.join(base, 'spark-files', 'rclone.conf')


class Rclone:
    """smb:// and Google Drive through `rclone mount` (FUSE, a user mount, no root).

    smb: an on-the-fly `:smb:` remote whose host, user and password come in RCLONE_SMB_*
    environment variables, so nothing is written to disk and nothing is on a command line.
    The password is first put through `rclone obscure -` (on its standard input), which is the
    form rclone takes. The server's root (the list of shares) is mounted at
    spark-net/smb/<user@host>; the share and folder are below it.

    Google Drive: the `gdrive` remote in rclone_conf(), made by add_google_account(),
    mounted at spark-net/gdrive."""
    TOOL = 'rclone'

    def __init__(self, runner: Optional[Callable] = None, conf: Optional[str] = None):
        self.runner = runner or subprocess.run
        self.conf = conf or rclone_conf()

    @staticmethod
    def available() -> bool:
        return bool(shutil.which('rclone'))

    def mountpoint(self, server) -> str:
        if isinstance(server, RawUrl):
            return os.path.join(mount_root(), 'gdrive')
        return os.path.join(mount_root(), 'smb', server.netloc())

    def obscure(self, password: str) -> str:
        try:
            done = self.runner(['rclone', 'obscure', '-'], input=password,
                               capture_output=True, text=True, timeout=15)
        except FileNotFoundError:
            raise NetworkError('missing', 'rclone')
        except (OSError, subprocess.SubprocessError) as exc:
            raise NetworkError('failed', str(exc))
        if done.returncode != 0 or not done.stdout.strip():
            raise NetworkError('failed', _last_line(done.stderr) or 'rclone obscure')
        return done.stdout.strip()

    def smb_env(self, server, password: Optional[str]) -> Dict[str, str]:
        user, domain = server.user, ''
        for sep in (';', '\\'):                     # smb://DOMAIN;user@host, DOMAIN\user
            if sep in user:
                domain, user = user.split(sep, 1)
                break
        env = {'RCLONE_SMB_HOST': server.host, 'RCLONE_SMB_USER': user or 'guest'}
        if domain:
            env['RCLONE_SMB_DOMAIN'] = domain
        if server.port:
            env['RCLONE_SMB_PORT'] = str(server.port)
        if password:
            env['RCLONE_SMB_PASS'] = self.obscure(password)
        return env

    def argv(self, remote: str, mountpoint: str, timeout: float) -> List[str]:
        return ['rclone', 'mount', remote, mountpoint, '--config', self.conf,
                '--daemon', '--daemon-wait', f'{int(timeout)}s',
                '--vfs-cache-mode', 'writes', '--dir-cache-time', '15s']

    def mount(self, server, password: Optional[str] = None,
              timeout: float = CONNECT_TIMEOUT) -> str:
        if isinstance(server, RawUrl):
            if gdrive_state(conf=self.conf, tool=True) != 'ready':
                raise NetworkError('no_account')
            remote, env, below = GDRIVE_REMOTE + ':', {}, ''
        elif getattr(server, 'scheme', '') == 'smb':
            remote, env = ':smb:', self.smb_env(server, password)
            below = server.path if server.path != '/' else ''
        else:
            raise NetworkError('failed', 'rclone here only does smb and Google Drive')
        point = self.mountpoint(server)
        os.makedirs(point, mode=0o700, exist_ok=True)
        if not os.path.ismount(point):
            try:
                done = self.runner(self.argv(remote, point, timeout),
                                   env=dict(os.environ, **env), stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=timeout + 5)
            except subprocess.TimeoutExpired:
                raise NetworkError('timeout')
            except FileNotFoundError:
                raise NetworkError('missing', 'rclone')
            except OSError as exc:
                raise NetworkError('failed', str(exc))
            if done.returncode != 0:
                raise NetworkError('failed', _scrub(_last_line(done.stderr),
                                                    server.url(password)))
        return point + below


def choose_backend(target):
    """sshfs for sftp; rclone for smb and Google Drive."""
    return SshFs() if getattr(target, 'scheme', '') == 'sftp' else Rclone()


def _scrub(text: str, url: str) -> str:
    """Error text without the password (it was in the URL we sent)."""
    try:
        pw = urlsplit(url).password
    except ValueError:
        pw = None
    if pw:
        for form in (pw, quote(pw, safe='')):
            text = text.replace(form, '***')
    return text.strip()


def _within(seconds: float, fn: Callable):
    """Run fn in a thread; (True, result) or (False, None) when it didn't return in time. A
    call stuck on a dead server is left behind (daemon thread), the caller moves on."""
    box: List = []

    def work():
        try:
            box.append((True, fn()))
        except BaseException as exc:   # noqa: BLE001 - handed to the caller
            box.append((False, exc))
    th = threading.Thread(target=work, name='net-call', daemon=True)
    th.start()
    th.join(seconds)
    if not box:
        return None, None
    return box[0]


def connect_blocking(server: Server, password: Optional[str], backend=None,
                     timeout: float = CONNECT_TIMEOUT) -> str:
    """Mount the server and check it answers a listing. Returns the local path. Raises
    NetworkError. Takes up to `timeout` seconds in total; call from a thread."""
    backend = backend or choose_backend(server)
    mount = lambda: backend.mount(server, password, timeout)    # noqa: E731
    done, value = _within(timeout, mount)
    if done is None:
        raise NetworkError('timeout')
    if not done:
        if isinstance(value, NetworkError):
            raise value
        raise NetworkError('failed', _scrub(str(value), server.url(password)))
    path = value
    done, value = _within(timeout, lambda: os.listdir(path))
    if done is None:
        raise NetworkError('timeout')
    if not done:
        detail = getattr(value, 'strerror', None) or str(value)
        raise NetworkError('failed', _scrub(detail, server.url(password)))
    return path


def start(fn: Callable[[], object], post: Callable[[Callable], None],
          done: Callable[[object, Optional[NetworkError]], None]) -> Callable[[], None]:
    """Run fn in a thread, then done(result, error) on the window's thread through post.
    Returns cancel(): after it, done is never called."""
    state = {'cancelled': False}

    def work():
        result, error = None, None
        try:
            result = fn()
        except NetworkError as exc:
            error = exc
        except Exception as exc:    # noqa: BLE001 - shown to the user, logged
            log.warning("network call failed: %s", exc)
            error = NetworkError('failed', str(exc))
        if not state['cancelled']:
            post(lambda: None if state['cancelled'] else done(result, error))

    threading.Thread(target=work, name='net', daemon=True).start()

    def cancel():
        state['cancelled'] = True
    return cancel


# ─── Google Drive ────────────────────────────────────────────

def gdrive_state(conf: Optional[str] = None, tool: Optional[bool] = None) -> str:
    """'none' (no rclone), 'no-account' or 'ready' (the gdrive remote has a token)."""
    if not (Rclone.available() if tool is None else tool):
        return 'none'
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(conf or rclone_conf(), encoding='utf-8')
    except (configparser.Error, OSError, UnicodeDecodeError):
        return 'no-account'
    if parser.has_section(GDRIVE_REMOTE) and parser.get(GDRIVE_REMOTE, 'type',
                                                         fallback='') == 'drive' \
            and parser.get(GDRIVE_REMOTE, 'token', fallback='').strip():
        return 'ready'
    return 'no-account'


ACCOUNT_TIMEOUT = 600             # seconds to finish signing in in the browser


def add_google_account(runner: Callable = subprocess.run, conf: Optional[str] = None,
                       timeout: float = ACCOUNT_TIMEOUT) -> None:
    """Sign in to Google: rclone opens the browser on Google's own page and waits for the
    answer on localhost, then writes the token to rclone_conf() (0600). Blocks until the
    person is done (call from a thread). Raises NetworkError."""
    conf = conf or rclone_conf()
    os.makedirs(os.path.dirname(conf), mode=0o700, exist_ok=True)
    if not os.path.exists(conf):
        os.close(os.open(conf, os.O_WRONLY | os.O_CREAT, 0o600))
    try:
        done = runner(['rclone', 'config', 'create', GDRIVE_REMOTE, 'drive', 'scope=drive',
                       '--config', conf], stdin=subprocess.DEVNULL, capture_output=True,
                      text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise NetworkError('timeout')
    except FileNotFoundError:
        raise NetworkError('missing', 'rclone')
    except OSError as exc:
        raise NetworkError('failed', str(exc))
    try:
        os.chmod(conf, 0o600)
    except OSError:
        pass
    if done.returncode != 0 or gdrive_state(conf=conf, tool=True) != 'ready':
        raise NetworkError('failed', _last_line(done.stderr) or 'no token')
