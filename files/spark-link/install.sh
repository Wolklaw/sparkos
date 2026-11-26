#!/usr/bin/env bash
# Install Spark Link, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test]          just you, into ~/.local; no root
#   bash install.sh --user --uninstall          remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-link] [--no-test]    system-wide, root
#   bash install.sh --uninstall                 remove the system-wide install, root
#
# --user     SparkOS keeps /usr read-only, so optional Spark apps install here. Needs only
#            what the SparkOS image has (Python 3 with tkinter and ssl, the openssl command,
#            GObject for D-Bus); nothing is downloaded.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# Installs the window, the background service as a systemd user unit (not switched on: the
# window enables it for you the first time you pair a phone), Spark Files' "Send to phone", and
# (system-wide) the firewalld service definition. Keys, paired phones and settings
# (~/.local/share/spark-link, ~/.config/spark-link) are not touched by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkLink
SLUG=spark-link
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
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
}

copy_app() {   # $1: where the program goes
  rm -rf -- "$1"
  install -d "$1/sparklink" "$1/icons"
  install -m 0644 "$here"/sparklink/*.py "$1/sparklink/"
  install -m 0644 "$here/spark_link.py" "$here/spark-app.json" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
}

# ─── Per user, no root ───────────────────────────────────────

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  CONF=${XDG_CONFIG_HOME:-$HOME/.config}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  UNIT=$CONF/systemd/user/$SLUG.service
  MANIFEST=$LIB/installed-files

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Link isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    # stop the background service and take it out of the login
    if command -v systemctl >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
      systemctl --user disable --now "$SLUG.service" >/dev/null 2>&1 || true
    fi
    pkill -u "$(id -u)" -f "$LIB/spark_link.py --service" 2>/dev/null || true
    rm -f -- "$CONF/systemd/user/graphical-session.target.wants/$SLUG.service"
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    for dir in "$CONF/systemd/user/graphical-session.target.wants" "$CONF/systemd/user" \
               "$CONF/systemd" "$DATA/kio/servicemenus" "$DATA/kio" "$HOME/.local/lib"; do
      rmdir --ignore-fail-on-non-empty "$dir" 2>/dev/null || true
    done
    if command -v systemctl >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
      systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi
    refresh_menus "$DATA/applications"
    echo "Spark Link removed for $(id -un). Your key, paired phones and settings stay in"
    echo "~/.local/share/$SLUG and ~/.config/$SLUG; delete those folders too if you want them gone."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter, ssl' 2>/dev/null; then
    echo "Spark Link needs Python 3 with tkinter and ssl, which this system doesn't have." >&2
    echo "On SparkOS they come with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi
  if ! command -v openssl >/dev/null && ! python3 -c 'import cryptography' 2>/dev/null; then
    echo "Spark Link needs the openssl command to make its key." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install openssl" >&2
    exit 1
  fi

  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_link.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point everything at the full path
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  sed "s|^Exec=spark-link|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
  chmod 0644 "$desktop"
  record "$desktop"
  # Spark Files' right-click "Send to phone" (a service menu; kept executable, as the service menu format asks)
  menu="$DATA/kio/servicemenus/$APP_ID.send.desktop"
  install -d "$DATA/kio/servicemenus"
  sed "s|^Exec=spark-link|Exec=$exec_bin|" "$here/$APP_ID.send.desktop" > "$menu"
  chmod 0755 "$menu"
  record "$menu"
  install -d "$(dirname "$UNIT")"
  sed "s|@BIN@|$exec_bin|" "$here/$SLUG.service" > "$UNIT"
  chmod 0644 "$UNIT"
  record "$UNIT"
  for size in $SIZES; do
    target="$DATA/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm 0644 "$here/icons/$SLUG-$size.png" "$target"
    record "$target"
  done
  target="$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
  install -Dm 0644 "$here/icons/$SLUG.svg" "$target"
  record "$target"
  if command -v systemctl >/dev/null && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  refresh_menus "$DATA/applications"

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  echo "Spark Link installed for $(id -un) in $LIB. Open it from the menu and pair your phone"
  echo "(Soot on the phone, Link to PC). Remove it with:"
  echo "  bash $here/install.sh --user --uninstall"
  exit 0
fi

# ─── System-wide, root ───────────────────────────────────────

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2
  exit 1
fi

SYSTEM_FILES="/usr/bin/$SLUG /usr/share/applications/$APP_ID.desktop
/usr/share/kio/servicemenus/$APP_ID.send.desktop /usr/lib/systemd/user/$SLUG.service
/usr/lib/firewalld/services/$SLUG.xml /usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

if [ "$UNINSTALL" = 1 ]; then
  rm -rf -- "$PREFIX"
  for f in $SYSTEM_FILES; do rm -f -- "$f"; done
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Link removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter python3-gobject-base openssl glib2 cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

copy_app "$PREFIX"
cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_link.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
install -Dm 0644 "$here/$APP_ID.send.desktop" "/usr/share/kio/servicemenus/$APP_ID.send.desktop"
install -d /usr/lib/systemd/user
sed "s|@BIN@|/usr/bin/$SLUG|" "$here/$SLUG.service" > "/usr/lib/systemd/user/$SLUG.service"
chmod 0644 "/usr/lib/systemd/user/$SLUG.service"
install -Dm 0644 "$here/$SLUG.firewalld.xml" "/usr/lib/firewalld/services/$SLUG.xml"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

for f in $SYSTEM_FILES; do test -e "$f"; done
test -f "$PREFIX/sparklink/service.py"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Link installed to $PREFIX."
