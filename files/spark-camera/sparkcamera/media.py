"""Everything GStreamer: finding cameras and microphones, the live preview, photos, video
recording with sound, the voice recorder with its level meter, and playing a recording back.

No GLib main loop. Tk's timer polls each session (poll()), the way Spark Media does; GStreamer's
own threads only fill a latest-frame slot or run a pad probe.

SPARK_CAMERA_FAKE=1 swaps the camera and microphone for videotestsrc and audiotestsrc, so the
tests (and CI, which has no camera) run the same pipelines.
"""

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core import log

Gst = GstApp = GstPbutils = None
GST_ERROR: Optional[str] = None
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstApp', '1.0')
    from gi.repository import Gst, GstApp          # type: ignore  # noqa: F811
    try:
        gi.require_version('GstPbutils', '1.0')
        from gi.repository import GstPbutils       # type: ignore  # noqa: F811
    except (ImportError, ValueError):
        GstPbutils = None
except (ImportError, ValueError) as exc:
    GST_ERROR = str(exc)

SECOND = 1_000_000_000
PREVIEW_WIDTH = 800
_init_lock = threading.Lock()
_ready = False


def init() -> Optional[str]:
    """Start GStreamer once. Returns None when it works, else why not."""
    global _ready
    if GST_ERROR:
        return GST_ERROR
    with _init_lock:
        if not _ready:
            try:
                Gst.init(None)
            except Exception as exc:               # noqa: BLE001 - whatever GStreamer says
                return str(exc)
            _ready = True
    return None


def available() -> bool:
    return init() is None


def fake() -> bool:
    return os.environ.get('SPARK_CAMERA_FAKE', '').lower() in ('1', 'true', 'yes')


def have(factory: str) -> bool:
    return available() and Gst.ElementFactory.find(factory) is not None


def make(factory: str, name: Optional[str] = None, **props):
    el = Gst.ElementFactory.make(factory, name)
    if el is None:
        raise RuntimeError(f"GStreamer element {factory} is missing")
    for key, value in props.items():
        el.set_property(key.replace('_', '-'), value)
    return el


# ─── Devices ───

@dataclass
class Mode:
    width: int
    height: int
    fps: float
    kind: str                       # 'raw' or 'jpeg'

    @property
    def key(self) -> str:
        return f"{self.width}x{self.height}"

    def caps(self) -> str:
        fps = max(1, int(round(self.fps)))
        base = 'image/jpeg' if self.kind == 'jpeg' else 'video/x-raw'
        return f"{base},width={self.width},height={self.height},framerate={fps}/1"

    def label(self) -> str:
        return f"{self.width}x{self.height}  {int(round(self.fps))} FPS"


@dataclass
class Source:
    id: str
    name: str
    kind: str                       # 'video' or 'audio'
    device: Any = None
    modes: List[Mode] = field(default_factory=list)
    fake: bool = False

    def element(self, name: Optional[str] = None):
        if self.fake:
            if self.kind == 'video':
                return make('videotestsrc', name, is_live=True, pattern='smpte')
            return make('audiotestsrc', name, is_live=True, wave='sine', freq=440.0, volume=0.3)
        el = self.device.create_element(name)
        if el is None:
            raise RuntimeError(f"couldn't open {self.name}")
        return el


_FRACTION = re.compile(r'(\d+)/(\d+)')


