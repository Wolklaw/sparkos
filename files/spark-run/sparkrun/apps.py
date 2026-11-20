"""Installed Windows apps: one prefix each under ~/.local/share/spark-run/prefixes/<slug>,
a spark-run.json beside its drive_c, an icon read from the program, and a menu entry in
~/.local/share/applications. Also "Run once", in a shared prefix of its own.

Everything here works without a display, so the command line and CI use it directly; the
window (ui.py) runs the same functions in a thread.
"""

import datetime
import io
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import APP_ID, APP_SLUG, errors, lnk, pe, sources, wine as winemod
from .core import (applications_dir, data_dir, ensure, folder_size, log, name_from_file,
                   prefixes_dir, read_json, remove_tree, run_once_prefix, slugify, write_json,
                   write_text)
from .errors import Problem
from .fetch import FetchError

META = 'spark-run.json'
ICON = 'icon.png'
ICON_ICO = 'icon.ico'
ENTRY_PREFIX = f'{APP_ID}.app-'
SKIP = re.compile(r'(?i)(^|[^a-z])(unins\d*|uninstall\w*|uninst|remove|setup|install(er)?|'
                  r'update[rs]?|updater|autoupdate|crash\w*|report\w*|helper|readme|help|'
                  r'website|homepage|license|licence|feedback|repair|vc_?redist\w*|'
                  r'dotnet\w*|ndp\d+\w*|directx\w*|dxsetup)([^a-z]|$)')
BS = chr(92)            # a backslash
WATCH_SECONDS = 12
SILENT = {'NSIS': ['/S'], 'Inno Setup': ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
          'WiX': ['/quiet', '/norestart'], 'Squirrel': ['--silent'],
          'InstallShield': ['/s'], 'Advanced Installer': ['/exenoui', '/qn']}     # how long a start is watched for an early failure

Report = Callable[..., None]          # report(stage_key, **values)
Choose = Callable[[List['Candidate']], Optional['Candidate']]


class RunError(Exception):
    def __init__(self, problem: Problem):
        super().__init__(problem.key)
        self.problem = problem


@dataclass
class Candidate:
    name: str
    path: str                 # Windows path, C:\...
    unix: str
    score: int = 0
    arguments: str = ''


@dataclass
class App:
    slug: str
    name: str
    program: str              # Windows path of the .exe the menu entry opens
    arguments: str = ''
    windows: str = winemod.DEFAULT_WINDOWS
    dxvk: bool = False
    source: str = ''
    added: str = ''
    wine: str = ''
    wm_class: str = ''
    candidates: List[Dict[str, str]] = field(default_factory=list)

    @property
    def prefix(self) -> str:
        return os.path.join(prefixes_dir(), self.slug)

    @property
    def drive_c(self) -> str:
        return os.path.join(self.prefix, 'drive_c')

    @property
    def icon(self) -> Optional[str]:
        for name in (ICON, ICON_ICO):
            path = os.path.join(self.prefix, name)
            if os.path.isfile(path):
                return path
        return None

    @property
    def entry(self) -> str:
        return os.path.join(applications_dir(), f'{ENTRY_PREFIX}{self.slug}.desktop')

    def unix_program(self) -> Optional[str]:
        return lnk.windows_to_unix(self.prefix, self.program)

    def to_json(self) -> Dict:
        return {'name': self.name, 'program': self.program, 'arguments': self.arguments,
                'windows': self.windows, 'dxvk': self.dxvk, 'source': self.source,
                'added': self.added, 'wine': self.wine, 'wm_class': self.wm_class,
                'candidates': self.candidates}

    def save(self) -> None:
        write_json(os.path.join(self.prefix, META), self.to_json())


# ─── Listing ─────────────────────────────────────────────────

