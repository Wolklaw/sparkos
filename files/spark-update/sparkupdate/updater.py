"""The background runs, started by systemd timers (nothing stays running in between):

  system run (root, spark-update.timer, hourly): when a check is due, download and stage the
      new SparkOS image (bootc upgrade, or rpm-ostree upgrade when packages are layered) and
      update system Flatpak apps. In notify-only mode it only checks. It never restarts.
  user run (you, spark-update-user.timer, hourly): update your own Flatpak apps when due, and
      show the "SparkOS updated" notification when a new version is staged.

Both wait for a later hour while a game is running, on a metered connection, or on a low
battery. Every command they run goes to the log."""

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import STATE_PATH
from . import guard
from .core import Env, load_json, log, run, save_json, state_dir, which
from .text import EN, t
from .settings import NOTIFY, STAGE, SystemSettings, load_prefs, load_system
from .status import Host, read_host

Runner = Callable[..., Tuple[int, str, str]]
CHECK, STAGE_NOW = 'check', 'stage'
RETRY_AFTER_FAIL = 3600            # a failed check is tried again an hour later
STATE_VERSION = 1


# ─── State files ───────────────────────────────────────────────

def load_state(env: Env, path: Optional[str] = None) -> Dict[str, Any]:
    return load_json(path or env.path(STATE_PATH))


def save_state(env: Env, data: Dict[str, Any], path: Optional[str] = None) -> None:
    data['state_version'] = STATE_VERSION
    save_json(path or env.path(STATE_PATH), data, mode=0o644)


def user_state_path() -> str:
    return os.path.join(state_dir(), 'state.json')


def direct_state_path() -> str:
    """Where a check run by the window itself (no system install) records what it did."""
    return os.path.join(state_dir(), 'system-state.json')


def due(last: Optional[float], every_hours: int, now: float, failed: bool = False) -> bool:
    if not last:
        return True
    if failed:
        return now - last >= RETRY_AFTER_FAIL
    return now - last >= every_hours * 3600 - 300     # the timer's hourly beat jitters a bit


# ─── The image ────────────────────────────────────────────────

def method_for(host: Host) -> str:
    """bootc unless packages are layered with rpm-ostree (bootc refuses those), or bootc
    isn't there."""
    if host.booted is not None and host.booted.layered:
        return 'rpm-ostree'
    if hasattr(os, 'geteuid') and os.geteuid() != 0:
        return 'rpm-ostree'         # bootc needs root; rpm-ostree asks polkit for you
    return 'bootc' if which('bootc') else 'rpm-ostree'


def parse_check(method: str, code: int, text: str) -> Tuple[Optional[bool], str]:
    """(is an update available, its version) from `<method> upgrade --check`.
    None when the output says neither (an error)."""
    version = ''
    match = re.search(r'^\s*Version:\s*(\S+)', text, re.M)
    if match:
        version = match.group(1)
    if method == 'rpm-ostree':
        if code == 77 or re.search(r'No updates? available', text, re.I):
            return False, ''
        if 'AvailableUpdate' in text:
            return True, version
        return (None, '') if code else (False, '')
    if code != 0:
        return None, ''
    if re.search(r'No changes in|No update available', text, re.I):
        return False, ''
    if re.search(r'Update available', text, re.I):
        return True, version
    return None, ''


def check_image(host: Host, runner: Runner) -> Dict[str, Any]:
    method = method_for(host)
    code, out, err = runner([method, 'upgrade', '--check'], timeout=600)
    available, version = parse_check(method, code, out + '\n' + err)
    if available is None:
        return {'ok': False, 'method': method, 'error': _first_error(out, err, code)}
    match = re.search(r'^\s*Digest:\s*(sha256:[0-9a-f]+)', out + '\n' + err, re.M)
    return {'ok': True, 'method': method, 'available': available, 'version': version,
            'digest': match.group(1) if match and available else ''}


def stage_image(host: Host, runner: Runner) -> Dict[str, Any]:
    method = method_for(host)
    cmd = ['bootc', 'upgrade'] if method == 'bootc' else \
        ['rpm-ostree', 'upgrade', '--unchanged-exit-77']
    code, out, err = runner(cmd, timeout=3 * 3600)
    if code in (0, 77):
        return {'ok': True, 'method': method}
    return {'ok': False, 'method': method, 'error': _first_error(out, err, code)}


