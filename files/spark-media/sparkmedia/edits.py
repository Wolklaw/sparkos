"""Photo edits: rotate, crop and auto-enhance, then save as a new file ("photo (edited).jpg")
or over the original when asked. The date taken and the camera stay in the saved file.

No Tk here: the viewer keeps an Edits and asks this module for the result."""

import os
from typing import Any, Dict, Optional, Tuple

from PIL import ExifTags, Image, ImageEnhance, ImageOps

from .core import log

Box = Tuple[int, int, int, int]

# (key, width, height); 0 means free. The ratio follows the photo: a portrait photo gets 3:4.
RATIOS = (('free', 0, 0), ('original', -1, -1), ('1:1', 1, 1), ('4:3', 4, 3), ('3:2', 3, 2),
          ('16:9', 16, 9))
# Formats Pillow writes and keeps EXIF in; everything else is saved as JPEG
SAVE_AS = {'JPEG': ('JPEG', '.jpg'), 'MPO': ('JPEG', '.jpg'), 'PNG': ('PNG', '.png'),
           'WEBP': ('WEBP', '.webp'), 'TIFF': ('TIFF', '.tif')}
KEEP_EXT = {'JPEG': ('.jpg', '.jpeg', '.jpe', '.jfif'), 'PNG': ('.png',), 'WEBP': ('.webp',),
            'TIFF': ('.tif', '.tiff')}


class Edits:
    """What's been done to a photo so far. crop is in the pixels of the rotated photo."""

    def __init__(self):
        self.rotation = 0                 # clockwise, 0/90/180/270
        self.crop: Optional[Box] = None
        self.enhance = False

    @property
    def changed(self) -> bool:
        return bool(self.rotation or self.crop or self.enhance)

    def rotate(self, size: Tuple[int, int], clockwise: bool = True) -> None:
        """Turn 90°, and turn the crop with the photo. size is the photo before any edit."""
        w, h = rotated_size(size, self.rotation)
        if self.crop:
            x0, y0, x1, y1 = self.crop
            self.crop = (h - y1, x0, h - y0, x1) if clockwise else (y0, w - x1, y1, w - x0)
        self.rotation = (self.rotation + (90 if clockwise else 270)) % 360


def rotated_size(size: Tuple[int, int], rotation: int) -> Tuple[int, int]:
    return (size[1], size[0]) if rotation % 180 else size


def rotate(image: Image.Image, rotation: int) -> Image.Image:
    method = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
              270: Image.Transpose.ROTATE_90}.get(rotation % 360)
    return image.transpose(method) if method is not None else image


def enhance(image: Image.Image) -> Image.Image:
    """Auto-enhance: stretch the tones to use the full range (ignoring the darkest and brightest
    half percent, keeping the colours' hue), then a little more colour."""
    alpha = image.getchannel('A') if image.mode == 'RGBA' else None
    rgb = image.convert('RGB')
    out = ImageOps.autocontrast(rgb, cutoff=(0.5, 0.5), preserve_tone=True)
    out = ImageEnhance.Color(out).enhance(1.12)
    if alpha is not None:
        out.putalpha(alpha)
    return out


def apply(image: Image.Image, edits: Edits, crop: bool = True) -> Image.Image:
    out = rotate(image, edits.rotation)
    if crop and edits.crop:
        out = out.crop(clamp_box(edits.crop, out.size))
    if edits.enhance:
        out = enhance(out)
    return out


# ─── Crop geometry ────────────────────────────────────────────

def ratio_for(key: str, size: Tuple[int, int]) -> float:
    """Width / height for a ratio key, turned to match the photo; 0 for free."""
    for name, rw, rh in RATIOS:
        if name == key:
            if rw == 0:
                return 0.0
            if rw < 0:
                return size[0] / size[1]
            ratio = rw / rh
            portrait = size[1] > size[0]
            return 1 / ratio if portrait and ratio != 1 else ratio
    return 0.0


