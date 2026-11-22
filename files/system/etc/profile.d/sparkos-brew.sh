# SparkOS: Homebrew's commands in PATH once it's set up (`spark brew`). Added at the end of PATH,
# so a Homebrew package never replaces a system command. On Bazzite, its own brew.sh (read
# first) has already done this and set HOMEBREW_PREFIX, so this does nothing there.
if [ -z "${HOMEBREW_PREFIX:-}" ] && [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv | grep -Ev '\bPATH=')"
  HOMEBREW_PREFIX="${HOMEBREW_PREFIX:-/home/linuxbrew/.linuxbrew}"
  export HOMEBREW_PREFIX
  case ":$PATH:" in
    *":$HOMEBREW_PREFIX/bin:"*) ;;
    *) export PATH="$PATH:$HOMEBREW_PREFIX/bin:$HOMEBREW_PREFIX/sbin" ;;
  esac
fi
