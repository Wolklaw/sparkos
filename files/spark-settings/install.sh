#!/usr/bin/env bash
# Install Spark Settings, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test]        just you, into ~/.local; no root
#   bash install.sh --user --uninstall        remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-settings] [--no-test]   system-wide, root
#   bash install.sh --uninstall               remove the system-wide install, root
#
# --deps     system-wide only: install Python's tkinter with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# This only installs the app. Putting it in the image is the build step: files/scripts/spark-settings.sh.
# Settings and the log (~/.config and ~/.local/state/spark-settings) are not touched by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkSettings
SLUG=spark-settings
PREFIX=/usr/lib/$SLUG
DEPS=0; TEST=1; USER_MODE=0; UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
  if command -v kbuildsycoca6 >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    kbuildsycoca6 >/dev/null 2>&1 || true
  fi
}

copy_app() {   # $1: destination folder
  install -d "$1/sparksettings" "$1/icons"
  install -m 0644 "$here"/sparksettings/*.py "$1/sparksettings/"
  install -m 0644 "$here/spark_settings.py" "$here/spark-app.json" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
}

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files
  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then echo "Spark Settings isn't installed for $(id -un)."; exit 0; fi
    while IFS= read -r path; do
      case "$path" in "$HOME"/*) rm -f -- "$path" ;; *) echo "skipping $path (outside $HOME)" >&2 ;; esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    refresh_menus "$DATA/applications"
    echo "Spark Settings removed for $(id -un)."
    exit 0
  fi
  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2; exit 1
  fi
  python3 -c 'import tkinter' 2>/dev/null || { echo "Spark Settings needs Python 3 with tkinter." >&2; exit 1; }
  rm -rf -- "$LIB"
  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }
  install -d "$(dirname "$BIN")"
  printf '#!/bin/sh\nexec /usr/bin/env python3 "%s/spark_settings.py" "$@"\n' "$LIB" > "$BIN"
  chmod 0755 "$BIN"; record "$BIN"
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-settings|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
  chmod 0644 "$desktop"; record "$desktop"
  for size in $SIZES; do
    target="$DATA/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm 0644 "$here/icons/$SLUG-$size.png" "$target"; record "$target"
  done
  target="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
  install -Dm 0644 "$here/icons/$SLUG.svg" "$target"; record "$target"
  refresh_menus "$DATA/applications"
  "$BIN" --version
  [ "$TEST" = 1 ] && "$BIN" --self-test
  echo "Spark Settings installed for $(id -un) in $LIB. Remove it with: bash $here/install.sh --user --uninstall"
  exit 0
fi

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2; exit 1
fi
if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"; done
  refresh_menus /usr/share/applications
  echo "Spark Settings removed from the system."
  exit 0
fi
if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter; do rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg"); done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi
rm -rf "$PREFIX"
copy_app "$PREFIX"
printf '#!/bin/sh\nexec /usr/bin/python3 %s/spark_settings.py "$@"\n' "$PREFIX" > /usr/bin/$SLUG
chmod 0755 /usr/bin/$SLUG
install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
test -x /usr/bin/$SLUG
/usr/bin/$SLUG --version
[ "$TEST" = 1 ] && /usr/bin/$SLUG --self-test
echo "Spark Settings installed to $PREFIX."
