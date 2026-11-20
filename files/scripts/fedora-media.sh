#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). Spark Media on plain Fedora.
#
# The real build (spark-media.sh) fails unless H.264, H.265, AAC and MP3 decoders exist. Fedora's
# own FFmpeg is reduced for patent reasons, so this installs Spark Media the same way but records
# which formats really decode instead of failing: the boot test and docs/fedora-base.md report it.
#
# H.264 comes from Cisco's OpenH264 (Cisco pays the licence), through Fedora's own
# fedora-cisco-openh264 repository. Kinoite ships "noopenh264", an empty stand-in library, so
# the GStreamer plugin alone loads but can't decode or encode; it is swapped for the real one.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-media"
test -f "$SRC/install.sh" || { echo "Spark Media source not found at $SRC"; exit 1; }

dnf_cisco() { dnf -y --setopt=install_weak_deps=False --enablerepo=fedora-cisco-openh264 "$@"; }
if rpm -q noopenh264 >/dev/null 2>&1; then
  dnf_cisco swap noopenh264 openh264 || echo "--- Cisco's OpenH264 not available"
fi
dnf_cisco install gstreamer1-plugin-openh264 || echo "--- gstreamer1-plugin-openh264 not available"

bash "$SRC/install.sh" --deps --no-test

test -x /usr/bin/spark-media
test -f /usr/share/applications/dev.wolklaw.SparkMedia.desktop

# Measure what really decodes: encode a short test clip, then decode it. (Spark Media's own
# --require only checks that a decoder element exists, which the noopenh264 stub also passes.)
mkdir -p /usr/share/sparkos/fedora-base
out=/usr/share/sparkos/fedora-base/media-formats.txt
roundtrip() { # name pipeline...
  local name=$1; shift
  if timeout 60 gst-launch-1.0 -q "$@" >/dev/null 2>&1; then
    echo "$name: decodes"
  else
    echo "$name: does not decode"
  fi
}
el() { gst-inspect-1.0 --exists "$1" 2>/dev/null && echo yes || echo no; }
{
  roundtrip "h264 (OpenH264)" videotestsrc num-buffers=30 ! video/x-raw,width=320,height=240 \
    ! openh264enc ! h264parse ! openh264dec ! fakesink
  if [ "$(el avdec_h265)" = yes ]; then
    echo "h265: a decoder exists (avdec_h265), no encoder in the image to test it with"
  else
    echo "h265: does not decode (no H.265 decoder in the image)"
  fi
  if [ "$(el avenc_aac)" = yes ]; then
    roundtrip "aac" audiotestsrc num-buffers=50 ! avenc_aac ! aacparse ! avdec_aac ! fakesink
  else
    echo "aac: not tested (no AAC encoder); decoder avdec_aac: $(el avdec_aac)"
  fi
  if [ "$(el lamemp3enc)" = yes ]; then
    roundtrip "mp3" audiotestsrc num-buffers=50 ! lamemp3enc ! mpegaudioparse ! mpg123audiodec ! fakesink
  else
    echo "mp3: not tested (no MP3 encoder); decoder mpg123audiodec: $(el mpg123audiodec)"
  fi
  for e in openh264dec openh264enc avdec_h264 avdec_h265 avdec_aac fdkaacdec mpg123audiodec; do
    echo "element $e: $(el $e)"
  done
  echo "openh264 library: $(rpm -q openh264 noopenh264 --qf '%{NAME} %{VERSION} (%{VENDOR})\n' 2>/dev/null | grep -v 'not installed' | paste -sd ' ')"
} | tee "$out"
echo "$(/usr/bin/spark-media --version) installed."
