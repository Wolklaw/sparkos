"""What one refresh of one machine says, whatever carried it: the probe's JSON (probe.sh) read
into plain dicts, SSH failures put into words, and the verdict line for the machine.

Nothing here talks to the network or to Tk, so it is all tested against fixtures."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import SYSTEM, USER, Machine

PROBE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe.sh')
PROBE_VERSION = 1

# why a refresh got no data
TIMEOUT = 'timeout'
UNREACHABLE = 'unreachable'
HOSTKEY_CHANGED = 'hostkey_changed'
HOSTKEY_UNKNOWN = 'hostkey_unknown'
AUTH = 'auth'
BAD_OUTPUT = 'bad_output'
NO_SSH = 'no_ssh'
ERROR = 'error'

# how bad, worst first
DOWN, BAD, WARN, OK = 'down', 'bad', 'warn', 'ok'
RANK = {DOWN: 0, BAD: 1, WARN: 2, OK: 3}

DISK_WARN, DISK_BAD = 90.0, 95.0
MEM_WARN = 5.0                      # % available
TEMP_WARN = 85.0
# Readings outside this range come from sensor slots with nothing behind them (a Dell OptiPlex's
# dell_smm reports 126 °C on an unused one) and would raise a false "running hot".
TEMP_PLAUSIBLE = (-40.0, 120.0)
# how long a machine Spark Connect told to reboot may stay silent before it counts as down
REBOOT_GRACE_S = 600.0


_START = re.compile(r'\{\s*"probe"')


def has_probe_output(text: str) -> bool:
    return bool(text and _START.search(text))


class ProbeError(ValueError):
    pass


@dataclass
class Result:
    """One refresh of one machine. data is the probe's JSON when ok; otherwise problem says
    why there is none, message is ssh's own words and fingerprint the host key it showed."""
    machine: str
    ok: bool
    data: Optional[Dict[str, Any]] = None
    problem: Optional[str] = None
    message: str = ''
    fingerprint: Optional[str] = None
    at: float = field(default_factory=time.time)


@dataclass
class Problem:
    level: str
    key: str                        # text.py key, 'verdict.<key>'
    args: Dict[str, Any] = field(default_factory=dict)
    unit: Optional[Tuple[str, str]] = None


# ─── The probe's JSON ─────────────────────────────────────────

def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ''