def modes_from_caps(caps) -> List[Mode]:
    """One Mode per picture size: the fastest way the camera offers it (raw wins a tie).
    Camera caps list every size and speed, as lists or ranges; this reads them as text."""
    best: Dict[Tuple[int, int], Mode] = {}
    for i in range(caps.get_size()):
        s = caps.get_structure(i)
        name = s.get_name()
        if name not in ('video/x-raw', 'image/jpeg'):
            continue
        ok_w, w = s.get_int('width')
        ok_h, h = s.get_int('height')
        if not (ok_w and ok_h) or w < 160 or h < 120:
            continue
        text = s.to_string()
        m = re.search(r'framerate=\(fraction\)(\{[^}]*\}|\[[^\]]*\]|[0-9/]+)', text)
        rates = [int(a) / max(1, int(b)) for a, b in _FRACTION.findall(m.group(1))] if m else []
        rates = [r for r in rates if 1 <= r <= 240]
        if not rates:
            continue
        mode = Mode(w, h, max(rates), 'jpeg' if name == 'image/jpeg' else 'raw')
        old = best.get((w, h))
        if old is None or mode.fps > old.fps + 0.5 or (abs(mode.fps - old.fps) <= 0.5
                                                       and mode.kind == 'raw'):
            best[(w, h)] = mode
    return sorted(best.values(), key=lambda m: (-m.width, -m.height))


def _device_id(device, kind: str) -> str:
    props = device.get_properties()
    if props is not None:
        for key in ('api.v4l2.path', 'device.path', 'node.name', 'object.path'):
            value = props.get_string(key)
            if value:
                return value
    return device.get_display_name()


def _scan(klass: str, kind: str) -> List[Source]:
    out: List[Source] = []
    monitor = Gst.DeviceMonitor.new()
    monitor.add_filter(klass, None)
    if not monitor.start():
        return out
    try:
        seen = set()
        for device in monitor.get_devices():
            dev_id = _device_id(device, kind)
            if dev_id in seen:
                continue
            seen.add(dev_id)
            name = re.sub(r'\s*\(V4L2\)$', '', device.get_display_name())
            src = Source(dev_id, name, kind, device)
            if kind == 'video':
                caps = device.get_caps()
                src.modes = modes_from_caps(caps) if caps is not None else []
                if not src.modes:
                    continue                # a metadata node (/dev/video1 on many webcams)
            out.append(src)
    finally:
        monitor.stop()
    return out


def fake_camera() -> Source:
    return Source('fake-camera', "Test pattern camera", 'video', None, [
        Mode(1280, 720, 30, 'raw'), Mode(640, 480, 30, 'raw'), Mode(320, 240, 15, 'raw')],
        fake=True)


def fake_mic() -> Source:
    return Source('fake-mic', "Test tone", 'audio', None, [], fake=True)


def list_cameras() -> List[Source]:
    if init():
        return []
    if fake():
        return [fake_camera()]
    return _scan('Video/Source', 'video')


def list_mics() -> List[Source]:
    if init():
        return []
    if fake():
        return [fake_mic()]
    # the monitor of an output ("Monitor of ...") is what the PC plays, not a microphone
    return [s for s in _scan('Audio/Source', 'audio') if '.monitor' not in s.id.lower()
            and not s.name.lower().startswith('monitor of')]


def pick_mode(modes: List[Mode], wanted: str) -> Optional[Mode]:
    """The saved size if the camera still has it; else the biggest size at 24 FPS or better up
    to 1280 wide (a light default); else the first one."""
    for m in modes:
        if m.key == wanted:
            return m
    for m in modes:
        if m.width <= 1280 and m.fps >= 24:
            return m
    return modes[0] if modes else None


# ─── Formats ───

@dataclass
class VideoFormat:
    key: str
    label: str
    ext: str
    video: str                      # the video encoder and parser, as a launch string
    audio: str                      # the audio encoder
    mux: str


