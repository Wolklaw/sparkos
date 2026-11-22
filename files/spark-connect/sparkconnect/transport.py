"""How Spark Connect reaches a machine. Only SSH for now: the system ssh client, so the owner's
key, ~/.ssh/config aliases and known_hosts work as they do in a terminal.

Every call uses BatchMode (never a password prompt) and strict host key checking (an unknown or
changed host key stops the call; Spark Connect never accepts one). A later part adds a hub
transport for machines that dial out; it returns the same probe JSON through the same Result,
so the screens don't change."""

import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import LOG_LINES, SSH_TIMEOUT_S
from .config import SYSTEM, USER, Machine
from .core import WINDOWS, cache_dir, log
from .probe import (BAD_OUTPUT, NO_SSH, PROBE_FILE, TIMEOUT, ProbeError, Result,
                    classify_ssh_failure, has_probe_output, parse_probe)

# what a restart came to
DONE, NEEDS_PASSWORD, REFUSED, FAILED = 'done', 'needs_password', 'refused', 'failed'

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
# systemctl --user needs the user's runtime folder; a non-interactive SSH login may not set it
USER_ENV = 'XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" '


@dataclass
class ActionResult:
    outcome: str
    message: str = ''


def ssh_path() -> Optional[str]:
    return shutil.which('ssh')


def probe_text() -> str:
    with open(PROBE_FILE, encoding='utf-8') as f:
        return f.read()


def probe_script(machine: Machine, log_lines: int = LOG_LINES) -> str:
    """The probe with this machine's settings set above it, each quoted for sh. Sent on stdin,
    so nothing from the config is ever parsed as part of a remote command line."""
    def scoped(pair) -> str:
        return f"{pair[0]}:{pair[1]}" if pair else ''

    fo = machine.failover
    values = {
        'SC_UNITS': ' '.join(machine.units),
        'SC_USER_UNITS': ' '.join(machine.user_units),
        'SC_TUNNEL': scoped(machine.tunnel),
        'SC_FAILOVER_DIR': fo.dir if fo else '',
        'SC_ACTIVE_UNIT': scoped(fo.active_unit) if fo else '',
        'SC_NETMON_LOG': fo.netmon_log if fo else '',
        'SC_LOCAL_URLS': ' '.join(f"{n}={u}" for n, u in machine.local_checks),
        'SC_LOG_LINES': str(int(log_lines)),
    }
    head = ''.join(f"{k}={shlex.quote(v)}\n" for k, v in values.items())
    return head + probe_text()


class SshTransport:
    name = 'ssh'

    def __init__(self, ssh: Optional[str] = None, extra_options: Optional[List[str]] = None,
                 multiplex: Optional[bool] = None):
        self.ssh = ssh or ssh_path()
        self.extra = list(extra_options or [])
        # Windows' OpenSSH has no ControlMaster; elsewhere one connection per host is reused
        self.multiplex = (not WINDOWS) if multiplex is None else multiplex

    def base_argv(self, machine: Machine, tty: bool = False) -> List[str]:
        argv = [self.ssh or 'ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=10',
                '-o', 'ServerAliveCountMax=2']
        if self.multiplex:
            argv += ['-o', 'ControlMaster=auto',
                     '-o', f"ControlPath={os.path.join(cache_dir(), 'cm-%C')}",
                     '-o', 'ControlPersist=120']
        argv += self.extra
        if machine.port:
            argv += ['-p', str(machine.port)]
        argv.append('-t' if tty else '-T')
        argv += ['--', machine.host]
        return argv

    def _run(self, machine: Machine, remote: str, stdin: Optional[str] = None,
             timeout: float = SSH_TIMEOUT_S):
        return subprocess.run(self.base_argv(machine) + [remote], input=stdin,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, creationflags=_NO_WINDOW)

    def fetch(self, machine: Machine) -> Result:
        """One refresh: the probe over one SSH call."""
        if not self.ssh:
            return Result(machine.name, False, problem=NO_SSH, message="ssh is not installed")
        try:
            script = probe_script(machine)
        except OSError as exc:
            return Result(machine.name, False, problem=BAD_OUTPUT,
                          message=f"probe.sh is missing: {exc}")
        try:
            done = self._run(machine, 'sh -s', stdin=script)
        except subprocess.TimeoutExpired:
            log.info("%s: timed out", machine.name)
            return Result(machine.name, False, problem=TIMEOUT,
                          message=f"no answer in {SSH_TIMEOUT_S} s")
        except OSError as exc:
            return Result(machine.name, False, problem=NO_SSH, message=str(exc))
        return result_from_ssh(machine.name, done.returncode, done.stdout, done.stderr)

    def restart(self, machine: Machine, scope: str, unit: str) -> ActionResult:
        """Restart one unit the config marks restartable. A system unit goes through sudo -n:
        if sudo wants a password, nothing runs and the outcome says so."""
        if not machine.can_restart(scope, unit):
            return ActionResult(REFUSED, f"{scope}:{unit} is not restartable in the config")
        if scope == USER:
            remote = f"{USER_ENV}systemctl --user restart -- {shlex.quote(unit)}"
        else:
            remote = f"sudo -n systemctl restart -- {shlex.quote(unit)}"
        log.info("%s: restart %s:%s", machine.name, scope, unit)
        try:
            done = self._run(machine, remote, timeout=60)
        except subprocess.TimeoutExpired:
            return ActionResult(FAILED, "no answer in 60 s; the restart may still be running")
        except OSError as exc:
            return ActionResult(FAILED, str(exc))
        err = (done.stderr or '').strip()
        if done.returncode == 0:
            return ActionResult(DONE)
        low = err.lower()
        if scope == SYSTEM and ('password is required' in low or 'terminal is required' in low
                                or 'askpass' in low):
            return ActionResult(NEEDS_PASSWORD, err)
        if done.returncode == 255:
            problem, message, _ = classify_ssh_failure(255, err)
            return ActionResult(FAILED, message)
        return ActionResult(FAILED, err.splitlines()[-1] if err else
                            f"exited with {done.returncode}")

    def tail(self, machine: Machine, scope: str, unit: str, on_line: Callable[[str], None],
             lines: int = 200) -> 'Tail':
        remote = ((USER_ENV + "journalctl --user " if scope == USER else "journalctl ") +
                  f"-u {shlex.quote(unit)} -f -n {int(lines)} -o short-iso --no-pager")
        return Tail(self.base_argv(machine) + [remote], on_line)


def result_from_ssh(name: str, returncode: Optional[int], stdout: str, stderr: str) -> Result:
    if returncode == 0 or has_probe_output(stdout):
        try:
            return Result(name, True, data=parse_probe(stdout))
        except ProbeError as exc:
            if returncode == 0:
                return Result(name, False, problem=BAD_OUTPUT, message=str(exc))
    problem, message, fingerprint = classify_ssh_failure(returncode, stderr)
    log.info("%s: %s (%s)", name, problem, message)
    return Result(name, False, problem=problem, message=message, fingerprint=fingerprint)


class Tail:
    """A live journalctl -f over SSH. Lines arrive on a thread and go to on_line, which must
    hand them to Tk's thread itself. stop() ends the ssh process."""

    def __init__(self, argv: List[str], on_line: Callable[[str], None]):
        self.on_line = on_line
        self.proc: Optional[subprocess.Popen] = None
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                         errors='replace', creationflags=_NO_WINDOW)
        except OSError as exc:
            on_line(f"[{exc}]")
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.on_line(line.rstrip('\n'))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
