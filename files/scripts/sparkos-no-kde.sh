#!/usr/bin/env bash
# The last step: SparkOS runs without KDE. The base (Fedora's base-atomic) has no desktop, and
# the steps before this one install the Spark one; this step sets up what they share and fails
# the build if any KDE package came in with them.
#
#   sign-in        greetd + Spark Greeter (on spark-compositor)
#   desktop        the Spark session (spark-compositor + Spark Shell)
#   passwords      GNOME Keyring, unlocked by the sign-in password. Not a Spark app yet: it is
#                  the one store apps already know how to use
#   icons          Breeze's icon and cursor artwork (files only, no KDE software): the SparkOS
#                  icon theme falls back to it for the icons it has not drawn yet
#   Qt             allowed: OpenRGB is a Qt program, not KDE
#
# Fails the build if any KDE package is installed or the sign-in screen is not set up.
set -oue pipefail

# --- passwords: GNOME Keyring (greetd's PAM file already has the optional pam_gnome_keyring
# lines, so the sign-in password unlocks it)
# pinentry-gnome3: GnuPG's passphrase window (pinentry-qt would bring in KDE libraries)
dnf -y install --setopt=install_weak_deps=False gnome-keyring gnome-keyring-pam pinentry-gnome3
test -f /usr/lib64/security/pam_gnome_keyring.so
grep -q 'pam_gnome_keyring.so' /usr/lib/pam.d/greetd

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

# --- the portals: secrets from GNOME Keyring
PORTALS=/usr/share/xdg-desktop-portal/sparkwl-portals.conf
sed -i 's/^org\.freedesktop\.impl\.portal\.Secret=.*/org.freedesktop.impl.portal.Secret=gnome-keyring/' "$PORTALS"
grep -qx 'org.freedesktop.impl.portal.Secret=gnome-keyring' "$PORTALS"
test -f /usr/share/xdg-desktop-portal/portals/gnome-keyring.portal

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
for p in greetd spark-compositor xdg-desktop-portal-wlr xdg-desktop-portal-gtk \
         breeze-icon-theme breeze-cursor-theme gnome-keyring pinentry-gnome3; do
  rpm -q --whatprovides "$p" >/dev/null 2>&1 || command -v "$p" >/dev/null 2>&1 \
    || { echo "$p went missing"; exit 1; }
done
for b in spark-compositor spark-greeter spark-shell spark-wl-session spark-terminal spark-files \
         spark-settings spark-update spark-pick; do
  command -v "$b" >/dev/null || { echo "$b went missing"; exit 1; }
done
# The compositor's libraries are all still there
! ldd /usr/bin/spark-compositor | grep -q 'not found'
# The Python the greeter and the shell use still imports
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk'
echo "No KDE: the Spark session and the Spark sign-in screen are what SparkOS runs."
