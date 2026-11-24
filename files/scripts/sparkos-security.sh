#!/usr/bin/env bash
# Containerfile step 5, after the Spark apps (Spark Link's firewalld service must exist first).
#
# Firewall: the default zone is SparkOS's own "sparkos" zone (files/system/usr/lib/firewalld/
# zones/sparkos.xml) instead of Fedora's FedoraWorkstation, which accepts every port from 1025
# to 65535 from the local network, so any program that listens is reachable by every device on
# it. The sparkos zone opens only what SparkOS uses: DHCPv6, mDNS (finding devices), Samba as a
# client, Spark Link, Nova's phone ports (files/system/usr/lib/firewalld/services/nova.xml;
# nothing listens there unless Nova is installed), KDE Connect, Steam Remote Play and Steam's local transfers. Anything else
# is a switch or a port in Spark Firewall. A network given its own zone in NetworkManager keeps it.
#
# Tailscale's interface goes to the trusted zone: every device there is one the owner signed in
# with their own account, and Tailscale encrypts the traffic. Tailscale isn't in the image; the
# setting does nothing until it is installed.
#
# Kernel: ptrace limited to a program's own children (Yama scope 1, Ubuntu's default). With 0,
# any program you run, a game under Wine for example, can read the memory of your browser or
# password manager. Debuggers still work on what they start; attaching to a running program
# needs sudo. Kernel addresses are hidden from users (kptr_restrict 1).
set -oue pipefail

zone=sparkos
test -f "/usr/lib/firewalld/zones/$zone.xml" || { echo "zone file missing"; exit 1; }
test -f /usr/lib/firewalld/services/spark-link.xml || { echo "spark-link service missing"; exit 1; }
test -f /usr/lib/firewalld/services/nova.xml || { echo "nova service missing"; exit 1; }
firewall-offline-cmd --check-config
firewall-offline-cmd --set-default-zone="$zone"
firewall-offline-cmd --zone=trusted --add-interface=tailscale0

test "$(firewall-offline-cmd --get-default-zone)" = "$zone"
open=$(firewall-offline-cmd --zone="$zone" --list-ports)
test -z "$open" || { echo "the $zone zone opens ports: $open"; exit 1; }
for svc in mdns spark-link nova kdeconnect steam-streaming; do
  firewall-offline-cmd --zone="$zone" --list-services | tr ' ' '\n' | grep -qx "$svc" \
    || { echo "$svc missing from $zone"; exit 1; }
done
firewall-offline-cmd --zone=trusted --list-interfaces | grep -qw tailscale0
echo "firewalld default zone: $zone ($(firewall-offline-cmd --zone="$zone" --list-services))"

mkdir -p /usr/lib/sysctl.d
cat > /usr/lib/sysctl.d/60-sparkos-hardening.conf <<'EOS'
# SparkOS hardening (files/scripts/sparkos-security.sh says why)
kernel.yama.ptrace_scope = 1
kernel.kptr_restrict = 1
EOS
