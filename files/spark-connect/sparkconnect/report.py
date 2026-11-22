"""Copy a report: a plain-text snapshot of one machine to paste into a Claude session or a note.
It holds what the screen shows (services, health, last errors) and nothing else."""

import time
from typing import List, Optional

from . import APP_NAME, VERSION
from . import core
from .config import Machine
from .probe import Result, hottest, is_taken_over, memory_used_pct, problems
from .text import t, verdict_text


def build(machine: Machine, result: Optional[Result], down_since: Optional[float] = None,
          now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    found = problems(machine, result, down_since)
    out: List[str] = [
        f"{machine.name} ({machine.host}), {APP_NAME} {VERSION} report, "
        f"{core.day_clock(now)}",
        "Verdict: " + (verdict_text(found[0]) if found else t('verdict.ok')),
    ]
    for p in found[1:]:
        out.append("         " + verdict_text(p))
    if result is None or not result.ok:
        if result is not None:
            out.append(f"SSH: {result.problem}: {result.message}")
            if result.fingerprint:
                out.append(f"Host key shown by ssh: {result.fingerprint}")
        return '\n'.join(out) + '\n'
    d = result.data or {}
    out.append(f"Refreshed {core.day_clock(result.at)}")
    out.append("")
    out.append("Health")
    out.append(f"  OS: {d['os'] or '?'}, kernel {d['kernel'] or '?'}")
    up = d.get('uptime_s')
    out.append(f"  Up {core.duration(up)}" +
               (f", last boot {core.day_clock(result.at - up)}" if up else ""))
    load = ' '.join('—' if v is None else f"{v:.2f}" for v in d['load'])
    out.append(f"  Load {load} on {int(d['cpus'] or 0)} CPUs, CPU {core.pct(d['cpu_pct'])}")
    mem = d['memory']
    out.append(f"  Memory {core.pct(memory_used_pct(d))} used of {core.size(mem['total'])}, "
               f"swap {core.size((mem['swap_total'] or 0) - (mem['swap_free'] or 0))} used of "
               f"{core.size(mem['swap_total'])}")
    for disk in d['disks']:
        out.append(f"  Disk {disk['mount']}: {core.pct(disk['pct'])} full, "
                   f"{core.size(disk['free'])} free of {core.size(disk['size'])}")
    if d['temps']:
        out.append(f"  Hottest sensor {core.temp(hottest(d))}")
    if d['tunnel']:
        tun = d['tunnel']
        conns = '?' if tun['connections'] is None else int(tun['connections'])
        out.append(f"  Tunnel {tun['unit']}: {tun['active']}, {conns} connections")
    if d['failover']:
        fo = d['failover']
        out.append("  Failover: " + ("TAKEN OVER, serving the sites" if is_taken_over(d)
                                     else "standing by"))
    out.append("")
    out.append("Services")
    for u in d['units']:
        restarts = '' if u['restarts'] is None else f", {int(u['restarts'])} restarts"
        out.append(f"  {u['scope']}:{u['name']}: {u['state']} ({u['active']}/{u['sub']}) "
                   f"for {core.duration(u['since_s'])}{restarts}")
    failed = [f"{f['scope']}:{f['name']}" for f in d['failed']
              if not machine.is_known_failed(f['name'])]
    if failed:
        out.append("  Failed units: " + ', '.join(failed))
    errors = [(u, u['log']) for u in d['units'] if u['state'] != 'running' and u['log']]
    if errors:
        out.append("")
        out.append("Last log lines of units that aren't running")
        for u, lines in errors:
            out.append(f"  {u['scope']}:{u['name']}")
            out.extend(f"    {line}" for line in lines)
    for c in d['local_checks']:
        out.append(f"Check {c['name']}: " + (c['error'] or f"HTTP {int(c['status'] or 0)}, "
                                             f"{int(c['ms'] or 0)} ms"))
    if d['failover'] and d['failover']['incidents']:
        out.append("")
        out.append("Last failover incidents")
        for inc in d['failover']['incidents']:
            out.append(f"  {core.day_clock(inc['mtime'])} {inc['name']}: {inc['first_line']}")
    return '\n'.join(out) + '\n'
