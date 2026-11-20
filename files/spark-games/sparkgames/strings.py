"""Every user-facing string, in one place, so a French translation can be added as a second
table. tr('key', name=...) formats one; a key missing from a translation falls back to English.
"""

import os
import time
from typing import Dict

EN: Dict[str, str] = {
    # sources and launchers
    'src_all': "ALL", 'src_steam': "STEAM", 'src_epic': "EPIC", 'src_gog': "GOG",
    'src_amazon': "AMAZON", 'src_lutris': "LUTRIS", 'src_own': "MINE",
    'launcher_steam': "Steam", 'launcher_heroic': "Heroic", 'launcher_lutris': "Lutris",
    'launcher_own': "Spark Games",
    'store_epic': "Epic Games Store", 'store_gog': "GOG", 'store_amazon': "Amazon Games",
    'flatpak': "Flatpak",

    # header and library
    'title': "SPARK GAMES", 'ready': "READY", 'scanning': "SCANNING", 'games_n': "{n} GAMES",
    'game_1': "1 GAME", 'starting': "STARTING {title}", 'scan_problem': "COULDN'T READ {names}",
    'sort_recent': "RECENT", 'sort_title': "A–Z",
    'search_hint': "Search  /",
    'tip_grid': "Covers", 'tip_list': "List", 'tip_settings': "Settings", 'tip_rescan': "Scan again",
    'add_game': "Add a game",
    'no_match': "Nothing matches “{query}”.",
    'none_in_filter': "No games from this launcher.",
    'never_played': "Not played yet",
    'scanning_first': "Looking for games…",

    # empty state
    'empty_title': "NO GAMES FOUND",
    'empty_body': ("Spark Games lists the games you installed with Steam, Heroic (Epic, GOG, "
                   "Amazon) or Lutris, and programs you add yourself. None of these launchers "
                   "has installed games for this account yet."),
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
    'set_files': "Settings: {config}   Playtime: {data}   Cache: {cache}",

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

TABLES: Dict[str, Dict[str, str]] = {'en': EN}     # add 'fr': FR here


def language() -> str:
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return value[:2].lower()
    return 'en'


TABLE = TABLES.get(language(), EN)


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
