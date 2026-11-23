"""Every user-facing string, in English and French. tr('key', name=...) formats one; a key
missing from French falls back to English.

The language comes from the PC's locale (LC_ALL, then LC_MESSAGES, then LANG: French when it
starts with "fr"), and SPARK_LANG=en or SPARK_LANG=fr overrides it.
"""

import os
import time
from typing import Dict

EN: Dict[str, str] = {
    # sources and launchers
    'src_all': "ALL", 'src_steam': "STEAM", 'src_epic': "EPIC", 'src_gog': "GOG",
    'src_amazon': "AMAZON", 'src_lutris': "LUTRIS", 'src_itch': "ITCH",
    'src_bottles': "BOTTLES", 'src_minecraft': "MINECRAFT", 'src_prism': "PRISM",
    'src_own': "MINE",
    'launcher_steam': "Steam", 'launcher_heroic': "Heroic", 'launcher_lutris': "Lutris",
    'launcher_itch': "itch", 'launcher_bottles': "Bottles",
    'launcher_minecraft': "Minecraft Launcher", 'launcher_prism': "Prism Launcher",
    'launcher_own': "Spark Games",
    'store_epic': "Epic Games Store", 'store_gog': "GOG", 'store_amazon': "Amazon Games",
    'flatpak': "Flatpak", 'shortcut': "non-Steam shortcut",

    # header and library
    'title': "SPARK GAMES", 'ready': "READY", 'scanning': "SCANNING", 'games_n': "{n} GAMES",
    'game_1': "1 GAME", 'starting': "STARTING {title}", 'scan_problem': "COULDN'T READ {names}",
    'went_wrong': "SOMETHING WENT WRONG", 'anticheat_badge': "ANTI-CHEAT",
    'sort_recent': "RECENT", 'sort_title': "A–Z",
    'search_hint': "Search  /",
    'tip_grid': "Covers", 'tip_list': "List", 'tip_settings': "Settings", 'tip_rescan': "Scan again",
    'tip_big': "Big screen (F11)",
    'add_game': "Add a game",
    'no_match': "Nothing matches “{query}”.",
    'none_in_filter': "No games from this launcher.",
    'never_played': "Not played yet",
    'scanning_first': "Looking for games…",
    'pad_on': "CONTROLLER: {name}", 'pad_off': "CONTROLLER DISCONNECTED",

    # empty state
    'empty_title': "NO GAMES FOUND",
    'empty_body': ("Spark Games lists the games you installed with Steam, Heroic (Epic, GOG, "
                   "Amazon), Lutris, itch, Bottles or a Minecraft launcher, and programs you add "
                   "yourself. None of these has installed games for this account yet."),
    'empty_store': "SparkOS doesn't include a launcher. Install one from the Store, then come "
                   "back here.",
    'open_welcome': "Open Spark Welcome", 'open_store': "Open the Store",

    # game page
    'play': "Play", 'back': "Back", 'open_folder': "Open folder",
    'fact_launcher': "LAUNCHER", 'fact_playtime': "PLAYTIME", 'fact_last': "LAST PLAYED",
    'fact_folder': "INSTALL FOLDER", 'fact_spark': "PLAYED FROM SPARK GAMES",
    'no_folder': "Unknown",
    'perf_title': "PERFORMANCE",
    'perf_mangohud': "FPS overlay (MangoHud)", 'perf_gamemode': "GameMode",
    'perf_own': "Applied when Spark Games starts this game.",
    'perf_steam': ("Steam starts this game, and Spark Games doesn't change Steam's settings. "
                   "In Steam, open the game's Properties and paste this into Launch options:"),
    'perf_heroic': "Heroic starts this game. Turn these on in Heroic's settings for the game.",
    'perf_lutris': "Lutris starts this game. Turn these on in Lutris's options for the game.",
    'perf_itch': "The itch app starts this game, and Spark Games doesn't change its settings.",
    'perf_bottles': "Bottles starts this program. Turn these on in the bottle's settings in "
                    "Bottles.",
    'perf_minecraft': "The Minecraft Launcher starts this game, and Spark Games doesn't change "
                      "its settings.",
    'perf_prism': "Prism Launcher starts this game. Turn these on in Prism's settings.",
    'copy': "Copy", 'copied': "COPIED",
    'no_gamemode': "GameMode isn't installed, so that switch does nothing.",
    'remove': "Remove from Spark Games",
    'remove_confirm': "Remove “{title}” from Spark Games? Its files stay where they are.",
    'ac_Denied': ("Kernel anti-cheat: listed as Denied. The developer doesn't allow Linux "
                  "players, so online play will probably not work."),
    'ac_Broken': ("Kernel anti-cheat: listed as Broken. Its anti-cheat doesn't work on Linux "
                  "yet, so online play will probably not work."),
    'ac_source': "Source: AreWeAntiCheatYet ({site}), checked {when}.",

    # add a game
    'add_title': "ADD A GAME",
    'add_body': ("Pick the program that starts the game: a Linux program, or a Windows .exe. "
                 "Windows games run with Proton through umu-run."),
    'add_choose': "Choose program", 'add_name': "NAME", 'add_program': "PROGRAM",
    'add_windows': "Windows program (Proton)", 'add_save': "Add", 'cancel': "Cancel",
    'add_none': "No program chosen yet.",
    'no_umu': ("umu-run isn't installed, so Windows games can't start from Spark Games. "
               "Bottles, a separate app from Flathub (not made by SparkOS), can run them."),
    'get_bottles': "Get Bottles from Flathub",

    # settings
    'settings_title': "SETTINGS",
    'set_after_launch': "WHEN A GAME STARTS",
    'after_stay': "STAY OPEN", 'after_minimize': "MINIMIZE", 'after_close': "CLOSE",
    'set_online': "ONLINE",
    'set_anticheat': "Anti-cheat warnings",
    'set_anticheat_note': ("Downloads the public AreWeAntiCheatYet list ({site}) at most once a "
                           "week. Nothing about your games is sent."),
    'set_found': "LAUNCHERS FOUND",
    'set_none': "None.",
    'set_pads': "CONTROLLERS",
    'set_pads_none': "None connected.",
    'set_pads_note': ("Read only while the Spark Games window is in front. D-pad or left stick "
                      "moves, A plays, B goes back, Y searches, Start opens the game page, "
                      "Guide opens the big screen."),
    'set_big': "Open the big screen",
    'set_files': "Settings: {config}   Playtime: {data}   Cache: {cache}",

    # big screen
    'big_recent': "KEEP PLAYING", 'big_all': "ALL GAMES",
    'big_play': "PLAY", 'big_back': "BACK", 'big_exit': "EXIT", 'big_search': "SEARCH",
    'big_page': "GAME PAGE", 'big_filter': "ROW", 'big_type': "TYPE",
    'big_keys': "Enter play · Esc back · / search · Space game page",
    'big_space': "SPACE", 'big_delete': "DELETE", 'big_clear': "CLEAR", 'big_done': "DONE",
    'big_search_for': "Search: {query}",
    'big_empty': "No games yet. Leave the big screen to add one.",

    # errors
    'err_missing_program': "Can't start this game: {detail} isn't installed.",
    'err_missing_file': "Can't start this game: the program is gone ({detail}).",
    'err_not_executable': "Can't start this game: {detail} isn't marked as a program.",
    'err_no_umu': "Can't start this Windows game: umu-run isn't installed.",
    'err_start_failed': "Can't start this game: {detail}",
    'err_unknown_source': "Can't start this game: unknown launcher {detail}.",
    'err_unexpected': "Something went wrong: {detail}",

    # stores and launchers
    'src_battlenet': 'BATTLE.NET',
    'src_ea': 'EA',
    'src_ubisoft': 'UBISOFT',
    'src_rockstar': 'ROCKSTAR',
    'launcher_spark': 'Spark Games',
    'launcher_battlenet': 'Battle.net',
    'launcher_ea': 'EA app',
    'launcher_ubisoft': 'Ubisoft Connect',
    'launcher_rockstar': 'Rockstar Games Launcher',
    'perf_spark': 'Spark Games starts this game with Proton (umu-run). MangoHud and GameMode apply when you turn them on here. GE-Proton replaces the default UMU-Proton for this game.',
    'perf_ge_proton': 'GE-Proton',
    'perf_cloud_saves': 'Cloud saves',
    'scope_installed': 'INSTALLED',
    'scope_all': 'ALL OWNED',
    'not_installed': 'NOT INSTALLED',
    'install_in_steam': "Install in Steam", 'steam_installing': "STEAM: INSTALL {title}",
    'install': 'Install',
    'install_to': 'Install to {path}',
    'install_change': 'Change',
    'install_checking': 'Asking the store for the size…',
    'install_confirm': 'Install {title}?\n\nDownload: {size}\nOn disk: {disk}\nFree space: {free}\nFolder: {path}',
    'size_unknown': 'unknown',
    'update': 'Update',
    'verify': 'Verify files',
    'uninstall_btn': 'Uninstall',
    'uninstall_confirm': 'Delete {title} and its files from {path}? Saves kept in the cloud stay there.',
    'uninstall_forget': "Stop using {title} in Spark Games? Its files in {path} are not deleted; Heroic's records are not touched.",
    'uninstalling': 'Uninstalling…',
    'update_first': '{title} has an update. Update it first? Choose No to play now.',
    'job_queued': 'Waiting for another install on this disk',
    'job_fetching_client': 'Downloading the store client',
    'job_fetching_installer': 'Downloading the installer',
    'job_installer_open': 'The installer window is open. Finish it there.',
    'job_install': 'Installing',
    'job_update': 'Updating',
    'job_verify': 'Verifying',
    'job_launcher': 'Installing',
    'job_paused': 'paused',
    'job_eta': '{eta} left',
    'job_pause': 'Pause',
    'job_resume': 'Resume',
    'job_cancel': 'Cancel',
    'job_cancelled': 'Cancelled. Installing again carries on from what was downloaded.',
    'owned_problem': 'Could not refresh the games you own on {names}.',
    'takeover_ask': "Spark Games found {count} games that Heroic installed. Use them here? They are not downloaded again, and Heroic's files are not changed or deleted.",
    'takeover_found': '{count} games installed by Heroic can be used here without downloading again.',
    'takeover_btn': "Use Heroic's games",
    'takeover_working': "Using Heroic's games…",
    'takeover_done': 'Heroic games added: {count}. Could not add: {failed}.',
    'stores_title': 'Stores and launchers',
    'stores_open': 'Accounts and launchers',
    'stores_note': "Sign in to a store and Spark Games lists the games you own there, and installs and starts them itself. Each is that company's own account; Spark Games is not made by or approved by them.",
    'accounts': 'ACCOUNTS',
    'signed_in': 'Signed in',
    'signed_in_as': 'Signed in as {name}',
    'not_signed_in': 'Not signed in',
    'sign_in': 'Sign in',
    'sign_out': 'Sign out',
    'sign_out_confirm': 'Sign out of {store}? Installed games stay installed.',
    'signin_preparing': 'Getting the {store} sign-in ready…',
    'signin_how_epic': 'Your browser opened the Epic page. Sign in, then copy the whole text of the page (it contains authorizationCode) and paste it here.',
    'signin_how_gog': "Your browser opened the GOG page. Sign in; it ends on a blank page. Copy that page's address from the address bar and paste it here.",
    'signin_how_amazon': "Your browser opened the Amazon page. Sign in; it then shows Amazon's store (amazon.com, whatever your country). That is expected: copy that page's whole address from the address bar and paste it here. It holds the sign-in code.",
    'signin_finish': 'Finish',
    'signin_open_again': 'Open the page again',
    'signin_working': 'Signing in…',
    'signin_done': 'Signed in to {store}.',
    'signin_argv_note': 'While the store program checks the code, the code is visible to other programs of your own user in the process list for a moment.',
    'signin_bad_code': 'No sign-in code found in what you pasted.',
    'signin_timeout': 'The store did not answer in time. Try again.',
    'signin_failed': 'The store did not accept the code. Codes are used once and expire quickly; start the sign-in again.',
    'launchers_title': 'LAUNCHERS',
    'launchers_note': "Windows launchers get their own Wine folder, and their installer runs through Proton. The Minecraft Launcher is Mojang's Linux version and needs neither. Spark Games downloads each one from the company's site; it cannot be checked against a fixed checksum, because they replace it in place.",
    'launcher_add': 'Add',
    'launcher_remove': 'Remove launcher',
    'launcher_added': 'Added',
    'launcher_not_added': 'Not added',
    'launcher_add_confirm': 'Download the {name} installer from its official address and run it? The installer opens its own window.',
    'launcher_add_confirm_native': 'Download the {name} from its official address and install it? Minecraft: Java Edition then shows in your library. You sign in with your Microsoft account in the launcher.',
    'launcher_remove_native_confirm': 'Remove the {name}? Your worlds and settings in ~/.minecraft are kept.',
    'launcher_remove_confirm': 'Remove {name} from Spark Games? A folder Spark Games made for it is deleted; one it only borrowed from Lutris is kept.',
    'launcher_use_lutris': "Use Lutris's",
    'launcher_lutris_confirm': 'Use the {name} that Lutris installed in {prefix}? Nothing is copied or moved, but Spark Games starts it with its own Proton, which can change that folder.',
    'err_not_installed': "This game isn't installed.",
    'err_no_client': 'The store program ({detail}) could not be downloaded.',
    'err_store_launch': 'The store would not start the game: {detail}',
    'err_uninstall': 'Could not uninstall the game.',
    'err_uninstall_outside': 'Not deleted: the folder is outside the folders Spark Games installs into. Remove it by hand if you want.',
    'err_job_died': 'The install stopped unexpectedly.',
    'err_job_start': 'Could not start the install.',
    'err_job_failed': 'The install failed.',
    'err_space': 'Not enough free disk space.',
    'err_network': 'The download failed: network problem.',
    'err_mismatch': 'The downloaded store program did not match its checksum and was deleted.',
    'err_signin_again': 'The store refused the saved sign-in. Sign in again.',
    'err_installer_host': "The download was sent to an address that isn't the company's. Stopped.",
    'err_installer_bad': 'The downloaded file does not look like the installer. Stopped.',
    'err_launcher_not_found': 'The installer finished but the launcher was not found. Add it again.',
    'err_space_detail': 'Not enough free space: the game needs {need} and {free} is free.',
    'err_client_network': 'The store program could not be downloaded: {detail}',
    'err_client_mismatch': 'The downloaded store program did not match its checksum and was deleted.',
    'err_client_space': 'Not enough free disk space to download the store program.',
    'err_client_unsupported': 'The store programs only exist for 64-bit PCs ({detail}).',
    'err_client_cancelled': 'Cancelled.',
    'err_client_missing': 'The store program ({detail}) is not here yet.',
    'err_client_signin': 'Sign in to the store first.',
    'err_client_list': 'The store would not list your games ({detail}).',

    # time
    'minutes': "{n} min", 'hours': "{h} h", 'hours_minutes': "{h} h {m} min", 'none': "—",
    'today': "Today", 'yesterday': "Yesterday", 'days_ago': "{n} days ago",
}

