"""One refresh of every machine and website, as JSON on stdout, for scripts and panels.
`spark-connect --status` runs it, no Tk, no window.

Same SSH calls as the window (BatchMode, never a password prompt, the same shared connection),
the same verdicts, the same words. Read-only: it runs the probe and the website GETs, nothing
else. The JSON carries the labels in the PC's language so a reader needs no translations of its
own."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from . import VERSION, config, core, sites
from .probe import (DOWN, OK, RANK, WARN, Result, hottest, level, memory_used_pct, problems,
                    worst_disk)
from .text import t, verdict_text

FORMAT = 1
LABELS = ('card.up', 'card.down', 'card.trouble', 'card.waiting', 'card.uptime', 'card.load',
          'card.memory', 'card.disk', 'card.temp', 'overview.machines', 'overview.sites',
          'status.no_config', 'status.config_error', 'widget.open')


def down_file() -> str:
    return os.path.join(core.cache_dir(), 'widget-down-since.json')


def remember_down(results: Dict[str, Result], path: Optional[str] = None) -> Dict[str, float]:
    """When each machine stopped answering. Each --status run is fresh, so "Unreachable since"
    would say the current time every minute; the first failure's time is kept in a small file
    in the cache folder until the machine answers again."""
    path = path or down_file()
    try:
        with open(path, encoding='utf-8') as f:
            known = {k: float(v) for k, v in json.load(f).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        known = {}
    since = {name: known.get(name, r.at) for name, r in results.items() if not r.ok}
    if since != known:
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(since, f)
            os.replace(tmp, path)
        except OSError:
            pass
    return since


def machine_entry(machine: config.Machine, result: Optional[Result],
                  down_since: Optional[float] = None) -> Dict[str, Any]:
    found = problems(machine, result, down_since=down_since)
    lvl = level(found) if result is not None else WARN
    if result is None:
        state = t('card.waiting')
    elif not result.ok:
        state = t('card.down')
    else:
        state = t('card.up') if lvl == OK else t('card.trouble')
    entry: Dict[str, Any] = {
        'name': machine.name, 'host': machine.host, 'level': lvl, 'state': state,
        'up': bool(result and result.ok),
        'verdict': verdict_text(found[0]) if found else t('verdict.ok'),
        'more': len(found) - 1 if len(found) > 1 else 0,
        'uptime': '—', 'load': '—', 'memory': '—', 'disk': '—', 'temp': '—',
    }
    data = result.data if result is not None and result.ok else None
    if data:
        disk = worst_disk(data)
        load = data['load'][0]
        entry.update(uptime=core.duration(data['uptime_s']),
                     load='—' if load is None else f"{load:.2f}",
                     memory=core.pct(memory_used_pct(data)),
                     disk=core.pct(disk['pct']) if disk else '—',
                     temp=core.temp(hottest(data)))
    return entry


def site_entry(result: sites.SiteResult) -> Dict[str, Any]:
    return {'name': result.name, 'url': result.url, 'ok': result.ok,
            'level': OK if result.ok else DOWN,
            'status': f"HTTP {result.status}" if result.status is not None
            else (result.error or t('widget.no_answer')),
            'ms': f"{result.ms:.0f} ms" if result.ms is not None else ''}


def collect(cfg: config.Config, transport, check_site=sites.check) -> Dict[str, Any]:
    """Every machine and site at once (one thread each); the slowest one sets the time."""
    jobs = len(cfg.machines) + len(cfg.sites)
    with ThreadPoolExecutor(max_workers=max(1, min(jobs, 16))) as pool:
        machine_jobs = [pool.submit(transport.fetch, m) for m in cfg.machines]
        site_jobs = [pool.submit(check_site, s) for s in cfg.sites]
        results = {m.name: j.result() for m, j in zip(cfg.machines, machine_jobs)}
        since = remember_down(results)
        machines = [machine_entry(m, results[m.name], since.get(m.name)) for m in cfg.machines]
        site_list = [site_entry(j.result()) for j in site_jobs]
    return machines_and_sites(machines, site_list)


def machines_and_sites(machines: List[Dict[str, Any]],
                       site_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    levels = [m['level'] for m in machines] + [s['level'] for s in site_list]
    worst = min(levels, key=lambda lv: RANK[lv], default=OK)
    bad = sum(1 for lv in levels if lv != OK)
    return {'level': worst,
            'summary': t('widget.all_good') if bad == 0 else t('widget.trouble', n=bad),
            'machines': machines, 'sites': site_list}


def report(config_path: Optional[str] = None, transport=None) -> Dict[str, Any]:
    out: Dict[str, Any] = {'format': FORMAT, 'version': VERSION, 'at': time.time(),
                           'checked': t('widget.checked', time=core.clock(time.time())),
                           'labels': {k: t(k) for k in LABELS}}
    path = config_path or core.config_path()
    try:
        cfg = config.load(path)
    except config.ConfigError as exc:
        out.update(level=DOWN, error=str(exc), summary=t('status.config_error'),
                   machines=[], sites=[])
        return out
    if not cfg.found or not (cfg.machines or cfg.sites):
        out.update(level=OK, summary=t('status.no_config'), machines=[], sites=[], empty=True)
        return out
    if transport is None:
        from .transport import SshTransport
        transport = SshTransport()
    out.update(collect(cfg, transport))
    return out


def main(config_path: Optional[str] = None) -> int:
    print(json.dumps(report(config_path), ensure_ascii=False))
    return 0


# ─── --status --json: the small contract Spark Shell's tray reads ─────────

TOTAL_TIMEOUT_S = 40.0       # the whole run, however many machines hang


def _run_all(jobs: List, deadline: float) -> List[Any]:
    """Runs every callable on its own daemon thread; one that is not back by the deadline
    gives None (the process can still exit)."""
    out: List[Any] = [None] * len(jobs)

    def go(i, fn):
        try:
            out[i] = fn()
        except Exception:                       # one broken job must not hide the others
            out[i] = None
    threads = [threading.Thread(target=go, args=(i, fn), daemon=True)
               for i, fn in enumerate(jobs)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(max(0.0, deadline - time.monotonic()))
    return out


def json_report(cfg: config.Config, transport, check_site=sites.check,
                total_timeout: float = TOTAL_TIMEOUT_S, down_path: Optional[str] = None
                ) -> Dict[str, Any]:
    """Every machine probed once and every site checked once, in parallel, in the contract:
    {checked, summary: ok|warn|down|empty, machines: [{name, state: ok|warn|down|rebooting,
    verdict, problems}], sites: [{name, url, state: ok|down, status, ms}]}.
    "rebooting" is never set here: it lives only in the open window's memory."""
    now = time.time()
    if not (cfg.machines or cfg.sites):
        return {'checked': int(now), 'summary': 'empty', 'machines': [], 'sites': []}
    deadline = time.monotonic() + total_timeout
    got = _run_all([(lambda m=m: transport.fetch(m)) for m in cfg.machines]
                   + [(lambda s=s: check_site(s)) for s in cfg.sites], deadline)
    results = {}
    for m, r in zip(cfg.machines, got):
        results[m.name] = r if r is not None else Result(
            m.name, False, problem='timeout', message=f"no answer in {total_timeout:.0f} s")
    since = remember_down(results, down_path)
    machines = []
    for m in cfg.machines:
        found = problems(m, results[m.name], down_since=since.get(m.name))
        lvl = level(found)
        state = 'ok' if lvl == OK else 'down' if lvl == DOWN else 'warn'
        machines.append({'name': m.name, 'state': state,
                         'verdict': verdict_text(found[0]) if found else t('verdict.ok'),
                         'problems': [verdict_text(p) for p in found]})
    site_list = []
    for s, r in zip(cfg.sites, got[len(cfg.machines):]):
        if r is None:
            r = sites.SiteResult(s.name, s.url, error='timed out')
        site_list.append({'name': r.name, 'url': r.url, 'state': 'ok' if r.ok else 'down',
                          'status': r.status,
                          'ms': None if r.ms is None else int(round(r.ms))})
    states = [m['state'] for m in machines] + [s['state'] for s in site_list]
    summary = 'down' if 'down' in states else 'warn' if 'warn' in states else 'ok'
    return {'checked': int(now), 'summary': summary, 'machines': machines, 'sites': site_list}


def json_main(config_path: Optional[str] = None, transport=None) -> int:
    """Prints the one JSON document. Exit 0 normally, 2 when there is nothing to check (no
    machine list, an empty one, or one that doesn't parse: then also an "error" field)."""
    extra: Dict[str, Any] = {}
    try:
        cfg = config.load(config_path or core.config_path())
    except config.ConfigError as exc:
        cfg = config.Config()
        extra['error'] = str(exc)
    if transport is None and (cfg.machines or cfg.sites):
        from .transport import SshTransport
        transport = SshTransport()
    out = json_report(cfg, transport)
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    return 2 if out['summary'] == 'empty' else 0
