"""The Spark compositor's control socket: $XDG_RUNTIME_DIR/spark-wl/ctl, a unix stream with a
line protocol. The shell sends `watch` and gets `ok`, then lines as things change:

    workspace <current> <count> <occupied>     1-based; occupied is "1,3" or "-"
    tiling <on|off>
    focus <pid> <app_id>                       ignored here

Commands (`workspace N|next|prev`, `move-to-workspace N|next|prev`, `tile-toggle`) go over a
short connection of their own, so a reply never mixes with the watch lines. An older compositor
has no socket: the link keeps trying with a growing wait, says so once, and shows nothing."""

import logging
import os

from gi.repository import Gio, GLib

log = logging.getLogger('spark-shell')

BACKOFF = (2, 5, 10, 30)          # seconds between tries while the socket is missing or closed


def socket_path() -> str:
    runtime = os.environ.get('XDG_RUNTIME_DIR') or '/run/user/%d' % os.getuid()
    return os.path.join(runtime, 'spark-wl', 'ctl')


def parse_line(line: str):
    """One line from the watch stream as a dict, or None for what is not ours to read.

    {'kind': 'workspace', 'current': 2, 'count': 4, 'occupied': [1, 2]},
    {'kind': 'tiling', 'on': True}, {'kind': 'ok'} or {'kind': 'error', 'text': ...}."""
    parts = (line or '').strip().split()
    if not parts:
        return None
    word = parts[0]
    try:
        if word == 'workspace' and len(parts) >= 3:
            count = int(parts[2])
            current = int(parts[1])
            if count < 1 or not 1 <= current <= count:
                return None
            occupied = []
            if len(parts) > 3 and parts[3] != '-':
                occupied = sorted({int(n) for n in parts[3].split(',') if n})
            return {'kind': 'workspace', 'current': current, 'count': count,
                    'occupied': [n for n in occupied if 1 <= n <= count]}
        if word == 'tiling' and len(parts) >= 2 and parts[1] in ('on', 'off'):
            return {'kind': 'tiling', 'on': parts[1] == 'on'}
    except ValueError:
        return None
    if word == 'ok':
        return {'kind': 'ok'}
    if word == 'error':
        return {'kind': 'error', 'text': ' '.join(parts[1:])}
    return None


class CompositorLink:
    """Holds the watch connection and the latest state. `on_change()` runs on every update."""

    def __init__(self, path=None):
        self.path = path or socket_path()
        self.connected = False
        self.current, self.count, self.occupied = 1, 1, []
        self.tiling = None                  # True / False once the compositor said, else None
        self.on_change = None
        self._conn = None
        self._stream = None
        self._tries = 0
        self._timer = 0
        self._announced = False
        self._stopped = False
        self._cancel = Gio.Cancellable()

    # lifecycle ---------------------------------------------------------------------------
    def start(self):
        self._stopped = False
        self._connect()

    def stop(self):
        self._stopped = True
        self._cancel.cancel()
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._drop()

    def visible(self) -> bool:
        return self.connected and self.count > 1

    def _changed(self):
        if self.on_change:
            self.on_change()

    def _retry(self):
        if self._stopped or self._timer:
            return
        wait = BACKOFF[min(self._tries, len(BACKOFF) - 1)]
        self._tries += 1
        self._timer = GLib.timeout_add_seconds(wait, self._retry_now)

    def _retry_now(self):
        self._timer = 0
        self._connect()
        return False

    def _drop(self):
        was = self.connected
        self.connected = False
        self.current, self.count, self.occupied, self.tiling = 1, 1, [], None
        if self._conn is not None:
            try:
                self._conn.close(None)
            except GLib.Error:
                pass
        self._conn = self._stream = None
        if was:
            self._changed()

    # watch connection --------------------------------------------------------------------
    def _connect(self):
        if self._stopped:
            return
        if not os.path.exists(self.path):
            self._failed('no control socket at %s (an older compositor?)' % self.path)
            return
        client = Gio.SocketClient()
        self._cancel = Gio.Cancellable()
        client.connect_async(Gio.UnixSocketAddress.new(self.path), self._cancel,
                             self._connected)

    def _failed(self, why):
        if not self._announced:
            self._announced = True
            log.info('workspaces: %s; no workspace indicator until it is there', why)
        self._retry()

    def _connected(self, client, result):
        try:
            conn = client.connect_finish(result)
        except GLib.Error as e:
            self._failed(e.message)
            return
        if self._stopped:
            conn.close(None)
            return
        self._conn = conn
        self._stream = Gio.DataInputStream.new(conn.get_input_stream())
        self._stream.set_newline_type(Gio.DataStreamNewlineType.LF)
        try:
            conn.get_output_stream().write_all(b'watch\n', None)
        except GLib.Error as e:
            self._drop()
            self._failed(e.message)
            return
        self._tries = 0
        self._announced = False
        self._read()

    def _read(self):
        stream = self._stream
        if stream is None:
            return
        stream.read_line_async(GLib.PRIORITY_DEFAULT, self._cancel, self._line, stream)

    def _line(self, stream, result, mine):
        if mine is not self._stream:
            return
        try:
            text, _length = stream.read_line_finish_utf8(result)
        except GLib.Error as e:
            if self._stopped:
                return
            self._drop()
            self._failed(e.message)
            return
        if text is None:                      # the compositor closed the socket
            self._drop()
            self._failed('the control socket closed')
            return
        self._apply(parse_line(text))
        self._read()

    def _apply(self, event):
        if not event:
            return
        kind = event['kind']
        if kind == 'ok':
            if not self.connected:
                self.connected = True
                self._changed()
        elif kind == 'workspace':
            self.connected = True
            self.current, self.count = event['current'], event['count']
            self.occupied = event['occupied']
            self._changed()
        elif kind == 'tiling':
            self.tiling = event['on']
            self._changed()

    # commands ----------------------------------------------------------------------------
    def send(self, command: str, done=None):
        """Run one command on its own connection; done(reply line) when answered ('' on failure)."""
        if not os.path.exists(self.path):
            if done:
                done('')
            return
        client = Gio.SocketClient()

        def connected(_client, result):
            try:
                conn = client.connect_finish(result)
                conn.get_output_stream().write_all((command + '\n').encode(), None)
            except GLib.Error as e:
                log.info('workspaces: %s failed: %s', command, e.message)
                if done:
                    done('')
                return
            stream = Gio.DataInputStream.new(conn.get_input_stream())
            stream.read_line_async(GLib.PRIORITY_DEFAULT, None, answered, conn)

        def answered(stream, result, conn):
            try:
                text, _length = stream.read_line_finish_utf8(result)
            except GLib.Error:
                text = None
            try:
                conn.close(None)
            except GLib.Error:
                pass
            reply = text or ''
            if reply.startswith('error'):
                log.info('workspaces: %s: %s', command, reply)
            if done:
                done(reply)

        client.connect_async(Gio.UnixSocketAddress.new(self.path), None, connected)

    def go_to(self, n):
        self.send('workspace %s' % n)

    def scroll(self, direction: int):
        self.send('workspace next' if direction > 0 else 'workspace prev')

    def toggle_tiling(self):
        self.send('tile-toggle')
