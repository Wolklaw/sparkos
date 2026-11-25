"""Working on video files with GStreamer in this process: join the buffer's pieces into an MP4
without re-encoding, read a clip's length and tracks, cut a clip at keyframes (also without
re-encoding), and grab a picture for the library."""

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .core import log

GST_ERROR: Optional[str] = None
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    try:
        gi.require_version('GstPbutils', '1.0')
        from gi.repository import GstPbutils
    except (ImportError, ValueError):
        GstPbutils = None
except (ImportError, ValueError) as _exc:          # no python3-gobject or no GStreamer typelib
    GST_ERROR = str(_exc)
    Gst = None
    GstPbutils = None

SECOND = 1_000_000_000
_lock = threading.Lock()
_ready = False


class ClipError(Exception):
    pass


def init() -> Optional[str]:
    """Start GStreamer once. None when it works, else why not."""
    global _ready
    if GST_ERROR:
        return GST_ERROR
    with _lock:
        if not _ready:
            try:
                Gst.init(None)
            except Exception as exc:               # noqa: BLE001
                return str(exc)
            _ready = True
    return None


def _make(factory: str, **props):
    element = Gst.ElementFactory.make(factory)
    if element is None:
        raise ClipError(f"GStreamer has no {factory}")
    for key, value in props.items():
        element.set_property(key.replace('_', '-'), value)
    return element


PARSERS = {'video/x-h264': 'h264parse', 'video/x-h265': 'h265parse', 'audio/mpeg': 'aacparse',
           'audio/x-opus': 'opusparse', 'audio/x-ac3': 'ac3parse'}


