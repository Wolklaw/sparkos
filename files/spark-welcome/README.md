# Spark Welcome

The first-login helper for SparkOS, aimed at people coming from Windows. It opens once at a user's first login and then stays in the menu as "Spark Welcome".

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

**Ships in the SparkOS image.** The build step is [files/scripts/spark-welcome.sh](../scripts/spark-welcome.sh), which runs `install.sh --deps` and puts the autostart entry in `/etc/xdg/autostart/`, so every new user gets the window once at their first login. It can also install for one user with no root (`install.sh --user`, below), for machines without it and for the future Spark Portal.

It is a step-by-step guide: each page says "Step N of 10", starts with a gold "What to do here" box, and the Next button names the next step. Every step can be skipped, nothing installs, copies or mounts until you click, and closing the window at any point is fine. Every on/off choice is a tick box (an empty box, or a filled box with a check mark) in a bordered chip with a hand cursor that lights up on hover and keyboard focus, so it reads as something to click. Click, Return or Space flips it.

1. **Welcome.** What SparkOS is, the list of the 10 steps with one line each, and a Start button.
2. **What's different.** Cards: apps come from the Store, Windows games run through Proton, updates replace the whole system (the previous version stays in the startup menu), no drive letters (C: is `/var/mnt/c`), the password instead of Yes / No, and the read-only system.
3. **What's the same.** The taskbar, window buttons, home folders, mouse and Ctrl shortcuts; a table of keyboard shortcuts; then "What you used on Windows": one line per Spark app with the Windows programs it replaces (Soot for Chrome and Edge, FreeSuite for Office, Outlook and Adobe Reader, Spark Files for File Explorer, and so on, 19 in all, listed in [sparkwelcome/switch.py](sparkwelcome/switch.py)), and an Open button when it's installed.
4. **Your drives.** Makes sure every drive with files opens at each start, so the files are usable without Windows ([sparkwelcome/drives.py](sparkwelcome/drives.py)).
   - **Windows drives** (NTFS, BitLocker) are opened by SparkOS at boot (`sparkos-windows-drives`, see [docs/windows-drives.md](../../docs/windows-drives.md)); the page reads its report and shows each one with its letter, folder, read-write / read-only / not opened badge, an Open button, and what to do when it is locked, hibernated or read-only on purpose. Letters are remembered, so D: stays `/var/mnt/d` after Windows is erased.
   - **Other drives** (exFAT, FAT32, ext4, Btrfs, XFS, F2FS partitions that aren't USB and aren't part of SparkOS) are listed with tick boxes. "Add" writes an `/etc/fstab` line through udisks (`Block.AddConfigurationItem`, the desktop asks for the password) at `/var/mnt/<label>` with `nofail`, then mounts it. It never formats or removes anything.
5. **Your files.** Finds NTFS partitions with `lsblk`, opens the one you pick read-only with `udisksctl mount -o ro` (the system may ask for your password), then:
   - **Your files.** Lists the Windows accounts' Desktop, Documents, Pictures, Videos, Music and Downloads that have files in them, with sizes, wherever Windows keeps them (OneDrive or another drive too: read from the account's `NTUSER.DAT` and the drive letters from the `SYSTEM` registry file, both read as plain files; other drives are opened read-only the same way), plus the fonts the account installed, and copies the ticked ones into the matching SparkOS folders (`xdg-user-dir`, fonts to `~/.local/share/fonts`). Copy, never move; nothing is opened for writing on the Windows drive. A file already here with the same size is skipped; a different file with the same name stays, and the copy is saved as `name (from Windows).ext`. Each file is written to a hidden temporary file and linked into place when complete, so a stopped copy leaves no half files and nothing already there is overwritten. Copies keep the Windows file's dates, not its permissions. Nothing is copied when the folders wouldn't leave 2 GB free. BitLocker drives are shown as locked. A drive Windows left hibernated (Fast Startup) won't mount, and the page says how to fix that.
   - **Your programs.** Reads the installed programs from the `SOFTWARE` hive and each account's `NTUSER.DAT` (uninstall keys, Store packages shown by readable name) and says for each one what to do here: the Spark app that replaces it (Open), a Linux version (Install, queued like the Apps page), Spark Games for game launchers, the website for apps with no Linux version, or "not needed" for drivers. Games with kernel-level anti-cheat are named as not working. Runtimes, drivers and Windows parts are left out; the rest are counted, and "Show their names" lists them with a Store button.
   - **Your Steam games.** Finds every Steam library on the Windows drives (`libraryfolders.vdf`, other drive letters through the `SYSTEM` hive), lists the games in each and how to add the folder in Steam so they don't download again, with an Open folder button.
