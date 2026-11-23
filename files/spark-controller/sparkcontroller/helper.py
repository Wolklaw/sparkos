"""spark-controller-helper: the one thing the window needs root for, run through pkexec.

  pkexec /usr/libexec/spark-controller-helper install-config   (the new configuration on stdin)
  pkexec /usr/libexec/spark-controller-helper release          (stop the service, fans go back)

It validates the configuration before writing it, so a window with a bug (or another program
running as the user) can't put anything but a well-formed fan list into /etc. It starts the
service when at least one fan is enabled and stops it, which hands every fan back, when none is.
"""

import subprocess
import sys
from typing import List, Optional

from . import config

SERVICE = "spark-controller.service"


def _systemctl(*args: str) -> int:
    try:
        return subprocess.run(["systemctl", *args], timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def install_config(text: str, path: str = "") -> int:
    try:
        data = config.loads(text)
    except config.ConfigError as exc:
        print(f"spark-controller-helper: not installed: {exc}", file=sys.stderr)
        return 2
    config.save(data, path)
    if any(entry["enabled"] for entry in data["fans"].values()):
        # restart (not just start): the daemon also notices the new file by itself, this
        # makes sure it is running at all
        _systemctl("start", SERVICE)
        _systemctl("kill", "--signal=SIGHUP", SERVICE)
    else:
        _systemctl("stop", SERVICE)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["install-config"]:
        return install_config(sys.stdin.read(config.MAX_FILE_BYTES + 1))
    if argv[:1] == ["release"]:
        return _systemctl("stop", SERVICE)
    print("usage: spark-controller-helper install-config < fans.json | release", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
