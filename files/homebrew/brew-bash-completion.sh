# SparkOS: bash completion for brew and the tools it installs, when Homebrew is installed in
# /home/linuxbrew/.linuxbrew. Installed as /etc/profile.d/brew-bash-completion.sh on the Fedora
# base (files/scripts/fedora-homebrew.sh); the same name as Bazzite's file, so it takes its place
# when a PC moves from Bazzite. Does nothing when Homebrew isn't installed, outside interactive
# bash, or the second time.
if [ -n "${BASH_VERSION-}" ] && [ -n "${PS1-}" ] && [ -z "${BREW_BASH_COMPLETION-}" ] &&
  [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
  # brew's own completion is linked in on first use (once; needs write access, as the person
  # who installed Homebrew has)
  if [ -w /home/linuxbrew/.linuxbrew ] &&
    ! [ -L /home/linuxbrew/.linuxbrew/etc/bash_completion.d/brew ]; then
    /home/linuxbrew/.linuxbrew/bin/brew completions link >/dev/null 2>&1
  fi
  if [ -d /home/linuxbrew/.linuxbrew/etc/bash_completion.d ]; then
    for rc in /home/linuxbrew/.linuxbrew/etc/bash_completion.d/*; do
      # shellcheck disable=SC1090
      [ -r "$rc" ] && . "$rc"
    done
    unset rc
  fi
  BREW_BASH_COMPLETION=1
  export BREW_BASH_COMPLETION
fi
