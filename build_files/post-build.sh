#!/usr/bin/bash
# Containerfile step 8: clean up at the end (what BlueBuild's post_build.sh does).
set -euo pipefail
shopt -s nullglob

# Anything installed under /opt (now in /usr/lib/opt) gets a link back at /opt/<name> on the
# running system, through systemd-tmpfiles. (FreeSuite also makes its own; both point to the
# same place.)
optfix_dir=/usr/lib/opt
optdirs=("$optfix_dir"/*)
if [ ${#optdirs[@]} -gt 0 ]; then
  echo "Links for packages installed in /opt:"
  for optdir in "${optdirs[@]}"; do
    opt=$(basename "$optdir")
    echo "L+?  \"/opt/$opt\"  -  -  -  -  $optfix_dir/$opt" | tee "/usr/lib/tmpfiles.d/99-sparkos-optfix-$opt.conf"
  done
fi

# Home folders live in /var/home. rpm-ostree tells SELinux so in file_contexts.subs_dist (the
# "/var/home /home" alias turned around), but a selinux-policy upgrade in this build puts the
# stock file back. Then every home folder is labelled default_t: sshd can't read ~/.ssh and
# a relabel breaks people's homes. Put the alias back and check that it works.
subs=/etc/selinux/targeted/contexts/files/file_contexts.subs_dist
sed -i 's|^/var/home[[:space:]]\+/home$|# &|' "$subs"
grep -qx '/home /var/home' "$subs" || echo '/home /var/home' >> "$subs"
for path in /var/home/someone/.ssh /home/someone/.ssh; do
  label=$(matchpathcon -n "$path")
  case "$label" in
    *:ssh_home_t:*) ;;
    *) echo "SELinux labels $path as $label, not ssh_home_t ($subs)"; exit 1 ;;
  esac
done

# The running system makes its own /var and /tmp: leave them empty in the image, and put /opt
# back as the link into /var that Fedora Atomic expects. (This step's own mount, build_files
# under /tmp, is left alone; it isn't part of the image.)
find /tmp -mindepth 1 -maxdepth 1 ! -path /tmp/build_files -exec rm -rf {} +
rm -rf /var/* /opt
ln -fs /var/opt /opt

# Keep rpm-ostree's copy of the package database the same file as the real one, so
# `rpm-ostree status` and updates see what this image installed and removed, not the base
# image's list. https://github.com/coreos/rpm-ostree/issues/4554
for file in rpmdb.sqlite rpmdb.sqlite-shm rpmdb.sqlite-wal; do
  target="/usr/share/rpm/$file"
  link="/usr/lib/sysimage/rpm-ostree-base-db/$file"
  if [ -f "$target" ] && [ -f "$link" ]; then
    ln -f "$target" "$link"   # a hard link, not a symlink
  fi
done
echo "Cleaned up."
