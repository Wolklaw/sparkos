#!/usr/bin/env bash
# Default apps for everyone: Soot for the web, FreeSuite for mail, calendar, PDF and every
# office format it opens (Word, Excel, PowerPoint, old and new, OpenDocument, RTF, CSV).
# Lines are added to Bazzite's /etc/xdg/mimeapps.list so its own entries stay.
# Plain text and Markdown stay with Kate. ONLYOFFICE stays installed and can still be
# picked under "Open with". A user's own choices still win.
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

add freesuite-writer.desktop \
  application/vnd.openxmlformats-officedocument.wordprocessingml.document \
  application/vnd.openxmlformats-officedocument.wordprocessingml.template \
  application/vnd.ms-word.document.macroEnabled.12 \
  application/vnd.ms-word.template.macroEnabled.12 \
  application/msword \
  application/vnd.oasis.opendocument.text \
  application/vnd.oasis.opendocument.text-template \
  application/rtf text/rtf

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

echo "--- $LIST"
cat "$LIST"
