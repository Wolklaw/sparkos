"""The recording pipeline, as gst-launch arguments: screen (or a test pattern) -> encoder ->
one-second MPEG-TS pieces through splitmuxsink, with one Opus or AAC track per audio source.

gst-launch runs as its own process, so a GStreamer crash never takes the service down, and
SIGINT ends it cleanly (-e). Which encoder runs is decided here from what gst-inspect finds:
the GPU's VA-API encoder first, then software ones."""

import shutil
import subprocess
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from . import buffer
from .core import fake


class Encoder(NamedTuple):
    codec: str            # 'h264' or 'hevc'
    element: str
    parser: str
    gpu: bool
    label: str


ENCODERS = (
    Encoder('h264', 'vah264enc', 'h264parse', True, 'H.264 (GPU)'),
    Encoder('h264', 'openh264enc', 'h264parse', False, 'H.264 (OpenH264)'),
    Encoder('h264', 'x264enc', 'h264parse', False, 'H.264 (x264)'),
    Encoder('hevc', 'vah265enc', 'h265parse', True, 'HEVC (GPU)'),
    Encoder('hevc', 'x265enc', 'h265parse', False, 'HEVC (x265)'),
)
AUDIO_ENCODERS = (('avenc_aac', 'aacparse', 'AAC'), ('fdkaacenc', 'aacparse', 'AAC'),
                  ('opusenc', 'opusparse', 'Opus'))
REQUIRED = ('queue', 'videorate', 'videoconvert', 'videoscale', 'splitmuxsink', 'mpegtsmux',
            'audioconvert', 'audioresample', 'tsdemux', 'mp4mux')
LIVE = ('pipewiresrc', 'pulsesrc')


def gst_tool(name: str) -> Optional[str]:
    return shutil.which(name)


_cache: Dict[str, bool] = {}


