"""Every sentence Spark Welcome shows, in one place.

To translate: add the same keys to FR (any key left out falls back to English). The language
comes from LANGUAGE / LC_ALL / LC_MESSAGES / LANG, so a French desktop picks FR by itself.
The app list's names and lines are in apps.json (name_fr, blurb_fr)."""

import os
from typing import Dict

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
    'nav.windows': "FILES FROM WINDOWS",
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
    'welcome.intro': "SparkOS is a Linux system for gaming and everyday use, built on Fedora "
                     "and Bazzite. It updates itself in the background and keeps the system "
                     "files read-only, so an update or an app can't break it.",
    'welcome.rest': "It comes with only its own apps. Everything else, from Steam to Discord, "
                    "is one click away: the next pages offer the common ones, and the Store "
                    "has the rest.",
    'welcome.onboard': "Already on this PC",
    'welcome.soot': "web browser",
    'welcome.freesuite': "documents, spreadsheets and presentations",
    'welcome.snip': "screenshots, text from the screen, screen recording",
    'welcome.media': "photos, videos and music",
    'welcome.games': "all your games from every launcher, in one library",
    'welcome.monitor': "task manager: what's running, End task, live graphs (Ctrl+Shift+Esc)",
    'welcome.how': "How this works",
    'welcome.skip': "Each page can be skipped. Nothing is installed or copied until you click "
                    "a button, and you can close this window at any time. Spark Welcome stays "
                    "in the app menu if you want it later.",

    # 2. games
    'games.title': "Games",
    'games.intro': "Tick the launchers you use. They install from Flathub for your account "
                   "only, no admin password, one at a time in the background. You can keep "
                   "going through the pages while they install.",
    'games.launchers': "Launchers",
    'games.spark_games': "Spark Games is installed: it shows the games from all these "
                         "launchers in one place.",
    'games.anticheat.label': "What doesn't work",
    'games.anticheat': "Games with kernel-level anti-cheat don't run on Linux, whatever the "
                       "launcher: Valorant, Fortnite, and some Call of Duty and EA games, among "
                       "others. That's the game maker's choice, not something SparkOS can fix. "
                       "Check a game before you buy it.",
    'games.anticheat.button': "Open areweanticheatyet.com",
    'games.later': "You can install more launchers later from the Store.",

    # 3. apps
    'apps.title': "Apps",
    'apps.intro': "Some apps people usually want. Nothing is ticked: pick what you use. Each "
                  "one says whose app it is.",
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
    'flatpak.remote_failed': "Couldn't add Flathub: {error}",
    'flatpak.cant_run': "Can't run flatpak: {error}",
    'flatpak.stopped': "Stopped when the window closed.",

    # 4. files from Windows
    'win.title': "Bring your files from Windows",
    'win.intro': "If Windows is on this PC too, Spark Welcome can copy your Desktop, "
                 "Documents, Pictures, Videos, Music and Downloads into the same folders here.",
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
    'win.done': "Copy finished",
    'win.done.cancelled': "Copy stopped",
    'win.done.copied': "Copied {n} files ({size}).",
    'win.done.skipped': "Skipped {n} already here with the same size.",
    'win.done.renamed': "{n} had the same name as a different file here and were saved as "
                        "\"name (from Windows)\".",
    'win.done.failed': "{n} couldn't be copied:",
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
    'done.intro': "Three things worth knowing.",
    'done.store.title': "Installing apps",
    'done.store': "The Store has thousands of apps that install with one click and update "
                  "by themselves. You can also double-click a downloaded .exe, .AppImage or "
                  ".rpm file: SparkOS says what it can do with it.",
    'done.store.button': "Open the Store",
    'done.snip.title': "Screenshots",
    'done.snip': "Press Print Screen, or open Spark Snip from the menu. It also copies text "
                 "from the screen and records video.",
    'done.snip.button': "Open Spark Snip",
    'done.settings.title': "Settings",
    'done.settings': "Display, sound, mouse, keyboard, accounts and the rest are in System "
                     "Settings, in the app menu.",
    'done.settings.button': "Open Settings",
    'done.show_again': "Show Spark Welcome at login",
    'done.menu': "{name} stays in the app menu.",
    'done.still_installing': "Apps are still installing. Leave this window open until they "
                             "finish; closing it stops them.",
}

FR: Dict[str, str] = {
    # Add French here, key by key. Missing keys show in English.
}


def language() -> str:
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


LANG = language()
_TABLE = {**EN, **FR} if LANG == 'fr' else EN


def t(key: str, **values) -> str:
    text = _TABLE.get(key)
    if text is None:
        text = EN.get(key, key)
    try:
        return text.format(**values) if values else text
    except (KeyError, IndexError, ValueError):
        return text
