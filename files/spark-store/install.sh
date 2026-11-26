#!/usr/bin/env bash
# Install Spark Store, for one user (no root) or for the whole system.
#
#   bash install.sh --user [--no-test]          just you, into ~/.local; no root
#   bash install.sh --user --uninstall          remove exactly what --user installed
#   bash install.sh [--deps] [--prefix /usr/lib/spark-store] [--no-test]    system-wide, root
#   bash install.sh --uninstall                 remove the system-wide install, root
#   bash install.sh --sources DIR               copy the optional Spark apps' sources into DIR
#   bash install.sh --optional                  list the optional Spark apps
#
# --user     SparkOS keeps /usr read-only, so optional Spark apps install here. Needs only
#            what the SparkOS image has (Python 3 with tkinter, flatpak); nothing is downloaded.
# --deps     system-wide only: install what it needs with dnf first (Fedora; the image build).
# --no-test  skip the self-test at the end.
#
# The Store lists the Spark apps from their spark-app.json files: this copies the ones in the
# sibling folders (files/spark-*/ in the SparkOS repo) and their icons into spark-apps/.
# Its desktop entry offers to open .flatpakref files and appstream:// links, but neither mode
# makes it the default for them: the SparkOS image decides that (sparkos-defaults.sh).
# Settings (~/.config/spark-store) and the catalog index (~/.cache/spark-store) are not
# touched by --uninstall.
#
# Optional Spark apps: a sibling folder files/spark-<name>/ with install.sh and spark-app.json
# is optional when no image build step installs it, that is when files/scripts/spark-<name>.sh
# doesn't exist. Its spark-app.json may say so too ("optional": true); if it says the opposite
# ("optional": false or "in_image": true), this stops with an error. --sources copies each
# optional app's folder, without tests/, __pycache__ and make_icons.py, into DIR/<slug>
# (the image build: /usr/share/spark-store/sources). Nothing is installed: the Store installs
# an app from there for one user (install.sh --user) when they click Install.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
APP_ID=dev.wolklaw.SparkStore
SLUG=spark-store
PREFIX=/usr/lib/$SLUG
DEPS=0
TEST=1
USER_MODE=0
UNINSTALL=0
SOURCES=
LIST_OPTIONAL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --deps) DEPS=1 ;;
    --no-test) TEST=0 ;;
    --prefix) PREFIX=$2; shift ;;
    --sources) SOURCES=${2:?--sources needs a folder}; shift ;;
    --optional) LIST_OPTIONAL=1 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
SIZES="16 22 24 32 48 64 128 256 512"

refresh_menus() {   # $1: the applications folder
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$1" 2>/dev/null || true
}

# The program, and every Spark app's spark-app.json + icon from the sibling folders
copy_app() {   # $1: destination folder
  local dest=$1 dir json slug icon
  install -d "$dest/sparkstore" "$dest/icons" "$dest/spark-apps"
  install -m 0644 "$here"/sparkstore/*.py "$here"/sparkstore/*.json "$dest/sparkstore/"
  install -m 0644 "$here/spark_store.py" "$here/spark-app.json" "$dest/"
  install -m 0644 "$here/icons/$SLUG-64.png" "$here/icons/$SLUG-256.png" "$dest/icons/"
  for dir in "$here"/../spark-*/; do
    json="$dir/spark-app.json"
    [ -f "$json" ] || continue
    slug=$(basename "$dir")
    [ "$slug" = "$SLUG" ] && continue
    install -d "$dest/spark-apps/$slug"
    install -m 0644 "$json" "$dest/spark-apps/$slug/spark-app.json"
    icon=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("icon") or "")' "$json" 2>/dev/null || true)
    if [ -n "$icon" ] && [ -f "$dir/$icon" ]; then
      install -m 0644 "$dir/$icon" "$dest/spark-apps/$slug/icon.png"
    elif [ -f "$dir/icons/$slug-256.png" ]; then
      install -m 0644 "$dir/icons/$slug-256.png" "$dest/spark-apps/$slug/icon.png"
    fi
  done
  python3 -m compileall -q "$dest"
}

# The optional Spark apps (see the top of this file), one slug per line
optional_apps() {
  local scripts=$here/../scripts dir slug says
  if [ ! -d "$scripts" ]; then
    echo "install.sh: no $scripts: run this from the SparkOS repo's files/spark-store" >&2
    return 1
  fi
  for dir in "$here"/../spark-*/; do
    slug=$(basename "$dir")
    [ -f "$dir/spark-app.json" ] && [ -f "$dir/install.sh" ] || continue
    says=$(python3 -c 'import json,sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("in-image" if d.get("optional") is False or d.get("in_image") is True
      else "optional" if d.get("optional") is True else "")' "$dir/spark-app.json")
    if [ -f "$scripts/$slug.sh" ]; then
      if [ "$says" = optional ]; then
        echo "install.sh: $slug/spark-app.json says optional, but files/scripts/$slug.sh installs it" >&2
        return 1
      fi
    else
      if [ "$says" = in-image ]; then
        echo "install.sh: $slug/spark-app.json says it's in the image, but no files/scripts/$slug.sh installs it" >&2
        return 1
      fi
      echo "$slug"
    fi
  done
}

