"""Volume through Spark Audio's own PipeWire backend (sparkaudio.backend), so there is one code
path: the same graph reader, the same wpctl calls and the same volume scale as the mixer window.

Spark Audio is a separate app. This finds its folder (a copy installed for the user, then a live
update, then the image's) and imports it. If Spark Audio isn't there, the volume item is off:
Spark Tray never carries a second PipeWire client of its own."""

import glob
import importlib
import os
import sys
from typing import Callable, List, Optional

from gi.repository import GLib

from .core import log

STEP = 0.05          # one scroll notch, in the slider scale (cube root of the gain)
MAX = 1.0            # the tray stays at 100%; the mixer window goes to 150%


def candidates() -> List[str]:
    forced = os.environ.get('SPARK_AUDIO_DIR')
    if forced:
        return [forced]
    home = os.path.expanduser('~')
    live = sorted(glob.glob('/var/lib/spark-apps/spark-audio/*/'), reverse=True)
    return [os.path.join(home, '.local/lib/spark-audio'), *live, '/usr/lib/spark-audio']


def find_spark_audio() -> Optional[str]:
    for folder in candidates():
        if os.path.isfile(os.path.join(folder, 'sparkaudio', 'backend.py')):
            return folder
    return None


def load_backend_module():
    """Import sparkaudio.backend from wherever Spark Audio is; None if it isn't installed."""
    if 'sparkaudio.backend' in sys.modules:
        return sys.modules['sparkaudio.backend']
    folder = find_spark_audio()
    if not folder:
        return None
    sys.path.insert(0, folder)
    try:
        return importlib.import_module('sparkaudio.backend')
    except Exception as exc:                      # noqa: BLE001 - a broken copy means "no volume"
        log.warning("Spark Audio's backend didn't load from %s: %s", folder, exc)
        return None
    finally:
        sys.path.remove(folder)


class Volume:
    """The default output: its name, volume (0..1 slider scale) and mute."""

    def __init__(self, on_change: Callable[[], None] = lambda: None, fake_dir: str = ''):
        self.on_change, self.fake_dir = on_change, fake_dir
        self.backend = None
        self._watch = 0
        # (node id, level) last asked for: Spark Audio sets the volume on a worker thread, so
        # quick scroll notches must count from what was asked, not from the level not yet set
        self._asked = None

    def start(self) -> bool:
        mod = load_backend_module()
        if mod is None:
            return False
        self.backend = mod.make_backend(self.fake_dir or None)
        self.backend.start()
        fd = self.backend.wake_fd
        self._watch = GLib.io_add_watch(fd, GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN,
                                        self._wake)
        return True

    def stop(self) -> None:
        if self._watch:
            GLib.source_remove(self._watch)
            self._watch = 0
        if self.backend:
            self.backend.close()
            self.backend = None

    def _wake(self, _fd, _cond) -> bool:
        changed = self.backend.drain() if self.backend else False
        if changed and self._asked:
            n = self.output()
            if not n or n.id != self._asked[0] or n.volume is None or abs(n.volume - self._asked[1]) < 0.005:
                self._asked = None
        if changed:
            self.on_change()
        return True

    def state(self):
        return self.backend.state() if self.backend else None

    def output(self):
        s = self.state()
        return s.sink_by_id(s.default_sink) if s else None

    def outputs(self) -> list:
        s = self.state()
        return list(s.sinks) if s else []

    def level(self) -> Optional[float]:
        n = self.output()
        if n and self._asked and self._asked[0] == n.id:
            return self._asked[1]
        return n.volume if n else None

    def muted(self) -> bool:
        n = self.output()
        return bool(n and n.mute)

    def set_level(self, value: float) -> None:
        n = self.output()
        if n:
            value = max(0.0, min(MAX, value))
            self._asked = (n.id, value)
            self.backend.set_volume(n, value)

    def nudge(self, notches: int) -> None:
        """Scroll: up is louder. Moving the volume up from muted turns the sound on."""
        n = self.output()
        if not n or n.volume is None:
            return
        if notches > 0 and n.mute:
            self.backend.set_mute(n, False)
        self.set_level(round(self.level() + notches * STEP, 3))

    def toggle_mute(self) -> None:
        n = self.output()
        if n:
            self.backend.set_mute(n, not n.mute)

    def set_default(self, node) -> None:
        self.backend.set_default(node)


def icon_for(level: Optional[float], muted: bool) -> str:
    if level is None:
        return 'audio-volume-muted'
    if muted or level <= 0.0:
        return 'audio-volume-muted'
    if level < 0.34:
        return 'audio-volume-low'
    if level < 0.67:
        return 'audio-volume-medium'
    return 'audio-volume-high'
