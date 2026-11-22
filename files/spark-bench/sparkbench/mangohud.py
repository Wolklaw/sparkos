"""Is MangoHud ready to record, and the fix that makes it so (and its undo).

What is checked:
  - MangoHud on this PC (the image's own copy), and for the Flatpak Steam its Vulkan layer
    org.freedesktop.Platform.VulkanLayer.MangoHud in the branch Steam's runtime uses;
  - the Flatpak Steam starts games with MANGOHUD=1 (its per-user Flatpak override);
  - MangoHud's config, in each place it is read from: the Flatpak Steam reads
    ~/.var/app/com.valvesoftware.Steam/.config/MangoHud/MangoHud.conf, everything else
    ~/.config/MangoHud/MangoHud.conf. It needs logging on a hotkey, a fixed duration, the overlay
    hidden, and an output folder.

The fix changes only those lines of those files, the MANGOHUD variable (and, for an output
folder outside Steam's own folder, access to that folder) in Steam's per-user override, and
creates the output folder. Before it writes, it keeps what was there in
~/.local/state/spark-bench/undo.json; Undo puts it back. Nothing system-wide is touched; the
Vulkan layer is only installed when asked, for this user, from Flathub."""

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import core
from .core import log

STEAM = 'com.valvesoftware.Steam'
LAYER = 'org.freedesktop.Platform.VulkanLayer.MangoHud'
HOST_LIBS = ('/usr/lib64/mangohud/libMangoHud.so', '/usr/lib/mangohud/libMangoHud.so',
             '/usr/lib/x86_64-linux-gnu/mangohud/libMangoHud.so')
SYSTEM_OVERRIDE = os.path.join('/var/lib/flatpak/overrides', STEAM)
MARK = "# Spark Bench: benchmark recording (Undo in Spark Bench puts the old lines back)"

Runner = Callable[[List[str]], Tuple[int, str]]


def run_command(argv: List[str], timeout: float = 20) -> Tuple[int, str]:
    """Run a command, never raising: (exit code, output); 127 when it isn't installed."""
    if shutil.which(argv[0]) is None:
        return 127, ''
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or '') + (p.stderr or '' if p.returncode else '')
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


# ─── Paths ────────────────────────────────────────────────────

def steam_dir() -> str:
    return os.path.join(core.home(), '.var', 'app', STEAM)


def steam_config() -> str:
    return os.path.join(steam_dir(), '.config', 'MangoHud', 'MangoHud.conf')


def host_config() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(core.home(), '.config')
    return os.path.join(base, 'MangoHud', 'MangoHud.conf')


def user_override() -> str:
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(core.home(), '.local', 'share')
    return os.path.join(base, 'flatpak', 'overrides', STEAM)


def default_output_folder(steam_flatpak: bool) -> str:
    """Inside Steam's own folder when Steam is a Flatpak: the sandbox can always write there,
    and this PC can read it."""
    if steam_flatpak:
        return os.path.join(steam_dir(), 'benchmark')
    return os.path.join(core.home(), 'Benchmarks')


def undo_path() -> str:
    return os.path.join(core.state_dir(), 'undo.json')


# ─── MangoHud's config file ───────────────────────────────────

def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding='utf-8', errors='replace', newline='') as f:
            return f.read()                   # newline='': Undo puts back the exact bytes
    except OSError:
        return None


def parse(text: Optional[str]) -> Dict[str, str]:
    """key -> value ('' for a bare flag like no_display). Comments are left out; a key set
    twice keeps the last value, as MangoHud does."""
    out: Dict[str, str] = {}
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, _, value = line.partition('=')
        out[key.strip()] = value.strip()
    return out


def wanted(hotkey: str, duration: int, folder: str) -> Dict[str, Optional[str]]:
    """The lines Spark Bench needs. None is a bare flag."""
    return {'toggle_logging': hotkey, 'log_duration': str(int(duration)), 'no_display': None,
            'output_folder': folder, 'log_interval': '0', 'autostart_log': '0'}


def _line(key: str, value: Optional[str]) -> str:
    return key if value is None else f"{key}={value}"


