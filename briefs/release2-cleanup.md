# Release 2 cleanup: fewer outside dependencies in the image

Read [README.md](README.md) first. This is image work, not a new app. It is the one session
allowed to edit `recipes/recipe.yml`, `files/scripts/*.sh` (except the Spark apps' own) and
`.github/workflows/boot-test.yml` while the other Release 2 sessions run. Those sessions only touch
their own app folders.

## Goal

The owner wants SparkOS to rely on other people's products as little as possible
([PLAN.md, Independence roadmap](../PLAN.md)). Each item below is small. Do them as separate
commits on one branch (`release2-cleanup`), each with a boot-test check that proves it.

1. **Keep Chakra Petch in the repo.** `files/scripts/sparkos-theme.sh` downloads it from Google's
   GitHub at every build (pinned commit, checksums). Put the three TTFs and `OFL.txt` in
   `files/sparkos-theme/fonts/` and install from there. No network for fonts.
2. **Remove Plasma System Monitor.** Spark Monitor (`files/spark-monitor`) ships and opens on
   Ctrl+Shift+Esc. Remove `plasma-systemmonitor` in the recipe, make Ctrl+Esc open Spark Monitor too
   (Plasma's default for its own monitor), and check nothing else in the image needs it
   (`rpm -q --whatrequires`). Update the recipe's policy comment.
3. **Open `.AppImage` files without Gear Lever.** `files/system/usr/bin/sparkos-open-package`
   fetches Gear Lever from Flathub on first use. Replace that path with SparkOS's own handling: ask
   once (kdialog) whether to run it now or add it to the menu; "add" moves it to `~/Applications/`,
   makes it executable, extracts its `.desktop` file and icon (`--appimage-extract '*.desktop'`
   and the icon it names, in a temp dir), and writes a menu entry pointing at the moved file, with
   a "Remove" action that deletes both. AppImages need FUSE 2 (`fuse-libs`); make sure it's in the
   image. Update [docs/installing-apps.md](../docs/installing-apps.md).
4. **Remove Tailscale.** Bazzite preinstalls it (a third-party service). Check it's there
   (`rpm -q tailscale`, its service), remove the package and any enabled unit. It stays
   installable for anyone who wants it; say how in the switching guide.
5. **Stop calling home to services SparkOS doesn't control:**
   - Fedora's usage counting: disable `rpm-ostree-countme.timer` (and DNF's countme if set).
   - NetworkManager's connectivity check to Fedora's servers: check what config ships
     (`NetworkManager-config-connectivity-fedora`?). Disabling it loses captive-portal detection
     (hotel and café Wi-Fi sign-in pages), so don't just turn it off: tell the owner the trade-off in
     the PR and leave it as is until they choose (off, or a SparkOS-owned check URL later).
   - KDE's "Get New Stuff" (downloads themes and add-ons from store.kde.org inside Settings): hide
     it with `[KDE Action Restrictions] ghns=false` in `/etc/xdg/kdeglobals`.
   - List anything else in the image that contacts an outside service on its own (look at enabled
     timers and services); report it in the PR. Don't remove what you're unsure about.

Use the `inspect` workflow (`gh workflow run inspect.yml -f command=...`) to look inside the
published image before and after.

## Done when

The image builds, the boot test passes with a check for each item (fonts installed with no
download, no `plasma-systemmonitor`, `.AppImage` opens with the Spark handler, no `tailscale`,
countme timer disabled, GHNS hidden), and a PR from `release2-cleanup` is open for the owner.
The connectivity-check choice is stated in the PR for the owner.
