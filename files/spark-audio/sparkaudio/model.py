"""PipeWire's graph as pw-dump describes it, and the few things the window needs from it:
outputs, inputs, the apps playing or recording, sound cards, and which output is the default.

Graph.apply() takes the arrays `pw-dump` and `pw-dump --monitor` print (the first is everything,
later ones hold only what changed; an object with "info": null is gone). Graph.state() turns it
into plain objects with friendly names."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .core import gain_to_volume

EQ_SINK_PREFIX = "spark_eq."          # the virtual output a filter-chain creates for an EQ
EQ_OUT_PREFIX = "spark_eq_out."       # its playback side towards the real output
OWN_PREFIX = "spark-audio-"           # streams this app starts itself (meters, the mic test)

SINK, SOURCE = 'Audio/Sink', 'Audio/Source'
PLAYBACK, CAPTURE = 'Stream/Output/Audio', 'Stream/Input/Audio'


@dataclass
class Node:
    id: int
    serial: int
    name: str                      # node.name, what wpctl/pactl call it
    title: str                     # friendly name for the list
    detail: str                    # "USB · Analog"
    kind: str                      # Audio/Sink, Audio/Source, Stream/Output/Audio, ...
    state: str = "idle"
    volume: Optional[float] = None   # slider scale 0..1+ (cube root of the gain), None if unknown
    mute: bool = False
    channels: int = 2
    device_id: Optional[int] = None
    target: Optional[int] = None     # streams: the node id it is linked to
    app: str = ""
    media: str = ""
    eq_for: Optional[str] = None     # EQ sinks: node.name of the real output behind it


@dataclass
class Profile:
    index: int
    name: str
    description: str
    available: bool


@dataclass
class Card:
    id: int
    name: str                      # device.name, what pactl calls the card
    title: str
    current: str = ""              # description of the active profile
    current_name: str = ""
    profiles: List[Profile] = field(default_factory=list)
    nodes: int = 0
    alsa_card: Optional[int] = None
    driver: str = ""


@dataclass
class State:
    sinks: List[Node] = field(default_factory=list)       # real outputs only, default first
    sources: List[Node] = field(default_factory=list)
    playing: List[Node] = field(default_factory=list)     # apps that play
    recording: List[Node] = field(default_factory=list)   # apps that record
    eq_sinks: Dict[str, Node] = field(default_factory=dict)   # real output node.name -> EQ sink
    cards: List[Card] = field(default_factory=list)
    default_sink: Optional[int] = None                    # node id (an EQ sink counts as its output)
    default_sink_raw: Optional[int] = None                # node id as PipeWire has it
    default_source: Optional[int] = None
    nodes: Dict[int, Node] = field(default_factory=dict)

    def sink_by_id(self, node_id) -> Optional[Node]:
        return next((n for n in self.sinks if n.id == node_id), None)

    def source_by_id(self, node_id) -> Optional[Node]:
        return next((n for n in self.sources if n.id == node_id), None)


# ─── The graph, kept up to date from pw-dump --monitor ────────

class Graph:
    def __init__(self):
        self.objects: Dict[int, Dict[str, Any]] = {}

    def apply(self, updates: List[Dict[str, Any]]) -> None:
        for obj in updates:
            if not isinstance(obj, dict) or 'id' not in obj:
                continue
            oid = obj['id']
            if 'info' in obj and obj['info'] is None:
                self.objects.pop(oid, None)
                continue
            old = self.objects.get(oid)
            if old is None or ('type' in obj and obj['type'] != old.get('type')):
                self.objects[oid] = _copy(obj)
                continue
            for key, value in obj.items():
                if key == 'info' and isinstance(value, dict):
                    info = old.setdefault('info', {})
                    for k, v in value.items():
                        if k == 'params' and isinstance(v, dict):
                            info.setdefault('params', {}).update(v)
                        else:
                            info[k] = v
                elif key == 'metadata' and isinstance(value, list):
                    _merge_metadata(old, value)
                else:
                    old[key] = value

    def default_name(self, key: str) -> Optional[str]:
        for obj in self.objects.values():
            if obj.get('type', '').endswith('Metadata') and \
                    obj.get('props', {}).get('metadata.name') == 'default':
                found = None
                for entry in obj.get('metadata') or []:
                    if entry.get('key') == key:
                        value = entry.get('value')
                        found = value.get('name') if isinstance(value, dict) else None
                return found
        return None

    # — turning it into something to show —
    def state(self) -> State:
        st = State()
        devices = {i: o for i, o in self.objects.items() if o.get('type', '').endswith(':Device')}
        links: List[Tuple[int, int]] = []
        for obj in self.objects.values():
            if obj.get('type', '').endswith(':Link'):
                info = obj.get('info') or {}
                if 'output-node-id' in info and 'input-node-id' in info:
                    links.append((info['output-node-id'], info['input-node-id']))

        for oid, obj in self.objects.items():
            if not obj.get('type', '').endswith(':Node'):
                continue
            info = obj.get('info') or {}
            props = info.get('props') or {}
            kind = props.get('media.class')
            if kind not in (SINK, SOURCE, PLAYBACK, CAPTURE):
                continue
            name = props.get('node.name', '')
            if name.startswith(EQ_OUT_PREFIX) or name.startswith('output.' + EQ_SINK_PREFIX) \
                    or name.startswith(OWN_PREFIX) or name.startswith('input.' + EQ_SINK_PREFIX):
                continue
            node = _node(oid, obj, props, devices.get(props.get('device.id')))
            if kind == SINK and name.startswith(EQ_SINK_PREFIX):
                node.eq_for = name[len(EQ_SINK_PREFIX):]
                st.eq_sinks[node.eq_for] = node
                st.nodes[oid] = node
                continue
            st.nodes[oid] = node
            if kind == SINK:
                st.sinks.append(node)
            elif kind == SOURCE:
                st.sources.append(node)
            elif kind == PLAYBACK:
                st.playing.append(node)
            else:
                st.recording.append(node)

        for out_id, in_id in links:
            if out_id in st.nodes and in_id in st.nodes:
                src, dst = st.nodes[out_id], st.nodes[in_id]
                if src.kind == PLAYBACK:
                    src.target = in_id
                if dst.kind == CAPTURE:
                    dst.target = out_id

        sink_name, source_name = self.default_name('default.audio.sink'), \
            self.default_name('default.audio.source')
        by_name = {n.name: n for n in st.nodes.values()}
        raw = by_name.get(sink_name) if sink_name else None
        st.default_sink_raw = raw.id if raw else None
        if raw and raw.eq_for:                    # the EQ is the default: its output is
            real = by_name.get(raw.eq_for)
            st.default_sink = real.id if real else raw.id
        else:
            st.default_sink = raw.id if raw else None
        src = by_name.get(source_name) if source_name else None
        st.default_source = src.id if src and src.kind == SOURCE else None

        st.sinks.sort(key=lambda n: (n.id != st.default_sink, n.title.lower()))
        st.sources.sort(key=lambda n: (n.id != st.default_source, n.title.lower()))
        st.playing.sort(key=lambda n: (n.title.lower(), n.id))
        st.recording.sort(key=lambda n: (n.title.lower(), n.id))

        per_device: Dict[int, int] = {}
        for n in list(st.sinks) + list(st.sources):
            if n.device_id is not None:
                per_device[n.device_id] = per_device.get(n.device_id, 0) + 1
        for did, obj in sorted(devices.items()):
            props = (obj.get('info') or {}).get('props') or {}
            if props.get('media.class') != 'Audio/Device':
                continue
            card = _card(did, obj, props, per_device.get(did, 0))
            if card.title == "Onboard audio":      # the codec shows on its outputs and inputs
                for n in list(st.sinks) + list(st.sources):
                    if n.device_id == did and n.title.startswith("Onboard audio ("):
                        card.title = n.title
                        break
            st.cards.append(card)
        st.cards.sort(key=lambda c: c.title.lower())
        return st


def _copy(obj):
    import copy
    return copy.deepcopy(obj)


def _merge_metadata(old: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
    current = old.setdefault('metadata', [])
    for entry in entries:
        key, subject = entry.get('key'), entry.get('subject')
        current[:] = [e for e in current if not (e.get('key') == key and e.get('subject') == subject)]
        if entry.get('value') is not None and key is not None:
            current.append(entry)


# ─── Friendly names ───────────────────────────────────────────

_BUS = {'usb': 'USB', 'pci': 'Built in', 'bluetooth': 'Bluetooth', 'firewire': 'FireWire'}


def _port_word(text: str) -> str:
    low = text.lower()
    m = re.search(r'\((hdmi|displayport|dp)\s*(\d+)?\)', low)
    if m:
        return ('HDMI' if m.group(1) == 'hdmi' else 'DisplayPort') + (f" {m.group(2)}" if m.group(2) else '')
    if 'hdmi' in low:
        return 'HDMI'
    if 'iec958' in low or 'digital' in low or 's/pdif' in low:
        return 'Digital (S/PDIF)'
    if 'headphone' in low:
        return 'Headphones'
    if 'headset' in low:
        return 'Headset'
    if 'analog' in low:
        return 'Analog'
    return ''


def pretty_title(name: str, description: str, nick: str, kind: str, dev_props: Dict[str, Any]) -> str:
    """The name shown in the list. Built from what the sound card says about itself, with a
    few fixes for names that are technically right and no use to a person."""
    low = f"{name} {description} {nick}".lower()
    port = _port_word(description or nick)
    if 'hdmi' in low or 'displayport' in low or 'navi' in low and 'hdmi/dp' in low:
        vendor = 'AMD ' if 'ati' in low or 'amd' in low or 'navi' in low else ''
        return f"{vendor}{port or 'HDMI / DisplayPort'}"
    codec = re.search(r'\b(ALC\d{3,4}|ALC\d+[A-Z]*)\b', f"{nick} {description}", re.I)
    if codec or 'hd audio controller' in low or 'hd-audio generic' in low or \
            (dev_props.get('alsa.card_name') == 'HD-Audio Generic'):
        return f"Onboard audio ({codec.group(1).upper()})" if codec else "Onboard audio"
    if 'c920' in low:
        return "Logitech C920 webcam" + (" microphone" if kind == SOURCE else "")
    if 'quadcast' in low:
        return "HyperX QuadCast" + (" headphone jack" if kind == SINK else "")
    base = nick or description or name
    base = re.sub(r'\s+(Analog|Digital|Mono|Stereo|Surround|Multichannel)\b.*$', '', base, flags=re.I)
    return base.strip() or name


def _node(oid: int, obj: Dict[str, Any], props: Dict[str, Any],
          device: Optional[Dict[str, Any]]) -> Node:
    info = obj.get('info') or {}
    kind = props['media.class']
    dev_props = ((device or {}).get('info') or {}).get('props') or {}
    name = props.get('node.name', f'node-{oid}')
    desc = props.get('node.description', '')
    nick = props.get('node.nick', '')
    profile = props.get('device.profile.description', '') or desc
    node = Node(id=oid, serial=int(props.get('object.serial', oid)), name=name, title='',
                detail='', kind=kind, state=info.get('state', 'idle'),
                channels=int(props.get('audio.channels', 2) or 2),
                device_id=props.get('device.id'))
    if kind in (SINK, SOURCE):
        if name.startswith(EQ_SINK_PREFIX):
            node.title = desc or name
        else:
            node.title = pretty_title(name, desc, nick, kind, dev_props)
            bus = _BUS.get(props.get('device.bus', ''), '')
            port = _port_word(profile)
            node.detail = ' · '.join(x for x in (bus, port) if x)
    else:
        node.app = props.get('application.name') or props.get('node.description') or name
        node.media = props.get('media.name', '')
        node.title = node.app
        node.detail = node.media if node.media and node.media.lower() != node.app.lower() else ''
    params = (info.get('params') or {})
    pl = params.get('Props') or []
    if pl and isinstance(pl[0], dict):
        p = pl[0]
        cv = p.get('channelVolumes')
        if cv:
            node.volume = gain_to_volume(max(cv) * float(p.get('volume', 1.0) or 1.0))
            node.channels = len(cv)
        elif 'volume' in p:
            node.volume = gain_to_volume(float(p['volume']))
        node.mute = bool(p.get('mute') or p.get('softMute'))
    return node


def _card(did: int, obj: Dict[str, Any], props: Dict[str, Any], nodes: int) -> Card:
    params = (obj.get('info') or {}).get('params') or {}
    name = props.get('device.name', f'device-{did}')
    desc = props.get('device.description', name)
    card = Card(id=did, name=name,
                title=pretty_title(name, desc, props.get('device.nick', ''), '', props),
                nodes=nodes, alsa_card=props.get('api.alsa.card'),
                driver=props.get('alsa.driver_name', ''))
    if 'ati hdmi' in f"{props.get('device.nick', '')} {desc}".lower() or 'hdmi' in desc.lower():
        card.title = "AMD HDMI / DisplayPort"
    cur = params.get('Profile') or []
    if cur and isinstance(cur[0], dict):
        card.current = cur[0].get('description', '')
        card.current_name = cur[0].get('name', '')
    for p in params.get('EnumProfile') or []:
        if isinstance(p, dict) and 'index' in p:
            card.profiles.append(Profile(p['index'], p.get('name', ''), p.get('description', ''),
                                         p.get('available', 'unknown') != 'no'))
    return card


def parse_dump(text: str) -> List[List[Dict[str, Any]]]:
    """Every JSON array in pw-dump's output (it prints one after another with --monitor)."""
    import json
    decoder, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        try:
            value, i = decoder.raw_decode(text, i)
        except ValueError:
            break
        if isinstance(value, list):
            out.append(value)
    return out
