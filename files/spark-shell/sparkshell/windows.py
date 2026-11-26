"""The task list's data: which windows exist, which is active, and acting on them.

spark-wl-windows (files/spark-compositor/spark-wl-windows) reads the Spark compositor's
wlr-foreign-toplevel list and prints it as one JSON line per change; actions (raise, minimise,
close) go back to it on stdin, one line each."""

import json
import logging
import os
import shutil

from gi.repository import Gio, GLib

log = logging.getLogger('spark-shell')

SNIP_OVERLAY_TITLE = 'Spark Snip capture'


class WindowTracker:
    """Runs spark-wl-windows and keeps `windows` current.
    on_changed(windows) is called after every update."""

    def __init__(self):
        self.windows = []
        self.all_ids = set()
        self.on_changed = lambda windows: None
        self.loaded = False
        self._stdin = None

    @staticmethod
    def _helper():
        return shutil.which('spark-wl-windows') or (
            '/usr/libexec/spark-wl-windows' if os.access('/usr/libexec/spark-wl-windows', os.X_OK)
            else None)

    def start(self):
        helper = self._helper()
        if not helper:
            log.error('window tracker: spark-wl-windows not found, taskbar stays empty')
            return
        self._start_helper(helper)

    def _start_helper(self, path):
        self._proc = Gio.Subprocess.new(
            [path], Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE)
        self._stdin = self._proc.get_stdin_pipe()
        out = Gio.DataInputStream.new(self._proc.get_stdout_pipe())
        self.loaded = True
        log.info('window tracker: %s', path)

        def got(stream, result):
            try:
                line, _len = stream.read_line_finish_utf8(result)
            except GLib.Error:
                line = None
            if line is None:
                # the helper died (compositor restart?): try again shortly
                self.loaded = False
                self._stdin = None
                GLib.timeout_add_seconds(2, lambda: self._start_helper(path) and False)
                return
            self.update(line)
            stream.read_line_async(GLib.PRIORITY_DEFAULT, None, got)
        out.read_line_async(GLib.PRIORITY_DEFAULT, None, got)

    # from spark-wl-windows ---------------------------------------------------------------------
    def update(self, payload: str):
        try:
            rows = json.loads(payload)
        except ValueError:
            return
        windows = []
        rows = rows if isinstance(rows, list) else []
        # every window, the hidden ones too: a new one closes the open menu
        self.all_ids = {str(r['id']) for r in rows if isinstance(r, dict) and r.get('id')}
        for row in rows:
            if isinstance(row, dict) and row.get('id'):
                if row.get('title') == SNIP_OVERLAY_TITLE:
                    continue        # Spark Snip's frozen-screen overlay is not a task
                windows.append({
                    'id': str(row['id']), 'title': str(row.get('title', '')),
                    'app': str(row.get('app', '')), 'cls': str(row.get('cls', '')),
                    'pid': int(row.get('pid') or 0), 'minimized': bool(row.get('minimized')),
                    'attention': bool(row.get('attention')), 'active': bool(row.get('active')),
                    'output': str(row.get('output', '')),
                })
        self.windows = windows
        self.on_changed(windows)

    # actions -----------------------------------------------------------------------------
    def act(self, action: str, window_id: str):
        if self._stdin is None or action not in ('activate', 'minimize', 'close'):
            return
        if not str(window_id).isdigit():
            return
        try:
            self._stdin.write_all(('%s %s\n' % (action, window_id)).encode(), None)
            self._stdin.flush(None)
        except GLib.Error as e:
            log.error('window action failed: %s', e.message)

    def active_window(self):
        return next((w for w in self.windows if w['active']), None)


def match_app(window: dict, desktop_id: str, startup_class: str = '') -> bool:
    """Does this window belong to the app with this desktop file id ('x.desktop' or 'x')?"""
    want = desktop_id[:-8] if desktop_id.endswith('.desktop') else desktop_id
    want = want.lower()
    if not want:
        return False
    app = window.get('app', '').lower()
    cls = window.get('cls', '').lower()
    startup_class = startup_class.lower()
    return want in (app, cls) or (bool(startup_class) and startup_class in (app, cls))

