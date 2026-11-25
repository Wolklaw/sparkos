# Switching this PC from Windows 11 to SparkOS

This guide covers what this PC has installed and plugged in, checked on 2026-11-19 and updated 2026-11-23 for the Spark apps. For any PC, Spark Welcome's **Move from Windows** page does the same from the Windows drive itself: it reads the installed programs and says what to use for each one, copies your files and fonts, finds your Steam libraries, and has a checklist for before you erase Windows. Each line says what happens on SparkOS:
- **Works**: no change for you.
- **Replaced**: a different program does the job.
- **Partly**: works with limits.
- **No**: keep Windows (dual boot or a Windows VM) for it.

"In the image" means SparkOS ships it already: only SparkOS's own apps (Soot, FreeSuite and the Spark apps) and the system itself. "Optional Spark app" means a Spark app you add with one click from Spark Store or Spark Welcome's Apps page. "From the Store" means you install it with one click from Spark Store. "Check" means I couldn't confirm it, and you should test it before you rely on it.

**Installing apps:** a store with an Install button, or double-click what you downloaded (`.exe`, `.AppImage`, `.rpm`). See [installing-apps.md](installing-apps.md).

## Devices

| Device | On SparkOS | Notes |
|---|---|---|
| Canon TR4700 series (network) printer | **Works** | Printing is driverless (IPP/AirPrint). SparkOS finds the printer on the network by itself. Add or check it in **Spark Settings**, Printers. |
| Canon TR4700 scanner | **Works** (check) | SANE's `pixma` and `airscan` scanner support is in the image. Scan with **Spark Scan**, SparkOS's own scanning app: preview, crop, the glass or the feeder, one PDF (searchable, if you want) or an image per page, saved to Documents/Scans. It has only been tested with SANE's test scanner so far; confirm with your printer on the first day. |
| Canon fax | **No** (probably) | The Linux printing system has no Canon fax support. Fax from the printer's own panel. |
| Canon IJ Printer Assistant (nozzle check, cleaning) | **Replaced** | Open the printer's IP address in a browser to reach its own maintenance page (Remote UI). |
| Logitech G502 HERO | **Works** | Mouse works as is. **Piper** (from the Store) sets DPI, buttons and lighting, replacing G HUB. Profiles already saved on the mouse keep working. |
| Keychron keyboard (VIA) | **Works** | Keyboard works as is. Remapping: usevia.app in **Chrome** (from the Store). SparkOS includes the permission rule VIA needs. Soot and Firefox can't do this, because they lack WebHID. |
| Caps Lock (any keyboard) | **Like Windows** | Turns on and off the moment you press it. On plain Linux it turns off when you release it, so a letter typed before the key is fully up still comes out in capitals. Tested in a VM so far, not yet on a real keyboard. To get Linux's way back: `sudo systemctl mask sparkos-capslock@.service`, then restart. |
| HyperX QuadCast mic | **Works** | Standard USB audio. |
| FiiO E10 USB DAC | **Works** | Standard USB audio. |
| Logitech C920 webcam | **Works** | Standard USB camera. |
| Focusrite Scarlett (Focusrite Control 2 installed; not plugged in today) | **Works** / control app **Replaced** | Audio works as standard USB audio. For the mixer and routing, `alsa-scarlett-gui` (from its GitHub releases) replaces Focusrite Control 2. |
| 8BitDo controller | **Works** | Works through Steam Input. Firmware updates and remapping need 8BitDo's Windows app, so use Windows or a Windows VM for those. |
| Bluetooth adapter | **Works** | |
| Realtek 2.5 GbE network | **Works** | |
| RX 6800 XT | **Works** | Open drivers are built in. **Spark Controller** (in the image) shows temperatures and sets fan curves. For overclocking and undervolting, **LACT** (Flathub) replaces Adrenalin; it isn't in the image because it needs a system service. |
| Three monitors, mixed refresh rates | **Works** | KDE Plasma on Wayland handles mixed refresh rates, VRR and HDR. Set them up in **Spark Settings**, Displays. |
| RGB: ASUS Aura, Patriot Viper RAM and SSD, Corsair RAM, Holtek RAM (SignalRGB) | **Partly** | **Spark Controller** (in the image) drives most of these through OpenRGB. RAM lighting sometimes needs one extra setting to work, so check it on day one. |
| Steam virtual mic and speakers, VB-CABLE | **Replaced** | PipeWire virtual devices. Route audio with **qpwgraph** (from the Store), or run `spark audio-channels on` for Game, Voice, Browser and Music outputs. |

