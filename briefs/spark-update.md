# Spark Update

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-update/`, `install.sh`, `--self-test`, tests, workflow). It ships in the image:
add `files/scripts/spark-update.sh` (the build step, like `spark-media.sh`), but don't edit
`recipes/recipe.yml` or `boot-test.yml`; the main SparkOS session wires it in at merge. Say in the
PR which recipe line and boot-test check you want.

## Why

SparkOS updates the whole system atomically (bootc/rpm-ostree images from
`ghcr.io/wolklaw/sparkos`), but what the user sees of it comes from Bazzite and Universal Blue
(`ujust`, their update service, their rollback helper, which even offers stock Bazzite images).
The owner wants SparkOS to rely on others as little as possible
([PLAN.md, Independence roadmap](../PLAN.md)). Spark Update is SparkOS's own updater, from the
approved mockup's notification: "SPARKOS UPDATED. The new version is ready. It starts the next
time you restart. Your apps are already up to date. [Later] [Restart]".

## What it does

1. **Background check (no window):** a systemd timer (system or user, whichever fits; justify it)
   that checks for a new SparkOS image every few hours and on a schedule that never interrupts
   a game: download and stage it (`bootc upgrade` or `rpm-ostree upgrade`), and update Flatpak apps
   (`flatpak update --noninteractive`, system and user). First find out what Bazzite runs today
   (`uupd`, `ublue-update`, `rpm-ostreed-automatic`, timers) and replace it with Spark Update's own,
   disabling theirs, so there's exactly one updater.
2. **Notification:** when an update is staged, a Plasma notification as in the mockup, with
   Restart and Later. Later reminds once a day at most, never while a game is fullscreen.
3. **Window** (from the menu or the notification): current version and date, the staged one if
   any, what changed (Soot and FreeSuite versions, which Spark apps changed, from image labels or
   files in the image; never invent a changelog), "Check now", "Restart to update", and
   **Roll back**: boot the previous version (`rpm-ostree rollback` through pkexec, then offer a
   restart), with a plain explanation that nothing is deleted.
4. **Settings:** automatic updates on or off, check frequency, "notify only" mode. Stored in
   `/etc/sparkos/update.conf` for system settings (written through pkexec) and `~/.config` for the
   user's notification preferences.

Must cost nothing while idle (timer, not a daemon), never restart on its own, and never block a
game. Every command it runs should be visible in its log (`~/.local/state/spark-update/`).

## Tests

Unit tests against fake `rpm-ostree status --json` / `bootc status --json` outputs (no update,
staged, failed, pinned), the notification throttle, the settings file. UI tests under Xvfb. In the
SparkOS image (CI): `--self-test` reads the real status and finds the image name
`ghcr.io/wolklaw/sparkos`. Real upgrades and rollbacks can't run in CI: say so in the PR.

## Done when

CI passes in Fedora and inside the SparkOS image, the build step exists, Bazzite's updater is
found and the plan to switch it off is in `files/scripts/spark-update.sh`, and a PR from
`spark-update` is open for the owner.
