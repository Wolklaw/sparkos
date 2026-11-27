#!/usr/bin/env bash
# The SparkOS look (Phase 3), from power-on to the desktop: the boot splash (Plymouth), the
# fonts, the logo icon, the wallpaper and os-release's logo and links.
# Static files (colour scheme, Plymouth theme, /etc/xdg defaults) come from files/system. This
# script renders the images from the SparkOS bot (files/sparkos-theme, a copy of
# branding/sparkos-bot.svg; bot.gif there is its animation, from tools/make-splash-animation.py),
# installs the fonts from files/sparkos-theme/fonts, and rebuilds the initramfs so the boot splash
# is in it.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/sparkos-theme"
BOT="$SRC/sparkos-bot.svg"
test -f "$BOT" || { echo "missing $BOT"; exit 1; }
WORK=$(mktemp -d)

# --- tools to render the SVG (removed again at the end)
dnf -y install --setopt=install_weak_deps=False librsvg2-tools
render() { rsvg-convert -w "$2" -h "$2" -o "$3" "$1"; }

# --- fonts: Inter (Fedora package, from the recipe) and Chakra Petch, kept in this repo at
# files/sparkos-theme/fonts (SIL Open Font License, OFL.txt next to it; from google/fonts commit
# e774067705989f0bcb5e32eb0e8f76c24d679f92). No download: the checksums catch a damaged copy.
FDIR=/usr/share/fonts/chakra-petch
mkdir -p "$FDIR"
while read -r sum name; do
  install -m 0644 "$SRC/fonts/$name" "$FDIR/$name"
  echo "$sum  $FDIR/$name" | sha256sum -c -
done <<'EOF'
d480f4f97405fac3600652e2e14fd0b14339031c0af4da11582994878f04d919 ChakraPetch-Medium.ttf
45264de3204ddbd5fb3e14a2402acd5c630d16650ae5fc221d2c52da46a6734b ChakraPetch-SemiBold.ttf
65fbf76d95651697275e19db4d717c0e95a789ddd3476478b05292104db278a0 ChakraPetch-Bold.ttf
13831d02389d917d22fcfa6c79f98f8acbf61d230add0e73a4d4dc5f3bfb9e56 OFL.txt
EOF
fc-cache -f
# (read the list once: `fc-list | grep -q` fails under pipefail when grep stops early)
FAMILIES=$(fc-list : family | tr ',' '\n' | sort -u)
echo "--- font families: $(grep -E '^(Inter|Chakra|Cascadia)' <<<"$FAMILIES" | tr '\n' ' ')"
grep -qx "Chakra Petch" <<<"$FAMILIES" || { echo "Chakra Petch not found by fontconfig"; exit 1; }
grep -qx "Inter" <<<"$FAMILIES" || { echo "Inter not found by fontconfig"; exit 1; }
CHAKRA_BOLD="$FDIR/ChakraPetch-Bold.ttf"

# --- the logo as an icon, for the launcher, About This System and os-release (LOGO=sparkos)
for s in 16 22 24 32 48 64 96 128 256 512; do
  d="/usr/share/icons/hicolor/${s}x${s}/apps"
  mkdir -p "$d"
  render "$BOT" "$s" "$d/sparkos.png"
done
render "$BOT" 256 /usr/share/pixmaps/sparkos-logo.png
gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true

# --- wallpaper: the dark field, the bot large and faint, one slipped magenta/cyan scan line
WALL=/usr/share/wallpapers/SparkOS/contents/images
mkdir -p "$WALL"
# (positions from the approved 1440x900 mockup, scaled by height: x2.4)
render "$BOT" 1488 "$WORK/bot-wall.png"
magick -size 3840x2160 xc:'#0a0919' \
  \( "$WORK/bot-wall.png" -alpha on -channel A -evaluate multiply 0.13 +channel \) \
  -gravity southeast -geometry +144+96 -composite -gravity northwest \
  -fill 'rgba(255,46,136,0.35)' -draw 'rectangle 0,1469 3839,1471' \
  -fill 'rgba(34,216,255,0.35)' -draw 'rectangle 0,1476 3839,1478' \
  "$WALL/3840x2160.png"
magick "$WALL/3840x2160.png" -resize 1920x1080 "$WALL/1920x1080.png"
magick "$WALL/3840x2160.png" -resize 400x225 /usr/share/wallpapers/SparkOS/contents/screenshot.png

# --- boot splash (Plymouth): the bot hammering the anvil over the spaced wordmark, with the
# magenta/cyan slip, on every screen
PLY=/usr/share/plymouth/themes/sparkos
word() { magick -background none -fill "$1" -font "$CHAKRA_BOLD" -pointsize 34 -kerning 11 label:SPARKOS "$2"; }
word '#f1efff' "$WORK/w.png"
word '#ff2e88' "$WORK/wa.png"
word '#22d8ff' "$WORK/wb.png"
magick \
  \( "$WORK/wb.png" -alpha on -channel A -evaluate multiply 0.9 +channel -repage +0+0 \) \
  \( "$WORK/wa.png" -alpha on -channel A -evaluate multiply 0.9 +channel -repage +6+0 \) \
  \( "$WORK/w.png" -repage +3+0 \) \
  -background none -layers merge +repage "$WORK/wordmark.png"
