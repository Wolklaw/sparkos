"""Wine itself: getting it (pinned download), making prefixes, running programs in them.

A prefix is one Windows "C: drive" with its own registry. Spark Run gives every installed
app its own, so removing an app removes everything it installed, and one app's settings or
runtimes can't break another.
"""

import ctypes
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Dict, List, Optional

from . import sources
from .core import data_dir, ensure, log, runtime_dir, state_dir, write_text
from .fetch import Progress, fetch

READY_MARK = '.spark-run-ready'
FONTS_MARK = '.spark-run-fonts'
WINDOWS_VERSIONS = ('win11', 'win10', 'win81', 'win8', 'win7', 'winxp')
DEFAULT_WINDOWS = 'win10'

# Libraries Wine loads from Linux (most with dlopen, so ldd on wine doesn't list them).
# (soname, what it's for, needed for most programs)
HOST_LIBS = (
    ('libfreetype.so.6', 'text', True),
    ('libfontconfig.so.1', 'fonts', True),
    ('libX11.so.6', 'windows (X11)', True),
    ('libXext.so.6', 'windows (X11)', True),
    ('libXrender.so.1', 'windows (X11)', False),
    ('libXi.so.6', 'mouse and keyboard (X11)', False),
    ('libXrandr.so.2', 'screen modes', False),
    ('libXcursor.so.1', 'mouse pointers', False),
    ('libXcomposite.so.1', 'windows (X11)', False),
    ('libGL.so.1', 'OpenGL', False),
    ('libvulkan.so.1', 'Vulkan (DXVK, 3D)', False),
    ('libgnutls.so.30', 'secure connections (https)', True),
    ('libpulse.so.0', 'sound', False),
    ('libasound.so.2', 'sound', False),
    ('libgstreamer-1.0.so.0', 'audio and video playback', False),
    ('libcups.so.2', 'printing', False),
)

# Windows fonts that Wine doesn't have, mapped to the system's Noto CJK fonts. Without them an
# embedded Chromium (CEF, as in Amazon Music) can crash on a page with Chinese, Japanese or
# Korean text. The Noto CJK fonts come with SparkOS.
FONT_REPLACEMENTS = (
    ('Noto Sans CJK SC', ('Microsoft YaHei', 'Microsoft YaHei UI', 'SimSun', 'NSimSun',
                          'SimHei')),
    ('Noto Sans CJK TC', ('Microsoft JhengHei', 'Microsoft JhengHei UI', 'PMingLiU',
                          'MingLiU')),
    ('Noto Sans CJK JP', ('Meiryo', 'Meiryo UI', 'MS Gothic', 'MS PGothic', 'MS UI Gothic',
                         'Yu Gothic', 'Yu Gothic UI')),
    ('Noto Sans CJK KR', ('Malgun Gothic', 'Gulim', 'Dotum', 'Batang')),
)


def fonts_reg_lines() -> List[str]:
    """The .reg lines that apply FONT_REPLACEMENTS."""
    lines = [r'[HKEY_CURRENT_USER\Software\Wine\Fonts\Replacements]']
    lines += [f'"{name}"="{target}"' for target, names in FONT_REPLACEMENTS for name in names]
    return lines + ['']


def fonts_version() -> str:
    """What the font marker holds, so a changed table is applied again to old prefixes."""
    return hashlib.sha256('\n'.join(fonts_reg_lines()).encode()).hexdigest()[:16]


class WineError(Exception):
    """kind: 'no_wine', 'prefix', 'exec'"""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail = kind, detail


