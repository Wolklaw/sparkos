"""Every sentence Spark Welcome shows, in English and in French.

The PC's language picks the table (lang.py: LC_ALL, LC_MESSAGES or LANG starting with "fr",
or SPARK_LANG=fr). The app list's French is in apps.json (name_fr, by_fr, blurb_fr)."""

from typing import Dict

from .lang import ui_language

EN: Dict[str, str] = {
    # frame
    'status.ready': "READY",
    'status.error': "SOMETHING WENT WRONG",
    'status.opened': "OPENED",
    'status.cant_open': "COULDN'T OPEN IT. IS IT INSTALLED?",
    'status.installed': "{name} INSTALLED",
    'status.failed': "{name} DIDN'T INSTALL",
    'error.unexpected': "Unexpected error:\n{error}",
    'nav.steps': "STEPS",
    'nav.welcome': "WELCOME",
    'nav.games': "GAMES",
    'nav.apps': "APPS",
    'nav.checks': "CHECK THIS PC",
    'nav.done': "DONE",
    'nav.next': "Next",
    'nav.back': "Back",
    'nav.close': "Close",
    'nav.note': "Every step is optional. Nothing installs until you click Install.",
    'work.installing': "INSTALLING {name}{pct}  ·  {n} OF {total}",
    'work.starting': "STARTING THE INSTALL…",
    'work.done': "INSTALLS FINISHED ({total})",
    'work.done_failed': "{failed} OF {total} INSTALLS FAILED. SEE GAMES AND APPS.",
    'close.installing': "Apps are still installing. Close anyway and stop them?",

    # 1. welcome
    'welcome.title': "Welcome to SparkOS",
    'welcome.intro': "SparkOS is a Linux system for gaming and everyday use, built on Fedora. "
                     "It updates itself in the background and keeps the system "
                     "files read-only, so an update or an app can't break it.",
    'welcome.how': "How this works",
    'welcome.skip': "Each page can be skipped. Nothing is installed or copied until you click "
                    "a button, and you can close this window at any time. Spark Welcome stays "
                    "in the app menu if you want it later.",

    # 2. games
    'games.title': "Games",
    'games.anticheat.label': "What doesn't work",
    'games.anticheat': "Games with kernel-level anti-cheat don't run on Linux, whatever the "
                       "launcher: Valorant, Fortnite, and some Call of Duty and EA games, among "
                       "others. That's the game maker's choice, not something SparkOS can fix. "
                       "Check a game before you buy it.",
    'games.anticheat.button': "Open areweanticheatyet.com",

    # 3. apps
    'apps.title': "Apps",
    'apps.by': "by {who}",
    'apps.install': "Install ticked ({n})",
    'apps.install_none': "Install ticked",
    'apps.retry': "Retry",
    'apps.store': "Find more in the Store",
    'apps.flathub': "These come from Flathub, the same place the Store installs from. They "
                    "update with the rest of your apps.",
    'apps.state.installed': "INSTALLED",
    'apps.state.queued': "WAITING",
    'apps.state.installing': "INSTALLING",
    'apps.state.failed': "FAILED",
    'apps.state.stopped': "STOPPED",
    'flatpak.no_reason': "flatpak stopped without saying why.",
    'web.comment': "{name}'s web player, in your browser",
    'web.bad_address': "This web app's address isn't a safe https address, so it wasn't added.",
    'flatpak.remote_failed': "Couldn't add Flathub: {error}",
    'flatpak.cant_run': "Can't run flatpak: {error}",
    'flatpak.stopped': "Stopped when the window closed.",

    # 4. files from Windows
    'win.safe': "It copies and never moves. The Windows drive is opened read-only, so nothing "
                "on it changes. Files that are already here with the same size are skipped. "
                "Opening the drive may ask for your password.",
    'win.scan': "Look again",
    'win.scanning': "Looking for Windows drives…",
    'win.lsblk_failed': "Couldn't list the drives: {error}",
    'win.none': "No Windows drive found. If Windows is on this PC, its drive may be "
                "encrypted with BitLocker, or on a disk that isn't connected.",
    'win.drives': "Windows drives",
    'win.locked': "LOCKED (BITLOCKER)",
    'win.open': "Open read-only",
    'win.mounting': "Opening {name} read-only. If a password window appears, it's the "
                    "system asking for your password…",
    'win.no_users': "No Windows user folders with files in them on this drive ({where}).",
    'win.account': "Windows account",
    'win.measuring': "measuring…",
    'win.size': "{size} · {files} files",
    'win.size.one': "{size} · 1 file",
    'win.copy': "Copy ticked",
    'win.cancel': "Stop",
    'win.tick_one': "TICK A FOLDER FIRST",
    'win.planning': "WORKING OUT WHAT TO COPY…",
    'win.copying': "COPYING {name}  ·  {done} OF {total}",
    'win.copy_failed': "The copy stopped: {error}",
    'win.no_space': "Nothing was copied: the ticked folders need {need} and SparkOS's disk "
                    "has {free} free (2 GB stays free so the system keeps working). Untick "
                    "the biggest folder and try again.",
    'win.done': "Copy finished",
    'win.done.cancelled': "Copy stopped",
    'win.done.copied': "Copied {n} files ({size}).",
    'win.done.skipped': "Skipped {n} already here with the same size.",
    'win.done.renamed': "{n} had the same name as a different file here and were saved as "
                        "\"name (from Windows)\".",
    'win.done.failed': "{n} couldn't be copied:",
    'win.renamed': "from Windows",
    'win.done.more': "…and {n} more. The full list is in the log.",
    'win.err.hibernated': "Windows didn't shut down fully (Fast Startup or hibernation), so "
                          "the drive is locked. Start Windows, turn off Fast Startup in Power "
                          "Options, shut down, and try again.",
    'win.err.password': "Opening the drive needs your password, and it wasn't given.",
    'win.err.bitlocker': "This drive is encrypted with BitLocker. SparkOS can't read it.",
    'win.err.generic': "The drive couldn't be opened.",

    # 5. checks
    'checks.title': "Check this PC",
    'checks.intro': "A quick look at the parts people usually worry about. It only reads; "
                    "nothing is changed.",
    'checks.again': "Check again",
    'checks.checking': "checking…",
    'checks.ok': "OK",
    'checks.look': "HAVE A LOOK",
    'check.crashed': "This check stopped with an error.",
    'check.graphics': "Graphics",
    'check.graphics.ok': "{gpu}. Driver: {driver}. Vulkan works.",
    'check.graphics.ok.detail': "Games use Vulkan, directly or through Proton. The driver "
                                "is part of SparkOS and updates with it.",
    'check.graphics.novk': "Graphics card found: {cards}. Vulkan wasn't tested "
                           "(vulkaninfo isn't installed).",
    'check.graphics.novk.detail': "The card has a driver. Without vulkaninfo this check can't "
                                  "tell whether Vulkan works.",
    'check.graphics.vkfail': "Graphics card found: {cards}, but no Vulkan device.",
    'check.graphics.vkfail.detail': "Vulkan only found a software renderer, so games would "
                                    "run on the processor. This can happen in a virtual "
                                    "machine, or when the card's driver didn't load.",
    'check.graphics.vkerror.detail': "vulkaninfo failed, so Vulkan may not work. Games need "
                                     "it. Restarting after an update often fixes this.",
    'check.graphics.none': "No graphics driver found.",
    'check.graphics.none.detail': "The system sees no graphics card with a driver loaded. "
                                  "In a virtual machine this is normal.",
    'check.sound': "Sound",
    'check.sound.ok': "Sound goes to {device}.",
    'check.sound.ok.detail': "{count} output device(s). Play the test sound to hear it.",
    'check.sound.none': "No sound output found.",
    'check.sound.none.detail': "Plug in speakers or headphones, or turn on the screen if it "
                               "carries the sound, then check again.",
    'check.sound.nowpctl': "Couldn't check: wpctl isn't installed.",
    'check.sound.error': "Couldn't ask the sound system.",
    'check.printers': "Printers and scanners",
    'check.printers.ok': "Printer ready: {names}.",
    'check.printers.none': "No printer set up yet.",
    'check.printers.none.detail': "Most recent network printers, Canon included, work with "
                                  "no driver: turn the printer on, connect it to the same "
                                  "network, then Add a printer.",
    'check.scanners.found': "Scanner found: {names}.",
    'check.scanners.none': "No scanner found.",
    'check.scanners.missing': "Scanners weren't checked (scanimage isn't installed).",
    'check.network': "Network and Bluetooth",
    'check.network.ok': "Connected by {how}: {name}.",
    'check.network.wifi': "Wi-Fi",
    'check.network.wired': "cable",
    'check.network.none': "Not connected to a network.",
    'check.network.none.detail': "Installing apps needs the internet.",
    'check.network.nonmcli': "Couldn't check the network: nmcli isn't installed.",
    'check.bt.on': "Bluetooth is on.",
    'check.bt.off': "Bluetooth is off.",
    'check.bt.none': "No Bluetooth on this PC.",
    'check.updates': "Updates",
    'check.updates.ok': "This system was built on {date} ({image}).",
    'check.updates.auto': "SparkOS updates itself in the background and switches to the new "
                          "version when you restart. Your apps from the Store update the "
                          "same way.",
    'check.updates.staged': "An update is downloaded and ready: restart to use it.",
    'check.updates.noostree': "Not an image-based SparkOS install.",
    'check.updates.noostree.detail': "rpm-ostree isn't here, so this check can't say how "
                                     "updates work on this system.",
    'check.updates.error': "Couldn't read the update status.",
    'fix.test_sound': "Play test sound",
    'fix.sound_settings': "Sound settings",
    'fix.add_printer': "Add a printer",
    'fix.network_settings': "Network settings",
    'fix.bluetooth_settings': "Bluetooth settings",

    # 6. done
    'done.title': "You're set",
    'done.store.title': "Installing apps",
    'done.store.button': "Open the Store",
    'done.settings.title': "Settings",
    'done.settings.button': "Open Settings",
    'done.show_again': "Show Spark Welcome at login",
    'done.menu': "{name} stays in the app menu.",
    'done.still_installing': "Apps are still installing. Leave this window open until they "
                             "finish; closing it stops them.",

    # moving from Windows (1.1)
    'open': "Open",
    'nav.windows': "YOUR FILES",
    'welcome.swaps': "What you used on Windows, and what does it here",
    'welcome.swaps.intro': "These are already on this PC. Open shows the app.",
    'welcome.instead': "Instead of {win}",
    'swap.browser.win': "Chrome, Edge or Firefox",
    'swap.browser.what': "Web browser. Sign in to your Google, Microsoft or Firefox account in "
                         "it to bring your bookmarks and passwords.",
    'swap.office.win': "Microsoft Office, Outlook and Adobe Reader",
    'swap.office.what': "Mail, calendar, documents, spreadsheets, presentations and PDF. Opens "
                        "and saves Word, Excel and PowerPoint files.",
    'swap.files.win': "File Explorer",
    'swap.files.what': "Your folders, drives and the trash. Extract and Compress are in the "
                       "right-click menu.",
    'swap.launcher.win': "the Start menu",
    'swap.launcher.what': "Press the Windows key (Meta) and type to find an app, a file or a "
                          "setting.",
    'swap.settings.win': "Windows Settings and the Control Panel",
    'swap.settings.what': "Displays, sound, network, Bluetooth, power, default apps, language, "
                          "printers and startup apps.",
    'swap.store.win': "the Microsoft Store and installers from websites",
    'swap.store.what': "Apps from Flathub and the optional Spark apps, installed in one click "
                       "and updated by themselves.",
    'swap.update.win': "Windows Update",
    'swap.update.what': "Gets the new version ready in the background and starts it at the "
                        "next restart. If something goes wrong, go back to the previous one.",
    'swap.monitor.win': "Task Manager",
    'swap.monitor.what': "What's running, End task and live graphs. Ctrl+Shift+Esc opens it, "
                         "as on Windows.",
    'swap.games.win': "Steam, Epic, GOG, Battle.net, EA and Ubisoft launchers",
    'swap.games.what': "All your games in one library. Signs in to Epic, GOG and Amazon "
                       "itself, and adds the other launchers for you.",
    'swap.run.win': "Windows programs (.exe and .msi)",
    'swap.run.what': "Runs Windows programs on Wine, or installs them as apps with their own "
                     "menu entry. Double-click a .exe to start.",
    'swap.snip.win': "the Snipping Tool and Xbox Game Bar recording",
    'swap.snip.what': "Print Screen or Meta+Shift+S for a screenshot, Meta+Shift+R to record "
                      "the screen, Meta+Shift+T to copy text from the screen.",
    'swap.media.win': "Photos, Media Player and VLC",
    'swap.media.what': "Photos, videos and music.",
    'swap.edit.win': "Notepad and Notepad++",
    'swap.edit.what': "Text and code editor.",
    'swap.calc.win': "Calculator",
    'swap.calc.what': "Standard, scientific and programmer.",
    'swap.archive.win': "7-Zip and WinRAR",
    'swap.archive.what': "zip, 7z, tar, rar and iso.",
    'swap.terminal.win': "Command Prompt, PowerShell and Windows Terminal",
    'swap.terminal.what': "Terminal. Ctrl+C and Ctrl+V copy and paste, as on Windows.",
    'swap.scan.win': "Windows Scan",
    'swap.scan.what': "Scans to PDF, with text you can search.",
    'swap.link.win': "Phone Link",
    'swap.link.what': "Links, files, notifications and the clipboard between your phone and "
                      "this PC. Pairs with Soot on Android.",
    'swap.controller.win': "Armoury Crate, iCUE-style RGB tools and fan control",
    'swap.controller.what': "Fans, RGB lighting and firmware updates for this PC.",
    'games.intro': "Spark Games is your game library on SparkOS. Steam is the one launcher you "
                   "install yourself.",
    'games.spark': "One library for Steam, Epic, GOG and Amazon games, with covers, play time "
                   "and a Play button. Sign in to Epic, GOG and Amazon inside Spark Games: no "
                   "other launcher needed.",
    'games.spark.stores': "Battle.net, the EA app, Ubisoft Connect and Rockstar are added from "
                          "Spark Games too: it installs each one on Wine and lists its games.",
    'games.open': "Open Spark Games",
    'games.launchers': "Install Steam",
    'games.steam_move': "Steam games on the Windows drive don't have to download again: the "
                        "Move from Windows page shows them and how to copy them.",
    'games.later': "Other launchers, like Minecraft's, are in Spark Games and the Store.",
    'apps.intro': "SparkOS apps first, then apps from other companies for what SparkOS doesn't "
                  "do itself. Nothing is ticked: pick what you use.",
    'apps.spark': "Spark apps you can add",
    'apps.spark.intro': "Made for SparkOS and already on this PC, not installed yet. They "
                        "install for your account, no download.",
    'apps.instead': "Instead of {win}",
    'optional.spark-space.win': "WinDirStat, TreeSize or WizTree",
    'optional.spark-bench.win': "CapFrameX or PresentMon",
    'optional.spark-connect.win': "Remote Desktop and PuTTY, for your own PCs and servers",
    'apps.others': "Apps from other companies",
    'apps.others.intro': "For chat, music, streaming and creative work. Each one says whose "
                         "app it is.",
    'win.title': "Your files",
    'win.intro': "Your drives are open, but your Desktop, Documents, Pictures and other "
                 "folders are still on the Windows drive (C:). Copy them here before you "
                 "erase it. This step also lists the programs you had, with what to use for "
                 "each one here, and the Steam games you can copy instead of downloading.",
    'win.programs': "Your Windows programs",
    'win.programs.intro': "Found on the Windows drive, with what to use here.",
    'win.others': "{n} other programs have no answer here. Look for them in the Store; many "
                  "Windows programs also run with Spark Run.",
    'win.others.show': "Show their names",
    'prog.spark': "Use {name}. It's already on this PC.",
    'prog.games': "Spark Games signs in to it or adds it for you.",
    'prog.app': "Install {name} for Linux.",
    'prog.optional': "Install {name}, made for SparkOS.",
    'prog.store': "Look for it in the Store.",
    'prog.install': "Install",
    'prog.queued': "Queued",
    'prog.anticheat': "Uses kernel-level anti-cheat: these games don't run on Linux.",
    'prog.onedrive': "No OneDrive app for Linux. Use onedrive.com in Soot. Before you erase "
                     "Windows, make sure your files are really on this drive or online (see "
                     "below).",
    'prog.cloud': "No app for Linux from this company. Use its website in Soot.",
    'prog.teams': "Use teams.microsoft.com in Soot.",
    'prog.drivers': "Not needed: the graphics drivers come with SparkOS and update with it.",
    'prog.peripherals': "No Linux version. Mouse and keyboard settings are in Spark Settings; "
                        "lighting and fans in Spark Controller.",
    'win.steam': "Steam games on the Windows drive",
    'win.steam.found': "{n} games are on this drive. Copying is faster than downloading them "
                       "again.",
    'win.steam.none': "Steam is on the Windows drive, but no games were found in its libraries "
                      "on this drive. Libraries on other drives are listed here.",
    'win.steam.more': "and {n} more",
    'win.steam.open': "Open folder",
    'win.steam.how': "For each game: in Steam here, start installing it, then pause the "
                     "download. Copy the game's folder from the Windows drive into {common}, "
                     "then resume. Steam checks the files and only downloads what's missing.",
    'win.before': "Before you erase Windows",
    'win.before.intro': "Copying folders doesn't bring everything. Check these while Windows "
                        "still works.",
    'win.before.1.title': "Passwords and bookmarks",
    'win.before.1': "They're encrypted on the Windows drive and can't be copied. Sign in to "
                    "your browser's account and turn on sync, or export the passwords from the "
                    "browser's settings, then import them in Soot.",
    'win.before.2.title': "OneDrive files",
    'win.before.2': "Files with a cloud icon are only online. Right-click the OneDrive folder "
                    "and pick Always keep on this device before you copy, or download them "
                    "later from onedrive.com.",
    'win.before.3.title': "Game saves",
    'win.before.3': "Most launchers sync saves online. Games that don't keep them in "
                    "Documents\\My Games, Saved Games or AppData: copy those folders too.",
    'win.before.4.title': "Licences",
    'win.before.4': "Write down the keys of programs you paid for, and sign out of apps that "
                    "only allow a few devices, like Adobe or Office.",
    'win.before.5.title': "Two-step codes",
    'win.before.5': "If an authenticator app or security key is set up on Windows, move it to "
                    "your phone first, or you could lock yourself out.",
    'win.before.6.title': "Wi-Fi password",
    'win.before.6': "Note it, or find it on your router.",
    'win.before.7.title': "BitLocker",
    'win.before.7': "A locked drive can't be opened here. Turn BitLocker off in Windows, or "
                    "note the recovery key from account.microsoft.com.",
    'win.before.8.title': "Fast Startup",
    'win.before.8': "Turn it off in Windows' power options. Windows otherwise keeps its drive "
                    "half-closed, and it can only be opened read-only here.",
    'win.before.9.title': "Keep Windows a little longer",
    'win.before.9': "Use SparkOS for a normal week first. Once nothing is missing, Windows can "
                    "go.",
    'done.intro': "Three things worth knowing.",
    'done.store': "Apps install from the Store with one click and update by themselves. "
                  "Double-click a downloaded .exe, .AppImage or .rpm: SparkOS says what it can "
                  "do with it, and Spark Run opens Windows programs.",
    'done.keys.title': "Windows keys that still work",
    'done.keys': "Windows key: Spark Launcher. Ctrl+Shift+Esc: Spark Monitor. Print Screen or "
                 "Meta+Shift+S: Spark Snip. Ctrl+C, Ctrl+V and Alt+Tab work as usual.",
    'done.settings': "Display, sound, network, Bluetooth, printers and the rest are in Spark "
                     "Settings.",

    # the guide (1.2)
    'nav.step': "Step {n} of {total}",
    'nav.next_to': "Next: {step}",
    'step.todo': "What to do here",
    'nav.different': "WHAT'S DIFFERENT",
    'nav.familiar': "WHAT'S THE SAME",
    'nav.drives': "YOUR DRIVES",
    'nav.erase': "ERASING WINDOWS",
    'welcome.guide': "This guide takes you through it one step at a time: what changes from "
                     "Windows, what doesn't, getting your drives and files here, and what to "
                     "check before you erase Windows.",
    'welcome.steps': "The steps",
    'welcome.start': "Start",
    'welcome.step.different': "Apps, updates and drives work differently here.",
    'welcome.step.familiar': "The taskbar, windows, folders and keyboard shortcuts you know.",
    'welcome.step.drives': "Make sure each drive with your files opens at every start.",
    'welcome.step.windows': "Copy your folders from the Windows drive.",
    'welcome.step.games': "Install Steam and the other game launchers.",
    'welcome.step.apps': "Install the apps you use.",
    'welcome.step.checks': "Graphics, sound, printers, network and updates.",
    'welcome.step.erase': "What to check before you erase Windows, and how.",
    'welcome.step.done': "Where to find things later.",

    'diff.title': "What's different",
    'diff.intro': "SparkOS is not Windows. These are the changes you will notice first.",
    'diff.todo': "Read the cards. Nothing to set up here.",
    'diff.store.title': "Apps come from the Store",
    'diff.store': "Instead of downloading installers from websites, install apps from the "
                  "Store. One click installs them, and they update by themselves. Spark Run "
                  "can open a downloaded .exe, but not every Windows program works.",
    'diff.store.button': "Open the Store",
    'diff.games.title': "Windows games run through Proton",
    'diff.games': "Steam and the other launchers run Windows games through Proton. Most "
                  "games work. Games with kernel-level anti-cheat don't; the Games step "
                  "says more.",
    'diff.update.title': "Updates replace the whole system",
    'diff.update': "SparkOS downloads the next version in the background and switches to it "
                   "when you restart. If something is wrong after an update, the previous "
                   "version is still in the startup menu: pick it there.",
    'diff.letters.title': "No drive letters",
    'diff.letters': "Everything is in one tree of folders. Your files are in your home "
                    "folder. Windows drives open as folders: C: is /var/mnt/c, D: is "
                    "/var/mnt/d. Spark Files lists your drives on the left.",
    'diff.password.title': "Your password instead of Yes / No",
    'diff.password': "Where Windows asks \"Do you want to allow this app to make changes?\", "
                     "SparkOS asks for your password, for example when you add a drive or "
                     "change a system setting.",
    'diff.sandbox.title': "The system can't be changed by accident",
    'diff.sandbox': "System files are read-only, and Store apps only see what they need. "
                    "Programs made for Windows, viruses included, don't run here on their own.",
    'diff.case.title': "Capital letters count in names",
    'diff.case': "Photo.jpg and photo.jpg can be two different files here.",

    'same.title': "What's the same",
    'same.intro': "Most of what you do every day works the way it did on Windows.",
    'same.todo': "Read the cards and try a few shortcuts. Nothing to set up here.",
    'same.taskbar.title': "The taskbar",
    'same.taskbar': "Along the bottom: the SPARK button opens the app menu (the Windows key "
                    "does too), then your pinned and open apps, then the clock, tray icons and "
                    "notifications on the right.",
    'same.windows.title': "Windows",
    'same.windows': "Minimize, maximize and close are at the top right of each window. "
                    "Windows key + arrows snap and maximize, as on Windows.",
    'same.files.title': "Your folders",
    'same.files': "Your home folder has Desktop, Documents, Downloads, Music, Pictures and "
                  "Videos. Spark Files works like File Explorer: right-click, drag and drop, "
                  "and a trash you can empty.",
    'same.mouse.title': "Keyboard and mouse",
    'same.mouse': "Ctrl+C, Ctrl+V, Ctrl+Z and the other Ctrl shortcuts work as usual. "
                  "Right-click opens a menu almost everywhere.",
    'same.keys': "Keyboard shortcuts",
    'key.menu': "Windows key",
    'key.menu.what': "Open the app menu",
    'key.switch': "Alt+Tab",
    'key.switch.what': "Switch windows",
    'key.close': "Alt+F4",
    'key.close.what': "Close the window",
    'key.snap': "Win+Left / Right",
    'key.snap.what': "Snap to half the screen. Win+Up maximizes, Win+Down restores.",
    'key.desktop': "Win+D",
    'key.desktop.what': "Show the desktop",
    'key.lock': "Win+L",
    'key.lock.what': "Lock the screen",
    'key.files': "Win+E",
    'key.files.what': "Open Spark Files",
    'key.settings': "Win+I",
    'key.settings.what': "Open Spark Settings",
    'key.monitor': "Ctrl+Shift+Esc",
    'key.monitor.what': "Open Spark Monitor (the Task Manager)",
    'key.snip': "Print Screen, Win+Shift+S",
    'key.snip.what': "Take a screenshot with Spark Snip",
    'key.clipboard': "Win+V",
    'key.clipboard.what': "Clipboard history",
    'key.emoji': "Win+.",
    'key.emoji.what': "Emoji",
    'key.terminal': "Ctrl+Alt+T",
    'key.terminal.what': "Open a terminal",
    'key.copy': "Ctrl+C / Ctrl+V / Ctrl+Z",
    'key.copy.what': "Copy, paste, undo",

    'drives.title': "Your drives",
    'drives.intro': "Each drive with your files on it should open by itself at every start, "
                    "so your games and files are there without Windows.",
    'drives.todo': "Check that each Windows drive below opens: click Open and look for your "
                   "files. If drives are listed under Other drives, tick them and click Add "
                   "ticked so they open at every start too.",
    'drives.win': "Windows drives",
    'drives.win.no_report': "SparkOS hasn't reported its Windows drives yet. Restart the PC, "
                            "then open this step again.",
    'drives.win.none': "No Windows drive found on this PC.",
    'drives.rw': "READ-WRITE",
    'drives.ro': "READ-ONLY",
    'drives.off': "NOT OPEN",
    'drives.win.locked': "Locked with BitLocker, so SparkOS can't read it. Turn BitLocker off "
                         "for this drive in Windows, then restart into SparkOS.",
    'drives.win.hibernated': "Windows didn't shut down fully, so this drive is read-only. "
                             "Start Windows, turn off Fast Startup in the power options, "
                             "shut down, then start SparkOS.",
    'drives.win.ro_choice': "Read-only on purpose. To write to it, change the line "
                            "\"{letter} ro\" to \"{letter} rw\" in {conf} and restart.",
    'drives.win.problem': "SparkOS says: {problem}",
    'drives.win.keep': "These drives keep their letter and their folder after you erase "
                       "Windows.",
    'drives.other': "Other drives",
    'drives.other.intro': "Drives with files that SparkOS doesn't open by itself yet. Adding "
                          "one opens it now and at every start, in the folder shown. Nothing "
                          "on it is changed or erased. SparkOS asks for your password.",
    'drives.other.none': "No other drives. USB drives and SD cards open by themselves when "
                         "you plug them in.",
    'drives.looking': "Looking for drives…",
    'drives.lsblk_failed': "Couldn't list the drives: {error}",
    'drives.added': "ADDED",
    'drives.add': "Add ticked ({n})",
    'drives.add_none': "Add ticked",
    'drives.again': "Look again",
    'drives.adding': "Adding. If a password window appears, it's SparkOS asking to change "
                     "its list of drives.",
    'drives.added_at': "{name} opens at {where}, now and at every start.",
    'drives.err.password': "Adding a drive needs your password, and it wasn't given.",
    'drives.err.damaged': "The drive's file system looks damaged, so it can't be opened.",
    'drives.err.generic': "The drive couldn't be added.",
    'drives.not_writable': "It opened, but you can't write to it: its files belong to "
                           "another user.",
    'drives.added_next_start': "It's added, but couldn't be opened now. It opens at the next "
                               "start.",

    'win.todo': "Pick the Windows drive, tick the folders you want, then click Copy ticked. "
                "Your other drives (D:, E: and so on) don't need copying: they stay after "
                "Windows is erased.",

    'erase.title': "Before you erase Windows",
    'erase.intro': "Once everything you need is here, the Windows partition can be erased "
                   "to free its space. Spark Welcome never erases anything itself.",
    'erase.todo': "Go through the list while Windows still starts. When nothing is missing, "
                  "erase the Windows partition in Spark Disks.",
    'erase.drives': "What stays and what goes",
    'erase.drives.unknown': "SparkOS hasn't reported its Windows drives, so this can't say "
                            "which ones stay.",
    'erase.c.title': "C: goes",
    'erase.c': "Erasing Windows means erasing C:. Anything on it that you haven't copied in "
               "step 5 is lost.",
    'erase.stay.title': "These drives stay",
    'erase.stay': "They are separate from Windows and keep their letter and folder:\n{drives}",
    'erase.how': "Erasing the Windows partition",
    'erase.how.title': "In Spark Disks",
    'erase.how.text': "Pick the Windows partition (C:, NTFS), choose Delete, and type the "
                      "device name it shows to confirm. Spark Disks closes the partition "
                      "first. The freed space can then hold a new partition for files.",
    'erase.disks': "Open Spark Disks",
    'erase.efi.title': "Leave the small partitions alone",
    'erase.efi': "Delete only the Windows partition. The small EFI partition is what the PC "
                 "starts from, and SparkOS may use it too.",
}