def video_formats() -> List[VideoFormat]:
    """The video formats this PC can write, best first. Checked against the installed
    GStreamer, not assumed."""
    if init():
        return []
    out = []
    if have('vp9enc') and have('opusenc') and have('webmmux'):
        out.append(VideoFormat(
            'webm-vp9', "WebM VP9", '.webm',
            "vp9enc deadline=1 cpu-used=5 row-mt=true threads=4 target-bitrate=5000000 "
            "keyframe-max-dist=60", "opusenc bitrate=128000", "webmmux"))
    aac = 'avenc_aac bitrate=160000' if have('avenc_aac') else (
        'fdkaacenc bitrate=160000' if have('fdkaacenc') else '')
    h264 = ''
    if have('vah264enc'):
        h264 = 'vah264enc bitrate=6000 key-int-max=60 ! h264parse'
    elif have('openh264enc'):
        h264 = 'openh264enc bitrate=6000000 complexity=0 ! h264parse'
    if h264 and aac and have('h264parse') and have('mp4mux'):
        out.append(VideoFormat('mp4-h264', "MP4 H.264", '.mp4', h264, aac, "mp4mux"))
    if have('vp8enc') and have('opusenc') and have('webmmux'):
        out.append(VideoFormat(
            'webm-vp8', "WebM VP8", '.webm',
            "vp8enc deadline=1 cpu-used=5 threads=4 target-bitrate=5000000 keyframe-max-dist=60",
            "opusenc bitrate=128000", "webmmux"))
    return out


@dataclass
class VoiceFormat:
    key: str
    label: str
    ext: str
    chain: str


def voice_formats() -> List[VoiceFormat]:
    if init():
        return []
    out = []
    if have('opusenc') and have('oggmux'):
        out.append(VoiceFormat('opus', "OPUS", '.opus', "opusenc bitrate=96000 ! oggmux"))
    if have('flacenc'):
        out.append(VoiceFormat('flac', "FLAC", '.flac', "flacenc"))
    return out


def pick_by_key(items: list, key: str):
    for item in items:
        if item.key == key:
            return item
    return items[0] if items else None


# ─── Frames ───

def rgb_to_image(w: int, h: int, data: bytes):
    from PIL import Image
    stride = (w * 3 + 3) & ~3
    return Image.frombuffer('RGB', (w, h), data, 'raw', 'RGB', stride, 1)


def sample_to_frame(sample) -> Optional[Tuple[int, int, bytes]]:
    caps = sample.get_caps()
    s = caps.get_structure(0)
    ok_w, w = s.get_int('width')
    ok_h, h = s.get_int('height')
    buf = sample.get_buffer()
    if not (ok_w and ok_h) or buf is None:
        return None
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return None
    try:
        return w, h, bytes(info.data)
    finally:
        buf.unmap(info)


def _poll_bus(pipeline, mask) -> list:
    bus = pipeline.get_bus()
    out = []
    while True:
        msg = bus.pop_filtered(mask)
        if msg is None:
            return out
        out.append(msg)


def plain_error(msg) -> str:
    """A GStreamer error as one plain sentence."""
    err, debug = msg.parse_error()
    text = err.message or "unknown error"
    low = (text + ' ' + (debug or '')).lower()
    if 'busy' in low or 'resource busy' in low:
        return "the device is busy, another program is using it"
    if 'permission' in low or 'denied' in low:
        return "no permission to open the device"
    if 'no such' in low or 'not found' in low or 'disconnect' in low:
        return "the device is gone"
    return text


# ─── Camera: preview, photos, recording ───

MIN_CLIP = 0.3                      # seconds a recording runs before a stop is let through


@dataclass
class _Recording:
    bin: Any
    sink_pad: Any
    tee_pad: Any
    mic: Any
    path: str
    started: float
    done: Any = None                # set when the file's sink has seen end-of-stream
    stopping: bool = False
    stop_at: float = 0.0


