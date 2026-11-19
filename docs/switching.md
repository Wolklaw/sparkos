# Switching this PC from Windows 11 to SparkOS

This guide covers what this PC has installed and plugged in, checked on 2026-11-19. Each line says what happens on SparkOS:
- **Works**: no change for you.
- **Replaced**: a different program does the job.
- **Partly**: works with limits.
- **No**: keep Windows (dual boot or a Windows VM) for it.

"In the image" means SparkOS ships it already. "Check" means I couldn't confirm it, and you should test it before you rely on it.

## Devices

| Device | On SparkOS | Notes |
|---|---|---|
| Canon TR4700 series (network) printer | **Works** | Printing is driverless (IPP/AirPrint). SparkOS finds the printer on the network by itself. Add or check it in System Settings > Printers (in the image). |
| Canon TR4700 scanner | **Works** (check) | Open **Skanpage** (in the image). SANE's `pixma` and `airscan` backends are both in the image. Confirm with your printer on the first day. |
| Canon fax | **No** (probably) | The Linux printing system has no Canon fax support. Fax from the printer's own panel. |
| Canon IJ Printer Assistant (nozzle check, cleaning) | **Replaced** | Open the printer's IP address in a browser to reach its own maintenance page (Remote UI). |
| Logitech G502 HERO | **Works** | Mouse works as is. **Piper** (in the image) sets DPI, buttons and lighting, replacing G HUB. Profiles already saved on the mouse keep working. |
| Keychron keyboard (VIA) | **Works** | Keyboard works as is. Remapping: usevia.app in **Chrome** (in the image). SparkOS includes the permission rule VIA needs. Soot and Firefox can't do this, because they lack WebHID. |
| HyperX QuadCast mic | **Works** | Standard USB audio. |
| FiiO E10 USB DAC | **Works** | Standard USB audio. |
| Logitech C920 webcam | **Works** | Standard USB camera. |
| Focusrite Scarlett (Focusrite Control 2 installed; not plugged in today) | **Works** / control app **Replaced** | Audio works as standard USB audio. For the mixer and routing, `alsa-scarlett-gui` (from its GitHub releases) replaces Focusrite Control 2. |
| 8BitDo controller | **Works** | Works through Steam Input. Firmware updates and remapping need 8BitDo's Windows app, so use Windows or a Windows VM for those. |
| Bluetooth adapter | **Works** | |
| Realtek 2.5 GbE network | **Works** | |
| RX 6800 XT | **Works** | Open drivers are built in. **LACT** (Flathub) replaces Adrenalin for fan curves and overclocking. It isn't in the image yet because it needs a system service. |
| Three monitors, mixed refresh rates | **Works** | KDE Plasma on Wayland handles mixed refresh rates, VRR and HDR. Set them up in System Settings > Display. |
| RGB: ASUS Aura, Patriot Viper RAM and SSD, Corsair RAM, Holtek RAM (SignalRGB) | **Partly** | **OpenRGB** (in the image) drives most of these. RAM lighting sometimes needs one extra setting to work, so check it on day one. |
| Steam virtual mic and speakers, VB-CABLE | **Replaced** | PipeWire virtual devices. Route audio with **qpwgraph** (in the image), or run `ujust setup-virtual-channels`. |

## Games and launchers

