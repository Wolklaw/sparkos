# Spark Controller

One app for the PC's hardware: fans, RGB lighting, and driver and firmware updates. It replaces SignalRGB, Armoury Crate, NZXT CAM and Fan Xpert for the owner. Source: [files/spark-controller](../files/spark-controller). In the SparkOS image.

Status: built 2026-11-23. Tested against a fake `/sys/class/hwmon` tree, a fake liquidctl and recorded fwupd output, and the window was opened on the owner's PC with nothing written. **Nothing has been written to a real fan, light or firmware yet.** See "Not tried on hardware".

## What the owner has

PRIME X670-P WIFI (nct6775 family sensor chip, not loaded before this app), Ryzen 7 7800X3D (k10temp), an AMD GPU (amdgpu, one fan), an NZXT USB controller (1e71:2012), the ASUS Aura controller (0b05:19af), a Logitech G502 SE (046d:c08b) and a Keychron V5 (3434:0351). The complaint that started this: fans run in bigger bursts than on Windows.

## The finding about the NZXT controller

liquidctl supports 1e71:2012 as an RGB-only device: three lighting channels, no fan or pump channels. So the NZXT box is not what drives the case fans. Their speed comes from the motherboard's fan headers, which is why the sensor-chip module (`nct6775`, `/usr/lib/modules-load.d/sparkos-nct6775.conf`) is the first thing to fix, and why the curves apply to hwmon fans. The bursts come from firmware curves that follow the temperature sample by sample.

## Fans

- **What is listed.** Every fan the kernel exposes under `/sys/class/hwmon` (`fanN_input`, `pwmN`, `pwmN_enable`) plus liquidctl fan and pump channels, with live speed and the temperatures. A fan with no `pwm` file is shown read only.
- **Curves.** Temperature to power for each fan, from CPU (Tctl), GPU (edge), the liquid sensor of a liquidctl cooler, or the hotter of CPU and GPU. Presets: Quiet, Balanced, Performance, Fixed %. Dragging a point turns a preset into a custom curve. Up to 12 points, power never falls as it gets hotter, a per-fan minimum so a fan doesn't stall.
- **Why the bursts stop.** `FanController` (`curve.py`) does three things the firmware doesn't: it averages the temperature over about 6 seconds, it holds the speed until the temperature has dropped by the hysteresis (3 degrees) on the way down, and it limits how fast the power moves (up 8 points a second, down 2). A game loading for two seconds no longer turns into a loud ramp and a drop.
- **Safe by default.** A fan is only controlled when its toggle is on and the configuration is applied. A missing or unreadable temperature goes to 80%, not to "keep the last value". A pump never goes under 50%. A fan that cannot be taken over is reported, not guessed at.
- **Handed back.** On a normal stop, on SIGTERM, on a crash, and when the toggle is turned off, every fan goes back to the mode it was in before (usually automatic). The service records the original mode of each fan in `/run/spark-controller/originals.json`, so the next start (or `ExecStopPost=spark-controller-daemon --release`) puts back what a kill left behind. "Hand all fans back" in the window does the same at any time.

## Why a root service and a polkit helper

Writing a pwm file needs root, and hwmon numbers change between boots, so a udev rule that makes one file writable by the user can't name it. The options were:

1. **udev rules that make the pwm files group-writable.** Rejected: the paths are not stable, and then any program the user runs could set a fan to 0%.
2. **Run the whole window as root.** Rejected: a Tk app with USB and a network of dependencies, as root.
3. **A small root service plus one polkit action (chosen).** `spark-controller.service` reads `/etc/spark-controller/fans.json` and does the writing. The window never writes a fan. To change the curves it runs `pkexec /usr/libexec/spark-controller-helper install-config` (action `dev.wolklaw.SparkController.configure`, password once per session, `auth_admin_keep`). The helper validates the file with the same code the service uses, so nothing but a well-formed fan list can reach `/etc`, then starts the service (or stops it when no fan is enabled). The service and the helper start Python with `-I` so nothing in the user's environment or current directory is imported as root.

