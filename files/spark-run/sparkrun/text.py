"""Every sentence Spark Run shows, in one place: English, and French for Quebec.
t('key', name=...) fills in the blanks; a key missing in French falls back to English."""

from .lang import ui_language

EN = {
    # window
    'title': "Spark Run",
    'tagline': "Windows programs, on Wine",
    'status.ready': "WINE {version} READY",
    'status.custom': "CUSTOM WINE",
    'status.missing': "WINE NOT DOWNLOADED YET",
    'status.installing': "INSTALLING",
    'status.error': "ERROR",
    'status.crashed': "SOMETHING WENT WRONG; SEE THE LOG",
    'apps.heading': "Installed Windows apps",
    'apps.empty': "No Windows apps installed yet.\n\nDouble-click an .exe or .msi file in "
                  "Dolphin, or choose one with Run a program.",
    'apps.games': "Games run better through Steam, Heroic or Spark Games.",
    'apps.meta': "{windows} · {size} · added {added}",
    'apps.meta_nosize': "{windows} · added {added}",
    'btn.run_file': "Run a program…",
    'btn.open': "Open",
    'btn.folder': "C: folder",
    'btn.options': "Options",
    'btn.uninstall': "Uninstall",
    'btn.cancel': "Cancel",
    'btn.close': "Close",
    'btn.save': "Save",
    'btn.remove': "Remove",
    'btn.run_once': "Run once",
    'btn.install': "Install as an app",
    'btn.open_now': "Open it now",
    'btn.guide': "What runs on SparkOS",
    'btn.log': "Show the log",
    'btn.choose': "Use this one",
    'btn.run_in': "Run an installer here…",
    'pick.file': "Choose a Windows program or installer",
    'pick.filter': "Windows programs and installers",

    # the file chooser window
    'file.kind.installer': "Installer ({maker})",
    'file.kind.installer_plain': "Installer",
    'file.kind.msi': "Windows Installer package (.msi)",
    'file.kind.program': "Program",
    'file.kind.dotnet': ".NET program",
    'file.bits': "{bits}-bit",
    'file.by': "by {publisher}",
    'file.version': "version {version}",
    'file.run_once_hint': "Run once: opens it now, nothing added to the menu.",
    'file.install_hint': "Install as an app: its own Windows folder and a menu entry with "
                         "its icon. Remove it any time from Spark Run.",
    'file.install_hint_program': "Install as an app: copies it into its own Windows folder "
                                 "and adds a menu entry with its icon.",
    'file.first_time': "First time only: Spark Run downloads {names} ({size}) from "
                       "GitHub and WineHQ, and checks each file's fingerprint before using "
                       "it.",
    'file.games': "For games, add them to Steam or Heroic instead.",

    # progress
    'step.setup': "Getting Wine",
    'step.prefix': "Preparing a Windows folder (the first one takes up to a minute)",
    'step.starting': "Starting {name}",
    'step.copying': "Copying {name}",
    'step.installer': "The installer is open in its own window. Finish it there.",
    'step.waiting': "Waiting for the installer's last steps. If the program opened at the "
                    "end, close it to finish.",
    'step.finishing': "Adding it to the menu",
    'step.dxvk': "Getting DXVK",
    'progress.download': "Downloading {name}: {done} of {total}",
    'progress.unpack': "Unpacking {name}",
    'done.installed': "{name} is in your app menu.",
    'done.running': "{name} is running.",

    # options
    'opt.heading': "Options for {name}",
    'opt.name': "NAME IN THE MENU",
    'opt.program': "PROGRAM TO OPEN",
    'opt.windows': "WINDOWS VERSION",
    'opt.windows_hint': "Some programs check the version and refuse to start on one they "
                        "don't expect.",
    'opt.dxvk': "DXVK",
    'opt.dxvk_hint': "Runs Direct3D 9, 10 and 11 on Vulkan. Helps some 3D programs; most "
                     "programs don't need it. Downloads {size} once.",
    'opt.dxvk_on': "On",
    'opt.dxvk_off': "Off",
    'opt.saved': "Saved.",
    'win.win11': "11", 'win.win10': "10", 'win.win81': "8.1", 'win.win8': "8",
    'win.win7': "7", 'win.winxp': "XP",
    'win.label': "Windows {v}",

    # uninstall
    'rm.heading': "Remove {name}?",
    'rm.body': "This deletes its Windows folder ({size}), with everything the program saved "
               "inside it, and its menu entry. Files it saved in your own Documents, "
               "Downloads, Music, Pictures or Videos stay.",
    'rm.done': "{name} was removed.",

    # pick the program after an install
    'choose.heading': "Which one is the program?",
    'choose.body': "The installer added more than one program. Pick the one the menu "
                   "entry should open. You can change it later in Options.",

    # errors: one plain sentence each, never a stack trace
    'error.heading': "{name} didn't run",
    'error.heading_install': "{name} wasn't installed",
    'error.no_file': "The file isn't there any more: {file}",
    'error.dos': "This is a DOS or 16-bit Windows program. Wine on SparkOS only runs 32 and "
                 "64-bit Windows programs. DOSBox can run DOS programs.",
    'error.not_windows': "This isn't a Windows program, or the file is damaged.",
    'error.arm': "This program is made for Windows on ARM processors, not for this PC. Look "
                 "for an x64 (64-bit) or x86 (32-bit) download instead.",
    'error.vc_runtime': "The program needs Microsoft's Visual C++ runtime ({dll}), which its "
                        "installer didn't include. Download the Visual C++ Redistributable "
                        "(x64 and x86) from Microsoft, then in Spark Run open this app's "
                        "Options and use Run an installer here.",
    'error.dotnet': "The program needs Microsoft .NET ({dll}). Wine Mono, which Spark Run "
                    "uses for .NET, couldn't run it.",
    'error.no_mono': "The program needs .NET ({dll}), and Wine Mono isn't downloaded. Open "
                     "Spark Run once while online so it can get it.",
    'error.missing_dll': "The program needs {dll}, which neither it nor Wine provides.",
    'error.not_found': "Wine couldn't find the program's file.",
    'error.crashed': "The program crashed. Some Windows programs don't run on Wine yet.",
    'error.display': "Wine couldn't open a window. Spark Run needs to be started from the "
                     "desktop, not from a text console.",
    'error.vulkan': "The program needs Vulkan, which this PC's graphics driver doesn't "
                    "offer. Try turning DXVK off in Options.",
    'error.killed': "The program was stopped (signal {code}).",
    'error.exited': "The program closed right after it started (exit code {code}).",
    'error.fetch_network': "Couldn't download Wine. Check the internet connection and try "
                           "again.",
    'error.fetch_mismatch': "A download didn't match the fingerprint Spark Run expects, so it "
                            "was deleted and not used. Try again later; if it keeps "
                            "happening, tell the SparkOS project.",
    'error.fetch_space': "There isn't enough free space to download and unpack Wine (about "
                         "1 GB needed).",
    'error.fetch_unpack': "The Wine download couldn't be unpacked.",
    'error.fetch_cancelled': "Download cancelled.",
    'error.no_wine': "Wine isn't set up. Open Spark Run while online to download it.",
    'error.prefix': "Wine couldn't prepare a Windows folder for this program.",
    'error.cancelled': "Cancelled. Nothing was added.",
    'error.nothing_installed': "The installer finished, but Spark Run couldn't find a "
                               "program it installed. Nothing was added.",
    'error.installer_failed': "The installer stopped before it finished (exit code {code}). "
                              "Nothing was added.",
    'error.program_gone': "The program's file isn't in its Windows folder any more. Choose "
                          "another in Options, or uninstall and install it again.",
    'error.no_display': "Spark Run needs a desktop session to show its window.",
    'error.unexpected': "Something went wrong inside Spark Run itself. The details are in "
                        "its log; please report it to the SparkOS project.",
    'error.footer': "The details are in the log. For what runs on SparkOS and what doesn't, "
                    "see the switching guide.",
}

