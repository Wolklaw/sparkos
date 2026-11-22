#!/usr/bin/env bash
# Fedora base only (Containerfile step 5, SPARKOS_BASE=fedora). Homebrew works in every shell
# once it's installed in /home/linuxbrew/.linuxbrew (sources: files/homebrew).
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
# Not here: Homebrew itself (Bazzite ships a copy and unpacks it on first boot) and its update
# timers. A new install gets Homebrew from brew.sh's installer; `sparkos-dev-setup --brew` says so.
set -oue pipefail

src=${CONFIG_DIRECTORY:-/tmp/files}/homebrew
install -Dm644 "$src/brew.sh" /etc/profile.d/brew.sh
install -Dm644 "$src/brew-bash-completion.sh" /etc/profile.d/brew-bash-completion.sh
install -Dm644 "$src/sparkos-brew.fish" /usr/share/fish/vendor_conf.d/sparkos-brew.fish
echo "Homebrew shell setup installed (does nothing until Homebrew is installed)"