def parse_probe(text: str) -> Dict[str, Any]:
    """The probe's output as a dict with every key present. Raises ProbeError if it isn't the
    probe's JSON (a login banner or a shell's error in its place, for example)."""
    found = _START.search(text)
    if not found:
        raise ProbeError("no probe output")
    start = found.start()
    try:
        raw = json.loads(text[start:])
    except ValueError as exc:
        raise ProbeError(f"the probe's output isn't valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get('probe') != PROBE_VERSION:
        raise ProbeError("not this version's probe output")
    mem = raw.get('memory') if isinstance(raw.get('memory'), dict) else {}
    load = raw.get('load') if isinstance(raw.get('load'), list) else []
    data: Dict[str, Any] = {
        'time': _num(raw.get('time')),
        'hostname': _text(raw.get('hostname')),
        'os': _text(raw.get('os')),
        'kernel': _text(raw.get('kernel')),
        'systemd': raw.get('systemd') is True,
        'uptime_s': _num(raw.get('uptime_s')),
        'cpus': _num(raw.get('cpus')),
        'load': [_num(v) for v in load[:3]] + [None] * (3 - len(load[:3])),
        'cpu_pct': _num(raw.get('cpu_pct')),
        'memory': {k: _num(mem.get(k)) for k in ('total', 'available', 'swap_total',
                                                  'swap_free')},
        'disks': [], 'temps': [], 'net': [], 'units': [], 'failed': [],
        'tunnel': None, 'failover': None, 'local_checks': [],
        'packages': {'manager': '', 'reboot': None, 'updates': None, 'security': None},
    }
    for d in raw.get('disks') or []:
        if isinstance(d, dict) and _num(d.get('size')):
            size, used = _num(d.get('size')), _num(d.get('used')) or 0.0
            free = _num(d.get('free'))
            # df's Use%: used / (used + available), so root's reserved blocks count as full
            total = used + free if free is not None else size
            data['disks'].append({'mount': _text(d.get('mount')), 'size': size, 'used': used,
                                  'free': free, 'pct': 100.0 * used / total if total else None})
    for tmp in raw.get('temps') or []:
        c = _num(tmp.get('c')) if isinstance(tmp, dict) else None
        if c is not None and TEMP_PLAUSIBLE[0] <= c <= TEMP_PLAUSIBLE[1]:
            data['temps'].append({'name': _text(tmp.get('name')).strip(), 'c': c})
    for n in raw.get('net') or []:
        if isinstance(n, dict) and n.get('iface'):
            data['net'].append({'iface': _text(n['iface']), 'rx': _num(n.get('rx')),
                                'tx': _num(n.get('tx'))})
    for u in raw.get('units') or []:
        if isinstance(u, dict) and u.get('name'):
            unit = {'name': _text(u['name']),
                    'scope': USER if u.get('scope') == USER else SYSTEM,
                    'load': _text(u.get('load')), 'active': _text(u.get('active')),
                    'sub': _text(u.get('sub')), 'result': _text(u.get('result')),
                    'restarts': _num(u.get('restarts')), 'since_s': _num(u.get('since_s')),
                    'description': _text(u.get('description')),
                    'log': [x for x in (u.get('log') or []) if isinstance(x, str)]}
            unit['state'] = unit_state(unit)
            data['units'].append(unit)
    for f in raw.get('failed') or []:
        if isinstance(f, dict) and f.get('name'):
            data['failed'].append({'name': _text(f['name']),
                                   'scope': USER if f.get('scope') == USER else SYSTEM})
    tun = raw.get('tunnel')
    if isinstance(tun, dict):
        data['tunnel'] = {'unit': _text(tun.get('unit')), 'active': _text(tun.get('active')),
                          'connections': _num(tun.get('connections'))}
    fo = raw.get('failover')
    if isinstance(fo, dict):
        data['failover'] = {
            'dir_found': fo.get('dir_found') is True,
            'active_unit': _text(fo.get('active_unit')),
            'active_state': _text(fo.get('active_state')),
            'incidents': [{'name': _text(i.get('name')), 'mtime': _num(i.get('mtime')),
                           'first_line': _text(i.get('first_line'))}
                          for i in (fo.get('incidents') or []) if isinstance(i, dict)],
            'netmon': [x for x in (fo.get('netmon') or []) if isinstance(x, str)],
        }
    pk = raw.get('packages')
    if isinstance(pk, dict):
        manager = _text(pk.get('manager'))
        rb = pk.get('reboot')
        data['packages'] = {
            'manager': manager if manager in ('apt', 'dnf') else '',
            'reboot': {'since': _num(rb.get('since')),
                       'pkgs': [_text(x) for x in (rb.get('pkgs') or []) if isinstance(x, str)]}
            if isinstance(rb, dict) else None,
            'updates': _num(pk.get('updates')),
            'security': _num(pk.get('security')),
        }
    for c in raw.get('local_checks') or []:
        if isinstance(c, dict) and c.get('name'):
            data['local_checks'].append({'name': _text(c['name']), 'url': _text(c.get('url')),
                                         'status': _num(c.get('status')),
                                         'ms': _num(c.get('ms')),
                                         'error': _text(c.get('error'))})
    return data


# unit states, as Spark Connect shows them
RUNNING, FAILED, RESTARTING, STOPPED, MISSING, UNKNOWN = (
    'running', 'failed', 'restarting', 'stopped', 'missing', 'unknown')


def unit_state(unit: Dict[str, Any]) -> str:
    active, sub = unit.get('active', ''), unit.get('sub', '')
    if unit.get('load') == 'not-found':
        return MISSING
    if active == 'failed':
        return FAILED
    if sub == 'auto-restart' or active in ('activating', 'deactivating', 'reloading'):
        return RESTARTING
    if active == 'active':
        return RUNNING
    if active == 'inactive':
        return STOPPED
    return UNKNOWN


# ─── SSH's own failures ───────────────────────────────────────

_FINGERPRINT = re.compile(r'(SHA256:[A-Za-z0-9+/=]{20,}|MD5(?::[0-9a-f]{2}){16})')


def classify_ssh_failure(returncode: Optional[int], stderr: str,
                         timed_out: bool = False) -> Tuple[str, str, Optional[str]]:
    """(problem, message, fingerprint) for an ssh call that gave no probe output."""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    found = _FINGERPRINT.search(stderr)
    fingerprint = found.group(1) if found else None
    low = stderr.lower()
    if 'remote host identification has changed' in low or \
            ('host key for' in low and 'has changed' in low):
        return HOSTKEY_CHANGED, _pick(lines, ('changed', 'offending')), fingerprint
    if 'host key is known' in low or 'host key verification failed' in low:
        return HOSTKEY_UNKNOWN, _pick(lines, ('no ', 'host key', 'verification')), fingerprint
    if timed_out or 'timed out' in low:
        return TIMEOUT, _pick(lines, ('timed out',)) or "no answer in time", None
    if 'permission denied' in low or 'too many authentication failures' in low:
        return AUTH, _pick(lines, ('permission denied', 'authentication')), None
    for marker in ('connection refused', 'no route to host', 'network is unreachable',
                   'could not resolve', 'name or service not known',
                   'temporary failure in name resolution', 'connection closed',
                   'connection reset', 'host is down'):
        if marker in low:
            return UNREACHABLE, _pick(lines, (marker,)), None
    if returncode == 255:
        return UNREACHABLE, lines[-1] if lines else "ssh could not connect", None
    return ERROR, lines[-1] if lines else f"ssh exited with {returncode}", None


def _pick(lines: List[str], words: Tuple[str, ...]) -> str:
    for line in lines:
        if any(w in line.lower() for w in words):
            return line.lstrip('@ ').strip()
    return lines[0] if lines else ''


# ─── The verdict ──────────────────────────────────────────────

def problems(machine: Machine, result: Optional[Result],
             down_since: Optional[float] = None,
             rebooting_since: Optional[float] = None) -> List[Problem]:
    """Everything wrong with one machine, worst first. Empty means all good. rebooting_since:
    when Spark Connect sent this machine a reboot; for REBOOT_GRACE_S after it, not answering
    is the reboot, not an outage."""
    if result is None:
        return [Problem(WARN, 'waiting')]
    if not result.ok and rebooting_since is not None \
            and result.at - rebooting_since < REBOOT_GRACE_S:
        return [Problem(WARN, 'rebooting', {'since': rebooting_since})]
    if not result.ok:
        key = {TIMEOUT: 'unreachable', UNREACHABLE: 'unreachable',
               HOSTKEY_CHANGED: 'hostkey_changed', HOSTKEY_UNKNOWN: 'hostkey_unknown',
               AUTH: 'auth', BAD_OUTPUT: 'bad_output', NO_SSH: 'no_ssh'}.get(
                   result.problem or '', 'error')
        return [Problem(DOWN, key, {'since': down_since or result.at,
                                    'message': result.message})]
    data = result.data or {}
    found: List[Problem] = []
    if not data.get('systemd'):
        found.append(Problem(WARN, 'no_systemd'))
    taken_over = is_taken_over(data)
    for unit in data.get('units', []):
        scope, name, state = unit['scope'], unit['name'], unit['state']
        where = (scope, name)
        if machine.is_takeover_unit(scope, name):
            continue                    # its state is the failover verdict below
        if state == FAILED:
            found.append(Problem(BAD, 'unit_failed', {'unit': name}, where))
        elif state == RESTARTING:
            found.append(Problem(BAD, 'unit_restarting', {'unit': name}, where))
        elif state == MISSING:
            found.append(Problem(WARN, 'unit_missing', {'unit': name}, where))
        elif state == STOPPED:
            found.append(Problem(BAD, 'unit_stopped', {'unit': name}, where))
    watched = {(u['scope'], u['name']) for u in data.get('units', [])}
    others = [f for f in data.get('failed', [])
              if (f['scope'], _bare(f['name'])) not in watched
              and not machine.is_known_failed(f['name'])]
    if len(others) == 1:
        found.append(Problem(BAD, 'unit_failed', {'unit': _bare(others[0]['name'])},
                             (others[0]['scope'], _bare(others[0]['name']))))
    elif others:
        found.append(Problem(BAD, 'units_failed', {'n': len(others)}))
    tun = data.get('tunnel')
    if tun and machine.tunnel and not machine.is_takeover_unit(*machine.tunnel):
        name = machine.tunnel[1]
        if tun['active'] in ('activating', 'deactivating', 'reloading'):
            if not any(p.unit == machine.tunnel for p in found):
                found.append(Problem(BAD, 'unit_restarting', {'unit': name}, machine.tunnel))
        elif tun['active'] != 'active':
            if not any(p.unit == machine.tunnel for p in found):
                found.append(Problem(BAD, 'tunnel_down', {'unit': name}, machine.tunnel))
        elif tun['connections'] == 0:
            found.append(Problem(BAD, 'tunnel_reconnecting', {'unit': name}, machine.tunnel))
    if taken_over:
        found.append(Problem(BAD, 'taken_over'))
    fo = data.get('failover')
    if machine.failover and fo is not None and not fo['dir_found']:
        found.append(Problem(WARN, 'failover_missing'))
    for d in data.get('disks', []):
        p = d.get('pct')
        if p is not None and p >= DISK_WARN:
            found.append(Problem(BAD if p >= DISK_BAD else WARN, 'disk_full',
                                 {'pct': p, 'mount': d['mount']}))
    mem = data.get('memory', {})
    if mem.get('total') and mem.get('available') is not None \
            and 100.0 * mem['available'] / mem['total'] < MEM_WARN:
        found.append(Problem(WARN, 'memory_low',
                             {'pct': 100.0 * mem['available'] / mem['total']}))
    hottest = max((t['c'] for t in data.get('temps', [])), default=None)
    if hottest is not None and hottest >= TEMP_WARN:
        found.append(Problem(WARN, 'hot', {'c': hottest}))
    reboot = data.get('packages', {}).get('reboot')
    if reboot is not None:
        found.append(reboot_problem(reboot))
    for c in data.get('local_checks', []):
        if c['error'] or c['status'] is None:
            found.append(Problem(BAD, 'check_failed', {'name': c['name'],
                                                        'why': c['error'] or '?'}))
        elif c['status'] >= 400:
            found.append(Problem(BAD, 'check_failed', {'name': c['name'],
                                                        'why': f"HTTP {int(c['status'])}"}))
    found.sort(key=lambda p: RANK[p.level])
    return found


def reboot_problem(reboot: Dict[str, Any]) -> Problem:
    """An update that waits on a reboot: a kernel, or the packages that asked (libc6 and the
    like, which every running program still has loaded in its old version). 'day' is the date
    the wait started, so the sentence stays the same from one refresh to the next."""
    day = reboot.get('since')
    pkgs = reboot.get('pkgs') or []
    if any(p.startswith('linux-image') for p in pkgs):
        return Problem(WARN, 'reboot_kernel', {'day': day})
    if pkgs:
        shown = ', '.join(pkgs[:3]) + (' …' if len(pkgs) > 3 else '')
        return Problem(WARN, 'reboot_pkgs', {'day': day, 'pkgs': shown})
    return Problem(WARN, 'reboot_needed', {'day': day})


def level(found: List[Problem]) -> str:
    return found[0].level if found else OK


def is_taken_over(data: Optional[Dict[str, Any]]) -> bool:
    fo = (data or {}).get('failover')
    return bool(fo and fo.get('active_unit') and fo.get('active_state') == 'active')


def _bare(unit: str) -> str:
    return unit[:-8] if unit.endswith('.service') else unit


def worst_disk(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    disks = [d for d in data.get('disks', []) if d.get('pct') is not None]
    return max(disks, key=lambda d: d['pct']) if disks else None


def memory_used_pct(data: Dict[str, Any]) -> Optional[float]:
    mem = data.get('memory', {})
    if not mem.get('total') or mem.get('available') is None:
        return None
    return 100.0 * (1 - mem['available'] / mem['total'])


def hottest(data: Dict[str, Any]) -> Optional[float]:
    return max((t['c'] for t in data.get('temps', [])), default=None)