FR: Dict[str, str] = {
    # frame
    'status.ready': "PRÊT",
    'status.error': "UN PROBLÈME EST SURVENU",
    'status.opened': "OUVERT",
    'status.cant_open': "IMPOSSIBLE DE L'OUVRIR. EST-IL INSTALLÉ?",
    'status.installed': "{name} INSTALLÉ",
    'status.failed': "{name} NE S'EST PAS INSTALLÉ",
    'error.unexpected': "Erreur inattendue :\n{error}",
    'nav.steps': "ÉTAPES",
    'nav.welcome': "BIENVENUE",
    'nav.games': "JEUX",
    'nav.apps': "APPLICATIONS",
    'nav.checks': "VÉRIFIER CE PC",
    'nav.done': "TERMINÉ",
    'nav.next': "Suivant",
    'nav.back': "Retour",
    'nav.close': "Fermer",
    'nav.note': "Chaque étape est facultative. Rien ne s'installe avant que vous cliquiez sur "
                "Installer.",
    'work.installing': "INSTALLATION DE {name}{pct}  ·  {n} SUR {total}",
    'work.starting': "DÉBUT DE L'INSTALLATION…",
    'work.done': "INSTALLATIONS TERMINÉES ({total})",
    'work.done_failed': "{failed} INSTALLATIONS SUR {total} ONT ÉCHOUÉ. VOYEZ JEUX ET "
                        "APPLICATIONS.",
    'close.installing': "Des applications s'installent encore. Fermer quand même et les "
                        "arrêter?",

    # 1. welcome
    'welcome.title': "Bienvenue dans SparkOS",
    'welcome.intro': "SparkOS est un système Linux pour les jeux et l'usage de tous les jours, "
                     "construit sur Fedora. Il se met à jour en arrière-plan et "
                     "garde les fichiers du système en lecture seule, alors une mise à jour ou "
                     "une application ne peut pas le briser.",
    'welcome.how': "Comment ça marche",
    'welcome.skip': "Chaque page peut être sautée. Rien n'est installé ni copié avant que vous "
                    "cliquiez sur un bouton, et vous pouvez fermer cette fenêtre en tout temps. "
                    "Spark Welcome reste dans le menu des applications si vous en avez besoin "
                    "plus tard.",

    # 2. games
    'games.title': "Jeux",
    'games.anticheat.label': "Ce qui ne fonctionne pas",
    'games.anticheat': "Les jeux avec un anti-triche au niveau du noyau ne tournent pas sous "
                       "Linux, peu importe le lanceur : Valorant, Fortnite, et certains jeux "
                       "Call of Duty et EA, entre autres. C'est le choix de l'éditeur du jeu, "
                       "pas quelque chose que SparkOS peut régler. Vérifiez un jeu avant de "
                       "l'acheter.",
    'games.anticheat.button': "Ouvrir areweanticheatyet.com",

    # 3. apps
    'apps.title': "Applications",
    'apps.by': "par {who}",
    'apps.install': "Installer la sélection ({n})",
    'apps.install_none': "Installer la sélection",
    'apps.retry': "Réessayer",
    'apps.store': "En trouver d'autres dans le magasin",
    'apps.flathub': "Elles viennent de Flathub, la même source que le magasin. Elles se "
                    "mettent à jour avec le reste de vos applications.",
    'apps.state.installed': "INSTALLÉE",
    'apps.state.queued': "EN ATTENTE",
    'apps.state.installing': "INSTALLATION",
    'apps.state.failed': "ÉCHEC",
    'apps.state.stopped': "ARRÊTÉE",
    'flatpak.no_reason': "flatpak s'est arrêté sans dire pourquoi.",
    'web.comment': "Le lecteur web de {name}, dans votre navigateur",
    'web.bad_address': "L'adresse de cette appli web n'est pas une adresse https sûre : elle "
                       "n'a pas été ajoutée.",
    'flatpak.remote_failed': "Impossible d'ajouter Flathub : {error}",
    'flatpak.cant_run': "Impossible de lancer flatpak : {error}",
    'flatpak.stopped': "Arrêté à la fermeture de la fenêtre.",

    # 4. files from Windows
    'win.safe': "Il copie et ne déplace jamais rien. Le disque Windows est ouvert en lecture "
                "seule, alors rien n'y change. Les fichiers déjà ici avec la même taille sont "
                "sautés. Ouvrir le disque peut demander votre mot de passe.",
    'win.scan': "Chercher de nouveau",
    'win.scanning': "Recherche des disques Windows…",
    'win.lsblk_failed': "Impossible de lister les disques : {error}",
    'win.none': "Aucun disque Windows trouvé. Si Windows est sur ce PC, son disque est "
                "peut-être chiffré avec BitLocker, ou sur un disque qui n'est pas branché.",
    'win.drives': "Disques Windows",
    'win.locked': "VERROUILLÉ (BITLOCKER)",
    'win.open': "Ouvrir en lecture seule",
    'win.mounting': "Ouverture de {name} en lecture seule. Si une fenêtre de mot de passe "
                    "apparaît, c'est le système qui demande votre mot de passe…",
    'win.no_users': "Aucun dossier d'utilisateur Windows avec des fichiers sur ce disque "
                    "({where}).",
    'win.account': "Compte Windows",
    'win.measuring': "calcul de la taille…",
    'win.size': "{size} · {files} fichiers",
    'win.size.one': "{size} · 1 fichier",
    'win.copy': "Copier la sélection",
    'win.cancel': "Arrêter",
    'win.tick_one': "COCHEZ D'ABORD UN DOSSIER",
    'win.planning': "PRÉPARATION DE LA COPIE…",
    'win.copying': "COPIE DE {name}  ·  {done} SUR {total}",
    'win.copy_failed': "La copie s'est arrêtée : {error}",
    'win.no_space': "Rien n'a été copié : les dossiers cochés demandent {need} et le disque "
                    "de SparkOS a {free} de libre (2 Go restent libres pour que le système "
                    "fonctionne). Décochez le plus gros dossier et réessayez.",
    'win.done': "Copie terminée",
    'win.done.cancelled': "Copie arrêtée",
    'win.done.copied': "{n} fichiers copiés ({size}).",
    'win.done.skipped': "{n} sautés, déjà ici avec la même taille.",
    'win.done.renamed': "{n} avaient le même nom qu'un autre fichier ici et ont été enregistrés "
                        "comme « nom (de Windows) ».",
    'win.done.failed': "{n} n'ont pas pu être copiés :",
    'win.renamed': "de Windows",
    'win.done.more': "…et {n} autres. La liste complète est dans le journal.",
    'win.err.hibernated': "Windows ne s'est pas complètement éteint (démarrage rapide ou "
                          "veille prolongée), alors le disque est verrouillé. Démarrez Windows, "
                          "désactivez le démarrage rapide dans les Options d'alimentation, "
                          "éteignez, puis réessayez.",
    'win.err.password': "Ouvrir le disque demande votre mot de passe, et il n'a pas été donné.",
    'win.err.bitlocker': "Ce disque est chiffré avec BitLocker. SparkOS ne peut pas le lire.",
    'win.err.generic': "Le disque n'a pas pu être ouvert.",

    # 5. checks
    'checks.title': "Vérifier ce PC",
    'checks.intro': "Un coup d'œil rapide aux parties qui inquiètent souvent. Il ne fait que "
                    "lire; rien n'est modifié.",
    'checks.again': "Vérifier de nouveau",
    'checks.checking': "vérification…",
    'checks.ok': "OK",
    'checks.look': "À VÉRIFIER",
    'check.crashed': "Cette vérification s'est arrêtée sur une erreur.",
    'check.graphics': "Graphiques",
    'check.graphics.ok': "{gpu}. Pilote : {driver}. Vulkan fonctionne.",
    'check.graphics.ok.detail': "Les jeux utilisent Vulkan, directement ou par Proton. Le "
                                "pilote fait partie de SparkOS et se met à jour avec lui.",
    'check.graphics.novk': "Carte graphique trouvée : {cards}. Vulkan n'a pas été testé "
                           "(vulkaninfo n'est pas installé).",
    'check.graphics.novk.detail': "La carte a un pilote. Sans vulkaninfo, cette vérification "
                                  "ne peut pas dire si Vulkan fonctionne.",
    'check.graphics.vkfail': "Carte graphique trouvée : {cards}, mais aucun périphérique "
                             "Vulkan.",
    'check.graphics.vkfail.detail': "Vulkan a seulement trouvé un rendu logiciel, alors les "
                                    "jeux tourneraient sur le processeur. Ça peut arriver dans "
                                    "une machine virtuelle, ou quand le pilote de la carte "
                                    "ne s'est pas chargé.",
    'check.graphics.vkerror.detail': "vulkaninfo a échoué, alors Vulkan ne fonctionne "
                                     "peut-être pas. Les jeux en ont besoin. Redémarrer après "
                                     "une mise à jour règle souvent le problème.",
    'check.graphics.none': "Aucun pilote graphique trouvé.",
    'check.graphics.none.detail': "Le système ne voit aucune carte graphique avec un pilote "
                                  "chargé. Dans une machine virtuelle, c'est normal.",
    'check.sound': "Son",
    'check.sound.ok': "Le son sort par {device}.",
    'check.sound.ok.detail': "{count} périphérique(s) de sortie. Faites jouer le son de test "
                             "pour l'entendre.",
    'check.sound.none': "Aucune sortie de son trouvée.",
    'check.sound.none.detail': "Branchez des haut-parleurs ou des écouteurs, ou allumez "
                               "l'écran s'il transmet le son, puis vérifiez de nouveau.",
    'check.sound.nowpctl': "Vérification impossible : wpctl n'est pas installé.",
    'check.sound.error': "Impossible d'interroger le système de son.",
    'check.printers': "Imprimantes et numériseurs",
    'check.printers.ok': "Imprimante prête : {names}.",
    'check.printers.none': "Aucune imprimante configurée pour l'instant.",
    'check.printers.none.detail': "La plupart des imprimantes réseau récentes, Canon "
                                  "comprises, fonctionnent sans pilote : allumez "
                                  "l'imprimante, branchez-la au même réseau, puis Ajouter une "
                                  "imprimante.",
    'check.scanners.found': "Numériseur trouvé : {names}.",
    'check.scanners.none': "Aucun numériseur trouvé.",
    'check.scanners.missing': "Les numériseurs n'ont pas été vérifiés (scanimage n'est pas "
                              "installé).",
    'check.network': "Réseau et Bluetooth",
    'check.network.ok': "Connecté par {how} : {name}.",
    'check.network.wifi': "Wi-Fi",
    'check.network.wired': "câble",
    'check.network.none': "Pas connecté à un réseau.",
    'check.network.none.detail': "Installer des applications demande Internet.",
    'check.network.nonmcli': "Impossible de vérifier le réseau : nmcli n'est pas installé.",
    'check.bt.on': "Le Bluetooth est activé.",
    'check.bt.off': "Le Bluetooth est désactivé.",
    'check.bt.none': "Pas de Bluetooth sur ce PC.",
    'check.updates': "Mises à jour",
    'check.updates.ok': "Ce système a été compilé le {date} ({image}).",
    'check.updates.auto': "SparkOS se met à jour en arrière-plan et passe à la nouvelle "
                          "version quand vous redémarrez. Vos applications du magasin se "
                          "mettent à jour de la même façon.",
    'check.updates.staged': "Une mise à jour est téléchargée et prête : redémarrez pour "
                            "l'utiliser.",
    'check.updates.noostree': "Ce n'est pas une installation de SparkOS à partir d'une image.",
    'check.updates.noostree.detail': "rpm-ostree n'est pas là, alors cette vérification ne "
                                     "peut pas dire comment les mises à jour fonctionnent "
                                     "sur ce système.",
    'check.updates.error': "Impossible de lire l'état des mises à jour.",
    'fix.test_sound': "Son de test",
    'fix.sound_settings': "Réglages du son",
    'fix.add_printer': "Ajouter une imprimante",
    'fix.network_settings': "Réglages du réseau",
    'fix.bluetooth_settings': "Réglages Bluetooth",

    # 6. done
    'done.title': "C'est prêt",
    'done.store.title': "Installer des applications",
    'done.store.button': "Ouvrir le magasin",
    'done.settings.title': "Réglages",
    'done.settings.button': "Ouvrir les réglages",
    'done.show_again': "Afficher Spark Welcome à la connexion",
    'done.menu': "{name} reste dans le menu des applications.",
    'done.still_installing': "Des applications s'installent encore. Laissez cette fenêtre "
                             "ouverte jusqu'à la fin; la fermer les arrête.",

    # moving from Windows (1.1)
    'open': "Ouvrir",
    'nav.windows': "VOS FICHIERS",
    'welcome.swaps': "Ce que vous utilisiez sous Windows, et ce qui le fait ici",
    'welcome.swaps.intro': "Elles sont déjà sur ce PC. Ouvrir affiche l'application.",
    'welcome.instead': "Au lieu de {win}",
    'swap.browser.win': "Chrome, Edge ou Firefox",
    'swap.browser.what': "Navigateur Web. Connectez-vous à votre compte Google, Microsoft ou "
                         "Firefox pour ramener vos favoris et mots de passe.",
    'swap.office.win': "Microsoft Office, Outlook et Adobe Reader",
    'swap.office.what': "Courriel, calendrier, documents, feuilles de calcul, présentations et "
                        "PDF. Ouvre et enregistre les fichiers Word, Excel et PowerPoint.",
    'swap.files.win': "l'Explorateur de fichiers",
    'swap.files.what': "Vos dossiers, vos disques et la corbeille. Extraire et Compresser sont "
                       "dans le menu du clic droit.",
    'swap.launcher.win': "le menu Démarrer",
    'swap.launcher.what': "Appuyez sur la touche Windows (Meta) et tapez pour trouver une "
                          "application, un fichier ou un réglage.",
    'swap.settings.win': "les Paramètres de Windows et le Panneau de configuration",
    'swap.settings.what': "Écrans, son, réseau, Bluetooth, alimentation, applications par "
                          "défaut, langue, imprimantes et démarrage.",
    'swap.store.win': "le Microsoft Store et les installateurs des sites Web",
    'swap.store.what': "Les applications de Flathub et les applications Spark facultatives, "
                       "installées en un clic et mises à jour toutes seules.",
    'swap.update.win': "Windows Update",
    'swap.update.what': "Prépare la nouvelle version en arrière-plan et la démarre au prochain "
                        "redémarrage. Si quelque chose ne va pas, revenez à la précédente.",
    'swap.monitor.win': "le Gestionnaire des tâches",
    'swap.monitor.what': "Ce qui tourne, Fin de tâche et graphiques en direct. Ctrl+Maj+Échap "
                         "l'ouvre, comme sous Windows.",
    'swap.games.win': "les lanceurs Steam, Epic, GOG, Battle.net, EA et Ubisoft",
    'swap.games.what': "Tous vos jeux dans une seule bibliothèque. Se connecte lui-même à "
                       "Epic, GOG et Amazon, et ajoute les autres lanceurs pour vous.",
    'swap.run.win': "les programmes Windows (.exe et .msi)",
    'swap.run.what': "Lance les programmes Windows avec Wine, ou les installe comme "
                     "applications avec leur entrée dans le menu. Double-cliquez sur un .exe "
                     "pour commencer.",
    'swap.snip.win': "l'Outil Capture et l'enregistrement de la Xbox Game Bar",
    'swap.snip.what': "Impr. écran ou Meta+Maj+S pour une capture, Meta+Maj+R pour enregistrer "
                      "l'écran, Meta+Maj+T pour copier le texte à l'écran.",
    'swap.media.win': "Photos, le Lecteur multimédia et VLC",
    'swap.media.what': "Photos, vidéos et musique.",
    'swap.edit.win': "le Bloc-notes et Notepad++",
    'swap.edit.what': "Éditeur de texte et de code.",
    'swap.calc.win': "la Calculatrice",
    'swap.calc.what': "Standard, scientifique et programmeur.",
    'swap.archive.win': "7-Zip et WinRAR",
    'swap.archive.what': "zip, 7z, tar, rar et iso.",
    'swap.terminal.win': "l'Invite de commandes, PowerShell et le Terminal Windows",
    'swap.terminal.what': "Terminal. Ctrl+C et Ctrl+V copient et collent, comme sous Windows.",
    'swap.scan.win': "Numériser de Windows",
    'swap.scan.what': "Numérise en PDF, avec du texte cherchable.",
    'swap.link.win': "Lien avec Windows (Phone Link)",
    'swap.link.what': "Liens, fichiers, notifications et presse-papiers entre votre téléphone "
                      "et ce PC. S'associe à Soot sur Android.",
    'swap.controller.win': "Armoury Crate, les outils RGB et le contrôle des ventilateurs",
    'swap.controller.what': "Ventilateurs, éclairage RGB et mises à jour du micrologiciel de "
                            "ce PC.",
    'games.intro': "Spark Games est votre bibliothèque de jeux sur SparkOS. Steam est le seul "
                   "lanceur à installer vous-même.",
    'games.spark': "Une bibliothèque pour les jeux Steam, Epic, GOG et Amazon, avec les "
                   "pochettes, le temps de jeu et un bouton Jouer. Connectez-vous à Epic, GOG "
                   "et Amazon dans Spark Games : aucun autre lanceur n'est nécessaire.",
    'games.spark.stores': "Battle.net, l'application EA, Ubisoft Connect et Rockstar "
                          "s'ajoutent aussi depuis Spark Games : il installe chacun avec Wine "
                          "et liste ses jeux.",
    'games.open': "Ouvrir Spark Games",
    'games.launchers': "Installer Steam",
    'games.steam_move': "Les jeux Steam du disque Windows n'ont pas à être téléchargés de "
                        "nouveau : la page Quitter Windows les montre et explique comment les "
                        "copier.",
    'games.later': "Les autres lanceurs, comme celui de Minecraft, sont dans Spark Games et le "
                   "magasin.",
    'apps.intro': "Les applications SparkOS d'abord, puis celles d'autres entreprises pour ce "
                  "que SparkOS ne fait pas lui-même. Rien n'est coché : choisissez ce que vous "
                  "utilisez.",
    'apps.spark': "Applications Spark à ajouter",
    'apps.spark.intro': "Faites pour SparkOS et déjà sur ce PC, pas encore installées. Elles "
                        "s'installent pour votre compte, sans téléchargement.",
    'apps.instead': "Au lieu de {win}",
    'optional.spark-space.win': "WinDirStat, TreeSize ou WizTree",
    'optional.spark-bench.win': "CapFrameX ou PresentMon",
    'optional.spark-connect.win': "Bureau à distance et PuTTY, pour vos propres PC et serveurs",
    'apps.others': "Applications d'autres entreprises",
    'apps.others.intro': "Pour clavarder, la musique, la diffusion et la création. Chacune "
                         "indique à qui elle appartient.",
    'win.title': "Vos fichiers",
    'win.intro': "Vos disques sont ouverts, mais votre Bureau, vos Documents, vos Images et "
                 "vos autres dossiers sont encore sur le disque Windows (C:). Copiez-les ici "
                 "avant de l'effacer. Cette étape liste aussi vos programmes, avec quoi "
                 "utiliser ici pour chacun, et les jeux Steam que vous pouvez copier au lieu "
                 "de les télécharger.",
    'win.programs': "Vos programmes Windows",
    'win.programs.intro': "Trouvés sur le disque Windows, avec quoi utiliser ici.",
    'win.others': "{n} autres programmes n'ont pas de réponse ici. Cherchez-les dans le "
                  "magasin; beaucoup de programmes Windows tournent aussi avec Spark Run.",
    'win.others.show': "Afficher leurs noms",
    'prog.spark': "Utilisez {name}. Il est déjà sur ce PC.",
    'prog.games': "Spark Games s'y connecte ou l'ajoute pour vous.",
    'prog.app': "Installez {name} pour Linux.",
    'prog.optional': "Installez {name}, fait pour SparkOS.",
    'prog.store': "Cherchez-le dans le magasin.",
    'prog.install': "Installer",
    'prog.queued': "En attente",
    'prog.anticheat': "Utilise un anti-triche au niveau du noyau : ces jeux ne tournent pas "
                      "sous Linux.",
    'prog.onedrive': "Pas d'application OneDrive pour Linux. Utilisez onedrive.com dans Soot. "
                     "Avant d'effacer Windows, assurez-vous que vos fichiers sont vraiment sur "
                     "ce disque ou en ligne (voir plus bas).",
    'prog.cloud': "Pas d'application Linux de cette entreprise. Utilisez son site dans Soot.",
    'prog.teams': "Utilisez teams.microsoft.com dans Soot.",
    'prog.drivers': "Pas nécessaire : les pilotes graphiques viennent avec SparkOS et se "
                    "mettent à jour avec lui.",
    'prog.peripherals': "Pas de version Linux. La souris et le clavier sont dans Spark "
                        "Settings; l'éclairage et les ventilateurs dans Spark Controller.",
    'win.steam': "Jeux Steam sur le disque Windows",
    'win.steam.found': "{n} jeux sont sur ce disque. Les copier est plus rapide que de les "
                       "télécharger de nouveau.",
    'win.steam.none': "Steam est sur le disque Windows, mais aucun jeu n'a été trouvé dans ses "
                      "bibliothèques sur ce disque. Celles des autres disques sont listées ici.",
    'win.steam.more': "et {n} autres",
    'win.steam.open': "Ouvrir le dossier",
    'win.steam.how': "Pour chaque jeu : dans Steam ici, lancez son installation, puis mettez "
                     "le téléchargement en pause. Copiez le dossier du jeu du disque Windows "
                     "dans {common}, puis reprenez. Steam vérifie les fichiers et ne "
                     "télécharge que ce qui manque.",
    'win.before': "Avant d'effacer Windows",
    'win.before.intro': "Copier les dossiers n'apporte pas tout. Vérifiez ceci pendant que "
                        "Windows fonctionne encore.",
    'win.before.1.title': "Mots de passe et favoris",
    'win.before.1': "Ils sont chiffrés sur le disque Windows et ne peuvent pas être copiés. "
                    "Connectez-vous au compte de votre navigateur et activez la "
                    "synchronisation, ou exportez les mots de passe depuis ses réglages, puis "
                    "importez-les dans Soot.",
    'win.before.2.title': "Fichiers OneDrive",
    'win.before.2': "Les fichiers avec une icône de nuage sont seulement en ligne. Faites un "
                    "clic droit sur le dossier OneDrive et choisissez Toujours conserver sur "
                    "cet appareil avant de copier, ou téléchargez-les plus tard depuis "
                    "onedrive.com.",
    'win.before.3.title': "Sauvegardes de jeux",
    'win.before.3': "La plupart des lanceurs synchronisent les sauvegardes en ligne. Les jeux "
                    "qui ne le font pas les gardent dans Documents\\My Games, Saved Games ou "
                    "AppData : copiez aussi ces dossiers.",
    'win.before.4.title': "Licences",
    'win.before.4': "Notez les clés des programmes payés, et déconnectez-vous des applications "
                    "limitées à quelques appareils, comme Adobe ou Office.",
    'win.before.5.title': "Codes de validation en deux étapes",
    'win.before.5': "Si une application d'authentification ou une clé de sécurité est "
                    "configurée sous Windows, déplacez-la d'abord vers votre téléphone, sinon "
                    "vous pourriez perdre l'accès à vos comptes.",
    'win.before.6.title': "Mot de passe Wi-Fi",
    'win.before.6': "Notez-le, ou trouvez-le sur votre routeur.",
    'win.before.7.title': "BitLocker",
    'win.before.7': "Un disque verrouillé ne peut pas être ouvert ici. Désactivez BitLocker "
                    "dans Windows, ou notez la clé de récupération sur account.microsoft.com.",
    'win.before.8.title': "Démarrage rapide",
    'win.before.8': "Désactivez-le dans les options d'alimentation de Windows. Sinon, Windows "
                    "laisse son disque à moitié fermé, et il ne peut être ouvert qu'en lecture "
                    "seule ici.",
    'win.before.9.title': "Gardez Windows encore un peu",
    'win.before.9': "Utilisez SparkOS pendant une semaine normale d'abord. Quand rien ne "
                    "manque, Windows peut partir.",
    'done.intro': "Trois choses à savoir.",
    'done.store': "Les applications s'installent depuis le magasin en un clic et se mettent à "
                  "jour toutes seules. Double-cliquez sur un .exe, .AppImage ou .rpm "
                  "téléchargé : SparkOS dit ce qu'il peut en faire, et Spark Run ouvre les "
                  "programmes Windows.",
    'done.keys.title': "Les touches de Windows qui marchent encore",
    'done.keys': "Touche Windows : Spark Launcher. Ctrl+Maj+Échap : Spark Monitor. Impr. écran "
                 "ou Meta+Maj+S : Spark Snip. Ctrl+C, Ctrl+V et Alt+Tab marchent comme "
                 "d'habitude.",
    'done.settings': "L'affichage, le son, le réseau, le Bluetooth, les imprimantes et le "
                     "reste sont dans Spark Settings.",

    # le guide (1.2)
    'nav.step': "Étape {n} sur {total}",
    'nav.next_to': "Suivant : {step}",
    'step.todo': "À faire ici",
    'nav.different': "CE QUI CHANGE",
    'nav.familiar': "CE QUI RESTE",
    'nav.drives': "VOS DISQUES",
    'nav.erase': "EFFACER WINDOWS",
    'welcome.guide': "Ce guide vous accompagne une étape à la fois : ce qui change par "
                     "rapport à Windows, ce qui reste, vos disques et vos fichiers, et quoi "
                     "vérifier avant d'effacer Windows.",
    'welcome.steps': "Les étapes",
    'welcome.start': "Commencer",
    'welcome.step.different': "Les applications, les mises à jour et les disques marchent "
                              "autrement ici.",
    'welcome.step.familiar': "La barre des tâches, les fenêtres, les dossiers et les "
                             "raccourcis que vous connaissez.",
    'welcome.step.drives': "Vérifier que chaque disque avec vos fichiers s'ouvre à chaque "
                           "démarrage.",
    'welcome.step.windows': "Copier vos dossiers depuis le disque Windows.",
    'welcome.step.games': "Installer Steam et les autres lanceurs de jeux.",
    'welcome.step.apps': "Installer les applications que vous utilisez.",
    'welcome.step.checks': "Graphiques, son, imprimantes, réseau et mises à jour.",
    'welcome.step.erase': "Quoi vérifier avant d'effacer Windows, et comment.",
    'welcome.step.done': "Où trouver les choses plus tard.",

    'diff.title': "Ce qui change",
    'diff.intro': "SparkOS n'est pas Windows. Voici les changements que vous verrez en "
                  "premier.",
    'diff.todo': "Lisez les cartes. Rien à régler ici.",
    'diff.store.title': "Les applications viennent du magasin",
    'diff.store': "Au lieu de télécharger des installateurs sur des sites, installez les "
                  "applications depuis le magasin. Un clic les installe, et elles se mettent "
                  "à jour toutes seules. Spark Run peut ouvrir un .exe téléchargé, mais pas "
                  "tous les programmes Windows.",
    'diff.store.button': "Ouvrir le magasin",
    'diff.games.title': "Les jeux Windows passent par Proton",
    'diff.games': "Steam et les autres lanceurs font tourner les jeux Windows avec Proton. "
                  "La plupart marchent. Ceux avec un anti-triche au niveau du noyau, non; "
                  "l'étape Jeux en dit plus.",
    'diff.update.title': "Les mises à jour remplacent tout le système",
    'diff.update': "SparkOS télécharge la version suivante en arrière-plan et passe dessus "
                   "au redémarrage. Si quelque chose cloche après une mise à jour, la version "
                   "précédente est encore dans le menu de démarrage : choisissez-la là.",
    'diff.letters.title': "Pas de lettres de lecteur",
    'diff.letters': "Tout est dans un seul arbre de dossiers. Vos fichiers sont dans votre "
                    "dossier personnel. Les disques Windows s'ouvrent comme des dossiers : C: "
                    "est /var/mnt/c, D: est /var/mnt/d. Spark Files liste vos disques à "
                    "gauche.",
    'diff.password.title': "Votre mot de passe au lieu de Oui / Non",
    'diff.password': "Là où Windows demande « Voulez-vous autoriser cette application à "
                     "apporter des modifications? », SparkOS demande votre mot de passe, par "
                     "exemple pour ajouter un disque ou changer un réglage du système.",
    'diff.sandbox.title': "Le système ne peut pas être modifié par accident",
    'diff.sandbox': "Les fichiers du système sont en lecture seule, et les applications du "
                    "magasin ne voient que ce dont elles ont besoin. Les programmes faits pour "
                    "Windows, virus compris, ne s'exécutent pas ici d'eux-mêmes.",
    'diff.case.title': "Les majuscules comptent dans les noms",
    'diff.case': "Photo.jpg et photo.jpg peuvent être deux fichiers différents ici.",

    'same.title': "Ce qui reste",
    'same.intro': "La plupart de ce que vous faites chaque jour marche comme sur Windows.",
    'same.todo': "Lisez les cartes et essayez quelques raccourcis. Rien à régler ici.",
    'same.taskbar.title': "La barre des tâches",
    'same.taskbar': "En bas : le bouton SPARK ouvre le menu des applications (la touche "
                    "Windows aussi), puis vos applications épinglées et ouvertes, puis "
                    "l'horloge, les icônes et les notifications à droite.",
    'same.windows.title': "Les fenêtres",
    'same.windows': "Réduire, agrandir et fermer sont en haut à droite de chaque fenêtre. "
                    "Touche Windows + flèches pour ancrer et agrandir, comme sur Windows.",
    'same.files.title': "Vos dossiers",
    'same.files': "Votre dossier personnel a Bureau, Documents, Téléchargements, Musique, "
                  "Images et Vidéos. Spark Files marche comme l'Explorateur : clic droit, "
                  "glisser-déposer, et une corbeille à vider.",
    'same.mouse.title': "Clavier et souris",
    'same.mouse': "Ctrl+C, Ctrl+V, Ctrl+Z et les autres raccourcis Ctrl marchent comme "
                  "d'habitude. Le clic droit ouvre un menu presque partout.",
    'same.keys': "Raccourcis clavier",
    'key.menu': "Touche Windows",
    'key.menu.what': "Ouvrir le menu des applications",
    'key.switch': "Alt+Tab",
    'key.switch.what': "Passer d'une fenêtre à l'autre",
    'key.close': "Alt+F4",
    'key.close.what': "Fermer la fenêtre",
    'key.snap': "Win+Gauche / Droite",
    'key.snap.what': "Ancrer sur la moitié de l'écran. Win+Haut agrandit, Win+Bas restaure.",
    'key.desktop': "Win+D",
    'key.desktop.what': "Afficher le bureau",
    'key.lock': "Win+L",
    'key.lock.what': "Verrouiller l'écran",
    'key.files': "Win+E",
    'key.files.what': "Ouvrir Spark Files",
    'key.settings': "Win+I",
    'key.settings.what': "Ouvrir Spark Settings",
    'key.monitor': "Ctrl+Maj+Échap",
    'key.monitor.what': "Ouvrir Spark Monitor (le Gestionnaire des tâches)",
    'key.snip': "Impr. écran, Win+Maj+S",
    'key.snip.what': "Faire une capture avec Spark Snip",
    'key.clipboard': "Win+V",
    'key.clipboard.what': "Historique du presse-papiers",
    'key.emoji': "Win+.",
    'key.emoji.what': "Émojis",
    'key.terminal': "Ctrl+Alt+T",
    'key.terminal.what': "Ouvrir un terminal",
    'key.copy': "Ctrl+C / Ctrl+V / Ctrl+Z",
    'key.copy.what': "Copier, coller, annuler",

    'drives.title': "Vos disques",
    'drives.intro': "Chaque disque avec vos fichiers doit s'ouvrir tout seul à chaque "
                    "démarrage, pour que vos jeux et fichiers soient là sans Windows.",
    'drives.todo': "Vérifiez que chaque disque Windows ci-dessous s'ouvre : cliquez sur "
                   "Ouvrir et cherchez vos fichiers. Si des disques sont listés sous Autres "
                   "disques, cochez-les et cliquez sur Ajouter pour qu'ils s'ouvrent aussi à "
                   "chaque démarrage.",
    'drives.win': "Disques Windows",
    'drives.win.no_report': "SparkOS n'a pas encore signalé ses disques Windows. Redémarrez "
                            "le PC, puis rouvrez cette étape.",
    'drives.win.none': "Aucun disque Windows sur ce PC.",
    'drives.rw': "LECTURE-ÉCRITURE",
    'drives.ro': "LECTURE SEULE",
    'drives.off': "PAS OUVERT",
    'drives.win.locked': "Verrouillé par BitLocker : SparkOS ne peut pas le lire. Désactivez "
                         "BitLocker pour ce disque dans Windows, puis redémarrez sur SparkOS.",
    'drives.win.hibernated': "Windows ne s'est pas arrêté complètement, donc ce disque est en "
                             "lecture seule. Démarrez Windows, désactivez le démarrage rapide "
                             "dans les options d'alimentation, éteignez, puis démarrez SparkOS.",
    'drives.win.ro_choice': "En lecture seule exprès. Pour y écrire, changez la ligne "
                            "« {letter} ro » en « {letter} rw » dans {conf} et redémarrez.",
    'drives.win.problem': "SparkOS dit : {problem}",
    'drives.win.keep': "Ces disques gardent leur lettre et leur dossier après l'effacement de "
                       "Windows.",
    'drives.other': "Autres disques",
    'drives.other.intro': "Des disques avec des fichiers que SparkOS n'ouvre pas encore tout "
                          "seul. En ajouter un l'ouvre maintenant et à chaque démarrage, dans "
                          "le dossier indiqué. Rien dessus n'est changé ni effacé. SparkOS "
                          "demande votre mot de passe.",
    'drives.other.none': "Aucun autre disque. Les clés USB et cartes SD s'ouvrent toutes "
                         "seules quand vous les branchez.",
    'drives.looking': "Recherche des disques…",
    'drives.lsblk_failed': "Impossible de lister les disques : {error}",
    'drives.added': "AJOUTÉ",
    'drives.add': "Ajouter les cochés ({n})",
    'drives.add_none': "Ajouter les cochés",
    'drives.again': "Chercher de nouveau",
    'drives.adding': "Ajout en cours. Si une fenêtre de mot de passe apparaît, c'est SparkOS "
                     "qui demande à changer sa liste de disques.",
    'drives.added_at': "{name} s'ouvre dans {where}, maintenant et à chaque démarrage.",
    'drives.err.password': "Ajouter un disque demande votre mot de passe, et il n'a pas été "
                           "donné.",
    'drives.err.damaged': "Le système de fichiers du disque semble endommagé, il ne peut pas "
                          "être ouvert.",
    'drives.err.generic': "Le disque n'a pas pu être ajouté.",
    'drives.not_writable': "Il s'est ouvert, mais vous ne pouvez pas y écrire : ses fichiers "
                           "appartiennent à un autre utilisateur.",
    'drives.added_next_start': "Il est ajouté, mais n'a pas pu être ouvert maintenant. Il "
                               "s'ouvrira au prochain démarrage.",

    'win.todo': "Choisissez le disque Windows, cochez les dossiers voulus, puis cliquez sur "
                "Copier les cochés. Vos autres disques (D:, E: et ainsi de suite) n'ont pas "
                "besoin d'être copiés : ils restent après l'effacement de Windows.",

    'erase.title': "Avant d'effacer Windows",
    'erase.intro': "Quand tout ce dont vous avez besoin est ici, la partition Windows peut "
                   "être effacée pour libérer sa place. Spark Welcome n'efface jamais rien "
                   "lui-même.",
    'erase.todo': "Parcourez la liste pendant que Windows démarre encore. Quand rien ne "
                  "manque, effacez la partition Windows dans Spark Disks.",
    'erase.drives': "Ce qui reste et ce qui part",
    'erase.drives.unknown': "SparkOS n'a pas signalé ses disques Windows, donc cette étape ne "
                            "peut pas dire lesquels restent.",
    'erase.c.title': "C: part",
    'erase.c': "Effacer Windows, c'est effacer C:. Tout ce qui s'y trouve et que vous n'avez "
               "pas copié à l'étape 5 est perdu.",
    'erase.stay.title': "Ces disques restent",
    'erase.stay': "Ils sont séparés de Windows et gardent leur lettre et leur dossier :\n"
                  "{drives}",
    'erase.how': "Effacer la partition Windows",
    'erase.how.title': "Dans Spark Disks",
    'erase.how.text': "Choisissez la partition Windows (C:, NTFS), puis Supprimer, et tapez "
                      "le nom de périphérique affiché pour confirmer. Spark Disks ferme la "
                      "partition d'abord. L'espace libéré peut ensuite accueillir une "
                      "nouvelle partition pour vos fichiers.",
    'erase.disks': "Ouvrir Spark Disks",
    'erase.efi.title': "Ne touchez pas aux petites partitions",
    'erase.efi': "Supprimez seulement la partition Windows. La petite partition EFI est celle "
                 "d'où le PC démarre, et SparkOS peut s'en servir aussi.",
}

LANG = ui_language()
_TABLE = {**EN, **FR} if LANG == 'fr' else EN


def t(key: str, **values) -> str:
    text = _TABLE.get(key)
    if text is None:
        text = EN.get(key, key)
    try:
        return text.format(**values) if values else text
    except (KeyError, IndexError, ValueError):
        return text