6. **Games.** Spark Games first (one library for Steam, Epic, GOG and Amazon, and it adds Battle.net, the EA app, Ubisoft Connect and Rockstar on Wine), then Steam, the one launcher installed from here. Says plainly that games with kernel anti-cheat (Valorant, Fortnite, some Call of Duty and EA games) don't run on Linux, with a link to areweanticheatyet.com.
7. **Apps.** Optional Spark apps first (Spark Space, Spark Bench, Spark Connect: the ones in `/usr/share/spark-store/sources` not installed yet, each with what it replaces; installed with the source's `install.sh --user`). Then apps from other companies for what SparkOS doesn't do itself: Discord, Signal, Telegram, WhatsApp (web), Spotify, Amazon Music (Amazon's Windows app with `spark-run --get amazon-music`, Ultra HD), OBS Studio, Zoom, GIMP, Krita, Kdenlive, Blender, Bitwarden; all unticked, each saying whose app it is. The list is [sparkwelcome/apps.json](sparkwelcome/apps.json). "Find more in the Store" opens Spark Store.
8. **Check this PC.** Read-only, each a green or amber line with a plain explanation and a button where one helps: graphics (`/sys/class/drm`, `vulkaninfo --summary`), sound (`wpctl status`, Play test sound), printers and scanners (`lpstat -e`, `scanimage -L`, Add a printer), network and Bluetooth (`nmcli`, `bluetoothctl`), updates (`rpm-ostree status`).
9. **Erasing Windows.** Says what goes (C:) and which drives stay, with their folders; the checklist (passwords and bookmarks, OneDrive files, game saves, licences, two-step codes, the Wi-Fi password, BitLocker, Fast Startup, and keeping Windows for a normal week first); how to delete the Windows partition in Spark Disks (Open Spark Disks); and to leave the EFI partition alone. Spark Welcome never erases anything itself.
10. **Done.** Three tips (the Store and double-clicking downloaded `.exe`/`.AppImage`/`.rpm` files; the Windows keys that still work: Windows key, Ctrl+Shift+Esc, Print Screen; Spark Settings) and a "Show Spark Welcome at login" box, off by default.

Installs run in the background, one at a time, with `flatpak install --user --noninteractive flathub <id>` (Spark apps with their `install.sh --user`), so no admin password. Progress shows on the app's row and at the bottom of the window, and you can keep going through the pages. A failed install shows flatpak's error and a Retry button. Before the first install it adds the Flathub user remote if it's missing.

## How it starts

- The autostart entry runs `spark-welcome --first-login`. That exits at once (before Tk is loaded) when `~/.config/spark-welcome/done` exists, so later logins cost nothing. It also exits in the installer's live session (user `liveuser`, or `/run/livesys` exists).
- `done` is written when you reach the last page or close the window. Ticking "Show Spark Welcome at login" writes `~/.config/spark-welcome/show-at-login`, and the window opens at each login until you untick it.
- `install.sh --user` puts the autostart entry in `~/.config/autostart/`; the system-wide install puts it in `/etc/xdg/autostart/`.

The steps (`catalog.py`, `flatpak.py`, `windows.py`, `drives.py`, `switch.py`, `checks.py`) have no window code, so the Spark Portal can reuse them. `app.py` and `pages.py` are the window, and every sentence is in [strings.py](sparkwelcome/strings.py) in English and French (the language follows `LANG`).

## Install, run, test

```
bash install.sh --user                   # for you only, no root: ~/.local/lib, ~/.local/bin, ~/.local/share, ~/.config/autostart
bash install.sh --user --uninstall       # removes exactly those files; settings and log stay
sudo bash install.sh --deps              # system-wide with Fedora packages (what the image build runs)
python3 spark_welcome.py                 # run from here
python3 spark_welcome.py --page windows  # start on one page
python3 spark_welcome.py --self-test     # app list, Tk, flatpak, udisksctl, lsblk, autostart entry; no display, no network
python3 -m unittest discover -s tests -v
python3 make_icons.py                    # redraw icons/ (the mark, and the SparkOS bot from branding/)
```

It needs only what the SparkOS image already has: Python 3 with Tk, flatpak, udisks2 and util-linux. The checks also use vulkaninfo, wpctl, lpstat, scanimage, nmcli, bluetoothctl and rpm-ostree when they're there, and say so when one is missing. [spark-app.json](spark-app.json) describes the app for the Portal.

CI ([workflow](../../.github/workflows/spark-welcome.yml)) runs the image build step and all tests under Xvfb in a Fedora container, then, inside the published SparkOS image, installs it with `--user` as a normal user, runs `--self-test` and the unit tests on the image's Python, uninstalls it, and fails if any file is left in the home folder ([tests/ci-user-install.sh](tests/ci-user-install.sh)).

Settings are in `~/.config/spark-welcome/`, the log in `~/.local/state/spark-welcome/`.

## Known gaps

- Opened on a real SparkOS desktop in CI, not used by hand yet. The boot test signs in to the Spark session in a VM, where it opens by itself at the first sign-in, then opens it from the app menu in English and in French, keeps a screenshot and fails on a Python traceback. The pages were checked on Windows with a fake Windows drive; the checks and installs are covered by tests with sample outputs and a fake flatpak, not on real hardware.
- The "fresh user account gets the window once at first login" part is covered by the `--first-login` tests and the autostart entry, not by a real login yet. The boot test doesn't cover it until Spark Welcome is added there.
- English and Quebec French, picked from the PC's language (`LC_ALL`, `LC_MESSAGES` or `LANG`; `SPARK_LANG=en|fr` overrides it). It no longer reads `LANGUAGE`.
- Programs from Windows: only what Windows lists as installed; portable programs aren't found. The answers are a fixed list in `switch.py`.
- Files from Windows: OneDrive folders that only exist online aren't copied (they aren't on the disk). Windows accounts are copied one at a time. Storage Spaces and dynamic disks aren't detected.
- No progress for flatpak's download size before an install starts; the bar follows flatpak's own percentage.
