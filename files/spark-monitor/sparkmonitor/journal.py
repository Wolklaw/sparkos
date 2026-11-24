"""The Logs tab's data: journal entries, plain-language headlines, filters, crashes, failed
units and whether the last boot ended cleanly. No Tk here, so it is all tested without a window.

Memory is capped: at most CAP entries are kept, each with a short list of fields (not the whole
journal record), and a message is cut at MESSAGE_MAX characters."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .procs import desktop_id_from_unit
from .text import t

CAP = 2000                 # entries kept in memory
MESSAGE_MAX = 2000         # characters kept of one message
FIELD_MAX = 600            # ... and of every other field
OUTPUT_FIELDS = ('MESSAGE', 'PRIORITY', 'SYSLOG_IDENTIFIER', '_SYSTEMD_UNIT',
                 '_SYSTEMD_USER_UNIT', 'UNIT', 'USER_UNIT', '_COMM', '_EXE', '_PID',
                 '_CMDLINE', '_UID', '_TRANSPORT', 'CODE_FILE', 'CODE_FUNC', 'COREDUMP_UNIT',
                 'COREDUMP_USER_UNIT')
DETAIL_FIELDS = (('_SYSTEMD_UNIT', 'detail.unit'), ('_SYSTEMD_USER_UNIT', 'detail.user_unit'),
                 ('SYSLOG_IDENTIFIER', 'detail.program'), ('_COMM', 'detail.process'),
                 ('_PID', 'detail.pid'), ('_EXE', 'detail.executable'),
                 ('_CMDLINE', 'detail.command'), ('_TRANSPORT', 'detail.transport'),
                 ('CODE_FILE', 'detail.code_file'), ('CODE_FUNC', 'detail.code_func'))

LEVELS = {'err': 3, 'warning': 4, 'all': 6}      # the Logs tab's three level choices
HOME = re.compile(r'/(?:var/)?home/[^/\s:]+')


@dataclass
class Entry:
    ts: int                          # microseconds since 1970
    prio: int
    message: str
    ident: str = ""
    unit: str = ""
    user_unit: str = ""
    about_unit: str = ""             # UNIT=/USER_UNIT=: the unit a systemd message is about
    comm: str = ""
    cursor: str = ""
    seq: int = 0
    extra: Dict[str, str] = field(default_factory=dict)


def field_text(value: Any, limit: int = FIELD_MAX) -> str:
    """A journal field as text. journalctl writes binary or non-UTF-8 values as a list of byte
    values, and very large ones as null."""
    if value is None:
        return ""
    if isinstance(value, list):
        try:
            value = bytes(int(b) & 0xFF for b in value).decode('utf-8', 'replace')
        except (TypeError, ValueError):
            return ""
    if not isinstance(value, str):
        value = str(value)
    return value if len(value) <= limit else value[:limit] + "…"


def parse_entry(line: str) -> Optional[Entry]:
    line = line.strip()
    if not line.startswith('{'):
        return None
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    if not isinstance(rec, dict):
        return None
    try:
        ts = int(rec.get('__REALTIME_TIMESTAMP') or 0)
    except (TypeError, ValueError):
        ts = 0
    try:
        prio = int(field_text(rec.get('PRIORITY'), 8) or 6)
    except ValueError:
        prio = 6
    message = field_text(rec.get('MESSAGE'), MESSAGE_MAX)
    extra = {}
    for key, _label in DETAIL_FIELDS:
        value = field_text(rec.get(key))
        if value:
            extra[key] = value
    return Entry(ts=ts, prio=max(0, min(7, prio)), message=message,
                 ident=field_text(rec.get('SYSLOG_IDENTIFIER'), 80),
                 unit=field_text(rec.get('_SYSTEMD_UNIT'), 120),
                 user_unit=field_text(rec.get('_SYSTEMD_USER_UNIT'), 120),
                 about_unit=field_text(rec.get('USER_UNIT') or rec.get('UNIT'), 120),
                 comm=field_text(rec.get('_COMM'), 40),
                 cursor=field_text(rec.get('__CURSOR'), 200), extra=extra)


def journal_args(boot: int, level: str, follow: bool, lines: int = CAP) -> List[str]:
    """journalctl's arguments: one boot, one level, the newest `lines`, then live."""
    args = ['journalctl', '-o', 'json', '--no-pager', '-b', str(boot), '-n', str(lines),
            '-p', str(LEVELS.get(level, 4)), '--output-fields=' + ','.join(OUTPUT_FIELDS)]
    if follow:
        args.append('-f')
    return args


