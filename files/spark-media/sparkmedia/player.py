"""Video and music through GStreamer's playbin.

No GLib main loop: the app polls the bus from Tk's timer. Video draws straight into a Tk
frame through the sink's window handle (Tk runs on X11, XWayland on a Wayland desktop), so
frames never pass through Python.
"""

import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from .core import file_uri, log, store_thumbnail, cached_thumbnail, subtitle_for, THUMB_SIZES

Gst = GstVideo = GstPbutils = None
GST_ERROR: Optional[str] = None
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstVideo', '1.0')
    from gi.repository import Gst, GstVideo      # type: ignore  # noqa: F811
    try:
        gi.require_version('GstPbutils', '1.0')
        from gi.repository import GstPbutils     # type: ignore  # noqa: F811
    except (ImportError, ValueError):
        GstPbutils = None
except (ImportError, ValueError) as exc:
    GST_ERROR = str(exc)

FLAG_VIDEO, FLAG_AUDIO, FLAG_TEXT, FLAG_SOFT_VOLUME = 1, 2, 4, 16
SECOND = 1_000_000_000
_init_lock = threading.Lock()
_ready = False


def available() -> bool:
    return init() is None


def init() -> Optional[str]:
    """Start GStreamer once. None when ready, otherwise why video and music can't play."""
    global _ready, GST_ERROR
    if Gst is None:
        return GST_ERROR or "GStreamer's Python bindings (python3-gobject) aren't installed"
    with _init_lock:
        if not _ready:
            # Tk windows are X11 windows, even on Wayland, so GL video must draw through X11
            os.environ.setdefault('GST_GL_WINDOW', 'x11')
            try:
                Gst.init(None)
            except Exception as exc:      # noqa: BLE001
                GST_ERROR = f"GStreamer would not start: {exc}"
                return GST_ERROR
            if Gst.ElementFactory.find('playbin') is None:
                GST_ERROR = "GStreamer's playbin is missing (gstreamer1-plugins-base)"
                return GST_ERROR
            _ready = True
    return None


def gst_version() -> str:
    if init() is not None:
        return ""
    return Gst.version_string().replace('GStreamer ', '')


def video_sink_names() -> List[str]:
    """Sinks that can draw into our window, best first, among those installed."""
    if init() is not None:
        return []
    return [name for name in ('glimagesink', 'xvimagesink', 'ximagesink')
            if Gst.ElementFactory.find(name) is not None]


# What a missing decoder means to a person
CODECS: Dict[str, Tuple[str, str]] = {
    'h264': ('H.264 video', 'video/x-h264, stream-format=(string)byte-stream, alignment=(string)au'),
    'h265': ('H.265 / HEVC video', 'video/x-h265, stream-format=(string)byte-stream, alignment=(string)au'),
    'vp8': ('VP8 video', 'video/x-vp8'),
    'vp9': ('VP9 video', 'video/x-vp9'),
    'av1': ('AV1 video', 'video/x-av1'),
    'mpeg2': ('MPEG-2 video', 'video/mpeg, mpegversion=(int)2, systemstream=(boolean)false'),
    'mp3': ('MP3 audio', 'audio/mpeg, mpegversion=(int)1, layer=(int)3'),
    'aac': ('AAC audio', 'audio/mpeg, mpegversion=(int)4, stream-format=(string)raw'),
    'flac': ('FLAC audio', 'audio/x-flac'),
    'vorbis': ('Vorbis audio', 'audio/x-vorbis'),
    'opus': ('Opus audio', 'audio/x-opus'),
    'ac3': ('Dolby Digital (AC-3) audio', 'audio/x-ac3'),
}


def decoders() -> Dict[str, bool]:
    """Which formats this system can decode."""
    if init() is not None:
        return {key: False for key in CODECS}
    factories = Gst.ElementFactory.list_get_elements(Gst.ELEMENT_FACTORY_TYPE_DECODER,
                                                     Gst.Rank.MARGINAL)
    out = {}
    for key, (_label, caps) in CODECS.items():
        wanted = Gst.Caps.from_string(caps)
        out[key] = any(f.can_sink_any_caps(wanted) for f in factories)
    return out


class Tags:
    def __init__(self):
        self.title: Optional[str] = None
        self.artist: Optional[str] = None
        self.album: Optional[str] = None
        self.cover: Optional[Image.Image] = None
        self.video_codec: Optional[str] = None
        self.audio_codec: Optional[str] = None