class Wine:
    def __init__(self, root: str, version: str):
        self.root, self.version = root, version

    @property
    def wine(self) -> str:
        return os.path.join(self.root, 'bin', 'wine')

    @property
    def wineserver(self) -> str:
        return os.path.join(self.root, 'bin', 'wineserver')

    @property
    def mono_dir(self) -> str:
        return os.path.join(self.root, 'share', 'wine', 'mono')

    @property
    def has_mono(self) -> bool:
        return os.path.isdir(os.path.join(self.mono_dir, sources.MONO.folder))

    def ok(self) -> bool:
        return os.access(self.wine, os.X_OK) and os.access(self.wineserver, os.X_OK)

    # ── environment ──

    def env(self, prefix: str, overrides: Optional[Dict[str, str]] = None,
            base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        env = dict(os.environ if base is None else base)
        for key in ('WINELOADER', 'WINESERVER', 'WINEDLLPATH', 'WINEARCH', 'WINEDEBUG',
                    'WINEDLLOVERRIDES'):
            env.pop(key, None)
        env['WINEPREFIX'] = prefix
        env['WINEDEBUG'] = os.environ.get('SPARK_RUN_WINEDEBUG', 'fixme-all')
        dlls = {'winemenubuilder.exe': 'd',    # Spark Run makes the menu entries itself
                'mshtml': 'd'}                 # no Wine Gecko download prompt
        if not self.has_mono:
            dlls['mscoree'] = 'd'              # no Wine Mono download prompt
        dlls.update(overrides or {})
        env['WINEDLLOVERRIDES'] = ';'.join(f'{k}={v}' for k, v in dlls.items())
        env['PATH'] = os.path.join(self.root, 'bin') + os.pathsep + env.get('PATH', '/usr/bin')
        return env

    # ── prefixes ──

    def prefix_ready(self, prefix: str) -> bool:
        return os.path.isfile(os.path.join(prefix, READY_MARK)) and \
            os.path.isdir(os.path.join(prefix, 'drive_c'))

    @property
    def template(self) -> str:
        """A fresh prefix that every new one is copied from (one per Wine version)."""
        return os.path.join(data_dir(), 'template', self.version)

    def create_prefix(self, prefix: str, windows: str = DEFAULT_WINDOWS,
                      log_path: Optional[str] = None) -> None:
        """Make a new prefix: a copy of the template prefix, which is made with wineboot the
        first time (about 20 seconds). `cp --reflink=auto` makes the copy share the
        template's disk space on btrfs, where SparkOS keeps /home, and takes a second;
        elsewhere it is a plain copy."""
        if not self.prefix_ready(self.template):
            self._make_template(log_path)
        parent = ensure(os.path.dirname(prefix))
        tmp = tempfile.mkdtemp(prefix='.new-', dir=parent)
        try:
            log.info("copying the template prefix to %s", prefix)
            done = subprocess.run(['cp', '-a', '--reflink=auto', self.template + '/.', tmp],
                                  capture_output=True, text=True, errors='replace')
            if done.returncode != 0:
                raise WineError('prefix', f"copying the template failed: {done.stderr[-500:]}")
            os.replace(tmp, prefix)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        if windows != DEFAULT_WINDOWS:
            self.set_windows_version(prefix, windows)

    def _make_template(self, log_path: Optional[str] = None) -> None:
        """wineboot a new prefix into a temporary folder, then rename it into place, so a
        half-made template is never copied (and two Spark Runs can't make it at once)."""
        parent = ensure(os.path.dirname(self.template))
        tmp = tempfile.mkdtemp(prefix='.new-', dir=parent)
        try:
            self._wineboot(tmp, DEFAULT_WINDOWS, log_path)
            try:
                os.rename(tmp, self.template)
            except OSError:
                if not self.prefix_ready(self.template):
                    raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for name in os.listdir(parent):               # templates of older Wines
            path = os.path.join(parent, name)
            if name != self.version and not name.startswith('.') and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)

    def _wineboot(self, prefix: str, windows: str, log_path: Optional[str] = None) -> None:
        ensure(prefix)
        out = _log_file(log_path)
        try:
            # winegstreamer off only while the prefix is made: a GStreamer bug can hang it
            env = self.env(prefix, {'winegstreamer': ''})
            log.info("making a prefix with wineboot in %s", prefix)
            code = subprocess.call([self.wine, 'wineboot', '--init'], env=env, stdout=out,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   cwd=prefix)
            self.wait(prefix)
            if code != 0 or not os.path.isfile(os.path.join(prefix, 'system.reg')):
                raise WineError('prefix', f"wineboot exited with {code}")
            reg = os.path.join(prefix, 'drive_c', 'spark-run-defaults.reg')
            write_text(reg, '\r\n'.join([
                'REGEDIT4', '',
                r'[HKEY_CURRENT_USER\Software\Wine\WineDbg]',
                '"ShowCrashDialog"=dword:00000000', '',      # Spark Run explains crashes
                r'[HKEY_CURRENT_USER\Software\Wine]',
                f'"Version"="{windows}"', ''] + fonts_reg_lines()))
            code = subprocess.call([self.wine, 'reg', 'import', r'C:\spark-run-defaults.reg'],
                                   env=env, stdout=out, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, cwd=prefix)
            os.unlink(reg)
            if code != 0:
                log.warning("reg import exited with %s in %s", code, prefix)
            self.wait(prefix)
            if code == 0:
                write_text(os.path.join(prefix, FONTS_MARK), fonts_version() + '\n')
            _own_desktop(prefix)
            write_text(os.path.join(prefix, READY_MARK), self.version + '\n')
        finally:
            if out is not subprocess.DEVNULL:
                out.close()

    def ensure_fonts(self, prefix: str, log_path: Optional[str] = None) -> bool:
        """Apply FONT_REPLACEMENTS to a prefix that doesn't have them yet (prefixes made
        before they existed). Cheap when done: one small file is read. True if applied now."""
        mark = os.path.join(prefix, FONTS_MARK)
        try:
            with open(mark, encoding='utf-8') as f:
                if f.read().strip() == fonts_version():
                    return False
        except OSError:
            pass
        reg = os.path.join(prefix, 'drive_c', 'spark-run-fonts.reg')
        write_text(reg, '\r\n'.join(['REGEDIT4', ''] + fonts_reg_lines()))
        out = _log_file(log_path)
        try:
            code = subprocess.call([self.wine, 'reg', 'import', r'C:\spark-run-fonts.reg'],
                                   env=self.env(prefix), stdout=out, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, cwd=prefix)
            self.wait(prefix)
        finally:
            if out is not subprocess.DEVNULL:
                out.close()
            try:
                os.unlink(reg)
            except OSError:
                pass
        if code != 0:
            log.warning("font reg import exited with %s in %s", code, prefix)
            return False
        write_text(mark, fonts_version() + '\n')
        return True

    def set_windows_version(self, prefix: str, version: str) -> None:
        if version not in WINDOWS_VERSIONS:
            raise ValueError(version)
        subprocess.call([self.wine, 'reg', 'add', r'HKCU\Software\Wine', '/v', 'Version',
                         '/t', 'REG_SZ', '/d', version, '/f'], env=self.env(prefix),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, cwd=prefix)
        self.wait(prefix)

    def query(self, prefix: str, key: str, value: Optional[str] = None) -> str:
        """`wine reg query`, for tests and the self-test."""
        cmd = [self.wine, 'reg', 'query', key] + (['/v', value] if value else [])
        try:
            return subprocess.run(cmd, env=self.env(prefix), capture_output=True, text=True,
                                  errors='replace', timeout=120, cwd=prefix).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ''

    # ── running ──

    def command(self, target: str, args: Optional[List[str]] = None) -> List[str]:
        if target.lower().endswith('.msi'):
            # msiexec wants a Windows path; Wine's Z: drive is the Linux root
            windows = 'Z:' + os.path.abspath(target).replace('/', chr(92))
            return [self.wine, 'msiexec', '/i', windows] + list(args or [])
        return [self.wine, target] + list(args or [])

    def start(self, prefix: str, target: str, args: Optional[List[str]] = None,
              overrides: Optional[Dict[str, str]] = None, log_path: Optional[str] = None,
              cwd: Optional[str] = None) -> subprocess.Popen:
        """Start a Windows program (or an .msi) in a prefix. Its output goes to log_path."""
        out = _log_file(log_path, truncate=True)
        try:
            return subprocess.Popen(self.command(target, args), env=self.env(prefix, overrides),
                                    stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True,
                                    cwd=cwd or os.path.dirname(target) or prefix)
        except OSError as exc:
            raise WineError('exec', str(exc)) from exc
        finally:
            if out is not subprocess.DEVNULL:
                out.close()

    def wait(self, prefix: str, cancel: Optional[threading.Event] = None) -> bool:
        """Wait until every Windows process in the prefix has ended. False if cancelled."""
        proc = subprocess.Popen([self.wineserver, '-w'], env=self.env(prefix),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, cwd=prefix)
        while True:
            try:
                proc.wait(timeout=0.5)
                return True
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    proc.wait()
                    return False

    def stop(self, prefix: str) -> None:
        """End every Windows process in the prefix (before deleting it)."""
        subprocess.call([self.wineserver, '-k'], env=self.env(prefix),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, cwd=prefix if os.path.isdir(prefix) else '/')


