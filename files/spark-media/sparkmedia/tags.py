"""Reading a song's tags: title, artist, album artist, album, track, disc, year, genre, length
and cover art.

TagLib does it, through its C library (libtag_c, TagLib 2), which SparkOS already has for
KDE's file indexing: about a millisecond a song. Where it's missing, GStreamer's Discoverer
reads the same tags, much more slowly. Both run in the library's scanning thread, never in
the window's."""

import ctypes
import ctypes.util
import io
import os
import re
import threading
from typing import Any, Dict, Optional

from PIL import Image

from .core import file_uri, log


class Song(dict):
    """path, title, artist, albumartist, album, track, disc, year, genre, length (seconds)."""


def _number(text: Optional[str]) -> int:
    """'3/12' -> 3, '2009-05-01' -> 2009, junk -> 0."""
    match = re.match(r'\s*(\d+)', text or '')
    return int(match.group(1)) if match else 0


def _clean(text: Optional[str]) -> str:
    return (text or '').replace('\x00', ' ').strip()


def empty(path: str) -> Song:
    return Song(path=path, title='', artist='', albumartist='', album='', track=0, disc=0,
                year=0, genre='', length=0.0)


def cover_from_bytes(data: bytes) -> Optional[Image.Image]:
    try:
        image = Image.open(io.BytesIO(data))
        image.draft('RGB', (512, 512))
        image.load()
        return image.convert('RGB')
    except Exception:      # noqa: BLE001
        return None


# ─── TagLib (libtag_c) ────────────────────────────────────────

class _Picture(ctypes.Structure):
    _fields_ = [('mimeType', ctypes.c_char_p), ('description', ctypes.c_char_p),
                ('pictureType', ctypes.c_char_p), ('data', ctypes.c_void_p),
                ('size', ctypes.c_uint)]


class TagLib:
    """The few TagLib C calls we need. Only one thread may use it at a time (TagLib's C binding
    keeps returned strings in one global list), so calls go through a lock."""

    def __init__(self, lib: ctypes.CDLL):
        self.lib = lib
        self.lock = threading.Lock()
        vp, cp = ctypes.c_void_p, ctypes.c_char_p
        lib.taglib_set_strings_unicode.argtypes = [ctypes.c_int]
        lib.taglib_set_strings_unicode(1)
        lib.taglib_set_string_management_enabled.argtypes = [ctypes.c_int]
        lib.taglib_set_string_management_enabled(0)        # we free each string ourselves
        lib.taglib_file_new.restype = vp
        lib.taglib_file_new.argtypes = [cp]
        lib.taglib_file_is_valid.argtypes = [vp]
        lib.taglib_file_free.argtypes = [vp]
        lib.taglib_file_tag.restype = vp
        lib.taglib_file_tag.argtypes = [vp]
        lib.taglib_file_audioproperties.restype = vp
        lib.taglib_file_audioproperties.argtypes = [vp]
        lib.taglib_audioproperties_length.argtypes = [vp]
        lib.taglib_free.argtypes = [vp]
        for name in ('title', 'artist', 'album', 'genre'):
            fn = getattr(lib, f'taglib_tag_{name}')
            fn.restype = vp                                 # a pointer we must free
            fn.argtypes = [vp]
        for name in ('year', 'track'):
            fn = getattr(lib, f'taglib_tag_{name}')
            fn.restype = ctypes.c_uint
            fn.argtypes = [vp]
        lib.taglib_property_get.restype = ctypes.POINTER(vp)
        lib.taglib_property_get.argtypes = [vp, cp]
        lib.taglib_property_free.argtypes = [ctypes.POINTER(vp)]
        self.pictures = hasattr(lib, 'taglib_complex_property_get')     # TagLib 2
        if self.pictures:
            lib.taglib_complex_property_get.restype = vp
            lib.taglib_complex_property_get.argtypes = [vp, cp]
            lib.taglib_picture_from_complex_property.argtypes = [vp, ctypes.POINTER(_Picture)]
            lib.taglib_complex_property_free.argtypes = [vp]

    def _text(self, pointer: Optional[int]) -> str:
        if not pointer:
            return ''
        try:
            return _clean(ctypes.string_at(pointer).decode('utf-8', 'replace'))
        finally:
            self.lib.taglib_free(pointer)

    def _property(self, handle: int, name: str) -> str:
        values = self.lib.taglib_property_get(handle, name.encode())
        if not values:
            return ''
        try:
            return _clean(ctypes.string_at(values[0]).decode('utf-8', 'replace')) \
                if values[0] else ''
        finally:
            self.lib.taglib_property_free(values)

    def read(self, path: str, want_cover: bool = False) -> Optional[Dict[str, Any]]:
        with self.lock:
            handle = self.lib.taglib_file_new(os.fsencode(path))
            if not handle:
                return None
            try:
                if not self.lib.taglib_file_is_valid(handle):
                    return None
                song = empty(path)
                tag = self.lib.taglib_file_tag(handle)
                if tag:
                    song['title'] = self._text(self.lib.taglib_tag_title(tag))
                    song['artist'] = self._text(self.lib.taglib_tag_artist(tag))
                    song['album'] = self._text(self.lib.taglib_tag_album(tag))
                    song['genre'] = self._text(self.lib.taglib_tag_genre(tag))
                    song['year'] = int(self.lib.taglib_tag_year(tag) or 0)
                    song['track'] = int(self.lib.taglib_tag_track(tag) or 0)
                song['albumartist'] = self._property(handle, 'ALBUMARTIST')
                song['disc'] = _number(self._property(handle, 'DISCNUMBER'))
                props = self.lib.taglib_file_audioproperties(handle)
                if props:
                    song['length'] = float(self.lib.taglib_audioproperties_length(props))
                cover = None
                if want_cover and self.pictures:
                    cover = self._picture(handle)
                return {'song': song, 'cover': cover}
            finally:
                self.lib.taglib_file_free(handle)

    def _picture(self, handle: int) -> Optional[bytes]:
        props = self.lib.taglib_complex_property_get(handle, b'PICTURE')
        if not props:
            return None
        try:
            picture = _Picture()
            self.lib.taglib_picture_from_complex_property(props, ctypes.byref(picture))
            if picture.data and picture.size:
                return ctypes.string_at(picture.data, picture.size)
            return None
        finally:
            self.lib.taglib_complex_property_free(props)


