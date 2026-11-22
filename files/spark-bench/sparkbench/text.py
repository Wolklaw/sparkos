"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # header and status
    'status.crashed': "SOMETHING WENT WRONG",
    'status.checking': "CHECKING THE SETUP",
    'status.setup_needed': "SETUP NEEDS A FIX",
    'status.ready': "READY · {key} RECORDS {s} S",
    'status.recording': "RECORDING · {left} LEFT",
    'status.saved': "RECORDING SAVED",
    'status.imported': "IMPORTED {n} FILES",
    'status.imported_one': "IMPORTED 1 FILE",
    'status.exported': "SAVED {name}",
    'status.fix_done': "FIX DONE",
    'status.undo_done': "UNDO DONE",
    'tab.setup': "SETUP",
    'tab.recordings': "RECORDINGS",
    'tab.compare': "COMPARE",

    # start and stop alerts (sound and notification)
    'alert.started': "Recording started",
    'alert.started_body': "MangoHud is recording for {s} seconds.",
    'alert.stopped': "Recording stopped",
    'alert.stopped_body': "The run is saved. Spark Bench has its numbers.",

    # setup
    'setup.title': "MangoHud setup",
    'setup.intro': "Spark Bench reads the frame times MangoHud writes while a game runs. "
                   "These checks show whether MangoHud can record in your games. Fix "
                   "writes only the lines listed before you confirm, and Undo puts back "
                   "what was there.",
    'setup.checking': "Checking…",
    'setup.hotkey': "Record key",
    'setup.duration': "Seconds",
    'setup.folder': "Recordings folder",
    'setup.change': "Change",
    'setup.folder_pick': "Where MangoHud saves recordings",
    'setup.hotkey_help': "The key is written the way MangoHud reads it: Control_L+F11 is "
                         "left Ctrl and F11. Press it in a game to start a recording; it stops "
                         "by itself after the seconds above, or press it again.",
    'setup.fix': "Fix",
    'setup.undo': "Undo",
    'setup.check': "Check again",

    'check.host': "MangoHud",
    'check.host_ok': "Installed on this PC.",
    'check.host_missing': "Not found on this PC. SparkOS includes it; on another system, "
                          "install the mangohud package.",
    'check.steam': "Steam",
    'check.steam_ok': "Flatpak Steam, runtime {branch}.",
    'check.steam_missing': "Flatpak Steam is not installed.",
    'check.no_flatpak': "Flatpak is not installed, so there is no Flatpak Steam to check.",
    'check.layer': "Layer for Steam",
    'check.layer_ok': "The MangoHud layer for runtime {branch} is installed.",
    'check.layer_missing': "Steam runs on runtime {branch}, but the MangoHud layer is "
                           "installed for: {have}. Games in Steam can't load MangoHud "
                           "without it.",
    'check.install_layer': "Install from Flathub",
    'check.none': "none",
    'check.env': "On in Steam",
    'check.env_ok': "MANGOHUD=1 is set in your Flatpak override for Steam.",
    'check.env_ok_system': "MANGOHUD=1 is set in the system-wide Flatpak override for Steam.",
    'check.env_missing': "MANGOHUD=1 is not set for Flatpak Steam, so games start without "
                         "MangoHud. Fix sets it for your user only.",
    'check.config_steam': "Config (Steam)",
    'check.config_host': "Config (this PC)",
    'check.config_ok': "{path}: {key} records {s} s into {folder}.",
    'check.config_missing': "{path} needs: {lines}",
    'check.config_none': "Config",
    'check.config_none_help': "Neither MangoHud nor Flatpak Steam was found, so there is no "
                              "config to check.",
    'check.native': "Other games",
    'check.native_help': "Games outside Flatpak Steam load MangoHud only when started with it: "
                         "add  MANGOHUD=1 %command%  to a game's launch options, or start it "
                         "with  mangohud <game>. Spark Bench doesn't change those.",

    'fix.title': "Apply these changes?",
    'fix.detail': "Nothing else is changed. Undo puts each file back as it is now.",
    'fix.file': "Write in {path}:",
    'fix.folder': "Create the folder {path}",
    'fix.override': "Add to your Flatpak override for Steam:",
    'fix.nothing': "Nothing to fix.",
    'fix.done': "Done.",
    'fix.restart_steam': "Restart Steam so games pick it up.",
    'fix.failed': "Part of the fix didn't work. Undo still puts back what was there.\n{error}",

    'undo.title': "Put things back?",
    'undo.detail': "This restores what was there before Fix.",
    'undo.changed': "(*) This file changed after the fix. Undo replaces those later edits too.",
    'undo.done': "Put back as before.",
    'undo.failed': "Undo didn't finish.\n{error}",
    'undo.restore_file': "restore {path}",
    'undo.remove_file': "remove {path}",
    'undo.remove_folder': "remove {path} (if empty)",
    'undo.uninstall': "uninstall {ref}",

    'layer.title': "Install the MangoHud layer?",
    'layer.body': "flatpak install --user flathub {ref}",
    'layer.detail': "This is the MangoHud Vulkan layer that Flathub publishes for Flatpak "
                    "apps; it is not made by Spark Bench. It goes in your user installation "
                    "and Undo uninstalls it.",
    'layer.working': "Installing from Flathub…",
    'layer.done': "The layer is installed. Restart Steam so games pick it up.",
    'layer.failed': "The install didn't work.\n{error}",

    # alerts
    'alerts.title': "Alerts",
    'alerts.intro': "While Spark Bench is open, it plays a sound and shows a notification when "
                    "a recording starts and when it stops.",
    'alerts.sound': "Sound",
    'alerts.background': "Also when closed",
    'alerts.try': "Try it",
    'alerts.background_help': "Also when closed: a small watcher starts with your session "
                              "(a systemd user service) and gives the same alerts with the "
                              "window closed. Turning it off removes the service.",
    'alerts.background_on': "The background watcher is on.",
    'alerts.background_off': "The background watcher is off and its service file is removed.",
    'alerts.background_failed': "The background watcher couldn't be changed: {error}",

    # recordings
    'runs.title': "Recordings",
    'runs.import': "Import Windows CSVs",
    'runs.import_title': "PresentMon CSVs recorded on Windows",
    'runs.add_folder': "Add folder",
    'runs.folder_title': "A folder with recordings",
    'runs.csv_files': "CSV files",
    'runs.all_files': "All files",
    'runs.refused_title': "Not a recording",
    'runs.refused': "These files have no MangoHud or PresentMon frame times: {names}",
    'runs.col_run': "Run",
    'runs.col_system': "System",
    'runs.col_avg': "Avg",
    'runs.col_low1': "1% low",
    'runs.col_low01': "0.1% low",
    'runs.col_note': "Note",
    'runs.count': "{n} runs",
    'runs.count_one': "1 run",
    'runs.recording': "recording",
    'runs.reading': "reading…",
    'runs.unreadable': "unreadable",
    'runs.left_out': "left out",
    'runs.trimmed': "trimmed",
    'runs.empty': "No recordings yet. Press the record key in a game, import Windows "
                  "PresentMon CSVs, or add a folder that has recordings.",
    'runs.pick': "Pick a run to see its numbers, or a game to rename it.",
    'runs.recording_help': "MangoHud is still writing this recording.",
    'runs.unreadable_help': "This file can't be read: {error}",
    'runs.per_second': "FPS each second",
    'runs.strip_top': "top {fps} FPS",
    'runs.trim': "Leave out seconds",
    'runs.trim_start': "Start",
    'runs.trim_end': "End",
    'runs.trim_help': "The recording is {total} long. Trimmed seconds are dim above and "
                      "don't count.",
    'runs.counted': "Counts in compare",
    'runs.open_folder': "Open folder",
    'runs.game': "Game",
    'runs.game_line': "{system}: {counted} of {n} counted",
    'runs.programs': "Recorded as: {names}",
    'runs.rename': "Game name",
    'runs.rename_button': "Rename",
    'runs.rename_help': "Give two games the same name to put them together, for example "
                        "when Windows names the game's program differently.",

    'stat.avg': "Avg FPS",
    'stat.low1': "1% low",
    'stat.low01': "0.1% low",
    'stat.duration': "Length",
    'stat.frames': "Frames",
    'stat.worst': "Worst frame",
    'stat.worst_value': "{ms} ms",

    # compare
    'compare.title': "Compare",
    'compare.export': "Export CSV",
    'compare.export_title': "Save the summary",
    'compare.baseline': "Against",
    'compare.base_tag': "base",
    'compare.runs': "{n} runs",
    'compare.runs_one': "1 run",
    'compare.reading': "Reading {n} recordings…",
    'compare.empty': "Nothing to compare yet. Counted runs show here once they are read.",
    'compare.no_base': "No counted {system} runs for this game.",
    'compare.method': "Each number is the average over a system's counted runs. A 1% low is "
                      "the average of the slowest 1% of frames, as FPS (0.1% the same with the "
                      "slowest 0.1%). MangoHud's own summary and some other tools use the 99th "
                      "percentile frame time instead, which gives a slightly higher number.",

    # command line
    'cli.help': "Spark Bench: MangoHud setup, start and stop alerts, and benchmark results.",
    'cli.help_tab': "open on this tab",
    'cli.help_watch': "watch for recordings with no window (used by the background service)",
    'cli.help_self_test': "check this install and exit",
    'cli.test_ok': "Self-test passed.",
    'cli.test_failed': "Self-test failed.",
    'cli.missing': "missing",
    'cli.found': "found",
    'cli.watching': "Watching: {folders}",
}