def load(slug: str) -> Optional[App]:
    if not slug or '/' in slug or slug.startswith('.'):
        return None
    data = read_json(os.path.join(prefixes_dir(), slug, META))
    if not data.get('program'):
        return None
    return App(slug=slug, name=str(data.get('name') or slug), program=str(data['program']),
               arguments=str(data.get('arguments') or ''),
               windows=str(data.get('windows') or winemod.DEFAULT_WINDOWS),
               dxvk=bool(data.get('dxvk')), source=str(data.get('source') or ''),
               added=str(data.get('added') or ''), wine=str(data.get('wine') or ''),
               wm_class=str(data.get('wm_class') or ''),
               candidates=[c for c in data.get('candidates') or [] if isinstance(c, dict)])


def all_apps() -> List[App]:
    try:
        names = os.listdir(prefixes_dir())
    except OSError:
        return []
    found = [load(n) for n in names]
    return sorted((a for a in found if a), key=lambda a: a.name.lower())


def unique_slug(name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while os.path.exists(os.path.join(prefixes_dir(), slug)):
        slug = f'{base}-{n}'
        n += 1
    return slug


# ─── Wine, set up on first use ───────────────────────────────

def ensure_wine(report: Report, cancel: Optional[threading.Event] = None) -> winemod.Wine:
    need = winemod.needs_download()
    if need:
        report('setup', size=sum(d.size for d in need), names=', '.join(d.name for d in need))

    def progress(stage: str, done: int, total: int) -> None:
        report('progress.' + stage, done=done, total=total)

    try:
        return winemod.setup(progress, cancel)
    except FetchError as exc:
        raise RunError(Problem(f'error.fetch_{exc.kind}', {'detail': exc.detail})) from exc
    except winemod.WineError as exc:
        raise RunError(Problem('error.no_wine', {'detail': exc.detail})) from exc


def _prepare_prefix(wine: winemod.Wine, prefix: str, report: Report, windows: str,
                    log_path: str) -> None:
    if wine.prefix_ready(prefix):
        return
    if os.path.isdir(prefix):
        remove_tree(prefix)               # a half-made prefix from an interrupted run
    report('prefix')
    try:
        wine.create_prefix(prefix, windows, log_path)
    except (winemod.WineError, OSError) as exc:
        raise RunError(Problem('error.prefix', {'detail': str(exc)})) from exc


# ─── Run once ────────────────────────────────────────────────

def check_file(path: str) -> pe.PEInfo:
    if not os.path.isfile(path):
        raise RunError(Problem('error.no_file', {'file': path}))
    info = pe.inspect(path)
    problem = errors.before_running(info)
    if problem:
        raise RunError(problem)
    return info


def run_once(path: str, args: Optional[List[str]] = None, report: Report = lambda *a, **k: None,
             cancel: Optional[threading.Event] = None) -> 'Launch':
    """Start a program (or an .msi) in the shared run-once prefix."""
    check_file(path)
    wine = ensure_wine(report, cancel)
    prefix = run_once_prefix()
    log_path = winemod.app_log('run-once')
    _prepare_prefix(wine, prefix, report, winemod.DEFAULT_WINDOWS, log_path)
    report('starting', name=os.path.basename(path))
    proc = wine.start(prefix, os.path.abspath(path), args, log_path=log_path)
    return Launch(proc, log_path, wine.has_mono, os.path.basename(path))


# ─── Install ─────────────────────────────────────────────────

def install(path: str, report: Report = lambda *a, **k: None, choose: Optional[Choose] = None,
            name: Optional[str] = None, mode: str = 'auto',
            cancel: Optional[threading.Event] = None, silent: bool = False) -> App:
    """Make a prefix, run the installer in it (or copy a program that needs no installing),
    find the installed program, read its icon, add it to the menu.

    mode: 'auto' (installer if it looks like one, else a program to copy in), 'installer',
    or 'portable'. silent: ask the installer to skip its wizard (see SILENT)."""
    path = os.path.abspath(path)
    info = check_file(path)
    portable = mode == 'portable' or (mode == 'auto' and not info.looks_like_installer)
    wine = ensure_wine(report, cancel)
    guess = name or _clean_product(info.product) or name_from_file(path)
    slug = unique_slug(guess)
    prefix = os.path.join(prefixes_dir(), slug)
    log_path = winemod.app_log(slug)
    ensure(prefixes_dir())
    try:
        _prepare_prefix(wine, prefix, report, winemod.DEFAULT_WINDOWS, log_path)
        if portable:
            report('copying', name=os.path.basename(path))
            found = [_copy_portable(prefix, path, guess)]
        else:
            args = silent_args(info) if silent else []
            found = _run_installer(wine, prefix, path, report, cancel, log_path, info, args)
        if cancel is not None and cancel.is_set():
            raise RunError(Problem('error.cancelled'))
        chosen = found[0]
        if choose and len(found) > 1:
            picked = choose(found)
            if picked is None:
                raise RunError(Problem('error.cancelled'))
            chosen = picked
        report('finishing')
        app = App(slug=slug, name=name or chosen.name or guess, program=chosen.path,
                  arguments=chosen.arguments, source=os.path.basename(path),
                  added=datetime.date.today().isoformat(), wine=wine.version,
                  wm_class=os.path.basename(chosen.unix).lower(),
                  candidates=[{'name': c.name, 'path': c.path, 'arguments': c.arguments}
                              for c in found])
        app.save()
        save_icon(app, chosen.unix)
        write_entry(app)
        log.info("installed %s as %s (%s)", path, slug, app.program)
        return app
    except BaseException:
        log.info("install of %s failed or was cancelled; removing %s", path, prefix)
        try:
            wine.stop(prefix)
        except OSError:
            pass
        remove_tree(prefix)
        raise


def _clean_product(product: str) -> str:
    text = re.sub(r'(?i)\b(setup|installer|install|x64|x86|64-bit|32-bit)\b', '', product)
    return re.sub(r'\s{2,}', ' ', text).strip(' -_.')


def _copy_portable(prefix: str, path: str, name: str) -> Candidate:
    """A program that runs without installing: copy it, and the .dll files beside it, into
    C:\\Program Files\\<name>."""
    folder_name = re.sub(r'[\\/:*?"<>|]+', ' ', name).strip() or 'Program'
    dest = ensure(os.path.join(prefix, 'drive_c', 'Program Files', folder_name))
    shutil.copy2(path, dest)
    src_dir = os.path.dirname(path)
    try:
        for entry in os.scandir(src_dir):
            if entry.is_file() and entry.name.lower().endswith('.dll'):
                shutil.copy2(entry.path, dest)
    except OSError:
        pass
    target = os.path.join(dest, os.path.basename(path))
    return Candidate(name=name, path=lnk.unix_to_windows(prefix, target), unix=target)


def silent_args(info: pe.PEInfo) -> List[str]:
    """The switch each installer maker uses for "install without the wizard"."""
    if info.kind == 'msi':
        return ['/qn']
    return SILENT.get(info.installer or '', [])


def _run_installer(wine: winemod.Wine, prefix: str, path: str, report: Report,
                   cancel: Optional[threading.Event], log_path: str,
                   info: pe.PEInfo, args: Optional[List[str]] = None) -> List[Candidate]:
    before = snapshot(prefix)
    report('installer', name=os.path.basename(path))
    proc = wine.start(prefix, path, args, log_path=log_path)
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            wine.stop(prefix)
            raise RunError(Problem('error.cancelled'))
        time.sleep(0.3)
    code = proc.returncode
    found = find_programs(prefix, before, hint=_clean_product(info.product) or
                          name_from_file(path))
    if not found:
        # some installers hand over to a second process and exit: wait for all of them
        report('waiting')
        if not wine.wait(prefix, cancel):
            raise RunError(Problem('error.cancelled'))
        found = find_programs(prefix, before, hint=name_from_file(path))
    if not found:
        problem = errors.after_exit(code, _tail(log_path), wine.has_mono)
        if problem:
            raise RunError(problem)
        raise RunError(Problem('error.nothing_installed' if code == 0 else
                               'error.installer_failed', {'code': str(code)}))
    return found


def snapshot(prefix: str) -> set:
    """Every .exe and .lnk in the prefix outside C:\\windows (to see what an installer adds)."""
    seen = set()
    drive_c = os.path.join(prefix, 'drive_c')
    for root, dirs, files in os.walk(drive_c, followlinks=False):
        if root == drive_c:
            dirs[:] = [d for d in dirs if d.lower() != 'windows']
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for f in files:
            if f.lower().endswith(('.exe', '.lnk')):
                seen.add(os.path.join(root, f))
    return seen


def find_programs(prefix: str, before: set, hint: str = '') -> List[Candidate]:
    """What the installer added that someone would want to open, best first: Start Menu and
    desktop shortcuts to .exe files first, then new .exe files; never uninstallers,
    updaters, setup or helper programs."""
    after = snapshot(prefix)
    new = after - before
    hint_words = set(re.findall(r'[a-z0-9]{3,}', hint.lower()))
    by_path: Dict[str, Candidate] = {}

    def score_name(text: str) -> int:
        words = set(re.findall(r'[a-z0-9]{3,}', text.lower()))
        return 3 if hint_words & words else 0

    for path in sorted(p for p in new if p.lower().endswith('.lnk')):
        shortcut = lnk.read(path)
        if not shortcut or not shortcut.target.lower().endswith('.exe'):
            continue
        unix = lnk.windows_to_unix(prefix, shortcut.target)
        if not unix and shortcut.relative:
            rel = os.path.normpath(os.path.join(os.path.dirname(path),
                                                shortcut.relative.replace('\\', '/')))
            unix = rel if os.path.isfile(rel) else None
        if not unix or not os.path.isfile(unix):
            continue
        title = os.path.splitext(os.path.basename(path))[0]
        if SKIP.search(title) or SKIP.search(os.path.basename(unix)):
            continue
        score = 10 + score_name(title) + score_name(os.path.basename(unix))
        if os.sep + 'Desktop' + os.sep in path:
            score += 2
        win = lnk.unix_to_windows(prefix, unix)
        old = by_path.get(win.lower())
        if old is None or old.score < score:
            by_path[win.lower()] = Candidate(title, win, unix, score, shortcut.arguments)
    if not by_path:
        for path in sorted(p for p in new if p.lower().endswith('.exe')):
            base = os.path.basename(path)
            if SKIP.search(base):
                continue
            info = pe.inspect(path)
            if info.kind != 'pe':
                continue
            title = info.product or os.path.splitext(base)[0]
            depth = path.count(os.sep)
            score = score_name(title) + score_name(base) + (2 if info.gui else 0) - depth // 4
            try:
                score += min(3, os.path.getsize(path) // (2 << 20))
            except OSError:
                pass
            win = lnk.unix_to_windows(prefix, path)
            by_path[win.lower()] = Candidate(title, win, path, score)
    return sorted(by_path.values(), key=lambda c: (-c.score, c.name.lower()))


# ─── Icons and menu entries ──────────────────────────────────

def save_icon(app: App, exe: str) -> Optional[str]:
    """Read the program's icon from its .exe into the prefix: icon.png (the largest image,
    with Pillow), else icon.ico as it is. None if the program has no icon."""
    for name in (ICON, ICON_ICO):
        try:
            os.unlink(os.path.join(app.prefix, name))
        except OSError:
            pass
    ico = pe.inspect(exe).icon_ico() if exe and os.path.isfile(exe) else None
    if not ico:
        return None
    png = os.path.join(app.prefix, ICON)
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(ico))
        sizes = sorted(getattr(image, 'ico').sizes(), key=lambda s: s[0] * s[1])
        if sizes:
            image.size = sizes[-1]
        image.load()
        image.convert('RGBA').save(png)
        return png
    except Exception as exc:     # noqa: BLE001 - any bad icon falls back to the .ico itself
        log.info("icon to png failed for %s (%s); keeping the .ico", exe, exc)
    ico_path = os.path.join(app.prefix, ICON_ICO)
    with open(ico_path, 'wb') as f:
        f.write(ico)
    return ico_path


def spark_run_command() -> List[str]:
    """How a menu entry starts Spark Run: the installed command, else this script."""
    for candidate in (os.environ.get('SPARK_RUN_BIN'), shutil.which(APP_SLUG)):
        if candidate and os.access(candidate, os.X_OK):
            return [os.path.abspath(candidate)]
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0].endswith('.py') else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'spark_run.py')
    return [sys.executable, script]