# ─── Names and headlines ──────────────────────────────────────

def clean_unit(unit: str) -> str:
    unit = re.sub(r'\.(service|scope)$', '', unit)
    return re.sub(r'@[0-9a-f]{8,}$', '', unit)


def source_name(e: Entry) -> str:
    """The app or service an entry belongs to, in a form a person recognises."""
    if e.ident == 'systemd' and (e.about_unit or e.user_unit or e.unit):
        unit = e.about_unit or e.user_unit or e.unit
    elif e.ident:
        unit = e.ident
    else:
        unit = e.comm or e.user_unit or e.unit
    if not unit:
        return "?"
    desktop = desktop_id_from_unit(unit)
    if desktop:
        return desktop
    return clean_unit(unit)


RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"Out of memory: Killed process \d+ \((.+?)\)"), 'head.oom'),
    (re.compile(r"Process \d+ \((.+?)\) of user \d+ dumped core"), 'head.dumped'),
    (re.compile(r"^(\S+?)\[\d+\]: segfault at"), 'head.segfault'),
    (re.compile(r"amdgpu.*(?:ring \S+ timeout|GPU reset begin|GPU reset succeeded)", re.I),
     'head.gpu_reset'),
    (re.compile(r"(?:blk_update_request: )?I/O error, dev (\S+?),"), 'head.io_error'),
    (re.compile(r"^Failed to start (.+?)\.?$"), 'head.failed_start'),
    (re.compile(r"Failed with result '([^']+)'"), 'head.failed_result'),
    (re.compile(r"Main process exited, code=(killed|dumped), status=(\S+)"), 'head.exited_bad'),
    (re.compile(r"Main process exited, code=exited, status=([1-9]\d*)/"), 'head.exited_code'),
]


def headline(e: Entry) -> str:
    """One plain sentence for the table. The message itself is always in the details."""
    name = source_name(e)
    message = e.message
    for pattern, key in RULES:
        match = pattern.search(message)
        if match:
            groups = match.groups()
            return t(key, name=name, what=groups[0] if groups else '',
                     how=groups[1] if len(groups) > 1 else '')
    first = message.split('\n', 1)[0].strip()
    return first if len(first) <= 220 else first[:219] + "…"


def level_name(prio: int) -> str:
    return t('level.error') if prio <= 3 else t('level.warning') if prio == 4 \
        else t('level.notice') if prio == 5 else t('level.info')


def when(ts: int, full: bool = False) -> str:
    if not ts:
        return "?"
    try:
        stamp = datetime.fromtimestamp(ts / 1e6).astimezone()
    except (OverflowError, OSError, ValueError):
        return "?"
    if full:
        return stamp.strftime('%Y-%m-%d %H:%M:%S ') + (stamp.tzname() or '')
    return stamp.strftime('%m-%d %H:%M:%S')


def matches(e: Entry, app: str, text: str) -> bool:
    """The two filters above the table. `app` matches the app, program or unit name; `text`
    matches the message or the headline. Both ignore case."""
    if app:
        needle = app.lower()
        if not any(needle in s.lower() for s in (source_name(e), e.ident, e.unit, e.user_unit,
                                                 e.comm)):
            return False
    if text:
        needle = text.lower()
        if needle not in e.message.lower() and needle not in headline(e).lower():
            return False
    return True


def scrub(text: str) -> str:
    """Take the user name out of paths before text leaves the window in a copy."""
    return HOME.sub('~', text)


def entry_text(e: Entry) -> str:
    lines = [f"{t('detail.time')}: {when(e.ts, True)}",
             f"{t('detail.level')}: {level_name(e.prio)} ({e.prio})",
             f"{t('detail.app')}: {source_name(e)}"]
    for key, label in DETAIL_FIELDS:
        if key in e.extra:
            lines.append(f"{t(label)}: {e.extra[key]}")
    lines.append(f"{t('detail.message')}: {e.message}")
    return scrub('\n'.join(lines))


# ─── Crashes ──────────────────────────────────────────────────

SIGNALS = {1: 'SIGHUP', 2: 'SIGINT', 3: 'SIGQUIT', 4: 'SIGILL', 5: 'SIGTRAP', 6: 'SIGABRT',
           7: 'SIGBUS', 8: 'SIGFPE', 9: 'SIGKILL', 11: 'SIGSEGV', 13: 'SIGPIPE',
           15: 'SIGTERM', 31: 'SIGSYS'}


