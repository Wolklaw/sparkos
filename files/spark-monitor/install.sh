#!/usr/bin/env bash
# Install Spark Monitor, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test]          just you, into ~/.local; no root
#   bash install.sh --user --uninstall          remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-monitor] [--no-test]    system-wide, root
#   bash install.sh --uninstall                 remove the system-wide install, root
#
# --user     SparkOS keeps /usr read-only, so optional Spark apps install here. Needs only
#            what the SparkOS image has (Python 3 with tkinter); nothing is downloaded.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# The Spark compositor binds Ctrl+Shift+Esc to Spark Monitor. Settings (~/.config/spark-monitor)
# and the log (~/.local/state/spark-monitor) are not touched by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkMonitor
SLUG=spark-monitor
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
USER_MODE=0
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
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
      echo "Spark Monitor isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    for dir in "$HOME/.local/lib"; do
      rmdir --ignore-fail-on-non-empty "$dir" 2>/dev/null || true
    done
    refresh_menus "$DATA/applications"
    echo "Spark Monitor removed for $(id -un). Settings stay in ~/.config/$SLUG; delete that"
    echo "folder too if you don't want them."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo "Spark Monitor needs Python 3 with tkinter, which this system doesn't have." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi

  rm -rf -- "$LIB"
  install -d "$LIB/sparkmonitor" "$LIB/icons"
  install -m 0644 "$here"/sparkmonitor/*.py "$LIB/sparkmonitor/"
  install -m 0644 "$here/spark_monitor.py" "$here/spark-app.json" "$LIB/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$LIB/icons/"
  python3 -m compileall -q "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_monitor.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entry at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-monitor|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
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
  echo "Spark Monitor installed for $(id -un) in $LIB. Ctrl+Shift+Esc opens it in the"
  echo "Spark session. Remove it with:"
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
  echo "Spark Monitor removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter xrdb hwdata cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
  # sharper app icons in the Apps tab; it works without
  python3 -c 'from PIL import ImageTk' 2>/dev/null || \
    dnf -y install --setopt=install_weak_deps=False python3-pillow-tk || \
    echo "--- optional: no Pillow, app icons are scaled by Tk"
fi

rm -rf "$PREFIX"
install -d "$PREFIX/sparkmonitor" "$PREFIX/icons"
install -m 0644 "$here"/sparkmonitor/*.py "$PREFIX/sparkmonitor/"
install -m 0644 "$here/spark_monitor.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
python3 -m compileall -q "$PREFIX"

cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_monitor.py "\$@"
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
test -f "$PREFIX/sparkmonitor/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Monitor installed to $PREFIX."