## Games and launchers

| Item | On SparkOS | Notes |
|---|---|---|
| Steam | **Works** | Install **Steam** from Spark Welcome's Games page or the Store. Proton runs Windows games. Games already on the Windows drives don't download again: Spark Welcome's Move from Windows page lists each Steam library, and you add its folder in Steam, Settings, Storage. |
| Epic Games, GOG, Amazon Games | **Works** | **Spark Games** (in the image) signs in to them itself, lists what you own and installs and starts the games. |
| Battle.net: World of Warcraft, Diablo III | **Works** | **Spark Games** adds Battle.net: it installs it on Wine and lists its games. |
| EA app | **Partly** | **Spark Games** adds it the same way. EA games you own on Steam are easier there. |
| Rockstar: GTA V Enhanced | **Partly** | **Spark Games** adds the Rockstar launcher. Story mode works. **GTA Online doesn't**: its anti-cheat blocks Linux. LSPD First Response depends on script hooks under Proton, so check it. |
| League of Legends, Teamfight Tactics | **No** | Riot Vanguard is kernel anti-cheat. Keep Windows for these. |
| Minecraft and CurseForge | **Replaced** | **Prism Launcher** (from the Store) signs in with your Microsoft account and imports CurseForge modpacks. |
| Jagex Launcher and RuneLite | **Replaced** | **Bolt** (from the Store) signs in with Jagex accounts. **RuneLite** (from the Store) runs natively. |
| RSI Launcher (Star Citizen) | **Partly** | Runs through the community LUG Helper. Not supported by CIG. |
| Crusader Kings III, Valheim, Undertale | **Works** | Native Linux versions on Steam. |
| Hogwarts Legacy, Palworld, Teardown, TCG Card Shop Simulator, Dawn of War Soulstorm | **Works** (check) | Generally fine under Proton. Check each on ProtonDB. |
| Dragon Ball Sparking! Zero | **Works** | ProtonDB Gold, trending Platinum (97 reports, strong confidence). Steam Deck: Playable. Checked 2026-11-19. |
| Forza Horizon 6 | **Works** | ProtonDB Gold (best report Platinum), 1,099 reports, strong confidence. Steam Deck: Verified. Checked 2026-11-19. |
| Harry Potter: Quidditch Champions | **Works** | ProtonDB Gold (best report Platinum), only 10 reports. Steam Deck: Verified. Needs an internet connection even for single player. Checked 2026-11-19. |
| Pokémon TCG Live | **Check** | Not on Steam or ProtonDB. Try its Windows installer with **Spark Run** (double-click the .exe); not tested yet. Fallback: the Android version in Androidbox, not confirmed. If neither works, use Windows or a phone. |
| Blitz (League companion) | **No** | Not needed without League. |

## Work, creative and everyday apps

