#!/usr/bin/env bash
# Build Spark Run's test programs (CI, in a Fedora container):
#   hello64.exe, hello32.exe   Spark Hello, with an icon and a version resource
#   spark-hello-setup.exe      an NSIS installer for it (Start Menu shortcuts, uninstaller)
#   spark-hello-msi.msi        an .msi for the 32-bit one (wixl), no shortcut
#   needs-missing-dll.exe      imports sparkmissing.dll, which doesn't exist
# Usage: build.sh OUT_DIR   (needs mingw64-gcc mingw32-gcc mingw32-nsis msitools python3-pillow)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?output folder}
mkdir -p "$out"
work=$(mktemp -d)
cp "$here"/hello.c "$here"/hello.rc "$here"/setup.nsi "$here"/hello.wxs \
   "$here"/needs-missing-dll.c "$here"/missing.def "$work/"
cd "$work"

# the icon: Spark Run's own drawing, as a multi-size .ico (16-256 px)
python3 - "$here/../../icons" <<'PY'
import sys
from PIL import Image
icons = sys.argv[1]
Image.open(f"{icons}/spark-run-256.png").save(
    "hello.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
PY

for arch in x86_64 i686; do
  bits=$([ $arch = x86_64 ] && echo 64 || echo 32)
  $arch-w64-mingw32-windres hello.rc -O coff -o hello$bits.res
  $arch-w64-mingw32-gcc -O2 -s -static-libgcc -o hello$bits.exe hello.c hello$bits.res
done
x86_64-w64-mingw32-dlltool -d missing.def -l libsparkmissing.a
x86_64-w64-mingw32-gcc -O2 -s -o needs-missing-dll.exe needs-missing-dll.c -L. -lsparkmissing
makensis -V2 setup.nsi
wixl -o spark-hello-msi.msi hello.wxs

cp hello64.exe hello32.exe spark-hello-setup.exe spark-hello-msi.msi needs-missing-dll.exe "$out/"
cd /
rm -rf "$work"
ls -l "$out"
file "$out"/* 2>/dev/null || true
