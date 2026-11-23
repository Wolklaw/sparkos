"""The actions: what each one says before it runs, and the terminal commands. Each action
names exactly what it will run and what it touches, and runs only after a confirmation.

There is no stop, disable or file editing, and no one-click failback: failback opens a terminal
with the command typed and waits for the owner to press Enter. Updating and rebooting a whole
machine are there only for machines whose config allows them (allow = ["update", "reboot"]).
An update runs in a terminal window, where the package manager lists what changes and asks
before it does anything."""

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


UPDATE_COMMANDS = {'apt': "sudo apt update && sudo apt full-upgrade",
                   'dnf': "sudo dnf upgrade --refresh"}


def update_command(manager: str) -> Optional[str]:
    """The update line for the server's package manager, None when the probe found none."""
    return UPDATE_COMMANDS.get(manager)


def update_remote(command: str) -> str:
    """The update in a terminal: it runs at once (the package manager still asks before it
    changes anything), then a normal shell stays open to read the result or reboot."""
    return 'bash -c ' + shlex.quote(f"{command}\necho\nexec bash -l")


def confirm_update(machine: Machine, manager: str, updates: Optional[float],
                   security: Optional[float]) -> Confirm:
    command = update_command(manager) or ''
    lines = [t('confirm.runs', command=f"{ssh_shown(machine)} {command}")]
    if updates is not None:
        lines.append(t('confirm.update_count', n=int(updates), security=int(security or 0)))
    lines.append(t('confirm.update_touches'))
    return Confirm(t('confirm.update_title', machine=machine.name),
                   t('confirm.update_body', machine=machine.name),
                   '\n\n'.join(lines), t('action.update_open'))


REBOOT_COMMAND = "sudo -n systemctl reboot"


def confirm_reboot(machine: Machine, standbys: List[str]) -> Confirm:
    """standbys: the machines whose failover watches this one; they may take over while it is
    down, and the sites only come back to it through their failback."""
    lines = [t('confirm.runs', command=f"{ssh_shown(machine)} {REBOOT_COMMAND}")]
    if machine.tunnel_hostnames:
        lines.append(t('confirm.reboot_sites', sites=', '.join(machine.tunnel_hostnames)))
    else:
        lines.append(t('confirm.reboot_touches', machine=machine.name))
    for standby in standbys:
        lines.append(t('confirm.reboot_standby', standby=standby, machine=machine.name))
    lines.append(t('confirm.reboot_sudo'))
    return Confirm(t('confirm.reboot_title', machine=machine.name),
                   t('confirm.reboot_body', machine=machine.name),
                   '\n\n'.join(lines), t('action.reboot'))


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