The window reads `/run/spark-controller/state.json` (world readable, no secrets) to show what the service is doing; a file older than 10 seconds counts as "not running".

## Spark RGB

liquidctl is imported as a Python library for NZXT and other USB controllers. OpenRGB runs as a command (`openrgb --list-devices`, `--device N --mode X --color HEX`) for the Aura controller, the G502 SE and the Keychron. Effects: static, breathing, fade, spectrum, off, at three speeds; an effect a device doesn't have falls back to the closest mode it lists. Apply to one device, apply to all, "Lights off". The setting is saved per device in `~/.config/spark-controller/rgb.json` and applied at login by an XDG autostart entry (`spark-controller --apply-rgb`). OpenRGB's own window is hidden in the menu; it stays as the command.

## Drivers and firmware

- **Device firmware** through `fwupdmgr` (LVFS): the devices with a name and version, the pending updates, "Check for updates" and "Install updates". fwupd asks for authorisation itself.
- **System drivers** are shown, not changed: the kernel, Mesa and the GPU firmware (amdgpu) versions, labelled as updated with the system image through Spark Update. The image is atomic, so changing one alone isn't possible.
- **BIOS** version, date and vendor from `/sys/class/dmi/id`. Spark doesn't flash the BIOS.

## Pads (added in 1.1.0)

The Pads tab covers what 8BitDo's Windows-only Ultimate Software and firmware updater did for the owner's pads, plus general controller testing. Source: `sparkcontroller/pads.py` (no UI) and `padsview.py`.

