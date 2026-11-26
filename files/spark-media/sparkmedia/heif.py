"""HEIC/HEIF and AVIF photos (what phones save) through libheif's C library, the one other desktops'
image plugins use, called with ctypes like TagLib and LibRaw.

libheif decodes AVIF with dav1d or libaom, and HEIC only when it has an HEVC decoder (libde265,
or its FFmpeg plugin). Which it has is asked at run time (have_decoder), so an error says
what's missing instead of guessing. libheif applies the photo's rotation and mirroring itself,
so the EXIF orientation inside is not applied a second time."""

import ctypes
import ctypes.util
import logging
import os
from typing import Dict, Optional, Tuple

from PIL import Image

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

HEIF_EXT = frozenset(('heic', 'heif', 'hif', 'heics', 'avif', 'avifs'))
HEVC, AV1 = 1, 4                      # enum heif_compression_format
RGB, INTERLEAVED_RGB, INTERLEAVED_RGBA, CHANNEL_INTERLEAVED = 1, 10, 11, 10


class _Error(ctypes.Structure):
    _fields_ = [('code', ctypes.c_int), ('subcode', ctypes.c_int), ('message', ctypes.c_char_p)]


class HeifError(Exception):
    pass


_lib: Optional[ctypes.CDLL] = None
_tried = False


def library() -> Optional[ctypes.CDLL]:
    global _lib, _tried
    if _tried:
        return _lib
    _tried = True
    names = [os.environ.get('SPARK_MEDIA_LIBHEIF', ''), 'libheif.so.1',
             ctypes.util.find_library('heif') or '']
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            _declare(lib)
        except (OSError, AttributeError) as exc:
            log.debug("libheif %s: %s", name, exc)
            continue
        if hasattr(lib, 'heif_init'):
            lib.heif_init(None)                  # loads the decoder plugins
        _lib = lib
        log.info("HEIF: libheif %s (%s); HEVC %s, AV1 %s", version(), name,
                 'yes' if lib.heif_have_decoder_for_format(HEVC) else 'no',
                 'yes' if lib.heif_have_decoder_for_format(AV1) else 'no')
        return lib
    return None


def _declare(lib: ctypes.CDLL) -> None:
    vp, ip = ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
    lib.heif_get_version.restype = ctypes.c_char_p
    if hasattr(lib, 'heif_init'):
        lib.heif_init.restype = _Error
        lib.heif_init.argtypes = [vp]
    lib.heif_have_decoder_for_format.argtypes = [ctypes.c_int]
    lib.heif_context_alloc.restype = vp
    lib.heif_context_free.argtypes = [vp]
    lib.heif_context_read_from_memory_without_copy.restype = _Error
    lib.heif_context_read_from_memory_without_copy.argtypes = [vp, vp, ctypes.c_size_t, vp]
    lib.heif_context_get_primary_image_handle.restype = _Error
    lib.heif_context_get_primary_image_handle.argtypes = [vp, ctypes.POINTER(vp)]
    for name in ('heif_image_handle_get_width', 'heif_image_handle_get_height',
                 'heif_image_handle_has_alpha_channel',
                 'heif_image_handle_get_number_of_thumbnails'):
        getattr(lib, name).argtypes = [vp]
    lib.heif_image_handle_get_list_of_thumbnail_IDs.argtypes = [
        vp, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int]
    lib.heif_image_handle_get_thumbnail.restype = _Error
    lib.heif_image_handle_get_thumbnail.argtypes = [vp, ctypes.c_uint32, ctypes.POINTER(vp)]
    lib.heif_image_handle_release.argtypes = [vp]
    lib.heif_decode_image.restype = _Error
    lib.heif_decode_image.argtypes = [vp, ctypes.POINTER(vp), ctypes.c_int, ctypes.c_int, vp]
    lib.heif_image_get_plane_readonly.restype = ctypes.POINTER(ctypes.c_uint8)
    lib.heif_image_get_plane_readonly.argtypes = [vp, ctypes.c_int, ip]
    lib.heif_image_get_width.argtypes = [vp, ctypes.c_int]
    lib.heif_image_get_height.argtypes = [vp, ctypes.c_int]
    lib.heif_image_release.argtypes = [vp]
    lib.heif_image_handle_get_number_of_metadata_blocks.argtypes = [vp, ctypes.c_char_p]
    lib.heif_image_handle_get_list_of_metadata_block_IDs.argtypes = [
        vp, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int]
    lib.heif_image_handle_get_metadata_size.restype = ctypes.c_size_t
    lib.heif_image_handle_get_metadata_size.argtypes = [vp, ctypes.c_uint32]
    lib.heif_image_handle_get_metadata.restype = _Error
    lib.heif_image_handle_get_metadata.argtypes = [vp, ctypes.c_uint32, vp]


def version() -> Optional[str]:
    lib = library()
    return lib.heif_get_version().decode() if lib is not None else None


def decoders() -> Dict[str, bool]:
    lib = library()
    if lib is None:
        return {'heic': False, 'avif': False}
    return {'heic': bool(lib.heif_have_decoder_for_format(HEVC)),
            'avif': bool(lib.heif_have_decoder_for_format(AV1))}


def is_heif(path: str) -> bool:
    return os.path.splitext(path)[1][1:].lower() in HEIF_EXT