| Windows app | On SparkOS | Notes |
|---|---|---|
| Microsoft 365: Word, Excel, PowerPoint | **Replaced** | **FreeSuite** 0.4.1 (in the image) is the default for .docx/.xlsx/.pptx, the old .doc/.xls/.ppt, OpenDocument, RTF, CSV and PDF. It reads old binary files only partly: .doc without formatting or pictures, .ppt as text only, .xls without charts or merged cells. For those, install **ONLYOFFICE** from the Store; it then shows under "Open with". Office on the web works in any browser. |
| Outlook | **Replaced** | **FreeSuite Mail** (in the image, default for email links). |
| Teams, OneNote, Copilot | **Replaced** | Their web versions, in Soot or Chrome. |
| Amazon Music | **Works** | The Windows app runs through **Spark Run** (Spark Welcome, Apps, installs it; or `spark-run --get amazon-music`), with Ultra HD (lossless FLAC) up to your DAC's sample rate. Spark Run adds the CJK font mapping and the empty `update.ini` it needs. Wine apps use the device's current rate, 48 kHz by default; for Ultra HD above that, pick a higher fixed rate in Spark Settings, Sound, or set it in `~/.config/pipewire/pipewire.conf.d/` (see the note in `/usr/share/pipewire/pipewire.conf.d/10-sparkos-sample-rates.conf`). The web player is standard quality only. |
| PDFgear | **Replaced** | **FreeSuite PDF** (in the image, default for PDFs). |
| Firefox, Chrome | **Works** | **Soot** (in the image) is the default browser. Chrome and Firefox install from the Store. |
| Google Drive | **Partly** | Add your Google account in KDE's Online Accounts (hidden from the menu: run `spark-settings --kde kcm_kaccounts`, or press the button in Spark Files' Network group), and Drive appears in Spark Files' sidebar. Unlike the Windows client, it doesn't keep offline copies. For that, use rclone or a paid client such as Insync. Not yet tried with a real account. |
| Discord, Spotify | **Works** | Both install from the Store. |
| OBS Studio | **Works** | From the Store. |
| Blender, GIMP, Audacity | **Works** | From the Store. Blender renders on the RX 6800 XT through HIP. |
| Photos, Media Player | **Replaced** | **Spark Media** (in the image) opens photos, videos and music by default: double-click a file, or open it from the menu to browse Pictures, Videos and Music. H.264, H.265, AAC and MP3 play out of the box. Photos get rotate, crop and auto-enhance (saved as a copy), and the music library browses by artist, album and song, with covers, playlists and media keys, so Elisa isn't needed. For heavier photo work and photo catalogues, **GIMP** and **digiKam** are in the Store. |
| Clipchamp | **Replaced** | **Kdenlive** (from the Store). |
| Snipping Tool, QuickOCR | **Replaced** | **Spark Snip** (in the image): Print or Meta+Shift+S for a screenshot (the Annotate button adds arrows, boxes, text, step numbers, highlights, pixelate and crop before you copy or save), Meta+Shift+T to copy text off the screen (OCR, English and French), Meta+Shift+R to start and stop a recording. The keys match Snipping Tool and PowerToys Text Extractor, with Meta for the Windows key. |
| ShareX | **Replaced** | **Spark Snip** for snips, annotating (arrows, boxes, text, steps, pixelate, crop), text and recordings. **Flameshot** (from the Store) is optional, only if you want its upload to a site (Spark Snip uploads nothing). |
| Notepad, Notepad++ | **Replaced** | **Spark Edit** (in the image): tabs, find and replace, and unsaved tabs come back after a restart, like Notepad on Windows 11. |
| 7-Zip, WinRAR | **Replaced** | **Spark Archive** (in the image): zip, 7z, rar, tar and iso, with passwords. Extract and Compress are in Spark Files' right-click menu. |
| WinDirStat | **Replaced** | **Spark Space**, an optional Spark app: a map of what takes the space on each drive, and the trash for what you don't want. |
| HWiNFO, Task Manager | **Replaced** | **Spark Monitor** (in the image): Ctrl+Shift+Esc, as on Windows (Meta+Esc and Ctrl+Esc work too). For detailed sensor readings like HWiNFO, **Mission Center** is in the Store. |
| Ryzen Master | **No** | Set PBO and Curve Optimizer in the BIOS instead. They then apply to both systems. |
| Logitech G HUB, SignalRGB, 8BitDo, Focusrite Control | See Devices above | |
| Wallpaper Engine | **Partly** | A community KDE plugin plays many Wallpaper Engine scenes. It isn't in the image. |
| Tailscale | **Works** | Not in the image (it's a company's service). To add it, run `sudo curl -fsSLo /etc/yum.repos.d/tailscale.repo https://pkgs.tailscale.com/stable/fedora/tailscale.repo`, then `rpm-ostree install tailscale` and restart. Then `sudo systemctl enable --now tailscaled` and `sudo tailscale up` to sign in. It updates with SparkOS from then on. |
| hide.me VPN, Hotspot Shield | **Partly** | Both offer Linux command-line clients. Plain WireGuard and OpenVPN connections import in **Spark Settings**, Network. |
| TeamViewer | **Works** | Download the Linux .rpm from teamviewer.com and double-click it: SparkOS asks, installs it and offers a restart. |
| PuTTY | **Replaced** | `ssh` in **Spark Terminal** (in the image), or **Spark Connect**, an optional Spark app, for your own servers. |
| Phone Link | **Replaced** | **Spark Link** (in the image): links, files, notifications and the clipboard between your phone and this PC. |
| Calculator | **Replaced** | **Spark Calc** (in the image): standard, scientific and programmer. |
| VirtualBox | **Partly** | **Virtual Machine Manager** (virt-manager) with KVM is the replacement and runs VMs faster than VirtualBox. libvirt, QEMU, UEFI firmware and a TPM are in the image but off: run `spark virt setup` (password once, then log out and in), and install *Virtual Machine Manager* from the Store. It replaces Bazzite's `ujust setup-virtualization`. `spark virt` shows what is ready, `spark virt undo` turns it off again. Needs SVM Mode on in the BIOS (`spark virt` says if it isn't). Not tried on a booted SparkOS yet, and VirtualBox's own `.vdi` disks need converting (`qemu-img convert`). |
| MuseHub | **No** | Windows and Mac only. |