def _is_set(values: Dict[str, str], key: str, value: Optional[str]) -> bool:
    if key not in values:
        # log_interval and autostart_log are 0 when left out
        return key in ('log_interval', 'autostart_log') and value == '0'
    if value is None:
        return values[key] not in ('0', 'false')
    return values[key] == value


def edit(text: Optional[str], want: Dict[str, Optional[str]]) -> Tuple[str, List[str]]:
    """The file with Spark Bench's lines in place, and the lines that changed. Other lines are
    kept as they are; a key already in the file is changed where it is."""
    values = parse(text)
    lines = (text or '').splitlines()
    out, changed, done = [], [], set()
    for line in lines:
        stripped = line.strip()
        key = stripped.partition('=')[0].strip() if stripped and not stripped.startswith('#') \
            else None
        if key in want and not _is_set(values, key, want[key]):
            if key in done:
                continue                      # a second copy of a key being changed: drop it
            done.add(key)
            new = _line(key, want[key])
            out.append(new)
            changed.append(new)
            continue
        if key in want:
            done.add(key)
        out.append(line)
    missing = [k for k in want if k not in done and not _is_set(values, k, want[k])]
    if missing:
        if out and out[-1].strip():
            out.append('')
        out.append(MARK)
        for key in missing:
            out.append(_line(key, want[key]))
            changed.append(_line(key, want[key]))
    return '\n'.join(out) + '\n', changed


# ─── What is there now ────────────────────────────────────────

@dataclass
class ConfigState:
    path: str
    target: str                         # 'steam' or 'host'
    exists: bool
    values: Dict[str, str]
    missing: List[str]                  # lines the fix would write


@dataclass
class Report:
    host_mangohud: bool = False
    flatpak: bool = False
    steam_flatpak: bool = False
    steam_branch: str = ''              # e.g. 25.08, the runtime Steam runs on
    layer_branches: List[str] = field(default_factory=list)
    env_enabled: bool = False           # MANGOHUD=1 in Steam's overrides
    env_where: str = ''                 # 'user' or 'system'
    configs: List[ConfigState] = field(default_factory=list)
    output_folder: str = ''             # the folder the fix writes (and the app watches)
    output_folders: List[str] = field(default_factory=list)   # every folder a config names
    undo_available: bool = False

    @property
    def layer_ok(self) -> bool:
        return not self.steam_flatpak or (self.steam_branch in self.layer_branches
                                          if self.steam_branch else bool(self.layer_branches))

    @property
    def configs_ok(self) -> bool:
        return bool(self.configs) and all(not c.missing for c in self.configs)

    @property
    def ready(self) -> bool:
        if not self.configs:
            return False
        if self.steam_flatpak and not (self.layer_ok and self.env_enabled):
            return False
        return self.configs_ok

    @property
    def fixable(self) -> bool:
        return bool(self.configs) and (not self.configs_ok or
                                       (self.steam_flatpak and not self.env_enabled))


def _override_env(text: Optional[str]) -> Optional[str]:
    """The MANGOHUD value in a Flatpak override file, or None."""
    section = ''
    for line in (text or '').splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section == '[Environment]' and line.startswith('MANGOHUD='):
            return line.partition('=')[2].strip()
    return None


def _filesystems(text: Optional[str]) -> List[str]:
    for line in (text or '').splitlines():
        if line.strip().startswith('filesystems='):
            return [p for p in line.split('=', 1)[1].strip().split(';') if p]
    return []


