"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # header
    'status.ready': "READY",
    'status.scanning': "SCANNING",
    'status.done': "SCANNED IN {seconds} S",
    'status.cancelled': "SCAN CANCELLED, PARTIAL RESULTS",
    'status.error': "SOMETHING WENT WRONG",
    'status.trashed': "MOVED {size} TO THE TRASH",
    'status.copied': "COMMAND COPIED",

    # start screen
    'home.heading': "WHERE DID THE SPACE GO",
    'home.sub': "Pick a drive or a folder. Spark Space measures it and shows what takes the room.",
    'home.scan_drive': "Scan drive",
    'home.scan_home': "Scan home",
    'home.home_title': "YOUR HOME FOLDER",
    'home.folder_title': "A FOLDER",
    'home.folder_body': "Scan any folder you choose. Other drives mounted inside it are "
                        "left out.",
    'home.choose': "Choose folder",
    'home.choose_title': "Choose a folder to scan",
    'drive.letter': "{letter}: drive",
    'drive.sparkos': "SparkOS",
    'drive.measuring': "measuring…",
    'drive.numbers': "{used} used  ·  {free} free  ·  {total}",
    'drive.no_numbers': "No numbers for this drive.",
    'drive.btrfs_note': "Btrfs: the used number counts compression, snapshots and shared "
                        "copies, so it won't match the total of the file sizes.",
    'drive.var_note': "Your home and the apps you added live here; the system image is "
                      "read-only and not counted.",
    'drive.ro_note': "Mounted read-only: you can look, Spark Space won't move anything here.",
    'drive.never_note': "Look only. Spark Space never moves anything on this drive.",
    'chip.read_only': "READ-ONLY",
    'chip.not_mounted': "NOT MOUNTED",

    # scanning
    'progress.heading': "SCANNING",
    'progress.files': "FILES",
    'progress.folders': "FOLDERS",
    'progress.size': "SIZE",
    'progress.unreadable': "CAN'T READ",
    'progress.cancel': "Cancel",
    'error.cant_scan_title': "Can't scan",
    'error.cant_scan': "Spark Space can't open {path}: {error}.",
    'error.open_title': "Can't open",
    'error.open': "Nothing could open {path}.",

    # results
    'results.drives': "Back to the drives",
    'results.up': "Up one folder (Backspace)",
    'results.rescan': "Rescan",
    'results.summary': "{size} in {files} files and {folders} folders  ·  {seconds} s",
    'results.unreadable': "{n} folders couldn't be read",
    'results.which': "Which?",
    'results.partial': "The scan was cancelled: these numbers only cover what was read "
                       "before that.",
    'results.other_fs': "{n} other drives mounted inside were left out.",
    'results.btrfs': "Btrfs: sizes here are the space files take before compression; "
                     "snapshots and shared copies aren't shown.",
    'results.df': "The drive reports {used} used; this scan found {found}.",
    'results.read_only': "This drive is mounted read-only: look only.",
    'results.nothing_selected': "Nothing selected",
    'results.select_help': "Click a block or a row. Double-click a folder to go in.",
    'results.files': "{n} files",
    'results.of_folder': "{pct} of this folder",
    'tab.folder': "FOLDER",
    'tab.largest': "LARGEST",
    'tab.types': "TYPES",
    'tab.hints': "HINTS",
    'col.name': "NAME",
    'col.size': "SIZE",
    'col.pct': "%",
    'col.bar': "",
    'col.files': "FILES",
    'col.kind': "TYPE",
    'col.where': "WHERE",
    'col.spot': "SPOT",
    'flag.other_fs': "[other drive]",
    'flag.system': "[system]",
    'flag.unreadable': "[can't read all]",
    'flag.shared': "[hard link, counted once]",
    'flag.link': "[link]",
    'list.more': "+{n} smaller items",
    'list.empty': "Empty",
    'list.no_files': "No files here.",
    'list.working': "Working…",
    'map.small': "{n} small items",
    'largest.all_types': "All types",
    'largest.only': "ONLY {kind}",
    'types.help': "Click a type to list only those files and light them up in the map.",
    'kind.video': "Video",
    'kind.games': "Games",
    'kind.models': "AI models",
    'kind.archives': "Archives and disk images",
    'kind.apps': "Apps and libraries",
    'kind.images': "Images",
    'kind.audio': "Audio",
    'kind.documents': "Documents",
    'kind.other': "Other",
    'unreadable.title': "Folders Spark Space couldn't read",
    'unreadable.body': "These belong to other users or to the system. Their size isn't in "
                       "the totals.",
    'unreadable.more': "and {n} more",

    # actions
    'action.open': "Open",
    'action.show': "Show in folder",
    'action.trash': "Move to trash",
    'trash.confirm_title': "Move {name} to the trash?",
    'trash.confirm': "Move this {what} ({size}) to the trash?",
    'trash.what_file': "file",
    'trash.what_folder': "folder and its {n} files",
    'trash.confirm_detail': "You can put it back from the trash until you empty it. The "
                            "space comes back only after the trash is emptied.",
    'trash.refused_title': "Not moved",
    'trash.failed_title': "Couldn't move it to the trash",
    'trash.failed': "The move failed: {error}.",
    'trash.no_trash': "This drive has no trash folder Spark Space can use, so nothing was "
                      "moved. Spark Space never deletes for good.",
    'refuse.d_drive': "The D: drive is look only. Spark Space never moves anything there.",
    'refuse.protected': "This folder is part of the system or your home itself; it stays.",
    'refuse.in_trash': "This is already in the trash.",
    'refuse.read_only': "This drive is mounted read-only.",
    'refuse.windows_system': "This belongs to Windows; Spark Space leaves it alone.",
    'refuse.gone': "This isn't there any more. Rescan to refresh.",
    'refuse.not_writable': "You don't have permission to move this.",

    # hints
    'hints.intro': "Places that often fill up. Spark Space explains them; it never cleans "
                   "them for you.",
    'hints.none': "Nothing known to clean up here.",
    'hints.copy': "Copy",
    'hint.cache.title': "App caches",
    'hint.cache.body': "~/.cache holds files apps can make again (thumbnails, downloads in "
                       "progress, browser caches). Moving parts of it to the trash is "
                       "usually safe with the apps closed; they rebuild what they need.",
    'hint.trash.title': "The trash",
    'hint.trash.body': "Files you moved to the trash still take space until you empty it, "
                       "from Spark Files or the desktop's trash.",
    'hint.flatpak.title': "Flatpak runtimes",
    'hint.flatpak.body': "Flatpak apps share runtimes, and old ones stay after the apps "
                         "that used them are gone. This command removes only the unused "
                         "ones; run it in a terminal and it lists them first.",
    'hint.containers.title': "Containers and images",
    'hint.containers.body': "Podman and Distrobox images and stopped containers. This "
                            "command removes stopped containers and unused images; it asks "
                            "first. Your Distrobox boxes are containers too, so read the "
                            "list.",
    'hint.journal.title': "System log",
    'hint.journal.body': "The system journal. This command trims it to 500 MB; it needs "
                         "your password.",
    'hint.shadercache.title': "Steam shader cache",
    'hint.shadercache.body': "Compiled shaders Steam keeps per game. Safe to clear with "
                             "Steam closed; games compile them again, so the first runs may "
                             "stutter. Steam can also clear it: Settings, Downloads.",
    'hint.steam_downloading.title': "Steam downloads in progress",
    'hint.steam_downloading.body': "Unfinished Steam downloads and updates. If a download "
                                   "was cancelled for good, Steam usually cleans this "
                                   "itself; pausing and removing it in Steam is the safe "
                                   "way.",
    'hint.app_cache.title': "Flatpak app cache",
    'hint.app_cache.body': "The cache of one Flatpak app. Safe to clear with that app "
                           "closed; it rebuilds what it needs.",
}