- **Listing** reads `/sys/class/input/event*` only, so it needs no permission. A device counts as a pad when it has at least four buttons in the joystick/gamepad range (0x120 to 0x13f) and an axis, and none of KEY_A, BTN_MOUSE or BTN_TOUCH. That drops keyboards, mice, touchpads and the "system control" HID nodes udev wrongly tags as joysticks (the owner's Keychron V5 has one; it showed up in the first version of the rule). Connection is the evdev bus type (USB, Bluetooth, virtual). Steam Input's copy of a real pad shows as virtual and is labelled. Battery: a `power_supply` whose device is a parent of the pad's input device, or whose name contains the pad's unique id (the Bluetooth address, which is how hid-playstation names it).
- **The tester** opens the event node read-only and non-blocking and reads `struct input_event` with plain `os.read` and the EVIOCGABS and EVIOCGKEY ioctls: no python-evdev, nothing to add to the image. Axes are sorted by where they rest: a non-negative axis that starts in the bottom tenth of its range is a trigger; the others pair up in code order as sticks (X/Y, then the next two). That copes with Xbox numbering (triggers on Z/RZ) and PlayStation numbering (right stick on Z/RZ, triggers on RX/RY) without a table of models, and an odd axis out shows as a bar. A trigger held down when Spark opens the pad would be misread; that is rare. Sticks show the dot, the kernel's `flat` deadzone as a dashed ring, and "measure rest drift" (three seconds untouched, widest wander per stick, suggested deadzone one point above it). Buttons without a standard name show their evdev code. The loop polls every 25 ms only while the tab is open and the window visible.
- **Look.** The house style as Spark Controller already has it: a lit button gets the magenta and cyan outlines slipped two pixels either side, a stick at its rim and a full trigger do the same, and a pad connecting or leaving tears the title and the tester's edge (stronger for leaving). Reduced motion turns the tearing off through the app's existing switch; the static offsets stay.
- **Rumble** uploads one `FF_RUMBLE` effect with EVIOCSFF (a 48-byte `ff_effect`), plays 600 ms and closes the file, which makes the kernel drop the effect. It needs write access and `FF_RUMBLE` in the pad's capabilities; the buttons say why they don't work otherwise.
- **Access.** The image has `steam-devices` (Valve), `game-devices-udev` (`71-8bitdo-gdu.rules`: 8BitDo and others) and systemd's rules, which tag controllers' event nodes `uaccess`, giving the person at the PC an ACL. Keyboards here are `root:input 0660` with no ACL. A pad no rule knows, or a virtual pad made by uinput, is unreadable by the user: the list says "Blocked" and the tester says to add the account to the `input` group (and warns that this also lets programs read keyboards).
- **Firmware** goes through the same `Fwupd` class as the Drivers tab: the controllers among `fwupdmgr get-devices` (plugin `ebitdo`, the same USB vendor as a connected pad, or a gamepad-like name), the pending updates, and "Check for updates". Installing differs in one way: it runs `fwupdmgr update <device-id>` for the selected controller only, never "update everything", behind a second confirming click. fwupd's plugin is named `ebitdo`, not 8bitdo. The tab reads the installed fwupd's own quirk list (`/usr/share/fwupd/quirks.d/builtin.quirk.gz`) to say whether a connected USB pad's id is claimed (fwupd 2.1.10 here lists 2DC8 products 1002, 2100, 2101, 5006, 5750, 6000 to 6002, 9000, 9001, 9012, 9015, AB11, AB12, AB20 and AB21, plus a few older vendor ids). Newer 8BitDo pads are not in it, and nothing over Bluetooth is. For those the tab says fwupd has no support and to use the maker's updater. Which retail models those ids are was not checked, so the tab shows the USB id, not model names.
- **Remapping is left out.** Writing Steam Input's config is Steam's, and it changes under us. The clean version is a daemon that grabs the pad (EVIOCGRAB) and re-emits a remapped virtual pad through uinput. That doubles every pad for games (Steam Input already does it, so a second layer fights it), needs a service with `/dev/uinput`, per-pad profiles, hotplug handling and a hold-to-exit failsafe so a bad map can't lock the owner out. It is a project of its own, not a tab; decide later whether the need is real.
- **Tested with fakes only.** A fake `/sys/class/input` tree with plain files standing in for event nodes (recorded `input_event` streams); a virtual pad through `/dev/uinput` where the CI container allows it (the owner's account can open `/dev/uinput`, but the node it creates carries no uaccess tag, so on the PC that test skips); recorded fwupd output. **No real controller has been plugged in.** Not checked: axis ranges and resting values of real 8BitDo, Xbox, DualSense and Switch pads, battery names, rumble on a real motor, hotplug timing (the list rescans every two seconds), any fwupd flash. The owner's screen was off, so there is no real-screen screenshot; the canvas was exported to an image and checked that way.

## Packages

`python3-liquidctl openrgb fwupd` (`build_files/packages.sh`). The image already has OpenRGB's udev rules (`openrgb-udev-rules`); `71-spark-controller.rules` repeats the owner's devices so lighting works without them. Both exist in Fedora 45 (liquidctl 1.16, OpenRGB 1.0 candidate).

## Not tried on hardware

Everything below is written to the documented behaviour of the kernel and the tools, and tested only against fakes. The first real run is the owner's.

- The `nct6775` module and the board's fan and pwm files after the first restart. If the chip is not found, the Overview says so.
- Taking over the GPU fan (`pwm1`) on this AMD card: manual mode turns off zero-RPM mode while Spark holds it.
- OpenRGB's output format and mode names for the Aura controller, G502 SE and Keychron.
- liquidctl's colour modes on the NZXT controller 1e71:2012.
- The fwupd install flow and its authorisation prompt (the JSON listing was read on this PC without installing anything).
- liquidctl fans and pumps: the owner has no cooler liquidctl can control, so that path is tested with a fake only.
- The window on a real session beyond opening each tab.
- The whole Pads tab with a real controller (see its section).

## Later

A per-fan "follow the other fan" source, a fan-test button that ramps one fan and reports the RPM, and per-game profiles through Spark Games.
