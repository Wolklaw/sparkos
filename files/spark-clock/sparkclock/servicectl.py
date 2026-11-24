"""Starting the background service from the window: through its systemd user unit when it is
installed, else as a plain detached process (which lasts until logout)."""

import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from . import core

UNIT = 'spark-clock.service'


def unit_installed() -> bool:
    config = os.environ.get('XDG_CONFIG_HOME') or os.path.join(core.home(), '.config')
    return any(os.path.isfile(os.path.join(base, 'systemd', 'user', UNIT))
               for base in (config, '/etc', '/usr/lib')) or \
        os.path.isfile('/usr/lib/systemd/user/' + UNIT)


def start() -> Tuple[bool, Optional[str]]:
    """Start the service now (and, with the unit, at every login). (True, None) or (False, why)."""
    systemctl = shutil.which('systemctl')
    if systemctl and unit_installed():
        done = subprocess.run([systemctl, '--user', 'enable', '--now', UNIT],
                              capture_output=True, text=True, timeout=20)
        if done.returncode == 0:
            return True, None
        return False, (done.stderr or done.stdout).strip() or f"systemctl exit {done.returncode}"
    launcher = os.path.join(core.lib_dir(), 'spark_clock.py')
    try:
        subprocess.Popen([sys.executable, launcher, '--daemon'], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as exc:
        return False, str(exc)
    return True, None
