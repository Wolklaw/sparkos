#!/usr/bin/env bash
# The SparkOS icon theme (files/sparkos-icons/SparkOS, brief: briefs/sparkos-icons.md), installed
# as /usr/share/icons/SparkOS. It inherits Breeze Dark, so every icon it doesn't draw yet still
# comes from Breeze. /etc/xdg/kdeglobals and the SparkOS look-and-feel package (files/system)
# make it the default; /usr/libexec/sparkos-icons-default moves a user who still has Breeze Dark
# written in their own settings over to it once, at sign-in.
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
test -n "$dirs"
for d in $dirs; do test -d "$DEST/$d" || { echo "index.theme lists $d, which is missing"; exit 1; }; done
for f in apps/scalable/preferences-system.svg apps/16/preferences-system.svg places/scalable/folder.svg \
         places/16/folder.svg places/scalable/user-trash.svg places/scalable/user-trash-full.svg \
         apps/scalable/application-x-executable.svg apps/scalable/com.valvesoftware.Steam.svg \
         places/symbolic/folder-symbolic.svg; do
  test -s "$DEST/$f" || { echo "missing $DEST/$f"; exit 1; }
done
grep -q '^Inherits=breeze-dark' "$DEST/index.theme"
grep -q '^Theme=SparkOS$' /etc/xdg/kdeglobals || { echo "/etc/xdg/kdeglobals doesn't make SparkOS the icon theme"; exit 1; }
test -x /usr/libexec/sparkos-icons-default
echo "SparkOS icon theme installed: $(find "$DEST" -name '*.svg' | wc -l) files."
