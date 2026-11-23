"""Whether Spark Update's own timer is the updater on this PC.

  spark  spark-update.timer is enabled: it downloads and stages SparkOS images and updates
         Flatpak apps (files/scripts/spark-update.sh turns it on in the image).
  none   it is off (a per-user install somewhere else, or something is wrong).

Read from which timers are enabled, so it is always what the PC really does."""

import os

from .core import Env

SPARK, NONE = 'spark', 'none'


def timer_enabled(env: Env, name: str, user: bool = False) -> bool:
    folders = ('/etc/systemd/user', '/usr/lib/systemd/user') if user else \
        ('/etc/systemd/system', '/usr/lib/systemd/system')
    return any(os.path.lexists(env.path(f'{f}/timers.target.wants/{name}')) for f in folders)


def engine(env: Env) -> str:
    return SPARK if timer_enabled(env, 'spark-update.timer') else NONE