def element_exists(element: str) -> bool:
    if element in _cache:
        return _cache[element]
    tool = gst_tool('gst-inspect-1.0')
    ok = False
    if tool:
        try:
            ok = subprocess.run([tool, '--exists', element], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    _cache[element] = ok
    return ok


def pick_encoder(codec: str, exists: Callable[[str], bool] = element_exists,
                 forced: Optional[str] = None) -> Optional[Encoder]:
    """The first encoder of this codec that is installed. `forced` (an element name) is for
    the tests, which can't use the GPU. HEVC falls back to nothing: asking for it on a PC
    without an encoder is the settings' problem to report, not a reason to switch silently."""
    for enc in ENCODERS:
        if enc.codec != codec or (forced and enc.element != forced):
            continue
        if exists(enc.element) and exists(enc.parser):
            if enc.gpu and not exists('vapostproc'):
                continue
            return enc
    return None


def pick_audio_encoder(exists: Callable[[str], bool] = element_exists):
    for element, parser, label in AUDIO_ENCODERS:
        if exists(element) and exists(parser):
            return element, parser, label
    return None


def scaled_size(width: int, height: int, size: str) -> Tuple[int, int]:
    """The output size for the 'native', '1080' or '720' setting: never larger than the
    source, same shape, even sides."""
    if size in ('1080', '720'):
        target = int(size)
        if height > target:
            width = int(round(width * target / height / 2)) * 2
            height = target
    return width - width % 2, height - height % 2


def fps_value(setting: str) -> Optional[int]:
    return None if setting == 'native' else int(setting)


def key_interval(setting: str) -> int:
    return fps_value(setting) or 120          # one keyframe a second; native: at most 2 s at 60


def bitrate_kbps(mbps: int, width: int, height: int, fps: int) -> int:
    """The cap is set for 2560x1440 at 60 fps; a smaller picture or a slower rate needs less."""
    pixels = (width * height) if width and height else 2560 * 1440
    scale = min(1.0, pixels / (2560 * 1440)) * min(1.0, fps / 60) ** 0.7
    return max(2000, int(mbps * 1000 * scale))


def video_chain(enc: Encoder, settings: dict, width: int, height: int) -> List[str]:
    """Everything from the raw frames to the parsed, encoded stream."""
    fps = fps_value(settings['fps'])
    out_w, out_h = (scaled_size(width, height, settings['size']) if width and height else (0, 0))
    tokens: List[str] = ['queue', 'max-size-buffers=4', 'max-size-bytes=0', 'max-size-time=0',
                         'leaky=downstream', '!']
    if fps:
        tokens += ['videorate', '!', f'video/x-raw,framerate={fps}/1', '!']
    kbps = bitrate_kbps(int(settings['bitrate']), out_w, out_h, fps or 60)
    key = key_interval(settings['fps'])
    size_caps = f',width={out_w},height={out_h}' if out_w else ''
    if enc.gpu:
        tokens += ['vapostproc', '!', f'video/x-raw(memory:VAMemory),format=NV12{size_caps}', '!',
                   enc.element, 'rate-control=vbr', f'bitrate={kbps}', 'target-percentage=70',
                   f'key-int-max={key}', 'b-frames=0']
    else:
        tokens += ['videoconvert', '!', 'videoscale', '!', f'video/x-raw,format=I420{size_caps}',
                   '!']
        if enc.element == 'openh264enc':
            tokens += [enc.element, f'bitrate={kbps * 1000}', f'gop-size={key}',
                       'complexity=low', 'rate-control=bitrate']
        elif enc.element == 'x264enc':
            tokens += [enc.element, 'tune=zerolatency', 'speed-preset=veryfast',
                       f'bitrate={kbps}', f'key-int-max={key}', 'bframes=0']
        else:
            tokens += [enc.element, 'tune=zerolatency', 'speed-preset=veryfast',
                       f'bitrate={kbps}', f'key-int-max={key}']
    tokens += ['!', enc.parser]
    if enc.parser == 'h264parse' or enc.parser == 'h265parse':
        tokens += ['config-interval=-1']
    return tokens + ['!', 'queue']


def audio_chain(source: List[str], enc) -> List[str]:
    element, parser, _label = enc
    return [*source, '!', 'audio/x-raw,rate=48000,channels=2', '!', 'audioconvert', '!',
            'audioresample', '!', 'queue', '!', element, 'bitrate=128000', '!', parser, '!',
            'queue']


def audio_sources(sound: bool, mic: bool) -> List[List[str]]:
    """The default output's monitor (what the speakers play), then the default microphone."""
    if fake():
        sources = []
        if sound:
            sources.append(['audiotestsrc', 'is-live=true', 'freq=440', 'volume=0.2'])
        if mic:
            sources.append(['audiotestsrc', 'is-live=true', 'freq=880', 'volume=0.2'])
        return sources
    sources = []
    if sound:
        sink = ''
        if shutil.which('pactl'):
            try:
                sink = subprocess.run(['pactl', 'get-default-sink'], capture_output=True,
                                      text=True, timeout=5).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
        sources.append(['pulsesrc', f'device={sink}.monitor' if sink else 'device=@DEFAULT_MONITOR@',
                        'do-timestamp=true', 'provide-clock=false', 'buffer-time=200000'])
    if mic:
        sources.append(['pulsesrc', 'do-timestamp=true', 'provide-clock=false',
                        'buffer-time=200000'])
    return sources


def build(settings: dict, enc: Encoder, video_source: List[str], width: int, height: int,
          audio_enc, folder: str) -> List[str]:
    """gst-launch arguments (without the program name)."""
    args = ['-e', '-q', *video_source, '!',
            *video_chain(enc, settings, width, height), '!', 'sink.video']
    if audio_enc:
        for i, source in enumerate(audio_sources(settings['sound'], settings['mic'])):
            args += [*audio_chain(source, audio_enc), '!', f'sink.audio_{i}']
    args += ['splitmuxsink', 'name=sink', 'muxer-factory=mpegtsmux',
             f'max-size-time={int(buffer.PIECE_SECONDS * 1_000_000_000)}',
             'send-keyframe-requests=true', f'location={folder}/{buffer.PATTERN}']
    return args


def fake_source(settings: dict, width: int = 640, height: int = 360) -> List[str]:
    fps = fps_value(settings['fps']) or 60
    return ['videotestsrc', 'is-live=true', 'pattern=ball', '!',
            f'video/x-raw,width={width},height={height},framerate={fps}/1']


def portal_source(fd: int, node: int) -> List[str]:
    return ['pipewiresrc', f'fd={fd}', f'path={node}', 'do-timestamp=true',
            'keepalive-time=1000', 'always-copy=true']


def missing_elements(exists: Callable[[str], bool] = element_exists) -> List[str]:
    return [e for e in REQUIRED if not exists(e)]


def describe(settings: dict, exists: Callable[[str], bool] = element_exists) -> Dict[str, object]:
    """What would run with these settings (for --status and the window)."""
    enc = pick_encoder(settings['codec'], exists)
    audio = pick_audio_encoder(exists)
    return {'encoder': enc.label if enc else None, 'audio': audio[2] if audio else None,
            'missing': missing_elements(exists)}
