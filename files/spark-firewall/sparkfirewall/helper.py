"""spark-firewall-helper: the one thing the window needs root for, run through pkexec.

  pkexec /usr/libexec/spark-firewall-helper apply    (a JSON list of operations on stdin)

It validates the list (ops.py) and runs each operation as exact firewall-cmd, nmcli or systemctl
command lines, with no shell. It stops at the first failure and says which one failed. Adding a
service or a port that is already there, or removing one that isn't, is not a failure.
"""

import sys
from typing import List, Optional

from . import ops as opsmod
from .fw import Runner, default_run

HARMLESS = ("ALREADY_ENABLED", "NOT_ENABLED", "ALREADY_SET", "ZONE_ALREADY_SET")


def running(run: Runner) -> bool:
    return run(["firewall-cmd", "--state"])[0] == 0


def apply(text: str, run: Runner = default_run, out=None, err=None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        todo = opsmod.loads(text)
    except opsmod.OpError as exc:
        print(f"spark-firewall-helper: refused: {exc}", file=err)
        return 2
    live = running(run)
    if not live and any(op["op"] not in ("power", "service", "port") for op in todo):
        print("spark-firewall-helper: the firewall is off, turn it on first", file=err)
        return 3
    for op in todo:
        for step in opsmod.steps(op):
            if step.needs_daemon and not live:
                continue
            code, stdout, stderr = run(step.argv)
            message = (stderr or stdout).strip()
            if code != 0 and not any(word in message for word in HARMLESS):
                print(f"spark-firewall-helper: failed ({opsmod.describe(op)}): "
                      f"{message or f'exit {code}'}", file=err)
                return 1
        print("ok " + opsmod.describe(op), file=out)
    if live and opsmod.needs_reload(todo):
        code, stdout, stderr = run(["firewall-cmd", "--reload"])
        if code != 0:
            print(f"spark-firewall-helper: saved, but the reload failed: "
                  f"{(stderr or stdout).strip()}", file=err)
            return 1
        print("ok reload", file=out)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["apply"]:
        return apply(sys.stdin.read(opsmod.MAX_BYTES + 1))
    print("usage: spark-firewall-helper apply < operations.json", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
