#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). Spark Media on plain Fedora.
#
# The real build (spark-media.sh) fails unless H.264, H.265, AAC and MP3 play. Fedora's own
# FFmpeg is reduced for patent reasons, so this installs Spark Media the same way but records
# which of those formats play instead of failing: the boot test and docs/fedora-base.md report it.
# Cisco's OpenH264 (an H.264 decoder Cisco pays the licence for) comes from Fedora's
# fedora-cisco-openh264 repository, which Fedora enables by default.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-media"
test -f "$SRC/install.sh" || { echo "Spark Media source not found at $SRC"; exit 1; }

dnf -y install --setopt=install_weak_deps=False gstreamer1-plugin-openh264 \
  || dnf -y install --setopt=install_weak_deps=False --enablerepo=fedora-cisco-openh264 gstreamer1-plugin-openh264 \
  || echo "--- OpenH264 not available"

bash "$SRC/install.sh" --deps --no-test

test -x /usr/bin/spark-media
test -f /usr/share/applications/dev.wolklaw.SparkMedia.desktop

# Measure each format the real build requires, one at a time
scratch=$(mktemp -d)
mkdir -p /usr/share/sparkos/fedora-base
out=/usr/share/sparkos/fedora-base/media-formats.txt
: > "$out"
for fmt in h264 h265 aac mp3; do
  if XDG_STATE_HOME="$scratch" XDG_CONFIG_HOME="$scratch" XDG_CACHE_HOME="$scratch" \
       /usr/bin/spark-media --self-test --require "$fmt" > "$scratch/$fmt.log" 2>&1; then
    echo "$fmt: plays" | tee -a "$out"
  else
    echo "$fmt: does not play" | tee -a "$out"
    tail -5 "$scratch/$fmt.log"
  fi
done
for el in avdec_h264 avdec_h265 openh264dec avdec_aac fdkaacdec mpg123audiodec; do
  if gst-inspect-1.0 --exists "$el"; then echo "element $el: yes"; else echo "element $el: no"; fi
done | tee -a "$out"
rm -rf "$scratch"
echo "$(/usr/bin/spark-media --version) installed."
