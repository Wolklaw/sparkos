#!/usr/bin/env bash
# Install Spark Update, for the whole system (the SparkOS image) or for one user (no root).
#
#   bash install.sh [--deps] [--prefix /usr/lib/spark-update] [--no-test]   system-wide, root
#   bash install.sh --uninstall                 remove the system-wide install, root
#   bash install.sh --user [--no-test]          just you, into ~/.local; no root
#   bash install.sh --user --uninstall          remove exactly what --user installed
#
# System-wide is the real thing: the hourly root timer that downloads and stages SparkOS images
# (spark-update.timer), the per-user timer for Flatpak apps and the notification
# (spark-update-user.timer, enabled for every user), the pkexec helper for roll back and
# settings, and its polkit files. files/scripts/spark-update.sh runs this in the image build.
# --user installs the window, the notification and your own Flatpak updates; downloading
# SparkOS images in the background needs root, so that part comes only with the image.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# Settings (/etc/sparkos/update.conf, ~/.config/spark-update), state and logs are not touched
# by --uninstall.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkUpdate
SLUG=spark-update
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
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

copy_app() {   # $1: the folder the app goes into
  rm -rf -- "$1"
  install -d "$1/sparkupdate" "$1/icons"
  install -m 0644 "$here"/sparkupdate/*.py "$1/sparkupdate/"
  install -m 0644 "$here/spark_update.py" "$here/spark-app.json" "$here/README.md" "$1/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$1/icons/"
  python3 -m compileall -q "$1"
}

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
  UNITS=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files

  user_systemctl() {   # best effort: there is no user manager in a container or over su
    if command -v systemctl >/dev/null && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
      systemctl --user "$@" >/dev/null 2>&1 || true
    fi
  }

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Update isn't installed for $(id -un) (no $MANIFEST)."
      exit 0
    fi
    user_systemctl disable --now spark-update-user.timer
    while IFS= read -r path; do
      case "$path" in
        "$HOME"/*) rm -f -- "$path" ;;              # never anything outside your home
        *) echo "skipping $path (outside $HOME)" >&2 ;;
      esac
    done < "$MANIFEST"
    rm -rf -- "$LIB"
    for dir in "$UNITS/timers.target.wants" "$UNITS" "$HOME/.local/lib"; do
      rmdir --ignore-fail-on-non-empty "$dir" 2>/dev/null || true
    done
    user_systemctl daemon-reload
    refresh_menus "$DATA/applications"
    echo "Spark Update removed for $(id -un). Settings stay in ~/.config/$SLUG and the log in"
    echo "~/.local/state/$SLUG; delete those folders too if you don't want them."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo "Spark Update needs Python 3 with tkinter, which this system doesn't have." >&2
    echo "On SparkOS it comes with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi

  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_update.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac

  # ~/.local/bin may not be on the desktop session's PATH: point at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  sed "s|^Exec=spark-update|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
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

  # the user timer: your Flatpak apps and the notification
  install -d "$UNITS/timers.target.wants"
  sed -e "s|^ExecStart=/usr/bin/spark-update|ExecStart=$exec_bin|" \
      -e "s|file:///usr/lib/spark-update/|file://$LIB/|" \
      "$here/systemd/spark-update-user.service" > "$UNITS/spark-update-user.service"
  install -m 0644 "$here/systemd/spark-update-user.timer" "$UNITS/spark-update-user.timer"
  ln -sfn ../spark-update-user.timer "$UNITS/timers.target.wants/spark-update-user.timer"
  record "$UNITS/spark-update-user.service"
  record "$UNITS/spark-update-user.timer"
  record "$UNITS/timers.target.wants/spark-update-user.timer"
  user_systemctl daemon-reload
  user_systemctl start spark-update-user.timer
  refresh_menus "$DATA/applications"

  test -x "$BIN"
  "$BIN" --version
  if [ "$TEST" = 1 ]; then
    "$BIN" --self-test
  fi
  echo "Spark Update installed for $(id -un) in $LIB. Background downloads of SparkOS itself"
  echo "come with the SparkOS image. Remove it with:"
  echo "  bash $here/install.sh --user --uninstall"
  exit 0
fi

# ─── System-wide, root ───────────────────────────────────────

if [ "$(id -u)" != 0 ]; then
  echo "install.sh: system-wide needs root. For just you, without root: install.sh --user" >&2
  exit 1
fi

SYSTEM_UNITS=/usr/lib/systemd/system
USER_UNITS=/usr/lib/systemd/user

enable_units() {   # works in an image build too (no running systemd needed)
  if command -v systemctl >/dev/null; then
    systemctl enable spark-update.timer
    systemctl --global enable spark-update-user.timer
  else
    install -d /etc/systemd/system/timers.target.wants /etc/systemd/user/timers.target.wants
    ln -sfn "$SYSTEM_UNITS/spark-update.timer" /etc/systemd/system/timers.target.wants/spark-update.timer
    ln -sfn "$USER_UNITS/spark-update-user.timer" /etc/systemd/user/timers.target.wants/spark-update-user.timer
  fi
}

if [ "$UNINSTALL" = 1 ]; then
  if command -v systemctl >/dev/null; then
    systemctl disable spark-update.timer 2>/dev/null || true
    systemctl --global disable spark-update-user.timer 2>/dev/null || true
  fi
  rm -f /etc/systemd/system/timers.target.wants/spark-update.timer \
        /etc/systemd/user/timers.target.wants/spark-update-user.timer
  rm -rf -- "$PREFIX"
  rm -f /usr/bin/$SLUG /usr/libexec/spark-update-helper \
        "$SYSTEM_UNITS/spark-update.service" "$SYSTEM_UNITS/spark-update.timer" \
        "$SYSTEM_UNITS/spark-update-now@.service" \
        "$USER_UNITS/spark-update-user.service" "$USER_UNITS/spark-update-user.timer" \
        "/usr/share/polkit-1/actions/$APP_ID.policy" /usr/share/polkit-1/rules.d/50-spark-update.rules \
        "/usr/share/applications/$APP_ID.desktop" \
        "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  for size in $SIZES; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
  done
  refresh_menus /usr/share/applications
  echo "Spark Update removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  # notify-send (libnotify) shows the notification; pkexec (polkit) runs the helper
  for pkg in python3 python3-tkinter libnotify polkit cascadia-mono-fonts; do
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
exec /usr/bin/python3 $PREFIX/spark_update.py "\$@"
EOF
chmod 0755 /usr/bin/$SLUG

# the root helper: -I, and the package only from the root-owned prefix
install -d /usr/libexec
sed "s|^LIB = .*|LIB = '$PREFIX'|" "$here/spark-update-helper" > /usr/libexec/spark-update-helper
chmod 0755 /usr/libexec/spark-update-helper
install -Dm 0644 "$here/polkit/$APP_ID.policy" "/usr/share/polkit-1/actions/$APP_ID.policy"
install -Dm 0644 "$here/polkit/50-spark-update.rules" /usr/share/polkit-1/rules.d/50-spark-update.rules

for unit in spark-update.service spark-update.timer spark-update-now@.service; do
  install -Dm 0644 "$here/systemd/$unit" "$SYSTEM_UNITS/$unit"
done
for unit in spark-update-user.service spark-update-user.timer; do
  install -Dm 0644 "$here/systemd/$unit" "$USER_UNITS/$unit"
done
enable_units

install -Dm 0644 "$here/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" \
    "/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true

test -x /usr/bin/$SLUG
test -x /usr/libexec/spark-update-helper
test -f "$PREFIX/sparkupdate/app.py"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Update installed to $PREFIX."
