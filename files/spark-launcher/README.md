# Spark Launcher

SparkOS's app menu. It is the SparkOS button on the dock and the SPARKOS label in the top bar, and the Meta key opens it. It replaced Plasma's Kickoff. Brief: [briefs/spark-launcher.md](../../briefs/spark-launcher.md).

**Where it runs now.** In the Spark session the menu is part of Spark Shell (`launcherui.py`), which shares this folder's `launcher_logic.py` for ranking and sums. It opens above the SPARK button and has apps, sums and the power row; it has no settings-page, recent-file or file search, because those came from KRunner, and it keeps pins in `~/.config/spark/shell.json`. The Plasma widget described below is not in the image (`/usr/share/plasma` is removed) and only works on a Plasma 6 desktop.

- **Search as you type:** apps show at once (Spark Launcher ranks them itself: name first, then words in the name, initials like `sm` for Spark Monitor, then what the app is, like "browser"). Settings pages, recent files, file search, places and the session words follow, from Plasma's own search (KRunner) when the widget runs on Plasma, with apps it already showed left out. Enter opens the top result; Up and Down move; Escape clears the box, then closes.
- **Sums:** type `12*3+0.5` or `sqrt(2)` and Spark Calc answers on the first line (`spark-calc --eval`, about 50 ms, nothing runs when you aren't typing a sum). Enter copies the answer. In French, `1,5 + 2` works and the answer has a decimal comma. Only digits, operators and Spark Calc's function names count as a sum, so app names never start a calculation.
- **Pinned apps** on top: Soot, FreeSuite and the Spark apps the first time (those installed). Right-click any app to pin or unpin it. In the widget, pins are kept by Plasma's activity database, like Kickoff's favourites; in Spark Shell they are the `pinned` list in `shell.json`.
- **All apps by category**, and **recent files** beside them.
- **Find more apps** opens Spark Store.
- **Power:** lock, sleep, sign out, restart, shut down. Sign out, restart and shut down ask first, in the launcher; the widget skips Plasma's own confirmation screen so you aren't asked twice. Spark Shell calls `loginctl` and `systemctl` directly.

English and French follow the session's language ([strings.js](package/contents/code/strings.js) has every word).

## How it's built

A Plasma 6 widget in QML ([package/](package)), id `dev.wolklaw.sparklauncher`. [main.qml](package/contents/ui/main.qml) connects Plasma's models to the open launcher: the same app, search, favourite and recent-file models Kickoff uses (`org.kde.plasma.private.kicker`), session actions (`org.kde.plasma.private.sessions`), and Spark Calc through Plasma's command runner. [Launcher.qml](package/contents/ui/Launcher.qml) is the open launcher; it knows nothing about Plasma, which is what lets the tests hand it plain lists. It provides `org.kde.plasma.launchermenu`, which is how Plasma knows the Meta key opens it.

The look is the Spark apps' (Spark Media's palette, mono type, sharp corners): the SPARKOS wordmark and the panel's frame tear 450 ms after it opens and every 7 to 12 seconds while open, and on events (a copied answer, a question before shut down, a pin). Off when Plasma's animations are off (widget); the small static slip stays.

## Install

In SparkOS the widget is no longer used: Spark Shell has the launcher. [files/scripts/spark-launcher.sh](../scripts/spark-launcher.sh) still copies the widget to `/usr/share/plasma/plasmoids/dev.wolklaw.sparklauncher`, and the no-KDE step then removes that folder.

On a Plasma 6 desktop, or to try a change without rebuilding the image:

    bash install.sh --user              # into ~/.local/share/plasma/plasmoids, no root
    bash install.sh --user --uninstall
    bash install.sh --self-test         # what it needs from Plasma, and whether spark-calc answers

With `--user`, add it yourself: right-click the panel, Add Widgets, Spark Launcher.

It has no `spark-app.json` on purpose: it's part of the desktop, not an app for Spark Store to list.

## Tests

    bash tests/run.sh       # needs qt6-qtdeclarative-devel and kf6-kirigami; no display

QML lint, then Qt Quick tests: [tst_search.qml](tests/tst_search.qml) checks the ranking, which text counts as a sum, the command quoting and that every word has a French one; [tst_launcher.qml](tests/tst_launcher.qml) opens the launcher with a fake app list and checks that the search box filters it, Enter opens the right row, KRunner's results follow without repeats, sums go to Spark Calc, shut down and restart ask first, lock doesn't, categories switch the list, and saves screenshots (English, French, search, sum, the shut down question).

[.github/workflows/spark-launcher.yml](../../.github/workflows/spark-launcher.yml) runs those, the image build step, and Plasma's widget runner (`plasmawindowed --smoke-test`, which builds the open launcher with Plasma's real models) on Fedora and inside the published SparkOS image. The boot test presses Meta on a booted SparkOS and checks the launcher opened, types a sum, and keeps the screenshots (`5-launcher-*.png`).

## Not done yet

- Not tried on the owner's PC yet: the boot test's VM is the first real desktop it runs on.
- Pinned apps can't be dragged to reorder yet (pin order is the order they were pinned).
