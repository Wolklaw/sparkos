"""How tests/fixtures/*.heic and *.avif were made (once, on a developer machine; the files are
checked in because the SparkOS image and Fedora have no HEVC encoder):

    python -m venv /tmp/v && /tmp/v/bin/pip install pillow-heif   # Pillow 13, pillow-heif 1.8
    /tmp/v/bin/python tests/make_heif_fixtures.py

The picture is four coloured quarters, so a test can tell it decoded the right way up:
top left red, top right green, bottom left blue, bottom right white."""

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'fixtures')


def quarters(w: int = 96, h: int = 64) -> Image.Image:
    image = Image.new('RGB', (w, h))
    for (x, y), colour in (((0, 0), (220, 30, 40)), ((1, 0), (30, 200, 60)),
                           ((0, 1), (40, 60, 220)), ((1, 1), (245, 245, 245))):
        image.paste(colour, (x * w // 2, y * h // 2, (x + 1) * w // 2, (y + 1) * h // 2))
    return image


def exif(orientation: int = 1) -> bytes:
    data = Image.Exif()
    data[0x010F] = 'Spark'
    data[0x0110] = 'Spark Phone'
    data[0x0112] = orientation
    data[0x8769] = {0x9003: '2025:06:21 14:05:00'}
    return data.tobytes()


def main() -> int:
    import pillow_heif
    pillow_heif.register_heif_opener()
    os.makedirs(OUT, exist_ok=True)
    picture = quarters()
    picture.save(os.path.join(OUT, 'quarters.heic'), quality=90, exif=exif())
    # stored on its side, with "turn 90° clockwise to show" (an upright 64 x 96 photo)
    picture.rotate(90, expand=True).save(os.path.join(OUT, 'turned.heic'), quality=90,
                                         exif=exif(6))
    picture.save(os.path.join(OUT, 'quarters.avif'), quality=90, exif=exif())
    for name in sorted(os.listdir(OUT)):
        if name.endswith(('.heic', '.avif')):
            print(name, os.path.getsize(os.path.join(OUT, name)), 'bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