FR = {
    'status.crashed': "QUELQUE CHOSE A MAL TOURNÉ",
    'status.checking': "VÉRIFICATION EN COURS",
    'status.setup_needed': "LA CONFIG DEMANDE UNE CORRECTION",
    'status.ready': "PRÊT · {key} ENREGISTRE {s} S",
    'status.recording': "ENREGISTREMENT · ENCORE {left}",
    'status.saved': "ENREGISTREMENT SAUVEGARDÉ",
    'status.imported': "{n} FICHIERS IMPORTÉS",
    'status.imported_one': "1 FICHIER IMPORTÉ",
    'status.exported': "{name} SAUVEGARDÉ",
    'status.fix_done': "CORRECTION FAITE",
    'status.undo_done': "ANNULATION FAITE",
    'tab.setup': "CONFIG",
    'tab.recordings': "ENREGISTREMENTS",
    'tab.compare': "COMPARER",

    'alert.started': "Enregistrement commencé",
    'alert.started_body': "MangoHud enregistre pendant {s} secondes.",
    'alert.stopped': "Enregistrement terminé",
    'alert.stopped_body': "La séance est sauvegardée. Spark Bench a ses chiffres.",

    'setup.title': "Configuration de MangoHud",
    'setup.intro': "Spark Bench lit les temps d'image que MangoHud écrit pendant qu'un jeu "
                   "tourne. Ces vérifications montrent si MangoHud peut enregistrer dans vos "
                   "jeux. Corriger écrit seulement les lignes affichées avant votre accord, "
                   "et Annuler remet ce qui était là.",
    'setup.checking': "Vérification…",
    'setup.hotkey': "Touche d'enregistrement",
    'setup.duration': "Secondes",
    'setup.folder': "Dossier des enregistrements",
    'setup.change': "Changer",
    'setup.folder_pick': "Où MangoHud sauvegarde les enregistrements",
    'setup.hotkey_help': "La touche s'écrit comme MangoHud la lit : Control_L+F11 veut dire "
                         "Ctrl gauche et F11. Appuyez dessus dans un jeu pour commencer un "
                         "enregistrement ; il s'arrête seul après les secondes ci-dessus, ou "
                         "appuyez de nouveau.",
    'setup.fix': "Corriger",
    'setup.undo': "Annuler",
    'setup.check': "Revérifier",

    'check.host': "MangoHud",
    'check.host_ok': "Installé sur ce PC.",
    'check.host_missing': "Introuvable sur ce PC. SparkOS l'inclut ; sur un autre système, "
                          "installez le paquet mangohud.",
    'check.steam': "Steam",
    'check.steam_ok': "Steam en Flatpak, runtime {branch}.",
    'check.steam_missing': "Steam en Flatpak n'est pas installé.",
    'check.no_flatpak': "Flatpak n'est pas installé, donc pas de Steam Flatpak à vérifier.",
    'check.layer': "Couche pour Steam",
    'check.layer_ok': "La couche MangoHud pour le runtime {branch} est installée.",
    'check.layer_missing': "Steam tourne sur le runtime {branch}, mais la couche MangoHud est "
                           "installée pour : {have}. Sans elle, les jeux de Steam ne peuvent "
                           "pas charger MangoHud.",
    'check.install_layer': "Installer depuis Flathub",
    'check.none': "aucun",
    'check.env': "Actif dans Steam",
    'check.env_ok': "MANGOHUD=1 est défini dans votre override Flatpak pour Steam.",
    'check.env_ok_system': "MANGOHUD=1 est défini dans l'override Flatpak de tout le système "
                           "pour Steam.",
    'check.env_missing': "MANGOHUD=1 n'est pas défini pour Steam en Flatpak, donc les jeux "
                         "démarrent sans MangoHud. Corriger le définit pour votre "
                         "utilisateur seulement.",
    'check.config_steam': "Config (Steam)",
    'check.config_host': "Config (ce PC)",
    'check.config_ok': "{path} : {key} enregistre {s} s dans {folder}.",
    'check.config_missing': "{path} demande : {lines}",
    'check.config_none': "Config",
    'check.config_none_help': "Ni MangoHud ni Steam en Flatpak n'ont été trouvés, donc il n'y "
                              "a pas de config à vérifier.",
    'check.native': "Autres jeux",
    'check.native_help': "Les jeux hors de Steam Flatpak chargent MangoHud seulement s'ils "
                         "démarrent avec lui : ajoutez  MANGOHUD=1 %command%  aux options de "
                         "lancement du jeu, ou lancez-le avec  mangohud <jeu>. Spark Bench ne "
                         "touche pas à ces réglages.",

    'fix.title': "Appliquer ces changements ?",
    'fix.detail': "Rien d'autre n'est modifié. Annuler remet chaque fichier comme il est "
                  "maintenant.",
    'fix.file': "Écrire dans {path} :",
    'fix.folder': "Créer le dossier {path}",
    'fix.override': "Ajouter à votre override Flatpak pour Steam :",
    'fix.nothing': "Rien à corriger.",
    'fix.done': "C'est fait.",
    'fix.restart_steam': "Redémarrez Steam pour que les jeux en tiennent compte.",
    'fix.failed': "Une partie de la correction n'a pas marché. Annuler remet quand même ce qui "
                  "était là.\n{error}",

    'undo.title': "Tout remettre comme avant ?",
    'undo.detail': "Ceci remet ce qui était là avant Corriger.",
    'undo.changed': "(*) Ce fichier a changé après la correction. Annuler remplace aussi ces "
                    "modifications.",
    'undo.done': "Remis comme avant.",
    'undo.failed': "L'annulation n'est pas allée au bout.\n{error}",
    'undo.restore_file': "remettre {path}",
    'undo.remove_file': "supprimer {path}",
    'undo.remove_folder': "supprimer {path} (s'il est vide)",
    'undo.uninstall': "désinstaller {ref}",

    'layer.title': "Installer la couche MangoHud ?",
    'layer.body': "flatpak install --user flathub {ref}",
    'layer.detail': "C'est la couche Vulkan de MangoHud que Flathub publie pour les apps "
                    "Flatpak ; elle n'est pas faite par Spark Bench. Elle va dans votre "
                    "installation utilisateur et Annuler la désinstalle.",
    'layer.working': "Installation depuis Flathub…",
    'layer.done': "La couche est installée. Redémarrez Steam pour que les jeux en tiennent "
                  "compte.",
    'layer.failed': "L'installation n'a pas marché.\n{error}",

    'alerts.title': "Alertes",
    'alerts.intro': "Quand Spark Bench est ouvert, il joue un son et affiche une notification "
                    "quand un enregistrement commence et quand il s'arrête.",
    'alerts.sound': "Son",
    'alerts.background': "Aussi fermé",
    'alerts.try': "Essayer",
    'alerts.background_help': "Aussi fermé : un petit veilleur démarre avec votre session "
                              "(un service utilisateur systemd) et donne les mêmes alertes "
                              "fenêtre fermée. Le désactiver supprime le service.",
    'alerts.background_on': "Le veilleur en arrière-plan est actif.",
    'alerts.background_off': "Le veilleur en arrière-plan est arrêté et son fichier de "
                             "service est supprimé.",
    'alerts.background_failed': "Le veilleur en arrière-plan n'a pas pu être changé : {error}",

    'runs.title': "Enregistrements",
    'runs.import': "Importer des CSV Windows",
    'runs.import_title': "CSV PresentMon enregistrés sous Windows",
    'runs.add_folder': "Ajouter un dossier",
    'runs.folder_title': "Un dossier avec des enregistrements",
    'runs.csv_files': "Fichiers CSV",
    'runs.all_files': "Tous les fichiers",
    'runs.refused_title': "Pas un enregistrement",
    'runs.refused': "Ces fichiers n'ont pas de temps d'image MangoHud ou PresentMon : {names}",
    'runs.col_run': "Séance",
    'runs.col_system': "Système",
    'runs.col_avg': "Moy.",
    'runs.col_low1': "1 % bas",
    'runs.col_low01': "0,1 % bas",
    'runs.col_note': "Note",
    'runs.count': "{n} séances",
    'runs.count_one': "1 séance",
    'runs.recording': "en cours",
    'runs.reading': "lecture…",
    'runs.unreadable': "illisible",
    'runs.left_out': "exclue",
    'runs.trimmed': "coupée",
    'runs.empty': "Aucun enregistrement pour l'instant. Appuyez sur la touche d'enregistrement "
                  "dans un jeu, importez des CSV PresentMon de Windows, ou ajoutez un dossier "
                  "qui contient des enregistrements.",
    'runs.pick': "Choisissez une séance pour voir ses chiffres, ou un jeu pour le renommer.",
    'runs.recording_help': "MangoHud écrit encore cet enregistrement.",
    'runs.unreadable_help': "Ce fichier ne peut pas être lu : {error}",
    'runs.per_second': "IPS chaque seconde",
    'runs.strip_top': "max {fps} IPS",
    'runs.trim': "Retirer des secondes",
    'runs.trim_start': "Début",
    'runs.trim_end': "Fin",
    'runs.trim_help': "L'enregistrement dure {total}. Les secondes retirées sont pâles "
                      "ci-dessus et ne comptent pas.",
    'runs.counted': "Compte dans la comparaison",
    'runs.open_folder': "Ouvrir le dossier",
    'runs.game': "Jeu",
    'runs.game_line': "{system} : {counted} sur {n} comptées",
    'runs.programs': "Enregistré sous : {names}",
    'runs.rename': "Nom du jeu",
    'runs.rename_button': "Renommer",
    'runs.rename_help': "Donnez le même nom à deux jeux pour les réunir, par exemple quand "
                        "Windows nomme le programme du jeu autrement.",

    'stat.avg': "IPS moy.",
    'stat.low1': "1 % bas",
    'stat.low01': "0,1 % bas",
    'stat.duration': "Durée",
    'stat.frames': "Images",
    'stat.worst': "Pire image",
    'stat.worst_value': "{ms} ms",

    'compare.title': "Comparer",
    'compare.export': "Exporter en CSV",
    'compare.export_title': "Sauvegarder le résumé",
    'compare.baseline': "Contre",
    'compare.base_tag': "base",
    'compare.runs': "{n} séances",
    'compare.runs_one': "1 séance",
    'compare.reading': "Lecture de {n} enregistrements…",
    'compare.empty': "Rien à comparer pour l'instant. Les séances comptées s'affichent ici une "
                     "fois lues.",
    'compare.no_base': "Aucune séance {system} comptée pour ce jeu.",
    'compare.method': "Chaque chiffre est la moyenne des séances comptées d'un système. Le "
                      "1 % bas est la moyenne du 1 % des images les plus lentes, en IPS (le "
                      "0,1 % bas, pareil avec 0,1 %). Le résumé de MangoHud et d'autres outils "
                      "prennent plutôt le 99e centile du temps d'image, ce qui donne un "
                      "chiffre un peu plus haut.",

    'cli.help': "Spark Bench : configuration de MangoHud, alertes de début et de fin, et "
                "résultats de benchmark.",
    'cli.help_tab': "ouvrir sur cet onglet",
    'cli.help_watch': "surveiller les enregistrements sans fenêtre (utilisé par le service "
                      "en arrière-plan)",
    'cli.help_self_test': "vérifier cette installation et quitter",
    'cli.test_ok': "Auto-test réussi.",
    'cli.test_failed': "Auto-test échoué.",
    'cli.missing': "absent",
    'cli.found': "trouvé",
    'cli.watching': "Surveillance : {folders}",
}

_TABLE = FR if ui_language() == 'fr' else EN


def t(key: str, /, **kw) -> str:
    text = _TABLE.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text


def tn(key: str, n: int, /, **kw) -> str:
    """t() for a count: key_one when n is 1, else key with {n} filled in."""
    if n == 1 and key + '_one' in EN:
        return t(key + '_one', **kw)
    return t(key, n=n, **kw)
