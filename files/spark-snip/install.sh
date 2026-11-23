#!/usr/bin/env bash
# Install Spark Snip system-wide. Run as root, from anywhere:
#
#   bash files/spark-snip/install.sh [--deps] [--prefix /usr/lib/spark-snip] [--no-test]
#
# --deps     install what it needs with dnf, skipping anything already there. The SparkOS
#            image build uses this; GStreamer plugins are checked by element, because
#            another system may provide them from differently named packages.
# --no-test  skip the self-test at the end (it needs Tesseract and GStreamer).
#
# Installs /usr/bin/spark-snip, the program under the prefix, the desktop entry (with its
# global shortcuts, picked up by KDE's kglobalaccel) and the icons.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
PREFIX=/usr/lib/spark-snip
DEPS=0
TEST=1
while [ $# -gt 0 ]; do
  case "$1" in
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

APP_ID=dev.wolklaw.SparkSnip

dnf_install() {
  dnf -y install --setopt=install_weak_deps=False "$@"
}

if [ "$DEPS" = 1 ]; then
  # 1. programs and data, by package name
  missing=()
  for pkg in tesseract tesseract-langpack-eng tesseract-langpack-fra \
             python3 python3-tkinter python3-pillow python3-pillow-tk python3-gobject-base \
             wl-clipboard xclip xrandr xrdb xdg-user-dirs xdg-utils cascadia-mono-fonts \
             gstreamer1 pulseaudio-utils; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf_install "${missing[@]}"
  fi

  # 2. GStreamer elements, by what provides them
  has() { gst-inspect-1.0 --exists "$1" 2>/dev/null; }
  plugins=()
  for pair in pipewiresrc:pipewire-gstreamer \
              videoconvert:gstreamer1-plugins-base opusenc:gstreamer1-plugins-base \
              audiomixer:gstreamer1-plugins-base \
              videocrop:gstreamer1-plugins-good pulsesrc:gstreamer1-plugins-good \
              vp8enc:gstreamer1-plugins-good mp4mux:gstreamer1-plugins-good; do
    has "${pair%%:*}" || plugins+=("${pair#*:}")
  done
  if [ ${#plugins[@]} -gt 0 ]; then
    mapfile -t plugins < <(printf '%s\n' "${plugins[@]}" | sort -u)
    echo "--- installing GStreamer plugins: ${plugins[*]}"
    dnf_install "${plugins[@]}"
  fi
  # H.264 is optional: VP8/WebM always works. Use it when the system can have it.
  if ! has h264parse; then
    dnf_install gstreamer1-plugins-bad-free || echo "--- optional: no h264parse, recordings will be WebM"
  fi
  if ! has x264enc && ! has openh264enc && ! has vah264enc; then
    dnf_install gstreamer1-plugin-openh264 || echo "--- optional: no software H.264 encoder"
  fi
fi

# The program
rm -rf "$PREFIX"
install -d "$PREFIX/sparksnip" "$PREFIX/icons"
install -m 0644 "$here"/sparksnip/*.py "$PREFIX/sparksnip/"
install -m 0644 "$here/spark_snip.py" "$PREFIX/spark_snip.py"
install -m 0644 "$here/icons/spark-snip-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

cat > /usr/bin/spark-snip <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_snip.py "\$@"
EOF
chmod 0755 /usr/bin/spark-snip

# Desktop entry, and the same file for kglobalaccel so its shortcuts work out of the box
install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
install -d /usr/share/kglobalaccel
ln -sfn "../applications/$APP_ID.desktop" "/usr/share/kglobalaccel/$APP_ID.desktop"

# Icons
for size in 16 22 24 32 48 64 128 256 512; do
  install -Dm 0644 "$here/icons/spark-snip-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/spark-snip.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

# Fail loudly if anything is missing
test -x /usr/bin/spark-snip
test -f "$PREFIX/sparksnip/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/spark-snip --version

if [ "$TEST" = 1 ]; then
  # OCR in English and French, and a test video through every installed encoder.
  # HOME may be unset or read-only in a build container; logs go to a throwaway folder.
  scratch=$(mktemp -d)
  XDG_STATE_HOME="$scratch" XDG_CONFIG_HOME="$scratch" /usr/bin/spark-snip --self-test
  rm -rf "$scratch"
fi
echo "Spark Snip installed to $PREFIX."