| Item | On SparkOS | Notes |
|---|---|---|
| Steam | **Works** | Built in, with Proton for Windows games. |
| Epic Games | **Works** | Through **Heroic** (in the image). |
| Battle.net: World of Warcraft, Diablo III | **Works** | Install Battle.net through **Lutris** (in Bazzite). |
| EA app | **Partly** | Through Lutris. EA games you own on Steam are easier there. |
| Rockstar: GTA V Enhanced | **Partly** | Story mode works. **GTA Online doesn't**: its anti-cheat blocks Linux. LSPD First Response depends on script hooks under Proton, so check it. |
| League of Legends, Teamfight Tactics | **No** | Riot Vanguard is kernel anti-cheat. Keep Windows for these. |
| Minecraft and CurseForge | **Replaced** | **Prism Launcher** (in the image) signs in with your Microsoft account and imports CurseForge modpacks. |
| Jagex Launcher and RuneLite | **Replaced** | **Bolt** (in the image) signs in with Jagex accounts. **RuneLite** (in the image) runs natively. |
| RSI Launcher (Star Citizen) | **Partly** | Runs through the community LUG Helper. Not supported by CIG. |
| Crusader Kings III, Valheim, Undertale | **Works** | Native Linux versions on Steam. |
| Hogwarts Legacy, Palworld, Teardown, TCG Card Shop Simulator, Dawn of War Soulstorm | **Works** (check) | Generally fine under Proton. Check each on ProtonDB. |
| Dragon Ball Sparking! Zero | **Works** | ProtonDB Gold, trending Platinum (97 reports, strong confidence). Steam Deck: Playable. Checked 2026-11-19. |
| Forza Horizon 6 | **Works** | ProtonDB Gold (best report Platinum), 1,099 reports, strong confidence. Steam Deck: Verified. Checked 2026-11-19. |
| Harry Potter: Quidditch Champions | **Works** | ProtonDB Gold (best report Platinum), only 10 reports. Steam Deck: Verified. Needs an internet connection even for single player. Checked 2026-11-19. |
| Pokémon TCG Live | **Check** | Not on Steam or ProtonDB. Lutris has one community install script whose author calls it temporary: click past install errors, and you may need to pick the language several times (last updated 2024-11). Fallback: the Android version in Waydroid (`ujust setup-waydroid`), not confirmed. If neither works, use Windows or a phone. |
| Blitz (League companion) | **No** | Not needed without League. |

## Work, creative and everyday apps

| Windows app | On SparkOS | Notes |
|---|---|---|
| Microsoft 365: Word, Excel, PowerPoint | **Replaced** | **FreeSuite** (in the image, default for .docx/.xlsx/.pptx/.csv/PDF). **ONLYOFFICE** (in the image) covers .doc/.xls/.ppt and OpenDocument until FreeSuite opens them. Office on the web works in any browser. |
| Outlook | **Replaced** | **FreeSuite Mail** (in the image, default for email links). |
| Teams, OneNote, Copilot, Amazon Music | **Replaced** | Their web versions, in Soot or Chrome. |
| PDFgear | **Replaced** | **FreeSuite PDF** (in the image, default for PDFs). |
| Firefox, Chrome | **Works** | **Soot** is the default browser. **Chrome** is in the image. Firefox is in Bazzite. |
| Google Drive | **Partly** | Add your Google account in System Settings > Online Accounts and Drive appears in Dolphin (in the image). Unlike the Windows client, it doesn't keep offline copies. For that, use rclone or a paid client such as Insync. |
| Discord, Spotify | **Works** | Both in the image. |
| OBS Studio | **Works** | In the image, with Bazzite's game-capture plugin. |
| Blender, GIMP, Audacity | **Works** | In the image. Blender renders on the RX 6800 XT through HIP. |
| Clipchamp | **Replaced** | **Kdenlive** (in the image). |
| ShareX | **Replaced** | **Spectacle** (built in) or **Flameshot** (in the image). |
| Notepad++ | **Replaced** | **Kate** (built in). |
| 7-Zip | **Replaced** | **Ark** (built in). |
| WinDirStat | **Replaced** | **Filelight** (in Bazzite). |
| HWiNFO, Task Manager | **Replaced** | **Mission Center** (in the image). |
| Ryzen Master | **No** | Set PBO and Curve Optimizer in the BIOS instead. They then apply to both systems. |
| Logitech G HUB, SignalRGB, 8BitDo, Focusrite Control | See Devices above | |
| Wallpaper Engine | **Partly** | A community KDE plugin plays many Wallpaper Engine scenes. It isn't in the image. |
| Tailscale | **Works** | In Bazzite. Run `ujust tailscale`. |
| hide.me VPN, Hotspot Shield | **Partly** | Both offer Linux command-line clients. Plain WireGuard and OpenVPN work in System Settings > Network. |
| TeamViewer | **Works** | Linux RPM from teamviewer.com. It isn't on Flathub, so it's not in the image. |
| PuTTY | **Replaced** | `ssh` in Konsole (built in). |
| VirtualBox | **Replaced** | Run `ujust setup-virtualization` to get **virt-manager**. It uses KVM and runs VMs much faster than VirtualBox on this PC today. |
| MuseHub | **No** | Windows and Mac only. |

