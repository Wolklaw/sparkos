#!/usr/bin/env python3
"""Draw the SparkOS cursor theme: XCursor files from the SVGs in cursors/src.

    python3 files/sparkos-icons/cursors/make_cursors.py OUT_DIR       # OUT_DIR/cursors/..., index.theme
    python3 files/sparkos-icons/cursors/make_cursors.py OUT_DIR --sheet docs/cursors.png

Each SVG in src/ is one shape on a 32 x 32 grid; its hotspot is the data-hotspot="x y" attribute on
the root. The Xcursor files are written here (header, table of contents, ARGB images, little
endian) at 24, 32, 48, 64 and 96 px. wait.svg and progress.svg hold a ring of ticks (ids t0..t7) and
become 8-frame animations. Every other name (CSS, legacy X11 and the hash names Breeze ships) is a
link to one of the shapes, made here, because the repository doesn't keep symlinks.

Needs python3-gobject with librsvg (gi Rsvg) and pycairo; the sheet also needs Pillow.
"""
import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
SIZES = (24, 32, 48, 64, 96)
FRAMES, DELAY_MS = 8, 90
ANIMATED = ("wait", "progress")
MAGENTA, CYAN = "#ff2e88", "#22d8ff"

# name -> the shape (file in src/) that draws it. Shapes themselves are not listed.
ALIASES = {
    # CSS / cursor-shape-v1 names
    "left_ptr": "default", "arrow": "default", "top_left_arrow": "default", "center_ptr": "default",
    "right_ptr": "default", "up-arrow": "default", "down-arrow": "default", "left-arrow": "default",
    "right-arrow": "default", "wayland-cursor": "default", "dnd-none": "default", "move": "grabbing",
    "dnd-move": "grabbing", "closedhand": "grabbing", "fcf21c00b30f7e3f83fe0dfd12e71cff": "grabbing",
    "4498f0e0c1937ffe01fd06f973665830": "grabbing", "9081237383d90e509aa00f00170e968f": "grabbing",
    "openhand": "grab", "hand": "pointer", "hand1": "pointer", "hand2": "pointer",
    "pointing_hand": "pointer", "9d800788f1b08800ae810202380a0822": "pointer",
    "e29285e634086352946a0e7090d73106": "pointer",
    "whats_this": "help", "question_arrow": "help", "left_ptr_help": "help", "dnd-ask": "context-menu",
    "5c6cd98b3f3ebcb1f9c7f1c204630408": "help", "d9ce0ab605698f320427677b458ad60b": "help",
    "dnd-copy": "copy", "1081e37283d90000800003c07f3ef6bf": "copy",
    "6407b0e94181790501fd1e167b474872": "copy", "b66166c04f8c3109214a4fbd64a50fc8": "copy",
    "link": "alias", "dnd-link": "alias", "3085a0e285430894940527032f8b26df": "alias",
    "640fb0e74195791501fd1ed57b41487f": "alias", "a2a266d0498c3104214a47bd64ab0fc8": "alias",
    "dnd-no-drop": "no-drop", "forbidden": "not-allowed", "crossed_circle": "not-allowed",
    "circle": "not-allowed", "03b6e0fcb3499374a867c041f52298f0": "not-allowed", "pirate": "x-cursor",
    "X_cursor": "x-cursor", "ibeam": "text", "xterm": "text", "cross": "crosshair", "tcross": "crosshair",
    "cross_reverse": "crosshair", "diamond_cross": "crosshair", "color-picker": "crosshair",
    "plus": "cell", "draft": "pencil",
    "fleur": "all-resize", "all-scroll": "all-resize", "size_all": "all-resize",
    "watch": "wait", "half-busy": "progress", "left_ptr_watch": "progress",
    "00000000000000020006000e7e9ffc3f": "progress", "08e8e1c95fe2fc01f976f1e063a24ccd": "progress",
    "3ecb610c1bf2410f44200f48c40d3599": "progress",
    # resize: sides and corners
    "e-resize": "size_hor", "w-resize": "size_hor", "ew-resize": "size_hor", "left_side": "size_hor",
    "right_side": "size_hor", "h_double_arrow": "size_hor", "sb_h_double_arrow": "size_hor",
    "size-hor": "size_hor",
    "n-resize": "size_ver", "s-resize": "size_ver", "ns-resize": "size_ver", "top_side": "size_ver",
    "bottom_side": "size_ver", "v_double_arrow": "size_ver", "sb_v_double_arrow": "size_ver",
    "size-ver": "size_ver", "00008160000006810000408080010102": "size_ver",
    "nw-resize": "size_fdiag", "se-resize": "size_fdiag", "nwse-resize": "size_fdiag",
    "top_left_corner": "size_fdiag", "bottom_right_corner": "size_fdiag", "bd_double_arrow": "size_fdiag",
    "size-fdiag": "size_fdiag",
    "ne-resize": "size_bdiag", "sw-resize": "size_bdiag", "nesw-resize": "size_bdiag",
    "top_right_corner": "size_bdiag", "bottom_left_corner": "size_bdiag", "fd_double_arrow": "size_bdiag",
    "size-bdiag": "size_bdiag",
    "split_h": "col-resize", "split_v": "row-resize",
    "sb_left_arrow": "size_hor", "sb_right_arrow": "size_hor", "sb_up_arrow": "size_ver",
    "sb_down_arrow": "size_ver",
}