class Player:
    """One playbin. Call poll() often (every ~100 ms) from the UI thread."""

    def __init__(self, on_event: Callable[[str, Any], None], window_handle: Optional[int] = None,
                 audio_sink: Optional[str] = None, video_sink: Optional[str] = None):
        problem = init()
        if problem:
            raise RuntimeError(problem)
        self.on_event = on_event
        self.playbin = Gst.ElementFactory.make('playbin', 'player')
        if self.playbin is None:
            raise RuntimeError("could not make a GStreamer playbin")
        self.window_handle = window_handle
        self.sink = None
        names = [video_sink] if video_sink else video_sink_names()
        for name in names:
            sink = Gst.ElementFactory.make(name, None)
            if sink is None:
                continue
            for prop, value in (('force-aspect-ratio', True), ('handle-events', False)):
                if sink.find_property(prop) is not None:
                    sink.set_property(prop, value)
            self.sink = sink
            log.info("video sink: %s", name)
            break
        if self.sink is not None:
            self.playbin.set_property('video-sink', self.sink)
        if audio_sink:
            self.playbin.set_property('audio-sink', Gst.ElementFactory.make(audio_sink, None))
        self.bus = self.playbin.get_bus()
        self.uri: Optional[str] = None
        self.path: Optional[str] = None
        self.tags = Tags()
        self.duration: Optional[float] = None
        self.playing = False
        self.ended = False
        self.error: Optional[str] = None
        self.subtitles_on = True
        self._has_video = False
        self._volume = 1.0
        self._muted = False

    # ── loading ──
    def load(self, path: str, video: bool = True, start: float = 0.0, play: bool = True) -> None:
        self.stop()
        self.path, self.uri = path, file_uri(path)
        self.tags, self.duration, self.ended, self.error = Tags(), None, False, None
        self._has_video = False
        self._pending_seek = start if start > 1 else 0.0
        flags = FLAG_AUDIO | FLAG_SOFT_VOLUME
        if video:
            flags |= FLAG_VIDEO | (FLAG_TEXT if self.subtitles_on else 0)
        self.playbin.set_property('flags', flags)
        self.playbin.set_property('uri', self.uri)
        sub = subtitle_for(path) if video else None
        self.playbin.set_property('suburi', file_uri(sub) if sub else None)
        if sub:
            log.info("subtitles: %s", sub)
        self._apply_volume()
        if video and self.sink is not None and self.window_handle:
            GstVideo.VideoOverlay.set_window_handle(self.sink, self.window_handle)
        self.playing = play
        self.playbin.set_state(Gst.State.PLAYING if play else Gst.State.PAUSED)

    def stop(self) -> None:
        self.playbin.set_state(Gst.State.NULL)
        self.playing = False

    def close(self) -> None:
        self.stop()

    # ── transport ──
    def play(self) -> None:
        if self.ended:
            self.ended = False
            self.seek(0)
        self.playing = True
        self.playbin.set_state(Gst.State.PLAYING)

    def pause(self) -> None:
        self.playing = False
        self.playbin.set_state(Gst.State.PAUSED)

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def position(self) -> Optional[float]:
        ok, value = self.playbin.query_position(Gst.Format.TIME)
        return value / SECOND if ok and value >= 0 else None

    def _query_duration(self) -> Optional[float]:
        ok, value = self.playbin.query_duration(Gst.Format.TIME)
        return value / SECOND if ok and value > 0 else None

    def seek(self, seconds: float, accurate: bool = True) -> None:
        seconds = max(0.0, seconds)
        if self.duration:
            seconds = min(seconds, max(0.0, self.duration - 0.05))
        flags = Gst.SeekFlags.FLUSH | (Gst.SeekFlags.ACCURATE if accurate
                                       else Gst.SeekFlags.KEY_UNIT)
        self.ended = False
        self.playbin.seek_simple(Gst.Format.TIME, flags, int(seconds * SECOND))

    def step(self, delta: float) -> None:
        pos = self.position()
        if pos is not None:
            self.seek(pos + delta)

    # ── sound ──
    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))
        self._apply_volume()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = bool(value)
        self._apply_volume()

    def _apply_volume(self) -> None:
        # the slider is linear to the ear: cubic to amplitude
        self.playbin.set_property('volume', self._volume ** 3)
        self.playbin.set_property('mute', self._muted)

    # ── tracks ──
    def has_video(self) -> bool:
        return self._has_video

    def track_counts(self) -> Tuple[int, int]:
        """(audio tracks, subtitle tracks)."""
        return (self.playbin.get_property('n-audio'), self.playbin.get_property('n-text'))

    def next_audio_track(self) -> Optional[int]:
        count = self.playbin.get_property('n-audio')
        if count < 2:
            return None
        index = (self.playbin.get_property('current-audio') + 1) % count
        self.playbin.set_property('current-audio', index)
        return index

    def toggle_subtitles(self) -> bool:
        self.subtitles_on = not self.subtitles_on
        flags = int(self.playbin.get_property('flags'))
        flags = flags | FLAG_TEXT if self.subtitles_on else flags & ~FLAG_TEXT
        self.playbin.set_property('flags', flags)
        return self.subtitles_on

    # ── window ──
    def expose(self, width: int, height: int) -> None:
        if self.sink is None or not self.window_handle:
            return
        try:
            GstVideo.VideoOverlay.set_render_rectangle(self.sink, 0, 0, width, height)
            GstVideo.VideoOverlay.expose(self.sink)
        except Exception:      # noqa: BLE001 - not every sink supports both
            pass

    # ── bus ──
    def poll(self) -> None:
        while True:
            msg = self.bus.pop()
            if msg is None:
                break
            self._handle(msg)

    def _handle(self, msg) -> None:
        t = msg.type
        if t == Gst.MessageType.EOS:
            self.ended, self.playing = True, False
            self.playbin.set_state(Gst.State.PAUSED)
            self.on_event('eos', None)
        elif t == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            log.error("gstreamer: %s (%s)", err.message, debug)
            if self.error is None:
                self.error = friendly_error(err.message, debug)
            self.playing = False
            self.playbin.set_state(Gst.State.NULL)
            self.on_event('error', self.error)
        elif t == Gst.MessageType.ELEMENT and GstPbutils is not None and \
                GstPbutils.is_missing_plugin_message(msg):
            what = GstPbutils.missing_plugin_message_get_description(msg)
            log.warning("missing plugin: %s", what)
            self.error = f"No decoder for {what} is installed."
        elif t == Gst.MessageType.TAG:
            self._read_tags(msg.parse_tag())
        elif t == Gst.MessageType.ASYNC_DONE:
            self.duration = self._query_duration() or self.duration
            self._has_video = self.playbin.get_property('n-video') > 0
            if self._pending_seek:
                start, self._pending_seek = self._pending_seek, 0.0
                self.seek(start)
            self.on_event('ready', None)
        elif t == Gst.MessageType.DURATION_CHANGED:
            self.duration = self._query_duration() or self.duration
        elif t == Gst.MessageType.STREAM_START:
            self.on_event('started', None)

    def _read_tags(self, taglist) -> None:
        def text(name):
            ok, value = taglist.get_string(name)
            return value.strip() if ok and value and value.strip() else None

        tags = self.tags
        tags.title = tags.title or text('title')
        tags.artist = tags.artist or text('artist') or text('album-artist')
        tags.album = tags.album or text('album')
        tags.video_codec = tags.video_codec or text('video-codec')
        tags.audio_codec = tags.audio_codec or text('audio-codec')
        if tags.cover is None:
            for name in ('image', 'preview-image'):
                ok, sample = taglist.get_sample(name)
                if ok and sample is not None:
                    tags.cover = sample_to_image(sample)
                    if tags.cover is not None:
                        break
        self.on_event('tags', tags)


