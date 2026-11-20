"""Paths, the log, running commands (every one is logged), and dates for people."""

import json
import logging
import os
import re
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import APP_NAME, APP_SLUG, SYSTEM_LOG, VERSION

log = logging.getLogger(APP_SLUG)


class Env:
    """The machine Spark Update looks at. With a root folder (tests, --root), every absolute
    path is read under it and status comes from JSON files there instead of commands."""

    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root) if root else None

    @property
    def fake(self) -> bool:
        return self.root is not None

    def path(self, p: str) -> str:
        if not self.root:
            return p
        return os.path.join(self.root, p.lstrip('/'))

    def read(self, p: str) -> Optional[str]:
        try:
            with open(self.path(p), encoding='utf-8', errors='replace') as f:
                return f.read()
        except OSError:
            return None

    def read_json(self, p: str) -> Optional[Any]:
        text = self.read(p)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None


# ─── Folders and the log ───────────────────────────────────────

def _xdg_dir(variable: str, fallback: str, create: bool = True) -> str:
    base = os.environ.get(variable) or os.path.join(os.path.expanduser('~'), fallback)
    path = os.path.join(base, APP_SLUG)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def config_dir() -> str:
    return _xdg_dir('XDG_CONFIG_HOME', '.config')


def state_dir() -> str:
    return _xdg_dir('XDG_STATE_HOME', os.path.join('.local', 'state'))


def cache_dir() -> str:
    return _xdg_dir('XDG_CACHE_HOME', '.cache')


def user_log_path() -> str:
    return os.path.join(state_dir(), f'{APP_SLUG}.log')


class JsonLines(logging.Formatter):
    """One JSON object per line, for `ujust update`: it follows uupd's journal through
    `jq 'fromjson? | ...description...'`, which drops plain text."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({'level': record.levelname.lower(),
                           'description': super().format(record)})


def setup_logging(system: bool = False, env: Optional[Env] = None) -> str:
    """The user's log in ~/.local/state/spark-update, or for the background run as root
    /var/log/spark-update (readable by everyone, so the window can show it)."""
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        log.removeHandler(h)
    path = (env or Env()).path(SYSTEM_LOG) if system else user_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=1,
                                      encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
        log.addHandler(handler)
        if system:
            os.chmod(path, 0o644)
    except OSError:
        log.addHandler(logging.NullHandler())
    if system and not sys.stdout.isatty():
        # the journal gets the same lines (systemd captures stderr)
        err = logging.StreamHandler(sys.stderr)
        err.setFormatter(JsonLines() if os.environ.get('SPARK_UPDATE_LOG_JSON') == '1'
                         else logging.Formatter('%(message)s'))
        log.addHandler(err)
    log.info("--- %s %s (python %s, uid %s) ---", APP_NAME, VERSION, sys.version.split()[0],
             os.getuid() if hasattr(os, 'getuid') else '?')
    return path


def run(cmd: Sequence[str], timeout: float = 3600, quiet: bool = False,
        env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """Run a command and log it, its exit code and the end of its output (every command
    Spark Update runs is in its log). Returns (code, stdout, stderr); code 127 when it can't start, 124 on timeout."""
    log.info("$ %s", ' '.join(cmd))
    try:
        proc = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                              env=env, stdin=subprocess.DEVNULL)
        code, out, err = proc.returncode, proc.stdout or '', proc.stderr or ''
    except FileNotFoundError as exc:
        code, out, err = 127, '', str(exc)
    except subprocess.TimeoutExpired as exc:
        code = 124
        out = exc.stdout.decode(errors='replace') if isinstance(exc.stdout, bytes) else ''
        err = f"stopped after {int(timeout)} s"
    except OSError as exc:
        code, out, err = 126, '', str(exc)
    # quiet: the command and its exit code only, unless it failed
    lines = [line for line in (out + '\n' + err).strip().splitlines() if line.strip()]
    tail = [] if quiet and code == 0 else lines[-12:]
    log.info("  exit %s%s", code, ''.join(f"\n  | {line}" for line in tail))
    return code, out, err


# ─── Small JSON files ──────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
    return {}


def save_json(path: str, data: Dict[str, Any], mode: Optional[int] = None) -> bool:
    """Write a temp file and swap it in, so an interrupted save keeps the old one."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        if mode is not None:
            os.chmod(path + '.tmp', mode)
        os.replace(path + '.tmp', path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("could not write %s: %s", path, exc)
        return False


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_UPDATE_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


# ─── Dates for people (local time: the PC's own clock) ─────────

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def day(ts: Optional[float]) -> str:
    """'Nov 17, 2026'"""
    if not ts:
        return "—"
    t = time.localtime(ts)
    return f"{MONTHS[t.tm_mon - 1]} {t.tm_mday}, {t.tm_year}"


def when(ts: Optional[float], now: Optional[float] = None) -> str:
    """'today 04:12', 'yesterday 22:05', 'Nov 17 04:12'"""
    if not ts:
        return "never"
    now = time.time() if now is None else now
    t, n = time.localtime(ts), time.localtime(now)
    clock = f"{t.tm_hour:02d}:{t.tm_min:02d}"
    if (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday):
        return f"today {clock}"
    y = time.localtime(now - 86400)
    if (t.tm_year, t.tm_yday) == (y.tm_year, y.tm_yday):
        return f"yesterday {clock}"
    return f"{MONTHS[t.tm_mon - 1]} {t.tm_mday} {clock}"


def parse_time(value: Any) -> Optional[float]:
    """Epoch seconds from a number or an RFC 3339 string ('2026-11-17T08:01:02Z')."""
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if not isinstance(value, str) or not value:
        return None
    match = re.match(r'(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?$',
                     value.strip())
    if not match:
        return None
    import calendar
    y, mo, d, h, mi, s = (int(match.group(i)) for i in range(1, 7))
    ts = calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0))
    tz = match.group(7)
    if tz and tz != 'Z':
        sign = 1 if tz[0] == '+' else -1
        digits = tz[1:].replace(':', '')
        ts -= sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return float(ts)


def which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def short(items: List[str], n: int = 3) -> str:
    return ', '.join(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else '')
