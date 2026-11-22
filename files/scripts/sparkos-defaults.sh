#!/usr/bin/env bash
# Default apps for everyone: Soot for the web, FreeSuite for mail, calendar, PDF and every
# office format it opens (Word, Excel, PowerPoint, old and new, OpenDocument, RTF, CSV), and
# Spark Media for photos, videos and music (every type its desktop entry lists).
# Lines are added to Bazzite's /etc/xdg/mimeapps.list so its own entries stay.
# Plain text, Markdown, code and config files open in Spark Edit; archives in Spark Archive (Ark
# stays installed for now, but is no longer the default).
# A user's own choices still win.
set -oue pipefail

LIST=/etc/xdg/mimeapps.list
touch "$LIST"
grep -q '^\[Default Applications\]' "$LIST" || printf '[Default Applications]\n' >> "$LIST"

add() { # desktop-file mime-type...
  local app=$1; shift
  for mime in "$@"; do
    sed -i "/^$(printf '%s' "$mime" | sed 's/[\/&.]/\\&/g')=/d" "$LIST"   # '+' is literal in sed's basic syntax
    sed -i "/^\[Default Applications\]/a $mime=$app" "$LIST"
  done
}

add dev.wolklaw.Soot.desktop \
  x-scheme-handler/http x-scheme-handler/https text/html application/xhtml+xml

add freesuite-mail.desktop     x-scheme-handler/mailto
add freesuite-calendar.desktop text/calendar
add freesuite-pdf.desktop      application/pdf

# Photos, videos and music: Spark Media, for every type it declares
MEDIA=/usr/share/applications/dev.wolklaw.SparkMedia.desktop
test -f "$MEDIA" || { echo "Spark Media is not installed (spark-media.sh runs first)"; exit 1; }
# shellcheck disable=SC2046
add dev.wolklaw.SparkMedia.desktop $(sed -n 's/^MimeType=//p' "$MEDIA" | tr ';' ' ')

# Installing apps by double-click, the way Windows users expect. sparkos-open-package hands
# .exe/.msi to Spark Run, adds AppImages to the menu itself, guides .rpm installs and explains .deb.
add sparkos-open-package.desktop \
  application/x-ms-dos-executable application/x-msi application/x-msdownload \
  application/vnd.microsoft.portable-executable application/x-ms-shortcut \
  application/vnd.appimage application/x-iso9660-appimage \
  application/x-rpm application/x-redhat-package-manager \
  application/vnd.debian.binary-package application/x-deb
add dev.wolklaw.SparkStore.desktop \
  application/vnd.flatpak.ref application/vnd.flatpak.repo                   # Flatpak links open in the Store

add freesuite-writer.desktop \
  application/vnd.openxmlformats-officedocument.wordprocessingml.document \
  application/vnd.openxmlformats-officedocument.wordprocessingml.template \
  application/vnd.ms-word.document.macroEnabled.12 \
  application/vnd.ms-word.template.macroEnabled.12 \
  application/msword \
  application/vnd.oasis.opendocument.text \
  application/vnd.oasis.opendocument.text-template \
  application/rtf text/rtf \
  text/plain text/markdown

add freesuite-sheets.desktop \
  application/vnd.openxmlformats-officedocument.spreadsheetml.sheet \
  application/vnd.openxmlformats-officedocument.spreadsheetml.template \
  application/vnd.ms-excel.sheet.macroEnabled.12 \
  application/vnd.ms-excel.template.macroEnabled.12 \
  application/vnd.ms-excel \
  application/vnd.oasis.opendocument.spreadsheet \
  application/vnd.oasis.opendocument.spreadsheet-template \
  text/csv text/tab-separated-values

add freesuite-slides.desktop \
  application/vnd.openxmlformats-officedocument.presentationml.presentation \
  application/vnd.openxmlformats-officedocument.presentationml.slideshow \
  application/vnd.openxmlformats-officedocument.presentationml.template \
  application/vnd.ms-powerpoint.presentation.macroEnabled.12 \
  application/vnd.ms-powerpoint.slideshow.macroEnabled.12 \
  application/vnd.ms-powerpoint.template.macroEnabled.12 \
  application/vnd.ms-powerpoint \
  application/vnd.oasis.opendocument.presentation \
  application/vnd.oasis.opendocument.presentation-template

# Text and code: Spark Edit (the types Fedora's shared-mime-info uses; not HTML, CSV or .desktop)
test -f /usr/share/applications/dev.wolklaw.SparkEdit.desktop || { echo "Spark Edit is not installed (spark-edit.sh runs first)"; exit 1; }
add dev.wolklaw.SparkEdit.desktop   text/plain text/markdown text/x-log text/x-readme text/x-python text/x-python3   application/x-shellscript text/x-shellscript application/json application/yaml application/x-yaml   application/toml text/x-ini text/x-systemd-unit text/x-dbus-service text/javascript   application/typescript text/css text/x-scss application/xml text/xml text/x-csrc text/x-chdr   text/x-c++src text/x-c++hdr text/rust text/x-go text/x-makefile text/x-cmake text/x-patch text/x-diff

# Archives and disc images: Spark Archive (AppImage type 1 stays with sparkos-open-package)
test -f /usr/share/applications/dev.wolklaw.SparkArchive.desktop || { echo "Spark Archive is not installed (spark-archive.sh runs first)"; exit 1; }
add dev.wolklaw.SparkArchive.desktop   application/zip application/x-zip-compressed   application/x-tar application/x-compressed-tar application/x-bzip-compressed-tar   application/x-bzip2-compressed-tar application/x-xz-compressed-tar application/x-zstd-compressed-tar   application/x-lzma-compressed-tar application/x-lz4-compressed-tar application/x-lzip-compressed-tar application/x-tarz   application/x-7z-compressed application/vnd.rar application/x-rar   application/gzip application/x-bzip application/x-bzip2 application/x-xz application/zstd   application/x-cd-image application/x-iso9660-image

echo "--- $LIST"
cat "$LIST"
