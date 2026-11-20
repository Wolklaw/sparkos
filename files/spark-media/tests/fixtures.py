"""Test files made on the spot: tagged songs (GStreamer encodes them, Python writes the FLAC
tags and cover), and a small camera RAW in the DNG format, written by hand."""

import io
import os
import struct
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image

# ─── DNG ──────────────────────────────────────────────────────

BYTE, ASCII, SHORT, LONG, RATIONAL, SRATIONAL = 1, 2, 3, 4, 5, 10
_SIZES = {BYTE: 1, ASCII: 1, SHORT: 2, LONG: 4, RATIONAL: 8, SRATIONAL: 8}


class _Tiff:
    """A little-endian TIFF built back to front: data first, then the IFDs that point to it."""

    def __init__(self):
        self.buf = bytearray(b'II*\x00\x00\x00\x00\x00')

    def blob(self, data: bytes) -> int:
        if len(self.buf) % 2:
            self.buf += b'\x00'
        at = len(self.buf)
        self.buf += data
        return at

    @staticmethod
    def _pack(kind: int, values) -> bytes:
        if kind == ASCII:
            return values.encode('ascii') + b'\x00'
        if kind == BYTE:
            return bytes(values)
        if kind == SHORT:
            return struct.pack(f'<{len(values)}H', *values)
        if kind == LONG:
            return struct.pack(f'<{len(values)}I', *values)
        if kind in (RATIONAL, SRATIONAL):
            fmt = 'I' if kind == RATIONAL else 'i'
            out = b''
            for num, den in values:
                out += struct.pack(f'<{fmt}{fmt}', num, den)
            return out
        raise ValueError(kind)

    def ifd(self, entries: Sequence[Tuple[int, int, object]]) -> int:
        packed = []
        for tag, kind, values in sorted(entries, key=lambda e: e[0]):
            if kind != ASCII and not isinstance(values, (list, tuple)):
                values = [values]
            data = self._pack(kind, values)
            count = len(data) // _SIZES[kind]
            if len(data) <= 4:
                field = data.ljust(4, b'\x00')
            else:
                field = struct.pack('<I', self.blob(data))
            packed.append(struct.pack('<HHI', tag, kind, count) + field)
        body = struct.pack('<H', len(packed)) + b''.join(packed) + b'\x00\x00\x00\x00'
        return self.blob(body)

    def finish(self, first_ifd: int) -> bytes:
        self.buf[4:8] = struct.pack('<I', first_ifd)
        return bytes(self.buf)


