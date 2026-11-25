# Spark Boxes

The SparkOS virtual machines window. It makes, starts and stops machines on libvirt and QEMU/KVM,
shows their screen, takes snapshots and hands them USB devices. It replaces Virtual Machine Manager
and VirtualBox. Version 0.1.0. Nothing leaves this PC.

## Using it

Turn libvirt on once: `spark virt setup` (password once, then log out and in). Then open Spark Boxes
from the app menu.

- **New machine.** Pick an ISO. The name and the system (Windows 11, Windows 10, Linux, other) are
  guessed from the disc's label; change them if wrong. CPUs, memory and disk start at sensible numbers
  for this PC (the disk is thin: it grows as used). Windows 11 gets UEFI with Secure Boot (Microsoft
  keys enrolled) and a TPM 2.0, which its installer asks for.
- **Screen.** OPEN SCREEN shows the machine in a window: keyboard and mouse grab (Ctrl+Alt lets go),
  full screen, Ctrl+Alt+Del.
- **Settings.** CPUs, memory, extra disk, the CD, network on or off, what boots first. A change that
  needs the machine off says so.
- **Snapshots.** Take, revert (asks first) and delete. They are external, so they also work with UEFI.
- **USB.** Give a device to a running machine, take it back. The drive holding D: and the system
  disk are never offered, and neither is anything mounted.
- **Windows drivers.** Windows machines start on plain devices (SATA disk, e1000e network) that need
  no driver. GET WINDOWS DRIVERS downloads the virtio-win disc over https, checks its SHA-256 and
  attaches it as a second CD; install the drivers from inside Windows. It does not switch the
  machine's devices over for you.

## The command line

```
spark-boxes                 open the window
spark-boxes NAME            open that machine's screen
spark-boxes --list          print the machines and their state
spark-boxes --start NAME    turn a machine on
spark-boxes --shutdown NAME ask a machine to shut down
spark-boxes --version
spark-boxes --self-test     check what it needs, without a window or a real machine
```

`SPARK_BOXES_URI` points it at another libvirt (default `qemu:///system`). Language follows
`LC_ALL`, `LC_MESSAGES`, `LANG` (English or Quebec French); `SPARK_LANG=en|fr` wins.

## How it is built

GTK 3 (the machine's screen is spice-gtk's widget, which has no GTK 4 build), python3-libvirt and
spice-gtk3. libvirt's events run on the GLib main loop (`sparkboxes/eventloop.py`): libvirt's own
Python loop calls back from a second thread, which corrupted GTK's memory in the window tests.
The machine description is built in `sparkboxes/xmlgen.py`; UEFI is chosen by libvirt's firmware
descriptors, so no OVMF path is written.

## Tests

```
python3 -m unittest tests.test_core                                   # XML, USB filter, virtio, Manager
dbus-run-session -- xvfb-run -a python3 -m unittest tests.test_ui     # the window, English and French
SPARK_LANG=fr ...                                                      # the same in French
```

They run on libvirt's built-in test driver and a fake sysfs. The test driver can't do external
snapshots, device updates or volume upload, so those paths are covered with fakes (see the tests);
the XML was also checked against a real libvirt 12.6 session driver. A real Windows 11 install has
not been tried. `SPARK_SHOT_DIR=dir` saves screenshots of every page.

## Installing

On SparkOS it is in the image (`files/scripts/spark-boxes.sh`, with python3-libvirt and spice-gtk3 from
`build_files/packages.sh`). Elsewhere: `bash install.sh --user` (no root; needs Python 3, PyGObject, GTK 3,
python3-libvirt, and spice-gtk3 for the screen), `bash install.sh --user --uninstall`, or `sudo bash
install.sh --deps` for the whole system. Uninstalling never touches your machines or their disks.