def clamp_box(box: Box, size: Tuple[int, int]) -> Box:
    x0, y0, x1, y1 = box
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    x0, y0 = max(0, min(size[0] - 1, int(round(x0)))), max(0, min(size[1] - 1, int(round(y0))))
    x1, y1 = max(x0 + 1, min(size[0], int(round(x1)))), max(y0 + 1, min(size[1], int(round(y1))))
    return x0, y0, x1, y1


def largest_box(size: Tuple[int, int], ratio: float, center: Optional[Tuple[float, float]] = None
                ) -> Box:
    """The biggest box of this ratio that fits the photo, centred (on center if given)."""
    w, h = size
    if ratio <= 0:
        return 0, 0, w, h
    bw, bh = (w, w / ratio) if w / ratio <= h else (h * ratio, h)
    cx, cy = center if center else (w / 2, h / 2)
    x0 = max(0.0, min(w - bw, cx - bw / 2))
    y0 = max(0.0, min(h - bh, cy - bh / 2))
    return clamp_box((x0, y0, x0 + bw, y0 + bh), size)


def fit_ratio(box: Box, ratio: float, size: Tuple[int, int]) -> Box:
    """The box changed to the ratio, keeping its centre and area as far as the photo allows."""
    if ratio <= 0:
        return clamp_box(box, size)
    x0, y0, x1, y1 = box
    area = max(1.0, (x1 - x0) * (y1 - y0))
    bw = (area * ratio) ** 0.5
    bh = bw / ratio
    w, h = size
    if bw > w:
        bw, bh = w, w / ratio
    if bh > h:
        bw, bh = h * ratio, h
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    nx0 = max(0.0, min(w - bw, cx - bw / 2))
    ny0 = max(0.0, min(h - bh, cy - bh / 2))
    return clamp_box((nx0, ny0, nx0 + bw, ny0 + bh), size)


def drag_box(start: Box, handle: str, dx: float, dy: float, ratio: float,
             size: Tuple[int, int], minimum: int = 16) -> Box:
    """Move ('move') or resize (a handle: 'n', 'se', 'w', ...) a box by a drag, keeping a ratio
    when one is set, and inside the photo."""
    w, h = size
    x0, y0, x1, y1 = (float(v) for v in start)
    if handle == 'move':
        bw, bh = x1 - x0, y1 - y0
        nx0 = max(0.0, min(w - bw, x0 + dx))
        ny0 = max(0.0, min(h - bh, y0 + dy))
        return clamp_box((nx0, ny0, nx0 + bw, ny0 + bh), size)
    if 'w' in handle:
        x0 = min(x1 - minimum, max(0.0, x0 + dx))
    if 'e' in handle:
        x1 = max(x0 + minimum, min(float(w), x1 + dx))
    if 'n' in handle:
        y0 = min(y1 - minimum, max(0.0, y0 + dy))
    if 's' in handle:
        y1 = max(y0 + minimum, min(float(h), y1 + dy))
    if ratio > 0:
        bw, bh = x1 - x0, y1 - y0
        if handle in ('n', 's'):
            bw = bh * ratio
        elif handle in ('e', 'w'):
            bh = bw / ratio
        elif bw / bh > ratio:
            bw = bh * ratio
        else:
            bh = bw / ratio
        # the corner or edge opposite the handle stays put
        ax = x1 if 'w' in handle else x0
        ay = y1 if 'n' in handle else y0
        if handle in ('n', 's'):
            ax = (x0 + x1) / 2 - bw / 2
        if handle in ('e', 'w'):
            ay = (y0 + y1) / 2 - bh / 2
        # shrink to fit inside the photo, keeping the ratio
        limit_w = (ax if 'w' in handle else w - ax) if handle not in ('n', 's') else w
        limit_h = (ay if 'n' in handle else h - ay) if handle not in ('e', 'w') else h
        if bw > limit_w:
            bw, bh = limit_w, limit_w / ratio
        if bh > limit_h:
            bw, bh = limit_h * ratio, limit_h
        x0 = ax - bw if 'w' in handle else ax
        y0 = ay - bh if 'n' in handle else ay
        if handle in ('n', 's'):
            x0 = max(0.0, min(w - bw, x0))
        if handle in ('e', 'w'):
            y0 = max(0.0, min(h - bh, y0))
        x1, y1 = x0 + bw, y0 + bh
    return clamp_box((x0, y0, x1, y1), size)