def inspect(settings: Dict, runner: Runner = run_command,
            system_override: str = SYSTEM_OVERRIDE) -> Report:
    r = Report()
    r.host_mangohud = bool(shutil.which('mangohud')) or any(os.path.exists(p) for p in HOST_LIBS)
    code, out = runner(['flatpak', '--version'])
    r.flatpak = code == 0
    if r.flatpak:
        code, out = runner(['flatpak', 'info', '--show-runtime', STEAM])
        if code == 0 and out.strip():
            r.steam_flatpak = True
            r.steam_branch = out.strip().splitlines()[0].rsplit('/', 1)[-1]
        code, out = runner(['flatpak', 'list', '--runtime', '--columns=application,branch'])
        if code == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == LAYER and parts[1] not in r.layer_branches:
                    r.layer_branches.append(parts[1])
    user_value = _override_env(read_text(user_override()))
    system_value = _override_env(read_text(system_override))
    if user_value is not None:
        r.env_enabled, r.env_where = user_value == '1', 'user'
    elif system_value is not None:
        r.env_enabled, r.env_where = system_value == '1', 'system'

    targets = []
    if r.steam_flatpak:
        targets.append((steam_config(), 'steam'))
    if r.host_mangohud:
        targets.append((host_config(), 'host'))
    folder = choose_output_folder(settings, r.steam_flatpak, [p for p, _ in targets])
    r.output_folder = folder
    want = wanted(settings.get('hotkey') or '', settings.get('duration') or 0, folder)
    for path, target in targets:
        text = read_text(path)
        values = parse(text)
        need = dict(want)
        if values.get('output_folder'):
            need.pop('output_folder')         # their own folder stays; it is watched too
        missing = [_line(k, v) for k, v in need.items() if not _is_set(values, k, v)]
        r.configs.append(ConfigState(path=path, target=target, exists=text is not None,
                                     values=values, missing=missing))
        of = values.get('output_folder')
        if of:
            of = os.path.expanduser(of)
            if of not in r.output_folders:
                r.output_folders.append(of)
    if folder not in r.output_folders:
        r.output_folders.insert(0, folder)
    r.undo_available = os.path.exists(undo_path())
    return r


def choose_output_folder(settings: Dict, steam_flatpak: bool, configs: List[str]) -> str:
    """The settings' folder; else the one the first config already names; else the default."""
    if settings.get('output_folder'):
        return os.path.expanduser(settings['output_folder'])
    for path in configs:
        value = parse(read_text(path)).get('output_folder')
        if value:
            return os.path.expanduser(value)
    return default_output_folder(steam_flatpak)


# ─── The fix ──────────────────────────────────────────────────

@dataclass
class Change:
    kind: str                     # 'file', 'override', 'folder'
    path: str
    lines: List[str]              # what changes, for people
    new_text: Optional[str] = None
    argv: Optional[List[str]] = None


def plan(report: Report, settings: Dict) -> List[Change]:
    """Everything the fix would do, nothing done yet."""
    changes: List[Change] = []
    folder = report.output_folder
    want = wanted(settings.get('hotkey') or '', settings.get('duration') or 0, folder)
    for c in report.configs:
        if not c.missing:
            continue
        need = dict(want)
        if c.values.get('output_folder'):
            need.pop('output_folder')
        new_text, lines = edit(read_text(c.path), need)
        changes.append(Change('file', c.path, lines, new_text=new_text))
    if not os.path.isdir(folder):
        changes.append(Change('folder', folder, [folder]))
    if report.steam_flatpak:
        args, lines = [], []
        if not report.env_enabled:
            args.append('--env=MANGOHUD=1')
            lines.append('MANGOHUD=1')
        if not _inside(folder, steam_dir()) and \
                folder not in _filesystems(read_text(user_override())):
            args.append(f'--filesystem={folder}')
            lines.append(f'filesystem {folder}')
        if args:
            changes.append(Change('override', user_override(), lines,
                                  argv=['flatpak', 'override', '--user'] + args + [STEAM]))
    return changes


def _inside(path: str, folder: str) -> bool:
    path, folder = os.path.abspath(path), os.path.abspath(folder)
    return path == folder or path.startswith(folder + os.sep)


def _sha(text: Optional[str]) -> Optional[str]:
    return None if text is None else hashlib.sha256(text.encode('utf-8')).hexdigest()


