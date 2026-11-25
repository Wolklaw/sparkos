# Spark Boxes: virtual machines

Built into the image (it needs image packages). Replaces virt-manager and VirtualBox.

## Why

`spark virt setup` (PR #90) turns on libvirt, QEMU/KVM, UEFI firmware and a software TPM, then
tells the owner to install Virtual Machine Manager from Flathub. That is someone else's app, and
an old-fashioned one: making a Windows 11 VM in it takes a dozen screens. VirtualBox is "Partly"
in [docs/switching.md](../docs/switching.md) for the same reason.

## What

- **List of VMs** with state (off, running, paused), OS icon, CPUs, memory, disk size. Start,
  shut down (ACPI), force off (confirmed), pause, resume, delete (confirmed, asks whether to
  delete the disk too).
- **New VM in one screen.** Pick an ISO (file picker, or drop it on the window), pick a preset,
  name it, Create.
  - Presets: **Windows 11**, **Windows 10**, **Linux**, **Other**. The preset is guessed from the
    ISO's volume label (`isoinfo`-free: read the ISO 9660 primary volume descriptor at byte 32808
    in Python), and the owner can change it.
  - Defaults from the host: half the CPU threads up to 8 (owner's PC: 8 of 16), memory 8 GB for
    Windows and 4 GB for Linux but never more than half of RAM, disk 80 GB for Windows and 40 GB
    for Linux (thin qcow2, grows as used).
  - Windows 11 gets what its installer checks for: UEFI with Secure Boot (the `secboot` OVMF
    build with Microsoft keys enrolled) and a TPM 2.0 (swtpm). No registry bypass tricks.
- **Console in the app.** The VM's screen in a Spark Boxes window over SPICE: keyboard and mouse
  grab with a visible "Ctrl+Alt to release" hint, resize the guest to the window when the guest
  supports it, full screen, send Ctrl+Alt+Del, clipboard sharing when the guest has the SPICE
  agent.
- **Snapshots:** take, list, revert, delete, with a name and the date. Revert is confirmed.
- **USB devices:** a list of the host's USB devices with "Give to this VM" and "Take back"
  (libvirt hostdev, hot plug). Spark Disks' rule holds here too: never offer the drive that holds
  D: or the system disk.
- **Settings per VM:** CPUs, memory, add a disk, change the CD (ISO), network on/off, boot order.
  Changes that need the VM off say so.
- **Windows drivers:** a button "Get the Windows drivers (virtio-win)" that downloads Red Hat's
  virtio-win ISO from fedorapeople.org, checks its sha256 against the one published next to it,
  and attaches it as a second CD. Without it, Windows VMs use SATA disks and an e1000e network
  card, which work with no drivers, only slower. The default for new Windows VMs is the
  no-driver setup, so creating a VM never needs a download.
- **When libvirt is off:** the window says "Virtual machines are off" and a TURN ON button runs
  `spark virt setup` (it asks for the password once and needs a log out and in; say so).
- `spark-boxes --list`, `--start NAME`, `--stop NAME` for the terminal.

Non-goals for 0.1: shared folders (virtiofs and Windows' WinFsp need guest work; a later
version), GPU passthrough, importing VirtualBox `.vdi`/`.ova` (later: `qemu-img convert` makes it
easy), cloning, remote hosts, LXC.

## How

- **libvirt at `qemu:///system`.** `spark virt setup` already puts the owner in the `libvirt`
  group, and libvirt's own polkit rule lets that group manage VMs without a password.
- **Talk to libvirt through `python3-libvirt`** (add it to the image), not by parsing `virsh`
  output. Fall back to `virsh` only where it is simpler. Listen to libvirt's domain events for
  state changes instead of polling.
- **Write the domain XML ourselves** from the preset (q35 machine, `host-passthrough` CPU,
  virtio or SATA disk, virtio or e1000e network on libvirt's `default` NAT network, SPICE with
  a unix socket, `virtio-vga` video, ich9 sound, USB tablet, qemu guest agent channel, TPM 2.0
  emulated for Windows, OVMF loader and NVRAM). Keep the XML builder in one module with tests;
  it is the part most likely to be wrong. Validate with `virt-xml-validate` in CI if it is
  available.
- **Disks** go in libvirt's `default` storage pool (`/var/lib/libvirt/images`), created by
  `vol-create` through libvirt, so the qemu process can read them without home folder
  permission tricks. If the default pool does not exist yet, define it (that is what
  virt-manager does).
- **Console:** SPICE through the `SpiceClientGtk` widget (`spice-gtk3` and its typelib; add them to
  the image). That makes Spark Boxes a **GTK 3 app**, not Tk: embedding a SPICE display in Tk is not
  possible. Follow the other GTK Spark apps for structure and the house style (`wolklaw-design`
  skill: dark, sharp 3px corners, magenta/cyan channel slip only, mono font), English and French.
- **Snapshots:** VMs with UEFI keep their NVRAM in a separate file, and libvirt cannot take
  internal snapshots of those. Use external snapshots (disk-only when off, with memory when
  running) and libvirt's revert for external snapshots (libvirt 9.9 and newer; check the
  version in the image and say in the PR what was tried).