FR = {
    'status.ready': "PRÊT",
    'status.scanning': "ANALYSE EN COURS",
    'status.done': "ANALYSÉ EN {seconds} S",
    'status.cancelled': "ANALYSE ANNULÉE, RÉSULTATS PARTIELS",
    'status.error': "QUELQUE CHOSE A ÉCHOUÉ",
    'status.trashed': "{size} MIS À LA CORBEILLE",
    'status.copied': "COMMANDE COPIÉE",

    'home.heading': "OÙ EST PASSÉ L'ESPACE",
    'home.sub': "Choisissez un disque ou un dossier. Spark Space le mesure et montre ce qui "
                "prend la place.",
    'home.scan_drive': "Analyser le disque",
    'home.scan_home': "Analyser le dossier perso",
    'home.home_title': "VOTRE DOSSIER PERSONNEL",
    'home.folder_title': "UN DOSSIER",
    'home.folder_body': "Analysez le dossier de votre choix. Les autres disques montés "
                        "dedans sont laissés de côté.",
    'home.choose': "Choisir un dossier",
    'home.choose_title': "Choisir un dossier à analyser",
    'drive.letter': "Disque {letter}:",
    'drive.sparkos': "SparkOS",
    'drive.measuring': "mesure…",
    'drive.numbers': "{used} utilisés  ·  {free} libres  ·  {total}",
    'drive.no_numbers': "Pas de chiffres pour ce disque.",
    'drive.btrfs_note': "Btrfs : l'espace utilisé tient compte de la compression, des "
                        "instantanés et des copies partagées, il ne correspond donc pas au "
                        "total des tailles de fichiers.",
    'drive.var_note': "Votre dossier perso et les applis ajoutées sont ici ; l'image "
                      "système est en lecture seule et n'est pas comptée.",
    'drive.ro_note': "Monté en lecture seule : vous pouvez regarder, Spark Space n'y "
                     "déplace rien.",
    'drive.never_note': "Consultation seulement. Spark Space ne déplace jamais rien sur ce "
                        "disque.",
    'chip.read_only': "LECTURE SEULE",
    'chip.not_mounted': "NON MONTÉ",

    'progress.heading': "ANALYSE",
    'progress.files': "FICHIERS",
    'progress.folders': "DOSSIERS",
    'progress.size': "TAILLE",
    'progress.unreadable': "ILLISIBLES",
    'progress.cancel': "Annuler",
    'error.cant_scan_title': "Analyse impossible",
    'error.cant_scan': "Spark Space ne peut pas ouvrir {path} : {error}.",
    'error.open_title': "Ouverture impossible",
    'error.open': "Rien n'a pu ouvrir {path}.",

    'results.drives': "Retour aux disques",
    'results.up': "Dossier parent (Retour arrière)",
    'results.rescan': "Réanalyser",
    'results.summary': "{size} dans {files} fichiers et {folders} dossiers  ·  {seconds} s",
    'results.unreadable': "{n} dossiers illisibles",
    'results.which': "Lesquels ?",
    'results.partial': "L'analyse a été annulée : ces chiffres ne couvrent que ce qui a "
                       "été lu avant.",
    'results.other_fs': "{n} autres disques montés dedans ont été laissés de côté.",
    'results.btrfs': "Btrfs : les tailles ici sont celles des fichiers avant compression ; "
                     "les instantanés et les copies partagées n'apparaissent pas.",
    'results.df': "Le disque indique {used} utilisés ; cette analyse a trouvé {found}.",
    'results.read_only': "Ce disque est monté en lecture seule : consultation seulement.",
    'results.nothing_selected': "Rien de sélectionné",
    'results.select_help': "Cliquez un bloc ou une ligne. Double-cliquez un dossier pour y "
                           "entrer.",
    'results.files': "{n} fichiers",
    'results.of_folder': "{pct} de ce dossier",
    'tab.folder': "DOSSIER",
    'tab.largest': "LES PLUS GROS",
    'tab.types': "TYPES",
    'tab.hints': "PISTES",
    'col.name': "NOM",
    'col.size': "TAILLE",
    'col.pct': "%",
    'col.bar': "",
    'col.files': "FICHIERS",
    'col.kind': "TYPE",
    'col.where': "OÙ",
    'col.spot': "ENDROIT",
    'flag.other_fs': "[autre disque]",
    'flag.system': "[système]",
    'flag.unreadable': "[lecture partielle]",
    'flag.shared': "[lien physique, compté une fois]",
    'flag.link': "[lien]",
    'list.more': "+{n} éléments plus petits",
    'list.empty': "Vide",
    'list.no_files': "Aucun fichier ici.",
    'list.working': "Calcul…",
    'map.small': "{n} petits éléments",
    'largest.all_types': "Tous les types",
    'largest.only': "SEULEMENT {kind}",
    'types.help': "Cliquez un type pour ne lister que ces fichiers et les faire ressortir "
                  "sur la carte.",
    'kind.video': "Vidéo",
    'kind.games': "Jeux",
    'kind.models': "Modèles d'IA",
    'kind.archives': "Archives et images disque",
    'kind.apps': "Applis et bibliothèques",
    'kind.images': "Images",
    'kind.audio': "Audio",
    'kind.documents': "Documents",
    'kind.other': "Autre",
    'unreadable.title': "Dossiers que Spark Space n'a pas pu lire",
    'unreadable.body': "Ils appartiennent à d'autres utilisateurs ou au système. Leur "
                       "taille n'est pas dans les totaux.",
    'unreadable.more': "et {n} autres",

    'action.open': "Ouvrir",
    'action.show': "Afficher dans le dossier",
    'action.trash': "Mettre à la corbeille",
    'trash.confirm_title': "Mettre {name} à la corbeille ?",
    'trash.confirm': "Mettre ce {what} ({size}) à la corbeille ?",
    'trash.what_file': "fichier",
    'trash.what_folder': "dossier et ses {n} fichiers",
    'trash.confirm_detail': "Vous pourrez le restaurer depuis la corbeille tant qu'elle "
                            "n'est pas vidée. L'espace ne revient qu'une fois la corbeille "
                            "vidée.",
    'trash.refused_title': "Rien n'a été déplacé",
    'trash.failed_title': "Impossible de le mettre à la corbeille",
    'trash.failed': "Le déplacement a échoué : {error}.",
    'trash.no_trash': "Ce disque n'a pas de corbeille utilisable par Spark Space, donc rien "
                      "n'a été déplacé. Spark Space ne supprime jamais définitivement.",
    'refuse.d_drive': "Le disque D: est en consultation seulement. Spark Space n'y déplace "
                      "jamais rien.",
    'refuse.protected': "Ce dossier fait partie du système ou est votre dossier perso "
                        "lui-même ; il reste.",
    'refuse.in_trash': "C'est déjà dans la corbeille.",
    'refuse.read_only': "Ce disque est monté en lecture seule.",
    'refuse.windows_system': "Ceci appartient à Windows ; Spark Space n'y touche pas.",
    'refuse.gone': "Ceci n'existe plus. Réanalysez pour mettre à jour.",
    'refuse.not_writable': "Vous n'avez pas la permission de déplacer ceci.",

    'hints.intro': "Des endroits qui se remplissent souvent. Spark Space les explique ; il "
                   "ne les nettoie jamais à votre place.",
    'hints.none': "Rien de connu à nettoyer ici.",
    'hints.copy': "Copier",
    'hint.cache.title': "Caches des applis",
    'hint.cache.body': "~/.cache contient des fichiers que les applis peuvent refaire "
                       "(miniatures, téléchargements en cours, caches de navigateur). En "
                       "mettre une partie à la corbeille est en général sans risque, applis "
                       "fermées ; elles refont ce dont elles ont besoin.",
    'hint.trash.title': "La corbeille",
    'hint.trash.body': "Les fichiers mis à la corbeille prennent encore de la place tant "
                       "qu'elle n'est pas vidée, depuis Spark Files ou la corbeille du "
                       "bureau.",
    'hint.flatpak.title': "Runtimes Flatpak",
    'hint.flatpak.body': "Les applis Flatpak partagent des runtimes, et les anciens restent "
                         "après le départ des applis qui s'en servaient. Cette commande "
                         "retire seulement ceux qui ne servent plus ; lancée dans un "
                         "terminal, elle les liste d'abord.",
    'hint.containers.title': "Conteneurs et images",
    'hint.containers.body': "Images Podman et Distrobox et conteneurs arrêtés. Cette "
                            "commande retire les conteneurs arrêtés et les images inutilisées ; "
                            "elle demande d'abord. Vos boîtes Distrobox sont aussi des "
                            "conteneurs, lisez donc la liste.",
    'hint.journal.title': "Journal système",
    'hint.journal.body': "Le journal du système. Cette commande le réduit à 500 Mo ; elle "
                         "demande votre mot de passe.",
    'hint.shadercache.title': "Cache de shaders Steam",
    'hint.shadercache.body': "Les shaders compilés que Steam garde par jeu. Sans risque à "
                             "vider, Steam fermé ; les jeux les recompilent, les premiers "
                             "lancements peuvent donc saccader. Steam peut aussi le vider : "
                             "Paramètres, Téléchargements.",
    'hint.steam_downloading.title': "Téléchargements Steam en cours",
    'hint.steam_downloading.body': "Téléchargements et mises à jour Steam inachevés. Si un "
                                   "téléchargement a été annulé pour de bon, Steam nettoie "
                                   "en général lui-même ; le mettre en pause et le retirer "
                                   "dans Steam est la façon sûre.",
    'hint.app_cache.title': "Cache d'une appli Flatpak",
    'hint.app_cache.body': "Le cache d'une appli Flatpak. Sans risque à vider, cette appli "
                           "fermée ; elle refait ce dont elle a besoin.",
}

_TABLE = FR if ui_language() == 'fr' else EN


def t(key: str, **kw) -> str:
    text = _TABLE.get(key)
    if text is None:
        text = EN.get(key, key)
    return text.format(**kw) if kw else text
