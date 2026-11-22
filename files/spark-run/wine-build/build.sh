#!/usr/bin/env bash
# Builds the Wine that Spark Run downloads, from WineHQ's own source, as a relocatable "wow64"
# Wine: 64-bit Linux code only, running 32 and 64-bit Windows programs without any 32-bit Linux
# libraries. .github/workflows/wine-build.yml runs it twice, compares the results and publishes
# the archive as a release of this repository; sparkrun/sources.py pins its URL, size and SHA-256.
#
# Run as root in the pinned Fedora container (the workflow does), from anywhere:
#   bash build.sh OUTDIR       build; leaves OUTDIR/<name>.tar.xz and OUTDIR/build-info.txt
#   bash build.sh --name       print the archive's name (and its top folder), e.g. wine-11.22-1-amd64-wow64
#   bash build.sh --tag        print the release tag, e.g. wine-11.22-1
#
# Reproducible on purpose: the container image is pinned by digest, packages come only from
# Fedora 45's release repository (frozen since release day, no updates), the source is checked
# against WineHQ's signature and a pinned SHA-256, the build runs in /build, every timestamp is
# the source's own (SOURCE_DATE_EPOCH), and the archive is written in a fixed order with fixed
# owners. Two builds give the same SHA-256; the workflow checks that every time.
#
# To build a newer Wine: change WINE_VERSION and WINE_SHA256 (checked against WineHQ's .sign by
# the build), reset BUILD to 1, run the workflow, then pin the new archive in sources.py.
# Change BUILD alone to rebuild the same Wine differently (another Fedora, other options).
set -euo pipefail

WINE_VERSION=11.22
WINE_SHA256=f172e9c1be73e862057deae1f0e03ce95919986c5df8a18e1c0829c34863c9ee
BUILD=2   # 1 was built without the C++ cross-compilers (no icu.dll, dmsynth.dll); don't use it
WINE_URL="https://dl.winehq.org/wine/source/${WINE_VERSION%%.*}.x/wine-$WINE_VERSION.tar.xz"
# Alexandre Julliard, Wine's maintainer, signs every WineHQ source release with this key.
WINEHQ_KEY=DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D

NAME="wine-$WINE_VERSION-$BUILD-amd64-wow64"
case "${1:-}" in
  --name) echo "$NAME"; exit 0 ;;
  --tag) echo "wine-$WINE_VERSION-$BUILD"; exit 0 ;;
  ''|-*) echo "usage: bash build.sh OUTDIR | --name | --tag" >&2; exit 2 ;;
esac
OUT=$(mkdir -p "$1" && cd "$1" && pwd)
[ "$(id -u)" = 0 ] || { echo "run as root in the build container" >&2; exit 2; }
grep -q '^VERSION_ID=45$' /etc/os-release || { echo "expected Fedora 45" >&2; exit 2; }

# What Wine's configure looks for: cross-compilers for the Windows side, and headers for each
# Linux library it loads (most with dlopen, so they are not needed at run time unless used).
# No mingw32-*/mingw64-* libraries: Wine then uses its own bundled copies (FAudio, libpng, vkd3d,
# libxml2...) instead of needing Fedora's mingw DLLs next to it.
PACKAGES=(
  gcc make flex bison perl-interpreter xz tar gnupg2 findutils file binutils
  mingw32-gcc mingw64-gcc mingw32-gcc-c++ mingw64-gcc-c++
  alsa-lib-devel pulseaudio-libs-devel gstreamer1-devel gstreamer1-plugins-base-devel
  libavcodec-free-devel libavformat-free-devel libavutil-free-devel
  libX11-devel libXext-devel libXrender-devel libXi-devel libXrandr-devel libXcursor-devel
  libXcomposite-devel libXinerama-devel libXfixes-devel libXxf86vm-devel
  wayland-devel libxkbcommon-devel mesa-libGL-devel mesa-libEGL-devel libglvnd-devel
  vulkan-loader-devel vulkan-headers ocl-icd-devel opencl-headers
  freetype-devel fontconfig-devel gnutls-devel krb5-devel libnetapi-devel
  cups-devel dbus-devel systemd-devel libusb1-devel sdl2-compat-devel
  libgphoto2-devel sane-backends-devel libv4l-devel libpcap-devel pcsc-lite-devel unixODBC-devel
)
step() { echo; echo "=== $*"; }

step "Packages, from Fedora 45's release repository only"
# distro-sync first: the container image may carry newer packages from updates, and the -devel
# packages must match the libraries exactly. After it, every package is the release-day version.
dnf -y --repo=fedora distro-sync
dnf -y --repo=fedora --setopt=install_weak_deps=False install "${PACKAGES[@]}"

step "Source: $WINE_URL"
rm -rf /build && mkdir -p /build && cd /build
curl -fsSL --retry 5 -o "wine-$WINE_VERSION.tar.xz" "$WINE_URL"
curl -fsSL --retry 5 -o "wine-$WINE_VERSION.tar.xz.sign" "$WINE_URL.sign"
echo "$WINE_SHA256  wine-$WINE_VERSION.tar.xz" | sha256sum -c -
export GNUPGHOME=/build/gnupg
mkdir -m 700 "$GNUPGHOME"
for server in "https://keys.openpgp.org/vks/v1/by-fingerprint/$WINEHQ_KEY" \
              "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x$WINEHQ_KEY"; do
  curl -fsSL --retry 3 "$server" -o key.asc && gpg --batch --quiet --import key.asc && break || true
done
gpg --batch --status-fd 1 --verify "wine-$WINE_VERSION.tar.xz.sign" "wine-$WINE_VERSION.tar.xz" \
  | grep -q "^\[GNUPG:\] VALIDSIG $WINEHQ_KEY " \
  || { echo "WineHQ's signature does not check out"; exit 1; }
