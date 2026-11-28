#!/usr/bin/env bash
# The last step: SparkOS runs without KDE. The base (Fedora's base-atomic) has no desktop, and
# the steps before this one install the Spark one; this step sets up what they share and fails
# the build if any KDE package came in with them.
#
#   sign-in        greetd + Spark Greeter (on spark-compositor)
#   desktop        the Spark session (spark-compositor + Spark Shell)
#   passwords      Spark Secrets (spark-secrets, org.freedesktop.secrets), unlocked by the sign-in
#                  password through spark-secrets-pam in greetd's PAM file. GNOME Keyring is not
#                  in the image; ssh-agent (openssh's socket-activated user unit) holds SSH keys
#   icons          Breeze's icon artwork (files only, no KDE software): the SparkOS
#                  icon theme falls back to it for third-party apps' icons. The cursors are SparkOS's own
#   Qt             allowed: OpenRGB is a Qt program, not KDE
#
# Fails the build if any KDE package is installed or the sign-in screen is not set up.
set -oue pipefail

# --- passwords: Spark Secrets (files/spark-session). The sign-in password unlocks it:
# pam_exec runs spark-secrets-pam, which leaves the unlock key in /run/spark-secrets.
# pinentry-gnome3: GnuPG's passphrase window (pinentry-qt would bring in KDE libraries); it does
# not need gnome-keyring
dnf -y install --setopt=install_weak_deps=False python3-cryptography pinentry-gnome3
PAM=/usr/lib/pam.d/greetd
sed -i '/pam_gnome_keyring\.so/d' "$PAM"
sed -i '/^auth  *substack  *system-auth$/a auth       optional    pam_exec.so quiet expose_authtok /usr/libexec/spark-secrets-pam' "$PAM"
grep -q 'pam_exec.so quiet expose_authtok /usr/libexec/spark-secrets-pam' "$PAM"
! grep -q 'pam_gnome_keyring' "$PAM"
for f in /usr/bin/spark-secrets /usr/libexec/spark-secrets-pam \
         /usr/lib/systemd/user/spark-secrets.service \
         /usr/share/dbus-1/services/dev.wolklaw.SparkSecrets.service \
         /usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.sparksecrets.service \
         /usr/share/xdg-desktop-portal/portals/sparksecrets.portal; do
  test -f "$f" || { echo "$f is missing (the spark-session step puts it there)"; exit 1; }
