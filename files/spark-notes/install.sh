#!/usr/bin/env bash
# Install Spark Notes, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test] [--no-start]   just you, into ~/.local; no root
#   bash install.sh --user --uninstall                remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-notes] [--no-test]   system-wide, root
#   bash install.sh --uninstall                       remove the system-wide install, root
#
# --user     SparkOS keeps /usr read-only, so this installs into ~/.local. Needs Python 3 with
#            PyGObject and GTK 4, which the SparkOS image has, and wl-clipboard for the clipboard
#            history. Nothing is downloaded. It also installs the clipboard watcher as a user
#            service and starts it (--no-start to leave it off). The Meta+V shortcut only comes
#            with the system-wide install (the desktop reads it from there); per user, start the
#            clipboard from the app menu (right-click Spark Notes) or run: spark-notes --clipboard
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# Meta+V is bound by the Spark compositor in the image (files/scripts/spark-notes.sh sets up the
# rest), not by this script. Notes (~/.local/share/spark-notes), settings
# (~/.config/spark-notes) and the log (~/.local/state/spark-notes) are not touched by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkNotes
CLIP_ID=dev.wolklaw.SparkNotes.Clipboard
SLUG=spark-notes
UNIT=spark-notes-clipboard.service
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
START=1
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
    --no-start) START=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"
GI_CHECK='import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk'

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
}

user_bus() {   # true when systemctl --user can talk to a running user manager
  command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1
}

copy_app() {   # $1: destination folder
  install -d "$1/sparknotes" "$1/icons"
  install -m 0644 "$here"/sparknotes/*.py "$1/sparknotes/"
  install -m 0644 "$here/spark_notes.py" "$here/spark-app.json" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
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
  UNIT_PATH=$CONFIG/systemd/user/$UNIT

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Notes isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    if user_bus; then
      systemctl --user disable --now "$UNIT" >/dev/null 2>&1 || true
    fi
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    rmdir --ignore-fail-on-non-empty "$HOME/.local/lib" 2>/dev/null || true
    user_bus && systemctl --user daemon-reload >/dev/null 2>&1 || true
    refresh_menus "$DATA/applications"
    echo "Spark Notes removed for $(id -un). Your notes stay in $DATA/$SLUG, settings in"
    echo "$CONFIG/$SLUG and the log in ~/.local/state/$SLUG; delete those folders too if you don't"
    echo "want them."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c "$GI_CHECK" 2>/dev/null; then
    echo "Spark Notes needs Python 3 with GTK 4, which this system doesn't have." >&2
    echo "On SparkOS they come with the image; on Fedora: sudo dnf install python3-gobject gtk4 wl-clipboard" >&2
    exit 1
  fi
  if ! command -v wl-paste >/dev/null || ! command -v wl-copy >/dev/null; then
    echo "note: wl-clipboard is missing, so the clipboard history won't work (notes will)."
    echo "      On Fedora: sudo dnf install wl-clipboard"
  fi

  rm -rf -- "$LIB"
  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_notes.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entries at the full path
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  desktop="$DATA/applications/$APP_ID.desktop"
  sed -e "s|^Exec=spark-notes|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
  chmod 0644 "$desktop"
  record "$desktop"
  # the popup entry carries Meta+V; per user it is left out so it can't fight another
  # desktop's Meta+V for the key. The app menu action still opens the popup.
  for size in $SIZES; do
    target="$DATA/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm 0644 "$here/icons/$SLUG-$size.png" "$target"
    record "$target"
  done
  target="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
  install -Dm 0644 "$here/icons/$SLUG.svg" "$target"
  record "$target"

  # the clipboard watcher, as a user service
  install -d "$(dirname "$UNIT_PATH")"
  sed -e "s|@BIN@|$BIN|" "$here/$UNIT" > "$UNIT_PATH"
  chmod 0644 "$UNIT_PATH"
  record "$UNIT_PATH"
  refresh_menus "$DATA/applications"

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  if user_bus; then
    systemctl --user daemon-reload
    if [ "$START" = 1 ]; then
      systemctl --user enable --now "$UNIT" >/dev/null 2>&1 \
        && echo "The clipboard watcher is on (systemctl --user status $UNIT)." \
        || echo "note: couldn't start the clipboard watcher; run: systemctl --user enable --now $UNIT"
    fi
  else
    echo "note: no user service manager here; the watcher starts at your next login."
  fi
  echo "Spark Notes installed for $(id -un) in $LIB. It's in the app menu. Remove it with:"
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
  rm -f "/usr/share/spark-apps/$SLUG.json" /usr/bin/$SLUG "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/applications/$CLIP_ID.desktop" \
        "/usr/lib/systemd/user/$UNIT" "/usr/lib/systemd/user/graphical-session.target.wants/$UNIT" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Notes removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-gobject gobject-introspection gtk4 wl-clipboard; do
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
exec /usr/bin/python3 $PREFIX/spark_notes.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG
install -Dm 0644 "$here/spark-app.json" "/usr/share/spark-apps/$SLUG.json"

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
install -Dm 0644 "$here/$CLIP_ID.desktop" "/usr/share/applications/$CLIP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

# the watcher: a user service every login starts. The "enabled" link goes in /usr (next to the
# other units the image enables), so it needs no /etc merge and works with no systemd running.
install -d /usr/lib/systemd/user/graphical-session.target.wants
sed -e "s|@BIN@|/usr/bin/$SLUG|" "$here/$UNIT" > "/usr/lib/systemd/user/$UNIT"
chmod 0644 "/usr/lib/systemd/user/$UNIT"
ln -sfn "../$UNIT" "/usr/lib/systemd/user/graphical-session.target.wants/$UNIT"

command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -f "$PREFIX/sparknotes/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
test -f "/usr/lib/systemd/user/$UNIT"
test -L "/usr/lib/systemd/user/graphical-session.target.wants/$UNIT"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Notes installed to $PREFIX."
