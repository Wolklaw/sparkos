# Spark Run

SparkOS's own way to run Windows programs. Double-click an `.exe` or `.msi` and choose **Run once** or **Install as an app**. An installed app gets its own Windows folder (a Wine prefix), a menu entry with the program's own icon, and a place in Spark Run's window, where you can open it, open its `C:` folder, change its options or uninstall it.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

It runs on Wine, on purpose: Wine is one of the things SparkOS keeps ([PLAN.md](../../PLAN.md), Independence roadmap). Spark Run replaces fetching Bottles, another project's app, from Flathub. Games should still go through Steam, Heroic or Spark Games, which bring their own Proton; Spark Run is for ordinary Windows programs.

## Where Wine comes from

Nothing Wine-related is added to the image. Fedora's `wine` package would add about **2 GiB** to it (56 packages; `wine-core` alone is 1.5 GB, `wine-mono` 311 MB; measured in the SparkOS image on 2026-11-20). Bazzite, which SparkOS is built on, ships no Wine (it has `umu-run`, `winetricks`, `wrestool`, `cabextract` and `7z`, but no `wine`).

So the first time someone runs a Windows program, Spark Run downloads into `~/.local/share/spark-run/runtime/`:

| What | From | Download | Why this one |
|---|---|---|---|
| Wine 11.22, vanilla, `amd64-wow64` | [SparkOS's own build](https://github.com/Wolklaw/sparkos/releases/tag/wine-11.22-2), a release of this repository | 73 MB | WineHQ's own source with no patches, built by this repository's CI (see [How Wine is built](#how-wine-is-built)). The `wow64` build runs 32 and 64-bit Windows programs without any 32-bit Linux libraries. 11.22 is the development series Fedora itself ships (Fedora 45 has 11.21). |
| Wine Mono 11.3.0 | [dl.winehq.org](https://dl.winehq.org/wine/wine-mono/11.3.0/) (WineHQ) | 38 MB | Wine's own .NET Framework replacement; 11.3.0 is the version Wine 11.22 asks for. Unpacked once next to Wine and shared by every app. |
| DXVK 3.1.1, only if turned on for an app | [doitsujin/dxvk](https://github.com/doitsujin/dxvk/releases/tag/v3.1.1) | 17 MB | Direct3D 9-11 on Vulkan, for the few non-game programs that need it. |

**How each download is checked:** the SHA-256 of each file is written in [sparkrun/sources.py](sparkrun/sources.py), in this repository, along with its exact size. A file that doesn't match is deleted and never unpacked, whatever the server says. The pinned values were compared with the release's own `sha256sums.txt` and with GitHub's asset digest when they were written. Nothing is unpacked outside its own folder, and a half-unpacked Wine is never used (it is unpacked to a temporary folder and renamed when complete). The window says what will be downloaded, from where, and how big it is, before it starts.

Moving to a newer Wine takes two steps: build it (change `WINE_VERSION` and `WINE_SHA256` in [wine-build/build.sh](wine-build/build.sh) and let the workflow publish it), then one edit to `sources.py` (and `spark-app.json`, which the tests compare): URL, size, SHA-256 and folder, plus the Wine Mono version that Wine names in `dlls/appwiz.cpl/addons.c`. CI then runs the test programs on it. Older downloaded Wines are deleted when a new one is unpacked; existing apps keep working (Wine updates a prefix the first time it runs in it).

On disk, Wine with Wine Mono takes 836 MB, once. A Wine 11 prefix is 602 MB (its DLLs are copied in: system32 280 MB, syswow64 262 MB), so Spark Run makes one **template prefix** per Wine version with `wineboot` (about 15 s) and makes every new prefix as `cp --reflink=auto` of it (about 1 s). On btrfs, where SparkOS keeps `/home`, the copies share the template's disk space: CI measured 606 MB for the first app (template included), then 2 MB and 6 MB for the next two. On other filesystems each prefix is a full 602 MB copy. Disk use shown in the window counts shared space in full.

## How Wine is built

Spark Run's Wine is built here, not taken from someone else's build. [wine-build/build.sh](wine-build/build.sh), run by [.github/workflows/wine-build.yml](../../.github/workflows/wine-build.yml):

- downloads WineHQ's source tarball for the pinned version, checks it against Alexandre Julliard's WineHQ release signature (key `DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D`) and a SHA-256 written in the script, and applies no patches;
- builds in `registry.fedoraproject.org/fedora:45`, pinned by digest, with packages only from Fedora 45's release repository (frozen since release day; the container is first synced down to it), with `--enable-archs=i386,x86_64` (wow64), no OSS and no tests, and fails if configure leaves anything else out;
- installs the runtime only (`make install-lib`: no headers or compilers), strips the Linux libraries, and packs it with fixed timestamps (the source's own), owners and file order;
- runs the result from another folder, with no display, to prove it is relocatable: `wineboot`, then 64 and 32-bit `cmd.exe`;
- builds twice, in parallel, and publishes only if both archives are byte for byte the same. The release (tag `wine-<version>-<build>`) has the archive, `sha256sums.txt` and `build-info.txt` (configure options, the Linux libraries each module links to, every package in the build container). A later run that rebuilds an existing release checks it gets the published file exactly, and never replaces it.

Build 2 of Wine 11.22 took 28 to 39 minutes of `make` on GitHub's 4-core runners (32 to 44 minutes per job), and the archive is 77.0 MB (73 MiB), against 98.2 MB for Kron4ek's build of the same Wine, which Spark Run used before. It is smaller because it has no headers or development tools. It also links its media module (`winedmo`) to Fedora 45's FFmpeg, where Kron4ek's links to an older FFmpeg that Fedora no longer ships. Build 1 (`wine-11.22-1`) was missing `icu.dll` and `dmsynth.dll` (no C++ cross-compiler) and is not used.

## What it does

- **Run once** runs the file in one shared prefix (`~/.local/share/spark-run/run-once`), so a quick run doesn't wait for a new prefix after the first time. Nothing is added to the menu.
- **Install as an app** makes a new prefix (a copy of the template) in `~/.local/share/spark-run/prefixes/<name>`, runs the installer in it, and finds what it installed: first the Start Menu and desktop shortcuts it made (read from the `.lnk` files), then new `.exe` files. Uninstallers, updaters, setup and helper programs are never picked. If the installer added several programs, the window asks which one the menu entry opens (Options can change it later). A program that needs no installer (a "portable" `.exe`) is copied into the prefix's `C:\Program Files\<name>`, with the `.dll` files beside it. `.msi` packages go through Wine's `msiexec`.
- **The menu entry** (`~/.local/share/applications/dev.wolklaw.SparkRun.app-<name>.desktop`) has the program's own icon, read from the `.exe`'s resources (the largest size, saved as PNG), and opens files you drop on it or pick with Open with (as Windows paths, `Z:\home\...`).
- **The window** (`spark-run` with no file) lists installed Windows apps with their icon, Windows version, disk use and date: **Open**, **C: folder**, **Options**, **Uninstall**, and **Run a program…** to pick a file. Options: the name in the menu, which program to open, the Windows version the app sees (11, 10, 8.1, 8, 7, XP), DXVK on or off, and **Run an installer here…** for a runtime a program needs (the Visual C++ Redistributable, for example) inside that app's prefix.
- **Uninstall** ends the app's processes and deletes its prefix (everything it installed and saved inside it) and its menu entry. Files it saved in your own Documents, Downloads, Music, Pictures or Videos stay: Wine links those folders to yours. The Windows Desktop folder is *not* linked, so installers can't drop `.lnk` files on the Plasma desktop.
- **Plain errors.** When a program can't run, the window says why in one sentence, with a link to the [switching guide](../../docs/switching.md) and the log; never Wine's output or a stack trace. It recognises, before running: DOS and 16-bit programs, ARM programs, files that aren't Windows programs; and after: missing DLLs (with specific advice for the Visual C++ runtime and .NET), crashes, programs that close at once, a missing display, a failed download or a fingerprint mismatch. A menu entry starts the program without loading the window at all; the window appears only if something goes wrong.
- **CJK fonts.** Every prefix maps the Windows Chinese, Japanese and Korean font names (Microsoft YaHei, SimSun, Meiryo, MS Gothic, Malgun Gothic and others) to the system's Noto Sans CJK fonts (`HKCU\Software\Wine\Fonts\Replacements`, table in [sparkrun/wine.py](sparkrun/wine.py)). Without them, an embedded Chromium such as Amazon Music's crashed on its sign-in page. New prefixes get them when the template is made; older prefixes get them the next time the app starts (a marker file, `.spark-run-fonts`, makes that happen once).
- **Known-app fixes** ([sparkrun/fixes.py](sparkrun/fixes.py)) create small files an app needs, keyed on the installed program's path, after an install and before each start, without overwriting anything. The first: an empty `update.ini` beside `Amazon Music.exe`, without which it stops with "No update.ini file found". To fix another app, add a line to `FIXES`.
- **Sound rate.** Windows programs under Wine read the sound device's current sample rate, 48 kHz unless something else set it. SparkOS lets PipeWire follow the rate of native players (`/usr/share/pipewire/pipewire.conf.d/10-sparkos-sample-rates.conf`), but not of Wine. For Amazon Music Ultra HD above 48 kHz on a DAC, set a higher fixed rate in `~/.config/pipewire/pipewire.conf.d/50-sample-rates.conf` (`default.clock.rate` and `default.clock.allowed-rates` both set to that rate) and run `spark audio-restart`.

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
spark-run --get amazon-music                      # install a known app (pinned installer, checked by SHA-256) unless it is there
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

- **Opened on a real SparkOS desktop in CI, not used by hand yet.** The boot test opens its window from the app menu in a Plasma 6.8 session in a VM, in English and in French, keeps a screenshot and fails on a Python traceback. CI runs real Wine in a container, with Xvfb in Fedora and with no display in the SparkOS image, using console test programs and silent installers. Nobody has double-clicked a real installer with a wizard on Plasma 6.8 yet.
- **Wine itself is the limit.** Programs that need anti-cheat, kernel drivers, the Microsoft Store, .NET Framework features Wine Mono lacks, or newer DirectX than Wine and DXVK offer won't run. The switching guide lists the owner's programs and what to use instead.
- **The Wine build trusts GitHub and Fedora.** Wine is built by GitHub's runners from Fedora 45's compilers and libraries; the build is reproducible, so anyone can rebuild it and compare the SHA-256, but nobody outside this repository has done so yet. Wine Mono comes from WineHQ and DXVK from the DXVK project's own releases, as before.
- **No CAPI (ISDN)**: Fedora has no `capi4linux`, so `capi2032.dll` isn't built. Nothing a desktop needs.
- **One Wine for everything.** Apps can't choose an older Wine; after a Wine update, a program that regressed can't be kept on the old one.
- **No Wine Gecko**, so in-program HTML views stay blank.
- **Run once shares one prefix** across everything run that way; what one program saves there, the next sees. Install as an app to keep a program apart.
- The `.msi` name shown before installing is the file name: Spark Run doesn't read the `.msi` database.