def _log_file(path: Optional[str], truncate: bool = False):
    if not path:
        return subprocess.DEVNULL
    ensure(os.path.dirname(path))
    return open(path, 'w' if truncate else 'a', encoding='utf-8', errors='replace')


def _own_desktop(prefix: str) -> None:
    """Wine links the Windows Desktop folder to ~/Desktop, so installers would drop .lnk
    files on the Plasma desktop. Give each prefix a Desktop of its own instead; Documents,
    Downloads, Music, Pictures and Videos stay linked to yours."""
    users = os.path.join(prefix, 'drive_c', 'users')
    try:
        names = os.listdir(users)
    except OSError:
        return
    for name in names:
        desktop = os.path.join(users, name, 'Desktop')
        if os.path.islink(desktop):
            os.unlink(desktop)
            os.makedirs(desktop, exist_ok=True)


# ─── Finding and getting Wine ────────────────────────────────

def installed() -> Optional[Wine]:
    """The Wine Spark Run uses: SPARK_RUN_WINE (a Wine folder, for development) or the pinned
    download. None until it has been downloaded."""
    override = os.environ.get('SPARK_RUN_WINE')
    if override:
        root = os.path.dirname(os.path.dirname(override)) if os.path.isfile(override) \
            else override
        found = Wine(root, 'custom')
        return found if found.ok() else None
    found = Wine(os.path.join(runtime_dir(), sources.WINE.folder), sources.WINE.version)
    return found if found.ok() else None