def brand(data: bytes) -> str:
    """'avif' or 'heic' from the file's own ftyp box (the extension can lie)."""
    if data[4:8] != b'ftyp':
        return ''
    size = int.from_bytes(data[:4], 'big')
    brands = [data[8:12]] + [data[i:i + 4] for i in range(16, min(size, 64), 4)]
    if any(b in (b'avif', b'avis') for b in brands):
        return 'avif'
    if any(b in (b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1')
           for b in brands):
        return 'heic'
    return ''


def _check(err: _Error, what: str) -> None:
    if err.code != 0:
        message = err.message.decode('utf-8', 'replace') if err.message else f'error {err.code}'
        raise HeifError(f"{what}: {message}")


def _decode_handle(lib, handle) -> Image.Image:
    alpha = bool(lib.heif_image_handle_has_alpha_channel(handle))
    image = ctypes.c_void_p()
    _check(lib.heif_decode_image(handle, ctypes.byref(image), RGB,
                                 INTERLEAVED_RGBA if alpha else INTERLEAVED_RGB, None), "decode")
    try:
        stride = ctypes.c_int(0)
        plane = lib.heif_image_get_plane_readonly(image, CHANNEL_INTERLEAVED, ctypes.byref(stride))
        width = lib.heif_image_get_width(image, CHANNEL_INTERLEAVED)
        height = lib.heif_image_get_height(image, CHANNEL_INTERLEAVED)
        if not plane or width <= 0 or height <= 0:
            raise HeifError("decode: no picture")
        data = ctypes.string_at(plane, stride.value * height)
        mode = 'RGBA' if alpha else 'RGB'
        return Image.frombuffer(mode, (width, height), data, 'raw', mode, stride.value, 1).copy()
    finally:
        lib.heif_image_release(image)


def _exif(lib, handle) -> Optional[Image.Exif]:
    count = lib.heif_image_handle_get_number_of_metadata_blocks(handle, b'Exif')
    if count <= 0:
        return None
    ids = (ctypes.c_uint32 * count)()
    lib.heif_image_handle_get_list_of_metadata_block_IDs(handle, b'Exif', ids, count)
    size = lib.heif_image_handle_get_metadata_size(handle, ids[0])
    if not 4 < size < 4_000_000:
        return None
    buf = ctypes.create_string_buffer(size)
    if lib.heif_image_handle_get_metadata(handle, ids[0], buf).code != 0:
        return None
    raw = buf.raw
    skip = int.from_bytes(raw[:4], 'big')          # where the TIFF header starts, after 4 bytes
    tiff = raw[4 + skip:]
    if tiff[:2] not in (b'II', b'MM'):
        at = max(raw.find(b'II*\x00'), raw.find(b'MM\x00*'))
        if at < 0:
            return None
        tiff = raw[at:]
    exif = Image.Exif()
    try:
        exif.load(b'Exif\x00\x00' + tiff)
    except Exception:      # noqa: BLE001 - damaged EXIF must not stop the photo
        return None
    exif[0x0112] = 1        # libheif has already turned the picture upright
    return exif


def read(path: str, thumbnail: int = 0) -> Tuple[Image.Image, Optional[Image.Exif], str]:
    """(upright picture, EXIF, 'HEIC' or 'AVIF'). With thumbnail, the smallest stored
    thumbnail at least that big when the file has one (fast), else the full picture."""
    lib = library()
    with open(path, 'rb') as f:
        data = f.read()
    kind = brand(data) or ('avif' if path.lower().endswith(('.avif', '.avifs')) else 'heic')
    label = kind.upper()
    if lib is None:
        raise HeifError(f"no libheif to read {label}")
    if not lib.heif_have_decoder_for_format(AV1 if kind == 'avif' else HEVC):
        raise HeifError(f"libheif {version()} has no {'AV1' if kind == 'avif' else 'HEVC'} "
                        "decoder")
    buf = ctypes.create_string_buffer(data, len(data))
    ctx = lib.heif_context_alloc()
    handle = ctypes.c_void_p()
    try:
        _check(lib.heif_context_read_from_memory_without_copy(ctx, buf, len(data), None), "read")
        _check(lib.heif_context_get_primary_image_handle(ctx, ctypes.byref(handle)), "open")
        exif = _exif(lib, handle)
        if thumbnail:
            small = _thumbnail(lib, handle, thumbnail)
            if small is not None:
                return small, exif, label
        return _decode_handle(lib, handle), exif, label
    finally:
        if handle:
            lib.heif_image_handle_release(handle)
        lib.heif_context_free(ctx)


def _thumbnail(lib, handle, at_least: int) -> Optional[Image.Image]:
    count = lib.heif_image_handle_get_number_of_thumbnails(handle)
    if count <= 0:
        return None
    ids = (ctypes.c_uint32 * count)()
    lib.heif_image_handle_get_list_of_thumbnail_IDs(handle, ids, count)
    best = None
    for item in ids:
        thumb = ctypes.c_void_p()
        if lib.heif_image_handle_get_thumbnail(handle, item, ctypes.byref(thumb)).code != 0:
            continue
        try:
            side = max(lib.heif_image_handle_get_width(thumb), lib.heif_image_handle_get_height(thumb))
            if side >= at_least and (best is None or side < best[0]):
                best = (side, _decode_handle(lib, thumb))
        except HeifError:
            continue
        finally:
            lib.heif_image_handle_release(thumb)
    return best[1] if best else None


def explain(path: str) -> str:
    """Why a HEIC or AVIF can't be shown here, for the error message (English; the viewer
    translates the known cases)."""
    lib = library()
    if lib is None:
        return 'nolib'
    with open(path, 'rb') as f:
        kind = brand(f.read(64))
    if kind == 'avif' and not lib.heif_have_decoder_for_format(AV1):
        return 'noav1'
    if kind != 'avif' and not lib.heif_have_decoder_for_format(HEVC):
        return 'nohevc'
    return 'damaged'

