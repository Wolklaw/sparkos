"""Camera RAW photos: CR2, CR3, NEF, ARW, DNG, RAF, ORF, RW2 (and PEF, SRW, NRW, RAW).

Two steps, so a RAW opens as fast as a JPEG:
1. The JPEG the camera stored inside the file. Every camera writes one; most are full size.
   Found by reading the file, no extra program needed.
2. When that preview is smaller than the photo, the full decode from the sensor data, in the
   background, by LibRaw's C library (SparkOS has it already).

The camera, lens, settings and date come from the RAW's TIFF tags (all of these formats but
CR3 and RAF are TIFF inside), read with Pillow's TIFF tag reader."""

import ctypes
import ctypes.util
import io
import logging
import os
import struct
from typing import Dict, List, Optional, Tuple

from PIL import ExifTags, Image, TiffImagePlugin

from . import APP_SLUG

log = logging.getLogger(APP_SLUG)

RAW_EXT = frozenset('cr2 cr3 crw nef nrw arw srf sr2 dng raf orf rw2 pef srw rwl 3fr iiq x3f'
                    .split())
TAGS_WANTED = {0x010F: 'make', 0x0110: 'model', 0x0112: 'orientation', 0x0132: 'datetime'}
EXIF_WANTED = {0x9003: 'taken', 0x829A: 'exposure', 0x829D: 'fnumber', 0x8827: 'iso',
               0x920A: 'focal', 0xA434: 'lens'}


def is_raw(path: str) -> bool:
    return os.path.splitext(path)[1][1:].lower() in RAW_EXT


# ─── The embedded JPEG ────────────────────────────────────────

def _jpeg_starts(data: bytes) -> List[int]:
    out, at = [], data.find(b'\xff\xd8\xff')
    while at >= 0 and len(out) < 64:
        out.append(at)
        at = data.find(b'\xff\xd8\xff', at + 3)
    return out


def previews(data: bytes) -> List[Tuple[int, int, int]]:
    """Every JPEG stored in the file that Pillow can read: (pixels, offset, (w, h)), largest
    first. The sensor data of some formats is itself a lossless JPEG; those don't decode with
    Pillow and are dropped when loading."""
    found = []
    for start in _jpeg_starts(data):
        try:
            with Image.open(io.BytesIO(data[start:])) as image:
                if image.format != 'JPEG' or image.mode not in ('RGB', 'L', 'CMYK', 'YCbCr'):
                    continue
                w, h = image.size
                if w >= 64 and h >= 64:
                    found.append((w * h, start, w, h))
        except Exception:      # noqa: BLE001 - random bytes that look like a JPEG start
            continue
    found.sort(reverse=True)
    return [(px, start, (w, h)) for px, start, w, h in found]