def make_dng(path: str, orientation: int = 1, raw_size=(192, 144), preview_size=(96, 72),
             make: str = 'Spark', model: str = 'Spark TestCam',
             taken: str = '2024:07:14 10:30:00') -> str:
    """A real (if tiny) DNG: an uncompressed thumbnail in IFD0, 12-bit RGGB sensor data in
    SubIFD 0, a JPEG preview in SubIFD 1, and EXIF with the date and exposure."""
    w, h = raw_size
    scene = Image.linear_gradient('L').resize((w, h)).convert('RGB')
    r, g, b = scene.split()
    b = b.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    scene = Image.merge('RGB', (r, g.point(lambda v: v // 2 + 60), b))
    pixels = scene.load()
    raw = bytearray()
    for y in range(h):
        for x in range(w):
            channel = (0 if y % 2 == 0 else 1) if x % 2 == 0 else (1 if y % 2 == 0 else 2)
            raw += struct.pack('<H', pixels[x, y][channel] * 16)          # 8 -> 12 bit
    preview = scene.resize(preview_size)
    jpeg = io.BytesIO()
    preview.save(jpeg, 'JPEG', quality=90)
    thumb = scene.resize((32, 24))

    t = _Tiff()
    raw_at = t.blob(bytes(raw))
    jpeg_at = t.blob(jpeg.getvalue())
    thumb_at = t.blob(thumb.tobytes())
    raw_ifd = t.ifd([
        (0x00FE, LONG, 0), (0x0100, LONG, w), (0x0101, LONG, h), (0x0102, SHORT, 16),
        (0x0103, SHORT, 1), (0x0106, SHORT, 32803), (0x0111, LONG, raw_at),
        (0x0115, SHORT, 1), (0x0116, LONG, h), (0x0117, LONG, len(raw)), (0x011C, SHORT, 1),
        (0x828D, SHORT, [2, 2]), (0x828E, BYTE, [0, 1, 1, 2]),
        (0xC61A, LONG, 0), (0xC61D, LONG, 4095),
    ])
    preview_ifd = t.ifd([
        (0x00FE, LONG, 1), (0x0100, LONG, preview_size[0]), (0x0101, LONG, preview_size[1]),
        (0x0102, SHORT, [8, 8, 8]), (0x0103, SHORT, 7), (0x0106, SHORT, 6),
        (0x0111, LONG, jpeg_at), (0x0115, SHORT, 3), (0x0116, LONG, preview_size[1]),
        (0x0117, LONG, len(jpeg.getvalue())), (0x011C, SHORT, 1),
    ])
    exif_ifd = t.ifd([
        (0x829A, RATIONAL, [(1, 125)]), (0x829D, RATIONAL, [(28, 10)]), (0x8827, SHORT, 200),
        (0x9003, ASCII, taken),
    ])
    ifd0 = t.ifd([
        (0x00FE, LONG, 1), (0x0100, LONG, 32), (0x0101, LONG, 24), (0x0102, SHORT, [8, 8, 8]),
        (0x0103, SHORT, 1), (0x0106, SHORT, 2), (0x010F, ASCII, make), (0x0110, ASCII, model),
        (0x0111, LONG, thumb_at), (0x0112, SHORT, orientation), (0x0115, SHORT, 3),
        (0x0116, LONG, 24), (0x0117, LONG, len(thumb.tobytes())), (0x011C, SHORT, 1),
        (0x0132, ASCII, taken), (0x014A, LONG, [raw_ifd, preview_ifd]),
        (0x8769, LONG, exif_ifd),
        (0xC612, BYTE, [1, 4, 0, 0]), (0xC613, BYTE, [1, 1, 0, 0]),
        (0xC614, ASCII, f'{make} {model}'),
        (0xC621, SRATIONAL, [(10000, 10000), (0, 10000), (0, 10000),
                             (0, 10000), (10000, 10000), (0, 10000),
                             (0, 10000), (0, 10000), (10000, 10000)]),
        (0xC628, RATIONAL, [(1, 2), (1, 1), (1, 2)]), (0xC65A, SHORT, 21),
    ])
    data = t.finish(ifd0)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def raw_like(path: str, preview: Tuple[int, int] = (300, 200), junk: int = 40000) -> str:
    """A file that is only bytes around a JPEG, like a format the TIFF reader doesn't know
    (CR3, RAF): the preview must still be found."""
    jpeg = io.BytesIO()
    Image.new('RGB', preview, '#ff4d8d').save(jpeg, 'JPEG')
    noise = bytes((i * 7919) % 251 for i in range(junk))
    with open(path, 'wb') as f:
        f.write(b'FAKERAW\x00' + noise + jpeg.getvalue() + noise)
    return path


# ─── Songs ────────────────────────────────────────────────────

def encode(gst, path: str, seconds: float = 1.0, tags: Optional[Dict[str, object]] = None) -> bool:
    """Encode a test tone by the file's extension (.ogg Vorbis, .flac, .mp3), with tags set
    through GStreamer's tag interface where the encoder takes them. False if this system
    can't encode that format."""
    Gst = gst.Gst
    ext = os.path.splitext(path)[1].lower()
    chain = {'.ogg': ['vorbisenc', 'oggmux'], '.flac': ['flacenc'],
             '.mp3': ['lamemp3enc', 'id3v2mux'], '.opus': ['opusenc', 'oggmux']}[ext]
    if any(Gst.ElementFactory.find(name) is None for name in chain):
        return False
    pipeline = Gst.Pipeline.new(None)
    src = Gst.ElementFactory.make('audiotestsrc', None)
    src.set_property('num-buffers', max(1, int(seconds * 44100 / 1024)))
    elements = [src, Gst.ElementFactory.make('audioconvert', None)]
    if ext == '.opus':
        elements.append(Gst.ElementFactory.make('audioresample', None))
    elements += [Gst.ElementFactory.make(name, None) for name in chain]
    sink = Gst.ElementFactory.make('filesink', None)
    sink.set_property('location', path)
    elements.append(sink)
    for element in elements:
        pipeline.add(element)
    for a, b in zip(elements, elements[1:]):
        a.link(b)
    if tags:
        taglist = Gst.TagList.new_empty()
        for name, value in tags.items():
            gvalue = value
            if isinstance(value, int):
                from gi.repository import GObject
                gvalue = GObject.Value(GObject.TYPE_UINT, value)
            taglist.add_value(Gst.TagMergeMode.REPLACE, name, gvalue)
        for element in elements:
            if isinstance(element, Gst.TagSetter):
                element.merge_tags(taglist, Gst.TagMergeMode.REPLACE)
    pipeline.set_state(Gst.State.PLAYING)
    msg = pipeline.get_bus().timed_pop_filtered(30 * gst.SECOND,
                                                Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipeline.set_state(Gst.State.NULL)
    return msg is not None and msg.type == Gst.MessageType.EOS


def flac_tags(path: str, comments: Dict[str, str], picture: Optional[bytes] = None) -> None:
    """Replace a FLAC file's Vorbis comments (and add a front cover) by rewriting its
    metadata blocks."""
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:4] == b'fLaC', "not a FLAC file"
    at, blocks = 4, []
    while True:
        head = data[at]
        length = int.from_bytes(data[at + 1:at + 4], 'big')
        kind = head & 0x7F
        if kind not in (1, 4, 6):                    # drop padding, comments, pictures
            blocks.append((kind, data[at + 4:at + 4 + length]))
        at += 4 + length
        if head & 0x80:
            break
    vendor = b'spark-media tests'
    body = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(comments))
    for key, value in comments.items():
        entry = f'{key}={value}'.encode('utf-8')
        body += struct.pack('<I', len(entry)) + entry
    blocks.append((4, body))
    if picture:
        mime = b'image/jpeg'
        with Image.open(io.BytesIO(picture)) as image:
            pw, ph = image.size
        pic = struct.pack('>I', 3) + struct.pack('>I', len(mime)) + mime + struct.pack('>I', 0)
        pic += struct.pack('>IIII', pw, ph, 24, 0) + struct.pack('>I', len(picture)) + picture
        blocks.append((6, pic))
    out = bytearray(b'fLaC')
    for i, (kind, body) in enumerate(blocks):
        last = 0x80 if i == len(blocks) - 1 else 0
        out += bytes([last | kind]) + len(body).to_bytes(3, 'big') + body
    out += data[at:]
    with open(path, 'wb') as f:
        f.write(out)


def cover_jpeg(colour: str = '#22d8ff', size: int = 300) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (size, size), colour).save(buf, 'JPEG')
    return buf.getvalue()


def fake_songs(n: int, artists: int = 400, albums_per_artist: int = 3) -> List[Dict[str, object]]:
    """n index entries that look like a real collection, for the speed test."""
    out = []
    for i in range(n):
        artist = i % artists
        album = (i // artists) % albums_per_artist
        out.append({'path': f'/music/Artist {artist}/Album {album}/{i:05d} Song {i}.flac',
                    'mtime': 1700000000.0 + i, 'size': 4000000 + i,
                    'title': f'Song {i}', 'artist': f'Artist {artist}',
                    'albumartist': f'Artist {artist}' if album == 0 else '',
                    'album': f'Album {album} of {artist}', 'track': i % 14 + 1, 'disc': 0,
                    'year': 1970 + i % 50, 'genre': 'Rock', 'length': 180.0 + i % 120})
    return out
