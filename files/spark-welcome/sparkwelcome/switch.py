"""Coming from Windows: which SparkOS app does the job of which Windows program, the optional
Spark apps the Store can install from this PC, and the programs found on a Windows drive with
what to use for each of them here.

The programs come from the Windows drive's own registry files (SOFTWARE and each account's
NTUSER.DAT, "Uninstall") and the Microsoft Store apps' folder names in Program Files\\WindowsApps,
all read as plain files, never written. No window code, so the Spark Portal can reuse it."""

import json
import os
import re
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from . import core
from .catalog import Entry
from .core import log
from .windows import _child, _walk_ci, read_hive, reg_text


# ─── SparkOS's own apps, and the Windows program each one replaces ──

@dataclass(frozen=True)
class Swap:
    key: str          # strings: swap.<key>.win (the Windows side) and swap.<key>.what
    name: str         # Spark Files
    command: str      # spark-files ('' when there is nothing to open, like the menu itself)
    desktop: str      # dev.wolklaw.SparkFiles


SWAPS: Tuple[Swap, ...] = (
    Swap('browser', 'Soot', 'soot', 'dev.wolklaw.Soot'),
    Swap('office', 'FreeSuite', 'freesuite', 'freesuite'),
    Swap('files', 'Spark Files', 'spark-files', 'dev.wolklaw.SparkFiles'),
    Swap('launcher', 'Spark Launcher', '', 'dev.wolklaw.SparkLauncher'),
    Swap('settings', 'Spark Settings', 'spark-settings', 'dev.wolklaw.SparkSettings'),
    Swap('store', 'Spark Store', 'spark-store', 'dev.wolklaw.SparkStore'),
    Swap('update', 'Spark Update', 'spark-update', 'dev.wolklaw.SparkUpdate'),
    Swap('monitor', 'Spark Monitor', 'spark-monitor', 'dev.wolklaw.SparkMonitor'),
    Swap('games', 'Spark Games', 'spark-games', 'dev.wolklaw.SparkGames'),
    Swap('run', 'Spark Run', 'spark-run', 'dev.wolklaw.SparkRun'),
    Swap('snip', 'Spark Snip', 'spark-snip', 'dev.wolklaw.SparkSnip'),
    Swap('media', 'Spark Media', 'spark-media', 'dev.wolklaw.SparkMedia'),
    Swap('edit', 'Spark Edit', 'spark-edit', 'dev.wolklaw.SparkEdit'),
    Swap('calc', 'Spark Calc', 'spark-calc', 'dev.wolklaw.SparkCalc'),
    Swap('archive', 'Spark Archive', 'spark-archive', 'dev.wolklaw.SparkArchive'),
    Swap('terminal', 'Spark Terminal', 'spark-terminal', 'dev.wolklaw.SparkTerminal'),
    Swap('scan', 'Spark Scan', 'spark-scan', 'dev.wolklaw.SparkScan'),
    Swap('link', 'Spark Link', 'spark-link', 'dev.wolklaw.SparkLink'),
    Swap('controller', 'Spark Controller', 'spark-controller', 'dev.wolklaw.SparkController'),
)


def swap(key: str) -> Optional[Swap]:
    return next((s for s in SWAPS if s.key == key), None)


def swap_installed(item: Swap) -> bool:
    return bool(item.command) and core.app_installed(item.desktop, item.command)


# ─── Optional Spark apps: not in the image, installed per user from the Store's sources ──

SOURCE_DIRS = ('/usr/share/spark-store/sources',)
# Spark Welcome's own words for the optional apps it knows, keyed by slug: the Windows tools
# each one replaces (strings: optional.<slug>.win). Others still show, with their own summary.
OPTIONAL_WIN = ('spark-space', 'spark-bench', 'spark-connect')


def source_dirs() -> List[str]:
    """The user's sources win over the image's, as in Spark Store."""
    home = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local',
                                                           'share')
    return [os.path.join(home, 'spark-store', 'sources')] + list(SOURCE_DIRS)