def sample_to_image(sample) -> Optional[Image.Image]:
    import io
    buf = sample.get_buffer()
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return None
    try:
        image = Image.open(io.BytesIO(bytes(info.data)))
        image.load()
        return image.convert('RGB')
    except Exception:      # noqa: BLE001
        return None
    finally:
        buf.unmap(info)


def friendly_error(message: str, debug: Optional[str]) -> str:
    low = f"{message} {debug or ''}".lower()
    if 'no decoder' in low or 'missing' in low and 'plugin' in low or 'codec' in low and 'not' in low:
        return "This file uses a format no installed decoder can play."
    if 'could not open resource' in low or 'not found' in low:
        return "The file could not be opened. It may have moved."
    if 'could not determine type' in low:
        return "This doesn't look like a video or audio file."
    if 'audio' in low and ('sink' in low or 'device' in low):
        return "No sound output is available."
    return message


def video_thumbnail(path: str, flavour: str = 'large', timeout: float = 8.0) -> Optional[Image.Image]:
    """A frame from 10% into the video, through playbin's convert-sample. Runs in a worker
    thread; cached in the freedesktop thumbnail folder like photos."""
    image = cached_thumbnail(path, flavour)
    if image is not None:
        return image
    if init() is not None:
        return None
    size = THUMB_SIZES[flavour]
    pb = Gst.ElementFactory.make('playbin', None)
    pb.set_property('uri', file_uri(path))
    pb.set_property('audio-sink', Gst.ElementFactory.make('fakesink', None))
    pb.set_property('video-sink', Gst.ElementFactory.make('fakesink', None))
    pb.set_property('flags', FLAG_VIDEO)
    bus = pb.get_bus()
    wait_ns = int(timeout * SECOND)
    try:
        pb.set_state(Gst.State.PAUSED)
        msg = bus.timed_pop_filtered(wait_ns, Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        if msg is None or msg.type == Gst.MessageType.ERROR:
            return None
        ok, duration = pb.query_duration(Gst.Format.TIME)
        if ok and duration > 0:
            pb.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                           int(duration * 0.1))
            bus.timed_pop_filtered(wait_ns, Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        caps = Gst.Caps.from_string(f'video/x-raw,format=RGB,width={size},'
                                    'pixel-aspect-ratio=1/1')
        sample = pb.emit('convert-sample', caps)
        if sample is None:
            return None
        structure = sample.get_caps().get_structure(0)
        width, height = structure.get_value('width'), structure.get_value('height')
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            stride = len(info.data) // height
            image = Image.frombuffer('RGB', (width, height), bytes(info.data), 'raw', 'RGB',
                                     stride, 1).copy()
        finally:
            buf.unmap(info)
        image.thumbnail((size, size))
        store_thumbnail(path, image, flavour)
        return image
    except Exception as exc:      # noqa: BLE001
        log.debug("no video thumbnail for %s: %s", path, exc)
        return None
    finally:
        pb.set_state(Gst.State.NULL)
