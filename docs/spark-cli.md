# spark: SparkOS's system commands

`spark` is SparkOS's own command for system jobs: updates, rollbacks, kernel arguments, services,
logs for a bug report. It replaces Universal Blue's `ujust` (Bazzite's `just` recipes), which plain
Fedora doesn't have (SparkOS was built on Bazzite until 2026-11-23). It's one bash script, [files/system/usr/bin/spark](../files/system/usr/bin/spark),
with no `just` and no other new package, built for Fedora Kinoite, SparkOS's base.
Tab completion: [files/system/usr/share/bash-completion/completions/spark](../files/system/usr/share/bash-completion/completions/spark).

```
spark help                  list the commands
spark help COMMAND          what one command does
spark --dry-run COMMAND     show what would change, change nothing
spark --yes COMMAND         don't ask "Continue?" (for scripts)
```

Commands that take an action (`on`, `off`...) show the current state when given none. Commands
that need admin rights print the command first, then ask for the password: `sudo` in a terminal,
a password window (`pkexec`) otherwise. Bigger changes (rollback, kernel arguments, cleaning,
restarts) ask "Continue?" first.

## Commands

| Command | What it does | Replaces (ujust) |
|---|---|---|
| **System and updates** | | |
| `spark info` | SparkOS version, image, kernel and its arguments, board and firmware, CPU, GPU, Mesa, memory, disks, Secure Boot, Spark Update's versions | `bios-info`, part of `device-info` |
| `spark status` | The installed versions (deployments), numbered for `pin`/`boot-default` | `rpm-ostree status` |
| `spark update` | Spark Update's "Check now" (download and stage, never restarts), then your own Flatpak apps | `update` |
| `spark rollback` | The previous version starts at the next restart (`spark-update --rollback`) | Bazzite's rollback helper |
| `spark pin [N]` / `spark unpin N` | Keep a version so updates never remove it (`ostree admin pin`) | (new) |
| `spark boot-default N` | Make version N the one that starts (`ostree admin set-default`) | (new) |
| `spark clean` | Unused container images, unused Flatpak runtimes, rpm-ostree's cache, Homebrew's old downloads | `clean-system` |
| `spark verify` | Check updates are signature-checked; offer to switch an unverified install to the signed image | `verify-image` |
| `spark overrides` | Files in /etc changed from the image (`ostree admin config-diff`) | `check-local-overrides` |
| **Boot and kernel** | | |
| `spark kargs [add\|remove ARG...]` | Show, add or remove kernel arguments | (several recipes used `rpm-ostree kargs`) |
| `spark initramfs [status\|regenerate\|reset]` | Build the initramfs on this PC, or go back to the image's | (new) |
| `spark grub-menu [status\|always\|auto\|hide]` | Boot menu always shown, or hidden after a good boot | `configure-grub` |
| `spark bios` | Restart into the UEFI settings | `bios` |
| `spark windows` | Restart into Windows once (UEFI `BootNext`) | `setup-boot-windows-steam` |
| `spark watchdog [status\|on\|off]` | Hardware watchdog (AMD `sp5100_tco`, Intel `iTCO_wdt`) | `configure-watchdog` |
| `spark sysrq [status\|on\|off]` | Alt+SysRq emergency keys (REISUB) | `reisub` |
| **Services** | | |
| `spark service NAME [status\|on\|off\|start\|stop\|restart]` | Any system service | (new) |
| `spark ssh [status\|on\|off\|once]` | SSH into this PC | `ssh` |
| **Gaming and sound** | | |
| `spark stop-proton` | Kill your Wine/Proton processes (a game stuck on close) | `fix-proton-hang` |
| `spark audio-restart` | Restart PipeWire for your session | `restart-pipewire` |
| `spark audio-channels [status\|on\|off]` | Game, Voice, Browser and Music outputs (for OBS and the like) | `setup-virtual-channels` |
| **Developer tools** | | |
| `spark brew` | Set up Homebrew if it isn't there (Homebrew's installer, pinned to one commit and checked by SHA-256) | Bazzite's `brew-setup` |
| `spark box [list\|new\|enter\|rm]` | Linux containers with Distrobox, or Toolbox when Distrobox isn't installed (plain Fedora) | `distrobox-new` |
| **Problems** | | |
| `spark logs [this\|last\|errors]` | The system log of this boot or the one before | `logs-this-boot`, `logs-last-boot` |
| `spark report [FOLDER]` | One `.tar.gz` with `spark info`, deployments, devices, Vulkan, failed services, crashes, Flatpak apps and both boots' logs. **Nothing is uploaded.** | `get-logs`, `device-info` (those upload to a pastebin) |