# ─── Saving ───────────────────────────────────────────────────

def edited_path(path: str, ext: str) -> str:
    """'photo.jpg' -> 'photo (edited).jpg', then 'photo (edited 2).jpg', ... never an existing
    file."""
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0]
    from .text import tr
    word = tr('edit.suffix')
    for n in range(1, 10000):
        label = word if n == 1 else f"{word} {n}"
        candidate = os.path.join(folder, f"{stem} ({label}){ext}")
        if not os.path.exists(candidate):
            return candidate
    raise OSError("too many edited copies")


def output_format(source_format: Optional[str], path: str) -> Tuple[str, str]:
    """(Pillow format, extension) to save an edit of this photo in."""
    fmt, ext = SAVE_AS.get((source_format or '').upper(), ('JPEG', '.jpg'))
    own = os.path.splitext(path)[1].lower()
    if own in KEEP_EXT.get(fmt, ()):
        ext = own
    return fmt, ext


def can_replace(source_format: Optional[str], path: str) -> bool:
    """Replace only rewrites a file in its own format (JPEG, PNG, WebP, TIFF). HEIC, RAW, GIF
    and the rest get an edited JPEG copy instead."""
    fmt = (source_format or '').upper()
    return fmt in SAVE_AS and os.path.splitext(path)[1].lower() in KEEP_EXT.get(SAVE_AS[fmt][0], ())


def exif_for_save(exif: Optional[Image.Exif]) -> Optional[bytes]:
    """The original EXIF, upright (the pixels are already turned), without the old thumbnail."""
    if exif is None or not len(exif):
        return None
    out = Image.Exif()
    for tag, value in exif.items():
        if tag in (0x0112, 0x0201, 0x0202, 0x0103, 0x0111, 0x0117, 0x0100, 0x0101, 0x8825):
            continue          # orientation, thumbnail, strips and sizes, GPS (kept below)
        out[tag] = value
    for ifd in (ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo):
        try:
            data = exif.get_ifd(ifd)
        except Exception:      # noqa: BLE001
            data = {}
        if data:
            data = {k: v for k, v in data.items()
                    if k not in (0xA002, 0xA003, 0xA005)}  # pixel size, interop: no longer true
            if data:
                out[ifd] = data
    out[0x0112] = 1
    try:
        return out.tobytes()
    except Exception as exc:      # noqa: BLE001 - a broken tag must not stop the save
        log.warning("could not keep EXIF: %s", exc)
        return None


def save(image: Image.Image, path: str, source_format: Optional[str],
         exif: Optional[Image.Exif], icc: Optional[bytes] = None, replace: bool = False) -> str:
    """Save an edited image next to the original (or over it) and return where it went.
    Written to a temporary file first, so a failed save never damages the original."""
    fmt, ext = output_format(source_format, path)
    if replace and not can_replace(source_format, path):
        raise ValueError("this format can't be written back; save a copy instead")
    target = path if replace else edited_path(path, ext)
    if fmt == 'JPEG' and image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    params: Dict[str, Any] = {}
    data = exif_for_save(exif)
    if data:
        params['exif'] = data
    if icc:
        params['icc_profile'] = icc
    if fmt == 'JPEG':
        params.update(quality=95, optimize=True)
    elif fmt == 'WEBP':
        params.update(quality=95)
    elif fmt == 'TIFF':
        params.update(compression='tiff_lzw')
    tmp = f"{target}.{os.getpid()}.part"
    try:
        image.save(tmp, fmt, **params)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    log.info("saved edit of %s to %s", path, target)
    return target
