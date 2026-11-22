"""The "SparkOS updated" notification (a Plasma notification through notify-send, with Later
and Restart), how often it may come back, and restarting when you click Restart."""

import os
import subprocess
import sys
from typing import Any, Dict, Optional

from . import APP_ID, APP_SLUG
from .core import log, run, which
from .text import t

DAY = 86400


def should_notify(now: float, key: str, record: Optional[Dict[str, Any]],
                  remind_hours: int = 24) -> bool:
    """A new version is always announced once. After that (Later, or closed) it comes back
    after remind_hours, and never sooner than a day."""
    if not isinstance(record, dict) or record.get('key') != key:
        return True
    last = record.get('at')
    if not isinstance(last, (int, float)):
        return True
    return now - last >= max(DAY, remind_hours * 3600)


def message(kind: str, version: str, apps_ok: bool):
    """(title, body, actions) for the notification; actions in the order shown."""
    if kind == 'ready':
        body = t('notify.ready.body')
        if apps_ok:
            body += ' ' + t('notify.apps_ok')
        return (t('notify.ready.title'), body,
                [('later', t('notify.later')), ('restart', t('notify.restart'))])
    body = t('notify.available.body', version=version) if version else \
        t('notify.available.body_no_version')
    return (t('notify.available.title'), body,
            [('later', t('notify.later')), ('open', t('notify.open'))])


def show(offer, apps_ok: bool) -> Optional[str]:
    """Show it and wait for the answer: 'restart', 'later', 'open', or None (closed).
    The notification stays until answered; the service that shows it ends then."""
    if not which('notify-send'):
        log.warning("notify-send isn't installed; no notification")
        return None
    title, body, actions = message(offer.kind, offer.version, apps_ok)
    cmd = ['notify-send', '--app-name=SparkOS', f'--icon={APP_ID}', '--urgency=normal',
           '--expire-time=0', f'--hint=string:desktop-entry:{APP_ID}', '--wait',
           '--action=default=' + t('notify.open')]
    cmd += [f'--action={name}={label}' for name, label in actions]
    cmd += [title, body]
    code, out, _ = run(cmd, timeout=7 * DAY)
    answer = out.strip().splitlines()[-1].strip() if out.strip() else ''
    if answer == 'default':
        return 'open'
    return answer or None


def restart_pc() -> bool:
    """Ask Plasma to close the apps and restart (apps with unsaved work can still stop it),
    or systemd when Plasma isn't there. Only ever called from a click on Restart."""
    log.info("restarting: the user clicked Restart")
    if which('gdbus') and os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        code, _, _ = run(['gdbus', 'call', '--session', '--dest', 'org.kde.Shutdown',
                          '--object-path', '/Shutdown', '--method',
                          'org.kde.Shutdown.logoutAndReboot'], timeout=30)
        if code == 0:
            return True
    code, _, _ = run(['systemctl', 'reboot'], timeout=60)
    return code == 0


def open_window() -> None:
    """Start the window on its own (the notification's service ends right after)."""
    exe = which(APP_SLUG)
    cmd = [exe] if exe else [sys.executable, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'spark_update.py')]
    if os.environ.get('INVOCATION_ID') and which('systemd-run'):
        # under the timer's service: start it as its own unit, or systemd would close the
        # window together with the service
        cmd = ['systemd-run', '--user', '--collect', '--quiet', '--'] + cmd
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("could not open the window: %s", exc)


def answer(choice: str) -> None:
    if choice == 'restart':
        restart_pc()
    elif choice == 'open':
        open_window()
