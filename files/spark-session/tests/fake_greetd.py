"""A stand-in for greetd: the same framing and JSON, a scripted account. For tests only."""

import json
import os
import socket
import struct
import tempfile
import threading


class FakeGreetd:
    """Accepts any number of connections. The one user 'alice' has the password PASSWORD; with
    second_factor=True a correct password is followed by a visible prompt that wants CODE."""

    PASSWORD, CODE = 'right-pass', '123456'

    def __init__(self, second_factor=False, delay=0.0):
        self.dir = tempfile.mkdtemp(prefix='fake-greetd-')
        self.path = os.path.join(self.dir, 'greetd.sock')
        self.second_factor, self.delay = second_factor, delay
        self.started = []            # (cmd, env) of every start_session
        self.requests = []           # every request, passwords included: tests only
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(8)
        self.stopped = False
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self):
        self.stopped = True
        self.server.close()
        try:
            os.unlink(self.path)
            os.rmdir(self.dir)
        except OSError:
            pass

    def _accept(self):
        while not self.stopped:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def _read(conn, count):
        out = b''
        while len(out) < count:
            chunk = conn.recv(count - len(out))
            if not chunk:
                raise EOFError
            out += chunk
        return out

    @staticmethod
    def _send(conn, message):
        data = json.dumps(message).encode()
        conn.sendall(struct.pack('=I', len(data)) + data)

    def _serve(self, conn):
        user, stage = None, None
        try:
            while True:
                (length,) = struct.unpack('=I', self._read(conn, 4))
                request = json.loads(self._read(conn, length))
                self.requests.append(request)
                kind = request['type']
                if kind == 'create_session':
                    user, stage = request['username'], 'password'
                    if user != 'alice':
                        self._send(conn, {'type': 'error', 'error_type': 'auth_error',
                                          'description': 'no such user'})
                        continue
                    self._send(conn, {'type': 'auth_message', 'auth_message_type': 'secret',
                                      'auth_message': 'Password: '})
                elif kind == 'post_auth_message_response':
                    answer = request['response']
                    if stage == 'password':
                        if answer != self.PASSWORD:
                            self._send(conn, {'type': 'error', 'error_type': 'auth_error',
                                              'description': 'Authentication failed'})
                        elif self.second_factor:
                            stage = 'code'
                            self._send(conn, {'type': 'auth_message', 'auth_message_type': 'visible',
                                              'auth_message': 'Verification code: '})
                        else:
                            stage = 'done'
                            self._send(conn, {'type': 'success'})
                    elif stage == 'code':
                        if answer == self.CODE:
                            stage = 'done'
                            self._send(conn, {'type': 'success'})
                        else:
                            self._send(conn, {'type': 'error', 'error_type': 'auth_error',
                                              'description': 'Authentication failed'})
                elif kind == 'start_session':
                    if stage != 'done':
                        self._send(conn, {'type': 'error', 'error_type': 'error',
                                          'description': 'not authenticated'})
                    else:
                        self.started.append((request['cmd'], request['env']))
                        self._send(conn, {'type': 'success'})
                elif kind == 'cancel_session':
                    user, stage = None, None
                    self._send(conn, {'type': 'success'})
        except (EOFError, OSError):
            pass
        finally:
            conn.close()
