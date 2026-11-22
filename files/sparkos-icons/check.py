#!/usr/bin/env python3
"""Check the SparkOS icon theme and draw a contact sheet of it.

    python3 files/sparkos-icons/check.py                    # checks only
    python3 files/sparkos-icons/check.py --sheet out.png    # checks, then the contact sheet

Checks: index.theme parses, every directory it lists exists (and has a section), every SVG
parses as XML with an <svg> root and a viewBox, every link stays inside the theme, each 24 px
file is the 22 px drawing with a 1 px margin, and every icon renders at 16, 22, 32, 48 and
256 px with rsvg-convert (ImageMagick's librsvg reader if rsvg-convert is missing) to a
non-empty picture.

The contact sheet has one row per icon and, for each size, the file the theme gives at that
size, on the dark background and on a light one. It needs Pillow.
"""
import argparse
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

THEME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SparkOS")
CHECK_SIZES = (16, 22, 32, 48, 256)
SHEET_SIZES = (16, 22, 24, 32, 48, 128)
DARK, LIGHT = (10, 9, 25), (246, 244, 255)
SVG_NS = "{http://www.w3.org/2000/svg}"

errors = []


def fail(msg):
    errors.append(msg)
    print("FAIL", msg)


def read_index():
    cp = configparser.ConfigParser(interpolation=None, strict=True)
    cp.optionxform = str
    with open(os.path.join(THEME, "index.theme"), encoding="utf-8") as f:
        cp.read_file(f)
    head = cp["Icon Theme"]
    for key in ("Name", "Comment", "Inherits", "Directories"):
        if key not in head:
            fail(f"index.theme: [Icon Theme] has no {key}")
    dirs = [d for d in head.get("Directories", "").split(",") if d]
    out = {}
    for d in dirs:
        if not os.path.isdir(os.path.join(THEME, d)):
            fail(f"index.theme lists {d}, which doesn't exist")
        if d not in cp:
            fail(f"index.theme lists {d} but has no [{d}] section")
            continue
        sec = cp[d]
        size = int(sec["Size"])
        kind = sec.get("Type", "Threshold")
        out[d] = (size, kind, int(sec.get("MinSize", size)), int(sec.get("MaxSize", size)))
    on_disk = {os.path.relpath(r, THEME) for r, _, fs in os.walk(THEME) if any(f.endswith(".svg") for f in fs)}
    for d in sorted(on_disk - set(dirs)):
        fail(f"{d} has icons but index.theme doesn't list it")
    return out


def check_svgs():
    for root, _, files in os.walk(THEME):
        for name in sorted(files):
            if not name.endswith(".svg"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, THEME)
            if os.path.islink(path):
                target = os.path.realpath(path)
                if not target.startswith(THEME + os.sep) or not os.path.exists(target):
                    fail(f"{rel}: link points outside the theme or nowhere")
                continue
            try:
                svg = ET.parse(path).getroot()
            except ET.ParseError as e:
                fail(f"{rel}: not valid XML ({e})")
                continue
            if svg.tag != SVG_NS + "svg" or "viewBox" not in svg.attrib:
                fail(f"{rel}: root must be <svg> with a viewBox")
            if name.endswith("-symbolic.svg") and "ColorScheme-Text" not in open(path, encoding="utf-8").read():
                fail(f"{rel}: symbolic icons use the ColorScheme-Text class")
    # 24 px = the 22 px drawing with a 1 px margin (only the first two lines differ)
    for ctx in os.listdir(THEME):
        d22, d24 = os.path.join(THEME, ctx, "22"), os.path.join(THEME, ctx, "24")
        if not os.path.isdir(d22):
            continue
        for name in os.listdir(d22):
            p22, p24 = os.path.join(d22, name), os.path.join(d24, name)
            if os.path.islink(p22):
                continue
            if not os.path.exists(p24):
                fail(f"{ctx}/24/{name} missing")
                continue
            a = open(p22, encoding="utf-8").read().splitlines()[2:]
            b = open(p24, encoding="utf-8").read().splitlines()[2:]
            if a != b:
                fail(f"{ctx}/24/{name} differs from {ctx}/22/{name} (copy the 22 px drawing again)")


def icon_names():
    names = set()
    for root, _, files in os.walk(THEME):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith(".svg") and not os.path.islink(p):
                names.add(f[:-4])
    order = ["preferences-system", "steam", "application-x-executable", "folder", "user-trash", "user-trash-full"]
    rest = sorted(n for n in names if n not in order and not n.endswith("-symbolic"))
    sym = sorted(n for n in names if n.endswith("-symbolic"))
    return [n for n in order if n in names] + rest + sym


