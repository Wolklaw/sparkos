"""Waking the PC from sleep for the next alarm.

Setting a wake time needs root, so it is done by a small helper that ships in the SparkOS image
(/usr/libexec/spark-clock-wake, run through pkexec; see files/spark-clock/system). This module
only decides WHEN to wake and asks the helper. It is pure apart from the one subprocess call,
which the tests replace.

  - Only the next ring is armed: the soonest enabled alarm, or snooze that is waiting. One
    wake time at a time; the helper replaces it.
  - The PC wakes LEAD seconds before, so it is up when the alarm rings. Once that moment has
    passed (the PC woke and may doze off again) the wake time moves to the alarm itself.
  - A ring more than MAX_AHEAD away is not armed (the helper refuses more than 8 days).
  - No helper (an image from before this feature) means "unavailable": nothing is called and
    the window says so. Alarms ring as before when the PC is awake.
"""

import os
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core import log
from .schedule import next_alarm_time

HELPER = '/usr/libexec/spark-clock-wake'
POLICY = '/usr/share/polkit-1/actions/dev.wolklaw.SparkClock.wake.policy'
PKEXEC = '/usr/bin/pkexec'
LEAD = 60                  # wake this long before the ring
MIN_AHEAD = 15             # never ask for a wake time closer than this (the helper wants 10)
MAX_AHEAD = 7 * 24 * 3600 + 3600     # inside the helper's 8 days
RETRY = 300                # seconds before trying again after a failure
TIMEOUT = 10

Run = Callable[[List[str]], Tuple[int, str]]


def default_run(argv: List[str]) -> Tuple[int, str]:
    done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT,
                          stdin=subprocess.DEVNULL, check=False)
    return done.returncode, (done.stderr or done.stdout).strip()


def available() -> bool:
    """The helper and its polkit action are both in this image."""
    return os.access(HELPER, os.X_OK) and os.path.isfile(POLICY) and os.access(PKEXEC, os.X_OK)


def next_ring(config: Dict[str, Any], snoozes: List[Dict[str, Any]], now: float) -> Optional[float]:
    """The soonest moment something rings: an enabled alarm or a snooze that is waiting."""
    moments = []
    for alarm in config['alarms']:
        if alarm['enabled']:
            at = next_alarm_time(alarm, now)
            if at is not None:
                moments.append(at)
    for snooze in snoozes:
        at = snooze.get('at')
        if isinstance(at, (int, float)) and at > now:
            moments.append(float(at))
    return min(moments) if moments else None


def wake_time(ring: Optional[float], now: float) -> Optional[int]:
    """When to wake for a ring at `ring`, as whole epoch seconds, or None for no wake time."""
    if ring is None or ring - now > MAX_AHEAD:
        return None
    early = ring - LEAD
    if early >= now + MIN_AHEAD:
        return int(early)
    if ring >= now + MIN_AHEAD:
        return int(ring)           # already inside the lead: wake at the ring itself
    return None                    # about to ring and the PC is awake


class WakeScheduler:
    """Keeps the helper's wake time equal to wake_time(next ring). Called every tick; it asks
    the helper only when the answer changes (or to retry after a failure)."""

    def __init__(self, run: Run = default_run, is_available: Callable[[], bool] = available):
        self.run, self.is_available = run, is_available
        self.armed: Any = 'unknown'       # what the helper holds: an epoch, None, or 'unknown'
        self.status = 'off'               # off, armed, unavailable, failed
        self.error = ''
        self.at: Optional[int] = None
        self.retry_at = 0.0
        self.last_try: Any = 'none'

    def update(self, config: Dict[str, Any], snoozes: List[Dict[str, Any]],
               now: float) -> Dict[str, Any]:
        enabled = bool(config['settings'].get('wake'))
        if not self.is_available():
            self.armed, self.status, self.at, self.error = 'unknown', 'unavailable', None, ''
            return self.note()
        want = wake_time(next_ring(config, snoozes, now), now) if enabled else None
        if want == self.armed:
            return self.note()
        if self.status == 'failed' and want == self.last_try and now < self.retry_at:
            return self.note()
        self.last_try = want
        command = ['clear'] if want is None else ['set', str(want)]
        try:
            code, message = self.run([PKEXEC, HELPER] + command)
        except (OSError, subprocess.SubprocessError) as exc:
            code, message = 1, str(exc)
        if code == 0:
            self.armed, self.at, self.error = want, want, ''
            self.status = 'armed' if want is not None else 'off'
            log.info("wake time %s", want if want is not None else "cleared")
        else:
            self.armed = 'unknown'
            self.status, self.error = 'failed', (message or f"exit {code}")[:200]
            self.retry_at = now + RETRY
            log.warning("wake time not set: %s", self.error)
        return self.note()

    def note(self) -> Dict[str, Any]:
        """What the service writes to service.json for the window to show."""
        return {'state': self.status, 'at': self.at, 'error': self.error}