class CameraSession:
    """One camera open: a live preview, the newest full-size frame for photos, and at most one
    recording at a time that can start and stop without closing the camera."""

    def __init__(self, camera: Source, mode: Mode):
        self.camera, self.mode = camera, mode
        self.pipeline = None
        self._lock = threading.Lock()
        self._preview: Optional[Tuple[int, int, bytes]] = None
        self._preview_n = 0
        self._shown_n = 0
        self._photo = None
        self.rec: Optional[_Recording] = None
        self.running = False
        self.first_frame = threading.Event()

    # -- life --

    def start(self) -> None:
        err = init()
        if err:
            raise RuntimeError(err)
        src = self.camera.element('src')
        if self.camera.fake:
            front = (f"capsfilter name=srccaps caps=video/x-raw,width={self.mode.width},"
                     f"height={self.mode.height},framerate={int(self.mode.fps)}/1")
        else:
            front = f"capsfilter name=srccaps caps={self.mode.caps()}"
        tail = (
            " ! queue max-size-buffers=3 leaky=downstream ! decodebin name=dec ! videoconvert "
            "! tee name=t "
            "t. ! queue max-size-buffers=2 leaky=downstream ! videoscale ! videoconvert "
            f"! video/x-raw,format=RGB,width={PREVIEW_WIDTH},pixel-aspect-ratio=1/1 "
            "! appsink name=preview emit-signals=true max-buffers=1 drop=true sync=false "
            "t. ! queue max-size-buffers=1 leaky=downstream ! videorate drop-only=true "
            "! video/x-raw,framerate=5/1 ! videoconvert ! video/x-raw,format=RGB "
            "! appsink name=photo emit-signals=true max-buffers=1 drop=true sync=false")
        pipe = Gst.parse_launch(front + tail)
        pipe.add(src)
        if not src.link(pipe.get_by_name('srccaps')):
            raise RuntimeError("couldn't link the camera to the pipeline")
        self.tee = pipe.get_by_name('t')
        pipe.get_by_name('preview').connect('new-sample', self._on_preview)
        pipe.get_by_name('photo').connect('new-sample', self._on_photo)
        self.pipeline = pipe
        if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._drain_errors()
            raise RuntimeError(self._last_error or "the camera didn't start")
        self.running = True
        log.info("camera %s started at %s (%s)", self.camera.name, self.mode.key, self.mode.kind)

    _last_error = ''

    def _drain_errors(self) -> None:
        for msg in _poll_bus(self.pipeline, Gst.MessageType.ERROR):
            self._last_error = plain_error(msg)

    def stop(self) -> None:
        if self.pipeline is None:
            return
        if self.rec is not None:
            self._teardown_recording(forced=True)
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = None
        self.running = False
        log.info("camera %s stopped", self.camera.name)

    # -- frames --

    def _on_preview(self, sink):
        sample = sink.emit('pull-sample')
        frame = sample_to_frame(sample) if sample is not None else None
        if frame is not None:
            with self._lock:
                self._preview = frame
                self._preview_n += 1
            self.first_frame.set()
        return Gst.FlowReturn.OK

    def _on_photo(self, sink):
        sample = sink.emit('pull-sample')
        if sample is not None:
            with self._lock:
                self._photo = sample
        return Gst.FlowReturn.OK

    def new_preview(self) -> Optional[Tuple[int, int, bytes]]:
        """The preview frame if it is newer than the last one handed out, else None."""
        with self._lock:
            if self._preview is None or self._preview_n == self._shown_n:
                return None
            self._shown_n = self._preview_n
            return self._preview

    def last_preview(self) -> Optional[Tuple[int, int, bytes]]:
        with self._lock:
            return self._preview

    def photo_frame(self) -> Optional[Tuple[int, int, bytes]]:
        """The newest full-size frame (up to a fifth of a second old), else the preview."""
        with self._lock:
            sample = self._photo
            preview = self._preview
        frame = sample_to_frame(sample) if sample is not None else None
        return frame or preview

    # -- recording --

    def recording(self) -> bool:
        return self.rec is not None

    def record_seconds(self) -> float:
        return time.monotonic() - self.rec.started if self.rec else 0.0

    def start_recording(self, path: str, fmt: VideoFormat, mic: Optional[Source]) -> None:
        if self.rec is not None or self.pipeline is None:
            raise RuntimeError("already recording")
        desc = (f"queue name=vin max-size-time=3000000000 max-size-buffers=0 max-size-bytes=0 "
                f"! videoconvert ! {fmt.video} ! queue ! mux. ")
        if mic is not None:
            desc += (f"queue name=ain max-size-time=3000000000 max-size-buffers=0 "
                     f"max-size-bytes=0 ! audioconvert ! audioresample ! {fmt.audio} "
                     f"! queue ! mux. ")
        desc += f"{fmt.mux} name=mux ! filesink name=out async=false location=\"{path}\""
        rec_bin = Gst.parse_bin_from_description(desc, False)
        rec_bin.set_property('name', 'rec')
        vin = rec_bin.get_by_name('vin')
        ghost = Gst.GhostPad.new('sink', vin.get_static_pad('sink'))
        rec_bin.add_pad(ghost)
        mic_el = None
        if mic is not None:
            mic_el = mic.element('mic')
            rec_bin.add(mic_el)
            if not mic_el.link(rec_bin.get_by_name('ain')):
                raise RuntimeError("couldn't link the microphone")
        # the first picture a camera hands over after the recorder is linked can be an old one
        # (the C920 sends one, then pauses for about a second), and the VP9 encoder sometimes
        # refuses the frame that follows it ("invalid parameter"), so the recording starts at
        # the second picture
        skip = [1]

        def first_frame(_pad, info):
            if skip[0] > 0:
                skip[0] -= 1
                return Gst.PadProbeReturn.DROP
            return Gst.PadProbeReturn.OK

        ghost.add_probe(Gst.PadProbeType.BUFFER, first_frame)
        done = threading.Event()
        out_pad = rec_bin.get_by_name('out').get_static_pad('sink')

        def watch(_pad, info):
            ev = info.get_event()
            if ev is not None and ev.type == Gst.EventType.EOS:
                done.set()
            return Gst.PadProbeReturn.OK

        out_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, watch)
        self.pipeline.add(rec_bin)
        # open the microphone and the encoders first (the microphone can take a second), so the
        # first frame doesn't wait for them and the sound and the picture start together
        rec_bin.set_state(Gst.State.PAUSED)
        rec_bin.get_state(5 * Gst.SECOND)
        tee_pad = self.tee.request_pad_simple('src_%u')
        # the file starts at 0, not at however long the preview has been running: the video and
        # the sound are shifted back by the pipeline's running time now (the recorder is already
        # open and warm, so its first frames follow at once)
        clock = self.pipeline.get_clock()
        if clock is not None:
            offset = -(clock.get_time() - self.pipeline.get_base_time())
            tee_pad.set_offset(offset)
            if mic_el is not None:
                mic_el.get_static_pad('src').set_offset(offset)
        if tee_pad.link(ghost) != Gst.PadLinkReturn.OK:
            self.pipeline.remove(rec_bin)
            raise RuntimeError("couldn't link the recorder")
        rec_bin.sync_state_with_parent()
        self.rec = _Recording(rec_bin, ghost, tee_pad, mic_el, path, time.monotonic(), done)
        log.info("recording to %s (%s%s)", path, fmt.key, ", with sound" if mic else "")

    def stop_recording(self) -> None:
        """Ask the recording to finish. poll() reports 'recorded' once the file is closed."""
        rec = self.rec
        if rec is None or rec.stopping:
            return
        rec.stopping = True
        rec.stop_at = time.monotonic()

        def probe(pad, _info):
            pad.unlink(rec.sink_pad)
            rec.sink_pad.send_event(Gst.Event.new_eos())
            if rec.mic is not None:
                rec.mic.send_event(Gst.Event.new_eos())
            return Gst.PadProbeReturn.REMOVE

        # a stop that comes before the first frame has gone in would leave the muxer waiting
        # for data that never arrives, so give it a moment (a double click on the button)
        wait = MIN_CLIP - (time.monotonic() - rec.started)
        if wait > 0:
            threading.Timer(wait, rec.tee_pad.add_probe,
                            (Gst.PadProbeType.BLOCK_DOWNSTREAM, probe)).start()
        else:
            rec.tee_pad.add_probe(Gst.PadProbeType.BLOCK_DOWNSTREAM, probe)

    def _teardown_recording(self, forced: bool = False) -> Tuple[str, float]:
        rec = self.rec
        self.rec = None
        seconds = time.monotonic() - rec.started
        try:
            self.tee.release_request_pad(rec.tee_pad)
        except Exception:                          # noqa: BLE001
            pass
        rec.bin.set_state(Gst.State.NULL)
        try:
            self.pipeline.remove(rec.bin)
        except Exception:                          # noqa: BLE001
            pass
        return rec.path, seconds

    def poll(self) -> List[Tuple[str, Any]]:
        """Messages for the window: ('error', text), ('recorded', (path, seconds))."""
        events: List[Tuple[str, Any]] = []
        if self.pipeline is None:
            return events
        for msg in _poll_bus(self.pipeline, Gst.MessageType.ERROR | Gst.MessageType.EOS):
            if msg.type == Gst.MessageType.ERROR:
                text = plain_error(msg)
                log.warning("camera pipeline error from %s: %s", msg.src.get_name(), text)
                if self.rec is not None and msg.src.has_ancestor(self.rec.bin):
                    path, seconds = self._teardown_recording(forced=True)
                    events.append(('error', f"the recording stopped: {text}"))
                    events.append(('recorded', (path, seconds)))
                else:
                    events.append(('error', text))
        rec = self.rec
        if rec is not None and rec.stopping and rec.done.is_set():
            events.append(('recorded', self._teardown_recording()))
        elif rec is not None and rec.stopping and time.monotonic() - rec.stop_at > 5.0:
            log.warning("recording didn't finish in 5 s, closing it")
            events.append(('recorded', self._teardown_recording(forced=True)))
        return events


