"""Everything that doesn't need a window: folders, the log, the profile settings, the colour
scheme, which shell to start, the link patterns, and what is running in a terminal."""

import json
import logging
import os
import pwd
import re
import shutil
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple

from . import APP_NAME, APP_SLUG, VERSION

log = logging.getLogger(APP_SLUG)

# ─── Folders and the log ────────────────────────────────────


def _xdg_dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config', create)


def state_dir(create: bool = True) -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'), create)


def setup_logging() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'),
                                      maxBytes=256 * 1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.info("--- %s %s starting (python %s) ---", APP_NAME, VERSION, sys.version.split()[0])


# ─── Profile settings ───────────────────────────────────────

SETTINGS_FILE = 'settings.json'
CURSORS = ('block', 'ibeam', 'underline')
BELLS = ('visual', 'sound', 'off')
FONT_SIZE_RANGE = (6, 48)
SCROLLBACK_RANGE = (0, 1_000_000)      # 0 = none; VTE also takes -1 (unlimited), we don't

DEFAULTS: Dict[str, Any] = {
    "shell": "",                 # empty: the user's login shell
    "start_dir": "",             # empty: the folder Spark Terminal was started from
    "font": "Cascadia Mono",
    "font_size": 11,
    "scrollback": 10000,
    "copy_on_select": True,
    "ctrl_c_v": True,            # Ctrl+C copies a selection, Ctrl+V pastes (pane.py)
    "confirm_close": True,
    "cursor": "block",
    "cursor_blink": True,
    "bell": "visual",
    "glitch": True,
}


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def clean_settings(raw: Any) -> Dict[str, Any]:
    """Settings as the app uses them: every key present, every value of the right kind and in
    range. Anything unknown or broken falls back to the default, so a hand-edited file can
    never stop the terminal from opening."""
    data = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return data
    for key in ('shell', 'start_dir', 'font'):
        value = raw.get(key)
        if isinstance(value, str):
            data[key] = value.strip()
    if not data['font']:
        data['font'] = DEFAULTS['font']
    data['font_size'] = _clamp_int(raw.get('font_size'), *FONT_SIZE_RANGE, DEFAULTS['font_size'])
    data['scrollback'] = _clamp_int(raw.get('scrollback'), *SCROLLBACK_RANGE,
                                    DEFAULTS['scrollback'])
    for key in ('copy_on_select', 'ctrl_c_v', 'confirm_close', 'cursor_blink', 'glitch'):
        if isinstance(raw.get(key), bool):
            data[key] = raw[key]
    if raw.get('cursor') in CURSORS:
        data['cursor'] = raw['cursor']
    if raw.get('bell') in BELLS:
        data['bell'] = raw['bell']
    return data


def load_settings() -> Dict[str, Any]:
    path = os.path.join(config_dir(create=False), SETTINGS_FILE)
    try:
        with open(path, encoding='utf-8') as f:
            return clean_settings(json.load(f))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
    return dict(DEFAULTS)


def save_settings(settings: Dict[str, Any]) -> bool:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    folder = config_dir()
    path = os.path.join(folder, SETTINGS_FILE)
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(clean_settings(settings), f, indent=2)
            f.write('\n')
        os.replace(path + '.tmp', path)
        return True
    except OSError as exc:
        log.warning("could not save %s: %s", path, exc)
        return False