def apply(changes: List[Change], runner: Runner = run_command) -> List[str]:
    """Do the planned changes. Returns the errors (empty when it all worked). What was there
    before is saved first, so Undo works even if a step fails."""
    record = core.read_json(undo_path(), {})
    record.setdefault('files', {})
    record.setdefault('folders', [])
    record['time'] = time.time()
    for ch in changes:
        if ch.kind in ('file', 'override') and ch.path not in record['files']:
            # the first fix's "before" is what Undo goes back to
            record['files'][ch.path] = {'before': read_text(ch.path)}
    core.write_json(undo_path(), record)
    errors = []
    for ch in changes:
        try:
            if ch.kind == 'file':
                core.write_text(ch.path, ch.new_text or '')
            elif ch.kind == 'folder':
                created = _make_dirs(ch.path)
                record['folders'] = record['folders'] + [p for p in created
                                                         if p not in record['folders']]
            elif ch.kind == 'override':
                code, out = runner(ch.argv or [])
                if code != 0:
                    errors.append(f"{' '.join(ch.argv or [])}: {out.strip() or code}")
        except OSError as exc:
            errors.append(f"{ch.path}: {exc}")
    for path in record['files']:
        record['files'][path]['after'] = _sha(read_text(path))
    core.write_json(undo_path(), record)
    log.info("fix applied: %s; errors: %s", [c.path for c in changes], errors)
    return errors


def _make_dirs(path: str) -> List[str]:
    """Create a folder and its missing parents; returns the folders that were created."""
    created, p = [], os.path.abspath(path)
    while not os.path.exists(p):
        created.append(p)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    os.makedirs(path, exist_ok=True)
    return list(reversed(created))


def record_layer_install(ref: str) -> None:
    record = core.read_json(undo_path(), {})
    record.setdefault('files', {})
    record.setdefault('folders', [])
    record['layer'] = ref
    record['time'] = time.time()
    core.write_json(undo_path(), record)


def layer_ref(report: Report) -> str:
    return f"{LAYER}//{report.steam_branch}" if report.steam_branch else LAYER


def install_layer(report: Report, runner: Runner = run_command) -> Tuple[bool, str]:
    """Install the MangoHud Vulkan layer for the Flatpak Steam, for this user, from Flathub."""
    ref = layer_ref(report)
    code, out = runner(['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub', ref])
    if code == 0:
        record_layer_install(ref)
    return code == 0, out


def undo_summary() -> List[str]:
    """What Undo would put back, for people; also says when a file changed since the fix."""
    from .text import t
    record = core.read_json(undo_path(), {})
    lines = []
    for path, item in record.get('files', {}).items():
        before = item.get('before')
        changed_since = item.get('after') and _sha(read_text(path)) != item.get('after')
        key = 'undo.remove_file' if before is None else 'undo.restore_file'
        lines.append(t(key, path=core.short_path(path)) + (' (*)' if changed_since else ''))
    for folder in reversed(record.get('folders', [])):
        lines.append(t('undo.remove_folder', path=core.short_path(folder)))
    if record.get('layer'):
        lines.append(t('undo.uninstall', ref=record['layer']))
    return lines


def undo(runner: Runner = run_command) -> List[str]:
    """Put back what the fix changed. Returns the errors."""
    record = core.read_json(undo_path(), {})
    errors = []
    for path, item in record.get('files', {}).items():
        before = item.get('before')
        try:
            if before is None:
                if os.path.exists(path):
                    os.unlink(path)
            else:
                core.write_text(path, before)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    for folder in reversed(record.get('folders', [])):
        try:
            os.rmdir(folder)
        except OSError:
            pass                          # not empty (recordings in it): it stays
    if record.get('layer'):
        code, out = runner(['flatpak', 'uninstall', '--user', '-y', '--noninteractive',
                            record['layer']])
        if code != 0:
            errors.append(f"flatpak uninstall {record['layer']}: {out.strip() or code}")
    if not errors:
        try:
            os.unlink(undo_path())
        except OSError:
            pass
    log.info("undo: errors %s", errors)
    return errors


def pretty_key(key: str) -> str:
    """MangoHud's 'Control_L+F11' as people write it: 'Ctrl+F11'."""
    names = {'control_l': 'Ctrl', 'control_r': 'Ctrl', 'control': 'Ctrl', 'shift_l': 'Shift',
             'shift_r': 'Shift', 'alt_l': 'Alt', 'alt_r': 'Alt', 'super_l': 'Super'}
    return '+'.join(names.get(p.lower(), p) for p in key.split('+')) if key else '—'