## Development

| Tool | On SparkOS | Notes |
|---|---|---|
| Git | **Works** | Built in. |
| Node.js, Python 3.13, GitHub CLI, JDK 17 | **Works** | Run `sparkos-dev-setup` once and Homebrew installs all four. The list is in `/usr/share/sparkos/Brewfile`. |
| VS Code | **Works** | In the image, as a Flatpak. For full access to system tools, open a terminal inside VS Code or use a Distrobox container. |
| Unity 6 and Unity Hub | **Works** (check) | **Unity Hub** (in the image) is the community Flatpak. Unity also publishes an official Linux Hub. |
| Ollama | **Works** | Use the official Linux install or the **Alpaca** app (Flathub). The RX 6800 XT is supported by ROCm. |
| Claude Code | **Works** | Open **Claude Code** from the app menu, right-click a folder in Dolphin and choose **Open Claude Code here**, or run `sparkos-claude` in a terminal. The first start installs it with Anthropic's official installer (into `~/.local`, updates itself). Run `sparkos-claude-import` once to bring over your Windows `CLAUDE.md`, skills, agents and commands. See [claude-code.md](claude-code.md). |
| Claude desktop app (Chat, Cowork, Code tab) | **No** | Its Linux version is a beta for Ubuntu and Debian only. On SparkOS, use Claude Code (above), and claude.ai in the browser for chat. |
| Antigravity IDE | **Check** | Look for a Linux download. |
| Inno Setup (Windows installers for your apps) | **Partly** | Runs under Wine or Bottles (in the image). For building and testing Windows releases, a Windows VM in virt-manager is the dependable choice. |
| Your own apps: Nova, BotWatch, Broke'nt, OSRS Toolkit, Upscape, Androidbox, Delta | **Check each** | They're Windows builds. Each needs a Linux build, as Soot and FreeSuite got, or runs in the Windows VM. |

## Faster than Windows 11?

Honest answer: for most of what you do, it should be at least as fast, but some things can be slower, and it gets measured rather than assumed (Phase 5 in PLAN.md).
- **Usually as fast or faster:** boot to desktop, the desktop itself, file operations, and many games on an AMD GPU. Bazzite's kernel and Mesa drivers are tuned for gaming, and Windows background services are gone.
- **Can be slower:** some DirectX 12 games under Proton run a few percent behind Windows. The first run of a game can stutter while shaders compile, and it settles after that.
- **The measurement:** the same games at the same settings and resolution on both systems. Linux is logged with MangoHud and Windows with PresentMon/CapFrameX, comparing average FPS and 1% lows. Boot time is timed on both. Results go into `docs/benchmarks.md`.

## The switch, step by step

1. Check the **Check** items above, especially the games you play most.
2. Install SparkOS alongside Windows (Phase 5 in PLAN.md). Windows stays until SparkOS has covered a normal week of work and games.
3. On SparkOS: sign in to Steam, Heroic, Bolt and Prism. Add your Google account. Run `sparkos-dev-setup`. Print and scan one page.
4. Keep Windows (on a smaller partition, or as a VM) for anything marked **No** that you still need.
