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
