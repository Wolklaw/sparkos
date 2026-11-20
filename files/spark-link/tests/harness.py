"""Runs the real Spark Link service for a test, with its own home folder, a free port, and a
FakeDesktop that writes down what the phone made the PC do.

On Linux the service runs as its own process (spark_link.py --service) and the test talks to
it over the real control socket, as the window does. Where there are no Unix sockets
(Windows, while developing) it runs in a thread of the test process instead."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

SUBPROCESS = hasattr(socket, 'AF_UNIX') and sys.platform.startswith('linux')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, settings: Dict[str, Any] = None, env: Dict[str, str] = None):
        self.tmp = tempfile.mkdtemp(prefix='spark-link-test-')
        self.home = os.path.join(self.tmp, 'home')
        self.run_dir = os.path.join(self.tmp, 'run')
        self.downloads = os.path.join(self.home, 'Downloads')
        self.log = os.path.join(self.tmp, 'desktop.jsonl')
        for d in (self.home, self.run_dir):
            os.makedirs(d, mode=0o700)
        self.port = free_port()
        self.env = dict(os.environ, HOME=self.home, XDG_CONFIG_HOME=os.path.join(self.home, '.config'),
                        XDG_DATA_HOME=os.path.join(self.home, '.local', 'share'),
                        XDG_STATE_HOME=os.path.join(self.home, '.local', 'state'),
                        XDG_RUNTIME_DIR=self.run_dir, SPARK_LINK_FAKE_DESKTOP=self.log,
                        SPARK_LINK_DOWNLOADS=self.downloads, LANG='C.UTF-8')
        self.env.pop('DBUS_SESSION_BUS_ADDRESS', None)
        self.env.update(env or {})
        settings = dict(settings or {})
        settings.setdefault('port', self.port)
        cfg = os.path.join(self.env['XDG_CONFIG_HOME'], 'spark-link')
        os.makedirs(cfg, exist_ok=True)
        with open(os.path.join(cfg, 'settings.json'), 'w', encoding='utf-8') as f:
            json.dump(settings, f)
        self.proc = None
        self.thread = None
        self.loop = None
        self.service = None
        self.ctl_client = None

    # ── start, stop ──
    def start(self) -> 'Service':
        if SUBPROCESS:
            self.proc = subprocess.Popen(
                [sys.executable, os.path.join(APP, 'spark_link.py'), '--service', '--no-mdns'],
                env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
            from sparklink.control import Control, NotRunning
            self.ctl_client = Control(os.path.join(self.run_dir, 'spark-link', 'control.sock'))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError('service exited: ' +
                                       self.proc.stdout.read().decode('utf-8', 'replace'))
                try:
                    self.ctl_client.request({'cmd': 'status', 'peek': True})
                    return self
                except NotRunning:
                    time.sleep(0.05)
            raise RuntimeError('service did not start')
        self._start_thread()
        return self

    def _start_thread(self) -> None:
        from sparklink import config, identity
        from sparklink.desktop import FakeDesktop
        from sparklink.devices import Devices
        from sparklink.service import Service as Svc
        data = os.path.join(self.env['XDG_DATA_HOME'], 'spark-link')
        settings = config.Settings(os.path.join(self.env['XDG_CONFIG_HOME'], 'spark-link',
                                                'settings.json'))
        ident = identity.load_or_create(data)
        devices = Devices(os.path.join(data, 'devices.json'))
        self.service = Svc(settings, ident, devices, FakeDesktop(self.log, self.downloads),
                           announce=False)
        ready = threading.Event()

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.call_soon(ready.set)
            self.loop.run_until_complete(self.service.run(None))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(10)
        time.sleep(0.2)

    def stop(self) -> None:
        try:
            self.ctl({'cmd': 'stop'})
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            if self.ctl_client:
                self.ctl_client.close()
        if self.thread is not None:
            self.thread.join(10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def output(self) -> str:
        if self.proc is not None and self.proc.stdout and self.proc.poll() is not None:
            return self.proc.stdout.read().decode('utf-8', 'replace')
        return ''

    # ── talking to it ──
    def ctl(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if self.proc is not None:
            return self.ctl_client.request(req)
        fut = asyncio.run_coroutine_threadsafe(self.service.control(req), self.loop)
        return fut.result(10)

    async def actl(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, self.ctl, req)

    def status(self) -> Dict[str, Any]:
        return self.ctl({'cmd': 'status', 'peek': True})

    async def wait_status(self, check, timeout: float = 10.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            st = await self.actl({'cmd': 'status', 'peek': True})
            if check(st):
                return st
            if time.monotonic() > deadline:
                raise AssertionError(f'status never matched: {json.dumps(st)[:2000]}')
            await asyncio.sleep(0.05)

    def actions(self, kind: str = None) -> List[Dict[str, Any]]:
        try:
            with open(self.log, encoding='utf-8') as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            rows = []
        return [r for r in rows if kind is None or r['action'] == kind]

    async def wait_action(self, kind: str, timeout: float = 10.0, **match) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for row in self.actions(kind):
                if all(row.get(k) == v for k, v in match.items()):
                    return row
            await asyncio.sleep(0.05)
        raise AssertionError(f'no {kind} {match}; saw {self.actions()}')
