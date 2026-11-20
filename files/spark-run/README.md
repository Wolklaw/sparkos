# Spark Run

SparkOS's own way to run Windows programs. Double-click an `.exe` or `.msi` and choose **Run once** or **Install as an app**. An installed app gets its own Windows folder (a Wine prefix), a menu entry with the program's own icon, and a place in Spark Run's window, where you can open it, open its `C:` folder, change its options or uninstall it.

It runs on Wine, on purpose: Wine is one of the things SparkOS keeps ([PLAN.md](../../PLAN.md), Independence roadmap). Spark Run replaces fetching Bottles, another project's app, from Flathub. Games should still go through Steam, Heroic or Spark Games, which bring their own Proton; Spark Run is for ordinary Windows programs.

## Where Wine comes from

Nothing Wine-related is added to the image. Fedora's `wine` package would add about **2 GiB** to it (56 packages; `wine-core` alone is 1.5 GB, `wine-mono` 311 MB; measured in the SparkOS image on 2026-11-20). Bazzite, which SparkOS is built on, ships no Wine (it has `umu-run`, `winetricks`, `wrestool`, `cabextract` and `7z`, but no `wine`).

So the first time someone runs a Windows program, Spark Run downloads into `~/.local/share/spark-run/runtime/`:

| What | From | Download | Why this one |
|---|---|---|---|
| Wine 11.22, vanilla, `amd64-wow64` | [Kron4ek/Wine-Builds](https://github.com/Kron4ek/Wine-Builds/releases/tag/11.22) on GitHub | 94 MB | WineHQ's own source with no extra patches, built on GitHub Actions. The `wow64` build runs 32 and 64-bit Windows programs without any 32-bit Linux libraries. 11.22 is the development series Fedora itself ships (Fedora 45 has 11.21). |
| Wine Mono 11.3.0 | [dl.winehq.org](https://dl.winehq.org/wine/wine-mono/11.3.0/) (WineHQ) | 38 MB | Wine's own .NET Framework replacement; 11.3.0 is the version Wine 11.22 asks for. Unpacked once next to Wine and shared by every app. |
| DXVK 3.1.1, only if turned on for an app | [doitsujin/dxvk](https://github.com/doitsujin/dxvk/releases/tag/v3.1.1) | 17 MB | Direct3D 9-11 on Vulkan, for the few non-game programs that need it. |

**How each download is checked:** the SHA-256 of each file is written in [sparkrun/sources.py](sparkrun/sources.py), in this repository, along with its exact size. A file that doesn't match is deleted and never unpacked, whatever the server says. The pinned values were compared with the release's own `sha256sums.txt` and with GitHub's asset digest when they were written. Nothing is unpacked outside its own folder, and a half-unpacked Wine is never used (it is unpacked to a temporary folder and renamed when complete). The window says what will be downloaded, from where, and how big it is, before it starts.

Moving to a newer Wine is one edit to `sources.py` (and `spark-app.json`, which the tests compare): URL, size and SHA-256, plus the Wine Mono version that Wine names in `dlls/appwiz.cpl/addons.c`. CI then runs the test programs on it. Older downloaded Wines are deleted when a new one is unpacked; existing apps keep working (Wine updates a prefix the first time it runs in it).

On disk, Wine with Wine Mono takes about 1 GB once; each installed app's prefix starts at about 200 MB plus the program.

## What it does

- **Run once** runs the file in one shared prefix (`~/.local/share/spark-run/run-once`), so a quick run doesn't wait for a new prefix after the first time. Nothing is added to the menu.
- **Install as an app** makes a new prefix in `~/.local/share/spark-run/prefixes/<name>`, runs the installer in it, and finds what it installed: first the Start Menu and desktop shortcuts it made (read from the `.lnk` files), then new `.exe` files. Uninstallers, updaters, setup and helper programs are never picked. If the installer added several programs, the window asks which one the menu entry opens (Options can change it later). A program that needs no installer (a "portable" `.exe`) is copied into the prefix's `C:\Program Files\<name>`, with the `.dll` files beside it. `.msi` packages go through Wine's `msiexec`.
- **The menu entry** (`~/.local/share/applications/dev.wolklaw.SparkRun.app-<name>.desktop`) has the program's own icon, read from the `.exe`'s resources (the largest size, saved as PNG), and opens files you drop on it or pick with Open with (as Windows paths, `Z:\home\...`).
- **The window** (`spark-run` with no file) lists installed Windows apps with their icon, Windows version, disk use and date: **Open**, **C: folder**, **Options**, **Uninstall**, and **Run a program…** to pick a file. Options: the name in the menu, which program to open, the Windows version the app sees (11, 10, 8.1, 8, 7, XP), DXVK on or off, and **Run an installer here…** for a runtime a program needs (the Visual C++ Redistributable, for example) inside that app's prefix.
- **Uninstall** ends the app's processes and deletes its prefix (everything it installed and saved inside it) and its menu entry. Files it saved in your own Documents, Downloads, Music, Pictures or Videos stay: Wine links those folders to yours. The Windows Desktop folder is *not* linked, so installers can't drop `.lnk` files on the Plasma desktop.
- **Plain errors.** When a program can't run, the window says why in one sentence, with a link to the [switching guide](../../docs/switching.md) and the log; never Wine's output or a stack trace. It recognises, before running: DOS and 16-bit programs, ARM programs, files that aren't Windows programs; and after: missing DLLs (with specific advice for the Visual C++ runtime and .NET), crashes, programs that close at once, a missing display, a failed download or a fingerprint mismatch. A menu entry starts the program without loading the window at all; the window appears only if something goes wrong.

Wine's own menu-entry maker (`winemenubuilder`) is off, so Wine never adds entries of its own; the Wine Gecko (HTML engine) prompt is off too. Programs that need Gecko to show an HTML page will show a blank area there.

## Install, run, test

```
bash install.sh --user                          # just you, into ~/.local; no root
bash install.sh --user --uninstall              # removes exactly what --user installed
bash install.sh --user --uninstall --purge      # also Wine, every Windows app and their menu entries
sudo bash install.sh --deps                     # system-wide (what the image build step runs)

spark-run                                       # the window: installed Windows apps
spark-run setup.exe                             # Run once / Install as an app (what a double-click does)
spark-run --run-once prog.exe [args] [--wait]   # no window unless it fails
spark-run --install setup.exe [--name N] [--silent] [--portable|--installer]
spark-run --open APP [files]                    # what a menu entry runs
spark-run --list [--json]
spark-run --set APP [--windows win7] [--dxvk on|off] [--name N]
spark-run --in APP vc_redist.x64.exe            # run another installer inside an app's prefix
spark-run --folder APP | --uninstall APP | --setup | --self-test | --version
```

`--silent` asks the installer to skip its wizard (`/qn` for `.msi`, `/S` for NSIS, `/VERYSILENT` for Inno Setup, `/quiet` for WiX bundles). `--no-window` puts problems on stderr instead of in a window. `--self-test` needs no display or network: it lists the pinned downloads, whether Wine is there (and runs `wine --version` if so), and which of the Linux libraries Wine loads are missing.

`--user` needs only what the SparkOS image already has (Python 3 with tkinter; Pillow for PNG icons). Settings would go in `~/.config/spark-run/`; the log is in `~/.local/state/spark-run/` (Spark Run's own and one per app, with Wine's output).

```
python3 -m unittest discover -s tests -v        # no Wine, display or network needed
python3 make_icons.py                           # redraw icons/ after changing the mark
```

The unit tests forge Windows files byte by byte (a PE with an icon and a version resource, a DOS program, `.lnk` shortcuts: `tests/forge.py`) and act out Wine with a script (`tests/fakewine.py`), so the whole install flow, the menu entries, the options, the errors and the window run without Wine. CI ([workflow](../../.github/workflows/spark-run.yml)) does the real thing: it builds Spark Hello (a tiny C program, 64 and 32-bit, with an icon and a version resource), an NSIS installer and an `.msi` for it, and a program that needs a DLL nobody has, with mingw-w64, NSIS and wixl. Then, in Fedora and inside the published SparkOS image as a normal user without root, `tests/ci_wine.sh` downloads the pinned Wine and Wine Mono, runs both programs once, checks the missing-DLL error is one plain sentence, installs the NSIS installer and checks the menu entry and the 256 px icon read from the `.exe`, opens it with a file, switches it to Windows 7 (and checks the program sees 6.1), turns DXVK on, installs the `.msi` silently and the program on its own, lists, and uninstalls everything.

`spark-app.json` describes the app for the Spark Portal, including what it downloads on first use.

## Hooking it in (for the main SparkOS session)

Spark Run doesn't change `sparkos-open-package`, the recipe or the boot test. To make double-clicking an `.exe` or `.msi` use it, in [sparkos-open-package](../system/usr/bin/sparkos-open-package):

```bash
  *.exe|*.msi)
    exec spark-run "$file"
    ;;
```

(with `with_helper com.usebottles.bottles ...` removed). The recipe line, after the other Spark apps: `- spark-run.sh # Spark Run: Windows programs on Wine`. The boot test can run `spark-run --self-test` (ends with `self-test passed`) and, with network, `tests/ci_wine.sh` as the test user.

## Known gaps

- **Not tried on a SparkOS desktop yet.** CI runs real Wine in a container, with Xvfb in Fedora and with no display in the SparkOS image, using console test programs and silent installers. Nobody has double-clicked a real installer with a wizard on Plasma 6.8 yet.
- **Wine itself is the limit.** Programs that need anti-cheat, kernel drivers, the Microsoft Store, .NET Framework features Wine Mono lacks, or newer DirectX than Wine and DXVK offer won't run. The switching guide lists the owner's programs and what to use instead.
- **Builds from one person.** The Wine build comes from Kron4ek's GitHub, built from WineHQ's source on GitHub Actions. The pinned SHA-256 protects against the file changing later, not against a bad build at the time it was pinned. Building Wine from WineHQ's source in this repository's own CI and publishing it as a SparkOS release would remove that tie; it's a bigger job (about an hour of CI per Wine release) and isn't done.
- **One Wine for everything.** Apps can't choose an older Wine; after a Wine update, a program that regressed can't be kept on the old one.
- **No Wine Gecko**, so in-program HTML views stay blank.
- **Run once shares one prefix** across everything run that way; what one program saves there, the next sees. Install as an app to keep a program apart.
- The `.msi` name shown before installing is the file name: Spark Run doesn't read the `.msi` database.