@dataclass
class Crash:
    ts: int
    pid: int
    uid: int
    sig: int
    exe: str
    size: Optional[int] = None
    stored: bool = False

    @property
    def app(self) -> str:
        return os.path.basename(self.exe) or "?" if self.exe else "?"

    @property
    def signal_name(self) -> str:
        return SIGNALS.get(self.sig, f"signal {self.sig}")

    @property
    def meaning(self) -> str:
        key = f'signal.{self.sig}'
        text = t(key)
        return t('signal.other') if text == key else text


def parse_crashes(text: Optional[str]) -> List[Crash]:
    """coredumpctl --json=short, newest first."""
    if not text or not text.strip():
        return []
    try:
        rows = json.loads(text)
    except ValueError:
        return []
    out: List[Crash] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            out.append(Crash(ts=int(row.get('time') or 0), pid=int(row.get('pid') or 0),
                             uid=int(row.get('uid') or 0), sig=int(row.get('sig') or 0),
                             exe=str(row.get('exe') or ''),
                             size=row.get('size') if isinstance(row.get('size'), int) else None,
                             stored=row.get('corefile') == 'present'))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda c: -c.ts)
    return out


def crash_args(c: Optional[Crash] = None) -> List[str]:
    if c is None:
        return ['coredumpctl', '--json=short', '--no-pager']
    secs = c.ts // 1_000_000
    return ['coredumpctl', 'info', '--no-pager', f'--since=@{secs}', f'--until=@{secs + 1}',
            f'{c.pid}']


PRIVATE_LINE = re.compile(r'^\s*(Machine ID|Boot ID|Hostname)\s*:', re.I)
OWNER_LINE = re.compile(r'^(\s*(?:Owner )?[UG]ID\s*:\s*\d+)\s*\(.*\)\s*$', re.I)


def scrub_info(text: str) -> str:
    """`coredumpctl info` without the machine ID, boot ID, host name and user name."""
    lines = []
    for line in text.splitlines():
        if PRIVATE_LINE.match(line):
            continue
        lines.append(OWNER_LINE.sub(r'\1', line))
    return scrub('\n'.join(lines))


def crash_report(c: Crash, info: Optional[str], os_line: str) -> str:
    head = [f"{t('report.title')}: {c.app}",
            f"{t('detail.time')}: {when(c.ts, True)}",
            f"{t('crash.signal')}: {c.signal_name}: {c.meaning}",
            f"{t('detail.pid')}: {c.pid}",
            f"{t('detail.executable')}: {scrub(c.exe)}"]
    if os_line:
        head.append(f"SparkOS: {os_line}")
    body = scrub_info(info) if info else t('crash.no_info')
    return '\n'.join(head) + '\n\n' + body + '\n'


# ─── Failed units and a bad last shutdown ─────────────────────

def parse_failed(text: Optional[str], user: bool = False) -> List[str]:
    """Unit names from `systemctl --failed --no-legend --plain`."""
    out = []
    for line in (text or '').splitlines():
        parts = line.split()
        if parts and re.search(r'\.(service|socket|mount|timer|target|path|scope|swap|device)$',
                               parts[0]):
            out.append(parts[0] + (' (user)' if user else ''))
    return out


CLEAN_MARKERS = [re.compile(p) for p in (
    r'Reached target (shutdown|final|reboot|poweroff|halt|exit)\.target',
    r'Reached target .*(Shutdown|Power-Off|Reboot|Final Step)',
    r'^Stopped target (basic|multi-user|sysinit|local-fs)\.target',
    r'^Stopped target (Basic System|Multi-User System|System Initialization|Local File Systems)',
    r'^Journal stopped$', r'^Shutting down\.?$', r'^SYSTEM_SHUTDOWN\b',
    r'^systemd-shutdown\[\d+\]: ', r'^Stopping Journal Service',
)]


def boot_ended_cleanly(tail_json: Optional[str]) -> Tuple[Optional[bool], int]:
    """Read the last lines of the previous boot (journalctl -b -1 -n 300 -o json): did it
    reach its shutdown steps? Returns (clean?, time of the last line). clean is None when
    there is no previous boot to look at. This is a guess from the log: a log cut short for
    another reason reads as unclean."""
    if not tail_json or not tail_json.strip():
        return None, 0
    last = 0
    clean = False
    seen = 0
    for line in tail_json.splitlines():
        e = parse_entry(line)
        if e is None:
            continue
        seen += 1
        last = max(last, e.ts)
        if any(p.search(e.message) for p in CLEAN_MARKERS):
            clean = True
    if not seen:
        return None, 0
    return clean, last
