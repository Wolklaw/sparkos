#!/usr/bin/env bash
# The SparkOS icon theme (files/sparkos-icons/SparkOS, brief: briefs/sparkos-icons.md), installed
# as /usr/share/icons/SparkOS. It inherits Breeze Dark, so every icon it doesn't draw yet still
# comes from Breeze's artwork (the icon files only, kept by sparkos-no-kde.sh; no KDE software).
# /etc/xdg/kdeglobals (files/system) makes it the default. Breeze Dark stays the parent for third-party
# apps only; the cursors are SparkOS's own (files/sparkos-icons/cursors).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/sparkos-icons/SparkOS"
DEST=/usr/share/icons/SparkOS
test -f "$SRC/index.theme" || { echo "SparkOS icon theme not found at $SRC"; exit 1; }
test -f /usr/share/icons/breeze-dark/index.theme || { echo "breeze-dark, which SparkOS inherits, is missing"; exit 1; }

rm -rf "$DEST"
cp -a "$SRC" "$DEST"          # -a keeps the alias links (folder -> inode-directory, ...)
chown -R root:root "$DEST"
find "$DEST" -type d -exec chmod 0755 {} +
find "$DEST" -type f -exec chmod 0644 {} +
gtk-update-icon-cache -f -t "$DEST" 2>/dev/null || true

# every directory index.theme lists exists, and the icons the defaults point at are there
dirs=$(sed -n 's/^Directories=//p' "$DEST/index.theme" | tr ',' ' ')
test -n "$dirs" || { echo "index.theme lists no Directories"; exit 1; }
for d in $dirs; do test -d "$DEST/$d" || { echo "index.theme lists $d, which is missing"; exit 1; }; done
for f in apps/scalable/preferences-system.svg apps/16/preferences-system.svg places/scalable/folder.svg \
         places/16/folder.svg places/scalable/user-trash.svg places/scalable/user-trash-full.svg \
         apps/scalable/application-x-executable.svg apps/scalable/com.valvesoftware.Steam.svg \
         places/symbolic/folder-symbolic.svg mimetypes/scalable/unknown.svg mimetypes/16/text-plain.svg \
         mimetypes/scalable/application-zip.svg mimetypes/22/application-x-msdownload.svg; do
  test -s "$DEST/$f" || { echo "missing $DEST/$f"; exit 1; }
done
grep -q '^Inherits=breeze-dark' "$DEST/index.theme" || { echo "index.theme doesn't inherit breeze-dark"; exit 1; }
grep -q '^Theme=SparkOS$' /etc/xdg/kdeglobals || { echo "/etc/xdg/kdeglobals doesn't make SparkOS the icon theme"; exit 1; }
# --- the SparkOS cursor theme, drawn from files/sparkos-icons/cursors/src into XCursor files
# (/usr/share/icons/SparkOS-cursors). It covers every name Breeze and Adwaita ship, so Breeze's
# cursors are not installed. SparkOS/cursors links to it (choosing "SparkOS" as the cursor theme
# works), and icons/default, the theme every toolkit falls back to, inherits it.
CUR_SRC="${CONFIG_DIRECTORY:-/tmp/files}/sparkos-icons/cursors"
CUR=/usr/share/icons/SparkOS-cursors
test -f "$CUR_SRC/make_cursors.py" || { echo "cursor generator not found at $CUR_SRC"; exit 1; }
rm -rf "$CUR"
python3 "$CUR_SRC/make_cursors.py" "$CUR"
chown -R root:root "$CUR"
find "$CUR" -type d -exec chmod 0755 {} +
find "$CUR" -type f -exec chmod 0644 {} +
ln -sfn ../SparkOS-cursors/cursors "$DEST/cursors"
mkdir -p /usr/share/icons/default
printf '[Icon Theme]\nInherits=SparkOS-cursors\n' > /usr/share/icons/default/index.theme
for n in default text pointer progress wait not-allowed size_hor left_ptr watch 00000000000000020006000e7e9ffc3f; do
  test -s "$DEST/cursors/$n" || { echo "cursor $n is missing"; exit 1; }
done
python3 - "$CUR/cursors" <<'PY'
import os, struct, sys
d = sys.argv[1]
for n in os.listdir(d):
    data = open(os.path.join(d, n), "rb").read(16)      # follows the links
    if data[:4] != b"Xcur":
        sys.exit(f"cursor {n} is not an Xcursor file")
PY

echo "SparkOS icon theme installed: $(find "$DEST" -name '*.svg' | wc -l) files."
