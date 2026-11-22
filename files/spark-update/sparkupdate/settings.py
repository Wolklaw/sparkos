"""Settings. System-wide ones (/etc/sparkos/update.conf: automatic updates, how often, notify
only, Flatpak) are written as root through the pkexec helper; the user's notification
preferences live in ~/.config/spark-update/settings.json."""

import os
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

from . import CONF_PATH
from .core import Env, config_dir, load_json, save_json

STAGE, NOTIFY = 'stage', 'notify'
EVERY_HOURS = (3, 6, 12, 24)
REMIND_HOURS = (24, 72, 168)          # Later reminds once a day at most


@dataclass
class SystemSettings:
    automatic: bool = True      # check on its own; off = only when you click Check now
    mode: str = STAGE           # stage: download and stage; notify: only check and tell
    every_hours: int = 6
    flatpak: bool = True        # update Flatpak apps too

    def problems(self) -> List[str]:
        out = []
        if self.mode not in (STAGE, NOTIFY):
            out.append(f"mode must be {STAGE} or {NOTIFY}")
        if self.every_hours not in EVERY_HOURS:
            out.append("check_every_hours must be one of " + ', '.join(map(str, EVERY_HOURS)))
        return out


KEYS = {'automatic': 'automatic', 'mode': 'mode', 'check_every_hours': 'every_hours',
        'flatpak': 'flatpak'}
TRUE, FALSE = ('yes', 'true', 'on', '1'), ('no', 'false', 'off', '0')


def parse_conf(text: str) -> Tuple[SystemSettings, List[str]]:
    """key = value lines; '#' starts a comment. Unknown keys and bad values are reported and
    the default is kept, so a typo never stops updates."""
    s = SystemSettings()
    warnings: List[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            continue
        if '=' not in line:
            warnings.append(f"line {n}: no '='")
            continue
        key, _, value = (p.strip() for p in line.partition('='))
        value = value.strip('"\'').lower()
        attr = KEYS.get(key.lower())
        if attr is None:
            warnings.append(f"line {n}: unknown setting {key}")
            continue
        if attr in ('automatic', 'flatpak'):
            if value in TRUE:
                setattr(s, attr, True)
            elif value in FALSE:
                setattr(s, attr, False)
            else:
                warnings.append(f"line {n}: {key} must be yes or no")
        elif attr == 'mode':
            if value in (STAGE, NOTIFY):
                s.mode = value
            else:
                warnings.append(f"line {n}: mode must be {STAGE} or {NOTIFY}")
        elif attr == 'every_hours':
            if value.isdigit() and int(value) in EVERY_HOURS:
                s.every_hours = int(value)
            else:
                warnings.append(f"line {n}: check_every_hours must be one of "
                                + ', '.join(map(str, EVERY_HOURS)))
    return s, warnings


def format_conf(s: SystemSettings) -> str:
    yn = {True: 'yes', False: 'no'}
    return (
        "# Spark Update, SparkOS's updater. The Spark Update window writes this file (as root,\n"
        "# through pkexec); you can also edit it by hand. Changes apply at the next check.\n"
        "#\n"
        "# automatic          yes: check on its own; no: only when you click Check now\n"
        "# mode               stage: download the new version and get it ready for the next\n"
        "#                    restart; notify: only check and tell you, download nothing\n"
        "# check_every_hours  3, 6, 12 or 24\n"
        "# flatpak            yes: update Flatpak apps too (system and yours)\n"
        "#\n"
        "# Spark Update never restarts the PC on its own.\n"
        f"automatic = {yn[s.automatic]}\n"
        f"mode = {s.mode}\n"
        f"check_every_hours = {s.every_hours}\n"
        f"flatpak = {yn[s.flatpak]}\n")


def load_system(env: Env) -> Tuple[SystemSettings, List[str]]:
    text = env.read(CONF_PATH)
    if text is None:
        return SystemSettings(), []
    return parse_conf(text)


def parse_assignments(args: List[str]) -> Tuple[Optional[SystemSettings], List[str]]:
    """'automatic=no' 'check_every_hours=12' ... (the helper's arguments) on top of the
    defaults. Anything unknown or out of range is an error: the helper writes nothing."""
    allowed = re.compile(r'^(automatic|mode|check_every_hours|flatpak)=[a-z0-9]+$')
    bad = [a for a in args if not allowed.match(a)]
    if bad:
        return None, [f"not a setting: {a}" for a in bad]
    s, warnings = parse_conf('\n'.join(args))
    if warnings:
        return None, warnings
    return s, s.problems()


def write_system(env: Env, s: SystemSettings) -> None:
    path = env.path(CONF_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write(format_conf(s))
    os.chmod(path + '.tmp', 0o644)
    os.replace(path + '.tmp', path)


def as_args(s: SystemSettings) -> List[str]:
    yn = {True: 'yes', False: 'no'}
    return [f"automatic={yn[s.automatic]}", f"mode={s.mode}",
            f"check_every_hours={s.every_hours}", f"flatpak={yn[s.flatpak]}"]


# ─── The user's own preferences ───────────────────────────────

@dataclass
class UserPrefs:
    notify: bool = True          # show the "SparkOS updated" notification
    remind_hours: int = 24       # after Later: remind again after this long (at least a day)
    glitch: bool = True


def prefs_path() -> str:
    return os.path.join(config_dir(), 'settings.json')


def load_prefs() -> UserPrefs:
    data = load_json(prefs_path())
    p = UserPrefs()
    if isinstance(data.get('notify'), bool):
        p.notify = data['notify']
    if data.get('remind_hours') in REMIND_HOURS:
        p.remind_hours = int(data['remind_hours'])
    if isinstance(data.get('glitch'), bool):
        p.glitch = data['glitch']
    return p


def save_prefs(p: UserPrefs, extra: Optional[Dict] = None) -> None:
    data = load_json(prefs_path())
    data.update(asdict(p))
    if extra:
        data.update(extra)
    save_json(prefs_path(), data)
