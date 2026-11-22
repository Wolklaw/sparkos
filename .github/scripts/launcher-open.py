#!/usr/bin/env python3
"""Did Spark Launcher open? Compares two QEMU screenshots (PNG) of the test VM, taken before
and after pressing Meta, and counts the pixels in the launcher's background colour (#04090b,
files/spark-launcher/package/contents/code/theme.js). The open launcher covers at least
640x520 of the screen, nearly all of it that colour; nothing else on the SparkOS desktop is.

    launcher-open.py before.png after.png [min-new-pixels]

Exit 0 if at least min-new-pixels (default 150000) more pixels have the colour after than
before. Standard library only (QEMU writes plain 8-bit RGB or RGBA PNGs)."""

import struct
import sys
import zlib

BG = (0x04, 0x09, 0x0b)


def pixels(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit(f"{path}: not a PNG")
    pos, idat, width = 8, b'', 0
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            width, height, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', body)
            if depth != 8 or color not in (2, 6) or interlace:
                raise SystemExit(f"{path}: only 8-bit RGB/RGBA, not interlaced")
            bpp = 3 if color == 2 else 4
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * bpp
    prev = bytearray(stride)
    count = 0
    i = 0
    for _ in range(height):
        kind = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        for x in range(0, stride, bpp):
            if abs(line[x] - BG[0]) <= 2 and abs(line[x + 1] - BG[1]) <= 2 and abs(line[x + 2] - BG[2]) <= 2:
                count += 1
        prev = line
    return count, width, height


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    need = int(sys.argv[3]) if len(sys.argv) > 3 else 150000
    before, w, h = pixels(sys.argv[1])
    after, _, _ = pixels(sys.argv[2])
    print(f"screen {w}x{h}: launcher colour {before} px before, {after} px after (need +{need})")
    return 0 if after - before >= need else 1


if __name__ == '__main__':
    sys.exit(main())
