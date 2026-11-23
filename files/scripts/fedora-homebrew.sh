#!/usr/bin/env bash
# Containerfile step 5. Homebrew works in every shell once it's installed in /home/linuxbrew/.linuxbrew (sources: files/homebrew).
#
# Fedora has no shell setup for Homebrew, so these are SparkOS's own:
#   /etc/profile.d/brew.sh                     PATH, MANPATH, INFOPATH, zsh completion (bash, zsh)
#   /etc/profile.d/brew-bash-completion.sh     bash completion
#   /usr/share/fish/vendor_conf.d/sparkos-brew.fish   the same for fish, if someone installs it
# Each does nothing when Homebrew isn't installed.
#
#   brew-update.timer, brew-upgrade.timer      Homebrew's automatic updates, run as the user who
#                                              owns Homebrew (/usr/libexec/sparkos-brew-run). Off
#                                              until `sparkos-dev-setup --brew` (00-sparkos-homebrew.preset).
#
# Not here: Homebrew itself. A new install gets Homebrew from brew.sh's installer (`spark brew`); `sparkos-dev-setup --brew` says so.
set -oue pipefail

src=${CONFIG_DIRECTORY:-/tmp/files}/homebrew
install -Dm644 "$src/brew.sh" /etc/profile.d/brew.sh
install -Dm644 "$src/brew-bash-completion.sh" /etc/profile.d/brew-bash-completion.sh
install -Dm644 "$src/sparkos-brew.fish" /usr/share/fish/vendor_conf.d/sparkos-brew.fish
install -Dm755 "$src/sparkos-brew-run" /usr/libexec/sparkos-brew-run
for unit in brew-update.service brew-update.timer brew-upgrade.service brew-upgrade.timer; do
  install -Dm644 "$src/$unit" "/usr/lib/systemd/system/$unit"
done
systemctl preset brew-update.timer brew-upgrade.timer
for timer in brew-update.timer brew-upgrade.timer; do
  state=$(systemctl is-enabled "$timer" || true)
  [ "$state" = disabled ] || { echo "$timer is $state, should be off until sparkos-dev-setup --brew"; exit 1; }
done
echo "Homebrew shell setup and update timers installed (they do nothing until Homebrew is installed)"