def check_settings(settings: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Problems the settings window shows: (key, the value that's wrong)."""
    problems = []
    shell = settings.get('shell') or ''
    if shell and not resolve_program(shell):
        problems.append(('shell', shell))
    start = settings.get('start_dir') or ''
    if start and not os.path.isdir(os.path.expanduser(start)):
        problems.append(('start_dir', start))
    return problems


# ─── Which shell, where ─────────────────────────────────────


def resolve_program(name: str) -> Optional[str]:
    """Full path of a program given by name or path, or None."""
    name = os.path.expanduser(name)
    if os.sep in name:
        return name if os.path.isfile(name) and os.access(name, os.X_OK) else None
    return shutil.which(name)


def login_shell() -> str:
    """The user's shell: $SHELL, then the password database, then bash, then sh."""
    candidates = [os.environ.get('SHELL') or '']
    try:
        candidates.append(pwd.getpwuid(os.getuid()).pw_shell or '')
    except KeyError:
        pass
    candidates += ['/bin/bash', '/bin/sh']
    for shell in candidates:
        if shell and resolve_program(shell):
            return resolve_program(shell)
    return '/bin/sh'


def shell_argv(settings: Dict[str, Any]) -> List[str]:
    """argv for an interactive shell. A login shell's argv[0] starts with '-' in a real login;
    terminals start a plain interactive shell, as Konsole does."""
    shell = settings.get('shell') or ''
    path = resolve_program(shell) if shell else None
    return [path or login_shell()]


def start_folder(workdir: Optional[str], settings: Dict[str, Any],
                 cwd: Optional[str] = None) -> str:
    """Where a new terminal starts: --workdir, then the profile's folder, then the folder it
    was started from, then home. Anything that isn't a folder is skipped."""
    home = os.path.expanduser('~')
    if cwd is None:
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = home
    for candidate in (workdir, settings.get('start_dir'), cwd, home):
        if candidate:
            path = os.path.abspath(os.path.expanduser(candidate))
            if os.path.isdir(path):
                return path
    return '/'


def child_env(environ: Optional[Dict[str, str]] = None) -> List[str]:
    """The environment for a shell started in a tab, as VTE wants it (KEY=value strings).
    VTE adds TERM, COLORTERM and VTE_VERSION itself; the variables that would make programs
    think they're still in the terminal Spark Terminal was started from go."""
    env = dict(os.environ if environ is None else environ)
    for name in ('COLUMNS', 'LINES', 'TERM', 'COLORTERM', 'TERM_PROGRAM', 'TERM_PROGRAM_VERSION',
                 'KONSOLE_VERSION', 'KONSOLE_DBUS_SERVICE', 'KONSOLE_DBUS_SESSION',
                 'KONSOLE_DBUS_WINDOW', 'SHELL_SESSION_ID', 'WINDOWID', 'GIO_LAUNCHED_DESKTOP_FILE',
                 'GIO_LAUNCHED_DESKTOP_FILE_PID', 'DESKTOP_STARTUP_ID', 'XDG_ACTIVATION_TOKEN',
                 'VTE_VERSION'):
        env.pop(name, None)
    env['TERM_PROGRAM'] = APP_SLUG
    env['TERM_PROGRAM_VERSION'] = VERSION
    return [f'{k}={v}' for k, v in env.items()]


# ─── The colour scheme ──────────────────────────────────────

# The SparkOS scheme, the same colours as files/system/usr/share/konsole/SparkOS.colorscheme
# (Konsole's copy) and the desktop's SparkOS.colors.
SCHEME = {
    'background': '#05040f',
    'foreground': '#f1efff',
    'cursor': '#9be8b8',
    'cursor_text': '#0a0919',
    'highlight': '#9be8b8',
    'highlight_text': '#0a0919',
    'palette': [
        # normal: black red green yellow blue magenta cyan white
        '#141233', '#ff2e88', '#9be8b8', '#f4c95d', '#8ec9ff', '#b9a6ff', '#22d8ff', '#b3b0d2',
        # bright
        '#3c396e', '#ff6eaa', '#bef5d2', '#fade96', '#b9deff', '#d2c6ff', '#78e8ff', '#f1efff',
    ],
}

# The window around the terminals (the desktop's SparkOS colours)
CHROME = {
    'bg': '#0a0919', 'bg2': '#100f26', 'surface': '#141233', 'surface2': '#1b1948',
    'line': 'rgba(236,233,255,.14)', 'line_strong': 'rgba(236,233,255,.3)',
    'text': '#f1efff', 'muted': '#b3b0d2', 'accent': '#9be8b8', 'on_accent': '#0a0919',
    'pink': '#ff9ebb', 'ch_a': '#ff2e88', 'ch_b': '#22d8ff',
}

MONO_FAMILIES = ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Hack", "Noto Sans Mono",
                 "DejaVu Sans Mono", "Liberation Mono", "Monospace")


# ─── Links and file paths in the output ─────────────────────

# PCRE2 patterns VTE matches under the mouse (Ctrl+click opens them).
URL_PATTERN = (r"\b(?:https?|ftp|file|sftp|ssh|smb)://[^\s<>\"'`()\[\]{}]*[^\s<>\"'`()\[\]{}.,;:!?]"
               r"|\bmailto:[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# An absolute path or one from home ("~/"), optionally with :line or :line:column after it,
# as compilers and grep print them. Relative paths are found too when they contain a slash.
PATH_PATTERN = (r"(?:~|\.{1,2})?/[\w.~+@%=-]+(?:/[\w.~+@%=-]*)*(?::\d+){0,2}"
                r"|\b[\w.+@-]+(?:/[\w.+@-]+)+(?::\d+){0,2}")

_LINE_SUFFIX = re.compile(r'(?::\d+){1,2}$')


def path_target(text: str, cwd: Optional[str]) -> Optional[str]:
    """The file or folder a path in the output means, if it exists: ~ expanded, relative paths
    taken from the terminal's current folder, a trailing :line or :line:col dropped."""
    text = text.strip().rstrip('.,;:)')
    for candidate in (text, _LINE_SUFFIX.sub('', text)):
        path = os.path.expanduser(candidate)
        if not os.path.isabs(path):
            if not cwd:
                continue
            path = os.path.join(cwd, path)
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path
    return None


def uri_to_path(uri: Optional[str]) -> Optional[str]:
    """file:///home/a/b%20c -> /home/a/b c (what VTE reports for the shell's folder)."""
    if not uri or not uri.startswith('file://'):
        return None
    from urllib.parse import unquote, urlparse
    parsed = urlparse(uri)
    return unquote(parsed.path) or None


# ─── What is running in a terminal ──────────────────────────


def _proc_name(pid: int, proc: str = '/proc') -> str:
    try:
        with open(f'{proc}/{pid}/comm', encoding='utf-8', errors='replace') as f:
            return f.read().strip()
    except OSError:
        return ''


def running_program(shell_pid: int, foreground_pgid: int, proc: str = '/proc') -> Optional[str]:
    """Name of what's running in the foreground of a terminal other than its shell, or None
    when the shell is waiting for a command. foreground_pgid comes from tcgetpgrp() on the
    terminal; when it is the shell's own group, nothing else is running."""
    if shell_pid <= 0 or foreground_pgid <= 0 or foreground_pgid == shell_pid:
        return None
    return _proc_name(foreground_pgid, proc) or '?'


def process_cwd(pid: int, proc: str = '/proc') -> Optional[str]:
    try:
        return os.readlink(f'{proc}/{pid}/cwd')
    except OSError:
        return None


def command_label(argv: List[str]) -> str:
    """Short name for a tab: the program's own name ('/usr/bin/bash' -> 'bash')."""
    if not argv:
        return ''
    return os.path.basename(argv[0]) or argv[0]