# ─── Voice recorder ───

class VoiceSession:
    """The microphone with a level meter; with a path, also recorded to a file."""

    def __init__(self, mic: Source, fmt: Optional[VoiceFormat] = None, path: str = ''):
        self.mic, self.fmt, self.path = mic, fmt, path
        self.pipeline = None
        self.rms = [-90.0]
        self.peak = [-90.0]
        self.paused = False
        self._ran = 0.0                 # seconds recorded before the last pause
        self._since = 0.0
        self.finished = False
        self.stopping = False
        self._stop_at = 0.0

    def start(self) -> None:
        err = init()
        if err:
            raise RuntimeError(err)
        src = self.mic.element('src')
        if self.fmt is None:
            desc = ("audioconvert name=ain ! audioresample ! level name=lvl interval=50000000 "
                    "post-messages=true ! fakesink sync=false")
        else:
            desc = ("audioconvert name=ain ! audioresample ! level name=lvl interval=50000000 "
                    f"post-messages=true ! queue ! audioconvert ! audioresample ! "
                    f"{self.fmt.chain} ! filesink location=\"{self.path}\"")
        pipe = Gst.parse_launch(desc)
        pipe.add(src)
        if not src.link(pipe.get_by_name('ain')):
            raise RuntimeError("couldn't link the microphone")
        self.pipeline = pipe
        if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop_now()
            raise RuntimeError("the microphone didn't start")
        self._since = time.monotonic()
        log.info("voice %s on %s", "recording" if self.fmt else "monitor", self.mic.name)

    def seconds(self) -> float:
        if self.paused or self.pipeline is None:
            return self._ran
        return self._ran + time.monotonic() - self._since

    def pause(self) -> None:
        if self.pipeline is None or self.paused:
            return
        self._ran = self.seconds()
        self.paused = True
        self.pipeline.set_state(Gst.State.PAUSED)
        self.rms = self.peak = [-90.0]

    def resume(self) -> None:
        if self.pipeline is None or not self.paused:
            return
        self.paused = False
        self._since = time.monotonic()
        self.pipeline.set_state(Gst.State.PLAYING)

    def finish(self) -> None:
        """End the file properly: send EOS and wait for it in poll()."""
        if self.pipeline is None or self.stopping:
            return
        if self.paused:
            self._ran = self.seconds()
            self.paused = False
            self.pipeline.set_state(Gst.State.PLAYING)
        else:
            self._ran = self.seconds()
        self._since = time.monotonic()
        self.stopping = True
        self._stop_at = time.monotonic()
        self.pipeline.send_event(Gst.Event.new_eos())

    def stop_now(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self.finished = True

    def poll(self) -> List[Tuple[str, Any]]:
        events: List[Tuple[str, Any]] = []
        if self.pipeline is None:
            return events
        mask = Gst.MessageType.ERROR | Gst.MessageType.EOS | Gst.MessageType.ELEMENT
        for msg in _poll_bus(self.pipeline, mask):
            if msg.type == Gst.MessageType.ELEMENT:
                s = msg.get_structure()
                if s is not None and s.get_name() == 'level':
                    try:
                        self.rms = list(s.get_value('rms'))
                        self.peak = list(s.get_value('peak'))
                    except (TypeError, ValueError):
                        pass
            elif msg.type == Gst.MessageType.ERROR:
                text = plain_error(msg)
                log.warning("voice pipeline error: %s", text)
                events.append(('error', text))
            elif msg.type == Gst.MessageType.EOS:
                self.stop_now()
                events.append(('finished', (self.path, self._ran)))
        if self.stopping and not self.finished and time.monotonic() - self._stop_at > 5.0:
            log.warning("voice recording didn't finish in 5 s, closing it")
            self.stop_now()
            events.append(('finished', (self.path, self._ran)))
        return events


# ─── Playing a recording ───

class Playback:
    """Audio playback of one file through playbin."""

    def __init__(self):
        self.player = None
        self.uri = ''
        self.playing = False

    def play(self, path: str) -> None:
        err = init()
        if err:
            raise RuntimeError(err)
        self.stop()
        player = Gst.ElementFactory.make('playbin', 'player')
        if player is None:
            raise RuntimeError("GStreamer's playbin is missing")
        player.set_property('uri', Gst.filename_to_uri(path))
        player.set_property('video-sink', Gst.ElementFactory.make('fakesink', None))
        self.player, self.uri = player, path
        player.set_state(Gst.State.PLAYING)
        self.playing = True

    def toggle(self) -> None:
        if self.player is None:
            return
        self.playing = not self.playing
        self.player.set_state(Gst.State.PLAYING if self.playing else Gst.State.PAUSED)

    def stop(self) -> None:
        if self.player is not None:
            self.player.set_state(Gst.State.NULL)
        self.player, self.playing, self.uri = None, False, ''

    def position(self) -> Tuple[float, float]:
        if self.player is None:
            return 0.0, 0.0
        ok_p, pos = self.player.query_position(Gst.Format.TIME)
        ok_d, dur = self.player.query_duration(Gst.Format.TIME)
        return (pos / SECOND if ok_p else 0.0), (dur / SECOND if ok_d else 0.0)

    def poll(self) -> Optional[str]:
        """'ended' when it reached the end, 'error' if it failed."""
        if self.player is None:
            return None
        for msg in _poll_bus(self.player, Gst.MessageType.ERROR | Gst.MessageType.EOS):
            log.info("playback %s", 'error' if msg.type == Gst.MessageType.ERROR else 'ended')
            self.stop()
            return 'error' if msg.type == Gst.MessageType.ERROR else 'ended'
        return None


_durations: Dict[Tuple[str, float, int], float] = {}


def file_duration(path: str) -> float:
    """Length of an audio or video file in seconds, 0 when it can't be read."""
    if init() or GstPbutils is None:
        return 0.0
    try:
        st = os.stat(path)
    except OSError:
        return 0.0
    key = (path, st.st_mtime, st.st_size)
    if key not in _durations:
        try:
            info = GstPbutils.Discoverer.new(3 * SECOND).discover_uri(Gst.filename_to_uri(path))
            _durations[key] = max(0, info.get_duration()) / SECOND
        except Exception:                          # noqa: BLE001
            _durations[key] = 0.0
    return _durations[key]


def level_fraction(db: float) -> float:
    """-60 dB..0 dB as 0..1, for the meter."""
    return max(0.0, min(1.0, (db + 60.0) / 60.0))
