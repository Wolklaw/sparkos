"""Which updater downloads and stages SparkOS images on this PC.

  uupd   Universal Blue's uupd (uupd.timer, daily at 04:00), as Bazzite ships it. Spark Update
         adds the notification, the window, Check now (it starts uupd-manual.service) and
         roll back on top. The image build's default until Spark Update's own staging has
         run on a booted SparkOS.
  spark  Spark Update's own timer (spark-update.timer) with uupd switched off
         (files/scripts/spark-update.sh with SPARK_UPDATE_ENGINE=spark).
  none   neither is on (a per-user install somewhere else, or something is wrong).

Read from which timers are enabled, so it is always what the PC really does."""

import os
from typing import Any, Callable, Dict, Optional, Tuple

from .core import Env, run

SPARK, UUPD, NONE = 'spark', 'uupd', 'none'
UUPD_UNITS = ('uupd.service', 'uupd-manual.service')
ACTIVE = ('activating', 'active', 'reloading', 'deactivating')


def timer_enabled(env: Env, name: str, user: bool = False) -> bool:
    folders = ('/etc/systemd/user', '/usr/lib/systemd/user') if user else \
        ('/etc/systemd/system', '/usr/lib/systemd/system')
    return any(os.path.lexists(env.path(f'{f}/timers.target.wants/{name}')) for f in folders)


def engine(env: Env) -> str:
    if timer_enabled(env, 'spark-update.timer'):
        return SPARK
    if timer_enabled(env, 'uupd.timer'):
        return UUPD
    return NONE


def both_on(env: Env) -> bool:
    return timer_enabled(env, 'spark-update.timer') and timer_enabled(env, 'uupd.timer')


def _unix(value: Optional[str]) -> Optional[float]:
    """'@1763539200' (systemctl show --timestamp=unix) -> 1763539200.0"""
    if not value or not value.startswith('@'):
        return None
    try:
        ts = float(value[1:])
    except ValueError:
        return None
    return ts if ts > 0 else None


def parse_show(text: str) -> Dict[str, str]:
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            out[key.strip()] = value.strip()
    return out


def summarize(units: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """{'running', 'last_run' (when the last run ended), 'ok' (it succeeded), 'unit'}"""
    result: Dict[str, Any] = {'running': False, 'last_run': None, 'ok': None, 'unit': ''}
    for name, u in units.items():
        if u.get('ActiveState') in ACTIVE:
            result['running'] = True
        ts = _unix(u.get('ExecMainExitTimestamp'))
        if ts and (result['last_run'] is None or ts > result['last_run']):
            result.update(last_run=ts, unit=name,
                          ok=u.get('Result') == 'success' and u.get('ExecMainStatus', '0') in ('0', ''))
    return result


def uupd_status(env: Env, runner: Callable = run) -> Dict[str, Any]:
    """When uupd last ran, whether it worked, and whether it runs now (it updates the image and
    every Flatpak app in one go, so its result also says whether the apps are up to date)."""
    if env.fake:
        data = env.read_json('/status/uupd.json')
        return summarize(data if isinstance(data, dict) else {})
    units = {}
    for unit in UUPD_UNITS:
        code, out, _ = runner(['systemctl', 'show', '--timestamp=unix', '-p', 'ActiveState',
                               '-p', 'Result', '-p', 'ExecMainStatus', '-p',
                               'ExecMainExitTimestamp', unit], timeout=20, quiet=True)
        if code == 0:
            units[unit] = parse_show(out)
    return summarize(units)


def start_uupd(runner: Callable = run) -> Tuple[int, str]:
    """Check now under uupd: the same unit `ujust update` starts. Bazzite's polkit rule
    (uupd.rules) lets any user start it without a password."""
    code, out, err = runner(['systemctl', 'start', '--no-block', 'uupd-manual.service'],
                            timeout=120)
    return code, (err or out).strip()
