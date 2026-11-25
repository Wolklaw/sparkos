"""Network places and online accounts: sftp:// and smb:// servers, and Google Drive.

How it works: KIO (the same workers Dolphin uses: kio-extras' sftp and smb, kio-gdrive) is
mounted as an ordinary folder by kio-fuse, which is already in the image. kio-fuse answers
`org.kde.KIOFuse.VFS.mountUrl(url)` on the session bus with a local path under
$XDG_RUNTIME_DIR/kio-fuse-XXXX/. From there every feature of the app (listing, open, copy to
and from with progress and cancel, drag and drop) works on that path like on any folder, so
nothing here touches the file operations. Everything that can wait on a network runs in a
thread; the window only ever hears back through the bridge.

Passwords: never in settings.json and never in a bookmark. They go to the Secret Service
(KWallet or GNOME Keyring) through `secret-tool`, with the password on its standard input
(never on a command line).
"""

import logging
import os
import re
import shutil
import sqlite3
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


class NetworkError(Exception):
    """code: timeout | failed | no_kio | address; detail is the system's own words."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


# ─── where the mounts are ────────────────────────────────────

def runtime_dir() -> str:
    return os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'


def split_remote(path: str) -> Optional[Tuple[str, str]]:
    """('/run/user/1000/kio-fuse-AbC/sftp/me@host', 'sftp://me@host') for a path inside a
    kio-fuse mount, or None. The first folder below the mount is the scheme and the second
    the server (or the account list for gdrive)."""
    prefix = runtime_dir().rstrip('/') + '/kio-fuse-'
    if not path.startswith(prefix):
        return None
    parts = path[len(runtime_dir().rstrip('/')) + 1:].split('/')
    # parts: ['kio-fuse-AbC', scheme, host, ...]
    if len(parts) < 2 or not parts[1]:
        return None
    scheme = parts[1]
    base_parts = parts[:3] if scheme != 'gdrive' and len(parts) >= 3 and parts[2] else parts[:2]
    base = '/'.join([runtime_dir().rstrip('/')] + base_parts)
    if scheme == 'gdrive':
        label = 'Google Drive'
    else:
        label = f"{scheme}://{unquote(parts[2])}" if len(parts) >= 3 and parts[2] else scheme + '://'
    return base, label


def is_remote(path: str) -> bool:
    return bool(path) and path.startswith(runtime_dir().rstrip('/') + '/kio-fuse-')


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
        """For kio-fuse only; carries the password when there is one."""
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


# ─── mounting through kio-fuse ───────────────────────────────

class KioFuse:
    """The kio-fuse side: ask it for the local path of a URL. D-Bus activation starts it."""
    NAME, PATH, IFACE = 'org.kde.KIOFuse', '/org/kde/KIOFuse', 'org.kde.KIOFuse.VFS'

    def mount(self, url: str, timeout: float = CONNECT_TIMEOUT) -> str:
        try:
            import gi
            gi.require_version('Gio', '2.0')
            from gi.repository import Gio, GLib
        except (ImportError, ValueError):
            raise NetworkError('no_kio', 'gi')
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            reply = bus.call_sync(self.NAME, self.PATH, self.IFACE, 'mountUrl',
                                  GLib.Variant('(s)', (url,)), GLib.VariantType('(s)'),
                                  Gio.DBusCallFlags.NONE, int(timeout * 1000), None)
        except GLib.Error as exc:
            text = exc.message or ''
            if 'ServiceUnknown' in text or 'not provided' in text or 'No such' in text:
                raise NetworkError('no_kio', text)
            if 'Timeout' in text or 'timed out' in text.lower():
                raise NetworkError('timeout')
            raise NetworkError('failed', _scrub(text, url))
        path = reply.unpack()[0]
        if not path:
            raise NetworkError('failed', '')
        return path


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
    backend = backend or KioFuse()
    done, value = _within(timeout, lambda: backend.mount(server.url(password), timeout))
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

def accounts_db() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home(), '.config')
    return os.path.join(base, 'libaccounts-glib', 'accounts.db')


def gdrive_worker_present() -> bool:
    for base in ('/usr/lib64/qt6/plugins/kf6/kio', '/usr/lib/qt6/plugins/kf6/kio',
                 '/usr/lib64/qt6/plugins/kf6/kio/'):
        if os.path.exists(os.path.join(base, 'gdrive.so')):
            return True
    return False


def google_accounts(db: Optional[str] = None) -> int:
    """How many Google accounts KDE's Online Accounts has switched on (read-only look at
    the accounts database; 0 when there is none)."""
    path = db or accounts_db()
    if not os.path.exists(path):
        return 0
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)
        try:
            row = conn.execute("SELECT COUNT(*) FROM Accounts WHERE provider='google' "
                               "AND enabled=1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


def gdrive_state(worker: Optional[bool] = None, db: Optional[str] = None) -> str:
    """'none' (kio-gdrive isn't installed), 'no-account' or 'ready'."""
    if not (gdrive_worker_present() if worker is None else worker):
        return 'none'
    return 'ready' if google_accounts(db) else 'no-account'


def account_setup_command() -> Optional[List[str]]:
    """Opens KDE's Online Accounts page (Spark Settings hides it from the menu, but takes
    it as --kde kcm_kaccounts)."""
    if shutil.which('spark-settings'):
        return ['spark-settings', '--kde', 'kcm_kaccounts']
    if shutil.which('kcmshell6'):
        return ['kcmshell6', 'kcm_kaccounts']
    return None


def open_account_setup() -> bool:
    cmd = account_setup_command()
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True