FR: Dict[str, str] = {
    # sources et lanceurs
    'src_all': "TOUS", 'src_steam': "STEAM", 'src_epic': "EPIC", 'src_gog': "GOG",
    'src_amazon': "AMAZON", 'src_lutris': "LUTRIS", 'src_itch': "ITCH",
    'src_bottles': "BOTTLES", 'src_minecraft': "MINECRAFT", 'src_prism': "PRISM",
    'src_own': "LES MIENS",
    'launcher_steam': "Steam", 'launcher_heroic': "Heroic", 'launcher_lutris': "Lutris",
    'launcher_itch': "itch", 'launcher_bottles': "Bottles",
    'launcher_minecraft': "Minecraft Launcher", 'launcher_prism': "Prism Launcher",
    'launcher_own': "Spark Games",
    'store_epic': "Epic Games Store", 'store_gog': "GOG", 'store_amazon': "Amazon Games",
    'flatpak': "Flatpak", 'shortcut': "raccourci hors Steam",

    # en-tête et bibliothèque
    'title': "SPARK GAMES", 'ready': "PRÊT", 'scanning': "RECHERCHE",
    'games_n': "{n} JEUX", 'game_1': "1 JEU", 'starting': "LANCEMENT : {title}",
    'scan_problem': "IMPOSSIBLE DE LIRE {names}",
    'went_wrong': "UN PROBLÈME EST SURVENU", 'anticheat_badge': "ANTITRICHE",
    'sort_recent': "RÉCENTS", 'sort_title': "A–Z",
    'search_hint': "Rechercher  /",
    'tip_grid': "Pochettes", 'tip_list': "Liste", 'tip_settings': "Paramètres",
    'tip_rescan': "Chercher de nouveau", 'tip_big': "Grand écran (F11)",
    'add_game': "Ajouter un jeu",
    'no_match': "Aucun résultat pour « {query} ».",
    'none_in_filter': "Aucun jeu de ce lanceur.",
    'never_played': "Pas encore joué",
    'scanning_first': "Recherche des jeux…",
    'pad_on': "MANETTE : {name}", 'pad_off': "MANETTE DÉBRANCHÉE",

    # aucun jeu
    'empty_title': "AUCUN JEU TROUVÉ",
    'empty_body': ("Spark Games affiche les jeux installés avec Steam, Heroic (Epic, GOG, "
                   "Amazon), Lutris, itch, Bottles ou un lanceur Minecraft, et les programmes "
                   "que vous ajoutez vous-même. Aucun de ces lanceurs n'a encore installé de jeu "
                   "pour ce compte."),
    'empty_store': ("SparkOS n'inclut pas de lanceur. Installez-en un depuis la Boutique, puis "
                    "revenez ici."),
    'open_welcome': "Ouvrir Spark Welcome", 'open_store': "Ouvrir la Boutique",

    # page du jeu
    'play': "Jouer", 'back': "Retour", 'open_folder': "Ouvrir le dossier",
    'fact_launcher': "LANCEUR", 'fact_playtime': "TEMPS DE JEU", 'fact_last': "DERNIÈRE PARTIE",
    'fact_folder': "DOSSIER D'INSTALLATION", 'fact_spark': "JOUÉ DEPUIS SPARK GAMES",
    'no_folder': "Inconnu",
    'perf_title': "PERFORMANCE",
    'perf_mangohud': "Compteur d'images (MangoHud)", 'perf_gamemode': "GameMode",
    'perf_own': "Appliqué quand Spark Games lance ce jeu.",
    'perf_steam': ("Steam lance ce jeu, et Spark Games ne modifie pas les paramètres de Steam. "
                   "Dans Steam, ouvrez les Propriétés du jeu et collez ceci dans les options "
                   "de lancement :"),
    'perf_heroic': "Heroic lance ce jeu. Activez ces options dans les paramètres du jeu dans "
                   "Heroic.",
    'perf_lutris': "Lutris lance ce jeu. Activez ces options dans les options du jeu dans "
                   "Lutris.",
    'perf_itch': "L'appli itch lance ce jeu, et Spark Games ne modifie pas ses paramètres.",
    'perf_bottles': "Bottles lance ce programme. Activez ces options dans les paramètres de "
                    "la bouteille dans Bottles.",
    'perf_minecraft': "Le Minecraft Launcher lance ce jeu, et Spark Games ne modifie pas ses "
                      "paramètres.",
    'perf_prism': "Prism Launcher lance ce jeu. Activez ces options dans les paramètres de "
                  "Prism.",
    'copy': "Copier", 'copied': "COPIÉ",
    'no_gamemode': "GameMode n'est pas installé, alors cette option ne fait rien.",
    'remove': "Retirer de Spark Games",
    'remove_confirm': ("Retirer « {title} » de Spark Games? Ses fichiers restent où ils "
                       "sont."),
    'ac_Denied': ("Antitriche au niveau du noyau : classé Refusé. Le développeur n'accepte pas "
                  "les joueurs sous Linux, alors le jeu en ligne ne fonctionnera "
                  "probablement pas."),
    'ac_Broken': ("Antitriche au niveau du noyau : classé Brisé. Son antitriche ne fonctionne "
                  "pas encore sous Linux, alors le jeu en ligne ne fonctionnera "
                  "probablement pas."),
    'ac_source': "Source : AreWeAntiCheatYet ({site}), vérifié le {when}.",

    # ajouter un jeu
    'add_title': "AJOUTER UN JEU",
    'add_body': ("Choisissez le programme qui lance le jeu : un programme Linux ou un .exe "
                 "Windows. Les jeux Windows tournent avec Proton par umu-run."),
    'add_choose': "Choisir le programme", 'add_name': "NOM", 'add_program': "PROGRAMME",
    'add_windows': "Programme Windows (Proton)", 'add_save': "Ajouter", 'cancel': "Annuler",
    'add_none': "Aucun programme choisi.",
    'no_umu': ("umu-run n'est pas installé, alors les jeux Windows ne peuvent pas partir "
               "depuis Spark Games. Bottles, une appli distincte sur Flathub (pas faite par "
               "SparkOS), peut les lancer."),
    'get_bottles': "Obtenir Bottles sur Flathub",

    # paramètres
    'settings_title': "PARAMÈTRES",
    'set_after_launch': "QUAND UN JEU DÉMARRE",
    'after_stay': "RESTER OUVERT", 'after_minimize': "RÉDUIRE", 'after_close': "FERMER",
    'set_online': "EN LIGNE",
    'set_anticheat': "Avertissements antitriche",
    'set_anticheat_note': ("Télécharge la liste publique d'AreWeAntiCheatYet ({site}) au plus "
                           "une fois par semaine. Rien sur vos jeux n'est envoyé."),
    'set_found': "LANCEURS TROUVÉS",
    'set_none': "Aucun.",
    'set_pads': "MANETTES",
    'set_pads_none': "Aucune branchée.",
    'set_pads_note': ("Lues seulement quand la fenêtre de Spark Games est au premier plan. La "
                      "croix ou le stick gauche déplace, A joue, B revient, Y cherche, Start "
                      "ouvre la page du jeu, Guide ouvre le grand écran."),
    'set_big': "Ouvrir le grand écran",
    'set_files': "Paramètres : {config}   Temps de jeu : {data}   Cache : {cache}",

    # grand écran
    'big_recent': "CONTINUER", 'big_all': "TOUS LES JEUX",
    'big_play': "JOUER", 'big_back': "RETOUR", 'big_exit': "QUITTER",
    'big_search': "RECHERCHER", 'big_page': "PAGE DU JEU", 'big_filter': "RANGÉE",
    'big_type': "ÉCRIRE",
    'big_keys': "Entrée jouer · Échap retour · / rechercher · Espace page du jeu",
    'big_space': "ESPACE", 'big_delete': "EFFACER", 'big_clear': "VIDER", 'big_done': "OK",
    'big_search_for': "Recherche : {query}",
    'big_empty': "Aucun jeu pour l'instant. Quittez le grand écran pour en ajouter un.",

    # erreurs
    'err_missing_program': "Impossible de lancer ce jeu : {detail} n'est pas installé.",
    'err_missing_file': "Impossible de lancer ce jeu : le programme n'est plus là ({detail}).",
    'err_not_executable': ("Impossible de lancer ce jeu : {detail} n'est pas marqué comme "
                           "programme."),
    'err_no_umu': "Impossible de lancer ce jeu Windows : umu-run n'est pas installé.",
    'err_start_failed': "Impossible de lancer ce jeu : {detail}",
    'err_unknown_source': "Impossible de lancer ce jeu : lanceur inconnu ({detail}).",
    'err_unexpected': "Un problème est survenu : {detail}",

    # boutiques et lanceurs
    'src_battlenet': 'BATTLE.NET',
    'src_ea': 'EA',
    'src_ubisoft': 'UBISOFT',
    'src_rockstar': 'ROCKSTAR',
    'launcher_spark': 'Spark Games',
    'launcher_battlenet': 'Battle.net',
    'launcher_ea': 'EA app',
    'launcher_ubisoft': 'Ubisoft Connect',
    'launcher_rockstar': 'Rockstar Games Launcher',
    'perf_spark': "Spark Games lance ce jeu avec Proton (umu-run). MangoHud et GameMode s'appliquent si vous les activez ici. GE-Proton remplace UMU-Proton, la version par défaut, pour ce jeu.",
    'perf_ge_proton': 'GE-Proton',
    'perf_cloud_saves': 'Sauvegardes cloud',
    'scope_installed': 'INSTALLÉS',
    'scope_all': 'TOUS MES JEUX',
    'not_installed': 'NON INSTALLÉ',
    'install_in_steam': "Installer dans Steam", 'steam_installing': "STEAM : INSTALLER {title}",
    'install': 'Installer',
    'install_to': 'Installer dans {path}',
    'install_change': 'Changer',
    'install_checking': 'Demande de la taille à la boutique…',
    'install_confirm': 'Installer {title} ?\n\nTéléchargement : {size}\nSur le disque : {disk}\nEspace libre : {free}\nDossier : {path}',
    'size_unknown': 'inconnue',
    'update': 'Mettre à jour',
    'verify': 'Vérifier les fichiers',
    'uninstall_btn': 'Désinstaller',
    'uninstall_confirm': 'Supprimer {title} et ses fichiers dans {path} ? Les sauvegardes dans le cloud restent là-bas.',
    'uninstall_forget': 'Ne plus utiliser {title} dans Spark Games ? Ses fichiers dans {path} ne sont pas supprimés et les données de Heroic ne sont pas touchées.',
    'uninstalling': 'Désinstallation…',
    'update_first': "{title} a une mise à jour. La faire d'abord ? Choisissez Non pour jouer tout de suite.",
    'job_queued': "En attente d'une autre installation sur ce disque",
    'job_fetching_client': 'Téléchargement du programme de la boutique',
    'job_fetching_installer': "Téléchargement de l'installeur",
    'job_installer_open': "La fenêtre de l'installeur est ouverte. Terminez-y l'installation.",
    'job_install': 'Installation',
    'job_update': 'Mise à jour',
    'job_verify': 'Vérification',
    'job_launcher': 'Installation',
    'job_paused': 'en pause',
    'job_eta': 'encore {eta}',
    'job_pause': 'Pause',
    'job_resume': 'Reprendre',
    'job_cancel': 'Annuler',
    'job_cancelled': "Annulé. Installer de nouveau reprend là où le téléchargement s'est arrêté.",
    'owned_problem': "Impossible d'actualiser les jeux que vous possédez sur {names}.",
    'takeover_ask': 'Spark Games a trouvé {count} jeux installés par Heroic. Les utiliser ici ? Ils ne sont pas retéléchargés, et les fichiers de Heroic ne sont ni modifiés ni supprimés.',
    'takeover_found': '{count} jeux installés par Heroic peuvent être utilisés ici sans retéléchargement.',
    'takeover_btn': 'Utiliser les jeux de Heroic',
    'takeover_working': 'Ajout des jeux de Heroic…',
    'takeover_done': 'Jeux de Heroic ajoutés : {count}. Non ajoutés : {failed}.',
    'stores_title': 'Boutiques et lanceurs',
    'stores_open': 'Comptes et lanceurs',
    'stores_note': "Connectez-vous à une boutique et Spark Games liste les jeux que vous y possédez, puis les installe et les lance lui-même. Chaque compte est celui de l'entreprise ; Spark Games n'est ni créé ni approuvé par elles.",
    'accounts': 'COMPTES',
    'signed_in': 'Connecté',
    'signed_in_as': 'Connecté : {name}',
    'not_signed_in': 'Non connecté',
    'sign_in': 'Se connecter',
    'sign_out': 'Se déconnecter',
    'sign_out_confirm': 'Se déconnecter de {store} ? Les jeux installés restent installés.',
    'signin_preparing': 'Préparation de la connexion à {store}…',
    'signin_how_epic': 'Votre navigateur a ouvert la page Epic. Connectez-vous, puis copiez tout le texte de la page (il contient authorizationCode) et collez-le ici.',
    'signin_how_gog': "Votre navigateur a ouvert la page GOG. Connectez-vous ; elle finit sur une page blanche. Copiez l'adresse de cette page dans la barre d'adresse et collez-la ici.",
    'signin_how_amazon': "Votre navigateur a ouvert la page Amazon. Connectez-vous ; elle affiche ensuite la boutique Amazon (amazon.com, quel que soit votre pays). C'est normal : copiez l'adresse complète de cette page dans la barre d'adresse et collez-la ici. Elle contient le code de connexion.",
    'signin_finish': 'Terminer',
    'signin_open_again': 'Rouvrir la page',
    'signin_working': 'Connexion…',
    'signin_done': 'Connecté à {store}.',
    'signin_argv_note': 'Pendant que le programme de la boutique vérifie le code, ce code est visible un instant, dans la liste des processus, des autres programmes de votre propre utilisateur.',
    'signin_bad_code': 'Aucun code de connexion dans ce que vous avez collé.',
    'signin_timeout': "La boutique n'a pas répondu à temps. Réessayez.",
    'signin_failed': "La boutique a refusé le code. Un code ne sert qu'une fois et expire vite ; recommencez la connexion.",
    'launchers_title': 'LANCEURS',
    'launchers_note': "Les lanceurs Windows ont chacun leur propre dossier Wine, et leur installeur tourne avec Proton. Le Minecraft Launcher est la version Linux de Mojang et n'a besoin ni de l'un ni de l'autre. Spark Games télécharge chacun sur le site de l'entreprise ; il ne peut pas être vérifié avec une somme de contrôle fixe, car elles le remplacent sur place.",
    'launcher_add': 'Ajouter',
    'launcher_remove': 'Retirer le lanceur',
    'launcher_added': 'Ajouté',
    'launcher_not_added': 'Non ajouté',
    'launcher_add_confirm': "Télécharger l'installeur de {name} à son adresse officielle et l'exécuter ? L'installeur ouvre sa propre fenêtre.",
    'launcher_add_confirm_native': "Télécharger le {name} à son adresse officielle et l'installer ? Minecraft: Java Edition apparaît ensuite dans votre bibliothèque. Vous vous connectez avec votre compte Microsoft dans le lanceur.",
    'launcher_remove_native_confirm': "Retirer le {name} ? Vos mondes et réglages dans ~/.minecraft sont conservés.",
    'launcher_remove_confirm': 'Retirer {name} de Spark Games ? Un dossier créé par Spark Games pour lui est supprimé ; un dossier simplement emprunté à Lutris est conservé.',
    'launcher_use_lutris': 'Utiliser celui de Lutris',
    'launcher_lutris_confirm': "Utiliser {name} installé par Lutris dans {prefix} ? Rien n'est copié ni déplacé, mais Spark Games le lance avec son propre Proton, ce qui peut modifier ce dossier.",
    'err_not_installed': "Ce jeu n'est pas installé.",
    'err_no_client': "Le programme de la boutique ({detail}) n'a pas pu être téléchargé.",
    'err_store_launch': "La boutique n'a pas lancé le jeu : {detail}",
    'err_uninstall': 'Impossible de désinstaller le jeu.',
    'err_uninstall_outside': 'Non supprimé : le dossier est hors des dossiers où Spark Games installe. Supprimez-le à la main si vous le voulez.',
    'err_job_died': "L'installation s'est arrêtée de façon inattendue.",
    'err_job_start': "Impossible de démarrer l'installation.",
    'err_job_failed': "L'installation a échoué.",
    'err_space': "Pas assez d'espace disque libre.",
    'err_network': 'Le téléchargement a échoué : problème de réseau.',
    'err_mismatch': 'Le programme de boutique téléchargé ne correspondait pas à sa somme de contrôle et a été supprimé.',
    'err_signin_again': 'La boutique a refusé la connexion enregistrée. Reconnectez-vous.',
    'err_installer_host': "Le téléchargement a été redirigé vers une adresse qui n'est pas celle de l'entreprise. Arrêté.",
    'err_installer_bad': "Le fichier téléchargé ne ressemble pas à l'installeur. Arrêté.",
    'err_launcher_not_found': "L'installeur s'est terminé mais le lanceur est introuvable. Ajoutez-le de nouveau.",
    'err_space_detail': "Pas assez d'espace libre : le jeu demande {need} et {free} sont libres.",
    'err_client_network': "Le programme de la boutique n'a pas pu être téléchargé : {detail}",
    'err_client_mismatch': 'Le programme de boutique téléchargé ne correspondait pas à sa somme de contrôle et a été supprimé.',
    'err_client_space': "Pas assez d'espace disque pour télécharger le programme de la boutique.",
    'err_client_unsupported': "Les programmes de boutique n'existent que pour les PC 64 bits ({detail}).",
    'err_client_cancelled': 'Annulé.',
    'err_client_missing': "Le programme de la boutique ({detail}) n'est pas encore là.",
    'err_client_signin': "Connectez-vous d'abord à la boutique.",
    'err_client_list': "La boutique n'a pas listé vos jeux ({detail}).",

    # temps
    'minutes': "{n} min", 'hours': "{h} h", 'hours_minutes': "{h} h {m} min", 'none': "—",
    'today': "Aujourd'hui", 'yesterday': "Hier", 'days_ago': "Il y a {n} jours",
}

