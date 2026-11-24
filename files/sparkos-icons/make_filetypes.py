#!/usr/bin/env python3
"""Write the file-type icons (batch 3) into SparkOS/mimetypes.

    python3 files/sparkos-icons/make_filetypes.py

This is how the SVGs were first written. They are plain, readable SVG: edit them by hand
afterwards and don't run this again unless you mean to start over (it overwrites).

Every file type is a page with a cut corner. The glyph is a list of rectangles and polygons;
`slip` parts get the magenta/cyan copies (2 px at 48, 1 px at 22 and 16), `flat` parts are drawn
on top with no slip (swatches, cut-outs). The 24 px files are the 22 px drawings with a 1 px margin.
Aliases are symbolic links named after the freedesktop / shared-mime-info icon names.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "SparkOS", "mimetypes")

PAGE, EDGE, FOLD = "#2c2870", "#4a45a6", "#4a45a6"
MINT, MUTED, GOLD = "#9be8b8", "#b3b0d2", "#f4c95d"
LILAC, PINK, SKY, CLAY = "#b9a6ff", "#ff9ebb", "#8ec9ff", "#f0a671"
MAG, CYAN = "#ff2e88", "#22d8ff"

# page outlines: (path of the page, path of the fold, slip offset)
FRAME = {
    48: ("M9 4 H29 L39 14 V44 H9 Z", "M29 4 V14 H39 Z", 2),
    22: ("M3.5 1.5 H13.5 L18.5 6.5 V20.5 H3.5 Z", "M13.5 1.5 V6.5 H18.5 Z", 1),
    16: ("M3.5 0.5 H9.5 L13.5 4.5 V15.5 H3.5 Z", "M9.5 0.5 V4.5 H13.5 Z", 1),
}


def R(x, y, w, h, fill=None):
    return ("rect", x, y, w, h, fill)


def P(d, fill=None, rule=False):
    return ("path", d, fill, rule)


def pix(rows, fill=None):
    """rows: [(y, [(x, w), ...]), ...] -> one 1 px high rect per run."""
    return [R(x, y, w, 1, fill) for y, runs in rows for x, w in runs]


def el(item, default):
    if item[0] == "rect":
        _, x, y, w, h, fill = item
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill or default}"/>'
    _, d, fill, rule = item
    extra = ' fill-rule="evenodd"' if rule else ""
    return f'<path d="{d}" fill="{fill or default}"{extra}/>'


def mirror(items, axis2, size=1):
    """Mirror rects across x = axis2 / 2."""
    out = []
    for it in items:
        _, x, y, w, h, f = it
        out.append(R(axis2 - (x + w), y, w, h, f))
    return out


# ----------------------------------------------------------------------------------------------
# glyphs: name -> {size: dict(color=..., slip=[...], flat=[...])}
# ----------------------------------------------------------------------------------------------
G = {}


def glyph(name, size, color, slip=(), flat=()):
    G.setdefault(name, {})[size] = dict(color=color, slip=list(slip), flat=list(flat))


# text: one mint line with the slip, muted lines under it
glyph("text-plain", 48, MINT, [R(13, 20, 22, 3)],
      [R(13, 26, 22, 3, MUTED), R(13, 32, 22, 3, MUTED), R(13, 38, 14, 3, MUTED)])
glyph("text-plain", 22, MINT, [R(6, 9, 10, 1)],
      [R(6, 11, 10, 1, MUTED), R(6, 13, 10, 1, MUTED), R(6, 15, 10, 1, MUTED), R(6, 17, 6, 1, MUTED)])
glyph("text-plain", 16, MINT, [R(5, 6, 6, 1)],
      [R(5, 8, 6, 1, MUTED), R(5, 10, 6, 1, MUTED), R(5, 12, 3, 1, MUTED)])

# python: indented lines
glyph("text-x-python", 48, MINT,
      [R(13, 20, 12, 3), R(19, 26, 16, 3), R(19, 32, 10, 3), R(13, 38, 14, 3)])
glyph("text-x-python", 22, MINT,
      [R(6, 9, 5, 1), R(8, 11, 7, 1), R(8, 13, 4, 1), R(6, 15, 6, 1)])
glyph("text-x-python", 16, MINT,
      [R(5, 6, 4, 1), R(7, 8, 5, 1), R(7, 10, 3, 1), R(5, 12, 5, 1)])

# script / shell: a prompt
glyph("text-x-script", 48, PINK,
      [P("M13 21 H17 L25 29 L17 37 H13 L21 29 Z"), R(27, 35, 8, 3)])
glyph("text-x-script", 22, PINK,
      pix([(9, [(6, 2)]), (10, [(7, 2)]), (11, [(8, 2)]), (12, [(9, 2)]), (13, [(8, 2)]), (14, [(7, 2)]),
           (15, [(6, 2)])]) + [R(12, 15, 4, 1)])
glyph("text-x-script", 16, PINK,
      pix([(6, [(5, 2)]), (7, [(6, 2)]), (8, [(7, 2)]), (9, [(6, 2)]), (10, [(5, 2)])]) + [R(8, 10, 3, 1)])

# JavaScript / TypeScript / JSON: braces
b48 = [R(16, 20, 4, 3), R(15, 23, 3, 5), R(13, 28, 3, 3), R(15, 31, 3, 5), R(16, 36, 4, 3)]
glyph("application-javascript", 48, GOLD, b48 + mirror(b48, 48))
b22 = [R(8, 9, 1, 1), R(7, 10, 1, 2), R(6, 12, 1, 1), R(7, 13, 1, 2), R(8, 15, 1, 1)]
glyph("application-javascript", 22, GOLD, b22 + mirror(b22, 22))
b16 = [R(6, 6, 1, 1), R(5, 7, 1, 2), R(4, 9, 1, 1), R(5, 10, 1, 2), R(6, 12, 1, 1)]
glyph("application-javascript", 16, GOLD, b16 + mirror(b16, 17))

# HTML / XML: angle brackets, the slip on the left one only (both touch at small sizes)
glyph("text-html", 48, CLAY, [P("M18 20 H22 L17 29.5 L22 39 H18 L13 29.5 Z")],
      [P("M30 20 H26 L31 29.5 L26 39 H30 L35 29.5 Z", CLAY)])
glyph("text-html", 22, CLAY,
      pix([(10, [(9, 1)]), (11, [(8, 1)]), (12, [(7, 1)]), (13, [(6, 1)]), (14, [(7, 1)]), (15, [(8, 1)]),
           (16, [(9, 1)])]),
      pix([(10, [(12, 1)]), (11, [(13, 1)]), (12, [(14, 1)]), (13, [(15, 1)]), (14, [(14, 1)]),
           (15, [(13, 1)]), (16, [(12, 1)])], CLAY))
glyph("text-html", 16, CLAY,
      pix([(7, [(7, 1)]), (8, [(6, 1)]), (9, [(5, 1)]), (10, [(6, 1)]), (11, [(7, 1)])]),
      pix([(7, [(9, 1)]), (8, [(10, 1)]), (9, [(11, 1)]), (10, [(10, 1)]), (11, [(9, 1)])], CLAY))

# CSS: a selector line, two property swatches
glyph("text-css", 48, SKY, [R(13, 20, 16, 3)],
      [R(13, 26, 5, 5, PINK), R(21, 27, 14, 3, MUTED), R(13, 34, 5, 5, GOLD), R(21, 35, 10, 3, MUTED)])
glyph("text-css", 22, SKY, [R(6, 9, 6, 1)],
      [R(6, 12, 3, 3, PINK), R(10, 13, 6, 1, MUTED), R(6, 16, 3, 3, GOLD), R(10, 17, 4, 1, MUTED)])
glyph("text-css", 16, SKY, [R(5, 6, 5, 1)],
      [R(5, 8, 2, 2, PINK), R(8, 9, 4, 1, MUTED), R(5, 11, 2, 2, GOLD), R(8, 12, 3, 1, MUTED)])

# C#: a hash
glyph("text-x-csharp", 48, LILAC,
      [R(19, 19, 3, 21), R(27, 19, 3, 21), R(13, 25, 22, 3), R(13, 32, 22, 3)])
glyph("text-x-csharp", 22, LILAC,
      [R(9, 9, 1, 9), R(13, 9, 1, 9), R(6, 12, 11, 1), R(6, 15, 11, 1)])
glyph("text-x-csharp", 16, LILAC,
      [R(7, 6, 1, 7), R(10, 6, 1, 7), R(5, 8, 7, 1), R(5, 11, 7, 1)])

# archive: a zipper with a pull
teeth48 = [R(21 if i % 2 == 0 else 24, 6 + 4 * i, 3, 2, MUTED) for i in range(6)]
glyph("package-x-generic", 48, GOLD, [R(20, 29, 8, 11)], teeth48 + [R(22, 33, 4, 3, PAGE)])
glyph("package-x-generic", 22, GOLD, [R(9, 13, 4, 5)],
      [R(10 if y % 2 == 0 else 11, y, 1, 1, MUTED) for y in range(2, 13)] + [R(10, 15, 2, 1, PAGE)])
glyph("package-x-generic", 16, GOLD, [R(7, 9, 4, 5)],
      [R(8 if y % 2 == 0 else 9, y, 1, 1, MUTED) for y in range(1, 9)] + [R(8, 11, 2, 1, PAGE)])

# image: mountains and a sun
glyph("image-x-generic", 48, SKY, [P("M13 40 V35 L20 28 L25 34 L29 30 L35 36 V40 Z")], [R(27, 20, 5, 5, GOLD)])
glyph("image-x-generic", 22, SKY, [P("M6 18 V15 L9 12 L11 14 L13 12 L16 15 V18 Z")], [R(13, 8, 2, 2, GOLD)])
glyph("image-x-generic", 16, SKY, [P("M5 13 V11 L7 9 L9 11 L10 10 L12 12 V13 Z")], [R(9, 6, 2, 2, GOLD)])

# audio: two beamed notes
glyph("audio-x-generic", 48, PINK,
      [R(19, 24, 3, 11), R(30, 21, 3, 11), P("M19 24 L33 21 V24 L19 27 Z"), R(14, 34, 8, 5), R(25, 31, 8, 5)])
glyph("audio-x-generic", 22, PINK,
      [R(8, 9, 6, 2), R(8, 11, 1, 5), R(13, 11, 1, 4), R(6, 16, 3, 2), R(11, 15, 3, 2)])
glyph("audio-x-generic", 16, PINK,
      [R(6, 6, 5, 1), R(6, 7, 1, 4), R(10, 7, 1, 3), R(4, 11, 3, 2), R(8, 10, 3, 2)])

# video: a screen with a play cut-out
glyph("video-x-generic", 48, LILAC, [R(13, 21, 22, 16)], [P("M21 25 V33 L28 29 Z", PAGE)])
glyph("video-x-generic", 22, LILAC, [R(6, 10, 10, 7)],
      [R(9, 11, 1, 5, PAGE), R(10, 12, 1, 3, PAGE), R(11, 13, 1, 1, PAGE)])
glyph("video-x-generic", 16, LILAC, [R(5, 7, 7, 6)], [R(7, 8, 1, 4, PAGE), R(8, 9, 1, 2, PAGE)])

# PDF: a heading, a line, and a clay band with the three letters
pdf_letters = [R(12, 35, 2, 6, PAGE), R(12, 35, 5, 2, PAGE), R(12, 38, 5, 2, PAGE), R(16, 36, 2, 3, PAGE),
               R(21, 35, 2, 6, PAGE), R(21, 35, 4, 2, PAGE), R(21, 39, 4, 2, PAGE), R(25, 36, 2, 4, PAGE),
               R(30, 35, 2, 6, PAGE), R(30, 35, 6, 2, PAGE), R(30, 38, 4, 2, PAGE)]
glyph("application-pdf", 48, CLAY, [R(13, 20, 16, 3)],
      [R(13, 26, 22, 2, MUTED), R(9, 32, 30, 12, CLAY)] + pdf_letters)
glyph("application-pdf", 22, CLAY, [R(6, 8, 8, 1)],
      [R(6, 10, 10, 1, MUTED), R(4, 13, 14, 7, CLAY), R(6, 15, 2, 3, PAGE), R(10, 15, 2, 3, PAGE),
       R(14, 15, 2, 3, PAGE)])
glyph("application-pdf", 16, CLAY, [R(5, 4, 5, 1)],
      [R(5, 6, 6, 1, MUTED), R(4, 10, 9, 5, CLAY), R(5, 11, 1, 3, PAGE), R(8, 11, 1, 3, PAGE),
       R(11, 11, 1, 3, PAGE)])

# office: word processing (a title block and paragraphs)
glyph("x-office-document", 48, SKY, [R(13, 20, 14, 5)],
      [R(13, 28, 22, 2, MUTED), R(13, 32, 22, 2, MUTED), R(13, 36, 22, 2, MUTED), R(13, 40, 12, 2, MUTED)])
glyph("x-office-document", 22, SKY, [R(6, 9, 7, 2)],
      [R(6, 12, 10, 1, MUTED), R(6, 14, 10, 1, MUTED), R(6, 16, 6, 1, MUTED)])
glyph("x-office-document", 16, SKY, [R(5, 6, 5, 2)],
      [R(5, 9, 6, 1, MUTED), R(5, 11, 6, 1, MUTED), R(5, 13, 3, 1, MUTED)])

# office: spreadsheet (a header row and a grid)
glyph("x-office-spreadsheet", 48, MINT, [R(13, 20, 22, 5)],
      [R(13, 30, 22, 2, MUTED), R(13, 35, 22, 2, MUTED), R(13, 40, 22, 2, MUTED),
       R(19, 25, 2, 17, MUTED), R(27, 25, 2, 17, MUTED)])
glyph("x-office-spreadsheet", 22, MINT, [R(6, 9, 10, 2)],
      [R(6, 13, 10, 1, MUTED), R(6, 16, 10, 1, MUTED), R(9, 11, 1, 7, MUTED), R(12, 11, 1, 7, MUTED)])
glyph("x-office-spreadsheet", 16, MINT, [R(5, 6, 7, 2)],
      [R(5, 10, 7, 1, MUTED), R(5, 13, 7, 1, MUTED), R(7, 8, 1, 6, MUTED), R(10, 8, 1, 6, MUTED)])

# office: presentation (a slide with bars on a stand)
glyph("x-office-presentation", 48, GOLD, [P("M13 21 H35 V35 H13 Z M16 24 V32 H32 V24 Z", rule=True)],
      [R(19, 28, 3, 4, GOLD), R(24, 26, 3, 6, GOLD), R(29, 24, 3, 8, GOLD),
       R(23, 35, 2, 5, MUTED), R(19, 40, 10, 2, MUTED)])
glyph("x-office-presentation", 22, GOLD, [P("M6 9 H16 V16 H6 Z M7 10 V15 H15 V10 Z", rule=True)],
      [R(8, 13, 1, 2, GOLD), R(10, 12, 1, 3, GOLD), R(12, 11, 1, 4, GOLD),
       R(10, 16, 2, 2, MUTED), R(8, 18, 6, 1, MUTED)])
glyph("x-office-presentation", 16, GOLD, [P("M5 6 H12 V12 H5 Z M6 7 V11 H11 V7 Z", rule=True)],
      [R(7, 9, 1, 2, GOLD), R(9, 8, 1, 3, GOLD), R(8, 12, 1, 1, MUTED), R(6, 13, 5, 1, MUTED)])

# Windows program (.exe, .msi): a window with a run triangle
glyph("application-x-msdownload", 48, MINT, [P("M13 20 H35 V40 H13 Z M15 26 V38 H33 V26 Z", rule=True)],
      [P("M21 29 V35 L27 32 Z", MINT)])
glyph("application-x-msdownload", 22, MINT, [P("M6 9 H16 V18 H6 Z M7 12 V17 H15 V12 Z", rule=True)],
      [R(9, 13, 1, 3, MINT), R(10, 14, 1, 1, MINT)])
glyph("application-x-msdownload", 16, MINT, [P("M5 6 H12 V13 H5 Z M6 8 V12 H11 V8 Z", rule=True)],
      [R(7, 9, 1, 2, MINT), R(8, 10, 1, 1, MINT)])

# Android package: a phone
glyph("application-vnd.android.package-archive", 48, SKY,
      [P("M15 19 H33 V42 H15 Z M18 22 V36 H30 V22 Z", rule=True)],
      [R(22, 38, 4, 2, PAGE), R(23, 24, 2, 5, SKY), P("M20 29 H28 L24 34 Z", SKY)])
glyph("application-vnd.android.package-archive", 22, SKY,
      [P("M6 8 H16 V19 H6 Z M8 10 V16 H14 V10 Z", rule=True)],
      [R(10, 17, 2, 1, PAGE)])
glyph("application-vnd.android.package-archive", 16, SKY,
      [P("M4 5 H13 V14 H4 Z M6 7 V12 H11 V7 Z", rule=True)],
      [R(8, 13, 1, 1, PAGE)])

# disc image (.iso)
glyph("application-x-cd-image", 48, LILAC,
      [P("M14 30 A10 10 0 1 0 34 30 A10 10 0 1 0 14 30 Z M21 30 A3 3 0 1 0 27 30 A3 3 0 1 0 21 30 Z", rule=True)],
      [R(29, 24, 3, 2, PAGE)])
glyph("application-x-cd-image", 22, LILAC,
      [P("M6 14 A5 5 0 1 0 16 14 A5 5 0 1 0 6 14 Z M9.5 14 A1.5 1.5 0 1 0 12.5 14 A1.5 1.5 0 1 0 9.5 14 Z",
         rule=True)])
glyph("application-x-cd-image", 16, LILAC,
      [P("M5 10 A3.5 3.5 0 1 0 12 10 A3.5 3.5 0 1 0 5 10 Z M7.5 10 A1 1 0 1 0 9.5 10 A1 1 0 1 0 7.5 10 Z",
         rule=True)])

# font: a capital A
glyph("font-x-generic", 48, PINK, [P("M13 40 L21 20 H27 L35 40 H30 L28.5 36 H19.5 L18 40 Z M24 25.5 L21.4 32 H26.6 Z",
                                      rule=True)])
glyph("font-x-generic", 22, PINK, pix([
    (9, [(10, 2)]), (10, [(9, 1), (12, 1)]), (11, [(9, 1), (12, 1)]), (12, [(8, 1), (13, 1)]),
    (13, [(8, 1), (13, 1)]), (14, [(7, 8)]), (15, [(7, 1), (14, 1)]), (16, [(6, 1), (15, 1)]),
    (17, [(6, 1), (15, 1)])]))
glyph("font-x-generic", 16, PINK, pix([
    (6, [(8, 2)]), (7, [(7, 1), (10, 1)]), (8, [(7, 1), (10, 1)]), (9, [(6, 1), (11, 1)]),
    (10, [(6, 6)]), (11, [(6, 1), (11, 1)]), (12, [(5, 1), (12, 1)]), (13, [(5, 1), (12, 1)])]))

# unknown: a question mark
glyph("unknown", 48, MUTED,
      [R(15, 20, 14, 3), R(13, 23, 3, 3), R(29, 23, 4, 6), R(22, 29, 8, 3), R(22, 32, 4, 3), R(22, 37, 4, 3)])
glyph("unknown", 22, MUTED,
      [R(8, 9, 5, 1), R(7, 10, 1, 1), R(13, 10, 1, 2), R(11, 12, 2, 1), R(10, 13, 2, 1), R(10, 14, 2, 1),
       R(10, 16, 2, 2)])
glyph("unknown", 16, MUTED,
      [R(6, 6, 4, 1), R(5, 7, 1, 1), R(10, 7, 1, 2), R(8, 9, 2, 2), R(8, 12, 2, 2)])

# ----------------------------------------------------------------------------------------------
# aliases: the icon names Spark Files, Plasma and Breeze use -> the icon above.
# Breeze draws most of these, and an icon theme's own names win over the generic fallback, so every
# name Breeze has in a family has to point at ours or Breeze's file would show.
# ----------------------------------------------------------------------------------------------
ALIASES = {
    "text-plain": """text-x-generic text-x-generic-template text-x-plain text-x-readme text-x-log
        text-x-markdown text-markdown text-x-copying text-x-authors text-x-changelog text-x-credits
        text-x-install text-x-nfo text-enriched text-x-patch text-x-po text-x-gettext-translation
        text-x-makefile text-x-cmake text-x-tex text-x-bibtex text-x-texinfo text-troff text-x-troff-man
        text-wiki text-vtt text-x-hex text-x-ldif text-x-opml text-x-opml+xml text-x-dtd text-directory
        text-x-rpm-spec text-dockerfile text-vcalendar text-calendar text-x-vcard text-x-mpsub
        text-x-microdvd text-x-ssa text-x-subviewer application-x-subrip application-x-srt
        application-x-sami application-x-zerosize application-x-theme text-x-katefilelist text-xmcd
        text-vnd.abc text-vnd.typst application-toml application-x-desktop""",
    "text-x-python": "text-x-python2 text-x-python3 application-x-python-bytecode",
    "text-x-script": """text-x-shellscript application-x-shellscript application-x-executable-script
        text-x-sh text-x-bash text-x-perl application-x-perl application-x-awk text-x-awk text-x-lua
        text-x-tcl application-x-ruby application-x-php text-x-php text-x-r application-x-rdata
        text-x-sql application-sql application-x-gdscript text-x-qml""",
    "application-javascript": """text-javascript text-x-javascript application-x-javascript
        application-json text-x-typescript application-x-typescript text-x-java text-x-java-source
        application-x-java application-x-java-applet text-x-kotlin text-x-scala text-x-go text-rust
        text-x-rust text-x-haskell text-x-nim text-x-pascal text-x-adasrc text-x-fortran text-fortran
        text-x-lilypond text-x-c++src text-x-c++hdr text-x-csrc text-x-chdr text-x-objcsrc text-x-objchdr application-x-godot-project application-x-godot-resource application-x-godot-scene
        application-x-godot-shader""",
    "text-html": """viewhtml application-xhtml+xml application-xml text-xml text-sgml application-xsd
        application-xslt+xml application-rss+xml application-atom+xml application-mathml+xml
        application-relaxng text-rdf text-rdf+xml text-x-xslfo text-vnd.wap.wml
        application-vnd.google-earth.kml+xml application-x-xliff text-vnd.trolltech.linguist""",
    "text-css": "text-x-scss text-x-sass",
    "text-x-csharp": "text-csharp",
    "package-x-generic": """application-zip application-x-zip application-x-zip-compressed application-x-7z-compressed
        application-x-tar application-gzip application-x-gzip application-x-compressed-tar
        application-x-bzip application-x-bzip2 application-x-bzip-compressed-tar
        application-x-bzip2-compressed-tar application-x-xz application-x-xz-compressed-tar
        application-zstd application-x-zstd application-x-zstd-compressed-tar
        application-x-lzma-compressed-tar application-x-tarz application-x-lrzip application-vnd.rar
        application-x-rar application-x-rpm application-x-source-rpm application-x-deb
        application-vnd.debian.binary-package application-x-archive application-x-java-archive
        application-x-jar application-x-lha application-x-cpio application-x-compress application-x-lzop
        application-x-zoo application-x-arj application-x-ace application-x-arc application-x-ar
        application-x-xz-pkg application-x-tzo application-vnd.squashfs application-vnd.snap
        application-x-ms-wim application-x-xpinstall application-x-zip-compressed-fb2 application-msix""",
    "image-x-generic": """image-png image-jpeg image-gif image-bmp image-webp image-tiff image-avif image-heif
        image-heic image-jxl image-jpeg2000 image-svg+xml image-svg+xml-compressed image-x-svg+xml
        image-x-icon image-x-ico image-ico image-vnd.microsoft.icon image-x-win-bitmap image-x-win-bmp
        image-x-xcf image-x-compressed-xcf image-x-psd image-x-psdimage-x-psd image-x-tga
        image-x-portable-bitmap image-x-eps image-x-adobe-dng image-x-emf image-x-wmf application-x-wmf
        image-vnd.djvu image-vnd.dwg image-vnd.dgn image-x-xfig image-x-krita
        image-x-vnd.trolltech.qpicture application-illustrator""",
    "audio-x-generic": """audio-mpeg audio-mp3 audio-mp2 audio-mp4 audio-x-mp2 audio-x-mpeg audio-flac audio-x-flac
        audio-x-flac+ogg audio-ogg audio-x-vorbis+ogg audio-x-speex+ogg audio-opus audio-x-opus+ogg
        audio-aac audio-x-aac audio-webm audio-x-ms-wma audio-x-matroska audio-x-wav audio-vnd.wave
        audio-x-aiff audio-midi audio-ac3 audio-x-adpcm audio-x-monkey audio-prs.sid audiobook
        audio-vnd.rn-realvideo audio-vn.rn-realmedia application-ogg application-x-cda
        application-x-audacity-project application-x-audacity-project+sqlite3 podcast x-media-podcast""",
    "video-x-generic": """video-mp4 video-webm video-x-matroska video-x-msvideo video-x-flv video-x-wmv video-x-ms-wmv
        video-x-theora+ogg video-x-ogm+ogg video-mp2t video-quicktime video-mpeg video-x-mpeg video-3gpp
        video-x-anim video-x-flic video-x-mng video-vnd.rn-realvideo video-x-javafx video-x-ms-wmp
        video-mlt-playlist video-vivo video-wavelet video-x-google-vlc-plugin application-vnd.rn-realmedia
        application-x-flash-video application-x-shockwave-flash application-x-mplayer2
        application-x-kdenlive application-x-kdenlivetitle""",
    "application-pdf": "viewpdf application-x-pdf application-postscript viewps application-x-gzpostscript application-x-gzdvi application-x-bzdvi viewdvi",
    "x-office-document": """application-msword application-msword-template application-vnd.ms-word
        application-vnd.ms-word.document.macroenabled.12 application-vnd.ms-word.template.macroenabled.12
        application-vnd.openxmlformats-officedocument.wordprocessingml.document
        application-vnd.openxmlformats-officedocument.wordprocessingml.template
        application-vnd.oasis.opendocument.text application-vnd.oasis.opendocument.text-template
        application-vnd.oasis.opendocument.text-master application-vnd.oasis.opendocument.web-template
        application-vnd.sun.xml.writer application-vnd.sun.xml.writer.template application-vnd.sun.xml.writer.global
        application-sxw application-rtf text-rtf libreoffice-text libreoffice-text-template
        libreoffice-oasis-text libreoffice-oasis-text-template libreoffice-master-document
        libreoffice-oasis-master-document libreoffice-oasis-web-template application-wps-office.doc
        application-wps-office.docx application-wps-office.dot application-wps-office.dotx
        application-x-abiword application-x-mswrite application-x-kword application-x-applix-word
        application-vnd.wordperfect application-epub+zip application-x-fictionbook+xml application-x-lyx
        application-vnd.ms-publisher vnd.ms-publisher application-x-chm odf""",
    "x-office-spreadsheet": """application-vnd.ms-excel application-vnd.ms-excel.addin.macroenabled.12
        application-vnd.ms-excel.sheet.binary.macroenabled.12 application-vnd.ms-excel.sheet.macroenabled.12
        application-vnd.ms-excel.template.macroenabled.12
        application-vnd.openxmlformats-officedocument.spreadsheetml.sheet
        application-vnd.openxmlformats-officedocument.spreadsheetml.template
        application-vnd.oasis.opendocument.spreadsheet application-vnd.oasis.opendocument.spreadsheet-template
        application-vnd.sun.xml.calc application-vnd.sun.xml.calc.template application-vnd.stardivision.calc
        libreoffice-spreadsheet libreoffice-spreadsheet-template libreoffice-oasis-spreadsheet
        libreoffice-oasis-spreadsheet-template application-wps-office.xls application-wps-office.xlsx
        application-wps-office.xlt application-wps-office.xltx application-x-gnumeric
        application-x-applix-spreadsheet application-x-quattropro application-x-siag text-csv
        text-tab-separated-values application-vnd.oasis.opendocument.chart""",
    "x-office-presentation": """application-vnd.ms-powerpoint application-vnd.ms-powerpoint.addin.macroenabled.12
        application-vnd.ms-powerpoint.presentation.macroenabled.12
        application-vnd.ms-powerpoint.slide.macroenabled.12
        application-vnd.ms-powerpoint.slideshow.macroenabled.12
        application-vnd.ms-powerpoint.template.macroenabled.12
        application-vnd.openxmlformats-officedocument.presentationml.presentation
        application-vnd.openxmlformats-officedocument.presentationml.slideshow
        application-vnd.openxmlformats-officedocument.presentationml.template
        application-vnd.oasis.opendocument.presentation application-vnd.oasis.opendocument.presentation-template
        application-vnd.sun.xml.impress application-vnd.sun.xml.impress.template libreoffice-presentation
        libreoffice-presentation-template libreoffice-oasis-presentation
        libreoffice-oasis-presentation-template application-wps-office.ppt application-wps-office.pptx
        application-wps-office.pot application-wps-office.potx application-x-kpresenter""",
    "application-x-msdownload": """application-x-ms-dos-executable application-vnd.microsoft.portable-executable
        application-x-ms-ne-executable application-x-msdos-program application-x-dosexec application-x-msi
        application-x-ms-installer application-x-ms-pe""",
    "application-vnd.android.package-archive": "android-package-archive application-vnd.android.app-bundle",
    "application-x-cd-image": """application-x-iso application-x-iso9660-image application-vnd.efi.iso
        application-x-compressed-iso application-x-raw-disk-image application-x-qemu-disk
        application-x-vdi-disk application-x-apple-diskimage application-x-cue application-x-vhd
        application-x-vhdx application-x-k3b virtualbox-hdd virtualbox-vdi virtualbox-vhd virtualbox-vmdk
        virtualbox-ova virtualbox-ovf""",
    "font-x-generic": """font-ttf font-otf font-woff font-woff2 font-sfnt font-collection application-x-font-ttf
        application-x-font-otf application-x-font-type1 application-x-font-pcf application-x-font-bdf
        application-x-font-afm application-x-font-snf application-x-font-ttx application-font-woff
        application-font-woff2 application-vnd.ms-fontobject application-x-font-woff""",
    "unknown": "application-octet-stream application-x-generic",
}


def svg(name, size, label):
    page, fold, slip = FRAME[size]
    g = G[name][size]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
        f"  <!-- {label}. SparkOS icon theme, {size} grid. -->",
        f'  <path d="{page}" fill="{PAGE}" stroke="{EDGE}" stroke-width="1"/>',
        f'  <path d="{fold}" fill="{FOLD}"/>',
    ]
    if g["slip"]:
        lines.append(f"  <!-- the slip: magenta {slip} left, cyan {slip} right, the colour on top -->")
        for dx, col in ((-slip, MAG), (slip, CYAN), (0, g["color"])):
            tr = f' transform="translate({dx} 0)"' if dx else ""
            lines.append(f'  <g{tr} fill="{col}">')
            lines += ["    " + el(i, col) for i in g["slip"]]
            lines.append("  </g>")
    for item in g["flat"]:
        lines.append("  " + el(item, MUTED))
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


LABELS = {
    "text-plain": "Plain text", "text-x-python": "Python source", "text-x-script": "Shell script and other scripts",
    "application-javascript": "JavaScript, TypeScript, JSON", "text-html": "HTML and XML",
    "text-css": "CSS", "text-x-csharp": "C#", "package-x-generic": "Archive (zip, 7z, tar and more)",
    "image-x-generic": "Image", "audio-x-generic": "Audio", "video-x-generic": "Video",
    "application-pdf": "PDF", "x-office-document": "Word-processing document",
    "x-office-spreadsheet": "Spreadsheet", "x-office-presentation": "Presentation",
    "application-x-msdownload": "Windows program (.exe, .msi), opened by Spark Run",
    "application-vnd.android.package-archive": "Android package (APK)",
    "application-x-cd-image": "Disc and disk image (ISO)", "font-x-generic": "Font",
    "unknown": "Unknown or generic file",
}


def main():
    dirs = {"scalable": 48, "22": 22, "16": 16}
    for d in list(dirs) + ["24"]:
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    for name in G:
        for d, size in dirs.items():
            with open(os.path.join(OUT, d, name + ".svg"), "w", encoding="utf-8") as f:
                f.write(svg(name, size, LABELS[name]))
        a = svg(name, 22, LABELS[name]).splitlines()
        a[0] = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 24 24" width="24" height="24">'
        a[1] = f"  <!-- {LABELS[name]}, drawn for 22 px, shown at 24 with a 1 px margin. -->"
        with open(os.path.join(OUT, "24", name + ".svg"), "w", encoding="utf-8") as f:
            f.write("\n".join(a) + "\n")
    n = 0
    for target, names in ALIASES.items():
        for alias in names.split():
            for d in ("scalable", "22", "24", "16"):
                link = os.path.join(OUT, d, alias + ".svg")
                if os.path.lexists(link):
                    os.remove(link)
                os.symlink(target + ".svg", link)
                n += 1
    print(f"{len(G)} icons, {n} alias links")


if __name__ == "__main__":
    main()
