"""The actions: what each one says before it runs, and the terminal commands. Each action
names exactly what it will run and what it touches, and runs only after a confirmation.

There is no stop, disable, reboot, file editing or package install, and no one-click failback:
failback opens a terminal with the command typed and waits for the owner to press Enter."""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .config import USER, Machine
from .core import WINDOWS, log
from .text import t


@dataclass
class Confirm:
    title: str
    message: str
    detail: str
    button: str


def restart_command(scope: str, unit: str) -> str:
    if scope == USER:
        return f"systemctl --user restart {unit}"
    return f"sudo -n systemctl restart {unit}"


def ssh_shown(machine: Machine) -> str:
    port = f" -p {machine.port}" if machine.port else ""
    return f"ssh{port} {machine.host}"


def confirm_restart(machine: Machine, scope: str, unit: str) -> Confirm:
    lines = [t('confirm.runs', command=f"{ssh_shown(machine)} {restart_command(scope, unit)}")]
    if machine.is_tunnel(scope, unit):
        if machine.tunnel_hostnames:
            lines.append(t('confirm.tunnel_sites', sites=', '.join(machine.tunnel_hostnames)))
        else:
            lines.append(t('confirm.tunnel_unlisted'))
    else:
        lines.append(t('confirm.touches_unit', unit=unit))
    if scope != USER:
        lines.append(t('confirm.sudo'))
    return Confirm(t('confirm.restart_title', unit=unit, machine=machine.name),
                   t('confirm.restart_body', unit=unit, machine=machine.name),
                   '\n\n'.join(lines), t('action.restart'))


def confirm_terminal(machine: Machine) -> Confirm:
    return Confirm(t('confirm.terminal_title', machine=machine.name),
                   t('confirm.terminal_body', machine=machine.name),
                   t('confirm.runs', command=ssh_shown(machine)) + '\n\n' +
                   t('confirm.terminal_touches'), t('action.terminal'))


def confirm_failback(machine: Machine) -> Confirm:
    command = machine.failover.failback if machine.failover else ''
    return Confirm(t('confirm.failback_title', machine=machine.name),
                   t('confirm.failback_body'),
                   t('confirm.typed', command=command, machine=ssh_shown(machine)) + '\n\n' +
                   t('confirm.failback_touches'), t('action.failback_open'))


def typed_not_run(command: str) -> str:
    """A remote bash line that puts command on the prompt, editable, without running it. Enter
    runs it; Ctrl+C drops it. Either way a normal shell follows."""
    prompt = '(press Enter to run) $ '
    inner = (f"read -e -i {shlex.quote(command)} -p {shlex.quote(prompt)} line "
             '&& eval "$line"\nexec bash -l')
    return 'bash -c ' + shlex.quote(inner)


def terminal_argv(machine: Machine, remote: Optional[str] = None,
                  ssh: Optional[str] = None) -> List[str]:
    """The command that opens a terminal window running ssh to machine (and remote there, if
    given). Spark Terminal on SparkOS, another terminal on other Linux desktops; on Windows, a new
    console window (Windows Terminal when it is the default terminal)."""
    inner = [ssh or 'ssh']
    if machine.port:
        inner += ['-p', str(machine.port)]
    inner += ['-t', '--', machine.host] if remote else ['--', machine.host]
    if remote:
        inner.append(remote)
    if WINDOWS:
        return inner                     # started with CREATE_NEW_CONSOLE
    for term, flag in (('spark-terminal', '-e'), ('konsole', '-e'), ('x-terminal-emulator', '-e'),
                       ('gnome-terminal', '--'), ('xterm', '-e')):
        if shutil.which(term):
            return [term, flag] + inner
    return []


def open_terminal(machine: Machine, remote: Optional[str] = None) -> bool:
    argv = terminal_argv(machine, remote)
    if not argv:
        return False
    log.info("terminal: %s", ' '.join(shlex.quote(a) for a in argv))
    try:
        if WINDOWS:
            subprocess.Popen(argv, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        else:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True,
                             cwd=os.path.expanduser('~'))
        return True
    except OSError as exc:
        log.warning("terminal failed: %s", exc)
        return False
