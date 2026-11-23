#!/usr/bin/env bash
# Containerfile step 5. Homebrew works in every shell once it's installed in /home/linuxbrew/.linuxbrew (sources: files/homebrew).
#
# On Bazzite, Homebrew's shell setup comes from Universal Blue: /etc/profile.d/brew.sh and
# brew-bash-completion.sh (in the image, but no package owns them) and
# /usr/share/fish/vendor_conf.d/ublue-brew.fish. Plain Fedora has none of them, so a PC that
# moves from Bazzite would keep Homebrew in /var/home/linuxbrew (/home is a link to /var/home,
# which an image change keeps) but lose it from PATH. These are SparkOS's own versions:
#   /etc/profile.d/brew.sh                     PATH, MANPATH, INFOPATH, zsh completion (bash, zsh)
#   /etc/profile.d/brew-bash-completion.sh     bash completion
#   /usr/share/fish/vendor_conf.d/sparkos-brew.fish   the same for fish, if someone installs it
# Each does nothing when Homebrew isn't installed. The profile.d files keep Bazzite's names so
# that on a move from Bazzite they replace its copies instead of running next to them.
#
#   brew-update.timer, brew-upgrade.timer      Homebrew's automatic updates, with Bazzite's names
#                                              and schedule, run as the user who owns Homebrew
#                                              (/usr/libexec/sparkos-brew-run). Off until
#                                              `sparkos-dev-setup --brew` (00-sparkos-homebrew.preset);
#                                              a PC that had them on under Bazzite keeps them on,
#                                              since /etc's links point at the same names.
#
# Not here: Homebrew itself (Bazzite ships a copy and unpacks it on first boot). A new install
# gets Homebrew from brew.sh's installer (`spark brew`); `sparkos-dev-setup --brew` says so.
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
