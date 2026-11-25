"""What the panel clock needs from Spark Clock, without copying any of it: the next alarm.

Spark Clock is its own app (files/spark-clock) installed in /usr/lib/spark-clock, or per user in
~/.local/lib/spark-clock. Its `sparkclock` package knows how alarms are stored and when each
next rings; this module imports it from wherever it is and asks. If Spark Clock isn't there the
answer is None and the panel just shows the time."""

import os
import sys
import time

CANDIDATES = (
    os.path.expanduser('~/.local/lib/spark-clock'),
    '/usr/lib/spark-clock',
)


def _modules():
    for base in CANDIDATES:
        if os.path.isfile(os.path.join(base, 'sparkclock', 'store.py')):
            if base not in sys.path:
                sys.path.append(base)
            try:
                from sparkclock import schedule, store
                return schedule, store
            except Exception:
                return None
    return None


def next_alarm(now=None):
    """(epoch seconds, label) of the next enabled alarm, or None."""
    mods = _modules()
    if mods is None:
        return None
    schedule, store = mods
    now = time.time() if now is None else now
    try:
        config = store.load_config()
        best = None
        for raw in config.get('alarms', []):
            alarm = store.clean_alarm(raw)
            if not alarm['enabled']:
                continue
            when = schedule.next_alarm_time(alarm, now)
            if when is not None and (best is None or when < best[0]):
                best = (when, alarm['label'])
        return best
    except Exception:
        return None


def clock_command():
    for exe in ('/usr/bin/spark-clock', os.path.expanduser('~/.local/bin/spark-clock')):
        if os.access(exe, os.X_OK):
            return [exe]
    return None
