#!/usr/bin/env bash
# Install Spark Games. The SparkOS image build installs it system-wide
# (files/scripts/spark-games.sh runs --deps). It also installs for one user, with no root, for
# other systems and the future Spark Portal:
#
#   bash files/spark-games/install.sh --user              install to ~/.local
#   bash files/spark-games/install.sh --user --uninstall  remove exactly what that installed
#
# System-wide, as root (what the image build runs):
#
#   bash files/spark-games/install.sh [--deps] [--prefix /usr/lib/spark-games] [--no-test]
#   bash files/spark-games/install.sh --uninstall
#
# --deps     (system-wide only) install what it needs with dnf, skipping what's already there.
#            --user can't add system packages (SparkOS's /usr is read-only); it checks that
#            Python, Tk and Pillow are there and stops with a clear message if not.
# --no-test  skip the self-test at the end.
#
# Installed: the program (with its test fixtures, for --self-test), a spark-games command, the
# desktop entry and the icons. The list of installed files is kept in <prefix>/installed-files,
# which --uninstall reads. Settings, playtime and cache in your home folder are left alone.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkGames
SLUG=spark-games
USER_MODE=0
UNINSTALL=0
DEPS=0
TEST=1
PREFIX=
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$USER_MODE" = 1 ]; then
  if [ "$(id -u)" = 0 ]; then
    echo "install.sh: --user installs for the person running it; run it without sudo." >&2
    exit 1
  fi
  if [ "$DEPS" = 1 ]; then
    echo "install.sh: --deps needs root and doesn't go with --user." >&2
    exit 2
  fi
  : "${HOME:?HOME is not set}"
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  PREFIX=${PREFIX:-$HOME/.local/lib/$SLUG}
  BIN=$HOME/.local/bin
  APPS=$DATA/applications
  ICONS=$DATA/icons/hicolor
else
  PREFIX=${PREFIX:-/usr/lib/$SLUG}
  BIN=/usr/bin
  APPS=/usr/share/applications
  ICONS=/usr/share/icons/hicolor
fi
MANIFEST=$PREFIX/installed-files

refresh_menus() {
  if [ "$USER_MODE" = 1 ]; then
    # The shell notices new files in ~/.local/share by itself. The system cache tools are
    # skipped: they'd leave cache files in ~/.local that uninstall would then have to guess
    # about.
    :
  else
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f "$ICONS" || true
  fi
}

# ─── Uninstall ────────────────────────────────────────────────
if [ "$UNINSTALL" = 1 ]; then
  if [ ! -f "$MANIFEST" ]; then
    echo "Spark Games isn't installed in $PREFIX (no $MANIFEST)."
    exit 0
  fi
  while IFS= read -r path; do
    case "$path" in
      "$PREFIX"/*) ;;                    # the program folder goes in one piece below
      /*) rm -f -- "$path" ;;
    esac
  done < "$MANIFEST"
  rm -rf -- "$PREFIX"
  refresh_menus
  echo "Spark Games removed from $PREFIX."
  if [ "$USER_MODE" = 1 ]; then
    echo "Your settings, playtime and cache are still in ~/.config/$SLUG, ~/.local/share/$SLUG and ~/.cache/$SLUG; delete them if you don't want them."
  fi
  exit 0
fi

# ─── What it needs ────────────────────────────────────────────
if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter python3-pillow python3-pillow-tk xdg-utils \
             cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
fi

PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
  echo "install.sh: python3 is missing." >&2
  exit 1
fi
if ! problem=$("$PYTHON" - <<'PY' 2>&1
import sys
missing = []
for name in ('tkinter', 'sqlite3', 'PIL.Image', 'PIL.ImageTk'):
    try:
        __import__(name)
    except Exception:
        missing.append(name)
if sys.version_info < (3, 9):
    missing.append('Python 3.9 or newer')
if missing:
    print(', '.join(missing))
    sys.exit(1)
PY
); then
  echo "install.sh: Spark Games needs these Python parts, which are missing: $problem" >&2
  if [ "$USER_MODE" = 1 ]; then
    echo "SparkOS includes them; on another system, install python3-tkinter and python3-pillow-tk." >&2
  fi
  exit 1
fi

# ─── The program ──────────────────────────────────────────────
installed=()
put() {   # mode source destination
  install -Dm "$1" "$2" "$3"
  installed+=("$3")
}

rm -rf -- "$PREFIX"
install -d "$PREFIX/sparkgames" "$PREFIX/icons"
install -m 0644 "$here"/sparkgames/*.py "$PREFIX/sparkgames/"
install -m 0644 "$here/spark_games.py" "$PREFIX/spark_games.py"
install -m 0644 "$here/spark-app.json" "$PREFIX/spark-app.json"
install -m 0644 "$here/icons/$SLUG-256.png" "$PREFIX/icons/"
cp -R "$here/tests/fixtures" "$PREFIX/fixtures"
"$PYTHON" -m compileall -q "$PREFIX/sparkgames" "$PREFIX/spark_games.py" >/dev/null || true

install -d "$BIN"
cat > "$BIN/$SLUG" <<EOF
#!/bin/sh
exec "$PYTHON" "$PREFIX/spark_games.py" "\$@"
EOF
chmod 0755 "$BIN/$SLUG"
installed+=("$BIN/$SLUG")

# Desktop entry: a user install points at the full path, since ~/.local/bin may not be on the
# desktop session's PATH.
tmp_desktop=$(mktemp)
if [ "$USER_MODE" = 1 ]; then
  sed "s|^Exec=$SLUG|Exec=\"$BIN/$SLUG\"|" "$here/$APP_ID.desktop" > "$tmp_desktop"
else
  cp "$here/$APP_ID.desktop" "$tmp_desktop"
fi
put 0644 "$tmp_desktop" "$APPS/$APP_ID.desktop"
rm -f "$tmp_desktop"
for size in 16 22 24 32 48 64 128 256 512; do
  put 0644 "$here/icons/$SLUG-$size.png" "$ICONS/${size}x${size}/apps/$APP_ID.png"
done
put 0644 "$here/icons/$SLUG.svg" "$ICONS/scalable/apps/$APP_ID.svg"

printf '%s\n' "${installed[@]}" > "$MANIFEST"
refresh_menus

# Fail loudly if anything is missing
test -x "$BIN/$SLUG"
test -f "$PREFIX/sparkgames/app.py"
test -f "$APPS/$APP_ID.desktop"
"$BIN/$SLUG" --version

if [ "$TEST" = 1 ]; then
  # HOME may be read-only in a build container; anything the test writes goes to a scratch folder
  scratch=$(mktemp -d)
  XDG_STATE_HOME="$scratch" XDG_CONFIG_HOME="$scratch" XDG_CACHE_HOME="$scratch" \
    XDG_DATA_HOME="$scratch" "$BIN/$SLUG" --self-test
  rm -rf "$scratch"
fi

echo "Spark Games installed to $PREFIX."
if [ "$USER_MODE" = 1 ]; then
  case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Note: $BIN isn't on your PATH, so type $BIN/$SLUG in a terminal (the app menu works as is)." ;;
  esac
fi
