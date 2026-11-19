# Testing WolkOS in a VM (Phase 1)

A VM shows that WolkOS boots, has the right name and installs its apps. It can't show gaming performance, because VM graphics are far slower than your RX 6800 XT. Performance testing happens in Phase 5 on real hardware.

## 1. Install a VM app (once)

Use either one:
- **VMware Workstation Pro**: free for personal use from Broadcom's site. It has better 3D support of the two.
- **VirtualBox**: free from virtualbox.org.

Virtualization (SVM) is already on in your BIOS (checked 2026-11-19).

## 2. Get the Bazzite ISO

From bazzite.gg, choose: **Desktop**, GPU **AMD/Intel**, desktop **KDE Plasma**. That's the image WolkOS is built on.

## 3. Create the VM

| Setting | Value |
|---|---|
| Guest OS type | Linux, Fedora 64-bit |
| Firmware | **UEFI**, with Secure Boot **off** |
| CPU | 4 cores or more |
| RAM | 8 GB or more (you have 32 GB) |
| Disk | 80 GB or more, on C: or E: (not D:) |
| Display | 3D acceleration on, maximum video memory |

Boot the ISO and install with the defaults, then create your user.

## 4. Switch the VM to WolkOS

Open Konsole in the VM:

```
rpm-ostree rebase ostree-unverified-registry:ghcr.io/wolklaw/wolkos:latest
systemctl reboot
```

After the reboot, switch to the signed image:

```
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/wolklaw/wolkos:latest
systemctl reboot
```

## 5. Check that it worked

```
grep -E '^(NAME|PRETTY_NAME)=' /etc/os-release   # should say WolkOS
rpm-ostree status | head -5                        # should show ghcr.io/wolklaw/wolkos, signed
flatpak list --app | grep -Ei 'heroic|onlyoffice'  # both listed
```

Heroic and ONLYOFFICE install in the background a few minutes after the first login, and a notification appears when they're done. If they don't appear after 10 minutes, send me the output of:

```
systemctl status system-flatpak-setup.service
```

Also open **System Settings > About this System** and confirm it says WolkOS.

**Phase 1 is done when** all of the above checks out. Send me what you see, including anything that looks wrong.
