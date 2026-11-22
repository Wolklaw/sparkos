# SparkOS: Homebrew in fish, when Homebrew is installed in /home/linuxbrew/.linuxbrew.
# Installed as /usr/share/fish/vendor_conf.d/sparkos-brew.fish on the Fedora base
# (files/scripts/fedora-homebrew.sh). Same result as /etc/profile.d/brew.sh: Homebrew's folders
# at the end of PATH, so the system's own programs win. Does nothing without Homebrew.
if test -x /home/linuxbrew/.linuxbrew/bin/brew
    set -gx HOMEBREW_PREFIX /home/linuxbrew/.linuxbrew
    set -gx HOMEBREW_CELLAR $HOMEBREW_PREFIX/Cellar
    set -gx HOMEBREW_REPOSITORY $HOMEBREW_PREFIX/Homebrew
    # adds only what's missing, so a PATH that came from the login shell stays as it is
    fish_add_path --global --append --path $HOMEBREW_PREFIX/bin $HOMEBREW_PREFIX/sbin
    if not contains $HOMEBREW_PREFIX/share/info $INFOPATH
        set -gx INFOPATH $HOMEBREW_PREFIX/share/info $INFOPATH
    end
    if status --is-interactive
        for dir in $HOMEBREW_PREFIX/share/fish/completions $HOMEBREW_PREFIX/share/fish/vendor_completions.d
            if test -d $dir; and not contains $dir $fish_complete_path
                set -ga fish_complete_path $dir
            end
        end
    end
end
