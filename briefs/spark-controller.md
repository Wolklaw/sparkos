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

## Later

A per-fan "follow the other fan" source, a fan-test button that ramps one fan and reports the RPM, and per-game profiles through Spark Games.
