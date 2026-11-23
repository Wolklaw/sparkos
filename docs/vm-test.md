# Testing SparkOS in a VM (Phase 1)

A VM shows that SparkOS boots, has the right name and installs its apps. It can't show gaming performance, because VM graphics are far slower than your RX 6800 XT. Performance testing happens in Phase 5 on real hardware.

## 1. Install a VM app (once)

Use either one:
- **VMware Workstation Pro**: free for personal use from Broadcom's site. It has better 3D support of the two.
- **VirtualBox**: free from virtualbox.org.

Virtualization (SVM) is already on in your BIOS (checked 2026-11-19).

## 2. Get the SparkOS installer

Download every file of the [installer release](https://github.com/Wolklaw/sparkos/releases/tag/installer) and join them with `join-iso.cmd` (Windows) or `join-iso.sh` (Linux), as in [install.md](install.md).

## 3. Create the VM

| Setting | Value |
|---|---|
| Guest OS type | Linux, Fedora 64-bit |
| Firmware | **UEFI** (Secure Boot on or off: SparkOS runs Fedora's signed kernel) |
| CPU | 4 cores or more |
| RAM | 8 GB or more (you have 32 GB) |
| Disk | 80 GB or more, on C: or E: (not D:) |
| Display | 3D acceleration on, maximum video memory |

Boot the ISO and install with the defaults, then create your user.

## 4. Or switch an existing Fedora atomic VM

A VM already running Fedora Kinoite (or Bazzite, or another Fedora atomic desktop) can move to SparkOS instead. In a terminal:

```
rpm-ostree rebase ostree-unverified-registry:ghcr.io/wolklaw/sparkos:latest
systemctl reboot
```

After the reboot, switch to the signed image:

```
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:latest
systemctl reboot
```

## 5. Check that it worked

```
grep -E '^(NAME|PRETTY_NAME)=' /etc/os-release   # should say SparkOS
rpm-ostree status | head -5                        # should show ghcr.io/wolklaw/sparkos, signed
```

Spark Welcome opens at the first login. Also open **Spark Settings** (or System Settings > About this System) and confirm it says SparkOS.

Send me what you see, including anything that looks wrong.
