# Spark Launcher

Read [README.md](README.md) first, and load the `wolklaw-design` skill for the look.

## Why

The app launcher button (the first icon on the dock) opens Plasma's Kickoff menu with Bazzite's icon. It's
the thing the owner clicks most, and it isn't SparkOS's.

## What it does

- The SparkOS button on the dock (its own icon) and the Meta key open the launcher.
- Type to search at once: apps, settings pages, recent files, and simple sums (Spark Calc's engine).
- Pinned apps on top (the Spark apps, Soot, FreeSuite by default; the owner can pin and unpin), then all
  apps by category, recent files, and the power buttons (sleep, restart, shut down, sign out, lock) with a
  confirmation for shut down and restart.
- A link to Spark Store for "find more apps".

## How

A Plasma widget (QML, `org.kde.plasma.*` APIs), because the dock is Plasma's and Plasma stays. It replaces
`org.kde.plasma.kickoff` in the SparkOS layout (`files/system/usr/share/plasma/look-and-feel/...`). Search
uses Plasma's own search backend (KRunner) so apps and settings are found the same way; the look is
SparkOS's.

## Tests

`plasmapkg2`/`kpackagetool6` installs it, QML lint, a QML test that the search box filters a fake app list,
and the boot test screenshots the open launcher.

## Done when

CI passes, the boot test shows the launcher open, and the PR is open for the owner.
