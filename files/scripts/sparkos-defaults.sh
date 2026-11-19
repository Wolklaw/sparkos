#!/usr/bin/env bash
# Default apps for everyone: Soot for the web, FreeSuite for mail, calendar and the
# formats it opens. Lines are added to Bazzite's /etc/xdg/mimeapps.list so its own
# entries stay. ONLYOFFICE stays installed for formats FreeSuite doesn't open
# (.doc, .xls, .ppt and OpenDocument files). A user's own choices still win.
set -oue pipefail

LIST=/etc/xdg/mimeapps.list
touch "$LIST"
grep -q '^\[Default Applications\]' "$LIST" || printf '[Default Applications]\n' >> "$LIST"

add() { # mime-type desktop-file
  sed -i "/^$(printf '%s' "$1" | sed 's/[\/&.]/\\&/g')=/d" "$LIST"   # '+' is literal in sed's basic syntax
  sed -i "/^\[Default Applications\]/a $1=$2" "$LIST"
}

add x-scheme-handler/http   dev.wolklaw.Soot.desktop
add x-scheme-handler/https  dev.wolklaw.Soot.desktop
add text/html               dev.wolklaw.Soot.desktop
add application/xhtml+xml   dev.wolklaw.Soot.desktop

add x-scheme-handler/mailto freesuite-mail.desktop
add text/calendar           freesuite-calendar.desktop
add application/vnd.openxmlformats-officedocument.wordprocessingml.document   freesuite-writer.desktop
add application/vnd.openxmlformats-officedocument.spreadsheetml.sheet         freesuite-sheets.desktop
add text/csv                freesuite-sheets.desktop
add application/vnd.openxmlformats-officedocument.presentationml.presentation freesuite-slides.desktop
add application/pdf         freesuite-pdf.desktop

echo "--- $LIST"
cat "$LIST"