# Every name a compositor, GTK, Qt, Chromium/Firefox, X11 or wp-cursor-shape-v1 can ask for, plus
# every file Breeze and Adwaita ship. check.py fails if one is missing from the output.
REQUIRED = """default context-menu help pointer progress wait cell crosshair text vertical-text alias copy
 move no-drop not-allowed grab grabbing e-resize n-resize ne-resize nw-resize s-resize se-resize
 sw-resize w-resize ew-resize ns-resize nesw-resize nwse-resize col-resize row-resize all-scroll
 zoom-in zoom-out dnd-ask all-resize left_ptr xterm hand1 hand2 watch left_ptr_watch fleur
 sb_h_double_arrow sb_v_double_arrow top_left_corner top_right_corner bottom_left_corner
 bottom_right_corner top_side bottom_side left_side right_side question_arrow X_cursor pirate
 crossed_circle plus size_hor size_ver size_fdiag size_bdiag openhand closedhand pointing_hand ibeam
 split_h split_v arrow top_left_arrow cross tcross dnd-move dnd-copy dnd-link dnd-none dnd-no-drop
 forbidden link whats_this left_ptr_help half-busy circle color-picker pencil draft h_double_arrow
 v_double_arrow bd_double_arrow fd_double_arrow size_all center_ptr right_ptr
 00000000000000020006000e7e9ffc3f 00008160000006810000408080010102 03b6e0fcb3499374a867c041f52298f0
 08e8e1c95fe2fc01f976f1e063a24ccd 1081e37283d90000800003c07f3ef6bf 3085a0e285430894940527032f8b26df
 3ecb610c1bf2410f44200f48c40d3599 4498f0e0c1937ffe01fd06f973665830 5c6cd98b3f3ebcb1f9c7f1c204630408
 640fb0e74195791501fd1ed57b41487f 6407b0e94181790501fd1e167b474872 9081237383d90e509aa00f00170e968f
 9d800788f1b08800ae810202380a0822 a2a266d0498c3104214a47bd64ab0fc8 b66166c04f8c3109214a4fbd64a50fc8
 d9ce0ab605698f320427677b458ad60b e29285e634086352946a0e7090d73106 fcf21c00b30f7e3f83fe0dfd12e71cff
""".split()


def shapes():
    return sorted(f[:-4] for f in os.listdir(SRC) if f.endswith(".svg"))


def render(svg_text, size):
    """The SVG at size x size as premultiplied ARGB32 bytes (cairo's order, little endian)."""
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    handle = Rsvg.Handle.new_from_data(svg_text.encode("utf-8"))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surf)
    ok = handle.render_document(ctx, _rect(size))
    if not ok:
        raise RuntimeError("rsvg could not render")
    surf.flush()
    return bytes(surf.get_data())


def _rect(size):
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    r = Rsvg.Rectangle()
    r.x = r.y = 0
    r.width = r.height = size
    return r


def hotspot(svg_text):
    m = re.search(r'data-hotspot="(\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"', svg_text)
    if not m:
        raise ValueError("no data-hotspot")
    return float(m.group(1)), float(m.group(2))


def frame_svg(text, i):
    """Frame i of a busy shape: tick i magenta, the one behind it cyan, the rest muted."""
    for tick, colour in ((i, MAGENTA), ((i - 1) % FRAMES, CYAN)):
        text = re.sub(r'(<rect id="t%d"[^>]*?fill=")[^"]*(")' % tick, r"\g<1>%s\g<2>" % colour, text)
    return text


def xcursor(images):
    """images: list of (nominal_size, width, height, xhot, yhot, delay_ms, argb_bytes)."""
    n = len(images)
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, n)
    pos = 16 + 12 * n
    toc, body = b"", b""
    for nominal, w, h, xh, yh, delay, px in images:
        toc += struct.pack("<III", 0xFFFD0002, nominal, pos + len(body))
        body += struct.pack("<IIIIIIIII", 36, 0xFFFD0002, nominal, 1, w, h, xh, yh, delay) + px
    return head + toc + body


