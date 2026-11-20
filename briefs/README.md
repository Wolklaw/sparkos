# Briefs for new SparkOS apps

Each brief here describes one app the owner wants SparkOS to ship. Build one per session. Read this
file first, then the app's brief.

| Brief | App | Status |
|---|---|---|
| [spark-welcome.md](spark-welcome.md) | Spark Welcome: first-login setup | Not started |
| [spark-games.md](spark-games.md) | Spark Games: one library for every launcher | Owner has started notes; ask for them first |
| [spark-monitor.md](spark-monitor.md) | Spark Monitor: task manager (Ctrl+Shift+Esc) | Not started |

## What SparkOS is

A Bazzite-based image (Fedora 45, KDE Plasma 6, Python 3.15) built with BlueBuild from
[recipes/recipe.yml](../recipes/recipe.yml). The system is atomic: `/usr` is read-only on a running
machine, so apps go into the image at build time. Users install other software with Flatpak
(`flatpak install --user`), the Store (Bazaar) or by double-clicking a downloaded file
([sparkos-open-package](../files/system/usr/bin/sparkos-open-package)).

**App policy (owner's decision):** SparkOS preinstalls only the owner's own apps (Soot, FreeSuite,
Spark Snip, Spark Media, and these). No other company's or project's app ships in the image. An app
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
- `files/scripts/spark-<name>.sh`: the image build step. It runs `install.sh --deps` and fails the
  build if the app isn't installed. Add it to the recipe's script list after `spark-media.sh` and
  before `sparkos-defaults.sh`, and add the app's name to the policy comment at the top.
- `.github/workflows/spark-<name>.yml`: install and test in a `fedora:latest` container, UI tests
  under Xvfb. Copy [spark-media.yml](../.github/workflows/spark-media.yml).
- [boot-test.yml](../.github/workflows/boot-test.yml): add a "Check Spark <Name>" step that runs
  `spark-<name> --self-test` inside the real image. Put it outside the `FULL` condition at first;
  it can move into the weekly full run once it has passed a few times.
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
- Update [README.md](../README.md) and [PLAN.md](../PLAN.md) where they list SparkOS's apps, and mark
  the brief's status in the table above when the PR is open.
