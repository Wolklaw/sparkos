"""Talking to PipeWire.

Reading: one long-running `pw-dump --monitor` prints the whole graph once, then only what
changes, so the window updates when something happens and costs nothing when nothing does.
Writing: wpctl (volume, mute, default output), pactl (move an app's stream, pick a card
profile). Every command runs on a worker thread so the window never waits for it.

FakeBackend answers the same calls from a saved pw-dump (tests, screenshots, --fake DIR) and
changes that copy in memory; it starts no program."""

import json
import os
import queue
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence

from .core import log, run, volume_to_gain
from .model import CAPTURE, PLAYBACK, SINK, SOURCE, Graph, Node, State, parse_dump


class Backend:
    fake = False

    def __init__(self):
        self.graph = Graph()
        self.lock = threading.Lock()
        self.connected = False
        self.error = ""
        self._dirty = True
        self._state: Optional[State] = None
        self._stop = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._done: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._wake_r, self._wake_w = os.pipe()
        os.set_blocking(self._wake_r, False)
        os.set_blocking(self._wake_w, False)
        self._pending: Dict[int, float] = {}
        self._volume_busy: set = set()
        self._plock = threading.Lock()

    # — the wake-up pipe: Tk's file handler watches wake_fd —
    @property
    def wake_fd(self) -> int:
        return self._wake_r

    def _wake(self) -> None:
        try:
            os.write(self._wake_w, b'x')
        except OSError:
            pass

    def drain(self) -> bool:
        """Call when wake_fd is readable. Runs finished-command callbacks (on the calling
        thread) and says whether the graph changed."""
        try:
            while os.read(self._wake_r, 4096):
                pass
        except (BlockingIOError, OSError):
            pass
        while True:
            try:
                self._done.get_nowait()()
            except queue.Empty:
                break
            except Exception:                   # noqa: BLE001 - a callback must not stop the loop
                log.exception("callback failed")
        with self.lock:
            changed, self._dirty = self._dirty, False
        return changed

    def post(self, fn: Callable[[], None]) -> None:
        """Run fn on the Tk thread (from drain). Safe to call from any thread."""
        self._done.put(fn)
        self._wake()

    # — reading —
    def start(self) -> None:
        self._thread = threading.Thread(target=self._reader, name="pw-dump", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.kill()

    def state(self) -> State:
        with self.lock:
            if self._state is None or self._dirty_state:
                self._state = self.graph.state()
                self._dirty_state = False
            return self._state

    _dirty_state = True

    def _reader(self) -> None:
        while not self._stop.is_set():
            try:
                self._proc = subprocess.Popen(['pw-dump', '--monitor'], stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, bufsize=0)
            except OSError as exc:
                self.error = f"pw-dump: {exc}"
                self.connected = False
                self._signal()
                self._stop.wait(3)
                continue
            with self.lock:
                self.graph = Graph()
            self.connected = True
            self.error = ""
            buf = ""
            decoder = json.JSONDecoder()
            fd = self._proc.stdout.fileno()
            while not self._stop.is_set():
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                buf += chunk.decode('utf-8', errors='replace')
                batch = []
                while True:
                    buf = buf.lstrip()
                    if not buf:
                        break
                    try:
                        value, end = decoder.raw_decode(buf)
                    except ValueError:
                        break               # not all of it has arrived yet
                    buf = buf[end:]
                    if isinstance(value, list):
                        batch.append(value)
                if batch:
                    with self.lock:
                        for updates in batch:
                            self.graph.apply(updates)
                    self._signal()
            self.connected = False
            self.error = "PipeWire is not running"
            self._signal()
            if self._proc and self._proc.poll() is None:
                self._proc.kill()
            self._stop.wait(2)

    def _signal(self) -> None:
        with self.lock:
            self._dirty = True
            self._dirty_state = True
        self._wake()

    # — writing —
    def submit(self, work: Callable[[], Any], done: Optional[Callable[[Any], None]] = None) -> None:
        def job():
            try:
                result = work()
            except Exception as exc:        # noqa: BLE001
                log.exception("command failed")
                result = exc
            if done is not None:
                self._done.put(lambda: done(result))
                self._wake()
        threading.Thread(target=job, daemon=True).start()

    def command(self, argv: Sequence[str], done: Optional[Callable[[Any], None]] = None) -> None:
        def work():
            r = run(argv)
            if r.returncode != 0:
                log.warning("%s -> %s %s", ' '.join(argv), r.returncode, r.stderr.strip())
            return r
        self.submit(work, done)

    def set_volume(self, node: Node, volume: float) -> None:
        """volume is the slider scale. Dragging sends many values; only the latest matters,
        so one worker per node sends the newest and then looks again."""
        with self._plock:
            self._pending[node.id] = volume
            if node.id in self._volume_busy:
                return
            self._volume_busy.add(node.id)

        def work():
            while True:
                with self._plock:
                    value = self._pending.pop(node.id, None)
                    if value is None:
                        self._volume_busy.discard(node.id)
                        return
                self._apply_volume(node, value)
        threading.Thread(target=work, daemon=True).start()

    def _apply_volume(self, node: Node, volume: float) -> None:
        run(['wpctl', 'set-volume', str(node.id), f"{max(0.0, min(1.5, volume)):.3f}"])

    def set_mute(self, node: Node, mute: bool, done=None) -> None:
        self.command(['wpctl', 'set-mute', str(node.id), '1' if mute else '0'], done)

    def set_default(self, node: Node, done=None) -> None:
        self.command(['wpctl', 'set-default', str(node.id)], done)

    def move_stream(self, stream: Node, target: Node, done=None) -> None:
        verb = 'move-sink-input' if stream.kind == PLAYBACK else 'move-source-output'
        self.command(['pactl', verb, str(stream.serial), target.name], done)

    def set_profile(self, card_name: str, profile_name: str, done=None) -> None:
        self.command(['pactl', 'set-card-profile', card_name, profile_name], done)

    def set_param(self, node_id: int, params: List[Any]) -> None:
        """Change a filter-chain control live (an EQ band)."""
        body = '{ params = [ ' + ' '.join(json.dumps(p) if isinstance(p, str) else repr(float(p))
                                          for p in params) + ' ] }'
        self.command(['pw-cli', 's', str(node_id), 'Props', body])

    def close(self) -> None:
        self.stop()


class FakeBackend(Backend):
    """The same calls answered from a saved pw-dump; nothing is started."""
    fake = True

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder
        self.calls: List[tuple] = []
        path = os.path.join(folder, 'pw-dump.json')
        with open(path, encoding='utf-8') as f:
            for updates in parse_dump(f.read()):
                self.graph.apply(updates)
        self.connected = True

    def start(self) -> None:
        self._signal()

    def stop(self) -> None:
        pass

    def _node_obj(self, node: Node) -> Optional[Dict[str, Any]]:
        return self.graph.objects.get(node.id)

    def _apply_volume(self, node: Node, volume: float) -> None:
        self.calls.append(('volume', node.id, round(volume, 3)))
        obj = self._node_obj(node)
        if obj:
            with self.lock:
                p = obj['info'].setdefault('params', {}).setdefault('Props', [{}])[0]
                gain = volume_to_gain(volume)
                p['channelVolumes'] = [gain] * max(1, len(p.get('channelVolumes') or [0, 0]))
                p['volume'] = 1.0
            self._signal()

    def _edit_props(self, node: Node, **values) -> None:
        obj = self._node_obj(node)
        if obj:
            with self.lock:
                obj['info'].setdefault('params', {}).setdefault('Props', [{}])[0].update(values)
            self._signal()

    def set_mute(self, node: Node, mute: bool, done=None) -> None:
        self.calls.append(('mute', node.id, mute))
        self._edit_props(node, mute=mute)
        if done:
            self.submit(lambda: None, lambda _r: done(None))

    def set_default(self, node: Node, done=None) -> None:
        self.calls.append(('default', node.id))
        key = 'default.audio.sink' if node.kind == SINK else 'default.audio.source'
        with self.lock:
            for obj in self.graph.objects.values():
                if obj.get('props', {}).get('metadata.name') == 'default':
                    obj['metadata'] = [e for e in obj.get('metadata', []) if e.get('key') != key]
                    obj['metadata'].append({'subject': 0, 'key': key, 'type': 'Spa:String:JSON',
                                            'value': {'name': node.name}})
        self._signal()
        if done:
            self.submit(lambda: None, lambda _r: done(None))

    def move_stream(self, stream: Node, target: Node, done=None) -> None:
        self.calls.append(('move', stream.id, target.id))
        with self.lock:
            for obj in self.graph.objects.values():
                info = obj.get('info') or {}
                if obj.get('type', '').endswith(':Link'):
                    if stream.kind == PLAYBACK and info.get('output-node-id') == stream.id:
                        info['input-node-id'] = target.id
                    if stream.kind == CAPTURE and info.get('input-node-id') == stream.id:
                        info['output-node-id'] = target.id
        self._signal()
        if done:
            self.submit(lambda: None, lambda _r: done(None))

    def set_profile(self, card_name: str, profile_name: str, done=None) -> None:
        self.calls.append(('profile', card_name, profile_name))
        if done:
            self.submit(lambda: None, lambda _r: done(None))

    def set_param(self, node_id: int, params: List[Any]) -> None:
        self.calls.append(('param', node_id, tuple(params)))

    def command(self, argv, done=None) -> None:
        self.calls.append(('command', tuple(argv)))
        if done:
            self.submit(lambda: None, lambda _r: done(None))


def make_backend(fake_dir: Optional[str]) -> Backend:
    return FakeBackend(fake_dir) if fake_dir else Backend()


def has_tools() -> Dict[str, bool]:
    import shutil
    return {name: shutil.which(name) is not None
            for name in ('pw-dump', 'wpctl', 'pactl', 'pw-record', 'pw-play', 'pw-cli', 'amixer')}