if [ "$LIST_OPTIONAL" = 1 ]; then
  optional_apps
  exit 0
fi

if [ -n "$SOURCES" ]; then
  apps=$(optional_apps)
  install -d -m 0755 "$SOURCES"
  for slug in $apps; do
    rm -rf -- "${SOURCES:?}/$slug"
    cp -r -- "$here/../$slug" "$SOURCES/$slug"
    rm -rf -- "$SOURCES/$slug/tests"
    find "$SOURCES/$slug" \( -name __pycache__ -o -name '*.pyc' -o -name make_icons.py \) -prune \
      -exec rm -rf -- {} +
    chmod -R u=rwX,go=rX "$SOURCES/$slug"
    chmod 0755 "$SOURCES/$slug/install.sh"
    test -f "$SOURCES/$slug/spark-app.json"
    grep -q -- '--user' "$SOURCES/$slug/install.sh"
    echo "source of $slug: $SOURCES/$slug ($(du -sk "$SOURCES/$slug" | cut -f1) KB)"
  done
  exit 0
fi

# ─── Per user, no root ───────────────────────────────────────

if [ "$USER_MODE" = 1 ]; then
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || { echo "install.sh --user: HOME is not set" >&2; exit 1; }
  DATA=${XDG_DATA_HOME:-$HOME/.local/share}
  LIB=$HOME/.local/lib/$SLUG
  BIN=$HOME/.local/bin/$SLUG
  MANIFEST=$LIB/installed-files

  if [ "$UNINSTALL" = 1 ]; then
    if [ ! -f "$MANIFEST" ]; then
      echo "Spark Store isn't installed for $(id -un) (no $MANIFEST)."
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
    echo "Spark Store removed for $(id -un). Apps you installed with it stay; settings stay in"
    echo "~/.config/$SLUG and the catalog index in ~/.cache/$SLUG (delete those too if you like)."
    exit 0
  fi

  if [ "$(id -u)" = 0 ]; then
    echo "install.sh --user: you're root; this would install for root only." >&2
    echo "Run it as the person who will use it, or drop --user for a system-wide install." >&2
    exit 1
  fi
  if ! python3 -c 'import tkinter, sqlite3' 2>/dev/null; then
    echo "Spark Store needs Python 3 with tkinter and sqlite3, which this system doesn't have." >&2
    echo "On SparkOS they come with the image; on Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
  fi
  command -v flatpak >/dev/null || echo "note: flatpak isn't installed; only the Spark apps will show." >&2

  rm -rf -- "$LIB"
  copy_app "$LIB"
  : > "$MANIFEST"
  record() { printf '%s\n' "$1" >> "$MANIFEST"; }

  install -d "$(dirname "$BIN")"
  cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/env python3 "$LIB/spark_store.py" "\$@"
EOF
  chmod 0755 "$BIN"
  record "$BIN"

  # ~/.local/bin may not be on the desktop session's PATH: point the entry at the full path
  desktop="$DATA/applications/$APP_ID.desktop"
  install -d "$DATA/applications"
  case "$BIN" in *" "*) exec_bin="\"$BIN\"" ;; *) exec_bin=$BIN ;; esac
  sed "s|^Exec=spark-store|Exec=$exec_bin|" "$here/$APP_ID.desktop" > "$desktop"
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
  echo "Spark Store installed for $(id -un) in $LIB. Remove it with:"
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
  echo "Spark Store removed from the system."
  exit 0
fi

if [ "$DEPS" = 1 ]; then
  missing=()
  for pkg in python3 python3-tkinter flatpak xrdb cascadia-mono-fonts; do
    rpm -q --whatprovides "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "--- installing: ${missing[*]}"
    dnf -y install --setopt=install_weak_deps=False "${missing[@]}"
  fi
  # sharper icons and JPEG screenshots; it works without
  python3 -c 'from PIL import ImageTk' 2>/dev/null || \
    dnf -y install --setopt=install_weak_deps=False python3-pillow-tk || \
    echo "--- optional: no Pillow, icons are scaled by Tk"
fi

rm -rf "$PREFIX"
copy_app "$PREFIX"

cat > /usr/bin/$SLUG <<EOF
#!/bin/sh
exec /usr/bin/python3 $PREFIX/spark_store.py "\$@"
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
test -f "$PREFIX/sparkstore/app.py"
test -f "$PREFIX/sparkstore/own-apps.json"
test -f "/usr/share/applications/$APP_ID.desktop"
/usr/bin/$SLUG --version
if [ "$TEST" = 1 ]; then
  /usr/bin/$SLUG --self-test
fi
echo "Spark Store installed to $PREFIX."