def lookup(dirs, name, size):
    """The file the theme gives for name at size (freedesktop lookup, scale 1)."""
    best, best_dist = None, None
    for d, (s, kind, lo, hi) in dirs.items():
        path = os.path.join(THEME, d, name + ".svg")
        if not os.path.exists(path):
            continue
        if kind == "Fixed":
            dist = abs(s - size)
        elif kind == "Scalable":
            dist = 0 if lo <= size <= hi else min(abs(lo - size), abs(hi - size))
        else:
            dist = abs(s - size)
        if dist == 0 and kind == "Fixed":
            return path
        if best is None or dist < best_dist or (dist == best_dist and kind == "Fixed"):
            best, best_dist = path, dist
    return best


def render(svg, size, out):
    if shutil.which("rsvg-convert"):
        cmd = ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", out, svg]
    else:
        # render at the target size (not drawn small and enlarged): density from the SVG's width
        width = float(ET.parse(svg).getroot().get("width", "16"))
        cmd = ["magick", "-background", "none", "-density", str(96 * size / width), f"rsvg:{svg}",
               "-resize", f"{size}x{size}!", out]
    subprocess.run(cmd, check=True, capture_output=True)


def check_renders(dirs, tmp):
    for name in icon_names():
        for size in CHECK_SIZES:
            path = lookup(dirs, name, size)
            out = os.path.join(tmp, f"{name}-{size}.png")
            try:
                render(path, size, out)
            except subprocess.CalledProcessError as e:
                fail(f"{name} at {size}: render failed: {e.stderr.decode(errors='replace').strip()}")
                continue
            if not os.path.getsize(out):
                fail(f"{name} at {size}: empty picture")
                continue
            try:
                from PIL import Image
            except ImportError:
                continue
            im = Image.open(out).convert("RGBA")
            if im.size != (size, size) or im.getchannel("A").getextrema()[1] == 0:
                fail(f"{name} at {size}: wrong size or fully transparent")


def sheet(dirs, tmp, out_path, zoom):
    from PIL import Image, ImageDraw
    names = icon_names()
    pad, label_w = 12, 230
    col_w = [s + pad for s in SHEET_SIZES]
    half = sum(col_w) + pad
    row_h = [max(SHEET_SIZES) + pad if not n.endswith("-symbolic") else 48 + pad for n in names]
    W, H = label_w + 2 * half, 28 + sum(row_h)
    img = Image.new("RGB", (W, H), DARK)
    img.paste(LIGHT, (label_w + half, 0, W, H))
    draw = ImageDraw.Draw(img)
    x = label_w + pad
    for side, fg in ((0, (179, 176, 210)), (half, (60, 58, 90))):
        cx = x + side
        for s, w in zip(SHEET_SIZES, col_w):
            draw.text((cx, 8), str(s), fill=fg)
            cx += w
    y = 28
    for name, h in zip(names, row_h):
        draw.text((8, y + 4), name, fill=(241, 239, 255))
        for side in (0, half):
            cx = x + side
            for s, w in zip(SHEET_SIZES, col_w):
                if name.endswith("-symbolic") and s > 48:
                    cx += w
                    continue
                path = lookup(dirs, name, s)
                png = os.path.join(tmp, f"sheet-{name}-{s}.png")
                src = path
                if name.endswith("-symbolic") and side:
                    # on the light side, show the symbolic icon in dark text colour, as Plasma would
                    src = os.path.join(tmp, f"{name}-light.svg")
                    with open(path, encoding="utf-8") as f:
                        open(src, "w", encoding="utf-8").write(f.read().replace("#f1efff", "#120f2e"))
                render(src, s, png)
                icon = Image.open(png).convert("RGBA")
                img.paste(icon, (cx, y), icon)
                cx += w
        y += h
    if zoom > 1:
        img = img.resize((W * zoom, H * zoom), Image.NEAREST)
    img.save(out_path)
    print("contact sheet:", out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", help="write a contact sheet PNG here")
    ap.add_argument("--zoom", type=int, default=1, help="enlarge the sheet (nearest neighbour)")
    args = ap.parse_args()
    dirs = read_index()
    check_svgs()
    with tempfile.TemporaryDirectory() as tmp:
        check_renders(dirs, tmp)
        if args.sheet and not errors:
            sheet(dirs, tmp, args.sheet, args.zoom)
    if errors:
        print(f"{len(errors)} problem(s)")
        return 1
    print(f"OK: {len(icon_names())} icons, {len(dirs)} directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
