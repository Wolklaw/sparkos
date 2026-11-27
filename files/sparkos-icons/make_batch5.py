#!/usr/bin/env python3
"""Write batch 5: the icon names Spark apps and Spark Shell ask for that SparkOS had not drawn.

    python3 files/sparkos-icons/make_batch5.py

How the SVGs were first written. They are plain SVG: edit them by hand afterwards and don't run this
again unless you mean to start over (it overwrites).

  status/   system-shutdown, printer, printer-printing, dialog-information, dialog-question,
            dialog-warning, dialog-error, dialog-password (symbolic at 16, 22, 24; the five dialogs also
            in colour at 16, 22, 24 and scalable), plus aliases for the other names the tray asks for.
  apps/     utilities-terminal, system-software-install (tile at scalable, 22, 24, 16, and symbolic).

The 24 px files are the 22 px drawings with a 1 px margin. Symbolic glyphs are drawn on a 16 grid; the
22 px files carry the same glyph with a 3 px margin. Aliases are relative symbolic links.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(HERE, "SparkOS")
TILE, EDGE, MINT, MUTED, GOLD = "#141233", "#ece9ff", "#9be8b8", "#b3b0d2", "#f4c95d"
LILAC, SKY, MAG, CYAN = "#b9a6ff", "#8ec9ff", "#ff2e88", "#22d8ff"
STYLE = '  <style id="current-color-scheme">.ColorScheme-Text { color: #f1efff; }</style>'
NS = 'xmlns="http://www.w3.org/2000/svg"'

# Symbolic glyphs on a 16 grid: lists of (path, evenodd).
SYM = {
    "system-shutdown": [
        "M11.73 3.18 A6.5 6.5 0 1 1 4.27 3.18 L5.42 4.81 A4.5 4.5 0 1 0 10.58 4.81 Z", "M7 1 H9 V8 H7 Z"],
    "printer": [
        "M4 1 H12 V5 H4 Z M5 2 V4 H11 V2 Z", "M1 6 H15 V12 H12 V10 H4 V12 H1 Z", "M5 11 H11 V15 H5 Z"],
    "printer-printing": [
        "M4 1 H12 V5 H4 Z", "M1 6 H15 V12 H12 V10 H4 V12 H1 Z M11 7 H13 V8.5 H11 Z",
        "M5 11 H11 V15 H5 Z M6 12.5 H10 V13.5 H6 Z"],
    "dialog-information": [
        "M1 1 H15 V15 H1 Z M7 3.5 H9 V5.5 H7 Z M7 7 H9 V12.5 H7 Z"],
    "dialog-question": [
        "M1 1 H15 V15 H1 Z M5 3.5 H11 V8.5 H9 V10 H7 V7 H9 V5.5 H5 Z M7 11.5 H9 V13.5 H7 Z"],
    "dialog-warning": [
        "M8 1 L15.5 14.5 H0.5 Z M7 5.5 H9 V10 H7 Z M7 11 H9 V13 H7 Z"],
    "dialog-error": [
        "M5 1 H11 L15 5 V11 L11 15 H5 L1 11 V5 Z M6 4.6 L8 6.6 L10 4.6 L11.4 6 L9.4 8 L11.4 10 L10 11.4 "
        "L8 9.4 L6 11.4 L4.6 10 L6.6 8 L4.6 6 Z"],
    "dialog-password": [
        "M3 7 H13 V15 H3 Z M7.2 9.5 H8.8 V12.5 H7.2 Z",
        "M4.5 7 V4.5 A3.5 3.5 0 0 1 11.5 4.5 V7 H9.5 V4.5 A1.5 1.5 0 0 0 6.5 4.5 V7 Z"],
}
TITLES = {
    "system-shutdown": "Shut down", "printer": "Printer", "printer-printing": "Printer, printing",
    "dialog-information": "Information", "dialog-question": "Question", "dialog-warning": "Warning",
    "dialog-error": "Error", "dialog-password": "Password",
}
# The dialogs in colour: shape colour. The shape is path 0 (and the padlock's body); the rest are cut-outs or parts.
DIALOG_COLOUR = {"dialog-information": SKY, "dialog-question": LILAC, "dialog-warning": GOLD,
                 "dialog-error": MAG, "dialog-password": MINT}


def sym_svg(name, size):
    pre = {16: "", 22: '    <g transform="translate(3 3)">\n'}[size]
    lines = [f'<svg {NS} viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
             f"  <!-- {TITLES[name]}. Symbolic, drawn for {'16' if size == 16 else '22'} px. -->", STYLE]
    if size == 22:
        lines.append('  <g transform="translate(3 3)">')
    for d in SYM[name]:
        lines.append(f'  <path class="ColorScheme-Text" fill="currentColor" fill-rule="evenodd" d="{d}"/>')
    if size == 22:
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def dialog_svg(name, size):
    colour = DIALOG_COLOUR[name]
    scale, off, slip = {48: (3, 0, 2), 22: (1, 3, 1), 16: (1, 0, 1)}[size]
    parts = SYM[name]
    d = " ".join(parts)  # shapes and cut-outs share one evenodd path; the padlock's shackle is a plain part
    lines = [f'<svg {NS} viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
             f"  <!-- {TITLES[name]}, in colour, drawn on the 16 grid for {size} px. The slip is the only decoration. -->"]
    tf = f"translate({off} {off}) scale({scale})" if scale != 1 or off else ""
    s = slip / scale
    for dx, col in ((-s, MAG), (s, CYAN)):
        lines.append(f'  <path fill="{col}" fill-rule="evenodd" transform="translate({off + dx * scale:g} {off}) scale({scale})" d="{d}"/>')
    lines.append(f'  <path fill="{colour}" fill-rule="evenodd"{(" transform=%s" % chr(34) + tf + chr(34)) if tf else ""} d="{d}"/>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def chev(pts, col, w, dx=0):
    p = " ".join(f"{x + dx:g},{y:g}" for x, y in pts)
    return f'  <polyline points="{p}" fill="none" stroke="{col}" stroke-width="{w}"/>'


def tile(size, title):
    if size == 48:
        return [f'<svg {NS} viewBox="0 0 48 48" width="48" height="48">',
                f"  <!-- {title}. SparkOS icon theme, 48 grid. -->",
                f'  <rect x="4.5" y="4.5" width="39" height="39" rx="3" fill="{TILE}" stroke="{EDGE}" stroke-opacity="0.22"/>']
    r = {22: "2", 16: "1.5"}[size]
    wh = size - 1
    return [f'<svg {NS} viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
            f"  <!-- {title}, drawn for {size} px. -->",
            f'  <rect x="0.5" y="0.5" width="{wh}" height="{wh}" rx="{r}" fill="{TILE}" stroke="{EDGE}" stroke-opacity="0.22"/>']


def terminal(size):
    lines = tile(size, "Terminal")
    if size == 48:
        pts, w, s = [(12, 15), (22, 24), (12, 33)], 3, 2
        lines += [chev(pts, MAG, w, -s), chev(pts, CYAN, w, s), chev(pts, MINT, w),
                  f'  <rect x="25" y="31" width="12" height="3" fill="{MUTED}"/>']
    elif size == 22:
        pts = [(5.5, 6.5), (10.5, 11), (5.5, 15.5)]
        lines += [chev(pts, MAG, 1.5, -1), chev(pts, CYAN, 1.5, 1), chev(pts, MINT, 1.5),
                  f'  <rect x="12" y="14" width="6" height="2" fill="{MUTED}"/>']
    else:
        pts = [(4, 4.5), (8, 8), (4, 11.5)]
        lines += [chev(pts, MAG, 1.5, -1), chev(pts, CYAN, 1.5, 1), chev(pts, MINT, 1.5),
                  f'  <rect x="9" y="11" width="4" height="1" fill="{MUTED}"/>']
    return lines + ["</svg>"]


ARROW = {48: "M22 9 H26 V19 H31 L24 27 L17 19 H22 Z", 22: "M9.5 3.5 H12.5 V8 H16 L11 13 L6 8 H9.5 Z",
         16: "M6.5 2.5 H9.5 V6.5 H12 L8 10.5 L4 6.5 H6.5 Z"}
TRAY = {48: ("12,27 12,38 36,38 36,27", 3), 22: ("4.5,12 4.5,17.5 17.5,17.5 17.5,12", 1),
        16: ("3.5,10 3.5,13.5 12.5,13.5 12.5,10", 1)}


def install(size):
    lines = tile(size, "Software install")
    s = {48: 2, 22: 1, 16: 1}[size]
    d = ARROW[size]
    pts, w = TRAY[size]
    lines.append(f'  <polyline points="{pts}" fill="none" stroke="{MINT}" stroke-width="{w}"/>')
    lines.append(f'  <path d="{d}" fill="{MAG}" transform="translate({-s} 0)"/>')
    lines.append(f'  <path d="{d}" fill="{CYAN}" transform="translate({s} 0)"/>')
    lines.append(f'  <path d="{d}" fill="{GOLD}"/>')
    return lines + ["</svg>"]


APP_SYM = {
    "utilities-terminal": ("Terminal", [
        "M1 2 H15 V14 H1 Z M2 4 V13 H14 V4 Z", "M4 6 H5.5 L8.5 8.5 L5.5 11 H4 L6.5 8.5 Z", "M9 10 H12 V11 H9 Z"]),
    "system-software-install": ("Software install", [
        "M6.5 1 H9.5 V6 H12.5 L8 10.5 L3.5 6 H6.5 Z", "M2 9 H3.5 V13 H12.5 V9 H14 V14.5 H2 Z"]),
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def as24(text):
    a = text.splitlines()
    a[0] = f'<svg {NS} viewBox="-1 -1 24 24" width="24" height="24">'
    a[1] = a[1].split(",")[0].split(". Symbolic")[0].rstrip(".") + ", drawn for 22 px, shown at 24 with a 1 px margin. -->"
    if a[1].startswith("  <!--") is False:
        a[1] = "  " + a[1]
    return "\n".join(a) + "\n"


def link(target, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.lexists(path):
        os.remove(path)
    os.symlink(target, path)


def main():
    st = os.path.join(T, "status")
    for name in SYM:
        write(f"{st}/symbolic/{name}-symbolic.svg", sym_svg(name, 16))
        t22 = sym_svg(name, 22)
        write(f"{st}/22/{name}-symbolic.svg", t22)
        write(f"{st}/24/{name}-symbolic.svg", as24(t22))
        if name in DIALOG_COLOUR:
            write(f"{st}/scalable/{name}.svg", dialog_svg(name, 48))
            c22 = dialog_svg(name, 22)
            write(f"{st}/22/{name}.svg", c22)
            write(f"{st}/24/{name}.svg", as24(c22))
            write(f"{st}/16/{name}.svg", dialog_svg(name, 16))
            link(f"../symbolic/{name}-symbolic.svg", f"{st}/16/{name}-symbolic.svg")
        else:
            for d in ("22", "24"):
                link(f"{name}-symbolic.svg", f"{st}/{d}/{name}.svg")
            link(f"../symbolic/{name}-symbolic.svg", f"{st}/16/{name}.svg")
    # aliases: the tray asks for these names; they are the same drawing as an existing one
    for alias, target in (("network-wireless-disabled", "network-wireless-off"),
                          ("network-wireless-offline", "network-wireless-off"),
                          ("battery-full-charging", "battery-100-charging")):
        link(f"{target}-symbolic.svg", f"{st}/symbolic/{alias}-symbolic.svg")
        for d in ("22", "24"):
            link(f"{target}-symbolic.svg", f"{st}/{d}/{alias}.svg")
            link(f"{target}-symbolic.svg", f"{st}/{d}/{alias}-symbolic.svg")
        link(f"../symbolic/{target}-symbolic.svg", f"{st}/16/{alias}.svg")
        link(f"../symbolic/{target}-symbolic.svg", f"{st}/16/{alias}-symbolic.svg")
    # app tiles
    for name, fn in (("utilities-terminal", terminal), ("system-software-install", install)):
        for d, size in (("scalable", 48), ("22", 22), ("16", 16)):
            write(f"{T}/apps/{d}/{name}.svg", "\n".join(fn(size)) + "\n")
        write(f"{T}/apps/24/{name}.svg", as24("\n".join(fn(22)) + "\n"))
        title, parts = APP_SYM[name]
        body = [f'<svg {NS} viewBox="0 0 16 16" width="16" height="16">',
                f"  <!-- {title}, symbolic. -->", STYLE]
        body += [f'  <path class="ColorScheme-Text" fill="currentColor" fill-rule="evenodd" d="{d}"/>' for d in parts]
        write(f"{T}/apps/symbolic/{name}-symbolic.svg", "\n".join(body + ["</svg>"]) + "\n")
    print("batch 5 written")


if __name__ == "__main__":
    main()