FR = {
    'title': "Spark Run",
    'tagline': "Programmes Windows, sur Wine",
    'status.ready': "WINE {version} PRÊT",
    'status.custom': "WINE PERSONNALISÉ",
    'status.missing': "WINE PAS ENCORE TÉLÉCHARGÉ",
    'status.installing': "INSTALLATION",
    'status.error': "ERREUR",
    'status.crashed': "UN PROBLÈME EST SURVENU; VOYEZ LE JOURNAL",
    'apps.heading': "Applications Windows installées",
    'apps.empty': "Aucune application Windows installée pour l'instant.\n\nDouble-cliquez "
                  "sur un fichier .exe ou .msi dans Dolphin, ou choisissez-en un avec "
                  "Lancer un programme.",
    'apps.games': "Les jeux fonctionnent mieux avec Steam, Heroic ou Spark Games.",
    'apps.meta': "{windows} · {size} · ajoutée le {added}",
    'apps.meta_nosize': "{windows} · ajoutée le {added}",
    'btn.run_file': "Lancer un programme…",
    'btn.open': "Ouvrir",
    'btn.folder': "Dossier C:",
    'btn.options': "Options",
    'btn.uninstall': "Désinstaller",
    'btn.cancel': "Annuler",
    'btn.close': "Fermer",
    'btn.save': "Enregistrer",
    'btn.remove': "Supprimer",
    'btn.run_once': "Lancer une fois",
    'btn.install': "Installer comme application",
    'btn.open_now': "L'ouvrir maintenant",
    'btn.guide': "Ce qui fonctionne sur SparkOS",
    'btn.log': "Voir le journal",
    'btn.choose': "Utiliser celui-ci",
    'btn.run_in': "Lancer un installateur ici…",
    'error.vc_runtime': "Le programme a besoin du moteur d'exécution Visual C++ de Microsoft "
                        "({dll}), que son installateur n'incluait pas. Téléchargez le Visual "
                        "C++ Redistributable (x64 et x86) chez Microsoft, puis dans Spark Run "
                        "ouvrez les Options de cette application et utilisez Lancer un "
                        "installateur ici.",
    'pick.file': "Choisir un programme ou un installateur Windows",
    'pick.filter': "Programmes et installateurs Windows",
    'file.kind.installer': "Installateur ({maker})",
    'file.kind.installer_plain': "Installateur",
    'file.kind.msi': "Paquet Windows Installer (.msi)",
    'file.kind.program': "Programme",
    'file.kind.dotnet': "Programme .NET",
    'file.bits': "{bits} bits",
    'file.by': "de {publisher}",
    'file.version': "version {version}",
    'file.run_once_hint': "Lancer une fois : l'ouvre maintenant, rien n'est ajouté au menu.",
    'file.install_hint': "Installer comme application : son propre dossier Windows et une "
                         "entrée de menu avec son icône. Retirez-le quand vous voulez depuis "
                         "Spark Run.",
    'file.install_hint_program': "Installer comme application : le copie dans son propre "
                                 "dossier Windows et ajoute une entrée de menu avec son "
                                 "icône.",
    'file.first_time': "La première fois seulement : Spark Run télécharge {names} ({size}) "
                       "depuis GitHub et WineHQ, et vérifie l'empreinte de chaque fichier "
                       "avant de l'utiliser.",
    'file.games': "Pour les jeux, ajoutez-les plutôt à Steam ou Heroic.",
    'step.setup': "Obtention de Wine",
    'step.prefix': "Préparation d'un dossier Windows (le premier prend jusqu'à une minute)",
    'step.starting': "Démarrage de {name}",
    'step.copying': "Copie de {name}",
    'step.installer': "L'installateur est ouvert dans sa propre fenêtre. Terminez-le là.",
    'step.waiting': "Attente des dernières étapes de l'installateur. Si le programme s'est "
                    "ouvert à la fin, fermez-le pour terminer.",
    'step.finishing': "Ajout au menu",
    'step.dxvk': "Obtention de DXVK",
    'progress.download': "Téléchargement de {name} : {done} sur {total}",
    'progress.unpack': "Décompression de {name}",
    'done.installed': "{name} est dans votre menu d'applications.",
    'done.running': "{name} est lancé.",
    'opt.heading': "Options de {name}",
    'opt.name': "NOM DANS LE MENU",
    'opt.program': "PROGRAMME À OUVRIR",
    'opt.windows': "VERSION DE WINDOWS",
    'opt.windows_hint': "Certains programmes vérifient la version et refusent de démarrer "
                        "sur une version inattendue.",
    'opt.dxvk': "DXVK",
    'opt.dxvk_hint': "Exécute Direct3D 9, 10 et 11 sur Vulkan. Aide certains programmes 3D; "
                     "la plupart n'en ont pas besoin. Télécharge {size} une seule fois.",
    'opt.dxvk_on': "Activé",
    'opt.dxvk_off': "Désactivé",
    'opt.saved': "Enregistré.",
    'win.win11': "11", 'win.win10': "10", 'win.win81': "8.1", 'win.win8': "8",
    'win.win7': "7", 'win.winxp': "XP",
    'win.label': "Windows {v}",
    'rm.heading': "Supprimer {name}?",
    'rm.body': "Cela supprime son dossier Windows ({size}), avec tout ce que le programme y "
               "a enregistré, et son entrée de menu. Les fichiers enregistrés dans vos "
               "propres dossiers Documents, Téléchargements, Musique, Images ou Vidéos "
               "restent.",
    'rm.done': "{name} a été supprimé.",
    'choose.heading': "Lequel est le programme?",
    'choose.body': "L'installateur a ajouté plus d'un programme. Choisissez celui que "
                   "l'entrée de menu doit ouvrir. Vous pourrez le changer dans Options.",
    'error.heading': "{name} n'a pas démarré",
    'error.heading_install': "{name} n'a pas été installé",
    'error.no_file': "Le fichier n'est plus là : {file}",
    'error.dos': "C'est un programme DOS ou Windows 16 bits. Wine sur SparkOS n'exécute que "
                 "les programmes Windows 32 et 64 bits. DOSBox peut exécuter les programmes "
                 "DOS.",
    'error.not_windows': "Ce n'est pas un programme Windows, ou le fichier est endommagé.",
    'error.arm': "Ce programme est fait pour Windows sur processeur ARM, pas pour ce PC. "
                 "Cherchez plutôt un téléchargement x64 (64 bits) ou x86 (32 bits).",
    'error.dotnet': "Le programme a besoin de Microsoft .NET ({dll}). Wine Mono, que Spark "
                    "Run utilise pour .NET, n'a pas pu l'exécuter.",
    'error.no_mono': "Le programme a besoin de .NET ({dll}), et Wine Mono n'est pas "
                     "téléchargé. Ouvrez Spark Run une fois en ligne pour qu'il l'obtienne.",
    'error.missing_dll': "Le programme a besoin de {dll}, que ni lui ni Wine ne fournit.",
    'error.not_found': "Wine n'a pas trouvé le fichier du programme.",
    'error.crashed': "Le programme a planté. Certains programmes Windows ne fonctionnent pas "
                     "encore sur Wine.",
    'error.display': "Wine n'a pas pu ouvrir de fenêtre. Spark Run doit être lancé depuis le "
                     "bureau, pas depuis une console texte.",
    'error.vulkan': "Le programme a besoin de Vulkan, que le pilote graphique de ce PC "
                    "n'offre pas. Essayez de désactiver DXVK dans Options.",
    'error.killed': "Le programme a été arrêté (signal {code}).",
    'error.exited': "Le programme s'est fermé juste après son démarrage (code de sortie "
                    "{code}).",
    'error.fetch_network': "Impossible de télécharger Wine. Vérifiez la connexion Internet "
                           "et réessayez.",
    'error.fetch_mismatch': "Un téléchargement ne correspondait pas à l'empreinte attendue "
                            "par Spark Run : il a été supprimé et n'a pas été utilisé. "
                            "Réessayez plus tard; si cela se répète, signalez-le au projet "
                            "SparkOS.",
    'error.fetch_space': "Il n'y a pas assez d'espace libre pour télécharger et décompresser "
                         "Wine (environ 1 Go nécessaire).",
    'error.fetch_unpack': "Le téléchargement de Wine n'a pas pu être décompressé.",
    'error.fetch_cancelled': "Téléchargement annulé.",
    'error.no_wine': "Wine n'est pas installé. Ouvrez Spark Run en ligne pour le télécharger.",
    'error.prefix': "Wine n'a pas pu préparer de dossier Windows pour ce programme.",
    'error.cancelled': "Annulé. Rien n'a été ajouté.",
    'error.nothing_installed': "L'installateur a terminé, mais Spark Run n'a trouvé aucun "
                               "programme installé. Rien n'a été ajouté.",
    'error.installer_failed': "L'installateur s'est arrêté avant la fin (code de sortie "
                              "{code}). Rien n'a été ajouté.",
    'error.program_gone': "Le fichier du programme n'est plus dans son dossier Windows. "
                          "Choisissez-en un autre dans Options, ou désinstallez-le et "
                          "réinstallez-le.",
    'error.no_display': "Spark Run a besoin d'une session de bureau pour afficher sa fenêtre.",
    'error.unexpected': "Un problème est survenu dans Spark Run lui-même. Les détails sont "
                        "dans son journal; signalez-le au projet SparkOS.",
    'error.footer': "Les détails sont dans le journal. Pour savoir ce qui fonctionne sur "
                    "SparkOS, consultez le guide de transition.",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    try:
        return text.format(**kw) if kw else text
    except (KeyError, IndexError, ValueError):
        return text