def exec_quote(arg: str) -> str:
    """Quote one argument for a desktop entry's Exec key: the spec's quoting rules, then the
    escaping every desktop-entry string value gets (so a backslash is written twice)."""
    if not re.fullmatch(r'[A-Za-z0-9_@%+=:,./-]+', arg):
        arg = '"' + ''.join(BS + c if c in '"`$' + BS else c for c in arg) + '"'
    return arg.replace(BS, BS + BS).replace('%', '%%')


def win_split(text: str) -> List[str]:
    """Split a Windows command line the way programs do (CommandLineToArgvW): spaces
    separate, double quotes group, backslashes are literal except before a quote."""
    args, current, quoted, have, i = [], [], False, False, 0
    while i < len(text):
        c = text[i]
        if c == BS:
            n = 0
            while i < len(text) and text[i] == BS:
                n += 1
                i += 1
            if i < len(text) and text[i] == '"':
                current.append(BS * (n // 2))
                if n % 2:
                    current.append('"')
                    i += 1
            else:
                current.append(BS * n)
            have = True
            continue
        if c == '"':
            quoted, have = not quoted, True
        elif c in (' ', chr(9)) and not quoted:
            if have:
                args.append(''.join(current))
                current, have = [], False
        else:
            current.append(c)
            have = True
        i += 1
    if have:
        args.append(''.join(current))
    return args


def _entry_value(text: str) -> str:
    return text.replace('\\', '\\\\').replace('\n', ' ').replace('\r', ' ').strip()


def write_entry(app: App) -> str:
    cmd = ' '.join(exec_quote(a) for a in spark_run_command())
    icon = app.icon or APP_ID
    lines = [
        '[Desktop Entry]',
        'Type=Application',
        f'Name={_entry_value(app.name)}',
        'Comment=Windows program, runs with Spark Run (Wine)',
        'Comment[fr]=Programme Windows, lancé par Spark Run (Wine)',
        f'Exec={cmd} --open {app.slug} %F',
        f'Icon={_entry_value(icon)}',
        'Terminal=false',
        'Categories=Utility;',
        'Keywords=windows;wine;exe;',
        f'StartupWMClass={_entry_value(app.wm_class)}' if app.wm_class else None,
        f'X-SparkRun-App={app.slug}',
        'Actions=Folder;',
        '',
        '[Desktop Action Folder]',
        'Name=Open its C: folder',
        'Name[fr]=Ouvrir son dossier C:',
        f'Exec={cmd} --folder {app.slug}',
        '',
    ]
    write_text(app.entry, '\n'.join(line for line in lines if line is not None))
    refresh_menu()
    return app.entry


def refresh_menu() -> None:
    folder = applications_dir()
    for cmd in (['update-desktop-database', '-q', folder], ['kbuildsycoca6', '--noincremental']):
        if cmd[0] == 'kbuildsycoca6' and not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
            continue
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                pass


# ─── Opening, options, uninstalling ──────────────────────────

class Launch:
    """A started program, watched for an early failure."""

    def __init__(self, proc: subprocess.Popen, log_path: str, has_mono: bool, name: str):
        self.proc, self.log_path, self.has_mono, self.name = proc, log_path, has_mono, name

    def problem(self, quick: bool) -> Optional[Problem]:
        code = self.proc.poll()
        found = errors.after_exit(code, _tail(self.log_path), self.has_mono)
        if found is None and quick and code not in (None, 0):
            found = Problem('error.exited', {'code': str(code)})
        return found

    def watch(self, seconds: float = WATCH_SECONDS) -> Optional[Problem]:
        """Wait up to `seconds`; a problem if it ended badly in that time."""
        try:
            self.proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            return None
        return self.problem(quick=True)

    def wait(self) -> int:
        return self.proc.wait()


def open_app(app: App, files: Optional[List[str]] = None,
             report: Report = lambda *a, **k: None) -> Launch:
    wine = winemod.installed()
    if wine is None:
        wine = ensure_wine(report)
    exe = app.unix_program()
    if not exe or not os.path.isfile(exe):
        raise RunError(Problem('error.program_gone', {'name': app.name}))
    args = win_split(app.arguments) if app.arguments else []
    args += [lnk.unix_to_windows(app.prefix, f) if os.path.exists(f) else f
             for f in files or []]
    overrides = _dxvk_overrides(app)
    log_path = winemod.app_log(app.slug)
    proc = wine.start(app.prefix, exe, args, overrides=overrides, log_path=log_path,
                      cwd=os.path.dirname(exe))
    return Launch(proc, log_path, wine.has_mono, app.name)


def _dxvk_dlls() -> List[str]:
    folder = os.path.join(os.environ.get('SPARK_RUN_DXVK') or
                          os.path.join(data_dir(), 'runtime', sources.DXVK.folder), 'x64')
    try:
        return sorted(os.path.splitext(n)[0] for n in os.listdir(folder)
                      if n.lower().endswith('.dll'))
    except OSError:
        return ['d3d8', 'd3d9', 'd3d10core', 'd3d11', 'dxgi']


def _dxvk_overrides(app: App) -> Dict[str, str]:
    return {dll: ('n' if app.dxvk else 'b') for dll in _dxvk_dlls()}


def set_dxvk(app: App, on: bool, report: Report = lambda *a, **k: None) -> None:
    """On: copy DXVK's DLLs into the prefix (downloading DXVK once) and load them instead of
    Wine's own. Off: Wine's own Direct3D again (the copies stay, unused)."""
    if on:
        def progress(stage: str, done: int, total: int) -> None:
            report('progress.' + stage, done=done, total=total)
        try:
            folder = winemod.dxvk_dir(progress)
        except FetchError as exc:
            raise RunError(Problem(f'error.fetch_{exc.kind}', {'detail': exc.detail})) from exc
        windows = os.path.join(app.drive_c, 'windows')
        for arch, sub in (('x64', 'system32'), ('x32', 'syswow64')):
            src = os.path.join(folder, arch)
            if not os.path.isdir(src) or not os.path.isdir(os.path.join(windows, sub)):
                continue
            for dll in os.listdir(src):
                if dll.lower().endswith('.dll'):
                    shutil.copy2(os.path.join(src, dll), os.path.join(windows, sub, dll))
    app.dxvk = on
    app.save()


def set_windows(app: App, version: str) -> None:
    wine = winemod.installed()
    if wine is None:
        raise RunError(Problem('error.no_wine'))
    wine.set_windows_version(app.prefix, version)
    app.windows = version
    app.save()


def rename(app: App, name: str) -> None:
    name = name.strip()
    if name and name != app.name:
        app.name = name
        app.save()
        write_entry(app)


def set_program(app: App, windows_path: str, arguments: str = '') -> None:
    unix = lnk.windows_to_unix(app.prefix, windows_path)
    if not unix or not os.path.isfile(unix):
        raise RunError(Problem('error.program_gone', {'name': windows_path}))
    app.program, app.arguments = windows_path, arguments
    app.wm_class = os.path.basename(unix).lower()
    app.save()
    save_icon(app, unix)
    write_entry(app)


def uninstall(app: App) -> None:
    """End its processes, delete the prefix and the menu entry."""
    wine = winemod.installed()
    if wine is not None and os.path.isdir(app.prefix):
        wine.stop(app.prefix)
    for path in (app.entry,):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    remove_tree(app.prefix)
    try:
        os.unlink(winemod.app_log(app.slug))
    except OSError:
        pass
    refresh_menu()
    log.info("uninstalled %s", app.slug)


def disk_use(app: App) -> int:
    return folder_size(app.prefix)


def open_folder(path: str) -> bool:
    for opener in ('xdg-open', 'gio'):
        if shutil.which(opener):
            cmd = [opener, path] if opener == 'xdg-open' else ['gio', 'open', path]
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
                return True
            except OSError:
                continue
    return False


def _tail(path: str, size: int = 256 * 1024) -> str:
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - size))
            return f.read().decode('utf-8', 'replace')
    except OSError:
        return ''
