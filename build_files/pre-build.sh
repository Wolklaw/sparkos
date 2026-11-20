#!/usr/bin/bash
# Containerfile step 2: get the base image ready for the steps after it (what BlueBuild's
# pre_build.sh and the start of each of its module steps do).
#
# On Fedora Atomic /opt is a link into /var, which isn't part of the image. For the build, /opt
# points into /usr/lib/opt instead, so anything installed under /opt (FreeSuite's release tarball
# expects it) ends up in the image; post-build.sh adds the links that make /opt/<name> work on a
# running system.
set -euo pipefail

optfix_dir=/usr/lib/opt
echo "Preparing /opt: links to $optfix_dir during the build"
mkdir -pv "$optfix_dir"
if [ -d /opt ] || [ -h /opt ]; then
  if ls -A /opt/* >/dev/null 2>&1; then
    echo "Moving /opt/* into $optfix_dir"
    mv -v /opt/* "$optfix_dir"
  fi
  rm -fr /opt
fi
ln -fs "$optfix_dir" /opt

# Directories some package scripts expect under /var (roothome, alternatives...). They're
# emptied again at the end (post-build.sh); the running system makes its own /var.
mkdir -p /var/roothome /var/opt /var/lib/alternatives /var/usrlocal
