#!/usr/bin/env bash
# Install or remove Spark Welcome. From anywhere:
#
#   bash files/spark-welcome/install.sh --user [--no-test]       for you only, no root
#   bash files/spark-welcome/install.sh --user --uninstall       remove that again
#   sudo bash files/spark-welcome/install.sh [--deps] [--prefix /usr/lib/spark-welcome] [--no-test]
#   sudo bash files/spark-welcome/install.sh --uninstall [--prefix ...]
#
# --user     installs to ~/.local/lib/spark-welcome, ~/.local/bin/spark-welcome,
#            ~/.local/share/applications, ~/.local/share/icons and ~/.config/autostart.
#            Works on a running SparkOS, where /usr is read-only. Needs only what the SparkOS
#            image already has (Python 3 with Tk, flatpak, udisksctl, lsblk).
# --deps     system-wide only: install what it needs with dnf, skipping anything already there.
#            The SparkOS image build uses this (files/scripts/spark-welcome.sh).
# --no-test  skip the self-test at the end.
# --uninstall removes exactly the files this script installs. Your settings
#            (~/.config/spark-welcome) and log (~/.local/state/spark-welcome) stay.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkWelcome
SLUG=spark-welcome
SIZES="16 22 24 32 48 64 128 256 512"
USER_MODE=0
UNINSTALL=0
DEPS=0
TEST=1
PREFIX=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$USER_MODE" = 1 ]; then
  if [ "$(id -u)" = 0 ]; then
    echo "install.sh: --user installs for the account that runs it; run it as yourself, not root." >&2
    exit 1
  fi
  if [ "$DEPS" = 1 ]; then
    echo "install.sh: --deps needs root and can't be used with --user (on SparkOS, /usr is read-only)." >&2
    exit 2
  fi
  data=${XDG_DATA_HOME:-$HOME/.local/share}
  config=${XDG_CONFIG_HOME:-$HOME/.config}
  PREFIX=${PREFIX:-$HOME/.local/lib/$SLUG}
  BIN=$HOME/.local/bin/$SLUG
  APPS=$data/applications
  ICONS=$data/icons/hicolor
  AUTOSTART=$config/autostart
else
  if [ "$(id -u)" != 0 ]; then
    echo "install.sh: the system-wide install needs root. For just your account, use --user." >&2
    exit 1
  fi
  PREFIX=${PREFIX:-/usr/lib/$SLUG}
  BIN=/usr/bin/$SLUG
  APPS=/usr/share/applications
  ICONS=/usr/share/icons/hicolor
  AUTOSTART=/etc/xdg/autostart
fi

# Everything this script puts outside $PREFIX. --uninstall removes exactly these and $PREFIX.
installed_files() {
  echo "$BIN"
  echo "$APPS/$APP_ID.desktop"
  echo "$AUTOSTART/$APP_ID.desktop"
  for size in $SIZES; do echo "$ICONS/${size}x${size}/apps/$APP_ID.png"; done
  echo "$ICONS/scalable/apps/$APP_ID.svg"
}

remove_prefix() {
  # only a folder that is clearly ours
  if [ -d "$PREFIX" ]; then
    if [ -f "$PREFIX/spark_welcome.py" ] || [ -z "$(ls -A "$PREFIX")" ]; then
      rm -rf "$PREFIX"
    else
      echo "install.sh: $PREFIX doesn't look like Spark Welcome; not removing it." >&2
      exit 1
    fi
  fi
}

