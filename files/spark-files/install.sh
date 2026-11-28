#!/usr/bin/env bash
# Install Spark Files, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--default] [--no-test]   just you, into ~/.local; no root
#   bash install.sh --user --uninstall               remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-files] [--no-test]   system-wide, root
#   bash install.sh --uninstall                      remove the system-wide install, root
#
# --user     installs into ~/.local and adds the D-Bus files in ~/.local/share/dbus-1/services,
#            so "Show in folder" in other apps reaches Spark Files. Needs only what the SparkOS
#            image has (Python 3 with tkinter, Pillow, PyGObject); nothing is downloaded.
# --default  with --user: also make it your default file manager (inode/directory), with
#            xdg-mime. --uninstall removes the default if Spark Files was it.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# The system-wide install doesn't make itself the default; on SparkOS the image does that
# (files/scripts/spark-files.sh and sparkos-defaults.sh). Settings (~/.config/spark-files) and
# the log (~/.local/state/spark-files) are not touched by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkFiles
SLUG=spark-files
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
USER_MODE=0
UNINSTALL=0
DEFAULT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --default) DEFAULT=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
}

copy_app() {   # $1: destination folder
  install -d "$1/sparkfiles" "$1/icons"
  install -m 0644 "$here"/sparkfiles/*.py "$1/sparkfiles/"
  install -m 0644 "$here/spark_files.py" "$here/spark-app.json" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
}

dbus_file() {   # $1: template, $2: command, $3: destination
  sed "s|^Exec=/usr/bin/spark-files|Exec=$2|" "$here/$1" > "$3"
  chmod 0644 "$3"
}

# ─── Per user, no root ───────────────────────────────────────

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Files isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    if command -v xdg-mime >/dev/null && [ "$(xdg-mime query default inode/directory 2>/dev/null)" = "$APP_ID.desktop" ]; then
      echo "Spark Files was the default for folders; choose another file manager if you have one."
    fi
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    rmdir --ignore-fail-on-non-empty "$HOME/.local/lib" "$DATA/dbus-1/services" "$DATA/dbus-1" 2>/dev/null || true
    refresh_menus "$DATA/applications"
    echo "Spark Files removed for $(id -un). Settings stay in ~/.config/$SLUG and the log in"
    echo "~/.local/state/$SLUG; delete those folders too if you don't want them."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo "Spark Files needs Python 3 with tkinter, which this system doesn't have." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi

  rm -rf -- "$LIB"
  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_files.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entries at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-files|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
  chmod 0644 "$desktop"
  record "$desktop"
  # D-Bus activation: the session bus reads ~/.local/share/dbus-1/services before the system's
  install -d "$DATA/dbus-1/services"
  dbus_file "$APP_ID.service" "$BIN" "$DATA/dbus-1/services/$APP_ID.service"
  record "$DATA/dbus-1/services/$APP_ID.service"
  dbus_file org.freedesktop.FileManager1.service "$BIN" \
    "$DATA/dbus-1/services/org.freedesktop.FileManager1.service"
  record "$DATA/dbus-1/services/org.freedesktop.FileManager1.service"
  for size in $SIZES; do
    target="$DATA/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm 0644 "$here/icons/$SLUG-$size.png" "$target"
    record "$target"
  done
  target="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
  install -Dm 0644 "$here/icons/$SLUG.svg" "$target"
  record "$target"
  refresh_menus "$DATA/applications"
  if [ "$DEFAULT" = 1 ]; then
    if command -v xdg-mime >/dev/null; then
      xdg-mime default "$APP_ID.desktop" inode/directory
      echo "Folders now open in Spark Files."
    else
      echo "xdg-mime isn't installed: set the default file manager in System Settings." >&2
    fi
  fi

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  echo "Spark Files installed for $(id -un) in $LIB. It's in the app menu. Remove it with:"
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
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
        "/usr/share/dbus-1/services/$APP_ID.service" \
        "/usr/share/dbus-1/services/$APP_ID.FileManager1.service" \
        /usr/share/dbus-1/services/org.freedesktop.FileManager1.service \
        "/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.spark.service" \
        /usr/share/xdg-desktop-portal/portals/spark.portal \
        /usr/share/xdg-desktop-portal/spark-portals.conf
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Files removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter python3-pillow python3-pillow-tk python3-gobject glib2 \
             gstreamer1-plugins-base xrdb cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
copy_app "$PREFIX"

cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_files.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
install -Dm 0644 "$here/$APP_ID.service" "/usr/share/dbus-1/services/$APP_ID.service"
# named after the D-Bus name it answers: dbus-broker warns at every login otherwise ("is not named
# after the D-Bus name"); the old dev.wolklaw.SparkFiles.FileManager1.service name goes
rm -f "/usr/share/dbus-1/services/$APP_ID.FileManager1.service"
install -Dm 0644 "$here/org.freedesktop.FileManager1.service" \
  /usr/share/dbus-1/services/org.freedesktop.FileManager1.service
# the portal backend (file chooser, "Open with"); only the Spark session's portals.conf uses it
install -Dm 0644 "$here/portal/org.freedesktop.impl.portal.desktop.spark.service" \
  /usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.spark.service
install -Dm 0644 "$here/portal/spark.portal" /usr/share/xdg-desktop-portal/portals/spark.portal
install -Dm 0644 "$here/portal/spark-portals.conf" /usr/share/xdg-desktop-portal/spark-portals.conf
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -f "$PREFIX/sparkfiles/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
test -f /usr/share/xdg-desktop-portal/portals/spark.portal
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Files installed to $PREFIX."
