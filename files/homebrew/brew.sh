# SparkOS: Homebrew on PATH, when Homebrew is installed in /home/linuxbrew/.linuxbrew.
# Installed as /etc/profile.d/brew.sh on the Fedora base (files/scripts/fedora-homebrew.sh). Does
# nothing when Homebrew isn't installed.
#
# Sourced by login shells (bash, and zsh through Fedora's /etc/zprofile) and by bash's
# /etc/bashrc, so it is plain sh that runs again safely. It sets what `brew shellenv` sets,
# without starting brew (Ruby) on every shell. Homebrew's folders go at the end of PATH,
# so the system's own programs (dbus, python3, ...) win over Homebrew's copies.
if [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
  HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew
  HOMEBREW_CELLAR=$HOMEBREW_PREFIX/Cellar
  HOMEBREW_REPOSITORY=$HOMEBREW_PREFIX/Homebrew
  export HOMEBREW_PREFIX HOMEBREW_CELLAR HOMEBREW_REPOSITORY
  case ":${PATH-}:" in
    *":$HOMEBREW_PREFIX/bin:"*) ;;
    *) PATH="${PATH:+$PATH:}$HOMEBREW_PREFIX/bin:$HOMEBREW_PREFIX/sbin"; export PATH ;;
  esac
  # An empty entry in MANPATH means "and the usual places", which man works out from PATH,
  # Homebrew's man pages included. Only needed when MANPATH is set at all.
  if [ -n "${MANPATH-}" ]; then
    case ":$MANPATH:" in
      *::*) ;;
      *) MANPATH="$MANPATH:"; export MANPATH ;;
    esac
  fi
  case ":${INFOPATH-}:" in
    *":$HOMEBREW_PREFIX/share/info:"*) ;;
    *) INFOPATH="$HOMEBREW_PREFIX/share/info:${INFOPATH-}"; export INFOPATH ;;
  esac
  # zsh: completions for brew and the tools it installs
  if [ -n "${ZSH_VERSION-}" ] && [ -d "$HOMEBREW_PREFIX/share/zsh/site-functions" ]; then
    eval 'case " ${fpath[*]} " in
      *" $HOMEBREW_PREFIX/share/zsh/site-functions "*) ;;
      *) fpath=("$HOMEBREW_PREFIX/share/zsh/site-functions" $fpath); export FPATH ;;
    esac'
  fi
fi