# Plymouth's two-step plugin loops "throbber" frames and always plays the whole set in 2.0 s,
# however many frames there are (THROBBER_DURATION in plymouth's ply-throbber.c). So one loop is
# one hammer blow from the bot's animation (bot.gif, 25 fps): the hammer held up for
# 21 frames, then GIF frames 25-53 (raised, the blow with its sparks, the rebound, raised again).
# 50 frames x 0.04 s = 2.0 s, the GIF's own speed.
magick "$SRC/bot.gif" -coalesce -resize 240x240 "$WORK/gif-%03d.png"
test -s "$WORK/gif-053.png" || { echo "bot.gif is shorter than the boot splash loop needs"; exit 1; }
n=0
for i in $(printf '25 %.0s' $(seq 21)) $(seq 25 53); do
  n=$((n + 1))
  magick "$WORK/gif-$(printf %03d "$i").png" -background none -gravity center \
    \( -size 1x26 xc:none \) "$WORK/wordmark.png" -append +repage "$PLY/throbber-$(printf %04d "$n").png"
done
test "$n" -eq 50
# Password and dialog pieces (for encrypted disks) from Fedora's spinner theme
for f in bullet.png entry.png lock.png capslock.png keyboard.png keymap-render.png; do
  if [ -f "/usr/share/plymouth/themes/spinner/$f" ]; then cp "/usr/share/plymouth/themes/spinner/$f" "$PLY/"; fi
done
mkdir -p /etc/plymouth
printf '[Daemon]\nTheme=sparkos\nShowDelay=0\nDeviceTimeout=15\nUseSimpledrmNoLuks=1\n' > /etc/plymouth/plymouthd.conf

# --- os-release: the SparkOS logo and SparkOS's own links
sed -i \
  -e 's/^LOGO=.*/LOGO=sparkos/' \
  -e 's|^DOCUMENTATION_URL=.*|DOCUMENTATION_URL="https://github.com/Wolklaw/sparkos/tree/main/docs"|' \
  -e 's|^SUPPORT_URL=.*|SUPPORT_URL="https://github.com/Wolklaw/sparkos/issues"|' \
  /usr/lib/os-release
grep -q '^LOGO=sparkos$' /usr/lib/os-release

# --- rebuild the initramfs so it carries the SparkOS boot splash (and its fonts)
KVER=$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -1)
test -n "$KVER"
export DRACUT_NO_XATTR=1
# Upgrade again before dracut. Steps after packages.sh install more packages and can pull a newer
# library without the rest of its build (see packages.sh: libzstd 1.6.0 with the zstd 1.5.7
# command broke dracut, which packs the initramfs with zstd). Then check zstd runs.
dnf -y upgrade --exclude='kernel*'
echo ok | zstd -q > /dev/null
# dracut copies the groups and users that udev rules name (GROUP="kvm", OWNER=...) from /etc/group
# and /etc/passwd. In an image most of them live in /usr/lib/group and /usr/lib/passwd
# (nss-altfiles), so the initramfs lacked audio, disk, kvm, video, render, utmp... and every boot
# logged "Failed to resolve group" errors. Give dracut the full lists, then put the files back.
cp -a /etc/group "$WORK/group.orig"
cp -a /etc/passwd "$WORK/passwd.orig"
awk -F: 'NR==FNR { seen[$1] = 1; next } !seen[$1]' /etc/group /usr/lib/group >> /etc/group
awk -F: 'NR==FNR { seen[$1] = 1; next } !seen[$1]' /etc/passwd /usr/lib/passwd >> /etc/passwd
dracut_status=0
dracut --no-hostonly --kver "$KVER" --reproducible --zstd -v --add ostree --force \
  "/usr/lib/modules/$KVER/initramfs.img" > "$WORK/dracut.log" 2>&1 || dracut_status=$?
cp -a "$WORK/group.orig" /etc/group
cp -a "$WORK/passwd.orig" /etc/passwd
[ "$dracut_status" = 0 ] || { tail -40 "$WORK/dracut.log"; exit 1; }
for g in audio disk kvm video render utmp; do
  lsinitrd -f etc/group "/usr/lib/modules/$KVER/initramfs.img" | grep -q "^$g:" \
    || { echo "initramfs /etc/group lacks $g"; exit 1; }
done
chmod 0600 "/usr/lib/modules/$KVER/initramfs.img"
lsinitrd "/usr/lib/modules/$KVER/initramfs.img" > "$WORK/initrd.txt"
grep -q 'plymouth/themes/sparkos/throbber-0050.png' "$WORK/initrd.txt" || { echo "SparkOS boot splash is not in the initramfs"; exit 1; }
grep -q 'Theme=sparkos' <(lsinitrd -f etc/plymouth/plymouthd.conf "/usr/lib/modules/$KVER/initramfs.img") \
  || { echo "initramfs plymouthd.conf does not select sparkos"; exit 1; }

# --- clean up
dnf -y remove librsvg2-tools
rm -rf "$WORK"

# --- check every piece is in place
for f in \
  /usr/share/color-schemes/SparkOS.colors \
  "$WALL/3840x2160.png" /usr/share/wallpapers/SparkOS/metadata.json \
  "$PLY/sparkos.plymouth" "$PLY/throbber-0001.png" "$PLY/throbber-0050.png" \
  /usr/share/icons/hicolor/256x256/apps/sparkos.png /usr/share/pixmaps/sparkos-logo.png; do
  test -s "$f" || { echo "missing $f"; exit 1; }
done
echo "SparkOS look installed (kernel $KVER)."