def optional_apps(dirs: Optional[Sequence[str]] = None) -> List[Entry]:
    """The optional Spark apps whose source is on this PC, as entries Spark Welcome installs
    with their own `install.sh --user` (the same thing Spark Store's Install button runs)."""
    found: Dict[str, Entry] = {}
    for base in (dirs if dirs is not None else source_dirs()):
        try:
            slugs = sorted(os.listdir(base))
        except OSError:
            continue
        for slug in slugs:
            src = os.path.join(base, slug)
            if slug in found or not re.fullmatch(r'spark-[a-z0-9-]+', slug) \
                    or not os.path.isfile(os.path.join(src, 'install.sh')):
                continue
            try:
                with open(os.path.join(src, 'spark-app.json'), encoding='utf-8') as f:
                    meta = json.load(f)
            except (OSError, ValueError) as exc:
                log.info("optional app %s skipped: %s", slug, exc)
                continue
            if not isinstance(meta, dict) or not isinstance(meta.get('name'), str):
                continue
            blurb = meta.get('summary') or meta.get('description') or ''
            blurb_fr = meta.get('summary_fr') or meta.get('description_fr') or ''
            found[slug] = Entry(f'spark.{slug}', meta['name'], 'SparkOS',
                                str(blurb) or meta['name'], str(meta.get('name_fr') or ''),
                                str(blurb_fr), '',
                                source=src, command=str(meta.get('command') or slug),
                                desktop=str(meta.get('id') or ''))
    return list(found.values())


def optional_installed(entries: Sequence[Entry]) -> Set[str]:
    return {e.id for e in entries if core.app_installed(e.desktop, e.command)}


# ─── Programs on the Windows drive, and what to use here ──────

# What to do about a Windows program here:
#   ('spark', swap key)         a SparkOS app already on this PC does it: Open
#   ('optional', slug)          an optional Spark app: Install (from this PC)
#   ('app', catalog id)         an app Spark Welcome offers (Flathub, Spark Run or web): Install
#   ('games', '')               Spark Games signs in to that store or adds that launcher
#   ('note', strings key)       only words: no Linux version, or something to know first
Answer = Tuple[str, str]

PROGRAMS: Tuple[Tuple[str, Answer], ...] = (
    (r'^(google chrome|microsoft edge|microsoft\.microsoftedge|mozilla firefox|'
     r'opera( gx)?( stable)?|brave|vivaldi)\b',
     ('spark', 'browser')),
    (r'^(microsoft (office|365)|office 16|libreoffice|onlyoffice|wps office)',
     ('spark', 'office')),
    (r'^(adobe acrobat|foxit (pdf )?reader|pdfgear|sumatrapdf)', ('spark', 'office')),
    (r'^(microsoft outlook|microsoft\.outlookforwindows|thunderbird)', ('spark', 'office')),
    (r'^(notepad\+\+|sublime text|notepads)', ('spark', 'edit')),
    (r'^(7-zip|winrar|winzip|peazip|bandizip|nanazip)', ('spark', 'archive')),
    (r'^(sharex|greenshot|lightshot|snagit|microsoft\.screensketch)', ('spark', 'snip')),
    (r'^(vlc media player|mpc-(hc|be)|k-lite|foobar2000|potplayer|aimp|musicbee|'
     r'itunes|irfanview|xnview)', ('spark', 'media')),
    (r'^(hwinfo|cpu-z|gpu-z|process (explorer|hacker)|system informer|hwmonitor)',
     ('spark', 'monitor')),
    (r'^(armoury crate|signalrgb|nzxt cam|fan ?xpert|ai suite|openrgb|msi center|'
     r'gigabyte control center|(asus )?aura)', ('spark', 'controller')),
    (r'^(putty|kitty|mobaxterm|windows terminal|git for windows|git$|powershell|'
     r'microsoft\.(powershell|windowsterminal))', ('spark', 'terminal')),
    (r'^(naps2|vuescan|canon ij scan utility|epson scan|hp scan)', ('spark', 'scan')),
    (r'^(phone link|your phone|microsoft\.yourphone)', ('spark', 'link')),
    (r'^(windirstat|treesize|wiztree|spacesniffer)', ('optional', 'spark-space')),
    (r'^(capframex|presentmon|frameview|fraps)', ('optional', 'spark-bench')),
    (r'^steam$', ('app', 'com.valvesoftware.Steam')),
    (r'^(epic games launcher|epic online services|gog galaxy|amazon games|battle\.net|'
     r'ea app|ea desktop|origin$|ubisoft connect|uplay|rockstar games launcher|'
     r'heroic|playnite|xbox|microsoft\.gamingapp|itch$)', ('games', '')),
    (r'^(riot vanguard|riot client|league of legends|valorant|faceit|esea)',
     ('note', 'prog.anticheat')),
    (r'^discord', ('app', 'com.discordapp.Discord')),
    (r'^signal\b', ('app', 'org.signal.Signal')),
    (r'^telegram', ('app', 'org.telegram.desktop')),
    (r'^(whatsapp|5319275a\.whatsappdesktop)', ('app', 'web.whatsapp')),
    (r'^(spotify|spotifyab\.spotifymusic)', ('app', 'com.spotify.Client')),
    (r'^(amazon music|amazonmobilellc\.amazonmusic)', ('app', 'run.amazon-music')),
    (r'^obs studio', ('app', 'com.obsproject.Studio')),
    (r'^zoom\b', ('app', 'us.zoom.Zoom')),
    (r'^gimp\b', ('app', 'org.gimp.GIMP')),
    (r'^krita\b', ('app', 'org.kde.krita')),
    (r'^kdenlive', ('app', 'org.kde.kdenlive')),
    (r'^blender\b', ('app', 'org.blender.Blender')),
    (r'^bitwarden', ('app', 'com.bitwarden.desktop')),
    (r'^(microsoft onedrive|onedrive)', ('note', 'prog.onedrive')),
    (r'^(google drive|dropbox|icloud)', ('note', 'prog.cloud')),
    (r'^(microsoft teams|teams machine-wide|msteams)', ('note', 'prog.teams')),
    (r'^(amd software|amd radeon software|nvidia (app|geforce experience|graphics driver)|'
     r'intel.*graphics)', ('note', 'prog.drivers')),
    (r'^(logitech g hub|razer synapse|corsair (icue|device control)|steelseries gg)',
     ('note', 'prog.peripherals')),
)
_PROGRAMS = tuple((re.compile(pattern, re.I), answer) for pattern, answer in PROGRAMS)