echo "signed by $WINEHQ_KEY (WineHQ), SHA-256 matches the pin"
tar -xf "wine-$WINE_VERSION.tar.xz"

# Every timestamp the build writes (PE headers, the archive) is the source's own.
SOURCE_DATE_EPOCH=$(stat -c %Y "wine-$WINE_VERSION/VERSION")
export SOURCE_DATE_EPOCH TZ=UTC LC_ALL=C.UTF-8
FLAGS="-O2 -pipe -ffile-prefix-map=/build=."
CONFIGURE=(--prefix="/opt/$NAME" --enable-archs=i386,x86_64 --disable-tests --without-oss
           "CFLAGS=$FLAGS" "CROSSCFLAGS=$FLAGS" "LDFLAGS=-Wl,--build-id=sha1")

step "configure ${CONFIGURE[*]}"
mkdir build && cd build
../"wine-$WINE_VERSION"/configure "${CONFIGURE[@]}" > configure.log 2>&1 || { tail -50 configure.log; exit 1; }
# What configure turned off (a missing feature is a missing -devel package above)
sed -n '/^configure: WARNING\|^configure: libs\|^configure: Finished/p' configure.log | sort -u
# Left out on purpose: OSS (--without-oss) and CAPI (ISDN; Fedora has no capi4linux).
if grep '^configure: WARNING' configure.log | grep -v -i 'capi\|oss' | grep -q .; then
  echo "configure left something out (above): add the missing package"; exit 1
fi

step "make ($(nproc) threads)"
start=$(date +%s)
make -j"$(nproc)" > make.log 2>&1 || { grep -E -B5 -A5 'error|Error' make.log | tail -80; exit 1; }
make_seconds=$(( $(date +%s) - start ))
echo "built in $((make_seconds / 60)) min $((make_seconds % 60)) s"

step "install (runtime only, no headers or development tools)"
make install-lib DESTDIR=/build/stage > install.log 2>&1 || { tail -40 install.log; exit 1; }
cd /build
mv "stage/opt/$NAME" "$NAME"
# Debug symbols off the Linux side (the Windows side is built without them)
find "$NAME" -type f -print0 | while IFS= read -r -d '' f; do
  case "$(file -b "$f")" in ELF*) strip --strip-unneeded "$f" ;; esac
done
test -x "$NAME/bin/wine" && test -x "$NAME/bin/wineserver"
test -d "$NAME/lib/wine/x86_64-windows" && test -d "$NAME/lib/wine/i386-windows"
test -f "$NAME/lib/wine/x86_64-unix/ntdll.so"

step "archive"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --clamp-mtime --owner=0 --group=0 --numeric-owner \
    --mode='u+w,go-w' --format=gnu -cf - "$NAME" | xz -9 -T1 > "$OUT/$NAME.tar.xz"
sha256=$(sha256sum "$OUT/$NAME.tar.xz" | cut -d' ' -f1)
bytes=$(stat -c %s "$OUT/$NAME.tar.xz")

step "it runs from another folder (relocatable), 64 and 32-bit, with no display"
rm -rf /tmp/moved && mkdir /tmp/moved && tar -xJf "$OUT/$NAME.tar.xz" -C /tmp/moved
wine=/tmp/moved/$NAME/bin/wine
"$wine" --version
export WINEPREFIX=/tmp/smoke-prefix WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=d"
"$wine" wineboot -i
out64=$("$wine" cmd /c echo spark 64 | tr -d '\r')
out32=$("$wine" 'C:\windows\syswow64\cmd.exe' /c echo spark 32 | tr -d '\r')
"/tmp/moved/$NAME/bin/wineserver" -w
echo "$out64 / $out32"
[ "$out64" = "spark 64" ] && [ "$out32" = "spark 32" ] || { echo "smoke test failed"; exit 1; }
unset WINEPREFIX WINEDEBUG WINEDLLOVERRIDES

step "build info"
{
  echo "$NAME.tar.xz"
  echo "sha256: $sha256"
  echo "bytes: $bytes"
  echo "unpacked: $(du -sb "$NAME" | cut -f1) bytes"
  echo
  echo "Wine $WINE_VERSION from $WINE_URL"
  echo "source sha256: $WINE_SHA256 (signed by WineHQ key $WINEHQ_KEY)"
  echo "SOURCE_DATE_EPOCH: $SOURCE_DATE_EPOCH ($(date -u -d "@$SOURCE_DATE_EPOCH" +%FT%TZ))"
  echo "built on: $(. /etc/os-release && echo "$PRETTY_NAME"), container ${CONTAINER_IMAGE:-unknown}"
  echo "gcc: $(gcc -dumpfullversion), mingw: $(x86_64-w64-mingw32-gcc -dumpfullversion)"
  echo "configure: ${CONFIGURE[*]}"
  echo "make: $make_seconds s on $(nproc) threads"
  echo
  echo "Linux libraries each Wine module links to (most others are loaded with dlopen):"
  for f in "$NAME"/lib/wine/x86_64-unix/*.so; do
    printf '  %s: %s\n' "${f##*/}" "$(objdump -p "$f" | awk '/NEEDED/ {print $2}' | grep -v '^ntdll.so$\|^win32u.so$' | tr '\n' ' ')"
  done
  echo
  echo "configure warnings (features left out):"
  grep '^configure: WARNING' build/configure.log | sort -u | sed 's/^/  /' || echo "  none"
  echo
  echo "packages in the build container:"
  rpm -qa --qf '  %{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort
} > "$OUT/build-info.txt"
echo "$sha256  $NAME.tar.xz" > "$OUT/sha256sums.txt"
head -6 "$OUT/build-info.txt"