- **Image changes:** add `python3-libvirt`, `spice-gtk3` and what they pull in to the same
  virtualization block in `build_files/packages.sh`, with the `rpm -q` checks there. Measure the
  size they add and put it in the PR. `spark virt` stops pointing at Flathub's virt-manager and
  points at Spark Boxes instead; `spark virt status` shows whether Spark Boxes is there.
- **Desktop file and menu:** `dev.wolklaw.SparkBoxes`, category System/Emulator, open `.iso` with
  "Open with Spark Boxes" (not the default for `.iso`; Spark Archive and Spark Disks' image
  writer also open ISOs).

## Decisions

- **In the image, not optional.** It needs `python3-libvirt` and `spice-gtk3` from the image,
  and the libvirt stack is already there. It is still off until `spark virt setup`.
- **No live updates in 0.1** (it needs image packages); `live_update` false. Owner can change this
  once its image dependencies have settled, with `system_api` raised when they change.
- **Windows without drivers by default,** so a new VM never needs a download; virtio-win is
  one optional click.

## Tests

- Unit: the XML builder for each preset (golden files, plus "Windows 11 has a TPM and Secure
  Boot", "memory never over half of RAM"), the ISO label guesser on small generated ISO images,
  the USB device filter (system disk and D: refused), the virtio-win checksum check with a fake
  download.
- **libvirt's test driver** (`test:///default`) for the list, start, stop, pause, delete and
  snapshot logic with no KVM. Point the app at it with `SPARK_BOXES_URI=test:///default`.
- The window under Xvfb in English and French with the text-fit check, on the test driver.
- If the runner has `/dev/kvm`, one real run: define a tiny VM that boots a few-MB test ISO (or
  no disk, just UEFI), start it, check it runs, stop it, undefine it. Skip cleanly without KVM.
- The image build checks the new packages; the boot test opens the app from the menu in English
  and French like the other built-in apps (follow what it already does for them).
- Not covered by CI, say so in the PR: installing Windows 11 for real, USB pass-through of a real
  device, the SPICE console by hand. Try what you can on the owner's PC if `spark virt setup` has
  already run there; don't run it yourself (it changes groups and needs a log out).

## Files

`files/spark-boxes/` like the other built-in apps (`spark_boxes.py`, `sparkboxes/`, `install.sh`,
`spark-app.json`, desktop file, icons from `make_icons.py`, `tests/`, README.md),
`.github/workflows/spark-boxes.yml`, the Containerfile/install wiring the other built-in apps
use, `files/scripts/spark` (`spark virt`), [docs/switching.md](../docs/switching.md) VirtualBox
row, [docs/spark-cli.md](../docs/spark-cli.md), and the row in [README.md](README.md).

## Status

Brief written 2026-11-24. Not built yet.
