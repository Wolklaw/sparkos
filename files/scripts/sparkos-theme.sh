#!/usr/bin/env bash
# The SparkOS look (Phase 3), everywhere from power-on to the desktop:
#   boot splash (Plymouth), sign-in screen wallpaper, the splash after sign-in, the desktop
#   (colours, fonts, top bar and floating dock, wallpaper), lock screen, Konsole, About This
#   System and fastfetch.
# Static files (colour scheme, look-and-feel package, Plymouth theme, /etc/xdg defaults) come
# from files/system. This script renders the images from the SparkOS bot (files/sparkos-theme,
# a copy of branding/sparkos-bot.svg), installs the fonts, and rebuilds the initramfs so the
# boot splash is in it.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/sparkos-theme"
BOT="$SRC/sparkos-bot.svg"
test -f "$BOT" || { echo "missing $BOT"; exit 1; }
WORK=$(mktemp -d)

# --- tools to render the SVG (removed again at the end; ImageMagick is already in Bazzite)
dnf -y install --setopt=install_weak_deps=False librsvg2-tools
render() { rsvg-convert -w "$2" -h "$2" -o "$3" "$1"; }

# --- fonts: Inter (Fedora package, from the recipe) and Chakra Petch (Google Fonts, pinned)
FONTS_COMMIT=e774067705989f0bcb5e32eb0e8f76c24d679f92
FONTS_URL="https://raw.githubusercontent.com/google/fonts/$FONTS_COMMIT/ofl/chakrapetch"
FDIR=/usr/share/fonts/chakra-petch
mkdir -p "$FDIR"
while read -r sum name; do
  curl -fsSL --retry 5 -o "$FDIR/$name" "$FONTS_URL/$name"
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

# --- look-and-feel previews and the splash image
LNF=/usr/share/plasma/look-and-feel/dev.wolklaw.sparkos.desktop/contents
mkdir -p "$LNF/previews" "$LNF/splash/images"
magick "$WALL/3840x2160.png" -resize 640x360 "$LNF/previews/preview.png"
magick "$WALL/3840x2160.png" -resize 1920x1080 -quality 90 "$LNF/previews/fullscreenpreview.jpg"
render "$BOT" 560 "$LNF/splash/images/bot.png"
cp "$LNF/splash/images/bot.png" "$LNF/previews/splash.png"

# --- boot splash (Plymouth): the bot over the spaced wordmark, with the magenta/cyan slip
PLY=/usr/share/plymouth/themes/sparkos
render "$BOT" 240 "$WORK/bot-boot.png"
word() { magick -background none -fill "$1" -font "$CHAKRA_BOLD" -pointsize 34 -kerning 11 label:SPARKOS "$2"; }
word '#f1efff' "$WORK/w.png"
word '#ff2e88' "$WORK/wa.png"
word '#22d8ff' "$WORK/wb.png"
magick \
  \( "$WORK/wb.png" -alpha on -channel A -evaluate multiply 0.9 +channel -repage +0+0 \) \
  \( "$WORK/wa.png" -alpha on -channel A -evaluate multiply 0.9 +channel -repage +6+0 \) \
  \( "$WORK/w.png" -repage +3+0 \) \
  -background none -layers merge +repage "$WORK/wordmark.png"
magick "$WORK/bot-boot.png" -background none -gravity center \
  \( -size 1x26 xc:none \) "$WORK/wordmark.png" -append "$PLY/watermark.png"
# Password and dialog pieces (for encrypted disks) from Fedora's spinner theme
for f in bullet.png entry.png lock.png capslock.png keyboard.png keymap-render.png; do
  if [ -f "/usr/share/plymouth/themes/spinner/$f" ]; then cp "/usr/share/plymouth/themes/spinner/$f" "$PLY/"; fi
done
mkdir -p /etc/plymouth
printf '[Daemon]\nTheme=sparkos\nShowDelay=0\nDeviceTimeout=15\nUseSimpledrmNoLuks=1\n' > /etc/plymouth/plymouthd.conf

# --- remove Bazzite's own look where it would still show
rm -fv /etc/xdg/autostart/bazzite-announcement.desktop

# --- os-release: the SparkOS logo and SparkOS's own links
sed -i \
  -e 's/^LOGO=.*/LOGO=sparkos/' \
  -e 's|^DOCUMENTATION_URL=.*|DOCUMENTATION_URL="https://github.com/Wolklaw/sparkos/tree/main/docs"|' \
  -e 's|^SUPPORT_URL=.*|SUPPORT_URL="https://github.com/Wolklaw/sparkos/issues"|' \
  /usr/lib/os-release
grep -q '^LOGO=sparkos$' /usr/lib/os-release

# --- fastfetch: the SparkOS bot in place of Bazzite's logo, in mint, cyan and gold
FF=/usr/share/ublue-os/bazzite
if [ -f "$FF/fastfetch.jsonc" ]; then
  cp "$SRC/fastfetch-logo.txt" "$FF/logo.txt"
  sed -i -E \
    -e 's/"1": "[^"]*"/"1": "38;2;155;232;184"/' \
    -e 's/"2": "[^"]*"/"2": "38;2;34;216;255"/' \
    -e 's/"3": "[^"]*"/"3": "38;2;244;201;93"/' \
    "$FF/fastfetch.jsonc"
fi

# --- rebuild the initramfs so it carries the SparkOS boot splash (and its fonts)
KVER=$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -1)
test -n "$KVER"
export DRACUT_NO_XATTR=1
dracut --no-hostonly --kver "$KVER" --reproducible --zstd -v --add ostree --force \
  "/usr/lib/modules/$KVER/initramfs.img" > "$WORK/dracut.log" 2>&1 || { tail -40 "$WORK/dracut.log"; exit 1; }
chmod 0600 "/usr/lib/modules/$KVER/initramfs.img"
lsinitrd "/usr/lib/modules/$KVER/initramfs.img" > "$WORK/initrd.txt"
grep -q 'plymouth/themes/sparkos/watermark.png' "$WORK/initrd.txt" || { echo "SparkOS boot splash is not in the initramfs"; exit 1; }
grep -q 'Theme=sparkos' <(lsinitrd -f etc/plymouth/plymouthd.conf "/usr/lib/modules/$KVER/initramfs.img") \
  || { echo "initramfs plymouthd.conf does not select sparkos"; exit 1; }

# --- clean up
dnf -y remove librsvg2-tools
rm -rf "$WORK"

# --- check every piece is in place
for f in \
  /usr/share/color-schemes/SparkOS.colors \
  /usr/share/plasma/look-and-feel/dev.wolklaw.sparkos.desktop/metadata.json \
  "$LNF/layouts/org.kde.plasma.desktop-layout.js" \
  "$LNF/splash/Splash.qml" "$LNF/splash/images/bot.png" "$LNF/previews/preview.png" \
  "$WALL/3840x2160.png" /usr/share/wallpapers/SparkOS/metadata.json \
  "$PLY/sparkos.plymouth" "$PLY/watermark.png" \
  /usr/share/icons/hicolor/256x256/apps/sparkos.png /usr/share/pixmaps/sparkos-logo.png \
  /usr/share/konsole/SparkOS.profile /usr/share/konsole/SparkOS.colorscheme; do
  test -s "$f" || { echo "missing $f"; exit 1; }
done
grep -q '^LookAndFeelPackage=dev.wolklaw.sparkos.desktop$' /etc/xdg/kdeglobals
grep -q '^Theme=dev.wolklaw.sparkos.desktop$' /etc/xdg/ksplashrc
echo "SparkOS look installed (kernel $KVER)."
