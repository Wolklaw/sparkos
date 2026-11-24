# Spark Controller

One app for the PC's hardware: fans, RGB lighting, game controllers, and driver and firmware updates. It replaces SignalRGB, Armoury Crate, NZXT CAM and Fan Xpert.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Spark Controller ships in the SparkOS image ([build step](../scripts/spark-controller.sh)). It installs system-wide only (`sudo bash install.sh --deps`), because a root service sets the fan speeds. Design and the reasons for the choices: [briefs/spark-controller.md](../../briefs/spark-controller.md).

- **Overview:** CPU, GPU and liquid temperatures, every fan with its speed and who controls it, the current profile.
- **Fans:** a curve per fan from CPU, GPU, liquid or the hotter of CPU and GPU. Presets Quiet, Balanced, Performance and Fixed. The service smooths the temperature, waits before slowing down and limits how fast the power moves, so fans don't run in bursts. Every fan goes back to automatic when the service stops, crashes, or you turn it off.
- **Lighting:** liquidctl (NZXT) and OpenRGB (Aura, mouse, keyboard). Static colour, a few effects, apply to one or all, lights off. Saved per device and applied at login.
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

They use a fake `/sys/class/hwmon` tree, a fake liquidctl, invented fwupd output, a fake `/sys/class/input` tree with recorded input events, and a virtual gamepad made through `/dev/uinput` when the machine allows it (skipped otherwise). Nothing touches a real fan, light or firmware. Window tests are skipped without a display.
