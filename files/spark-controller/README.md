# Spark Controller

One app for the PC's hardware: fans, RGB lighting, gaming mouse DPI, game controllers, and driver and firmware updates. It replaces SignalRGB, Armoury Crate, NZXT CAM and Fan Xpert.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Spark Controller ships in the SparkOS image ([build step](../scripts/spark-controller.sh)). It installs system-wide only (`sudo bash install.sh --deps`), because a root service sets the fan speeds. Design and the reasons for the choices: [briefs/spark-controller.md](../../briefs/spark-controller.md).

- **Overview:** CPU, GPU and liquid temperatures, every fan with its speed and who controls it, the current profile.
- **Fans:** a curve per fan from CPU, GPU, liquid or the hotter of CPU and GPU. Presets Quiet, Balanced, Performance and Fixed. The service smooths the temperature, waits before slowing down and limits how fast the power moves, so fans don't run in bursts. Every fan goes back to automatic when the service stops, crashes, or you turn it off.
- **Lighting:** liquidctl (NZXT) and OpenRGB (Aura, mouse, keyboard). Static colour, a few effects, apply to one or all, lights off. Saved per device and applied at login.
- **Mouse:** gaming mice through libratbag's `ratbagd` (D-Bus, system bus; the package is in the image, and no root is needed for the person at the PC). It replaces the DPI part of Logitech G HUB. For each supported mouse it shows the onboard profiles (the one in use is marked; switched-off profiles are marked "off"), the DPI slots of the chosen profile (value from the list the mouse allows, on or off, which one is active and which is the default) and the report rate. It warns when the active slot is switched off or under 400 DPI (the mouse sat on a disabled 100 DPI slot once) and offers 2400 DPI in one click. **Nothing is sent to the mouse until Apply**; Apply writes the changes, calls the device's `Commit` so they are saved in the mouse's own memory (they hold on Windows too), then reads the mouse back and says if it did not keep them. It says so when ratbagd does not answer, when no supported mouse is found, and when the mouse is busy. It needs PyGObject (Gio), which the image has. **Tested on a Logitech G502 HERO only** (5 profiles, 5 slots each); other mice libratbag supports should work but have not been tried. **Button remapping, macros and lighting are not included yet**; a later version could add button remapping. The backend is in [`sparkcontroller/mouse.py`](sparkcontroller/mouse.py).
- **Pads:** game controllers. Lists what is connected (USB or Bluetooth, battery when the system reports one), with a live tester: every button lights, sticks are dots in circles with the kernel's deadzone and a "measure rest drift" button, triggers are bars, the d-pad, and a rumble test (heavy and light motor) where the pad supports force feedback. Controller firmware goes through fwupd like the Drivers tab, one device at a time, after a second confirming click; it says per pad whether fwupd supports the model (it reads the installed fwupd's own list: its ebitdo plugin covers a short list of 8BitDo USB models, and not Bluetooth). Plugging a pad in or out tears the title. Reading a pad needs the user to be allowed on `/dev/input/eventN`: the `uaccess` rules from steam-devices and game-devices-udev (8BitDo, Sony, Xbox and others) do that for the person at the PC; for a model they miss, the tab says so and how to add the `input` group. **Remapping is not included**, see the [brief](../../briefs/spark-controller.md). **No real controller has been tried yet**: it is tested with fake sysfs trees, recorded event streams and, where `/dev/uinput` allows, a virtual pad.
- **Drivers:** firmware updates through fwupd. Kernel, Mesa and GPU firmware are shown and updated with the system image through Spark Update. BIOS version is shown, not flashed.

Saving a curve asks for your password once (polkit). The nct6775 module that exposes the motherboard's fan headers loads at the next restart after install.

Settings are in `~/.config/spark-controller/`; fan curves in `/etc/spark-controller/fans.json`.

## Tests

```
cd files/spark-controller
python3 -m unittest discover -s tests -v
SPARK_LANG=fr python3 -m unittest discover -s tests -v
```

They use a fake `/sys/class/hwmon` tree, a fake liquidctl, invented fwupd output, a fake `/sys/class/input` tree with recorded input events, a fake ratbagd (a dict shaped like what a G502 HERO reports, `tests/fakeratbag.py`), and a virtual gamepad made through `/dev/uinput` when the machine allows it (skipped otherwise). Nothing touches a real fan, light or firmware. Window tests are skipped without a display.
