#!/usr/bin/bash
# Containerfile step 6: Flathub for the system and for each user (the recipe's
# "default-flatpaks" step, system and user scope, installing nothing).
#
# Nothing can be added to Flatpak at build time (its data lives in /var), so, as under
# BlueBuild, two small services add the remote on the running system: the system one 30 seconds
# after boot, the user one at each login. The unit names are the same as BlueBuild's
# (system-flatpak-setup, user-flatpak-setup), so the installer hook and the docs that name them
# still apply. The script is SparkOS's own: plain shell, no Nushell, no notifications (there's
# nothing to install, so "installing 0 Flatpaks" popups are dropped).
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")

install -Dm755 "$here/flathub-setup" /usr/libexec/sparkos/flathub-setup

mkdir -p /usr/lib/systemd/system /usr/lib/systemd/user
cat > /usr/lib/systemd/system/system-flatpak-setup.service <<'EOF'
[Unit]
Description=Add the Flathub remote for the system (SparkOS)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/sparkos/flathub-setup --system
EOF

cat > /usr/lib/systemd/system/system-flatpak-setup.timer <<'EOF'
[Unit]
Description=Add the Flathub remote for the system, after boot

[Timer]
OnBootSec=30

[Install]
WantedBy=timers.target
EOF

cat > /usr/lib/systemd/user/user-flatpak-setup.service <<'EOF'
[Unit]
Description=Add the Flathub remote for this user (SparkOS)
Wants=network-online.target
After=system-flatpak-setup.service
ConditionUser=!@system
ConditionPathIsDirectory=/var/home/%u

[Service]
Type=oneshot
ExecStart=/usr/libexec/sparkos/flathub-setup --user
EOF

cat > /usr/lib/systemd/user/user-flatpak-setup.timer <<'EOF'
[Unit]
Description=Add the Flathub remote for this user, after login

[Timer]
OnBootSec=30

[Install]
WantedBy=timers.target
EOF

systemctl enable --force system-flatpak-setup.timer
systemctl enable --force --global user-flatpak-setup.timer

test -x /usr/libexec/sparkos/flathub-setup
test -L /etc/systemd/system/timers.target.wants/system-flatpak-setup.timer
test -L /etc/systemd/user/timers.target.wants/user-flatpak-setup.timer
echo "Flathub setup installed (system at boot, each user at login)."
