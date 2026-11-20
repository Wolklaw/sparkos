"""The test fixtures: a fake home folder with a Flatpak Steam (two library folders, tools to
skip, non-Steam shortcuts), a Flatpak Heroic (Epic, GOG, Amazon), a regular Lutris, a regular
itch app, a Flatpak Bottles, the official Minecraft launcher and Prism Launcher. Used by the
unit tests and by --self-test, so an installed copy can prove its parsers still work.

In the repository they are in tests/fixtures/; install.sh copies them to <prefix>/fixtures/.
Files there say @HOME@ where a real file has the home folder; materialize() copies the tree,
puts the real folder in, builds each SQLite database from its .sql file (Lutris's pga.db,
itch's butler.db) and draws a few covers.
"""

import hashlib
import os
import re
import shutil
import sqlite3
from typing import Dict, List, Optional, Tuple

from PIL import Image

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# what scanning the fixture home must find, by source
EXPECTED: Dict[str, int] = {'steam': 7, 'epic': 1, 'gog': 1, 'amazon': 1, 'lutris': 2,
                            'itch': 2, 'bottles': 2, 'minecraft': 1, 'prism': 2}

STEAM = os.path.join('.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam')
HEROIC = os.path.join('.var', 'app', 'com.heroicgameslauncher.hgl', 'config', 'heroic')
LUTRIS = os.path.join('.local', 'share', 'lutris')
PRISM = os.path.join('.local', 'share', 'PrismLauncher')
SHORTCUT_ID = 2642853830          # the first shortcut in shortcuts.vdf (appid -1652113466)
CELESTE_ART = 'https://cdn.example.invalid/celeste-tall.jpg'
COVERS = {   # path in the fake home -> (size, colour)
    os.path.join(STEAM, 'appcache', 'librarycache', '620', 'library_600x900.jpg'):
        ((600, 900), '#3de8c8'),
    os.path.join(STEAM, 'appcache', 'librarycache', '1145360', '0f3a9c', 'library_600x900.jpg'):
        ((600, 900), '#ff4d8d'),
    os.path.join(STEAM, 'appcache', 'librarycache', '413150_library_600x900.jpg'):
        ((300, 450), '#f4c95d'),
    os.path.join(HEROIC, 'images-cache', hashlib.sha256(CELESTE_ART.encode()).hexdigest()):
        ((512, 512), '#22d8ff'),
    os.path.join(LUTRIS, 'coverart', 'battlenet.jpg'): ((264, 352), '#b9a6ff'),
    os.path.join(STEAM, 'userdata', '12345678', 'config', 'grid', f'{SHORTCUT_ID}p.jpg'):
        ((600, 900), '#ff2e88'),
    os.path.join(PRISM, 'icons', 'fabric-icon.png'): ((128, 128), '#dbd0b4'),
}
TEXT_EXT = ('.vdf', '.acf', '.json', '.sql', '.yml', '.cfg')
EVTEST_LINE = re.compile(r'^Event: time ([0-9.]+), type (\d+) \(\w+\), code (\d+) \(\w+\), '
                         r'value (-?\d+)')


def source_dir() -> Optional[str]:
    for path in (os.path.join(APP_DIR, 'tests', 'fixtures'), os.path.join(APP_DIR, 'fixtures')):
        if os.path.isdir(os.path.join(path, 'home')):
            return path
    return None


def anticheat_list() -> str:
    src = source_dir()
    return os.path.join(src, 'anticheat.json') if src else ''


def materialize(dest: str) -> str:
    """Build the fake home in dest (which should be empty). Returns dest."""
    src = source_dir()
    if not src:
        raise FileNotFoundError("the test fixtures are missing")
    home = os.path.abspath(dest)
    shutil.copytree(os.path.join(src, 'home'), home, dirs_exist_ok=True)
    for folder, _dirs, files in os.walk(home):
        for name in files:
            if not name.endswith(TEXT_EXT):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError:           # shortcuts.vdf is binary
                continue
            if '@HOME@' in text:
                # JSON and VDF both escape backslashes; Linux paths have none
                with open(path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(text.replace('@HOME@', home.replace('\\', '/')))
    for folder, _dirs, files in os.walk(home):
        for name in files:
            if not name.endswith('.sql'):
                continue
            with open(os.path.join(folder, name), encoding='utf-8') as f:
                script = f.read()
            con = sqlite3.connect(os.path.join(folder, name[:-4] + '.db'))
            try:
                con.executescript(script)
                con.commit()
            finally:
                con.close()
    for rel, (size, colour) in COVERS.items():
        path = os.path.join(home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.new('RGB', size, colour).save(path, 'JPEG')
    return home


def recorded_events(name: str) -> List[Tuple[float, int, int, int]]:
    """A controller recording, tests/fixtures/gamepad/<name>.evtest in evtest's text format, as
    (time, type, code, value); each SYN_REPORT line becomes (time, 0, 0, 0)."""
    src = source_dir()
    if not src:
        raise FileNotFoundError("the test fixtures are missing")
    events = []
    with open(os.path.join(src, 'gamepad', f'{name}.evtest'), encoding='utf-8') as f:
        for line in f:
            match = EVTEST_LINE.match(line)
            if match:
                events.append((float(match.group(1)), int(match.group(2)), int(match.group(3)),
                               int(match.group(4))))
            elif line.startswith('Event:') and 'SYN_REPORT' in line:
                stamp = float(line.split('time', 1)[1].split(',', 1)[0])
                events.append((stamp, 0, 0, 0))
    return events
