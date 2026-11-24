# Spark Audio

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look (the mono variant, the SparkOS colours).

## Why

Sound on SparkOS is Plasma's volume applet in the tray: one slider, a device list and a per-app list in a
small popup. The owner has a FiiO USB DAC, a HyperX QuadCast, a Logitech C920, onboard audio and HDMI
outputs, and wants a real mixer: every device named properly, per-app volume and routing, a mic test, a
simple equalizer, and control of a Focusrite Scarlett (Focusrite Control does not exist on Linux). The
owner wants as little third-party software as possible, so no pavucontrol, EasyEffects or qpwgraph.

## What it does

- Outputs and inputs: list, set the default, volume, mute, live level meter, the mode of each sound card.
- Apps: per-app volume and mute, and moving a playing or recording app to another device.
- Mic test: record 3 seconds from the default input and play them back on the default output.
- EQ: five bands and presets for one output, through a PipeWire filter-chain run as a user service, and
  removable without a trace.
- Scarlett: a page for the kernel's `scarlett2` ALSA controls (input level, air, pad, phantom power, direct
  monitor, output volumes, mixes, routing), shown only when such a card is found.
- Live updates without polling: the window reacts to PipeWire's own change messages.

Plasma's volume applet stays in the tray. Its "Configure Audio Devices..." entry still opens Plasma's Sound
page; Spark Audio opens from the menu, the dock or `spark-audio`. Rewiring the applet means patching
`plasma-pa`, so it is left as a decision for the owner.

## How

Python 3 and Tk, like Spark Monitor (no GTK or Qt needed for sliders and meters). It uses PipeWire's own
command line tools and no extra libraries:

- `pw-dump --monitor` for the graph and every change to it.
- `wpctl` and `pactl` to change volume, mute, default device, moves and card profiles.
- `pw-record --raw` for meters (only the visible default device, only while the window is shown) and the mic
  test, `pw-play` for the playback.
- `pipewire -c eq.conf` as `spark-audio-eq.service` (user unit) for the equalizer, `pw-cli` to change a band
  live. Removing an EQ puts the default back, stops the unit and deletes its files.
- `amixer` (package `alsa-utils`, installed by the image step) for the Scarlett controls.

## Honest limits

- The owner has no Scarlett plugged in. That page is built from the driver's control names and tested against
  a made-up dump, never on hardware. The README and the page say so. It needs trying on a real interface.
- Not tried by ear for long: the EQ. It was started and removed once on the owner's PC.

## Tests

- Unit tests, no PipeWire and no sound card: device naming on a sanitized real `pw-dump` of the owner's PC,
  graph updates, volume and mute and default through a fake backend, the EQ config and files with a fake
  `systemctl`, the Scarlett parser, classifier and writes against a fake `amixer`, the command line.
- Window tests under Xvfb: every tab builds, French text fits (run twice in CI, English and French).
- In the SparkOS image: the build step, `--self-test`, a per-user install and uninstall that leaves nothing.
  The boot test runs the self-test and checks the app is installed.

## Done when

CI passes on Fedora and in the SparkOS image and the PR is open for the owner. Marked 0.1.0 until the
Scarlett page has been tried on a real interface.
