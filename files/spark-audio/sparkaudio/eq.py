"""A small equalizer per output, through PipeWire's filter-chain.

Turning it on for an output writes one config file with one filter-chain per EQ'd output and
starts `pipewire -c <that file>` as a systemd user service (spark-audio-eq.service). Each chain
shows up as a new output named "<output> (EQ)"; the app makes that the default output when the
real one was, and puts it back when the EQ is turned off. Removing the last EQ stops and
deletes the service, the unit file and the config: nothing stays behind.

Five bands, as in sink-eq6 from PipeWire's own examples: low shelf, three peaking, high shelf.
A preamp lowers the level by the biggest boost so a boosted band does not clip."""

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from . import APP_SLUG
from .core import config_dir, log, run, load_json, save_json
from .model import EQ_OUT_PREFIX, EQ_SINK_PREFIX

UNIT = "spark-audio-eq.service"
GAIN_MIN, GAIN_MAX = -12.0, 12.0

# (label, type, frequency in Hz, Q)
BANDS = (
    ("BASS", "bq_lowshelf", 90.0, 0.7),
    ("LOW MID", "bq_peaking", 300.0, 1.0),
    ("MID", "bq_peaking", 1000.0, 1.0),
    ("PRESENCE", "bq_peaking", 3500.0, 1.0),
    ("TREBLE", "bq_highshelf", 9000.0, 0.7),
)

PRESETS = {                       # gains in dB, one per band
    "flat": (0, 0, 0, 0, 0),
    "bass": (6, 3, 0, 0, 0),
    "treble": (0, 0, 0, 3, 6),
    "voice": (-3, -1, 2, 4, 0),
    "warm": (3, 2, 0, -3, -5),
    "loudness": (6, 2, -2, 1, 5),
}


def preamp_gain(gains: Sequence[float]) -> float:
    """Linear multiplier that keeps the loudest boost from clipping (1.0 when nothing boosts)."""
    boost = max([0.0] + [float(g) for g in gains])
    return round(10 ** (-boost / 20.0), 4)


def clamp_gains(gains: Sequence[float]) -> List[float]:
    out = [max(GAIN_MIN, min(GAIN_MAX, float(g))) for g in list(gains)[:len(BANDS)]]
    return out + [0.0] * (len(BANDS) - len(out))


def preset_name(gains: Sequence[float]) -> str:
    for name, values in PRESETS.items():
        if all(abs(a - b) < 0.05 for a, b in zip(values, gains)):
            return name
    return "custom"


def control_names(index: int) -> str:
    return f"eq_band_{index + 1}"


def chain_config(real_name: str, title: str, gains: Sequence[float]) -> str:
    """The filter-chain module for one output, as PipeWire config text."""
    q = json.dumps
    nodes = ['{ type = builtin name = preamp label = linear '
             f'control = {{ "Mult" = {preamp_gain(gains)} "Add" = 0.0 }} }}']
    links = []
    prev = "preamp"
    for i, (_label, kind, freq, qual) in enumerate(BANDS):
        name = control_names(i)
        nodes.append(f'{{ type = builtin name = {name} label = {kind} '
                     f'control = {{ "Freq" = {freq} "Q" = {qual} "Gain" = {float(gains[i])} }} }}')
        links.append(f'{{ output = "{prev}:Out" input = "{name}:In" }}')
        prev = name
    return f"""    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = {q(title + " (EQ)")}
            media.name = {q(title + " (EQ)")}
            filter.graph = {{
                nodes = [
                    {(chr(10) + "                    ").join(nodes)}
                ]
                links = [
                    {(chr(10) + "                    ").join(links)}
                ]
            }}
            audio.channels = 2
            audio.position = [ FL FR ]
            capture.props = {{
                node.name = {q(EQ_SINK_PREFIX + real_name)}
                media.class = Audio/Sink
            }}
            playback.props = {{
                node.name = {q(EQ_OUT_PREFIX + real_name)}
                node.passive = true
                node.dont-fallback = true
                target.object = {q(real_name)}
            }}
        }}
    }}
"""


def full_config(outputs: Dict[str, Dict]) -> str:
    chains = ''.join(chain_config(name, o.get('title', name), clamp_gains(o.get('gains', [0] * 5)))
                     for name, o in sorted(outputs.items()) if o.get('enabled'))
    return f"""# Written by Spark Audio. Delete it from Spark Audio's EQ page, not by hand.
context.properties = {{
    log.level = 0
}}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-rt
        args = {{ nice.level = -11 }}
        flags = [ ifexists nofail ]
    }}
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-adapter }}
{chains}]
"""


