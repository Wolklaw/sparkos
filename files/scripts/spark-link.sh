#!/usr/bin/env bash
# Spark Link, SparkOS's own phone link (the phone side is in Soot's Android app). Its source
# lives in this repo at files/spark-link; the protocol is docs/spark-link-protocol.md.
#
# install.sh --deps installs it system-wide: the window, the background service as a systemd
# user unit (switched on per user by the window at the first pairing, so nobody who never
# pairs a phone has it running or listening), the "Send to phone" menu entry in Spark Files, and the firewalld
# service definition. Then this opens TCP 47100 in the default firewalld zone, unless that zone
# already allows it (Fedora's desktop zone allows ports 1025-65535). The build fails if the
# self-test or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-link"
test -f "$SRC/install.sh" || { echo "Spark Link source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-link
test -f /usr/share/applications/dev.wolklaw.SparkLink.desktop
test -f /usr/share/kio/servicemenus/dev.wolklaw.SparkLink.send.desktop
grep -q '^ExecStart=/usr/bin/spark-link --service$' /usr/lib/systemd/user/spark-link.service
test -f /usr/lib/firewalld/services/spark-link.xml
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkLink.svg

# ── Firewall: the Spark Link port, only where the default zone doesn't already allow it ──
port_open() {   # $1: zone. True if the zone's ports or services cover 47100/tcp.
  local spec lo hi
  firewall-offline-cmd --zone="$1" --list-services | tr ' ' '\n' | grep -qx spark-link && return 0
  for spec in $(firewall-offline-cmd --zone="$1" --list-ports); do
    case "$spec" in */tcp) ;; *) continue ;; esac
    spec=${spec%/tcp}
    lo=${spec%-*}; hi=${spec#*-}
    [ "$lo" -le 47100 ] && [ 47100 -le "$hi" ] && return 0
  done
  return 1
}
if command -v firewall-offline-cmd >/dev/null; then
  zone=$(firewall-offline-cmd --get-default-zone)
  echo "firewalld default zone: $zone ($(systemctl is-enabled firewalld.service 2>/dev/null || echo 'unit state unknown'))"
  if port_open "$zone"; then
    echo "TCP 47100 is already allowed in $zone; nothing changed."
  else
    firewall-offline-cmd --zone="$zone" --add-service=spark-link
    port_open "$zone"
    echo "Opened Spark Link (TCP 47100) in firewalld zone $zone."
  fi
  firewall-offline-cmd --zone="$zone" --list-services | tr ' ' '\n' | grep -qx mdns || \
    echo "note: mdns isn't allowed in $zone; phones will need the pairing link or the address"
else
  echo "firewalld isn't in the image; no firewall change."
fi

report=$(/usr/bin/spark-link --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-link --version) installed."