# Windows' own parts and the runtimes programs bring: never worth a line.
NOISE = re.compile(r'(redistributable|runtime|^microsoft \.net|\.net (framework|core|host)|sdk|'
                   r'update for|hotfix|\bkb\d{6,}|'
                   r'driver|service pack|language pack|webview2|directx|vcredist|'
                   r'microsoft visual c\+\+|windows (app )?cert|setup files|bootstrapper|'
                   r'^microsoft\.(windows|ui|net|vclibs|services|desktopappinstaller|'
                   r'storepurchaseapp|windowsstore|secur|xbox(gameoverlay|identity|speech)|'
                   r'zune|bing|getstarted|people|todos|powerautomate|549981c3f5f10|'
                   r'gethelp|gamingservices|ink\.|xbox\.tcui|xboxgamingoverlay|winget|'
                   r'applicationcompatibility|office\.actionsserver|officepushnotification|'
                   r'sechealthui|startexperiencesapp|edge\.gameassist|[0-9a-f]{13}$)|'
                   r'^microsoft\.\w*(video|image|media)extensions?$|^microsoftwindows\.|'
                   r'^microsoftcorporationii\.|application compatibility|gameinput|'
                   r'tap-windows|ovpn-dco|^cosign$|maintenance service|physx|^openal$|'
                   r'python launcher|printer registration)', re.I)

UNINSTALL = r'Microsoft\Windows\CurrentVersion\Uninstall'


@dataclass
class Program:
    name: str                 # as Windows showed it: "Discord", "7-Zip 24.08 (x64)"
    answer: Optional[Answer]  # None when Spark Welcome has nothing to say about it


@dataclass
class Programs:
    matched: List[Program] = field(default_factory=list)
    others: List[str] = field(default_factory=list)   # names with no answer, sorted


def display_name(name: str) -> str:
    """A Microsoft Store package's name made readable: SpotifyAB.SpotifyMusic -> Spotify Music.
    Other names stay as Windows showed them."""
    last = name.rsplit('.', 1)[-1]
    if ' ' in name or not re.fullmatch(r'[\w-]+(\.[\w-]+)+', name) \
            or not re.match(r'[A-Z0-9]', last) \
            or not re.search(r'[a-z]', last):              # Battle.net, Paint.NET stay
        return name
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', last)


def answer_for(name: str) -> Optional[Answer]:
    clean = name.strip()
    for pattern, answer in _PROGRAMS:
        if pattern.search(clean):
            return answer
    return None


def _uninstall_names(hive, base: str) -> List[str]:
    names = []
    try:
        keys = hive.subkeys(base)
    except (ValueError, struct.error) as exc:
        log.info("%s not read: %s", base, exc)
        return names
    for sub in keys:
        try:
            values = hive.values(f'{base}\\{sub}')
        except (ValueError, struct.error):
            continue
        name = reg_text(values.get('displayname'))
        component = values.get('systemcomponent')
        if not name or 'parentkeyname' in values or 'releasetype' in values:
            continue
        if component and component[1][:4] == b'\x01\x00\x00\x00':
            continue
        names.append(name)
    return names


