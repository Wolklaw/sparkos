#!/usr/bin/env bash
# CI: the file types for multi-part archive parts (dev.wolklaw.SparkArchive.xml), as GIO sees
# them (it reads the same shared-mime-info database as Qt).
#
#   mime_check.sh before OUT        what each sample file is before installing
#   mime_check.sh installed BEFORE  the parts have Spark Archive's types; nothing else changed
#   mime_check.sh removed BEFORE    after uninstalling: everything as before
#
# The samples: our parts (.r00 .r01 .s00 .z01 .z02 .7z.002 .zip.003 .tar.002), every name
# another installed type already claims with a glob that looks like ours (*.z64 and the
# like, read from globs2), and common archive names. Prints a table; fails on a difference.
set -euo pipefail
mode=$1 ref=$2
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT

ours=(photos.r00 photos.r01 photos.s00 photos.z01 photos.z02 photos.7z.002 photos.zip.003
      photos.tar.002)
others=(photos.rar photos.part2.rar photos.zip photos.7z photos.7z.001 photos.tar.gz
        photos.tar notes.txt script.r)
# names other types already claim that our globs would also match
for globs in /usr/share/mime/globs2 /usr/local/share/mime/globs2; do
  [ -f "$globs" ] || continue
  while IFS=: read -r _w type pattern _rest; do
    case "$type" in application/x-spark-*) continue ;; esac
    if printf '%s\n' "$pattern" | grep -Eqi '^\*\.([rsz][0-9][0-9]|(7z|zip|tar)\.[0-9]{3})$'; then
      others+=("sample${pattern#\*}")
    fi
  done < <(grep -v '^#' "$globs")
done

for name in "${ours[@]}" "${others[@]}"; do
  case "$name" in
    *.r00|*.rar) printf 'Rar!\x1a\x07\x00' > "$dir/$name" ;;   # a RAR volume starts so
    *.z01) printf 'PK\x07\x08' > "$dir/$name" ;;                # a split zip's first part
    *.txt|*.r) printf 'hello\n' > "$dir/$name"; continue ;;
    *) : > "$dir/$name" ;;
  esac
  # the same binary bytes every time (a NUL, then 0xff): content sniffing must not differ
  # between the checks, and must never take it for text
  { printf '\000'; head -c 199 /dev/zero | tr '\000' '\377'; } >> "$dir/$name"
done

type_of() {
  gio info -a standard::content-type "$1" 2>/dev/null | sed -n 's/^ *standard::content-type: //p'
}

if [ "$mode" = before ]; then
  for name in "${ours[@]}" "${others[@]}"; do
    printf '%s\t%s\n' "$name" "$(type_of "$dir/$name")"
  done | sort -u > "$ref"
  cat "$ref"
  exit 0
fi

fail=0
want() {   # name, type it should have now
  local got
  got=$(type_of "$dir/$1")
  if [ "$got" = "$2" ]; then echo "ok    $1: $got"; else echo "WRONG $1: $got (want $2)"; fail=1; fi
}
before() { awk -F'\t' -v n="$1" '$1 == n { print $2 }' "$ref"; }

if [ "$mode" = installed ]; then
  for name in "${ours[@]}"; do
    case "$name" in
      *.r[0-9][0-9]|*.s[0-9][0-9]) want "$name" application/x-spark-rar-part ;;
      *.z[0-9][0-9]) want "$name" application/x-spark-zip-part ;;
      *) want "$name" application/x-spark-split-part ;;
    esac
  done
else
  for name in "${ours[@]}"; do want "$name" "$(before "$name")"; done
fi
for name in "${others[@]}"; do want "$name" "$(before "$name")"; done
exit "$fail"
