"""Music that keeps playing while you browse: one audio player and the play queue, owned by the
app rather than by a screen. Screens listen for what happens and send it commands."""

import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import player as gst
from .core import log
from .playqueue import PlayQueue

POLL_MS = 150            # only while something plays
SKIP_AFTER_ERROR_MS = 1500

Listener = Callable[[str, Any], None]


class MusicSession:
    def __init__(self, app):
        self.app = app
        self.queue = PlayQueue()
        self.listeners: List[Listener] = []
        self.player: Optional[gst.Player] = None
        self.problem: Optional[str] = gst.init()
        self.finished = False
        self.error: Optional[str] = None
        self._poll_id: Optional[str] = None
        self._skip_id: Optional[str] = None
        self._errors_in_row = 0
        if self.problem is None:
            try:
                # no window: fakesink stands in for video, which is never decoded anyway
                self.player = gst.Player(self._on_player, video_sink='fakesink',
                                         audio_sink=os.environ.get('SPARK_MEDIA_AUDIO_SINK'))
            except RuntimeError as exc:
                self.problem = str(exc)
        if self.player is not None:
            sink = self.player.playbin.get_property('audio-sink')
            if sink is not None and sink.find_property('sync') is not None:
                sink.set_property('sync', True)     # a test's fakesink plays in real time too
            saved = app.settings.get("volume")
            self.player.volume = float(saved) if isinstance(saved, (int, float)) else 0.8
            self.player.muted = bool(app.settings.get("muted", False))

    # ── listeners ──
    def listen(self, fn: Listener) -> None:
        if fn not in self.listeners:
            self.listeners.append(fn)

    def unlisten(self, fn: Listener) -> None:
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _emit(self, what: str, data: Any = None) -> None:
        for fn in list(self.listeners):
            try:
                fn(what, data)
            except Exception:      # noqa: BLE001 - a broken screen must not stop the music
                log.exception("music listener failed on %s", what)

    # ── what's playing ──
    @property
    def current(self) -> Optional[str]:
        return self.queue.current

    @property
    def playing(self) -> bool:
        return bool(self.player and self.player.playing)

    def info(self, path: Optional[str] = None) -> Dict[str, Any]:
        """title, artist, album for a song: the library's tags, else the player's, else the
        file name."""
        path = path or self.current
        out = {'title': '', 'artist': '', 'album': '', 'path': path}
        if not path:
            return out
        song = self.app.song_info(path)
        if song:
            out.update(title=song.get('title') or '', artist=song.get('artist') or '',
                       album=song.get('album') or '')
        if self.player is not None and path == self.player.path:
            tags = self.player.tags
            out['title'] = out['title'] or tags.title or ''
            out['artist'] = out['artist'] or tags.artist or ''
            out['album'] = out['album'] or tags.album or ''
        out['title'] = out['title'] or os.path.splitext(os.path.basename(path))[0]
        return out

    # ── commands ──
    def play(self, items: Sequence[str], start: int = 0, shuffle: Optional[bool] = None) -> None:
        if not items:
            return
        if shuffle is not None:
            self.queue.shuffle = shuffle
        self.queue.set(items, start)
        self._errors_in_row = 0
        self._load()
        self._emit('queue')

    def add(self, items: Sequence[str]) -> None:
        idle = self.current is None
        self.queue.add(items)
        self._emit('queue')
        if idle and self.current:
            self._load()

    def play_next(self, items: Sequence[str]) -> None:
        idle = self.current is None
        self.queue.play_next(items)
        self._emit('queue')
        if idle and self.current:
            self._load()

    def jump(self, item_index: int) -> None:
        if self.queue.jump(item_index):
            self._load()

    def remove(self, item_index: int) -> None:
        was_current = item_index == self.queue.index
        self.queue.remove(item_index)
        self._emit('queue')
        if was_current:
            if self.current:
                self._load(play=self.playing)
            else:
                self.stop()

    def move(self, item_index: int, delta: int) -> None:
        self.queue.move(item_index, delta)
        self._emit('queue')

    def clear(self) -> None:
        self.queue.clear_upcoming()
        self._emit('queue')

    def toggle(self) -> None:
        if self.player is None or self.current is None:
            return
        if self.error and not self.player.playing:
            self._load()                       # try the file again
            return
        self.player.toggle()
        self.finished = False
        self._emit('state')
        self._ensure_poll()

    def next(self) -> None:
        if self.queue.next(wrap=True):
            self._load()

    def prev(self) -> None:
        if self.player is None:
            return
        pos = self.player.position() or 0
        if pos > 3 or len(self.queue) < 2:
            self.player.seek(0)
            self._emit('tick')
            return
        if self.queue.prev():
            self._load()

    def seek(self, seconds: float, accurate: bool = True) -> None:
        if self.player is not None:
            self.player.seek(seconds, accurate)

    def set_shuffle(self, on: bool) -> None:
        self.queue.set_shuffle(on)
        self._emit('queue')

    def set_repeat(self, on: bool) -> None:
        self.queue.repeat = on
        self._emit('state')

    def set_volume(self, value: float) -> None:
        if self.player is not None:
            self.player.volume = value
            if self.player.muted and value > 0:
                self.player.muted = False
            self.app.settings["volume"] = round(self.player.volume, 3)
            self.app.settings["muted"] = self.player.muted

    def set_muted(self, on: bool) -> None:
        if self.player is not None:
            self.player.muted = on
            self.app.settings["muted"] = on

    def pause(self) -> None:
        if self.player is not None and self.player.playing:
            self.player.pause()
            self._emit('state')

    def stop(self) -> None:
        self._cancel()
        if self.player is not None:
            self.player.stop()
        self._emit('state')

    def close(self) -> None:
        self._cancel()
        self.listeners.clear()
        if self.player is not None:
            self.player.close()
            self.player = None

    # ── inside ──
    def _load(self, play: bool = True) -> None:
        if self.player is None or self.current is None:
            return
        if self._skip_id:
            self.app.root.after_cancel(self._skip_id)
            self._skip_id = None
        path = self.current
        self.finished, self.error = False, None
        log.info("music: %s", path)
        self.player.load(path, video=False, play=play)
        self._emit('track', path)
        self._ensure_poll()

    def _ensure_poll(self) -> None:
        if self._poll_id is None and self.player is not None:
            self._poll_id = self.app.root.after(POLL_MS, self._poll)

    def _poll(self) -> None:
        self._poll_id = None
        if self.player is None:
            return
        self.player.poll()
        self._emit('tick')
        if self.player is not None and self.player.playing and self._poll_id is None:
            self._poll_id = self.app.root.after(POLL_MS, self._poll)

    def _cancel(self) -> None:
        for name in ('_poll_id', '_skip_id'):
            job = getattr(self, name)
            if job:
                try:
                    self.app.root.after_cancel(job)
                except Exception:      # noqa: BLE001
                    pass
                setattr(self, name, None)

    def _on_player(self, what: str, data: Any) -> None:
        if what == 'eos':
            if self.queue.next():
                self._load()
            else:
                self.finished = True
                self._emit('finished')
        elif what == 'error':
            self.error = str(data)
            self._errors_in_row += 1
            self._emit('error', data)
            # a missing or broken file in a playlist: go on to the next song after a moment
            if not self.queue.is_last() and self._errors_in_row < len(self.queue):
                self._skip_id = self.app.root.after(SKIP_AFTER_ERROR_MS, self._skip)
        elif what == 'ready':
            self._errors_in_row = 0
            self._emit('ready')
        elif what == 'tags':
            self._emit('tags', data)

    def _skip(self) -> None:
        self._skip_id = None
        if self.queue.next():
            self._load()
