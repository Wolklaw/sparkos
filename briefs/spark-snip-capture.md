# Spark Snip: capture without Spectacle

Read [README.md](README.md) first. Work only in `files/spark-snip/` (and its workflow). Don't edit
`recipes/recipe.yml` or `boot-test.yml`: the main SparkOS session removes Spectacle from the image
once this is merged.

## Goal

Spark Snip reads the screen through KDE's Spectacle today, which is the only reason Spectacle is in
SparkOS. The owner wants SparkOS to rely on other products as little as possible
([PLAN.md, Independence roadmap](../PLAN.md)). Make Spark Snip capture on its own so Spectacle can go.

- Find out exactly how Spark Snip uses Spectacle today: screenshots, region, window, screen
  recording, the Print and Meta+Shift+S/T/R shortcuts it takes over.
- Screenshots: use KWin's `org.kde.KWin.ScreenShot2` D-Bus interface (full screen, a monitor, the
  active window, a region), which Plasma restricts to apps that declare it:
  `X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2` in the desktop entry. If that fails,
  fall back to the XDG Desktop Portal screenshot call, then report clearly.
- Screen recording: if it goes through Spectacle, move it to the XDG ScreenCast portal + PipeWire,
  encoded with GStreamer (already in the image for Spark Media). Keep the formats it offers now.
- The shortcuts must still work without Spectacle installed: register them with Spark Snip's own
  desktop entry (`X-KDE-Shortcuts`) or kglobalaccel, and check nothing still points at Spectacle.
- Keep `--self-test` (no display needed) and add a check that Spectacle is not required.

## Done when

All tests pass (Fedora container under Xvfb, and inside the SparkOS image) with Spectacle not
installed in the test environment. The PR from `spark-snip-capture` says which capture paths were
tested where, which still need a real Plasma session (Wayland screen capture can't be fully tested
in CI), and what the main session should change in the recipe (remove `spectacle`).
