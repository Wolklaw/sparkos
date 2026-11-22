#!/usr/bin/env bash
# Run inside the SparkOS image by CI: what it has for archives today, so the PR can say what
# Spark Archive should own and what can leave with Ark. Prints only; never fails.
rpm -q --qf '%{NAME} %{VERSION} %{SIZE} bytes\n' libarchive 7zip unrar unar ark ark-libs p7zip 2>/dev/null
for p in libarchive 7zip unrar unar ark ark-libs; do
  echo "--- what needs $p:"
  rpm -q --whatrequires "$p" 2>/dev/null
done
echo "--- what needs libarchive.so.13:"
rpm -q --whatrequires 'libarchive.so.13()(64bit)' 2>/dev/null
echo "--- what recommends 7zip / unrar:"
rpm -q --whatrecommends 7zip 2>/dev/null; rpm -q --whatrecommends unrar 2>/dev/null
echo "--- 7z formats (rar?):"
7z i 2>/dev/null | grep -iE '\b(rar|rar5|iso|zip|7z|tar|zstd)\b' | head -20
echo "--- default apps for archives:"
grep -hiE 'zip|7z|rar|tar|iso|cd-image' /usr/share/applications/mimeapps.list \
  /etc/xdg/mimeapps.list /usr/share/applications/*-mimeapps.list 2>/dev/null | head -40
echo "--- service menus and file-item plugins:"
ls /usr/share/kio/servicemenus /usr/lib64/qt6/plugins/kf6/kfileitemaction 2>/dev/null
echo "--- desktop entries claiming archive types:"
grep -l -E 'MimeType=.*(application/zip|x-7z|vnd.rar|x-cd-image)' /usr/share/applications/*.desktop 2>/dev/null
exit 0