class _Remux:
    """filesrc ! demuxer ! parser ! mp4mux ! filesink. The streams are linked as the demuxer
    announces them."""

    def __init__(self, src: str, dst: str, demuxer: str):
        self.pipeline = Gst.Pipeline.new('remux')
        self.mux = _make('mp4mux', faststart=True)
        sink = _make('filesink', location=dst)
        source = _make('filesrc', location=src)
        self.demux = _make(demuxer)
        for e in (source, self.demux, self.mux, sink):
            self.pipeline.add(e)
        source.link(self.demux)
        self.mux.link(sink)
        self.demux.connect('pad-added', self._pad_added)
        self.tracks = 0
        self.bus = self.pipeline.get_bus()

    def _pad_added(self, _demux, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        name = caps.get_structure(0).get_name()
        parser_name = PARSERS.get(name)
        if parser_name is None:
            log.info("remux: leaving out a %s stream", name)
            return
        parser = _make(parser_name)
        # unbounded: a demuxer that reads the whole video before the audio would otherwise
        # stall against the muxer, which waits for both
        queue = _make('queue', max_size_buffers=0, max_size_bytes=0, max_size_time=0)
        self.pipeline.add(queue)
        self.pipeline.add(parser)
        queue.sync_state_with_parent()
        parser.sync_state_with_parent()
        pad.link(queue.get_static_pad('sink'))
        queue.link(parser)
        template = 'video_%u' if name.startswith('video') else 'audio_%u'
        target = self.mux.request_pad_simple(template)
        parser.get_static_pad('src').link(target)
        self.tracks += 1

    def run(self, timeout: float, seek: Optional[Tuple[int, int]] = None) -> None:
        pipe = self.pipeline
        if pipe.set_state(Gst.State.PAUSED) == Gst.StateChangeReturn.FAILURE:
            pipe.set_state(Gst.State.NULL)
            raise ClipError("the pipeline would not start")
        try:
            if seek is not None:
                # wait until every stream is announced and prerolled, then cut
                msg = self.bus.timed_pop_filtered(int(timeout * SECOND),
                                                  Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
                if msg is None or msg.type == Gst.MessageType.ERROR:
                    raise ClipError(self._why(msg))
                start, stop = seek
                ok = self.demux.seek(1.0, Gst.Format.TIME,
                               Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                               Gst.SeekType.SET, start, Gst.SeekType.SET, stop)
                if not ok:
                    raise ClipError("the file could not be cut there")
            pipe.set_state(Gst.State.PLAYING)
            msg = self.bus.timed_pop_filtered(int(timeout * SECOND),
                                              Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if msg is None:
                raise ClipError("timed out")
            if msg.type == Gst.MessageType.ERROR:
                raise ClipError(self._why(msg))
            if not self.tracks:
                raise ClipError("no video found")
        finally:
            pipe.set_state(Gst.State.NULL)

    @staticmethod
    def _why(msg) -> str:
        if msg is None:
            return "timed out"
        err, debug = msg.parse_error()
        return f"{err.message}"


def _run_remux(src: str, dst: str, demuxer: str, timeout: float,
               seek: Optional[Tuple[int, int]] = None) -> None:
    problem = init()
    if problem:
        raise ClipError(problem)
    tmp = dst + '.part'
    try:
        _Remux(src, tmp, demuxer).run(timeout, seek)
        if not os.path.isfile(tmp) or os.path.getsize(tmp) < 1000:
            raise ClipError("the file came out empty")
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _renumber(data: bytearray, last: Dict[int, int]) -> None:
    """Every piece comes from its own muxer, so its 4-bit continuity counters start over.
    GStreamer's tsdemux takes that for lost packets and drops frames (the keyframes with
    them). Shift each piece's counters so they carry on from the piece before."""
    delta: Dict[int, int] = {}
    for i in range(0, len(data) - 187, 188):
        if data[i] != 0x47:
            continue
        pid = ((data[i + 1] & 0x1F) << 8) | data[i + 2]
        if pid == 0x1FFF:
            continue
        flags = data[i + 3]
        cc = flags & 0x0F
        payload = bool(flags & 0x10)
        if pid not in delta:
            if pid in last:
                delta[pid] = (last[pid] + (1 if payload else 0) - cc) & 0x0F
            else:
                delta[pid] = 0
        shift = delta[pid]
        if shift:
            cc = (cc + shift) & 0x0F
            data[i + 3] = (flags & 0xF0) | cc
        last[pid] = cc


def join_pieces(paths: List[str], joined: str) -> int:
    """MPEG-TS pieces joined into one stream (counters renumbered). Returns the bytes."""
    total = 0
    last: Dict[int, int] = {}
    with open(joined, 'wb') as out:
        for path in paths:
            try:
                with open(path, 'rb') as f:
                    data = bytearray(f.read())
            except OSError as exc:
                log.warning("piece %s lost while saving: %s", path, exc)
                continue
            _renumber(data, last)
            out.write(data)
            total += len(data)
    return total


def save_clip(paths: List[str], dst: str, scratch: str, timeout: float = 120.0) -> None:
    """Pieces in, MP4 out, no re-encoding. `scratch` is a folder for the joined stream."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    joined = os.path.join(scratch, f'join-{os.getpid()}-{int(time.time() * 1000)}.ts')
    try:
        if join_pieces(paths, joined) < 1000:
            raise ClipError("the buffer is empty")
        _run_remux(joined, dst, 'tsdemux', timeout)
    finally:
        try:
            os.remove(joined)
        except OSError:
            pass


def trim_clip(src: str, dst: str, start: float, end: float, timeout: float = 120.0) -> None:
    """A copy of src from start to end (seconds), cut at the keyframe at or before start:
    nothing is re-encoded, so it is exact to about a second."""
    if end <= start:
        raise ClipError("the end is before the start")
    _run_remux(src, dst, 'qtdemux', timeout, (int(start * SECOND), int(end * SECOND)))


# ─── Reading a clip ───

_info: Dict[Tuple[str, float, int], Dict[str, Any]] = {}


def probe(path: str) -> Dict[str, Any]:
    """{'duration': s, 'video': bool, 'audio': tracks, 'size': (w, h), 'codec': text}.
    Empty values when the file can't be read."""
    blank: Dict[str, Any] = {'duration': 0.0, 'video': False, 'audio': 0, 'size': (0, 0), 'codec': ''}
    if init() or GstPbutils is None:
        return blank
    try:
        st = os.stat(path)
    except OSError:
        return blank
    key = (path, st.st_mtime, st.st_size)
    if key not in _info:
        out = dict(blank)
        try:
            info = GstPbutils.Discoverer.new(5 * SECOND).discover_uri(Gst.filename_to_uri(path))
            out['duration'] = max(0, info.get_duration()) / SECOND
            videos = info.get_video_streams()
            out['video'] = bool(videos)
            out['audio'] = len(info.get_audio_streams())
            if videos:
                out['size'] = (videos[0].get_width(), videos[0].get_height())
                caps = videos[0].get_caps()
                out['codec'] = caps.get_structure(0).get_name().replace('video/x-', '') if caps else ''
        except Exception:                          # noqa: BLE001 - unreadable file
            pass
        _info[key] = out
    return _info[key]


def thumbnail(path: str, dst: str, width: int = 320, at: Optional[float] = None,
              timeout: float = 15.0) -> bool:
    """A JPEG of one frame (a third of the way in, or `at` seconds) as wide as `width`."""
    if init():
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    pipe = None
    try:
        pipe = Gst.parse_launch(
            f'filesrc location="{path}" ! decodebin name=d ! queue ! videoconvert ! videoscale '
            f'! video/x-raw,format=RGB,width={width},pixel-aspect-ratio=1/1 ! appsink name=out sync=false '
            'max-buffers=1 drop=true')
        sink = pipe.get_by_name('out')
        pipe.set_state(Gst.State.PAUSED)
        msg = pipe.get_bus().timed_pop_filtered(int(timeout * SECOND),
                                                Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        if msg is None or msg.type == Gst.MessageType.ERROR:
            return False
        ok, length = pipe.query_duration(Gst.Format.TIME)
        when = int((at if at is not None else (length / SECOND / 3 if ok else 0)) * SECOND)
        if when > 0:
            pipe.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, when)
            pipe.get_bus().timed_pop_filtered(int(timeout * SECOND),
                                              Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        sample = sink.emit('try-pull-preroll', timeout * SECOND)
        if sample is None:
            return False
        s = sample.get_caps().get_structure(0)
        w, h = s.get_value('width'), s.get_value('height')
        found, mapped = sample.get_buffer().map(Gst.MapFlags.READ)
        if not found:
            return False
        try:
            stride = (w * 3 + 3) // 4 * 4
            image = Image.frombuffer('RGB', (w, h), bytes(mapped.data), 'raw', 'RGB', stride, 1)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            image.save(dst + '.tmp', 'JPEG', quality=82)
            os.replace(dst + '.tmp', dst)
        finally:
            sample.get_buffer().unmap(mapped)
        return True
    except Exception as exc:                       # noqa: BLE001
        log.info("no thumbnail for %s: %s", path, exc)
        return False
    finally:
        if pipe is not None:
            pipe.set_state(Gst.State.NULL)
