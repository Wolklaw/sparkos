#!/usr/bin/env bash
# Install Spark Run, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test]          just you, into ~/.local; no root
#   bash install.sh --user --uninstall [--purge]  remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-run] [--no-test]    system-wide, root
#   bash install.sh --uninstall                 remove the system-wide install, root
#
# --user     SparkOS keeps /usr read-only, so optional Spark apps install here. Needs only
#            what the SparkOS image has (Python 3 with tkinter); Wine itself is downloaded by
#            Spark Run the first time someone runs a Windows program, not by this script.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build):
#            Python with tkinter and Pillow, and the libraries Wine loads (by soname, so
#            nothing is added when the image already has them).
# --purge    with --user --uninstall: also delete ~/.local/share/spark-run (downloaded Wine
#            and every installed Windows app) and the apps' menu entries.
# --no-test  skip the self-test at the end.
#
# Settings and logs (~/.config/spark-run, ~/.local/state/spark-run) are not touched by
# --uninstall without --purge.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkRun
SLUG=spark-run
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
USER_MODE=0
UNINSTALL=0
PURGE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"
# What Wine loads from Linux (most of it with dlopen), as RPM soname provides
WINE_LIBS="libfreetype.so.6()(64bit) libfontconfig.so.1()(64bit) libX11.so.6()(64bit)
  libXext.so.6()(64bit) libXrender.so.1()(64bit) libXi.so.6()(64bit) libXrandr.so.2()(64bit)
  libXcursor.so.1()(64bit) libXcomposite.so.1()(64bit) libGL.so.1()(64bit)
  libvulkan.so.1()(64bit) libgnutls.so.30()(64bit) libpulse.so.0()(64bit)
  libasound.so.2()(64bit) libgstreamer-1.0.so.0()(64bit) libcups.so.2()(64bit)"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
  if command -v kbuildsycoca6 >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    kbuildsycoca6 >/dev/null 2>&1 || true
  fi
}

# ─── Per user, no root ───────────────────────────────────────

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files

  if [ "$UNINSTALL" = 1 ]; then
    if [ "$PURGE" = 1 ]; then
      # the Windows apps' own menu entries, then Wine and every prefix
      for entry in "$DATA/applications/$APP_ID".app-*.desktop; do
        [ -e "$entry" ] && rm -f -- "$entry"
      done
      if [ -d "$DATA/$SLUG" ]; then
        # end any Windows program still running in a prefix before deleting it
        for server in "$DATA/$SLUG"/runtime/wine-*/bin/wineserver; do
          [ -x "$server" ] || continue
          for pfx in "$DATA/$SLUG"/prefixes/* "$DATA/$SLUG/run-once"; do
            [ -d "$pfx" ] && WINEPREFIX="$pfx" "$server" -k 2>/dev/null || true
          done
        done
        rm -rf --one-file-system -- "$DATA/$SLUG"
      fi
      rm -rf -- "${XDG_CONFIG_HOME:-$HOME/.config}/$SLUG" \
                "${XDG_STATE_HOME:-$HOME/.local/state}/$SLUG" \
                "${XDG_CACHE_HOME:-$HOME/.cache}/$SLUG"
    fi
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Run isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    rmdir --ignore-fail-on-non-empty "$HOME/.local/lib" 2>/dev/null || true
    refresh_menus "$DATA/applications"
    echo "Spark Run removed for $(id -un)."
    if [ "$PURGE" = 0 ] && [ -d "$DATA/$SLUG" ]; then
      used=$(du -sh --one-file-system "$DATA/$SLUG" 2>/dev/null | cut -f1)
      echo "Downloaded Wine and your installed Windows apps stay in $DATA/$SLUG (${used:-?}),"
      echo "and their menu entries need Spark Run to open. To delete those too:"
      echo "  bash $here/install.sh --user --uninstall --purge"
    fi
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo "Spark Run needs Python 3 with tkinter, which this system doesn't have." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi

  rm -rf -- "$LIB"
  install -d "$LIB/sparkrun" "$LIB/icons"
  install -m 0644 "$here"/sparkrun/*.py "$LIB/sparkrun/"
  install -m 0644 "$here/spark_run.py" "$here/spark-app.json" "$LIB/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$LIB/icons/"
  python3 -m compileall -q "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
SPARK_RUN_BIN="$BIN" exec /usr/bin/env python3 "$LIB/spark_run.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entry at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-run|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
  chmod 0644 "$desktop"
  record "$desktop"
  for size in $SIZES; do
    target="$DATA/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm 0644 "$here/icons/$SLUG-$size.png" "$target"
    record "$target"
  done
  target="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
  install -Dm 0644 "$here/icons/$SLUG.svg" "$target"
  record "$target"
  refresh_menus "$DATA/applications"

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  echo "Spark Run installed for $(id -un) in $LIB. It downloads Wine the first time you run"
  echo "a Windows program. Remove it with:"
  echo "  bash $here/install.sh --user --uninstall"
  exit 0
fi

# ─── System-wide, root ───────────────────────────────────────

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Run removed from the system. Each user's Wine and Windows apps stay in"
  echo "~/.local/share/spark-run."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter $WINE_LIBS; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
  # program icons as PNG; it works without (the .ico is used as is)
  python3 -c 'from PIL import Image, ImageTk' 2>/dev/null || \
    dnf -y install --setopt=install_weak_deps=False python3-pillow-tk || \
    echo "--- optional: no Pillow, program icons stay .ico files"
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkrun" "$PREFIX/icons"
install -m 0644 "$here"/sparkrun/*.py "$PREFIX/sparkrun/"
install -m 0644 "$here/spark_run.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
SPARK_RUN_BIN=/usr/bin/$SLUG exec /usr/bin/python3 $PREFIX/spark_run.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -f "$PREFIX/sparkrun/apps.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Run installed to $PREFIX."
