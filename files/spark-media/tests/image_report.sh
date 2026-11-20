#!/usr/bin/env bash
# What the SparkOS image has for Spark Media's music tags, camera RAW photos and photo saving.
# CI runs this inside the published image and puts the output on the run page.
set -u
echo "python: $(python3 -c 'import sys; print(sys.version.split()[0])')"
python3 - <<'EOF'
import importlib
for name in ('PIL', 'pillow_heif', 'rawpy', 'mutagen', 'gi', 'numpy', 'tinytag', 'piexif', 'exifread'):
    try:
        mod = importlib.import_module(name)
        print(f"module {name}: {getattr(mod, '__version__', 'yes')}")
    except Exception as exc:
        print(f"module {name}: no ({type(exc).__name__})")
try:
    from PIL import features
    print("pillow features:", {k: features.check(k) for k in ('jpg', 'webp', 'libtiff', 'zlib')})
except Exception as exc:
    print("pillow features: ?", exc)
try:
    import gi
    gi.require_version('Gst', '1.0'); gi.require_version('GstPbutils', '1.0')
    from gi.repository import Gst, GstPbutils
    Gst.init(None)
    print("gst:", Gst.version_string(), " discoverer:", hasattr(GstPbutils, 'Discoverer'))
except Exception as exc:
    print("gst: no", exc)
for ns, ver in (('GExiv2', '0.10'), ('GdkPixbuf', '2.0')):
    try:
        gi.require_version(ns, ver)
        importlib.import_module('gi.repository.' + ns)
        print(f"typelib {ns} {ver}: yes")
    except Exception as exc:
        print(f"typelib {ns} {ver}: no ({exc})")
EOF
for cmd in dcraw_emu simple_dcraw dcraw raw-identify ffprobe ffmpeg exiftool exiv2 gst-discoverer-1.0 \
           darktable-cli rawtherapee-cli magick convert vipsthumbnail; do
  printf 'command %-20s %s\n' "$cmd" "$(command -v "$cmd" || echo no)"
done
echo "--- libraries"
ldconfig -p 2>/dev/null | grep -i -E 'libraw|libexiv2|libtag|libavformat|libheif|libgexiv2|libkdcraw' | sed 's/ (.*=>/ =>/' | sort -u
echo "--- packages"
rpm -qa --qf '%{NAME} %{VERSION}\n' 2>/dev/null | grep -i -E 'libraw|exiv2|taglib|mutagen|ffmpeg|kdcraw|kimageformats|thumbnailer|python3-(pillow|numpy|gobject)' | sort
echo "--- who needs LibRaw"
rpm -q --whatrequires 'libraw_r.so.24()(64bit)' 'libraw.so.24()(64bit)' 2>/dev/null | sort -u | head
for f in /usr/lib64/libraw*.so*; do [ -e "$f" ] && rpm -qf "$f"; done 2>/dev/null | sort -u
echo "--- gst elements"
for e in id3demux apedemux taginject qtdemux matroskademux flacparse vorbisparse opusparse \
         wavpackdec avdec_wmav2 avdec_ape avdec_alac jpegdec; do
  printf '%-14s %s\n' "$e" "$(gst-inspect-1.0 --exists "$e" 2>/dev/null && echo yes || echo no)"
done
