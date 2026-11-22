# Your Windows drives on SparkOS

SparkOS opens your Windows drives by itself at every start, before you sign in, at the same place each time, under their Windows letters:

| Windows | SparkOS |
|---|---|
| `C:\` | `/var/mnt/c` (also `/mnt/c`) |
| `E:\Personal Projects` | `/var/mnt/e/Personal Projects` |
| `D:\` | `/var/mnt/d`, **read-only** |

The letters come from Windows itself (its registry file on C:), so they match what you see in Windows. A drive with no letter appears under its label. The files belong to you, so Git, Claude Code and your apps can use them like any other folder.

## Read-write, read-only or off

`/etc/sparkos/windows-drives.conf` says what each letter gets: `rw`, `ro` or `off`, with `*` for the rest. SparkOS ships with D: read-only (it holds downloads and temp files and is never written from SparkOS) and every other drive read-write. To change it:

```bash
sudo nano /etc/sparkos/windows-drives.conf
sudo systemctl restart sparkos-windows-drives
```

Read-write needs Windows to shut down fully. **Keep Fast Startup off in Windows** (Control Panel, Power Options, "Choose what the power buttons do"). If Windows was hibernated or didn't shut down cleanly, SparkOS opens that drive read-only and says why in `/run/sparkos/windows-drives.json` and in `journalctl -b -u sparkos-windows-drives`. Shut Windows down normally once and restart into SparkOS to fix it.

Drives locked with BitLocker are left closed.

## What uses it

- **Claude Code**: the app menu's Claude Code starts its folder picker in `/var/mnt/e/Personal Projects` the first time. With Nova installed (it isn't part of SparkOS: `bash "/var/mnt/e/Personal Projects/JARVIS/linux/install.sh" --user`), your Windows Claude Code setup is shared: global `CLAUDE.md`, skills, settings, and each project's memory and session history, so `claude --resume` finds the sessions you had on Windows. See [claude-code.md](claude-code.md).
- **Programs** can read `/run/sparkos/windows-drives.json`: one entry per drive with `letter`, `label`, `device`, `partuuid`, `mountpoint`, `mode` (`rw`, `ro` or `off`) and `problem`.
