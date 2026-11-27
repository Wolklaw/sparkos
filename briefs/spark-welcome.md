# Spark Welcome

Read [README.md](README.md) first for the conventions every Spark app follows.

## Why

SparkOS ships no third-party apps: no Steam, no Discord, no Firefox. That's the owner's decision, but
it means a new user lands on an empty desktop and has to know what to install and where. Bazzite
solved this with its Portal window, which SparkOS removes. Spark Welcome fills that gap, aimed at
people coming from Windows.

## What it does

Opens once at a user's first login, then stays in the menu as "Spark Welcome" for later. Every page
can be skipped, nothing installs without a click, and closing the window at any point is fine.

1. **Welcome.** One screen: what SparkOS is, what's on it (Soot, FreeSuite, Spark Snip, Spark Media),
   and that everything else is one click away. Show the SparkOS bot (`branding/sparkos-bot.svg`,
   rendered to PNG by `make_icons.py`).
2. **Games.** Tick boxes for the launchers, each with a one-line description and whose app it is:
   Steam (`com.valvesoftware.Steam`), Heroic for Epic, GOG and Amazon
   (`com.heroicgameslauncher.hgl`), Lutris for Battle.net and others (`net.lutris.Lutris`),
   ProtonUp-Qt (`net.davidotek.pupgui2`). Say honestly that games with kernel anti-cheat (Valorant,
   Fortnite, some Call of Duty and EA games) do not run on Linux, with a link to
   areweanticheatyet.com. If Spark Games is installed, mention it gathers every launcher's games in
   one place.
3. **Apps.** A short curated list by category, all Flathub IDs, unticked by default: chat (Discord,
   Signal, Telegram), music (Spotify), streaming and recording (OBS Studio), communication (Zoom),
   creative (GIMP, Krita, Kdenlive, Blender), utilities (KCalc, Bitwarden). Keep the list in one data
   file, easy to edit. "Find more in the Store" opens Bazaar.
4. **Bring your files from Windows.** Find Windows partitions (NTFS, via `lsblk -J -o
   NAME,FSTYPE,LABEL,MOUNTPOINT,SIZE`), mount them read-only with `udisksctl mount -o ro` (the user
   may be asked for their password), list the Windows user folders that have something in them
   (`Users/<name>/Desktop`, `Documents`, `Pictures`, `Videos`, `Music`, `Downloads`), show sizes,
   and copy the ticked ones into the matching SparkOS folders (`xdg-user-dir`). Copy, never move,
   never write to the Windows disk. Skip files that already exist with the same size. Show progress
   and a summary at the end. The owner will dual-boot, so this matters.
5. **Check this PC.** Read-only checks, each a green/amber line with a plain explanation and a fix
   button where one exists:
   - Graphics: GPU name and driver (`/sys/class/drm`, `vulkaninfo --summary`), Vulkan works.
   - Sound: an output device exists (`wpctl status`), with a "Play test sound" button.
   - Printers and scanners: `lpstat -e`, `scanimage -L`. "Add a printer" opens Settings' printer
     page. The owner has a Canon printer; driverless IPP should find it.
   - Network and Bluetooth: connected or not.
   - Updates: SparkOS updates itself in the background (`rpm-ostree status` for the current image
     date); say so.
6. **Done.** Three tips, with buttons: installing apps (Store, or double-click a downloaded `.exe`,
   `.AppImage` or `.rpm`), taking screenshots (Spark Snip, Print Screen), and where settings are.
   A "Show Spark Welcome at login" checkbox, off by default after this first run.

### 1.2: a step-by-step guide

The owner asked for an easy guide that welcomes people to SparkOS, says what's different from
Windows and what's still familiar, and helps them add their drives so their files work here and
Windows can be erased. Ten steps: Welcome, What's different, What's the same, Your drives, Your
files, Games, Apps, Check this PC, Erasing Windows, Done. Each page shows "Step N of 10" and a
"What to do here" box, and the Next button names the next step. The Drives step shows the Windows
drives SparkOS opens at boot (their letters are remembered, so they keep their folder after Windows
is gone) and adds other data drives to `/etc/fstab` through udisks, never formatting. The Erasing
Windows step lists what goes and what stays and points to Spark Disks; Spark Welcome never erases
anything. Tick boxes must look clickable (drawn box, border, hover).

Installs run in the background, one at a time, with `flatpak install --user --noninteractive
flathub <id>`, showing progress per app (parse flatpak's output, or show an indeterminate bar with the
current step). The user can keep moving through pages while they install. A failed install shows the
error and a Retry button; don't hide failures. Before the first install, make sure the Flathub user
remote exists (`flatpak remotes --user`; add it if missing).

## How it starts

Not in the first SparkOS build. Spark Welcome may later ship in the image (it matters most at the very
first login) or become the Spark Portal's first-run screen; that's the owner's call. Build it so either
works:

- `spark-welcome --first-login` exits at once if `~/.config/spark-welcome/done` exists, so later
  logins cost nothing.
- Installed with `install.sh --user`, it adds `~/.config/autostart/dev.wolklaw.SparkWelcome.desktop`
  (removed by `--uninstall`). Installed system-wide, the same entry goes in `/etc/xdg/autostart/`.
- Keep the steps (games, apps, files from Windows, checks) as separate modules with no window code
  in them, so the Portal can reuse them.
- Don't run in the installer's live session (user `liveuser`, or `/run/livesys` exists). The ISO has
  its own welcome dialog (`installer/system_files`).
- Write `done` when the user reaches the last page or closes the window.

## Tests

- Unit: the Windows-folder finder against a fake tree in a temp dir (several users, `Public`,
  `Default`, empty folders, junctions), the copy planner (sizes, skips, name clashes), the app list
  file loads, the flatpak command builder.
- UI under Xvfb: every page renders; skipping through all pages writes `done`; `--first-login` exits
  immediately when `done` exists.
- `--self-test`: the app list parses, `flatpak`, `udisksctl` and `lsblk` exist, the autostart entry
  is installed. No network, nothing installed.
- CI, inside the SparkOS image: `install.sh --user`, `--self-test`, `--uninstall` as a normal user.

## Done when

CI passes in Fedora and inside the SparkOS image, the app installs and uninstalls for one user with
no root, a fresh user account gets the window once at first login, and the PR is open for the owner.
It is not added to the recipe.