## Development

| Tool | On SparkOS | Notes |
|---|---|---|
| Git | **Works** | Built in. |
| Node.js, Python 3.13, GitHub CLI, JDK 17 | **Works** | Run `sparkos-dev-setup` once and Homebrew installs all four. The list is in `/usr/share/sparkos/Brewfile`. |
| VS Code | **Works** | In the image, as a Flatpak. For full access to system tools, open a terminal inside VS Code or use a Distrobox container. |
| Unity 6 and Unity Hub | **Works** (check) | **Unity Hub** (from the Store) is the community Flatpak. Unity also publishes an official Linux Hub. |
| Ollama | **Works** | Use the official Linux install or the **Alpaca** app (Flathub). The RX 6800 XT is supported by ROCm. |
| Claude Code | **Works** | Open **Claude Code** from the app menu, right-click a folder in Spark Files and choose **Open Claude Code here**, or run `sparkos-claude` in a terminal. The first start installs it with Anthropic's official installer (into `~/.local`, updates itself). Run `sparkos-claude-import` once to bring over your Windows `CLAUDE.md`, skills, agents and commands. See [claude-code.md](claude-code.md). |
| Claude desktop app (Chat, Cowork, Code tab) | **No** | Its Linux version is a beta for Ubuntu and Debian only. On SparkOS, use Claude Code (above), and claude.ai in the browser for chat. |
| Antigravity IDE | **Check** | Look for a Linux download. |
| Inno Setup (Windows installers for your apps) | **Partly** | Runs under Wine through Spark Run (double-click the .exe). For building and testing Windows releases, a Windows VM in virt-manager is the dependable choice. |
| Androidbox | **Works** (check) | Not preinstalled. SparkOS has everything it needs, so install it for your user (no admin password): download the latest release's source from github.com/Wolklaw/Androidbox/releases, unpack it, and run `bash packaging/linux/install.sh --user`. It then appears in the app menu. To update, do the same with a newer release. Android needs virtualization (KVM) turned on in the BIOS. The boot test installs and starts it this way on every build, but no Android has been run in it on SparkOS yet. The boss key and other shortcuts that work while another program is in front don't work on Linux. |
| Your own apps: Nova, BotWatch, Broke'nt, OSRS Toolkit, Upscape, Delta | **Check each** | They're Windows builds. Each needs a Linux build, as Soot and FreeSuite got, or runs in the Windows VM. |

## Faster than Windows 11?

Honest answer: for most of what you do, it should be at least as fast, but some things can be slower, and it gets measured rather than assumed (Phase 5 in PLAN.md).
- **Usually as fast or faster:** boot to desktop, the desktop itself, file operations, and many games on an AMD GPU. Current Mesa drivers do well on AMD GPUs, and Windows background services are gone.
- **Can be slower:** some DirectX 12 games under Proton run a few percent behind Windows. The first run of a game can stutter while shaders compile, and it settles after that.
- **The measurement:** the same games at the same settings and resolution on both systems. Linux is logged with MangoHud and Windows with PresentMon, and **Spark Bench** (an optional Spark app) reads both and compares average FPS and 1% lows. Boot time is timed on both. Results go into `docs/benchmarks.md`.

## The switch, step by step

1. Check the **Check** items above, especially the games you play most.
2. Install SparkOS alongside Windows: step by step in [install.md](install.md) (Phase 5 in PLAN.md). Windows stays until SparkOS has covered a normal week of work and games.
3. On SparkOS, open **Spark Welcome** and go through **Move from Windows**: copy your files and fonts, see what to use for each program, and add your Steam library folders in Steam. Sign in to Epic, GOG and Amazon in Spark Games, and to Bolt and Prism. Add your Google account. Run `sparkos-dev-setup`. Print and scan one page.
4. Before you erase Windows, go through the checklist at the end of Move from Windows: passwords and bookmarks, OneDrive files, game saves, licences, two-step codes, the Wi-Fi password, BitLocker and Fast Startup.
5. Keep Windows (on a smaller partition, or as a VM) for anything marked **No** that you still need.