def build_shape(name):
    text = open(os.path.join(SRC, name + ".svg"), encoding="utf-8").read()
    hx, hy = hotspot(text)
    images = []
    for size in SIZES:
        xh, yh = int(round(hx * size / 32)), int(round(hy * size / 32))
        if name in ANIMATED:
            for i in range(FRAMES):
                images.append((size, size, size, xh, yh, DELAY_MS, render(frame_svg(text, i), size)))
        else:
            images.append((size, size, size, xh, yh, 0, render(text, size)))
    return xcursor(images)


INDEX = """[Icon Theme]
Name=SparkOS cursors
Name[fr]=Curseurs SparkOS
Comment=SparkOS's own mouse pointers: dark body, light edge, straight cuts.
Comment[fr]=Les pointeurs de souris de SparkOS : corps sombre, bord clair, coupes droites.
"""


def build(out):
    cur = os.path.join(out, "cursors")
    os.makedirs(cur, exist_ok=True)
    for name in shapes():
        with open(os.path.join(cur, name), "wb") as f:
            f.write(build_shape(name))
    for name, target in ALIASES.items():
        if target not in shapes():
            raise SystemExit(f"{name} -> {target}: no such shape")
        dest = os.path.join(cur, name)
        if os.path.lexists(dest):
            os.remove(dest)
        os.symlink(target, dest)
    with open(os.path.join(out, "index.theme"), "w", encoding="utf-8") as f:
        f.write(INDEX)
    missing = [n for n in REQUIRED if not os.path.lexists(os.path.join(cur, n))]
    if missing:
        raise SystemExit("cursor names with no file: " + " ".join(missing))
    print(f"SparkOS cursors: {len(shapes())} shapes, {len(ALIASES)} names, in {cur}")


def read_xcursor(path):
    """Parse an Xcursor file: [(nominal, w, h, xhot, yhot, delay, pixels)]. Raises on a bad file."""
    data = open(path, "rb").read()
    magic, hsize, ver, n = struct.unpack_from("<4sIII", data, 0)
    if magic != b"Xcur" or hsize != 16 or n < 1:
        raise ValueError("bad header")
    out = []
    for i in range(n):
        typ, sub, pos = struct.unpack_from("<III", data, 16 + 12 * i)
        if typ != 0xFFFD0002:
            raise ValueError("not an image chunk")
        cs, ct, cn, cv, w, h, xh, yh, delay = struct.unpack_from("<IIIIIIIII", data, pos)
        if cs != 36 or ct != typ or cn != sub or w != sub or h != sub or not (0 <= xh < w and 0 <= yh < h):
            raise ValueError("bad image chunk")
        px = data[pos + 36: pos + 36 + 4 * w * h]
        if len(px) != 4 * w * h or not any(px[3::4]):
            raise ValueError("short or empty image")
        out.append((sub, w, h, xh, yh, delay, px))
    return out


def sheet(out, png, zoom=1):
    from PIL import Image, ImageDraw
    cur = os.path.join(out, "cursors")
    names = shapes()
    cell, cols = 96, 7
    rows = (len(names) + cols - 1) // cols
    W, H = cols * cell, rows * (cell + 14) + 8
    img = Image.new("RGB", (W * 2, H), (10, 9, 25))
    img.paste((246, 244, 255), (W, 0, W * 2, H))
    d = ImageDraw.Draw(img)
    for k, name in enumerate(names):
        frames = read_xcursor(os.path.join(cur, name))
        fr = [f for f in frames if f[0] == 48]
        for side, fg in ((0, (179, 176, 210)), (W, (60, 58, 90))):
            x, y = side + (k % cols) * cell, (k // cols) * (cell + 14) + 4
            _, w, h, xh, yh, _, px = fr[len(fr) // 2 if len(fr) > 1 else 0]
            im = Image.frombuffer("RGBA", (w, h), px, "raw", "BGRa", 0, 1)
            img.paste(im, (x + (cell - w) // 2, y + (cell - h) // 2), im)
            hx, hy = x + (cell - w) // 2 + xh, y + (cell - h) // 2 + yh
            d.rectangle((hx - 1, hy - 1, hx + 1, hy + 1), outline=(255, 46, 136))
            d.text((x + 4, y + cell - 2), name, fill=fg)
    if zoom > 1:
        img = img.resize((img.width * zoom, img.height * zoom), Image.NEAREST)
    img.save(png)
    print("contact sheet:", png)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--sheet")
    ap.add_argument("--zoom", type=int, default=1)
    a = ap.parse_args()
    build(a.out)
    if a.sheet:
        sheet(a.out, a.sheet, a.zoom)


if __name__ == "__main__":
    sys.exit(main())
