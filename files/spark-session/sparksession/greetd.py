"""greetd's IPC (see greetd-ipc(7)): a 4 byte native-endian length, then JSON, over the unix
socket named by $GREETD_SOCK. Plain blocking client, no GTK, so it can be tested alone."""

import json
import os
import socket
import struct
import time


class GreetdError(Exception):
    """greetd answered with an error. kind is 'auth_error' (wrong password) or 'error'."""

    def __init__(self, kind, description):
        super().__init__(description)
        self.kind, self.description = kind, description


class Client:
    def __init__(self, path=None):
        path = path or os.environ.get('GREETD_SOCK')
        if not path:
            raise GreetdError('error', 'GREETD_SOCK is not set')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(60)
        try:
            self.sock.connect(path)
        except OSError:
            self.sock.close()
            raise

    def close(self):
        self.sock.close()

    def _send(self, message):
        data = json.dumps(message).encode()
        self.sock.sendall(struct.pack('=I', len(data)) + data)

    def _read(self, count):
        out = b''
        while len(out) < count:
            chunk = self.sock.recv(count - len(out))
            if not chunk:
                raise GreetdError('error', 'greetd closed the connection')
            out += chunk
        return out

    def _call(self, message):
        self._send(message)
        (length,) = struct.unpack('=I', self._read(4))
        reply = json.loads(self._read(length))
        if reply.get('type') == 'error':
            raise GreetdError(reply.get('error_type', 'error'), reply.get('description', ''))
        return reply

    # --- the four requests ---
    def create_session(self, username):
        return self._call({'type': 'create_session', 'username': username})

    def respond(self, text):
        """Answer an auth_message. None for messages that need no answer (info, error)."""
        return self._call({'type': 'post_auth_message_response', 'response': text})

    def start_session(self, cmd, env=()):
        return self._call({'type': 'start_session', 'cmd': list(cmd), 'env': list(env)})

    def cancel_session(self):
        return self._call({'type': 'cancel_session'})


def login(client, username, answer, cmd, env=()):
    """Run a whole login. answer(kind, text) -> str|None is asked for every auth_message
    (kind is visible, secret, info or error). Returns after start_session succeeds (greetd then
    ends the greeter). Raises GreetdError; the pending session is cancelled first."""
    reply = None
    for attempt in range(10):
        try:
            reply = client.create_session(username)
            break
        except GreetdError as exc:
            # greetd can still be tearing down the cancelled attempt a moment after it answered
            if 'already being configured' not in str(exc) or attempt == 9:
                raise
            time.sleep(0.3)
    try:
        while reply['type'] == 'auth_message':
            kind = reply.get('auth_message_type', 'secret')
            text = answer(kind, reply.get('auth_message', ''))
            reply = client.respond(text)
        return client.start_session(cmd, env)
    except BaseException:
        try:
            client.cancel_session()
        except Exception as exc:           # noqa: BLE001
            client.cancel_error = f'{type(exc).__name__}: {exc}'
        raise