def needs_download() -> List[sources.Download]:
    """What setup() would download now."""
    wine = installed()
    if wine is None:
        return [sources.WINE, sources.MONO]
    return [] if wine.has_mono or wine.version == 'custom' else [sources.MONO]


def setup(progress: Optional[Progress] = None, cancel: Optional[threading.Event] = None,
          mono: bool = True) -> Wine:
    """Download and unpack Wine (and Wine Mono) if they aren't there. Returns the Wine."""
    wine = installed()
    if wine is None:
        root = fetch(sources.WINE, ensure(runtime_dir()), _tagged(progress, 'wine'), cancel)
        wine = Wine(root, sources.WINE.version)
        if not wine.ok():
            raise WineError('no_wine', f"{root} has no bin/wine")
        _forget_old_wines(root)
    if mono and not wine.has_mono and wine.version != 'custom':
        fetch(sources.MONO, ensure(wine.mono_dir), _tagged(progress, 'mono'), cancel)
    return wine


def dxvk_dir(progress: Optional[Progress] = None,
             cancel: Optional[threading.Event] = None) -> str:
    return fetch(sources.DXVK, ensure(runtime_dir()), _tagged(progress, 'dxvk'), cancel)


def _tagged(progress: Optional[Progress], key: str) -> Optional[Progress]:
    if progress is None:
        return None
    return lambda stage, done, total: progress(f'{key}.{stage}', done, total)


def _forget_old_wines(keep: str) -> None:
    """After an update to the pinned Wine, delete older downloaded Wines (prefixes keep
    working: Wine updates a prefix the first time it runs in it)."""
    folder = os.path.dirname(keep)
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if name.startswith('wine-') and path != keep and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def missing_libs() -> List[tuple]:
    """HOST_LIBS that can't be found on this system."""
    known = set()
    try:
        out = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=10,
                             errors='replace').stdout
        known = {line.split()[0] for line in out.splitlines()[1:] if line.strip()}
    except (OSError, subprocess.TimeoutExpired):
        pass
    missing = []
    for soname, what, needed in HOST_LIBS:
        if soname in known:
            continue
        try:
            ctypes.CDLL(soname)
        except OSError:
            missing.append((soname, what, needed))
    return missing


def app_log(slug: str) -> str:
    return os.path.join(state_dir(), f'{slug}.log')
