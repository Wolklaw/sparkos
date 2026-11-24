"""spark-backup-helper: everything that needs root. Started by systemd (run) or by the window
through pkexec (the rest).

  spark-backup-helper run                    one backup now, in this process (the service)
  spark-backup-helper start                  start the service in the background
  spark-backup-helper save-config            new settings on stdin: validate, save, set the timer
  spark-backup-helper remove-snapshot NAME   delete one snapshot of /home

Settings are validated before anything is written, and a snapshot name has to be one this
app would have made, so a window with a bug can't get the helper to touch anything else."""

import os
import subprocess
import sys
from typing import List, Optional

from . import TIMER_DROPIN, config, schedule
from .engine import Backup, BackupError
from .runner import Runner

SERVICE = "spark-backup.service"
TIMER = "spark-backup.timer"


def _systemctl(*args: str) -> int:
    try:
        return subprocess.run(["systemctl", *args], timeout=60).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def dropin_path() -> str:
    return os.environ.get("SPARK_BACKUP_DROPIN") or TIMER_DROPIN


def save_config(text: str, systemctl=None) -> int:
    systemctl = systemctl or _systemctl
    try:
        data = config.loads(text)
    except config.ConfigError as exc:
        print(f"spark-backup-helper: not saved: {exc}", file=sys.stderr)
        return 2
    config.save(data)
    path = dropin_path()
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(schedule.dropin(data))
    systemctl("daemon-reload")
    if data["enabled"]:
        return 0 if systemctl("enable", "--now", TIMER) == 0 else 1
    systemctl("disable", "--now", TIMER)
    return 0


def run_now() -> int:
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print(f"spark-backup-helper: {exc}", file=sys.stderr)
        return 2
    try:
        report = Backup(cfg, Runner()).run()
    except BackupError as exc:
        print(f"spark-backup-helper: {exc}", file=sys.stderr)
        return 3 if str(exc) == "busy" else 1
    print(f"snapshot {report['snapshot'] or '-'}, copy {report['copy']}, "
          f"{report['removed']} removed here, {report['removed_copies']} removed there"
          + (f", error: {report['error']}" if report["error"] else ""))
    return 0 if report["ok"] else 1


def remove_snapshot(name: str) -> int:
    from .engine import exclusive
    try:
        cfg = config.load()
        backup = Backup(cfg, Runner())
        with exclusive(backup.lock_path()):
            backup.remove_local(name)
    except (BackupError, config.ConfigError) as exc:
        print(f"spark-backup-helper: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["run"]:
        return run_now()
    if argv[:1] == ["start"]:
        return _systemctl("start", "--no-block", SERVICE)
    if argv[:1] == ["save-config"]:
        return save_config(sys.stdin.read(config.MAX_FILE_BYTES + 1))
    if len(argv) == 2 and argv[0] == "remove-snapshot":
        return remove_snapshot(argv[1])
    print("usage: spark-backup-helper run | start | save-config < settings.json | "
          "remove-snapshot NAME", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