def _first_error(out: str, err: str, code: int) -> str:
    lines = [ln.strip() for ln in (err or out).strip().splitlines() if ln.strip()]
    for ln in lines:
        if ln.lower().startswith('error'):
            return ln[:300]
    return (lines[-1][:300] if lines else f"exit code {code}")


# ─── Flatpak ──────────────────────────────────────────────────

def flatpak_apps(scope: str, runner: Runner) -> Optional[Dict[str, str]]:
    code, out, _ = runner(['flatpak', 'list', f'--{scope}', '--app',
                           '--columns=application,active'], timeout=120, quiet=True)
    if code != 0:
        return None
    apps = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            apps[parts[0]] = parts[1]
    return apps


def update_flatpak(scope: str, runner: Runner, now: float) -> Dict[str, Any]:
    """`flatpak update --<scope>`; which apps changed comes from their commit before and
    after, not from parsing flatpak's progress output."""
    before = flatpak_apps(scope, runner)
    if before is None:
        return {'ok': None, 'at': now, 'updated': [], 'error': t('err.no_flatpak')}
    code, out, err = runner(['flatpak', 'update', f'--{scope}', '--noninteractive', '-y'],
                            timeout=2 * 3600)
    after = flatpak_apps(scope, runner) or {}
    updated = sorted(a for a, commit in after.items() if a in before and before[a] != commit)
    result = {'ok': code == 0, 'at': now, 'updated': updated, 'count': len(after)}
    if code != 0:
        result['error'] = _first_error(out, err, code)
    return result


# ─── The system run (root) ────────────────────────────────────

def system_run(env: Env, now_mode: Optional[str] = None, runner: Runner = run,
               clock: Callable[[], float] = time.time, state_path: Optional[str] = None,
               flatpak_scope: str = 'system') -> int:
    """One background pass. now_mode ('check' or 'stage') is a click on Check now: it runs
    whatever the settings and the hour, but still never restarts."""
    conf, warnings = load_system(env)
    for w in warnings:
        log.warning("update.conf %s", w)
    state = load_state(env, state_path)
    now = clock()
    if now_mode is None:
        if not conf.automatic:
            return 0
        if not due(state.get('last_check'), conf.every_hours, now,
                   failed=state.get('result') == 'failed'):
            return 0
        why = guard.wait_reason(env)
        if why:
            wait = EN[why[0]].format(**why[1])
            if state.get('reason') != wait or state.get('result') != 'postponed':
                log.info("waiting for a later hour: %s", wait)
            # the English for the log, the key so the window can say it in its own language
            state.update(result='postponed', reason=wait, reason_key=why[0],
                         reason_args=why[1], last_run=now, running=False)
            save_state(env, state, state_path)
            return 0
    lock = _lock(env, state_path, wait=bool(now_mode))
    if lock is None:
        return 0                    # another run is at it right now
    mode = now_mode or (CHECK if conf.mode == NOTIFY else STAGE_NOW)
    state = load_state(env, state_path)      # the other run may have just finished
    log.info("%s run: %s", 'manual' if now_mode else 'scheduled',
             'check only' if mode == CHECK else 'check, download and stage')
    state.update(running=True, phase='checking', last_run=now, reason='', manual=bool(now_mode))
    save_state(env, state, state_path)
    try:
        return _system_pass(env, conf, state, mode, runner, clock, state_path, flatpak_scope)
    finally:
        state['running'] = False
        state['phase'] = 'done'
        state['finished'] = clock()
        save_state(env, state, state_path)
        lock.close()


