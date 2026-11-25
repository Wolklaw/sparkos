"""Shared by the tests: a temporary home (set before the app reads it), real system fonts to
test with, and a way to make a copy of one under a name no system font has."""

import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

# a home of its own, set before anything reads it (fontconfig reads these in each fc-* run)
TMP = tempfile.mkdtemp(prefix='spark-fonts-test-')
os.environ.update({
    'HOME': TMP,
    'XDG_DATA_HOME': os.path.join(TMP, 'data'),
    'XDG_CONFIG_HOME': os.path.join(TMP, 'config'),
    'XDG_STATE_HOME': os.path.join(TMP, 'state'),
    'XDG_CACHE_HOME': os.path.join(TMP, 'cache'),
    'SPARK_FONTS_REDUCED_MOTION': '1',
})

from sparkfonts import core, fcdata, fontfile  # noqa: E402

HAVE_FC = shutil.which('fc-list') is not None and shutil.which('fc-cache') is not None
SYSTEM_FACES = fcdata.list_faces() if HAVE_FC else []


def pick_font(want_ext=('.ttf', '.otf'), variable=None, maximum=3_000_000):
    """A real font file from the system: the smallest static one by default."""
    best = None
    for face in SYSTEM_FACES:
        if not face.path.lower().endswith(want_ext) or face.index != 0:
            continue
        if variable is not None and face.variable != variable:
            continue
        try:
            size = os.path.getsize(face.path)
        except OSError:
            continue
        if size <= maximum and (best is None or size < best[0]):
            best = (size, face.path)
    return best[1] if best else None


def pick_collection():
    for face in SYSTEM_FACES:
        if face.path.lower().endswith('.ttc'):
            return face.path
    return None


def rename_family(src, dst, family):
    """Copy a font and give it another family name (so it can't clash with a system font):
    rewrites the UTF-16 name records in place when the new name has the same length, else
    raises. Only for static TrueType fonts, which is all the tests ask for."""
    with open(src, 'rb') as f:
        data = bytearray(f.read())
    old = None
    details = fontfile.read_details(src)
    old = details.family
    if len(family) != len(old):
        family = (family + old)[:len(old)] if len(family) < len(old) else family[:len(old)]
    for enc in ('utf-16-be', 'latin-1'):
        a, b = old.encode(enc), family.encode(enc)
        data = bytearray(bytes(data).replace(a, b))
    with open(dst, 'wb') as f:
        f.write(data)
    return family


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w') as z:
        for name, payload in entries:
            z.writestr(name, payload)


def fresh_home():
    """Empty user fonts, trash and cache before a test."""
    for sub in ('data', 'cache'):
        shutil.rmtree(os.path.join(TMP, sub), ignore_errors=True)
    os.makedirs(core.fonts_dir(), exist_ok=True)
