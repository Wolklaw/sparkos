#!/usr/bin/bash
# Containerfile step 3: copy a folder of files/ into the image (the recipe's "files" step).
#   copy-files.sh SOURCE DESTINATION     e.g. copy-files.sh system /
# Same as BlueBuild's files module: everything in files/SOURCE, dotfiles included, copied over
# what's there; a .gitkeep is not kept.
set -euo pipefail

src=${CONFIG_DIRECTORY:-/tmp/files}/${1:?source folder under files/}
dest=${2:?destination}
test -d "$src" || { echo "files/$1 not found"; exit 1; }

shopt -s dotglob
mkdir -p "$dest"
echo "Copying $src/* to $dest"
cp -rf "$src"/* "$dest"
rm -f "${dest%/}/.gitkeep"
