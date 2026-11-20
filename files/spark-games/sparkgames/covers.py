"""Cover thumbnails: each launcher's art, cut once to the tile size with Pillow and kept in
~/.cache/spark-games/covers/. The grid never loads full-size art."""

import hashlib
import os
from typing import Optional

from PIL import Image, ImageOps

from .core import cache_dir, log


def thumb_path(src: str, width: int, height: int) -> Optional[str]:
    try:
        st = os.stat(src)
    except OSError:
        return None
    digest = hashlib.sha1(f'{src}|{st.st_mtime_ns}|{st.st_size}'.encode('utf-8',
                          'surrogateescape')).hexdigest()
    return os.path.join(cache_dir(), 'covers', f'{digest}-{width}x{height}.jpg')


def thumbnail(src: str, width: int, height: int) -> Optional[Image.Image]:
    """The cover cut to width x height (cropped to fill, centred). Cached; None if unreadable.
    Safe to call from a worker thread."""
    if not src:
        return None
    path = thumb_path(src, width, height)
    if path is None:
        return None
    if os.path.isfile(path):
        try:
            with Image.open(path) as cached:
                cached.load()
                return cached.copy()
        except OSError:
            pass
    try:
        with Image.open(src) as image:
            image.draft('RGB', (width * 2, height * 2))          # JPEG: decode smaller
            image = ImageOps.exif_transpose(image).convert('RGB')
            thumb = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        log.info("cover unreadable %s: %s", src, exc)
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        thumb.save(path, 'JPEG', quality=88)
    except OSError as exc:
        log.info("cover not cached %s: %s", path, exc)
    return thumb