refresh_menus() {
  if [ "$USER_MODE" = 0 ]; then
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f "$ICONS" || true
  fi
  # Plasma picks up new and removed entries by itself; this just makes it immediate.
  if [ "$USER_MODE" = 1 ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
  fi
}

if [ "$UNINSTALL" = 1 ]; then
  while read -r f; do
    if [ -e "$f" ] || [ -L "$f" ]; then rm -f "$f" && echo "removed $f"; fi
    # icon folders left empty (hicolor/16x16/apps...); standard folders like ~/.local/bin stay
    case "$f" in
      "$ICONS"/*)
        d=$(dirname "$f")
        while [ "$d" != "$ICONS" ] && rmdir "$d" 2>/dev/null; do d=$(dirname "$d"); done ;;
    esac
  done < <(installed_files)
  if [ -d "$PREFIX" ]; then remove_prefix && echo "removed $PREFIX"; fi
  refresh_menus
  if [ "$USER_MODE" = 1 ]; then
    echo "Spark Welcome removed. Your settings in ${XDG_CONFIG_HOME:-$HOME/.config}/$SLUG and the log in ${XDG_STATE_HOME:-$HOME/.local/state}/$SLUG were left; delete them if you want."
  else
    echo "Spark Welcome removed."
  fi
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter flatpak udisks2 util-linux xdg-user-dirs xdg-utils \
             cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
  # The checks also use vulkaninfo, wpctl, lpstat, scanimage, nmcli, bluetoothctl and
  # rpm-ostree when they're there (Bazzite has them); without them a check says it couldn't
  # look, so they aren't pulled in here.
fi

PYTHON=/usr/bin/python3
[ -x "$PYTHON" ] || PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
  echo "install.sh: Python 3 isn't installed." >&2
  exit 1
fi

# The program
remove_prefix
install -d "$PREFIX/sparkwelcome" "$PREFIX/icons"
install -m 0644 "$here"/sparkwelcome/*.py "$here/sparkwelcome/apps.json" "$PREFIX/sparkwelcome/"
install -m 0644 "$here/spark_welcome.py" "$here/spark-app.json" "$PREFIX/"
install -m 0644 "$here/icons/$SLUG-256.png" "$here"/icons/sparkos-bot-*.png "$PREFIX/icons/"
"$PYTHON" -m compileall -q "$PREFIX" >/dev/null || true

install -d "$(dirname "$BIN")"
sh_quote() {   # 'single-quoted', for the wrapper script
  local q="'\\''"
  printf "'%s'" "${1//\'/$q}"
}
printf '#!/bin/sh\nexec %s %s "$@"\n' "$(sh_quote "$PYTHON")" \
  "$(sh_quote "$PREFIX/spark_welcome.py")" > "$BIN"
chmod 0755 "$BIN"

# Desktop entries: the menu entry, and the autostart entry that opens it once at first login.
# Per user, ~/.local/bin may not be on the desktop's PATH, so the entries use the full path.
exec_line() {   # desktop-entry Exec value for "$BIN $1"
  if [ "$USER_MODE" = 1 ]; then
    local quoted=${BIN//\\/\\\\}
    quoted=${quoted//\"/\\\"}
    quoted=${quoted//\$/\\\$}
    quoted=${quoted//\`/\\\`}
    printf '"%s"%s' "$quoted" "${1:+ $1}"
  else
    printf '%s%s' "$SLUG" "${1:+ $1}"
  fi
}
write_entry() {   # source, target, Exec value
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      Exec=*) printf 'Exec=%s\n' "$3" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$1" > "$2"
}
install -d "$APPS" "$AUTOSTART"
write_entry "$here/$APP_ID.desktop" "$APPS/$APP_ID.desktop" "$(exec_line '')"
write_entry "$here/$APP_ID-autostart.desktop" "$AUTOSTART/$APP_ID.desktop" \
  "$(exec_line --first-login)"
chmod 0644 "$APPS/$APP_ID.desktop" "$AUTOSTART/$APP_ID.desktop"
for size in $SIZES; do
  install -Dm 0644 "$here/icons/$SLUG-$size.png" "$ICONS/${size}x${size}/apps/$APP_ID.png"
done
install -Dm 0644 "$here/icons/$SLUG.svg" "$ICONS/scalable/apps/$APP_ID.svg"
refresh_menus

# Fail loudly if anything is missing
while read -r f; do test -e "$f" || { echo "install.sh: $f is missing" >&2; exit 1; }; done \
  < <(installed_files)
test -f "$PREFIX/sparkwelcome/app.py"
"$BIN" --version

if [ "$TEST" = 1 ]; then
  if [ "$USER_MODE" = 1 ]; then
    "$BIN" --self-test
  else
    # HOME may be unset or read-only in a build container.
    scratch=$(mktemp -d)
    XDG_STATE_HOME="$scratch" XDG_CONFIG_HOME="$scratch" XDG_CACHE_HOME="$scratch" \
      "$BIN" --self-test
    rm -rf "$scratch"
  fi
fi
if [ "$USER_MODE" = 1 ]; then
  echo "Spark Welcome installed for $(id -un) in $PREFIX. It opens at your next login once,"
  echo "and it's in the app menu. Remove it with: bash $here/install.sh --user --uninstall"
else
  echo "Spark Welcome installed to $PREFIX."
fi