done
# GNOME Keyring and its PAM module go. rpm -e, not dnf: it stops the build if something still
# needs them. They delete their own files only, so the Spark Secrets files above stay.
# (The .service file of theirs is org.freedesktop.secrets.service; ours has another name.)
gk=(gnome-keyring gnome-keyring-pam)
mapfile -t present < <(rpm -q --qf '%{NAME}\n' "${gk[@]}" 2>/dev/null | grep -v ' ' || true)
if [ ${#present[@]} -gt 0 ]; then
  echo "removing ${present[*]}"
  rpm -e "${present[@]}"
fi
! rpm -q gnome-keyring gnome-keyring-pam >/dev/null 2>&1
# SSH keys: openssh's agent starts on first use at $XDG_RUNTIME_DIR/ssh-agent.socket (the Spark
# session sets SSH_AUTH_SOCK to it). The PKCS#11 autostart went with gnome-keyring.
systemctl --global enable ssh-agent.socket
test -L /etc/systemd/user/sockets.target.wants/ssh-agent.socket
rm -f /etc/xdg/autostart/gnome-keyring-*.desktop

# --- KDE: none in the base; if a package pulled some in, it goes here, and dnf lists in the
# build log what needed it (fix that step instead).
KDE_RE='^(plasma|kwin|kf6-|kde|kwallet|kscreen|dolphin|kio|plasmalogin|xdg-desktop-portal-kde|polkit-kde|kinfocenter|kmenuedit|kglobalacceld|powerdevil|bluedevil|kactivitymanagerd|baloo|milou|kpipewire|layer-shell-qt|libkscreen|libplasma|kdecoration|signon|kaccounts|ksshaskpass|kdialog|kcm-|flatpak-kcm|qqc2-breeze|aurorae|pam-kwallet|ksystemstats|ocean-sound|kate-libs|kdesu|kde-cli|kdegraphics|kdenetwork|kio-|kcgroups|ksecret|libkworkspace|kuserfeedback|kpackage|breeze-gtk|plasma5support|libksysguard|kwayland|knighttime|kunifiedpush|kjournald|kwrited|krdp|keditbookmarks|kamera|kdnssd|kpmcore|kquickimageeditor|xwaylandvideobridge|konsole|ark|akonadi|audiocd-kio|colord-kde|desktop-backgrounds-kde|fedora-chromium-config-kde|ffmpegthumbs|accounts-qml-module)'
mapfile -t kde < <(rpm -qa --qf '%{NAME}\n' | grep -E "$KDE_RE" | sort -u)
if [ ${#kde[@]} -gt 0 ]; then
  echo "removing ${#kde[@]} KDE packages"
  printf '  %s\n' "${kde[@]}"
  dnf -y remove --setopt=clean_requirements_on_remove=False "${kde[@]}" \
    || echo "dnf reported errors (scriptlets); the checks below decide"
fi

# --- leftovers nothing uses (about 520 MB). rpm -e, not dnf: it stops the build if anything
# still needs one of them instead of taking that with it.
#   ibus and its engines: spark-compositor has no input-method protocol, so no app can reach
#     them; cldr-emoji-annotation only fed ibus-typing-booster (Spark Emoji has its own list)
#   boto3/botocore: the AWS SDK, a weak dependency of sos
#   localsearch: GNOME's file indexer, autostarted at sign-in, used by nothing Spark
unused=(ibus python3-ibus ibus-libs ibus-gtk3 ibus-gtk4 ibus-setup ibus-anthy ibus-anthy-python ibus-hangul
        ibus-libpinyin ibus-m17n ibus-chewing ibus-typing-booster
        cldr-emoji-annotation cldr-emoji-annotation-dtd libpinyin libpinyin-data anthy-unicode
        kasumi-unicode m17n-lib m17n-db libhangul libchewing
        python3-boto3 python3-s3transfer python3-botocore python3-jmespath
        localsearch)
mapfile -t present < <(rpm -q --qf '%{NAME}\n' "${unused[@]}" 2>/dev/null | grep -v ' ' || true)
if [ ${#present[@]} -gt 0 ]; then
  echo "removing ${#present[@]} unused packages"
  rpm -e "${present[@]}"
fi
left=$(rpm -q --qf '%{NAME}\n' "${unused[@]}" 2>/dev/null | grep -v ' ' || true)
[ -z "$left" ] || { echo "unused packages are still installed:"; echo "$left"; exit 1; }
rm -f /etc/xdg/autostart/localsearch-3.desktop

# --- the portals: Spark's own backend answers settings, inhibit, notifications and print; secrets
# are Spark Secrets'. The GTK portal is not part of the image.
PORTALS=/usr/share/xdg-desktop-portal/sparkwl-portals.conf
sed -i 's/^org\.freedesktop\.impl\.portal\.Secret=.*/org.freedesktop.impl.portal.Secret=sparksecrets/' "$PORTALS"
grep -qx 'org.freedesktop.impl.portal.Secret=sparksecrets' "$PORTALS"
grep -qx 'default=sparkos' "$PORTALS"
! grep -q gtk "$PORTALS"
test -f /usr/share/xdg-desktop-portal/portals/sparkos.portal
if rpm -q xdg-desktop-portal-gtk >/dev/null 2>&1; then
  echo "removing xdg-desktop-portal-gtk"
  rpm -e xdg-desktop-portal-gtk
fi
! rpm -q xdg-desktop-portal-gtk >/dev/null 2>&1

# --- sign-in: greetd with the Spark greeter is the display manager
install -D -m 0644 /usr/share/spark-session/greetd-config.toml /etc/greetd/config.toml
rm -f /etc/systemd/system/display-manager.service
systemctl enable --force greetd.service
[ "$(basename "$(readlink /etc/systemd/system/display-manager.service)")" = greetd.service ]
grep -q '^command = "/usr/libexec/spark-greeter-session"$' /etc/greetd/config.toml
# The default session is the Spark one, and it is the only one
test -f /usr/share/wayland-sessions/spark-wl.desktop
others=$(find /usr/share/wayland-sessions /usr/share/xsessions -name '*.desktop' \
  ! -name spark-wl.desktop 2>/dev/null || true)
[ -z "$others" ] || { echo "sessions other than Spark are left:"; echo "$others"; exit 1; }

# --- checks: no KDE package, nothing Spark needs went with it
left=$(rpm -qa --qf '%{NAME}\n' | grep -E "$KDE_RE" || true)
[ -z "$left" ] || { echo "KDE packages are still installed:"; echo "$left"; exit 1; }
for f in /usr/bin/kwin_wayland /usr/bin/plasmashell /usr/bin/plasmalogin /usr/bin/ksecretd \
         /usr/bin/kwalletd6 /usr/bin/dolphin /usr/bin/konsole /usr/bin/systemsettings; do
  [ ! -e "$f" ] || { echo "$f is still there"; exit 1; }
done
for p in greetd spark-compositor xdg-desktop-portal-wlr \
         breeze-icon-theme pinentry-gnome3 python3-cryptography; do
  rpm -q --whatprovides "$p" >/dev/null 2>&1 || command -v "$p" >/dev/null 2>&1 \
    || { echo "$p went missing"; exit 1; }
done
for b in spark-compositor spark-greeter spark-shell spark-wl-session spark-terminal spark-files \
         spark-settings spark-update spark-pick spark-secrets ssh-agent; do
  command -v "$b" >/dev/null || { echo "$b went missing"; exit 1; }
done
# The compositor's libraries are all still there
! ldd /usr/bin/spark-compositor | grep -q 'not found'
# The Python the greeter and the shell use still imports
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk'
echo "No KDE: the Spark session and the Spark sign-in screen are what SparkOS runs."
