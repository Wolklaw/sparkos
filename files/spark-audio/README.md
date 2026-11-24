# Spark Audio

The SparkOS sound mixer. It lists every output and input with a name you can read, sets the default, changes volume and mute with a live level meter, sets the volume of each app and moves an app to another output, tests the microphone, adds a simple equalizer to an output, and has a page for Focusrite Scarlett interfaces. It replaces Focusrite Control and a separate mixer. Plasma's volume applet stays in the tray.

It follows the PC's language: French (Quebec) when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Version 0.1.0. It ships in the SparkOS image ([build step](../scripts/spark-audio.sh)) and installs for one user without root (`install.sh --user`).

**Honest status.** Everything except the Scarlett page was tried on the owner's PC (FiiO USB DAC-E10, HyperX QuadCast, onboard ALC897, AMD HDMI, Logitech C920). The **Scarlett page has never touched a real interface**: nobody had one plugged in. It is written against the control names of the kernel's `scarlett2` driver (as the driver source names them) and tested only against a made-up `amixer contents` dump of a 2i2 in `tests/fixtures`. Expect wrong or missing controls on a real one until it has been tried; the page says so at the top.

## What is in it

- **Outputs:** every output, with the sound card's own name when PipeWire's is raw ("FiiO USB DAC-E10", "Onboard audio (ALC897)", "AMD HDMI / DisplayPort"). Set default, mute, volume slider, and a live meter on the default output. Below, **Sound cards**: the mode of each card (an HDMI card with no screen has no output until the mode is on; the onboard card switches between analog and digital jacks).
- **Inputs:** the same for microphones, plus **Mic test**: records 3 seconds from the default input, then plays them back on the default output.
- **Apps:** each app that is playing or recording, with its own volume, mute and a menu to move it to another output (or input). EQ outputs show as "(EQ)" targets.
- **EQ:** five bands (bass 90 Hz, low mid 300 Hz, mid 1 kHz, presence 3.5 kHz, treble 9 kHz, plus or minus 12 dB) and six presets, for one output at a time. Double-click a band to reset it.
- **Scarlett:** only appears when a card with `scarlett2` controls is found: input level (line or instrument), air, pad, phantom power, direct monitor, output volumes, monitor mixes (A, B, ...), routing, and the read-only status (sync, clock). Anything it does not recognise goes under "Other controls" instead of being hidden.

Tabs: Ctrl+1 to Ctrl+5 (a missing Scarlett tab is skipped), Ctrl+W closes. A second `spark-audio` brings the open window forward.

## How it opens from Plasma's volume applet

The tray applet stays as it is. Its **Configure Audio Devices...** entry opens Plasma's own Sound page (`systemsettings kcm_pulseaudio`), and it is not rewired: the applet is compiled into `plasma-pa`, so redirecting that action would mean patching KDE's package or hiding its settings page, and that is more than this app should do on its own. Open Spark Audio from the app menu (type "audio" or "sound"), from the dock, or with `spark-audio`. The menu entry also has right-click shortcuts to Outputs, Inputs and EQ. If the owner wants the applet to open it, say so and it can be done as a separate change with its cost written down.

## How it works

- **Reading.** One long-running `pw-dump --monitor` process: the first message is the whole graph, later ones are partial updates (`info: null` means removed). Nothing is polled. The window sleeps on a pipe and wakes only when the graph changes; rows are matched by node ID and updated, never rebuilt, and a slider you are dragging is left alone.
- **Writing.** `wpctl set-volume`, `set-mute` and `set-default`, and `pactl move-sink-input`, `move-source-output` and `set-card-profile`. Slider drags are coalesced so a fast drag sends a few commands, not hundreds.
- **Volume scale.** The slider is the cube root of PipeWire's channel volume, the same scale as Plasma's applet and `wpctl`, so 50% here is 50% there.
- **Meters.** `pw-record --raw` on the default output's monitor (`stream.capture.sink=true`) or the default input, at a low rate, only for the visible tab's default device and only while the window is shown. Hidden or minimized: all meters stop. Spark Audio's own streams are named `spark-audio-...` and left out of the lists.
- **Equalizer.** A second PipeWire process, run as the user unit `spark-audio-eq.service` (`pipewire -c ~/.config/spark-audio/eq.conf`), holds one filter-chain per EQ'd output: a pre-amp that lowers the level by the largest boost (so boosts do not clip) and five biquad bands. Each shows up as an output named after the real one with "(EQ)" at the end, and the real output is routed through it. Sliders change the running chain through `pw-cli`, without restarting. **Remove EQ** (or **Remove every EQ**) puts the default back on the real output, stops and disables the unit, and deletes `eq.conf` and the unit file, so nothing is left. `spark-audio --remove-eq` does the same from a terminal, and `install.sh --uninstall` runs it.
- **Scarlett.** `amixer -c N contents` to read and `amixer -c N cset numid=X value` to write, polled every 2 seconds only while the Scarlett tab is visible. Cards are found from `/proc/asound/cards` and kept when at least two control names match the `scarlett2` driver's. `amixer` is in `alsa-utils`, which the image build step installs.

Settings are in `~/.config/spark-audio/`, the log in `~/.local/state/spark-audio/`.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed (and any EQ service)
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
spark-audio                               # or find it in the menu
spark-audio --tab eq                      # open on a tab: outputs, inputs, apps, eq, scarlett
spark-audio --self-test                   # what it can read on this PC; no display needed
spark-audio --remove-eq                   # delete the equalizer service and its files
spark-audio --fake tests/fixtures         # the window with the test data instead of this PC
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has (Python 3 with tkinter, PipeWire's tools). It installs to `~/.local/lib/spark-audio/`, `~/.local/bin/spark-audio`, `~/.local/share/applications/` and `~/.local/share/icons/`, and lists every file it wrote in `~/.local/lib/spark-audio/installed-files` for `--uninstall`. Settings and the log are left in place.

`spark-app.json` describes the app for the Spark Portal.

The tests run on saved data: `tests/fixtures/pw-dump.json` is a real `pw-dump` of the owner's PC with serial numbers and paths removed, `amixer-contents.txt` is a made-up Scarlett 2i2, and `proc-asound-cards.txt` its card list. They cover device naming, graph updates, volume and mute and default through a fake backend, the EQ files and service calls (with a fake `systemctl`), the Scarlett parser and writes, the command line, every tab under Xvfb, and the French text. CI ([workflow](../../.github/workflows/spark-audio.yml)) runs the image build step and the tests in English and French in Fedora, and inside the published SparkOS image installs it with `--user` as a normal user, runs the self-test and the tests, uninstalls it and checks nothing is left.

## Known gaps

- **Scarlett: not tried on hardware.** See above. Routing is shown as far as the driver's enum controls allow; the Scarlett 4th gen and Clarett+ use other control names and may only show under "Other controls". The kernel's `Level Meter` control is not shown.
- **The EQ was started and removed once on the owner's PC.** It has not been listened to for long, and games that pick an output by name will not use the "(EQ)" output until they are pointed at it.
- **One EQ service for all outputs.** Changing which outputs have an EQ restarts it, which cuts the sound for a moment.
- **No per-app EQ, no surround, no sample-rate or buffer settings.** Those stay in PipeWire's own config.
- **The mic test plays on the default output**, not a chosen one.
- English and Quebec French, picked from the PC's language; every sentence is in `sparkaudio/text.py`.
