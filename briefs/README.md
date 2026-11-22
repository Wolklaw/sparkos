# Briefs for new SparkOS apps

Each brief here describes one optional Spark app. Build one per session. Read this file first, then
the app's brief.

**Update (owner's decision, 2026-11-20): Spark Welcome, Spark Games and Spark Monitor ship in the
first SparkOS build.** Each app also adds `files/scripts/spark-<name>.sh` (the image build step, like
`spark-media.sh`), but does not edit `recipes/recipe.yml` or `boot-test.yml`: the main SparkOS session
wires all three in when it merges the PRs, so three PRs don't fight over the same files. Keep the
per-user install mode below too: later Spark apps will be optional, through one **Spark Portal** where
every optional Spark app is listed and can be installed or removed with a click.

| Brief | App | Status |
|---|---|---|
| [spark-welcome.md](spark-welcome.md) | Spark Welcome: first-login setup | Merged ([#4](https://github.com/Wolklaw/sparkos/pull/4)), in [files/spark-welcome](../files/spark-welcome); ships in the first build |
| [spark-games.md](spark-games.md) | Spark Games: one library for every launcher | Merged ([#3](https://github.com/Wolklaw/sparkos/pull/3)), in [files/spark-games](../files/spark-games); ships in the first build |
| [spark-monitor.md](spark-monitor.md) | Spark Monitor: task manager (Ctrl+Shift+Esc) | Merged ([#5](https://github.com/Wolklaw/sparkos/pull/5)), in [files/spark-monitor](../files/spark-monitor); ships in the first build. Ctrl+Shift+Esc not yet tried on hardware |
| [spark-store.md](spark-store.md) | Spark Store: SparkOS's own store over Flathub, with the Spark apps in it (replaces Bazaar; the Spark Portal idea) | In the first release next to Bazaar ([#10](https://github.com/Wolklaw/sparkos/pull/10)), in [files/spark-store](../files/spark-store); not the default store yet (Bazaar keeps .flatpakref links until it's tried on a desktop) |
| [spark-update.md](spark-update.md) | Spark Update: SparkOS's own updater, notification and rollback | In the first release ([#7](https://github.com/Wolklaw/sparkos/pull/7)), in [files/spark-update](../files/spark-update). Bazzite's uupd keeps downloading updates until Spark Update's own engine is proven on a booted SparkOS (`SPARK_UPDATE_ENGINE=spark`) |
| [spark-snip-capture.md](spark-snip-capture.md) | Spark Snip captures without Spectacle | Merged ([#6](https://github.com/Wolklaw/sparkos/pull/6)): captures through KWin, Spectacle kept as a fallback until the boot test's real-session capture passes |
| [release2-cleanup.md](release2-cleanup.md) | Image cleanup: font in the repo, Plasma System Monitor and Tailscale out, own AppImage handling, no calling home | Merged ([#13](https://github.com/Wolklaw/sparkos/pull/13)). The connectivity check is the owner's call (see the PR) |
| [spark-edit.md](spark-edit.md) | Spark Edit: light text and code editor | In the first release ([#12](https://github.com/Wolklaw/sparkos/pull/12)), in [files/spark-edit](../files/spark-edit); default for text and code files |
| [spark-calc.md](spark-calc.md) | Spark Calc: standard, scientific and programmer calculator | In the first release ([#8](https://github.com/Wolklaw/sparkos/pull/8)), in [files/spark-calc](../files/spark-calc) |
| [spark-archive.md](spark-archive.md) | Spark Archive: zip, 7z, tar and more, Extract/Compress in Dolphin (replaces Ark) | In the first release ([#14](https://github.com/Wolklaw/sparkos/pull/14)), in [files/spark-archive](../files/spark-archive); default for archives. Ark stays installed until Dolphin's menu is tried on hardware |
| [spark-scan.md](spark-scan.md) | Spark Scan: scanning with preview, crop, multi-page PDF and OCR | In the first release ([#9](https://github.com/Wolklaw/sparkos/pull/9)), in [files/spark-scan](../files/spark-scan); tested with SANE's test scanner, not yet with the Canon |
| [spark-run.md](spark-run.md) | Spark Run: Windows programs on Wine (replaces Bottles) | In the first release ([#17](https://github.com/Wolklaw/sparkos/pull/17)), in [files/spark-run](../files/spark-run); double-clicking .exe/.msi opens it. Wine is downloaded on first use |
| [sparkos-on-fedora.md](sparkos-on-fedora.md) | Prototype: SparkOS built on plain Fedora instead of Bazzite (separate test image) | Merged ([#16](https://github.com/Wolklaw/sparkos/pull/16)) as a separate image, `sparkos-fedora`; results in [docs/fedora-base.md](../docs/fedora-base.md). Moving the real base is a later decision |
| [spark-link.md](spark-link.md) | Spark Link: phone and PC linked with no outside service (PC side; phone side in Soot's Android app; protocol in [docs](../docs/spark-link-protocol.md)) | In the first release ([#11](https://github.com/Wolklaw/sparkos/pull/11)), in [files/spark-link](../files/spark-link); protocol draft 2 agreed with the phone side ([Soot#3](https://github.com/Wolklaw/Soot/pull/3)). KDE Connect stays. Not yet tried with a real phone |
| [spark-connect.md](spark-connect.md) | Spark Connect (working name), first part: see and fix the owner's home Linux servers over SSH, on SparkOS and Windows. Later parts add the venue laptop and the GestionDirecte tablets ([PLAN.md](../PLAN.md), "Remote care") | Merged ([#11](https://github.com/Wolklaw/sparkos/pull/11)), optional app, in [files/spark-connect](../files/spark-connect). Not yet connected to the owner's real machines |
| [spark-files.md](spark-files.md) | Spark Files: SparkOS's own file manager (replaces Dolphin) | Brief written 2026-11-22, not started |
| [spark-terminal.md](spark-terminal.md) | Spark Terminal: SparkOS's own terminal on the VTE library (replaces Konsole) | Built 2026-11-22, PR open, in [files/spark-terminal](../files/spark-terminal); in the image, the default terminal, Konsole hidden. Not yet tried on a booted SparkOS |
| [spark-launcher.md](spark-launcher.md) | Spark Launcher: SparkOS's own app menu and dock button (replaces Kickoff) | Brief written 2026-11-22, not started |
| [sparkos-icons.md](sparkos-icons.md) | SparkOS's own icon theme over Breeze Dark, in four batches (taskbar, folders, file types, tray), one session and PR each | Brief written 2026-11-22, not started |
| [build-without-bluebuild.md](build-without-bluebuild.md) | SparkOS built from its own Containerfile, side by side with the BlueBuild build | Merged ([#15](https://github.com/Wolklaw/sparkos/pull/15)); the real build uses the Containerfile since 2026-11-20 ([docs/building.md](../docs/building.md)) |

## Optional apps install on their own

SparkOS is atomic: `/usr` is read-only on a running machine, so an optional app can't install there
the way the image build does. Each optional app must install for one user with no root:

- `install.sh --user` installs to `~/.local/lib/spark-<name>/`, `~/.local/bin/spark-<name>`,
  `~/.local/share/applications/` and `~/.local/share/icons/`, and `install.sh --user --uninstall`
  removes exactly what it installed. Missing system packages can't be added with `dnf` on SparkOS, so
  the app must run on what the SparkOS image already has (Python 3, Tk, Pillow, GStreamer, GObject),
  or bundle pure-Python dependencies in its own folder. `--self-test` reports anything missing.
- Keep the system-wide mode (`install.sh --deps`, root) too, so the owner can still decide to move an
  app into the image later.
- A machine-readable `spark-app.json` in the app folder (id, name, one-line description, version,
  size, what it needs) so the Portal can list it without running it.
- How the Portal will fetch apps (GitHub release tarballs checked against SHA256SUMS like FreeSuite, or
  the owner's own Flatpak repository) is not decided. Don't build either yet; just keep the app
  self-contained in its folder so both are possible.

## What SparkOS is

A Bazzite-based image (Fedora 45, KDE Plasma 6, Python 3.15) built with BlueBuild from
[recipes/recipe.yml](../recipes/recipe.yml). The system is atomic: `/usr` is read-only on a running
machine, so apps go into the image at build time. Users install other software with Flatpak
(`flatpak install --user`), the Store (Bazaar) or by double-clicking a downloaded file
([sparkos-open-package](../files/system/usr/bin/sparkos-open-package)).

**App policy (owner's decision):** SparkOS preinstalls only the owner's own apps (Soot, FreeSuite,
Spark Snip, Spark Media); more Spark apps are optional, through the future Spark Portal. No other company's or project's app ships in the image. An app
may *offer* to install a third-party app (Steam, Discord...), but only from Flathub, only when the
user clicks, and it must say plainly whose app it is.

**Speed rule:** the owner does not want SparkOS to feel sluggish. Each app should open in well under a
second, use near-zero CPU when idle, and never block its window while it works.

## Follow the existing Spark apps

[Spark Media](../files/spark-media) and [Spark Snip](../files/spark-snip) are the pattern. Copy their
shape:

- `files/spark-<name>/`: `spark_<name>.py` (entry point), a `spark<name>/` package (`__init__.py`
  with `APP_ID`, `APP_NAME`, `VERSION`; `app.py`, `core.py`, `widgets.py`...), `install.sh`
  (`--deps`, `--prefix /usr/lib/spark-<name>`, `--no-test`), `make_icons.py`, `icons/`,
  `dev.wolklaw.Spark<Name>.desktop`, `tests/` (unittest), `README.md`.
- **Not** `files/scripts/spark-<name>.sh`, the recipe, or the boot test: optional apps stay out of the
  image. (Spark Media's `files/scripts/spark-media.sh` shows what that would look like if the owner
  later moves one in.)
- `.github/workflows/spark-<name>.yml`: install and test in a `fedora:latest` container, UI tests
  under Xvfb. Copy [spark-media.yml](../.github/workflows/spark-media.yml). Add a second job that
  pulls `ghcr.io/wolklaw/sparkos:latest`, runs `install.sh --user` as a normal user inside it,
  then `--self-test`, then `--uninstall`, to prove the app works on real SparkOS without root.
- App ID `dev.wolklaw.Spark<Name>`, command `/usr/bin/spark-<name>`, settings in
  `~/.config/spark-<name>/`, log in `~/.local/state/spark-<name>/`, cache in `~/.cache/spark-<name>/`.
- Every app has `--version` and `--self-test` (no display needed; checks what it depends on).

## Look

The owner's house style is the `wolklaw-design` skill (load it): the desktop/tool-app variant, BotWatch
palette, mono type, uppercase micro-labels, sharp 3px corners, and the magenta/cyan channel slip as
the only decoration (on headings, on events, on errors). Copy `widgets.py` from Spark Media (`T`,
`Glitch`, `GlitchText`, `IconButton`, `Mark`, `Strip`, `pick_mono`) rather than writing new widgets,
so the apps look like one family. Icons are drawn by `make_icons.py`, never copied art.

Copy: plain verbs, not corny, honest about what works and what doesn't. Write user-facing strings in
one place so a French translation can be added (the owner is in Quebec).

## Working in this repo

- Other sessions work in this folder at the same time. **Stage explicit paths only; never
  `git add -A` or `git add .`**.
- Work on a branch (`spark-<name>`) and open a pull request for the owner to merge. Don't push to
  `main`.
- Never commit `cosign.key`.
- Times for the owner are in Eastern (Quebec), not UTC.
- Don't list the app as part of SparkOS in [README.md](../README.md) or [PLAN.md](../PLAN.md); it's
  optional. Mark the brief's status in the table above when the PR is open.
