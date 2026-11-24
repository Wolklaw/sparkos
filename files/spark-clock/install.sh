#!/usr/bin/env bash
# Install Spark Clock, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test] [--no-service]    just you, into ~/.local; no root
#   bash install.sh --user --uninstall                   remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-clock] [--no-test]    system-wide, root
#   bash install.sh --uninstall                          remove the system-wide install, root
#
# --user        SparkOS keeps /usr read-only, so optional Spark apps install here. Needs only
#               what the SparkOS image has (Python 3 with tkinter and gobject).
# --no-service  --user only: don't start the background service now (the window can start it
#               later; it starts at every login once turned on).
# --deps        system-wide only: install what it needs with dnf first (Fedora).
# --no-test     skip the self-test at the end.
#
# The service (spark-clock.service, a systemd user unit) is what rings alarms and timers. It is
# started and enabled here. --uninstall stops and disables it. Your alarms and the log stay in
# ~/.config/spark-clock and ~/.local/state/spark-clock. Spark Clock is Linux only.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkClock
SLUG=spark-clock
UNIT=$SLUG.service
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
SERVICE=1
USER_MODE=0
UNINSTALL=0
STAGE=
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --stage) STAGE=$2; shift ;;
    --no-service) SERVICE=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
  if command -v kbuildsycoca6 >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    kbuildsycoca6 >/dev/null 2>&1 || true
  fi
}

copy_app() {   # $1: target folder
  install -d "$1/sparkclock" "$1/icons" "$1/sounds"
  install -m 0644 "$here"/sparkclock/*.py "$1/sparkclock/"
  install -m 0644 "$here"/sounds/*.wav "$1/sounds/"
  install -m 0644 "$here/spark_clock.py" "$here/spark-app.json" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
}

user_systemctl() {   # a failing systemctl never fails the install (no user bus in a container)
  command -v systemctl >/dev/null && systemctl --user "$@" 2>/dev/null
}

# Live updates (files/spark-apps): --stage DIR writes the app's folder exactly as the system
# install builds it (what goes in /usr/lib/$SLUG), and stops. CI packs that into the signed
# bundle, so the bundle and the image's built-in copy can't differ.
if [ -n "$STAGE" ]; then
  copy_app "$STAGE"
  find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
  exit 0
fi

# ─── Per user, no root ───────────────────────────────────────

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Clock isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    user_systemctl disable --now "$UNIT" || true
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    rmdir --ignore-fail-on-non-empty "$HOME/.local/lib" 2>/dev/null || true
    user_systemctl daemon-reload || true
    refresh_menus "$DATA/applications"
    echo "Spark Clock removed for $(id -un), and its service stopped. Your alarms stay in"
    echo "~/.config/$SLUG and the log in ~/.local/state/$SLUG; delete them too if you want."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo "Spark Clock needs Python 3 with tkinter, which this system doesn't have." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi
  if ! python3 -c 'import gi' 2>/dev/null; then
    echo "note: python3-gobject is missing, so the service can't ring (the window works)." >&2
  fi

  # a running service keeps the old code until it restarts; stop it while the files change
  user_systemctl stop "$UNIT" || true
  rm -rf -- "$LIB"
  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_clock.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entry at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-clock|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
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

  unit="$CONFIG/systemd/user/$UNIT"
  install -d "$(dirname "$unit")"
  case "$BIN" in *" "*) unit_bin="\"$BIN\"" ;; *) unit_bin=$BIN ;; esac
  sed "s|@BIN@|$unit_bin|" "$here/systemd/$UNIT" > "$unit"
  chmod 0644 "$unit"
  record "$unit"
  refresh_menus "$DATA/applications"

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  user_systemctl daemon-reload || true
  if [ "$SERVICE" = 1 ]; then
    if user_systemctl enable --now "$UNIT"; then
      echo "The service is on: alarms and timers ring with the window closed."
    else
      echo "Couldn't start the service here. Open Spark Clock and press TURN ON," >&2
      echo "or run:  systemctl --user enable --now $UNIT" >&2
    fi
  fi
  echo "Spark Clock installed for $(id -un) in $LIB."
  echo "Remove it with:  bash $here/install.sh --user --uninstall"
  exit 0
fi

# ─── System-wide, root ───────────────────────────────────────

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2
  exit 1
fi

if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  rm -f "/usr/share/spark-apps/$SLUG.json" /usr/bin/$SLUG "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg" "/usr/lib/systemd/user/$UNIT"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Clock removed from the system. Each user turns the service off with:"
  echo "  systemctl --user disable --now $UNIT"
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter python3-gobject pipewire-utils; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

rm -rf "$PREFIX"
copy_app "$PREFIX"

# Live updates: launch.py starts the newest verified live copy of this app, else the
# built-in one in $PREFIX (also what starts where Spark Apps isn't installed)
cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
[ -f /usr/lib/spark-apps/launch.py ] && exec /usr/bin/python3 -I /usr/lib/spark-apps/launch.py $SLUG "\$@"
exec /usr/bin/python3 $PREFIX/spark_clock.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG
install -Dm 0644 "$here/spark-app.json" "/usr/share/spark-apps/$SLUG.json"

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -d /usr/lib/systemd/user
sed "s|@BIN@|/usr/bin/$SLUG|" "$here/systemd/$UNIT" > "/usr/lib/systemd/user/$UNIT"
chmod 0644 "/usr/lib/systemd/user/$UNIT"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -f "$PREFIX/sparkclock/app.py"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Clock installed to $PREFIX."
echo "Each user starts the service once (or presses TURN ON in the window):"
echo "  systemctl --user enable --now $UNIT"
