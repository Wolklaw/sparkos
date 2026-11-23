# Spark Settings

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-settings/`, `install.sh`, `spark-app.json`, `--self-test`, tests, workflow).
This one goes **in the image** (owner's decision, 2026-11-22): add `files/scripts/spark-settings.sh`
like `spark-files.sh`, but don't edit the Containerfile, `boot-test.yml` or `sparkos-defaults.sh`;
say in the PR what the main session must wire in. Branch `spark-settings`.

## Why

KDE's System Settings is the last big piece of the desktop that's plainly someone else's app. The
owner wants it replaced like Dolphin, Konsole and Kickoff were ([PLAN.md](../PLAN.md), "Independence
roadmap"). KDE's settings modules (KCMs) stay as the engine for what Spark Settings doesn't cover
yet, the way Wine stays under Spark Run: nothing the owner can set today may get lost.

## What it does

One window: a sidebar of pages and search across every setting (typing "refresh" finds the display
page's refresh rate). Each page changes things through the system's own tools, applies at once
where it's safe, and offers to revert anything that can lock you out of the screen.

**Pages, first version** (each through the tool in brackets; check each is in the image):
- **Displays** (`kscreen-doctor`): the owner's three monitors drawn as boxes to arrange, and for each
  one resolution, refresh rate, scale, rotation, VRR, HDR, primary. Changes that could blank a
  screen revert after 15 s unless kept.
- **Sound** (`wpctl`/PipeWire): output and input device, volume, per-app volume, a test tone. The
  owner's FiiO DAC and QuadCast must show by their names.
- **Network** (`nmcli`): Wi-Fi list and connect, wired status, VPN connections (WireGuard, OpenVPN
  import), proxy.
- **Bluetooth** (BlueZ over D-Bus or `bluetoothctl`): on/off, pair, connect, forget, battery.
- **Appearance:** SparkOS accent colour (mint by default), wallpaper, cursor size, font size. Only
  SparkOS's own look; no theme browser.
- **Mouse, keyboard and controllers:** pointer speed and acceleration, scroll direction, keyboard
  layouts (with the US-international dead keys), repeat rate, the Caps Lock fix
  (`sparkos-capslock`), shortcuts for the Spark apps.
- **Power:** power profile (`powerprofilesctl`), screen off and sleep timers, what the power button
  does.
- **Default apps** (`xdg-mime`): browser, mail, files, terminal, text, media, archives.
- **Startup:** apps that open at sign-in, on/off (including the startup sound).
- **Users:** your name, picture and password; add a user (through `accountsservice`/polkit).
- **Date, time and language** (`timedatectl`, `localectl`): time zone (Eastern by default for the
  owner), 24-hour clock, language and formats (English and French).
- **Printers** (CUPS, `lpadmin`): the printers found on the network, add one, print a test page. The
  owner's Canon TR4700 is the check.
- **Storage and games drive:** the games drive setting, mounted drives, a link to Spark Space if
  installed.
- **Updates:** opens Spark Update.
- **About:** SparkOS version and image, hardware, a "Copy system info" button for bug reports.

**More settings.** Every KCM Spark Settings doesn't cover yet, listed by name under one page and
opened with `kcmshell6 <module>` in its own window. Search covers them too. Each release moves more
of them into Spark pages; the PR lists what's left.

## Replacing System Settings

- Spark Settings takes System Settings' place in the launcher, the dock's pinned apps if it's there,
  Spark Welcome's last tip (`files/spark-welcome/sparkwelcome/core.py`), and launcher search
  (`files/spark-launcher`, which uses the `krunner_systemsettings` runner today).
- Plasma opens settings from many places (tray icons' "Configure...", right-click on the desktop >
  Configure Display Settings, notifications, the volume and network applets). Find how each one
  starts System Settings (the `systemsettings` command, `kcmshell6`, or `.desktop` files through
  KIO) and route the pages Spark Settings owns to it, for example `spark-settings --page displays`.
  The rest keep opening KDE's module. Say in the PR which entry points were checked and how.
- System Settings stays installed but hidden (`NoDisplay=true`) for one release, then goes, like
  Dolphin and Konsole. `spark-settings --kde` opens it while it's there.

## Both bases

It must work natively on both images: `ghcr.io/wolklaw/sparkos` (Bazzite) and `ghcr.io/wolklaw/sparkos-fedora`
(plain Fedora Kinoite, the same Containerfile with `SPARKOS_BASE=fedora`; see
[docs/fedora-base.md](../docs/fedora-base.md)). Check each tool a page uses is in both; where one is
missing on a base, add it in `build_files/packages.sh` for that base (say what it adds) or have the
page say plainly what's missing. CI runs `--self-test` inside both images.

## Speed

Opens in under a second. Each page reads its state when you open it, not at start. Nothing polls:
watch D-Bus signals (NetworkManager, BlueZ, PipeWire via `pw-mon` or `wpctl` subscribe) only while
the page is on screen.

## Tests

- Each page against fake tools (scripts in `tests/fixtures/` that print saved output of
  `kscreen-doctor -j`, `wpctl status`, `nmcli -t`, `bluetoothctl`, `lpstat`) and checks the command
  each change would run. Never change the CI machine's real settings.
- Display revert timer, search, French strings, under Xvfb.
- Inside `ghcr.io/wolklaw/sparkos:latest`: `--self-test` reports which tools are present.
- Not testable in CI: real monitors, Bluetooth, printers. The owner checks them on their PC; list
  them as "not tried yet" in the README until then.

## Done when

CI passes, the build step exists, every page above works against its fixtures, More settings lists
the remaining KCMs, and the PR from `spark-settings` is open with the entry-point routing explained.