def embedded_preview(path: str, max_side: int = 0) -> Optional[Image.Image]:
    """The biggest JPEG the camera stored in the RAW, decoded. With max_side, decoded at a
    fraction of its size (fast thumbnails). Not rotated; see orientation()."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None
    for _px, start, _size in previews(data):
        try:
            image = Image.open(io.BytesIO(data[start:]))
            if max_side:
                image.draft('RGB', (max_side, max_side))
            image.load()
            return image.convert('RGB')
        except Exception:      # noqa: BLE001 - lossless sensor data, a truncated preview
            continue
    return None


# ─── Tags ─────────────────────────────────────────────────────

def _tiff_header(f) -> Optional[bytes]:
    """A standard TIFF header with the file's byte order and first IFD offset (ORF and RW2
    use their own magic number, which Pillow's tag reader won't take)."""
    f.seek(0)
    head = f.read(8)
    if len(head) < 8 or head[:2] not in (b'II', b'MM'):
        return None
    return head[:2] + (b'*\x00' if head[:2] == b'II' else b'\x00*') + head[4:8]


def _load_ifd(f, ifh: bytes, offset: int) -> Optional[TiffImagePlugin.ImageFileDirectory_v2]:
    ifd = TiffImagePlugin.ImageFileDirectory_v2(ifh=ifh)
    try:
        f.seek(offset)
        ifd.load(f)
    except Exception:      # noqa: BLE001
        return None
    return ifd


def _ifds(f) -> List[TiffImagePlugin.ImageFileDirectory_v2]:
    """IFD0, then the EXIF IFD if there is one."""
    ifh = _tiff_header(f)
    if ifh is None:
        return []
    order = '<' if ifh[:2] == b'II' else '>'
    first = _load_ifd(f, ifh, struct.unpack(order + 'I', ifh[4:8])[0])
    if first is None:
        return []
    out = [first]
    exif_at = first.get(0x8769)
    if isinstance(exif_at, int) and exif_at > 0:
        sub = _load_ifd(f, ifh, exif_at)
        if sub is not None:
            out.append(sub)
    return out


def _value(v):
    if isinstance(v, tuple) and len(v) == 1:
        v = v[0]
    if isinstance(v, bytes):
        v = v.decode('latin-1', 'replace')
    if isinstance(v, str):
        v = v.strip('\x00 ').strip()
    return v


def info(path: str) -> Dict[str, object]:
    """make, model, orientation, taken, exposure, fnumber, iso, focal, lens: whatever the file
    has. Empty for formats that aren't TIFF inside (CR3, RAF); their preview's EXIF fills in."""
    out: Dict[str, object] = {}
    try:
        with open(path, 'rb') as f:
            ifds = _ifds(f)
    except OSError:
        return out
    if not ifds:
        return out
    for tag, name in TAGS_WANTED.items():
        if tag in ifds[0]:
            out[name] = _value(ifds[0][tag])
    if len(ifds) > 1:
        for tag, name in EXIF_WANTED.items():
            if tag in ifds[1]:
                out[name] = _value(ifds[1][tag])
    return out


def exif_of(path: str, preview: Optional[Image.Image] = None) -> Image.Exif:
    """An EXIF block for a saved edit of the RAW: camera, lens, settings and the date taken."""
    exif = Image.Exif()
    if preview is not None:
        try:
            got = preview.getexif()
            for tag, value in got.items():
                if tag in (0x010F, 0x0110, 0x0131, 0x0132):
                    exif[tag] = value
            sub = got.get_ifd(ExifTags.IFD.Exif)
            if sub:
                exif[ExifTags.IFD.Exif] = dict(sub)
        except Exception:      # noqa: BLE001
            pass
    facts = info(path)
    for tag, name in TAGS_WANTED.items():
        if name in facts and name != 'orientation' and isinstance(facts[name], str):
            exif[tag] = facts[name]
    sub = dict(exif.get(ExifTags.IFD.Exif) or {}) if isinstance(exif.get(ExifTags.IFD.Exif), dict) \
        else {}
    for tag, name in EXIF_WANTED.items():
        if name in facts and facts[name] not in (None, ''):
            sub[tag] = facts[name]
    if sub:
        exif[ExifTags.IFD.Exif] = sub
    return exif


ORIENT = {3: 180, 6: 90, 8: 270}


def orientation(path: str, preview: Optional[Image.Image] = None) -> int:
    """Clockwise degrees to turn the picture upright: the RAW's own tag, else the preview's."""
    value = info(path).get('orientation')
    if not isinstance(value, int) and preview is not None:
        try:
            value = preview.getexif().get(0x0112)
        except Exception:      # noqa: BLE001
            value = None
    return ORIENT.get(value, 0) if isinstance(value, int) else 0


def upright(image: Image.Image, degrees: int) -> Image.Image:
    method = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
              270: Image.Transpose.ROTATE_90}.get(degrees)
    return image.transpose(method) if method is not None else image


def sensor_size(path: str) -> Optional[Tuple[int, int]]:
    """The photo's full size in pixels, when the file says (DNG and most TIFF-based RAWs):
    the biggest main image (NewSubfileType 0) in IFD0 or its SubIFDs."""
    try:
        with open(path, 'rb') as f:
            ifh = _tiff_header(f)
            ifds = _ifds(f)
            if not ifds or ifh is None:
                return None
            subs = ifds[0].get(0x014A) or ()
            if isinstance(subs, int):
                subs = (subs,)
            candidates = [ifds[0]] + [ifd for ifd in (_load_ifd(f, ifh, o) for o in subs[:8])
                                      if ifd is not None]
    except OSError:
        return None
    best = None
    for ifd in candidates:
        w, h, kind = _value(ifd.get(0x0100)), _value(ifd.get(0x0101)), _value(ifd.get(0x00FE, 0))
        if isinstance(w, int) and isinstance(h, int) and kind == 0:
            if best is None or w * h > best[0] * best[1]:
                best = (w, h)
    return best


# ─── The full decode (LibRaw) ─────────────────────────────────

class _Processed(ctypes.Structure):
    """libraw_processed_image_t"""
    _fields_ = [('type', ctypes.c_int), ('height', ctypes.c_ushort), ('width', ctypes.c_ushort),
                ('colors', ctypes.c_ushort), ('bits', ctypes.c_ushort),
                ('data_size', ctypes.c_uint), ('data', ctypes.c_ubyte * 1)]


_libraw: Optional[ctypes.CDLL] = None
_libraw_tried = False


def libraw() -> Optional[ctypes.CDLL]:
    """LibRaw's C library (the thread-safe build)."""
    global _libraw, _libraw_tried
    if _libraw_tried:
        return _libraw
    _libraw_tried = True
    names = ['libraw_r.so.25', 'libraw_r.so.24', 'libraw_r.so.23',
             ctypes.util.find_library('raw_r') or '', ctypes.util.find_library('raw') or '']
    if os.name == 'nt':
        names += ['libraw.dll']
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            _declare(lib)
        except (OSError, AttributeError) as exc:
            log.debug("LibRaw %s: %s", name, exc)
            continue
        _libraw = lib
        log.info("RAW decode: LibRaw %s (%s)", lib.libraw_version().decode(), name)
        return lib
    return None