def program_names(root: str, profiles: Sequence[str] = ()) -> List[str]:
    """Display names of the programs installed on the Windows drive mounted at root: the
    machine's (SOFTWARE, 64- and 32-bit) and each account's (NTUSER.DAT), plus Microsoft Store
    apps by package name. Read-only; [] when nothing can be read."""
    names: List[str] = []
    config = _walk_ci(root, r'Windows\System32\config')
    software = read_hive(_child(config or '', 'SOFTWARE', want_dir=False))
    if software is not None:
        names += _uninstall_names(software, UNINSTALL)
        names += _uninstall_names(software, 'WOW6432Node\\' + UNINSTALL)
    for profile in profiles:
        hive = read_hive(_child(profile, 'NTUSER.DAT', want_dir=False))
        if hive is not None:
            names += _uninstall_names(hive, 'Software\\' + UNINSTALL)
    store = _walk_ci(root, r'Program Files\WindowsApps')
    if store:
        try:
            for entry in os.scandir(store):
                package = entry.name.split('_', 1)[0]
                if '.' in package and entry.is_dir(follow_symlinks=False):
                    names.append(package)
        except OSError:
            pass
    return names


def sort_programs(names: Sequence[str]) -> Programs:
    """One line per answer (Discord and Discord PTB show once), noise left out."""
    out = Programs()
    seen_answers: Set[Answer] = set()
    seen_names: Set[str] = set()
    for name in sorted(set(n.strip() for n in names if n and n.strip()),
                       key=lambda n: (n.lower(), n)):
        answer = answer_for(name) or answer_for(display_name(name))
        if answer is not None:
            if answer in seen_answers:
                continue
            seen_answers.add(answer)
            out.matched.append(Program(display_name(name), answer))
        elif not NOISE.search(name) and display_name(name).lower() not in seen_names:
            seen_names.add(display_name(name).lower())
            out.others.append(display_name(name))
    order = {'spark': 0, 'games': 1, 'app': 2, 'optional': 3, 'note': 4}
    out.matched.sort(key=lambda p: (order.get(p.answer[0], 9) if p.answer else 9,
                                    p.name.lower()))
    out.others.sort(key=str.lower)
    return out


def find_programs(root: str, profiles: Sequence[str] = ()) -> Programs:
    return sort_programs(program_names(root, profiles))


# ─── Steam games on the Windows drive ─────────────────────────

STEAM_DIRS = (r'Program Files (x86)\Steam', r'Program Files\Steam')


@dataclass
class SteamLibrary:
    where: str               # as Windows shows it: D:\SteamLibrary
    games: List[str] = field(default_factory=list)   # folder names in steamapps\common
    common: str = ''         # that folder here, when its drive could be opened


def steam_libraries(root: str, drives=None) -> List[SteamLibrary]:
    """Steam's game libraries listed in the Windows drive's libraryfolders.vdf, with the games
    in each. Libraries on other drives are found by their letter through drives (a
    windows.Drives, which opens them read-only); without it only the Windows drive's are."""
    letter = drives.windows_letter if drives is not None else 'C'
    for rel in STEAM_DIRS:
        steam = _walk_ci(root, rel)
        if not steam:
            continue
        vdf = _child(_walk_ci(steam, 'steamapps') or '', 'libraryfolders.vdf', want_dir=False)
        paths = [f"{letter}:\\{rel}"]
        if vdf:
            try:
                with open(vdf, encoding='utf-8', errors='replace') as f:
                    text = f.read()
                for raw in re.findall(r'"path"\s+"([^"]+)"', text):
                    path = raw.replace('\\\\', '\\').rstrip('\\')
                    if path.lower() not in (p.lower() for p in paths):
                        paths.append(path)
            except OSError:
                pass
        out = []
        for path in paths:
            lib = SteamLibrary(path)
            match = re.match(r'([A-Za-z]):\\?(.*)$', path)
            point = None
            if match and match.group(1).upper() == letter.upper():
                point = root
            elif match and drives is not None:
                point = drives.mount_point(match.group(1))
            common = _walk_ci(point, match.group(2) + r'\steamapps\common') if point else None
            if common:
                lib.common = common
                try:
                    lib.games = sorted((e.name for e in os.scandir(common)
                                        if e.is_dir(follow_symlinks=False)
                                        and e.name.lower() != 'steamworks shared'),
                                       key=str.lower)
                except OSError:
                    pass
            out.append(lib)
        return out
    return []


STEAM_FLATPAK_COMMON = os.path.join('~', '.var', 'app', 'com.valvesoftware.Steam', '.local',
                                    'share', 'Steam', 'steamapps', 'common')
