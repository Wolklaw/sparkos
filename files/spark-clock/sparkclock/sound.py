"""Playing the alarm sound, through PipeWire (pw-play) or, if that is missing, PulseAudio's
paplay, GStreamer or ffplay. One program run per play; a loop starts it again after a short gap
until it is stopped. No threads: the service's one-second tick calls Loop.tick()."""

import os
import shutil
import subprocess
from typing import List, Optional

from . import core
from .core import log

BUILT_IN = ('beacon', 'pulse', 'chime', 'drift', 'static')
GAP = 0.8                      # seconds of quiet between two plays of the file
PLAYERS = ('pw-play', 'paplay', 'gst-play-1.0', 'ffplay')


def sound_path(name: str) -> Optional[str]:
    """A built-in sound's name or a path to an audio file -> a file that exists, else None."""
    if name in BUILT_IN:
        found = os.path.join(core.lib_dir(), 'sounds', name + '.wav')
        return found if os.path.isfile(found) else None
    if name and os.path.isabs(name) and os.path.isfile(name):
        return name
    return None


def find_player() -> Optional[str]:
    """The command that plays a file. SPARK_CLOCK_PLAYER overrides it (the tests use it)."""
    forced = os.environ.get('SPARK_CLOCK_PLAYER')
    if forced:
        return forced
    for name in PLAYERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def play_command(player: str, file: str, volume: int) -> List[str]:
    base = os.path.basename(player)
    level = max(0, min(100, volume)) / 100
    if base == 'pw-play':
        return [player, f"--volume={level:.2f}", file]
    if base == 'paplay':
        return [player, f"--volume={int(level * 65536)}", file]
    if base == 'gst-play-1.0':
        return [player, '--quiet', f"--volume={level:.2f}", file]
    if base == 'ffplay':
        return [player, '-nodisp', '-autoexit', '-loglevel', 'quiet', '-volume',
                str(int(level * 100)), file]
    return [player, file, str(volume)]


class Loop:
    """One sound, played again and again until stop()."""

    def __init__(self, clock=None):
        self.proc: Optional[subprocess.Popen] = None
        self.file: Optional[str] = None
        self.volume = 80
        self.next_at = 0.0
        self.plays = 0
        self.clock = clock or core.now
        self.broken = False

    @property
    def playing(self) -> bool:
        return self.file is not None

    def start(self, name: str, volume: int = 80) -> bool:
        """Start the loop. False if there is nothing to play it with or nothing to play."""
        self.stop()
        file = sound_path(name) or sound_path('beacon')
        self.broken = file is None or find_player() is None
        if self.broken:
            log.warning("no sound: file=%s player=%s", file, find_player())
            return False
        self.file, self.volume, self.next_at, self.plays = file, volume, 0.0, 0
        self.tick()
        return True

    def tick(self) -> None:
        if self.file is None:
            return
        if self.proc is not None:
            if self.proc.poll() is None:
                return
            self.proc = None
            self.next_at = self.clock() + GAP
        if self.clock() < self.next_at:
            return
        player = find_player()
        if player is None:
            return
        try:
            self.proc = subprocess.Popen(play_command(player, self.file, self.volume),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
            self.plays += 1
        except OSError as exc:
            log.warning("can't start %s: %s", player, exc)
            self.next_at = self.clock() + 5

    def stop(self) -> None:
        proc, self.proc, self.file = self.proc, None, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)           # reap it, or it stays a zombie
                except subprocess.TimeoutExpired:
                    pass


def play_once(name: str, volume: int = 80) -> Optional[subprocess.Popen]:
    """The preview button: the sound once, not waited for."""
    file, player = sound_path(name), find_player()
    if file is None or player is None:
        return None
    try:
        return subprocess.Popen(play_command(player, file, volume), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None