def _lock(env: Env, state_path: Optional[str], wait: bool):
    """One run at a time (the timer's and a Check now click could meet). The lock file sits
    next to the state file; the kernel drops the lock if the process dies."""
    path = (state_path or env.path(STATE_PATH)) + '.lock'
    try:
        import fcntl
    except ImportError:                     # not Linux: tests on Windows
        return open(os.devnull, 'w')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f = open(path, 'w')
    except OSError as exc:
        log.warning("no lock file (%s); going ahead", exc)
        return open(os.devnull, 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except OSError:
        f.close()
        return None
    return f


def _system_pass(env: Env, conf: SystemSettings, state: Dict[str, Any], mode: str,
                 runner: Runner, clock, state_path, flatpak_scope) -> int:
    host = read_host(env, prefer_bootc=True)
    if host.booted is None:
        state.update(result='failed', error=f"can't read the system status: {host.error}",
                     last_check=clock())
        log.error("%s", state['error'])
        return 1
    state['booted_version'] = host.booted.version
    if _held_back(host, state, runner, mode):
        pass
    elif mode == CHECK:
        result = check_image(host, runner)
        state['method'] = result['method']
        if not result['ok']:
            state.update(result='failed', error=result['error'])
        elif result['available']:
            state.update(result='available', available_version=result['version'], error='')
        elif host.update_ready:
            state.update(result='staged', staged_version=host.staged.version, error='')
        else:
            state.update(result='up_to_date', available_version='', error='')
    else:
        state['phase'] = 'downloading'
        save_state(env, state, state_path)
        result = stage_image(host, runner)
        state['method'] = result['method']
        if not result['ok']:
            state.update(result='failed', error=result['error'])
        else:
            after = read_host(env, prefer_bootc=True)
            if after.update_ready:
                state.update(result='staged', staged_version=after.staged.version,
                             available_version='', error='')
                log.info("SparkOS %s is staged; it starts at the next restart",
                         after.staged.version)
            else:
                state.update(result='up_to_date', staged_version='', available_version='',
                             error='')
                log.info("SparkOS is up to date (%s)", host.booted.version)
    state['last_check'] = clock()
    if conf.flatpak and mode == STAGE_NOW:
        state['phase'] = 'flatpak'
        save_state(env, state, state_path)
        state['flatpak'] = update_flatpak(flatpak_scope, runner, clock())
        updated = state['flatpak'].get('updated') or []
        log.info("Flatpak (%s): %s", flatpak_scope,
                 f"{len(updated)} app(s) updated: {', '.join(updated)}" if updated
                 else "nothing to update" if state['flatpak'].get('ok') else
                 state['flatpak'].get('error', 'failed'))
    return 0 if state.get('result') != 'failed' else 1


def _held_back(host: Host, state: Dict[str, Any], runner: Runner, mode: str) -> bool:
    """After a roll back, a scheduled run doesn't stage the version you rolled back from
    again (otherwise the next restart would bring it straight back), and in notify mode
    doesn't report it as available. It stages (or reports) the next newer one. Check now (a
    manual run) and booting that version again end the hold. True when this run is done
    (nothing more to do: no staging, no second check); the state says why."""
    held = state.get('held')
    if not isinstance(held, dict) or not held.get('digests'):
        state.pop('held', None)
        return False
    if state.get('manual') or host.booted.digest in held['digests']:
        log.info("no longer holding back SparkOS %s", held.get('version', '?'))
        state.pop('held', None)
        return False
    result = check_image(host, runner)
    state['method'] = result['method']
    if not result['ok']:
        state.update(result='failed', error=result['error'])
    elif result['available'] and result['digest'] not in held['digests']:
        state.pop('held', None)
        if mode == CHECK:
            state.update(result='available', available_version=result['version'], error='')
            log.info("SparkOS %s is newer than the version you rolled back from; it's "
                     "available", result['version'] or '?')
            return True
        log.info("SparkOS %s is newer than the version you rolled back from; staging it",
                 result['version'] or '?')
        return False
    else:
        state.update(result='up_to_date', staged_version='', available_version='', error='')
        log.info("not %s SparkOS %s again: you rolled back from it. The next newer version "
                 "will be %s", 'reporting' if mode == CHECK else 'staging',
                 held.get('version', '?'), 'reported' if mode == CHECK else 'staged')
    return True


# ─── Rolling back (the helper runs this as root) ──────────────

def rollback(env: Env, runner: Runner = run) -> Tuple[int, str]:
    """Make the previous version the one the next restart starts. Nothing is deleted: the
    current version stays on disk, and running this again undoes it. A staged update is
    dropped first, so the restart really goes back."""
    host = read_host(env)
    if host.booted is None:
        return 1, t('err.no_status', why=host.error)
    if host.rollback is None and not host.rollback_queued:
        return 1, t('err.no_previous')
    if host.staged is not None:
        code, out, err = runner(['rpm-ostree', 'cleanup', '--pending'], timeout=600)
        if code != 0:
            return code, _first_error(out, err, code)
    code, out, err = runner(['rpm-ostree', 'rollback'], timeout=600)
    if code != 0:
        return code, _first_error(out, err, code)
    # Remember what you rolled back from, so the timer doesn't stage it again (_held_back).
    # Rolling back a second time undoes the first, and the hold with it.
    state = load_state(env)
    digests = [d.digest for d in (host.booted, host.staged) if d is not None and d.digest]
    if host.rollback_queued or not digests:
        state.pop('held', None)
    else:
        state['held'] = {'digests': digests, 'version': host.booted.version}
    save_state(env, state)
    return 0, ''


# ─── The user run ─────────────────────────────────────────────

@dataclass
class Offer:
    kind: str          # 'ready': staged, restart to use it; 'available': notify-only mode
    key: str
    version: str


def what_to_offer(host: Host, sys_state: Dict[str, Any]) -> Optional[Offer]:
    if host.rollback_queued:
        return None
    if host.update_ready:
        return Offer('ready', host.staged.key, host.staged.version)
    if sys_state.get('result') == 'available':
        version = str(sys_state.get('available_version') or '')
        return Offer('available', 'available:' + (version or 'unknown'), version)
    return None


def apps_up_to_date(conf: SystemSettings, sys_state: Dict[str, Any],
                    user_state: Dict[str, Any], now: float) -> bool:
    """True only when Flatpak updates are on and both the system's and your last update
    finished without error within the last day: then the notification may say so."""
    if not conf.flatpak:
        return False
    for result in (sys_state.get('flatpak'), user_state.get('flatpak')):
        if not isinstance(result, dict) or result.get('ok') is not True:
            return False
        if now - (result.get('at') or 0) > 86400:
            return False
    return True


def user_run(env: Env, runner: Runner = run, clock: Callable[[], float] = time.time,
             notifier: Optional[Callable[[Offer, bool], Optional[str]]] = None,
             on_answer: Optional[Callable[[str], None]] = None) -> int:
    from .notify import should_notify
    conf, _ = load_system(env)
    prefs = load_prefs()
    ustate = load_json(user_state_path())
    now = clock()

    flat = ustate.get('flatpak') if isinstance(ustate.get('flatpak'), dict) else {}
    if conf.automatic and conf.flatpak and conf.mode == STAGE and \
            due(flat.get('at'), conf.every_hours, now, failed=flat.get('ok') is False):
        wait = guard.reason_to_wait(env)
        if wait:
            if ustate.get('waiting') != wait:
                log.info("your Flatpak apps: waiting for a later hour: %s", wait)
            ustate['waiting'] = wait
        else:
            ustate['waiting'] = ''
            ustate['flatpak'] = update_flatpak('user', runner, now)
            updated = ustate['flatpak'].get('updated') or []
            if updated or not ustate['flatpak'].get('ok'):
                log.info("your Flatpak apps: %s", f"updated {', '.join(updated)}" if updated
                         else ustate['flatpak'].get('error', 'failed'))
    save_json(user_state_path(), ustate)

    host = read_host(env)
    sys_state = load_state(env)
    offer = what_to_offer(host, sys_state)
    if offer is None or not prefs.notify:
        return 0
    if guard.game_running(env):
        return 0
    if notifier is None and not (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')):
        return 0                    # logged in without a desktop (ssh): nowhere to show it
    if not should_notify(now, offer.key, ustate.get('notified'), prefs.remind_hours):
        return 0
    ustate['notified'] = {'key': offer.key, 'at': now, 'version': offer.version}
    save_json(user_state_path(), ustate)
    log.info("notifying: SparkOS %s %s", offer.version or '', 'is ready' if offer.kind == 'ready'
             else 'is available')
    if notifier is None:
        from .notify import show
        notifier = show
    apps_ok = apps_up_to_date(conf, sys_state, ustate, now)
    answer = notifier(offer, apps_ok)
    log.info("notification answer: %s", answer or 'closed')
    ustate = load_json(user_state_path())
    if isinstance(ustate.get('notified'), dict):
        ustate['notified']['at'] = clock()            # Later counts from when it was answered
        ustate['notified']['answer'] = answer or 'closed'
    save_json(user_state_path(), ustate)
    if answer and on_answer:
        on_answer(answer)
    return 0
