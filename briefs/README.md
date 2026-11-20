# Briefs for new SparkOS apps

Each brief here describes one optional Spark app. Build one per session. Read this file first, then
the app's brief.

**None of these ships in the first SparkOS build.** The first build preinstalls only Soot, FreeSuite,
Spark Snip and Spark Media. The apps below are optional: the goal is one **Spark Portal** where every
optional Spark app is listed and can be installed or removed with a click. Until the Portal exists,
build each app so it installs on its own (see "Optional apps install on their own" below), and do not
add it to the recipe or the image.

| Brief | App | Status |
|---|---|---|
| [spark-welcome.md](spark-welcome.md) | Spark Welcome: first-login setup | Built: [files/spark-welcome](../files/spark-welcome), PR open on branch `spark-welcome` |
| [spark-games.md](spark-games.md) | Spark Games: one library for every launcher | Owner has started notes; ask for them first |
| [spark-monitor.md](spark-monitor.md) | Spark Monitor: task manager (Ctrl+Shift+Esc) | Not started |
| (no brief yet) | Spark Portal: the hub that lists, installs, updates and removes optional Spark apps | Idea; the owner decides the format first |

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
