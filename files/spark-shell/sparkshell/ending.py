"""Sign out, restart and shut down without killing open apps.

Plasma's ksmserver asks every app to close before the session ends; the Spark session has no
ksmserver. So the shell does the part that matters: it asks KWin to close every window (the same
close as the title bar's button, so an app can save or ask about unsaved work), waits for the
window list to empty, then runs the command. If windows are still open when the wait is over,
nothing is run: on_stuck(titles) lets the person choose to go anyway or stay."""

import logging

from gi.repository import GLib

log = logging.getLogger('spark-shell')

WAIT_S = 8.0
TICK_MS = 250


class SessionEnd:
    def __init__(self, tracker, run, on_stuck, wait_s=WAIT_S, timeout_add=None):
        self.tracker = tracker          # .windows (list of dicts), .loaded, .act('close', id)
        self.run = run                  # run(command)
        self.on_stuck = on_stuck        # on_stuck(command, [titles still open], label)
        self.wait_s = wait_s
        self.timeout_add = timeout_add or GLib.timeout_add
        self._ticks = 0
        self._command = None
        self._label = None

    @property
    def busy(self):
        return self._command is not None

    def start(self, command, force=False, label=None):
        """Close the windows, then run command. force runs it at once (the second ask).
        label comes back to on_stuck (which button it was)."""
        if force or not self.tracker.loaded or not self.tracker.windows:
            self._finish(command)
            return
        if self.busy:
            return
        self._command = command
        self._label = label
        self._ticks = 0
        for w in list(self.tracker.windows):
            self.tracker.act('close', w['id'])
        self.timeout_add(TICK_MS, self._tick)

    def _tick(self):
        command = self._command
        if command is None:
            return False
        if not self.tracker.windows:
            self._finish(command)
            return False
        self._ticks += 1
        if self._ticks * TICK_MS / 1000.0 >= self.wait_s:
            self._command = None
            titles = [w.get('title') or w.get('app') or '?' for w in self.tracker.windows]
            log.info('still open after %.0fs: %s', self.wait_s, ', '.join(titles))
            self.on_stuck(command, titles, self._label)
            return False
        return True

    def _finish(self, command):
        self._command = None
        self.run(command)
