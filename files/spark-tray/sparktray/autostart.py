"""Start Spark Tray at login, per user, the XDG way.

The image ships /etc/xdg/autostart/dev.wolklaw.SparkTray.desktop with OnlyShowIn=Spark, so the
tray starts in the `spark` session and not in Plasma (which has its own applets). A person
turns it on in Plasma with --enable, which writes a user file without OnlyShowIn, or off
everywhere with --disable (Hidden=true, which overrides the system file). --reset removes the
user file and returns to the default."""

import os
import shutil
from typing import Dict, Optional

from . import APP_ID
from . import core

FILE = f"{APP_ID}.desktop"
SYSTEM_FILE = os.path.join('/etc/xdg/autostart', FILE)


def user_file() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'autostart', FILE)


def in_spark_session(environ: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    desktops = [p.strip().lower() for p in (env.get('XDG_CURRENT_DESKTOP') or '').split(':')]
    return 'spark' in desktops


def executable() -> str:
    found = shutil.which('spark-tray')
    if found:
        return found
    local = os.path.join(os.path.expanduser('~'), '.local', 'bin', 'spark-tray')
    return local if os.path.exists(local) else 'spark-tray'


def desktop_text(exec_path: str, hidden: bool = False, only_show_in: str = '') -> str:
    lines = ['[Desktop Entry]', 'Type=Application', 'Name=Spark Tray',
             'Comment=Network, Bluetooth, power, printer and volume icons for the tray',
             'Comment[fr]=Icônes réseau, Bluetooth, alimentation, imprimantes et volume',
             f'Exec="{exec_path}"' if ' ' in exec_path else f'Exec={exec_path}',
             'Icon=dev.wolklaw.SparkTray', 'Terminal=false', 'NoDisplay=true',
             'X-GNOME-Autostart-Delay=2']
    if only_show_in:
        lines.append(f'OnlyShowIn={only_show_in};')
    if hidden:
        lines.append('Hidden=true')
    return '\n'.join(lines) + '\n'


def _read_hidden(path: str) -> Optional[bool]:
    """None when the file isn't there; else whether it says Hidden=true."""
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return None
    return any(line.strip().lower() == 'hidden=true' for line in text.splitlines())


def status(environ: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    """{'mode': 'on'|'off'|'default', 'effective': bool, 'spark_session': bool}"""
    spark = in_spark_session(environ)
    hidden = _read_hidden(user_file())
    if hidden is True:
        return {'mode': 'off', 'effective': False, 'spark_session': spark}
    if hidden is False:
        return {'mode': 'on', 'effective': True, 'spark_session': spark}
    system = os.path.exists(SYSTEM_FILE)
    return {'mode': 'default', 'effective': system and spark, 'spark_session': spark}


def _write(text: str) -> None:
    path = user_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(path + '.tmp', path)


def enable() -> None:
    _write(desktop_text(executable()))


def disable() -> None:
    _write(desktop_text(executable(), hidden=True))


def reset() -> None:
    try:
        os.remove(user_file())
    except FileNotFoundError:
        pass
    except OSError as exc:
        core.log.warning("could not remove %s: %s", user_file(), exc)
