#!/usr/bin/env bash
# Checks the kernel modules pinned in build_files/kmods.sh against their projects on GitHub.
# For each "name|https://github.com/OWNER/REPO/archive/COMMIT.tar.gz|SHA256|licence" line whose
# project has newer commits on its default branch, it downloads that branch's newest archive,
# computes its SHA-256 and rewrites the line (with --write), so a build can try the new code.
#
#   tools/pin-check.sh            report only
#   tools/pin-check.sh --write    also rewrite build_files/kmods.sh
#
# Prints one line per module (same / newer / other / error) and, with --write, the changed names to
# the file named by $PIN_CHANGES (one per line) for the workflow's pull request.
# Needs curl, sha256sum and either gh (logged in) or GITHUB_TOKEN for the API.
set -euo pipefail

here=$(cd "$(dirname "$0")/.." && pwd)
f=$here/build_files/kmods.sh
write=no
[ "${1:-}" = --write ] && write=yes
changes=${PIN_CHANGES:-/dev/null}
: >"$changes"

api() {
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    gh api "$1"
  else
    curl -fsSL ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} "https://api.github.com/$1"
  fi
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
rc=0
while IFS='|' read -r name url sum lic; do
  [[ $url =~ ^https://github\.com/([^/]+)/([^/]+)/archive/([0-9a-f]{40})\.tar\.gz$ ]] || continue
  repo=${BASH_REMATCH[1]}/${BASH_REMATCH[2]} pinned=${BASH_REMATCH[3]}
  if ! branch=$(api "repos/$repo" | python3 -c 'import json,sys; print(json.load(sys.stdin)["default_branch"])') ||
     ! head=$(api "repos/$repo/commits/$branch" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])'); then
    echo "error  $name: can't read $repo"; rc=1; continue
  fi
  if [ "$head" = "$pinned" ]; then
    echo "same   $name ($repo ${pinned:0:12})"; continue
  fi
  # only a pin the branch has moved past is bumped; a pin from another branch (diverged, or
  # newer than the branch) is left for a person to look at
  read -r status behind < <(api "repos/$repo/compare/$pinned...$head" |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status","?"), d.get("ahead_by","?"))' ||
    echo "? ?")
  if [ "$status" != ahead ]; then
    echo "other  $name: ${pinned:0:12} is $status against $repo $branch (${head:0:12}); not bumped"; continue
  fi
  echo "newer  $name: $repo $branch is $behind commits past ${pinned:0:12} (now ${head:0:12})"
  [ "$write" = yes ] || continue
  new=https://github.com/$repo/archive/$head.tar.gz
  if ! curl -fsSL --retry 3 -o "$tmp/a.tgz" "$new"; then
    echo "error  $name: can't download $new"; rc=1; continue
  fi
  newsum=$(sha256sum "$tmp/a.tgz" | cut -d' ' -f1)
  sed -i "s#\"$name|$url|$sum|#\"$name|$new|$newsum|#" "$f"
  grep -qF "\"$name|$new|$newsum|" "$f" || { echo "error  $name: rewrite failed"; rc=1; continue; }
  echo "$name $repo ${pinned:0:12}..${head:0:12} ($behind commits)" >>"$changes"
done < <(sed -n 's/^[[:space:]]*"\([^"]*\)"[[:space:]]*$/\1/p' "$f")
exit $rc
