"""Level meters and the 3-second mic test.

A meter is one `pw-record` writing raw 8 kHz mono samples; a thread turns them into a peak
25 times a second. A meter only exists while its row is on screen, and the window stops them
all when it is hidden, so an idle mixer opens no audio stream."""

import array
import math
import os
import subprocess
import tempfile
import threading
import time
from typing import Callable, Dict, Optional

from . import core
from .core import log
from .model import OWN_PREFIX

RATE = 8000
CHUNK = 320          # samples: 40 ms


class Meter:
    """Peak of what an output plays (its monitor) or an input hears, 0..1 on a dB-ish scale."""

    def __init__(self, node_name: str, is_sink: bool):
        self.node_name, self.is_sink = node_name, is_sink
        self.peak = 0.0
        self.alive = False
        self.stamp = 0.0
        self._proc: Optional[subprocess.Popen] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        argv = ['pw-record', '--raw', '--target', self.node_name, '--rate', str(RATE),
                '--channels', '1', '--format', 's16', '--latency', '40ms',
                '-P', f'{{ node.name = {OWN_PREFIX}meter media.name = {OWN_PREFIX}meter '
                      f'node.dont-reconnect = true'
                      + (' stream.capture.sink = true' if self.is_sink else '') + ' }',
                '-']
        try:
            self._proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                          bufsize=0)
        except OSError as exc:
            log.warning("meter for %s: %s", self.node_name, exc)
            return
        self.alive = True
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        fd = self._proc.stdout.fileno()
        pending = b''
        while not self._stop.is_set():
            data = os.read(fd, 4096)
            if not data:
                break
            pending += data
            usable = len(pending) - len(pending) % 2
            samples = array.array('h')
            samples.frombytes(pending[:usable])
            pending = pending[usable:]
            if samples:
                self.peak = level(max(abs(s) for s in samples) / 32768.0)
                self.stamp = time.monotonic()
        self.alive = False

    def read(self) -> float:
        """The current level, falling away smoothly when nothing new arrives."""
        if time.monotonic() - self.stamp > 0.3:       # no data: the stream is idle
            self.peak *= 0.8
        return self.peak

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.kill()
        self.alive = False
        self.peak = 0.0


def level(amplitude: float) -> float:
    """Amplitude (0..1) to a meter position (0..1): -60 dB at the bottom, 0 dB at the top."""
    if amplitude <= 0.001:
        return 0.0
    return max(0.0, min(1.0, 1.0 + 20 * math.log10(amplitude) / 60.0))


class FakeMeter(Meter):
    """A moving level that needs no audio (tests and screenshots)."""

    def __init__(self, node_name: str, is_sink: bool, seed: int = 0):
        super().__init__(node_name, is_sink)
        self.seed = seed or (sum(map(ord, node_name)) % 7)
        self.t0 = time.monotonic()

    def start(self) -> None:
        self.alive = True

    def read(self) -> float:
        t = time.monotonic() - self.t0
        v = 0.55 + 0.25 * math.sin(t * (2.1 + self.seed * 0.3)) + 0.12 * math.sin(t * 9.7)
        return max(0.0, min(1.0, v))


class MeterSet:
    """The meters that are on screen now, started and stopped as rows come and go."""

    def __init__(self, fake: bool = False):
        self.fake = fake
        self.meters: Dict[str, Meter] = {}

    def want(self, wanted: Dict[str, bool]) -> None:
        """wanted: node name -> is_sink. Starts missing meters, stops the ones not wanted."""
        for name in list(self.meters):
            if name not in wanted:
                self.meters.pop(name).stop()
        for name, is_sink in wanted.items():
            m = self.meters.get(name)
            if m is not None and not m.alive and not self.fake:
                self.meters.pop(name).stop()
                m = None
            if m is None:
                m = (FakeMeter if self.fake else Meter)(name, is_sink)
                m.start()
                self.meters[name] = m

    def read(self, name: str) -> float:
        m = self.meters.get(name)
        return m.read() if m else 0.0

    def stop_all(self) -> None:
        self.want({})


class MicTest:
    """Record 3 seconds from an input, then play them back on the default output.

    state: idle -> recording -> playing -> idle (or 'failed' with .error)"""

    SECONDS = 3

    def __init__(self, on_change: Callable[[], None], fake: bool = False):
        self.on_change = on_change
        self.fake = fake
        self.state = 'idle'
        self.error = ''
        self.started = 0.0
        self.path: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._cancel = threading.Event()

    def start(self, source_name: str, sink_name: Optional[str]) -> None:
        if self.state in ('recording', 'playing'):
            return
        self.state, self.error = 'recording', ''
        self.started = time.monotonic()
        self._cancel.clear()
        threading.Thread(target=self._run, args=(source_name, sink_name), daemon=True).start()
        self.on_change()

    def cancel(self) -> None:
        self._cancel.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _set(self, state: str, error: str = '') -> None:
        self.state, self.error = state, error
        self.started = time.monotonic()
        self.on_change()

    def _run(self, source_name: str, sink_name: Optional[str]) -> None:
        folder = os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()
        fd, path = tempfile.mkstemp(prefix='spark-audio-test-', suffix='.wav', dir=folder)
        os.close(fd)
        self.path = path
        try:
            if self.fake:
                self._cancel.wait(self.SECONDS)
                self._set('playing')
                self._cancel.wait(self.SECONDS)
                self._set('idle')
                return
            record = ['pw-record', '--target', source_name, '--rate', '48000', '--channels', '1',
                      '-n', str(48000 * self.SECONDS),
                      '-P', f'{{ node.name = {OWN_PREFIX}test media.name = {OWN_PREFIX}test }}',
                      path]
            self._proc = subprocess.Popen(record, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.PIPE, text=True)
            try:
                _, err = self._proc.communicate(timeout=self.SECONDS + 6)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.communicate()
                err = "recording did not stop"
            if self._cancel.is_set():
                self._set('idle')
                return
            # pw-record can exit non-zero after a good recording (a slow PipeWire sync on the way
            # out), so what counts is whether it wrote anything
            if os.path.getsize(path) < 4096:
                self._set('failed', (err or "nothing was recorded").strip().splitlines()[-1])
                return
            self._set('playing')
            play = ['pw-play', '-P', f'{{ node.name = {OWN_PREFIX}test media.name = {OWN_PREFIX}test }}']
            if sink_name:
                play += ['--target', sink_name]
            self._proc = subprocess.Popen(play + [path], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.PIPE, text=True)
            try:
                _, err = self._proc.communicate(timeout=self.SECONDS + 8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.communicate()
            self._set('idle')
        except OSError as exc:
            self._set('failed', str(exc))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