_taglib: Optional[TagLib] = None
_taglib_tried = False


def taglib() -> Optional[TagLib]:
    global _taglib, _taglib_tried
    if _taglib_tried:
        return _taglib
    _taglib_tried = True
    if os.environ.get('SPARK_MEDIA_NO_TAGLIB'):          # tests use this to try GStreamer
        return None
    names = ['libtag_c.so.2', 'libtag_c.so.1', ctypes.util.find_library('tag_c') or '']
    if os.name == 'nt':
        names += ['tag_c.dll', 'libtag_c.dll']
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            _taglib = TagLib(lib)
            log.info("tags: TagLib (%s)%s", name, "" if _taglib.pictures else ", no cover art")
            return _taglib
        except (OSError, AttributeError) as exc:
            log.debug("TagLib %s: %s", name, exc)
    return None


# ─── GStreamer's Discoverer ───────────────────────────────────

_discoverer = None


def _discover(path: str, want_cover: bool) -> Optional[Dict[str, Any]]:
    global _discoverer
    from . import player as gst
    if gst.init() is not None or gst.GstPbutils is None:
        return None
    Gst, GstPbutils = gst.Gst, gst.GstPbutils
    if _discoverer is None:
        _discoverer = GstPbutils.Discoverer.new(5 * Gst.SECOND)
    try:
        info = _discoverer.discover_uri(file_uri(path))
    except Exception as exc:      # noqa: BLE001 - GLib.Error for files it can't read
        log.debug("discoverer: %s: %s", path, exc)
        return None
    if info.get_result() != GstPbutils.DiscovererResult.OK or not info.get_audio_streams():
        return None
    song = empty(path)
    taglist = None
    for stream in info.get_audio_streams():
        taglist = stream.get_tags()
        if taglist is not None:
            break
    if taglist is None and hasattr(info, 'get_tags'):
        taglist = info.get_tags()
    cover = None
    if taglist is not None:
        def text(name):
            ok, value = taglist.get_string(name)
            return _clean(value) if ok else ''

        def uint(name):
            ok, value = taglist.get_uint(name)
            return int(value) if ok else 0

        song.update(title=text('title'), artist=text('artist'), album=text('album'),
                    albumartist=text('album-artist'), genre=text('genre'),
                    track=uint('track-number'), disc=uint('album-disc-number'))
        ok, when = taglist.get_date_time('datetime')
        if ok and when is not None and when.has_year():
            song['year'] = when.get_year()
        else:
            ok, date = taglist.get_date('date')
            if ok and date is not None:
                song['year'] = date.get_year()
        if want_cover:
            for name in ('image', 'preview-image'):
                ok, sample = taglist.get_sample(name)
                if ok and sample is not None:
                    buf = sample.get_buffer()
                    mapped, data = buf.map(Gst.MapFlags.READ)
                    if mapped:
                        try:
                            cover = bytes(data.data)
                        finally:
                            buf.unmap(data)
                        break
    duration = info.get_duration()
    if duration and duration > 0:
        song['length'] = duration / Gst.SECOND
    return {'song': song, 'cover': cover}


def backend() -> str:
    if taglib() is not None:
        return 'taglib'
    from . import player as gst
    return 'gstreamer' if gst.init() is None and gst.GstPbutils is not None else 'none'


def read(path: str, want_cover: bool = False) -> Dict[str, Any]:
    """{'song': Song, 'cover': bytes or None}. Never raises: an unreadable file gives a song
    with only its path, named after the file."""
    result = None
    lib = taglib()
    try:
        result = lib.read(path, want_cover) if lib is not None else _discover(path, want_cover)
    except Exception as exc:      # noqa: BLE001 - one broken file must not stop a scan
        log.warning("tags: %s: %s", path, exc)
    if result is None:
        result = {'song': empty(path), 'cover': None}
    return result
