"""The timer: the systemd drop-in the helper writes, and when the next run is due."""

import datetime as dt
from typing import Any, Dict

from . import config


def calendar(cfg: Dict[str, Any]) -> str:
    sched = cfg["schedule"]
    prefix = f"{sched['weekday']} " if sched["every"] == "weekly" else ""
    return f"{prefix}*-*-* {sched['time']}:00"


def dropin(cfg: Dict[str, Any]) -> str:
    """Replaces the timer's calendar. The empty OnCalendar= clears the one in the unit."""
    return ("# Written by spark-backup-helper. Change the schedule in Spark Backup.\n"
            "[Timer]\nOnCalendar=\n" f"OnCalendar={calendar(cfg)}\n")


def next_run(cfg: Dict[str, Any], now: dt.datetime) -> dt.datetime:
    """The next time the timer fires (it can start up to ten minutes later, or at the next
    start if the PC was off)."""
    sched = cfg["schedule"]
    hour, minute = (int(x) for x in sched["time"].split(":"))
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if sched["every"] == "weekly":
        want = config.WEEKDAYS.index(sched["weekday"])
        at += dt.timedelta(days=(want - now.weekday()) % 7)
        if at <= now:
            at += dt.timedelta(days=7)
    elif at <= now:
        at += dt.timedelta(days=1)
    return at
