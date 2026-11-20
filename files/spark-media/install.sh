#!/usr/bin/env bash
# Install Spark Media system-wide. Run as root, from anywhere:
#
#   bash files/spark-media/install.sh [--deps] [--prefix /usr/lib/spark-media] [--no-test]
#
# --deps     install what it needs with dnf, skipping anything already there. The SparkOS
#            image build uses this; GStreamer plugins are checked by element, because
#            Bazzite may already provide them from differently named packages.
# --no-test  skip the self-test at the end (it needs GStreamer).
#
# Installs /usr/bin/spark-media, the program under the prefix, the desktop entry and the icons.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
PREFIX=/usr/lib/spark-media
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

APP_ID=dev.wolklaw.SparkMedia

dnf_install() {
  dnf -y install --setopt=install_weak_deps=False "$@"
}

if [ "$DEPS" = 1 ]; then
  # 1. programs and data, by package name
  missing=()
  for pkg in python3 python3-tkinter python3-pillow python3-pillow-tk python3-gobject-base \
             gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
             xrdb xdg-user-dirs xdg-utils glib2 cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf_install "${missing[@]}"
  fi

  # 2. GStreamer elements, by what provides them
  has() { gst-inspect-1.0 --exists "$1" 2>/dev/null; }
  plugins=()
  for pair in playbin:gstreamer1-plugins-base glimagesink:gstreamer1-plugins-base \
              xvimagesink:gstreamer1-plugins-base vorbisdec:gstreamer1-plugins-base \
              opusdec:gstreamer1-plugins-base \
              pulsesink:gstreamer1-plugins-good matroskademux:gstreamer1-plugins-good \
              qtdemux:gstreamer1-plugins-good vp8dec:gstreamer1-plugins-good \
              flacdec:gstreamer1-plugins-good mpg123audiodec:gstreamer1-plugins-good \
              wavparse:gstreamer1-plugins-good; do
    has "${pair%%:*}" || plugins+=("${pair#*:}")
  done
  if [ ${#plugins[@]} -gt 0 ]; then
    mapfile -t plugins < <(printf '%s\n' "${plugins[@]}" | sort -u)
    echo "--- installing GStreamer plugins: ${plugins[*]}"
    dnf_install "${plugins[@]}"
  fi
  # H.264, H.265, AAC and most other formats come from FFmpeg through gst-libav. Bazzite ships
  # the full FFmpeg; plain Fedora has a reduced one. Optional here: the self-test reports it,
  # and the SparkOS build requires it (files/scripts/spark-media.sh).
  has avdec_aac || dnf_install gstreamer1-plugin-libav || echo "--- optional: no gst-libav"
  has dav1ddec || dnf_install gstreamer1-plugin-dav1d || echo "--- optional: no AV1 decoder"
  # HEIC and AVIF photos (phones save HEIC)
  python3 -c 'import pillow_heif' 2>/dev/null || dnf_install python3-pillow-heif \
    || echo "--- optional: no pillow-heif, HEIC photos won't open"
fi

# The program
rm -rf "$PREFIX"
install -d "$PREFIX/sparkmedia" "$PREFIX/icons"
install -m 0644 "$here"/sparkmedia/*.py "$PREFIX/sparkmedia/"
install -m 0644 "$here/spark_media.py" "$PREFIX/spark_media.py"
install -m 0644 "$here/icons/spark-media-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

cat > /usr/bin/spark-media <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_media.py "\$@"
EOF
chmod 0755 /usr/bin/spark-media

# Desktop entry and icons
install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in 16 22 24 32 48 64 128 256 512; do
  install -Dm 0644 "$here/icons/spark-media-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/spark-media.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

# Fail loudly if anything is missing
test -x /usr/bin/spark-media
test -f "$PREFIX/sparkmedia/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/spark-media --version

if [ "$TEST" = 1 ]; then
  # Photo formats, decoders, and short test files played to the end. HOME may be unset or
  # read-only in a build container; settings, logs and thumbnails go to a throwaway folder.
  scratch=$(mktemp -d)
  XDG_STATE_HOME="$scratch" XDG_CONFIG_HOME="$scratch" XDG_CACHE_HOME="$scratch" \
    /usr/bin/spark-media --self-test ${SPARK_MEDIA_REQUIRE:+--require "$SPARK_MEDIA_REQUIRE"}
  rm -rf "$scratch"
fi
echo "Spark Media installed to $PREFIX."