def _declare(lib: ctypes.CDLL) -> None:
    vp = ctypes.c_void_p
    lib.libraw_version.restype = ctypes.c_char_p
    lib.libraw_init.restype = vp
    lib.libraw_init.argtypes = [ctypes.c_uint]
    lib.libraw_open_file.argtypes = [vp, ctypes.c_char_p]
    lib.libraw_unpack.argtypes = [vp]
    lib.libraw_dcraw_process.argtypes = [vp]
    lib.libraw_dcraw_make_mem_image.restype = ctypes.POINTER(_Processed)
    lib.libraw_dcraw_make_mem_image.argtypes = [vp, ctypes.POINTER(ctypes.c_int)]
    lib.libraw_dcraw_clear_mem.argtypes = [ctypes.POINTER(_Processed)]
    lib.libraw_close.argtypes = [vp]
    lib.libraw_strerror.restype = ctypes.c_char_p
    lib.libraw_strerror.argtypes = [ctypes.c_int]
    lib.libraw_get_cam_mul.restype = ctypes.c_float
    lib.libraw_get_cam_mul.argtypes = [vp, ctypes.c_int]
    lib.libraw_set_user_mul.argtypes = [vp, ctypes.c_int, ctypes.c_float]
    lib.libraw_set_output_bps.argtypes = [vp, ctypes.c_int]


def decoder() -> Optional[str]:
    """What decodes the sensor data on this system, for the self-test and the README."""
    lib = libraw()
    return f"LibRaw {lib.libraw_version().decode()}" if lib is not None else None


def decode(path: str) -> Optional[Image.Image]:
    """The photo developed from the sensor data with the camera's white balance, 8 bits per
    channel, turned upright by LibRaw. None when LibRaw isn't installed or can't read it.
    Takes a second or more for a big photo: call it from a worker thread (ctypes lets the
    other threads run meanwhile)."""
    lib = libraw()
    if lib is None:
        return None
    handle = lib.libraw_init(0)
    if not handle:
        return None
    processed = None
    try:
        def check(code: int, what: str) -> None:
            if code != 0:
                raise OSError(f"{what}: {lib.libraw_strerror(code).decode('utf-8', 'replace')}")

        check(lib.libraw_open_file(handle, os.fsencode(path)), "open")
        # the camera's white balance, as dcraw's -w does (use_camera_wb has no C setter)
        mul = [lib.libraw_get_cam_mul(handle, i) for i in range(4)]
        if mul[0] > 0 and mul[1] > 0 and mul[2] > 0:
            if mul[3] <= 0:
                mul[3] = mul[1]
            for i, value in enumerate(mul):
                lib.libraw_set_user_mul(handle, i, value)
        lib.libraw_set_output_bps(handle, 8)
        check(lib.libraw_unpack(handle), "unpack")
        check(lib.libraw_dcraw_process(handle), "process")
        err = ctypes.c_int(0)
        processed = lib.libraw_dcraw_make_mem_image(handle, ctypes.byref(err))
        if not processed or err.value:
            check(err.value or -1, "image")
        img = processed.contents
        if img.type != 2 or img.bits != 8 or img.colors not in (1, 3):     # 2 = bitmap
            raise OSError(f"unexpected output: type {img.type}, {img.colors}x{img.bits} bit")
        offset = _Processed.data.offset
        data = ctypes.string_at(ctypes.addressof(img) + offset, img.data_size)
        mode = 'RGB' if img.colors == 3 else 'L'
        image = Image.frombytes(mode, (img.width, img.height), data)
        return image.convert('RGB')
    except Exception as exc:      # noqa: BLE001
        log.warning("LibRaw could not decode %s: %s", path, exc)
        return None
    finally:
        if processed:
            lib.libraw_dcraw_clear_mem(processed)
        lib.libraw_close(handle)


# ─── A RAW as Spark Media shows it ────────────────────────────

def needs_decode(preview_size: Tuple[int, int], full: Optional[Tuple[int, int]]) -> bool:
    """The embedded preview is enough when it's (nearly) the photo's full size."""
    long_side = max(preview_size)
    if full:
        return long_side < 0.9 * max(full)
    return long_side < 3000
