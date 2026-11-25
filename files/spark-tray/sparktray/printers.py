"""Printers through CUPS' own commands (lpstat, cancel, cupsenable), which the image has in
cups-client. They are read-only except cancelling a job and pausing or resuming a printer.
`runner(argv)` runs a program and returns a CompletedProcess (core.run, or a fake in tests)."""

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import core


@dataclass
class Printer:
    name: str
    state: str                 # 'idle', 'printing', 'stopped'
    default: bool = False
    detail: str = ''           # "Paused", "Out of paper", ...
    job: str = ''              # the job it is printing now, e.g. "Office-12"


@dataclass
class Job:
    id: str                    # "Office-12", what `cancel` takes
    printer: str
    user: str
    size: str
    when: str


@dataclass
class PrintState:
    available: bool = False
    printers: List[Printer] = field(default_factory=list)
    jobs: List[Job] = field(default_factory=list)


_PRINTER = re.compile(r'^printer (\S+) (?:is (idle)|now printing (\S+?)|disabled)(?:\.|\s|$)\s*(.*)$')
_JOB = re.compile(r'^(\S+-\d+)\s+(\S+)\s+(\d+)\s+(.*)$')


def parse_printers(text: str) -> List[Printer]:
    printers: Dict[str, Printer] = {}
    default = ''
    for line in text.splitlines():
        m = _PRINTER.match(line.strip())
        if m:
            name, idle, printing, rest = m.groups()
            if printing:
                state = 'printing'
            elif idle:
                state = 'idle'
            else:
                state = 'stopped'
            detail = ''
            if state == 'stopped':
                detail = rest.split(' - ', 1)[-1].strip() if ' - ' in rest else ''
                if not detail or detail == '-':
                    detail = 'Paused'
            elif 'disabled' in rest:
                state, detail = 'stopped', 'Paused'
            printers[name] = Printer(name, state, detail=detail, job=printing or '')
            continue
        m = re.match(r'^system default destination: (\S+)', line.strip())
        if m:
            default = m.group(1)
    if default in printers:
        printers[default].default = True
    return list(printers.values())


def parse_jobs(text: str) -> List[Job]:
    jobs = []
    for line in text.splitlines():
        m = _JOB.match(line.strip())
        if m:
            job_id, user, size, when = m.groups()
            jobs.append(Job(job_id, job_id.rsplit('-', 1)[0], user, size, when.strip()))
    return jobs


class Printing:
    def __init__(self, runner: Callable = core.run):
        self.run = runner

    def state(self) -> PrintState:
        s = PrintState()
        r = self.run(['lpstat', '-p', '-d'])
        if r.returncode == 127:
            return s
        if r.returncode != 0 and 'not running' in (r.stderr or '').lower():
            return s
        s.available = True
        s.printers = parse_printers(r.stdout)
        j = self.run(['lpstat', '-o'])
        if j.returncode == 0:
            s.jobs = parse_jobs(j.stdout)
        return s

    def cancel(self, job_id: str) -> bool:
        return self.run(['cancel', job_id]).returncode == 0

    def set_paused(self, printer: str, paused: bool) -> bool:
        return self.run(['cupsdisable' if paused else 'cupsenable', printer]).returncode == 0


def add_printer_command(which: Callable[[str], Optional[str]] = core.which) -> Optional[List[str]]:
    """Spark Settings' printers page when this PC has it, else system-config-printer."""
    if which('spark-settings'):
        return ['spark-settings', '--page', 'printers']
    if which('system-config-printer'):
        return ['system-config-printer']
    return None