TABLES: Dict[str, Dict[str, str]] = {'en': EN, 'fr': FR}


def language() -> str:
    """'fr' or 'en': SPARK_LANG if set, otherwise the first of LC_ALL, LC_MESSAGES, LANG."""
    forced = os.environ.get('SPARK_LANG', '').strip().lower()[:2]
    if forced in TABLES:
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


TABLE = TABLES[language()]


def set_language(lang: str) -> None:
    """Switch the table (the tests use it; the app picks once at start)."""
    global TABLE
    TABLE = TABLES.get(lang, EN)


def tr(key: str, **kw) -> str:
    text = TABLE.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text


def playtime(minutes: int) -> str:
    if not minutes or minutes <= 0:
        return tr('none')
    if minutes < 60:
        return tr('minutes', n=minutes)
    h, m = divmod(int(minutes), 60)
    if h >= 100 or not m:
        return tr('hours', h=h)
    return tr('hours_minutes', h=h, m=m)


def last_played(stamp: int, now: float = None) -> str:
    if not stamp:
        return tr('never_played')
    now = time.time() if now is None else now
    today = time.localtime(now)
    day_start = time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, -1))
    if stamp >= day_start:
        return tr('today')
    days = int((day_start - stamp) // 86400) + 1
    if days == 1:
        return tr('yesterday')
    if days < 7:
        return tr('days_ago', n=days)
    return time.strftime('%Y-%m-%d', time.localtime(stamp))