def unit_text(conf_path: str) -> str:
    return f"""[Unit]
Description=Spark Audio equalizer (PipeWire filter-chain)
After=pipewire.service
BindsTo=pipewire.service

[Service]
Type=simple
ExecStart=/usr/bin/pipewire -c {conf_path}
Restart=on-failure
Slice=session.slice

[Install]
WantedBy=pipewire.service
"""


@dataclass
class Eq:
    enabled: bool = False
    gains: List[float] = field(default_factory=lambda: [0.0] * len(BANDS))
    title: str = ""


class EqManager:
    """What is saved (~/.config/spark-audio/eq.json), the config and unit files, and the
    service. `systemctl` and the folders can be pointed elsewhere for tests."""

    def __init__(self, conf_path: Optional[str] = None, unit_dir: Optional[str] = None,
                 systemctl: Sequence[str] = ('systemctl', '--user'), fake: bool = False):
        self.conf_path = conf_path or os.path.join(config_dir(), 'eq.conf')
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
        self.unit_dir = unit_dir or os.path.join(base, 'systemd', 'user')
        self.systemctl = list(systemctl)
        self.fake = fake
        self.calls: List[tuple] = []
        self.data = load_json('eq.json') if not fake else {}
        self.outputs: Dict[str, Dict] = self.data.get('outputs', {})

    @property
    def unit_path(self) -> str:
        return os.path.join(self.unit_dir, UNIT)

    def get(self, real_name: str) -> Eq:
        o = self.outputs.get(real_name) or {}
        return Eq(bool(o.get('enabled')), clamp_gains(o.get('gains', [0.0] * len(BANDS))),
                  o.get('title', ''))

    def any_enabled(self) -> bool:
        return any(o.get('enabled') for o in self.outputs.values())

    def installed(self) -> bool:
        return os.path.exists(self.unit_path) or os.path.exists(self.conf_path)

    def _save(self) -> None:
        self.data['outputs'] = self.outputs
        if self.fake:
            return
        if self.outputs:
            save_json('eq.json', self.data)
        else:
            try:
                os.unlink(os.path.join(config_dir(), 'eq.json'))
            except OSError:
                pass

    def _ctl(self, *args: str) -> bool:
        self.calls.append(args)
        if self.fake:
            return True
        r = run(self.systemctl + list(args), timeout=20)
        if r.returncode != 0:
            log.warning("systemctl %s: %s", ' '.join(args), r.stderr.strip())
        return r.returncode == 0

    def _write_files(self) -> None:
        os.makedirs(os.path.dirname(self.conf_path), exist_ok=True)
        os.makedirs(self.unit_dir, exist_ok=True)
        for path, text in ((self.conf_path, full_config(self.outputs)),
                           (self.unit_path, unit_text(self.conf_path))):
            with open(path + '.tmp', 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(path + '.tmp', path)

    def save_gains(self, real_name: str, title: str, gains: Sequence[float]) -> None:
        """Remember the gains without touching the running chain (the live update does that)."""
        o = self.outputs.setdefault(real_name, {})
        o['gains'] = clamp_gains(gains)
        o['title'] = title or o.get('title', real_name)
        if o.get('enabled') and not self.fake:
            self._write_files()              # the next start uses them
        self._save()

    def enable(self, real_name: str, title: str, gains: Sequence[float]) -> bool:
        """Turn the EQ on for an output (starts or restarts the service)."""
        o = self.outputs.setdefault(real_name, {})
        o.update(enabled=True, gains=clamp_gains(gains), title=title)
        self._save()
        if self.fake:
            self.calls.append(('enable', real_name))
            return True
        self._write_files()
        self._ctl('daemon-reload')
        return self._ctl('enable', UNIT) and self._ctl('restart', UNIT)

    def disable(self, real_name: str) -> None:
        """Turn the EQ off for one output but keep its gains. The service stops when no
        output has an EQ any more."""
        if real_name in self.outputs:
            self.outputs[real_name]['enabled'] = False
        self._save()
        self._after_change()

    def remove(self, real_name: str) -> None:
        """Forget an output's EQ completely."""
        self.outputs.pop(real_name, None)
        self._save()
        self._after_change()

    def _after_change(self) -> None:
        if self.fake:
            self.calls.append(('after',))
            return
        if self.any_enabled():
            self._write_files()
            self._ctl('restart', UNIT)
        else:
            self.remove_service()

    def remove_service(self) -> None:
        """Stop and delete the service, its unit file and the config."""
        if not self.fake:
            self._ctl('disable', '--now', UNIT)
            for path in (self.unit_path, self.conf_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self._ctl('daemon-reload')
            self._ctl('reset-failed', UNIT)
            try:
                os.rmdir(config_dir())          # only when nothing else is in it
            except OSError:
                pass

    def remove_all(self) -> None:
        self.outputs.clear()
        self._save()
        self.remove_service()
