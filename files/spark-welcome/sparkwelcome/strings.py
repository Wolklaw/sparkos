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
    'welcome.edit': "text and code editor",
    'welcome.calc': "calculator: standard, scientific and programmer",
    'welcome.archive': "zip, 7z, tar, rar and iso; Extract and Compress in the file manager",
    'welcome.scan': "scanning to PDF, with searchable text",
    'welcome.run': "Windows programs (.exe and .msi)",
    'welcome.link': "your phone and this PC, through Soot's phone app",
    'welcome.store': "apps from Flathub, next to Bazaar",
    'welcome.update': "updates and going back to the previous version",
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
    'nav.windows': "FICHIERS DE WINDOWS",
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
                     "construit sur Fedora et Bazzite. Il se met à jour en arrière-plan et "
                     "garde les fichiers du système en lecture seule, alors une mise à jour ou "
                     "une application ne peut pas le briser.",
    'welcome.rest': "Il vient seulement avec ses propres applications. Tout le reste, de Steam "
                    "à Discord, est à un clic : les pages suivantes proposent les plus "
                    "courantes, et le magasin a le reste.",
    'welcome.onboard': "Déjà sur ce PC",
    'welcome.soot': "navigateur Web",
    'welcome.freesuite': "documents, feuilles de calcul et présentations",
    'welcome.snip': "captures d'écran, texte à l'écran, enregistrement de l'écran",
    'welcome.media': "photos, vidéos et musique",
    'welcome.games': "tous vos jeux de tous les lanceurs, dans une seule bibliothèque",
    'welcome.monitor': "gestionnaire des tâches : ce qui tourne, Fin de tâche, graphiques en "
                       "direct (Ctrl+Maj+Échap)",
    'welcome.edit': "éditeur de texte et de code",
    'welcome.calc': "calculatrice : standard, scientifique et programmeur",
    'welcome.archive': "zip, 7z, tar, rar et iso; Extraire et Compresser dans le gestionnaire "
                       "de fichiers",
    'welcome.scan': "numérisation en PDF, avec texte cherchable",
    'welcome.run': "programmes Windows (.exe et .msi)",
    'welcome.link': "votre téléphone et ce PC, avec l'application mobile de Soot",
    'welcome.store': "applications de Flathub, à côté de Bazaar",
    'welcome.update': "mises à jour et retour à la version précédente",
    'welcome.how': "Comment ça marche",
    'welcome.skip': "Chaque page peut être sautée. Rien n'est installé ni copié avant que vous "
                    "cliquiez sur un bouton, et vous pouvez fermer cette fenêtre en tout temps. "
                    "Spark Welcome reste dans le menu des applications si vous en avez besoin "
                    "plus tard.",

    # 2. games
    'games.title': "Jeux",
    'games.intro': "Cochez les lanceurs que vous utilisez. Ils s'installent depuis Flathub pour "
                   "votre compte seulement, sans mot de passe d'administrateur, un à la fois en "
                   "arrière-plan. Vous pouvez continuer à parcourir les pages pendant ce temps.",
    'games.launchers': "Lanceurs",
    'games.spark_games': "Spark Games est installé : il montre les jeux de tous ces lanceurs "
                         "au même endroit.",
    'games.anticheat.label': "Ce qui ne fonctionne pas",
    'games.anticheat': "Les jeux avec un anti-triche au niveau du noyau ne tournent pas sous "
                       "Linux, peu importe le lanceur : Valorant, Fortnite, et certains jeux "
                       "Call of Duty et EA, entre autres. C'est le choix de l'éditeur du jeu, "
                       "pas quelque chose que SparkOS peut régler. Vérifiez un jeu avant de "
                       "l'acheter.",
    'games.anticheat.button': "Ouvrir areweanticheatyet.com",
    'games.later': "Vous pourrez installer d'autres lanceurs plus tard à partir du magasin.",

    # 3. apps
    'apps.title': "Applications",
    'apps.intro': "Des applications que les gens veulent souvent. Rien n'est coché : "
                  "choisissez ce que vous utilisez. Chacune indique à qui elle appartient.",
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
    'flatpak.remote_failed': "Impossible d'ajouter Flathub : {error}",
    'flatpak.cant_run': "Impossible de lancer flatpak : {error}",
    'flatpak.stopped': "Arrêté à la fermeture de la fenêtre.",

    # 4. files from Windows
    'win.title': "Récupérer vos fichiers de Windows",
    'win.intro': "Si Windows est aussi sur ce PC, Spark Welcome peut copier votre Bureau, vos "
                 "Documents, Images, Vidéos, Musique et Téléchargements dans les mêmes "
                 "dossiers ici.",
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
    'done.intro': "Trois choses à savoir.",
    'done.store.title': "Installer des applications",
    'done.store': "Le magasin a des milliers d'applications qui s'installent en un clic et se "
                  "mettent à jour toutes seules. Vous pouvez aussi double-cliquer sur un "
                  "fichier .exe, .AppImage ou .rpm téléchargé : SparkOS vous dit ce qu'il peut "
                  "en faire.",
    'done.store.button': "Ouvrir le magasin",
    'done.snip.title': "Captures d'écran",
    'done.snip': "Appuyez sur Impr. écran, ou ouvrez Spark Snip dans le menu. Il copie aussi "
                 "le texte à l'écran et enregistre des vidéos.",
    'done.snip.button': "Ouvrir Spark Snip",
    'done.settings.title': "Réglages",
    'done.settings': "L'affichage, le son, la souris, le clavier, les comptes et le reste sont "
                     "dans Configuration du système, dans le menu des applications.",
    'done.settings.button': "Ouvrir les réglages",
    'done.show_again': "Afficher Spark Welcome à la connexion",
    'done.menu': "{name} reste dans le menu des applications.",
    'done.still_installing': "Des applications s'installent encore. Laissez cette fenêtre "
                             "ouverte jusqu'à la fin; la fermer les arrête.",
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
