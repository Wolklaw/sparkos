"""Spark Connect's status for the tray: runs `spark-connect --status --json` now and then, and
turns what it prints into a state, a count and a tooltip. Spark Connect is optional and per-user,
so everything here copes with it not being installed. No notifications: Spark Connect sends
those itself while it is open."""

import json
import logging
import time

from gi.repository import Gio, GLib

from .strings import tr

log = logging.getLogger('spark-shell')

COMMAND = ['spark-connect', '--status', '--json']
DESKTOP_ID = 'dev.wolklaw.SparkConnect.desktop'
INTERVAL = 60           # seconds between checks
TIMEOUT = 45            # then the check is killed
STATES = ('ok', 'warn', 'down')


def parse_status(text):
    """The JSON `spark-connect --status --json` prints, checked and filled in; None if it is not
    a status document. Missing or odd fields become empty values, never errors."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get('summary')
    if summary not in STATES + ('empty',):
        summary = 'empty'
    machines, sites = [], []
    for m in data.get('machines') if isinstance(data.get('machines'), list) else []:
        if not isinstance(m, dict):
            continue
        state = m.get('state')
        problems = m.get('problems')
        machines.append({
            'name': str(m.get('name') or '?'),
            'state': state if state in STATES + ('rebooting',) else 'warn',
            'verdict': str(m.get('verdict') or ''),
            'problems': [str(p) for p in problems] if isinstance(problems, list) else []})
    for s in data.get('sites') if isinstance(data.get('sites'), list) else []:
        if not isinstance(s, dict):
            continue
        status, ms = s.get('status'), s.get('ms')
        sites.append({
            'name': str(s.get('name') or s.get('url') or '?'), 'url': str(s.get('url') or ''),
            'state': 'ok' if s.get('state') == 'ok' else 'down',
            'status': status if isinstance(status, int) and not isinstance(status, bool) else None,
            'ms': ms if isinstance(ms, (int, float)) and not isinstance(ms, bool) else None})
    checked = data.get('checked')
    return {'checked': checked if isinstance(checked, (int, float)) else None,
            'summary': summary, 'machines': machines, 'sites': sites}


def problem_count(status) -> int:
    """How many machines and sites are not fine (rebooting counts as fine: it is expected)."""
    if not status:
        return 0
    return (sum(1 for m in status['machines'] if m['state'] in ('warn', 'down'))
            + sum(1 for s in status['sites'] if s['state'] != 'ok'))


def widget_state(status) -> str:
    """ok | warn | down | unknown, for the dot's colour."""
    if not status or status['summary'] == 'empty':
        return 'unknown'
    return status['summary']


def summary_text(status, language=None) -> str:
    """The one line for the tooltip."""
    if status is None:
        return tr('connect_checking', language)
    if status['summary'] == 'empty':
        return tr('connect_empty', language)
    n = problem_count(status)
    if n == 0:
        return tr('connect_all_ok', language)
    bad = [m['name'] for m in status['machines'] if m['state'] in ('warn', 'down')]
    bad += [s['name'] for s in status['sites'] if s['state'] != 'ok']
    shown = ', '.join(bad[:3]) + (', ...' if len(bad) > 3 else '')
    return (tr('connect_problem_one', language) if n == 1 else
            tr('connect_problem_many', language) % n) + (' (%s)' % shown)


def site_text(site) -> str:
    """'200, 85 ms' or 'down'."""
    bits = []
    if site['status'] is not None:
        bits.append(str(site['status']))
    if site['ms'] is not None:
        bits.append('%d ms' % site['ms'])
    return ', '.join(bits) if bits else tr('connect_state_down')


def checked_text(status) -> str:
    if not status or status['checked'] is None:
        return ''
    return tr('connect_checked') % time.strftime('%H:%M:%S', time.localtime(status['checked']))


def host_connector(setting: str, connectors, tray_connector: str) -> str:
    """The panel that shows the widget: the chosen connector if it is connected, else the
    tray's panel (the first one)."""
    return setting if setting and setting in connectors else tray_connector


class ConnectStatus:
    """Runs the check every minute while enabled. `status` is the last parsed document (None
    before the first answer); `on_change()` runs after every change."""

    def __init__(self):
        self.enabled = False
        self.installed = False
        self.status = None
        self.on_change = None
        self._timer = 0
        self._proc = None
        self._kill = 0
        self._warned = False

    def available(self) -> bool:
        """Shown only when enabled and the program is on PATH."""
        return self.enabled and self.installed

    def set_enabled(self, enabled: bool):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.status = None
            self.check()
            self._timer = GLib.timeout_add_seconds(INTERVAL, self._tick)
        else:
            if self._timer:
                GLib.source_remove(self._timer)
                self._timer = 0
            self._stop_proc()
            self.installed = False
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def _tick(self):
        self.check()
        return True

    def check(self):
        """Start a check now unless one is running."""
        if not self.enabled or self._proc is not None:
            return
        found = GLib.find_program_in_path(COMMAND[0])
        if bool(found) != self.installed:
            self.installed = bool(found)
            self._changed()
        if not found:
            if not self._warned:
                self._warned = True
                log.info('connect widget is on but spark-connect is not installed')
            return
        self._warned = False
        try:
            proc = Gio.Subprocess.new([found] + COMMAND[1:],
                                      Gio.SubprocessFlags.STDOUT_PIPE |
                                      Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as e:
            log.info('could not start spark-connect: %s', e.message)
            return
        self._proc = proc
        self._kill = GLib.timeout_add_seconds(TIMEOUT, self._timed_out, proc)
        proc.communicate_utf8_async(None, None, self._done, proc)

    def _timed_out(self, proc):
        self._kill = 0
        if self._proc is proc:
            log.info('spark-connect --status took over %d s, stopped it', TIMEOUT)
            proc.force_exit()
        return False

    def _stop_proc(self):
        if self._kill:
            GLib.source_remove(self._kill)
            self._kill = 0
        if self._proc is not None:
            self._proc.force_exit()
            self._proc = None

    def _done(self, proc, result, _proc):
        if self._proc is not proc:
            return              # switched off meanwhile
        if self._kill:
            GLib.source_remove(self._kill)
            self._kill = 0
        self._proc = None
        try:
            _ok, out, _err = proc.communicate_utf8_finish(result)
        except GLib.Error:
            return              # killed: keep what we showed
        code = proc.get_exit_status() if proc.get_if_exited() else -1
        if code == 2:
            self.status = {'checked': time.time(), 'summary': 'empty', 'machines': [],
                           'sites': []}
        elif code == 0:
            parsed = parse_status(out)
            if parsed is None:
                return
            self.status = parsed
        else:
            return
        self._changed()
