# Spark Update

SparkOS's own updater: the "SparkOS updated" notification, a window with what changed, Check
now, Restart and Roll back, and (when switched on) its own background downloads, replacing
Universal Blue's `uupd`. There is always exactly one updater, and never none.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

## Who downloads updates (the engine)

| Engine | Downloads and stages images | Spark Update does |
|---|---|---|
| `uupd` (the first release only; SparkOS has used `spark` and removed uupd since 2026-11-20) | Universal Blue's `uupd.timer`, daily at 04:00, as Bazzite ships it (image, Flatpak apps, brew) | the notification, the window, Check now (starts `uupd-manual.service`, the same as `ujust update`), Restart, Roll back |
| `spark` (**SparkOS today**) | `spark-update.timer` (below). Where uupd is installed, `uupd.timer` is off and its units run Spark Update; SparkOS removes the uupd package, and `ujust update` runs Spark Update's Check now | everything |

The image build picks it with `SPARK_UPDATE_ENGINE` (`files/scripts/spark-update.sh`); the
switch to `spark` waits until Spark Update's own staging has worked on a booted SparkOS. The
app reads which timer is enabled, so the window always shows what the PC really does. The
self-test fails the image build if no updater, or two, are on.

## With the spark engine

- **In the background:** a systemd timer, not a daemon. Every few hours (6 by default) it
  downloads the new SparkOS image and gets it ready for the next restart (`bootc upgrade`, or
  `rpm-ostree upgrade` when packages are layered), and updates Flatpak apps (system and yours).
  It waits for a later hour while a game runs (Steam, Proton/Wine, gamescope), on a metered
  connection or on a battery under 20%. It runs at the lowest CPU and disk priority. It
  **never restarts the PC on its own.**
- **Settings** (below) apply to this timer; under uupd, uupd keeps its own daily schedule.

## With either engine

- **The notification**, when a new version is ready: "SparkOS updated. The new version is
  ready. It starts the next time you restart. Your apps are already up to date." with
  **Later** and **Restart**. The apps sentence shows only when the last Flatpak updates
  really finished. Later brings it back after a day at the soonest (or 3 days, or a week, in
  Settings), never while a game runs. Restart asks Plasma to close your apps first.
- **The window** (menu: Spark Update): the version running now and the one the next restart
  starts, what changed between them, Check now, Restart to update, Roll back, Settings, Log.

## What changed

Nothing is invented. Each SparkOS image carries `/usr/share/sparkos/release.json` (written by
the image build): the versions of Soot, FreeSuite, every Spark app, the Bazzite base, the Linux
kernel, Mesa, KDE Plasma and Flatpak. The window compares the file of the running version with
the one of the staged version (or, with no update waiting, with the previous version). For a
version built before that file existed, it reads the same things from that version's files on
disk (`/ostree/deploy/...`). If neither can be read, it says so.

## Roll back

Roll back makes the next restart start the previous version (`rpm-ostree rollback`, through
pkexec, which asks for an administrator password). Nothing is deleted: files, settings and apps
stay, and the current version stays on disk, so Cancel roll back undoes it. A staged update is
dropped first so the restart really goes back. Automatic updates then skip the version you
rolled back from (it's recorded as `held` in `/var/lib/spark-update/state.json`) and stage the
next newer one when there is one (in notify mode they don't report it as available, and tell
you about the next newer one). Check now, or booting that version again, ends the hold: Check
now gets whatever is newest. The window says which version is held back. Turn automatic
updates off in Settings to stay on the old one.

## Settings

| Where | What |
|---|---|
| `/etc/sparkos/update.conf` (everyone; the window writes it through pkexec) | `automatic` yes/no, `mode` stage/notify (notify: check and tell, download nothing), `check_every_hours` 3/6/12/24, `flatpak` yes/no |
| `~/.config/spark-update/settings.json` (you) | notification on/off, remind after Later: 1, 3 or 7 days |

## Files

| Path | What |
|---|---|
| `spark_update.py`, `sparkupdate/` | the app: `cli.py`, `updater.py` (the runs), `status.py` (rpm-ostree/bootc status), `release.py` (what's in a version), `notify.py`, `guard.py` (games, metered, battery), `settings.py`, `app.py` (window), `widgets.py` (copied from Spark Media), `text.py` (every sentence) |
| `systemd/spark-update.timer` + `.service` | root, hourly look; a check when due (default every 6 h). Root because staging an image needs it and it should happen with nobody logged in |
| `systemd/spark-update-now@.service` | Check now from the window (`@check` or `@stage`); active local users may start it without a password (`polkit/50-spark-update.rules`) |
| `systemd/spark-update-user.timer` + `.service` | every user, hourly: their own Flatpak apps and the notification |
| `spark-update-helper` | `/usr/libexec/spark-update-helper`, run through pkexec (`polkit/dev.wolklaw.SparkUpdate.policy`): `rollback`, `set key=value...`, `check`/`stage` |
| State and logs | `/var/lib/spark-update/state.json` and `/var/log/spark-update/spark-update.log` (background runs, readable by everyone), `~/.local/state/spark-update/` (yours). Every command run is in the log; the window's Log button shows both |

## Install

```bash
sudo bash install.sh --deps [--engine uupd|spark]   # system-wide: what the image build does
bash install.sh --user             # just you, no root: the window, the notification, your Flatpak apps
bash install.sh --user --uninstall
```

Background downloads of SparkOS itself need the system install (root), which ships in the
image. In the image build, `files/scripts/spark-update.sh` installs it, switches off Bazzite's
updater, writes `release.json` and fails the build if the self-test finds another updater on.

## Commands

```bash
spark-update                  # the window
spark-update --status         # versions: running, next restart, previous
spark-update --rollback       # same as the window's Roll back
spark-update --notify-test    # show the real notification with a made-up version (doesn't restart)
spark-update --self-test      # what it needs and finds; no display needed
```

## Tests

```bash
python -m unittest discover -s files/spark-update/tests -v
```

Fake `rpm-ostree status --json` and `bootc status --json` outputs (no update, staged, pinned,
rolled back, layered packages, a container), a fake root folder for the runs, and a fake
command runner, so nothing real is upgraded, rolled back or restarted. UI tests need a display
(CI: Xvfb). CI also runs the image build step and a per-user install inside the published
SparkOS image. Real upgrades, rollbacks and restarts can only be tried on a booted SparkOS PC.

Icons are drawn by `make_icons.py` (`python files/spark-update/make_icons.py`).
