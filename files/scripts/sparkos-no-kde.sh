#!/usr/bin/env bash
# The last step: SparkOS runs without KDE. Fedora Kinoite ships Plasma, KWin, Plasma Login
# Manager, Dolphin, Konsole, KWallet and the KDE Frameworks; the Spark equivalents are already
# installed by the steps before this one, so here the KDE packages go.
#
#   sign-in        greetd + Spark Greeter (on spark-compositor) instead of Plasma Login Manager
#   desktop        the Spark session (spark-compositor + Spark Shell) instead of Plasma and KWin
#   passwords      GNOME Keyring, unlocked by the sign-in password, instead of KWallet. Not a
#                  Spark app yet: it is the one store apps already know how to use
#   icons          Breeze's icon and cursor artwork stays (files only, no KDE software): the
#                  SparkOS icon theme falls back to it for the icons it has not drawn yet
#   Qt             stays: OpenRGB and the Spark Launcher's QML are Qt programs, not KDE
#
# Runs after every other step, so the earlier steps' checks against Plasma still see it.
# Fails the build if any KDE package is left or the sign-in screen is not set up.
set -oue pipefail

# --- passwords: GNOME Keyring (greetd's PAM file already has the optional pam_gnome_keyring
# lines, so the sign-in password unlocks it)
# pinentry-gnome3: GnuPG's passphrase window (pinentry-qt depends on KDE and goes below)
dnf -y install --setopt=install_weak_deps=False gnome-keyring gnome-keyring-pam pinentry-gnome3
test -f /usr/lib64/security/pam_gnome_keyring.so
grep -q 'pam_gnome_keyring.so' /usr/lib/pam.d/greetd

# --- remove KDE. Anything that needs these goes with them (Konsole, Ark, Akonadi, KDE's
# wallpapers); dnf lists it all in the build log.
KDE_RE='^(plasma|kwin|kf6-|kde|kwallet|kscreen|dolphin|kio|plasmalogin|xdg-desktop-portal-kde|polkit-kde|kinfocenter|kmenuedit|kglobalacceld|powerdevil|bluedevil|kactivitymanagerd|baloo|milou|kpipewire|layer-shell-qt|libkscreen|libplasma|kdecoration|signon|kaccounts|ksshaskpass|kdialog|kcm-|flatpak-kcm|qqc2-breeze|aurorae|pam-kwallet|ksystemstats|ocean-sound|kate-libs|kdesu|kde-cli|kdegraphics|kdenetwork|kio-|kcgroups|ksecret|libkworkspace|kuserfeedback|kpackage|breeze-gtk|plasma5support|libksysguard|kwayland|knighttime|kunifiedpush|kjournald|kwrited|krdp|keditbookmarks|kamera|kdnssd|kpmcore|kquickimageeditor|xwaylandvideobridge|konsole|ark|akonadi|audiocd-kio|colord-kde|desktop-backgrounds-kde|fedora-chromium-config-kde|ffmpegthumbs|accounts-qml-module)'
mapfile -t kde < <(rpm -qa --qf '%{NAME}\n' | grep -E "$KDE_RE" | sort -u)
echo "removing ${#kde[@]} KDE packages"
printf '  %s\n' "${kde[@]}"
# Only these and what depends on them: nothing else is swept up as "no longer needed".
dnf -y remove --setopt=clean_requirements_on_remove=False "${kde[@]}"

# What the packages leave behind, and SparkOS's own files that only Plasma read
rm -rf /usr/share/plasma /usr/share/wayland-sessions/plasma.desktop \
       /usr/share/xsessions/plasmax11.desktop \
       /etc/plasmalogin.conf /etc/plasmalogin.conf.d /etc/xdg/kwinrc /etc/xdg/plasmarc
# The Spark session that ran on KWin (spark-shell's spark.desktop): there is no KWin to run it
rm -f /usr/share/wayland-sessions/spark.desktop
# spark-settings.sh moved KDE's systemsettings and kcmshell6 here and put stand-ins in /usr/bin;
# with KDE gone, both are dead
rm -rf /usr/libexec/sparkos/kde-settings
rm -f /usr/bin/systemsettings /usr/bin/kcmshell6

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
         spark-settings spark-update; do
  command -v "$b" >/dev/null || { echo "$b went missing"; exit 1; }
done
# The compositor's libraries are all still there
! ldd /usr/bin/spark-compositor | grep -q 'not found'
# The Python the greeter and the shell use still imports
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk'
echo "No KDE: the Spark session and the Spark sign-in screen are what SparkOS runs."