Once it's set up, `/etc/profile.d/brew.sh` puts Homebrew at the end of `PATH` (SparkOS's own, from
[files/homebrew](../files/homebrew)). `sparkos-dev-setup --brew` now points to
`spark brew` when Homebrew is missing.

## ujust recipes left out, and why

- **Steam Deck, handhelds, HTPC and laptops:** `set-default-game-mode`, `set-default-desktop`,
  `setup-decky` and the Decky plugins, `get-framegen`, `get-lsfg`, `steamos-automount`,
  `cec-mode`, `cec-sleep`, `configure-htpc-auto-hdr`, `steam-icons`, the Framework recipes,
  `toggle-i915-sleep-fix`, `check-idle-power-draw`. SparkOS targets a desktop PC.
- **Nvidia and Intel:** `toggle-nvk`, `enroll-secure-boot-key` (Universal Blue's akmods key; Fedora's
  kernel is signed by Fedora), `global-dlss`, `manage-intel-ethernet`.
- **Installing other people's apps:** `install-jetbrains-toolbox`, `install-resolve`, `openrgb`,
  `install-coolercontrol`, `install-openrazer`, `asus`, `install-displaylink`, `resilio-sync`,
  `get-emudeck`, `get-steamcmd`, `get-protonplus`, `install-boxtron`, `setup-sunshine`,
  `install-punktfunk`, `configure-waydroid`, `cockpit`, `tailscale`, `get-media-app`, the web apps.
  SparkOS's app policy: apps come from the Store (Flathub), not from scripts that layer packages.
- **Bazzite's own parts:** `bazzite-cli`, `restore-bazzite-breeze-gtk-theme`, `toggle-user-motd`,
  `add-updater-to-steam`, `changelogs` (Spark Update's window shows what changed), `pick` (`spark
  help` lists everything), `distrobox-assemble` and `setup-distrobox-app` (Universal Blue's
  manifests and images).
- **Rewriting GRUB's config:** `regenerate-grub`, `grub-timeout`. Fedora's atomic images use a
  fixed GRUB config managed by bootupd, not one made by `grub2-mkconfig`. `spark windows` covers the
  dual-boot case without touching GRUB, and `spark grub-menu` the menu.
- **Needs a package the image doesn't have:** `benchmark` (stress-ng), `configure-snapshots`
  (snapper), `configure-beesd` (bees).
- **Too much to get right in a script, owner's call:** `setup-virtualization` (virt-manager,
  IOMMU, groups), `setup-luks-tpm-unlock` (Universal Blue's helpers; a mistake can lock you out
  of the disk).
- **Small, possible later if wanted:** `password-feedback` (asterisks in sudo), `wol` (Wake-on-LAN;
  NetworkManager does it), `add-user-to-input-group`, `toggle-gigabyte-wake-fix` (one board
  family), `configure-amd-hdmi21` (`spark kargs add amdgpu.dcfeaturemask=0x402` does it),
  `global-fsr4`, `toggle-save-panics`, `check-anticheat`, `fix-reset-steam` (deletes most of the
  Steam folder), `configure-us-intl-dead-keys` (System Settings has it), the automount recipes
  (SparkOS mounts Windows drives itself, see [windows-drives.md](windows-drives.md)),
  `setup-virtual-surround`, `toggle-bt-mic`.

SparkOS has no `ujust`; `spark` is the only one.

## Tested

In containers of `ghcr.io/wolklaw/sparkos-fedora:latest`, the Fedora test image before it became the only one (not a booted system), on 2026-11-22:
`bash -n` and ShellCheck 0.11 clean; every command's help; every command that changes something,
with `--dry-run`; `info`, `kargs`, `watchdog`, `sysrq`, `ssh` and `service` status for real;
`audio-channels on/off` for real (PipeWire's `pw-config` reads the file); `stop-proton` against
real processes named `wineserver` and `pressure-vessel`; `report` for real; `brew` for real as a
normal user (Homebrew installed and `brew --version` ran); the Windows boot entry read from a real
`efibootmgr` listing. Not tried on a booted SparkOS: `update`, `rollback`, `pin`, `boot-default`,
`kargs add/remove`, `initramfs`, `grub-menu`, `verify`'s rebase, `bios`, `windows`, `clean`'s
rpm-ostree step, `box` (rootless containers don't run inside a container).
