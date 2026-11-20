"""The window: pair a phone (QR code, link, typed address), the paired phones (battery, last
seen, send files, send a link, ring, unpair), and the feature switches. Everything it does goes
through the background service's control socket, from a worker thread, so the window never
waits on the service. It asks the service for news once a second while it's open."""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, FEATURES, VERSION
from . import qr
from .config import config_dir, load_json, log, save_json
from .control import Control, NotRunning, start_service
from .service import human_size
from .text import t
from .widgets import (MONO_FAMILIES, T, Glitch, GlitchPanel, GlitchText, Mark, Strip, Toggle,
                      WolkButton, mix)

TABS = ('devices', 'pair', 'features')
POLL_MS = 1000
URL_RE = re.compile(r'^https?://\S+$', re.IGNORECASE)


def reduced_motion() -> bool:
    """True when the desktop asks for no animation (Plasma: animation speed set to instant)."""
    if os.environ.get('SPARK_LINK_REDUCED_MOTION', '').lower() in ('1', 'true', 'yes'):
        return True
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    try:
        with open(os.path.join(base, 'kdeglobals'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'^AnimationDurationFactor\s*=\s*([0-9.]+)', f.read(), re.M)
        return bool(match) and float(match.group(1)) == 0
    except (OSError, ValueError):
        return False


def detect_scale(root: tk.Tk) -> float:
    """Plasma publishes its scaling to X programs as Xft.dpi; Tk ignores it, so read it."""
    forced = os.environ.get('SPARK_LINK_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if os.name != 'nt' and shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            match = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if match:
                return max(1.0, min(4.0, float(match.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def pick_mono(root: tk.Tk) -> str:
    families = {n.lower(): n for n in tkfont.families(root)}
    return next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                "TkFixedFont")


def ago(when: float) -> str:
    if not when:
        return t('dev.never')
    secs = max(0, time.time() - when)
    if secs < 60:
        return t('dev.last_seen', when=t('just_now'))
    if secs < 3600:
        return t('dev.last_seen', when=t('minutes_ago', n=int(secs // 60)))
    if secs < 86400:
        return t('dev.last_seen', when=t('hours_ago', n=int(secs // 3600)))
    return t('dev.last_seen', when=t('days_ago', n=int(secs // 86400)))


class Worker:
    """Runs control requests one after another in a thread; answers come back on Tk's
    thread through pump()."""

    def __init__(self):
        self.jobs: 'queue.Queue[Tuple[Callable[[], Any], Optional[Callable[[Any], None]]]]' = \
            queue.Queue()
        self.done: 'queue.Queue[Tuple[Optional[Callable[[Any], None]], Any]]' = queue.Queue()
        threading.Thread(target=self._run, name='control', daemon=True).start()

    def _run(self):
        while True:
            fn, then = self.jobs.get()
            try:
                result = fn()
            except Exception as exc:              # NotRunning and anything unexpected
                result = exc
            self.done.put((then, result))

    def submit(self, fn: Callable[[], Any], then: Optional[Callable[[Any], None]] = None):
        self.jobs.put((fn, then))

    def pump(self) -> None:
        while True:
            try:
                then, result = self.done.get_nowait()
            except queue.Empty:
                return
            if then is not None:
                then(result)


class TabBar(tk.Frame):
    """Uppercase mono tabs; the open one is lit with an accent bar under it (Spark Monitor's)."""

    def __init__(self, parent, tabs, command, font, px):
        super().__init__(parent, bg=T["bg"])
        self.command, self.current = command, None
        self.labels: Dict[str, Tuple[tk.Label, tk.Frame]] = {}
        for i, (key, text) in enumerate(tabs):
            cell = tk.Frame(self, bg=T["bg"])
            cell.pack(side="left", padx=(0 if i == 0 else px(2), 0))
            label = tk.Label(cell, text=text.upper(), font=font, bg=T["bg"], fg=T["muted"],
                             padx=px(12), pady=px(6), cursor="hand2", takefocus=1)
            label.pack()
            bar = tk.Frame(cell, height=max(2, px(2)), bg=T["bg"])
            bar.pack(fill="x")
            for seq in ("<ButtonRelease-1>", "<Return>", "<space>"):
                label.bind(seq, lambda _e, k=key: self.command(k))
            label.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
            label.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
            self.labels[key] = (label, bar)

    def _hover(self, key, on):
        if key != self.current:
            self.labels[key][0].config(bg=T["hover"] if on else T["bg"],
                                       fg=T["text"] if on else T["muted"])

    def select(self, key):
        self.current = key
        for k, (label, bar) in self.labels.items():
            on = k == key
            label.config(fg=T["accent"] if on else T["muted"], bg=T["bg"])
            bar.config(bg=T["accent"] if on else T["bg"])


class QRView(tk.Canvas):
    """The pairing link as a QR code: dark modules on a light tile (cameras want that), with
    the four-module quiet zone."""

    def __init__(self, parent, size: int):
        super().__init__(parent, width=size, height=size, bg=T["text"], highlightthickness=1,
                         highlightbackground=T["line2"], bd=0)
        self.size, self.text = size, None

    def show(self, text: Optional[str]):
        if text == self.text:
            return
        self.text = text
        self.delete("all")
        if not text:
            return
        matrix = qr.encode(text, 'M')
        n = len(matrix) + 8
        cell = max(1, self.size // n)
        off = (self.size - cell * n) // 2 + 4 * cell
        for y, row in enumerate(matrix):
            x = 0
            while x < len(row):                   # one rectangle per run of dark modules
                if row[x]:
                    start = x
                    while x < len(row) and row[x]:
                        x += 1
                    self.create_rectangle(off + start * cell, off + y * cell, off + x * cell,
                                          off + (y + 1) * cell, fill=T["bg"], width=0)
                else:
                    x += 1


class App:
    def __init__(self, tab: Optional[str] = None, control=None, poll: bool = True):
        if os.name == 'nt':                       # Windows dev runs only
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.ctl = control or Control()
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.prefs = load_json(os.path.join(config_dir(), 'window.json'))
        self.glitch = Glitch(self.root, enabled=not reduced_motion())
        self.worker = Worker()
        self.st: Optional[Dict[str, Any]] = None
        self.running: Optional[bool] = None
        self.polling = False
        self.poll_on = poll
        self.sig: Dict[str, str] = {}
        self.tab: Optional[str] = None
        self.message = ''
        self._afters: Dict[str, str] = {}
        self._build()
        self.show(tab if tab in TABS else self.prefs.get('tab') if self.prefs.get('tab') in TABS
                  else 'devices', glitch=False)
        self.root.deiconify()
        self.glitch.add(self.title, self.mark, self.strip, self.prompt)
        self._pump()
        if poll:
            self._poll()

    # — look helpers —
    def px(self, v: float) -> int:
        return int(round(v * self.scale))

    def font(self, size: int, bold: bool = True):
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def label(self, parent, text='', size=9, bold=False, fg=None, wrap=0, **kw):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=fg or T["text"],
                        font=self.font(size, bold), justify="left", anchor="w",
                        wraplength=self.px(wrap) if wrap else 0, **kw)

    def button(self, parent, text, command, variant="ghost"):
        return WolkButton(parent, text, command, self.font(8), variant=variant,
                          padx=self.px(10), pady=self.px(4))

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.say("SOMETHING WENT WRONG", error=True)

    # — layout —
    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(600), px(480))
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon = os.path.join(here, 'icons', f'{APP_SLUG}-64.png')
        if os.path.isfile(icon):
            try:
                self._icon = tk.PhotoImage(master=root, file=icon)
                root.iconphoto(True, self._icon)
            except tk.TclError:
                pass

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK LINK", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["muted"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")

        # answers the service is waiting for (pairing, incoming files), on every tab
        self.prompt = GlitchPanel(root, T["panel2"])
        self.prompt_body = tk.Frame(self.prompt.inner, bg=T["panel2"])
        self.prompt_body.pack(fill="x", padx=px(12), pady=px(10))

        self.tabs = TabBar(root, [(k, t(f'app.tab.{k}')) for k in TABS], self.show,
                           self.font(9), px)
        self.tabs.pack(fill="x", padx=px(10), pady=(px(6), 0))
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        self.views = {k: tk.Frame(self.body, bg=bg) for k in TABS}
        self.foot = tk.Label(root, text="", bg=T["panel"], fg=T["muted"], font=self.font(8, False),
                             anchor="w", padx=px(12), pady=px(5))
        self.foot.pack(fill="x", side="bottom")
        tk.Frame(root, bg=T["line"], height=1).pack(fill="x", side="bottom")

        self._build_features()
        geometry = self.prefs.get('geometry')
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{min(px(780), int(sw * .9))}x{min(px(640), int(sh * .9))}")

    def show(self, tab: str, glitch: bool = True):
        if tab == self.tab:
            return
        if self.tab:
            self.views[self.tab].pack_forget()
        self.tab = tab
        self.tabs.select(tab)
        self.views[tab].pack(fill="both", expand=True, padx=self.px(14), pady=self.px(10))
        self.sig.pop(tab, None)
        self.render()
        if glitch:
            self.glitch.now(self.title)

    def say(self, text: str, error: bool = False):
        self.message = text
        self.foot.config(text=text, fg=T["pink"] if error else T["muted"])
        if error:
            self.glitch.now(self.title, self.prompt, strong=True)

    # — talking to the service —
    def call(self, req: Dict[str, Any], then: Optional[Callable[[Dict[str, Any]], None]] = None,
             refresh: bool = True):
        def done(result):
            if isinstance(result, NotRunning):
                self.running = False
                self.render()
                self.say(str(result), error=True)
                return
            if isinstance(result, Exception):
                self.say(str(result), error=True)
                return
            if not result.get('ok') and result.get('error'):
                self.say(result['error'], error=True)
            if then is not None:
                then(result)
            if refresh:
                self.poll_now()
        self.worker.submit(lambda: self.ctl.request(req), done)

    def _pump(self):
        self.worker.pump()
        self._afters['pump'] = self.root.after(50, self._pump)

    def _poll(self):
        if self.root.state() != 'iconic':
            self.poll_now()
        self._afters['poll'] = self.root.after(POLL_MS, self._poll)

    def poll_now(self):
        if self.polling:
            return
        self.polling = True

        def done(result):
            self.polling = False
            if isinstance(result, Exception):
                self.running = False
                self.st = None
            else:
                self.running = True
                self.st = result
            self.render()

        self.worker.submit(lambda: self.ctl.request({'cmd': 'status'}), done)

    def apply_status(self, st: Optional[Dict[str, Any]], running: bool = True):
        """Tests: show this status as if the service had sent it."""
        self.st, self.running = st, running
        self.render()

    # — drawing —
    def changed(self, key: str, value: Any) -> bool:
        sig = json.dumps(value, sort_keys=True, default=str)
        if self.sig.get(key) == sig:
            return False
        self.sig[key] = sig
        return True

    def render(self):
        st = self.st
        if self.running is False:
            self.status.config(text="● " + t('app.status.stopped'), fg=T["pink"])
        elif st:
            if st['error']:
                self.status.config(text="● " + st['error'].upper()[:60], fg=T["pink"])
            elif st['listening']:
                self.status.config(text="● " + t('app.status.listening', port=st['port']),
                                   fg=T["accent"])
            else:
                self.status.config(text="○ " + t('app.status.idle'), fg=T["muted"])
            if st['events'] and not self.message:
                self.foot.config(text=st['events'][-1]['text'], fg=T["muted"])
        self.render_prompt()
        if self.tab == 'devices':
            self.render_devices()
        elif self.tab == 'pair':
            self.render_pair()
        elif self.tab == 'features':
            self.render_features()

    def clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    # — the prompt: what the service is waiting for —
    def render_prompt(self):
        st = self.st or {}
        req = (st.get('pairing') or {}).get('request')
        offer = next((x for x in st.get('transfers', []) if x['state'] == 'waiting'), None)
        what = ('stopped',) if self.running is False else \
            ('pair', req) if req else ('offer', offer['key'], offer['name']) if offer else None
        if not self.changed('prompt', what):
            return
        self.clear(self.prompt_body)
        if what is None:
            self.prompt.pack_forget()
            return
        body, px = self.prompt_body, self.px
        if what[0] == 'stopped':
            # the buttons go in first, so a long sentence wraps instead of squeezing them
            self.button(body, t('app.start'), self.start_service, "primary").pack(side="right")
            self.label(body, t('app.stopped'), 9, wrap=400).pack(side="left", fill="x",
                                                                  expand=True)
        elif what[0] == 'pair':
            col = tk.Frame(body, bg=body.cget('bg'))
            col.pack(side="left", fill="x", expand=True)
            self.label(col, t('pair.request', name=req['name']), 11, True,
                       fg=T["accent"]).pack(anchor="w")
            self.label(col, t('pair.request_key', key=req['key']), 8, fg=T["muted"]).pack(
                anchor="w", pady=(px(2), 0))
            self.button(body, t('pair.no'), lambda: self.call(
                {'cmd': 'pair.answer', 'yes': False})).pack(side="right", padx=(px(6), 0))
            self.button(body, t('pair.yes'), lambda: self.call(
                {'cmd': 'pair.answer', 'yes': True}), "primary").pack(side="right")
        else:
            name = self.device_name(offer['device'])
            self.button(body, t('offer.decline'), lambda k=offer['key']: self.call(
                {'cmd': 'file.answer', 'key': k, 'accept': False})).pack(side="right",
                                                                          padx=(px(6), 0))
            self.button(body, t('offer.accept'), lambda k=offer['key']: self.call(
                {'cmd': 'file.answer', 'key': k, 'accept': True}), "primary").pack(side="right")
            self.label(body, t('offer.in', name=name, file=offer['name'],
                               size=human_size(offer['size'])), 9, wrap=340).pack(
                side="left", fill="x", expand=True)
        self.prompt.pack(fill="x", padx=px(14), pady=(px(8), 0), before=self.tabs)
        self.glitch.now(self.prompt, strong=True)
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def device_name(self, device_id: str) -> str:
        for dev in (self.st or {}).get('devices', []):
            if dev['id'] == device_id:
                return dev['name']
        return '?'

    # — Phones —
    def render_devices(self):
        st = self.st or {}
        devices = st.get('devices', [])
        view = [{k: d[k] for k in ('id', 'name', 'connected', 'battery', 'charging',
                                   'always_accept', 'key', 'features')} for d in devices]
        # last seen moves on its own; redraw it at most once a minute
        minute = int(time.time() // 60)
        transfers = [x for x in st.get('transfers', []) if x['state'] != 'waiting'][-8:]
        if not self.changed('devices', [view, minute, transfers, self.running]):
            return
        frame, px = self.views['devices'], self.px
        self.clear(frame)
        if not devices:
            self.label(frame, t('dev.none'), 9, wrap=560, fg=T["muted"]).pack(anchor="w",
                                                                             pady=px(6))
            self.button(frame, t('app.tab.pair'), lambda: self.show('pair'),
                        "primary").pack(anchor="w", pady=px(6))
            return
        for dev in devices:
            card = GlitchPanel(frame, T["panel"])
            card.pack(fill="x", pady=(0, px(8)))
            inner = tk.Frame(card.inner, bg=T["panel"])
            inner.pack(fill="x", padx=px(12), pady=px(10))
            top = tk.Frame(inner, bg=T["panel"])
            top.pack(fill="x")
            self.label(top, dev['name'], 11, True).pack(side="left")
            on = dev['connected']
            self.label(top, ("● " + t('dev.connected')) if on else ("○ " + t('dev.offline')),
                       7, True, fg=T["accent"] if on else T["dim"]).pack(side="left",
                                                                         padx=(px(10), 0))
            facts = []
            if dev['battery'] is not None:
                facts.append(t('dev.battery_charging' if dev['charging'] else 'dev.battery',
                               level=dev['battery']))
            if not on:
                facts.append(ago(dev['last_seen']))
            facts.append(t('dev.key', key=dev['key']))
            low = dev['battery'] is not None and dev['battery'] <= 15 and not dev['charging']
            self.label(inner, '  ·  '.join(facts), 8, fg=T["gold"] if low else T["muted"]).pack(
                anchor="w", pady=(px(3), px(8)))
            row = tk.Frame(inner, bg=T["panel"])
            row.pack(fill="x")
            feats = set(dev['features'])
            mine = (st.get('features') or {})
            for text, feature, fn in ((t('dev.send_files'), 'files', self.send_files),
                                      (t('dev.send_link'), 'url', self.send_link),
                                      (t('dev.ring'), 'ring', self.ring)):
                b = self.button(row, text, lambda f=fn, d=dev: f(d))
                b.pack(side="left", padx=(0, px(6)))
                b.set_enabled(on and feature in feats and mine.get(feature, False))
            self.button(row, t('dev.unpair'), lambda d=dev: self.unpair(d), "danger").pack(
                side="right")
            Toggle(inner, t('dev.always_accept'), dev['always_accept'],
                   lambda v, d=dev: self.call({'cmd': 'device.always_accept', 'device': d['id'],
                                               'on': v}), self.font(7)).pack(anchor="w",
                                                                              pady=(px(8), 0))
        if transfers:
            self.label(frame, t('dev.transfers'), 7, True, fg=T["muted"]).pack(anchor="w",
                                                                        pady=(px(6), px(4)))
            for x in reversed(transfers):
                row = tk.Frame(frame, bg=T["bg"])
                row.pack(fill="x", pady=(0, px(2)))
                pct = f" {int(100 * x['done'] / x['size'])} %" if x['size'] and \
                    x['state'] in ('sending', 'receiving') else ''
                way = t('xfer.in' if x['direction'] == 'in' else 'xfer.out',
                        name=self.device_name(x['device']))
                colour = T["pink"] if x['state'] in ('failed',) else \
                    T["accent"] if x['state'] == 'done' else T["text"]
                self.label(row, f"{x['name']}  {way}  ·  "
                                f"{t('xfer.state.' + x['state'])}{pct}"
                                f"{'  ·  ' + x['reason'] if x['reason'] and x['state'] == 'failed' else ''}",
                           8, fg=colour).pack(side="left")
                if x['state'] in ('offered', 'sending', 'receiving', 'sent'):
                    self.button(row, t('xfer.stop'), lambda k=x['key']: self.call(
                        {'cmd': 'transfer.cancel', 'key': k})).pack(side="right")

    def send_files(self, dev):
        paths: List[str] = []
        kd = shutil.which('kdialog')
        if kd:
            try:
                out = subprocess.run([kd, '--title', t('dev.files_title', name=dev['name']),
                                      '--getopenfilename', os.path.expanduser('~'),
                                      '--multiple', '--separate-output'],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=3600)
                paths = [p for p in out.stdout.decode('utf-8', 'replace').splitlines() if p]
            except (OSError, subprocess.SubprocessError):
                kd = None
        if not kd:
            from tkinter import filedialog
            paths = list(filedialog.askopenfilenames(
                parent=self.root, title=t('dev.files_title', name=dev['name'])))
        if paths:
            self.call({'cmd': 'send.files', 'device': dev['id'], 'paths': paths},
                      lambda r: self.say(t('dev.files_sending', n=len(paths), name=dev['name']))
                      if r.get('ok') else None)

    def send_link(self, dev):
        top = tk.Toplevel(self.root, bg=T["bg"])
        top.title(t('dev.link_title', name=dev['name']))
        top.transient(self.root)
        px = self.px
        self.label(top, t('dev.link_prompt'), 9).pack(anchor="w", padx=px(14),
                                                      pady=(px(12), px(6)))
        entry = tk.Entry(top, font=self.font(10, False), bg=T["out_bg"], fg=T["text"],
                         insertbackground=T["accent"], relief="flat", highlightthickness=1,
                         highlightbackground=T["line2"], highlightcolor=T["accent"], width=48)
        entry.pack(fill="x", padx=px(14), ipady=px(4))
        try:
            clip = self.root.clipboard_get()
            if URL_RE.match(clip.strip()):
                entry.insert(0, clip.strip())
        except tk.TclError:
            pass
        entry.focus_set()

        def send(_e=None):
            url = entry.get().strip()
            if not URL_RE.match(url):
                self.say(t('err.bad_url'), error=True)
                return
            top.destroy()
            self.call({'cmd': 'send.url', 'device': dev['id'], 'url': url},
                      lambda r: self.say(t('dev.link_sent', name=dev['name']))
                      if r.get('ok') else None)

        row = tk.Frame(top, bg=T["bg"])
        row.pack(fill="x", padx=px(14), pady=px(12))
        self.button(row, t('dev.link_send'), send, "primary").pack(side="right")
        entry.bind("<Return>", send)
        top.bind("<Escape>", lambda _e: top.destroy())

    def ring(self, dev):
        self.call({'cmd': 'ring', 'device': dev['id']},
                  lambda r: self.say(t('dev.rung', name=dev['name'])) if r.get('ok') else None)

    def unpair(self, dev):
        if self.confirm(t('dev.unpair_title', name=dev['name']),
                        t('dev.unpair_confirm', name=dev['name']), t('dev.unpair')):
            self.call({'cmd': 'unpair', 'device': dev['id']})

    def confirm(self, title: str, text: str, ok: str) -> bool:
        top = tk.Toplevel(self.root, bg=T["bg"])
        top.title(title)
        top.transient(self.root)
        px = self.px
        answer = {'yes': False}
        self.label(top, title, 11, True, fg=T["pink"]).pack(anchor="w", padx=px(14),
                                                            pady=(px(12), px(4)))
        self.label(top, text, 9, wrap=380).pack(anchor="w", padx=px(14))
        row = tk.Frame(top, bg=T["bg"])
        row.pack(fill="x", padx=px(14), pady=px(12))

        def yes():
            answer['yes'] = True
            top.destroy()

        self.button(row, ok, yes, "danger").pack(side="right")
        self.button(row, t('dev.keep'), top.destroy).pack(
            side="right", padx=(0, px(6)))
        top.bind("<Escape>", lambda _e: top.destroy())
        top.wait_visibility()
        top.grab_set()
        self.root.wait_window(top)
        return answer['yes']

    # — Pair a phone —
    def render_pair(self):
        st = self.st or {}
        p = st.get('pairing') or {}
        state = ('active', p.get('link'), p.get('left'), p.get('wrong')) if p.get('active') \
            else ('idle', p.get('note'), st.get('error'))
        if not self.changed('pair', [state, self.running]):
            return
        frame, px = self.views['pair'], self.px
        if p.get('active') and getattr(self, '_pair_active', False):
            self._pair_left.config(text=t('pair.waiting', left=f"{p['left'] // 60}:"
                                                               f"{p['left'] % 60:02d}"))
            return
        self.clear(frame)
        self._pair_active = bool(p.get('active'))
        if not p.get('active'):
            self.label(frame, t('pair.intro'), 9, wrap=560).pack(anchor="w", pady=(px(4), px(10)))
            if p.get('note'):
                self.label(frame, p['note'], 9, wrap=560, fg=T["gold"]).pack(anchor="w",
                                                                           pady=(0, px(10)))
            if st.get('error'):
                self.label(frame, t('pair.not_listening', why=st['error']), 9, wrap=560,
                           fg=T["pink"]).pack(anchor="w", pady=(0, px(10)))
            self.button(frame, t('pair.start'), self.start_pairing, "primary").pack(anchor="w")
            self.label(frame, t('feat.local_only'), 8, wrap=560, fg=T["muted"]).pack(
                anchor="w", pady=(px(16), 0))
            return
        row = tk.Frame(frame, bg=T["bg"])
        row.pack(fill="x")
        code = QRView(row, px(250))
        code.pack(side="left", anchor="n")
        code.show(p['link'])
        col = tk.Frame(row, bg=T["bg"])
        col.pack(side="left", fill="both", expand=True, padx=(px(16), 0))
        self.label(col, t('pair.intro'), 9, wrap=330).pack(anchor="w")
        self.label(col, f"{p['code'][:3]} {p['code'][3:]}", 22, True, fg=T["accent"]).pack(
            anchor="w", pady=(px(10), 0))
        self._pair_left = self.label(col, t('pair.waiting', left=f"{p['left'] // 60}:"
                                                                 f"{p['left'] % 60:02d}"),
                                     7, True, fg=T["muted"])
        self._pair_left.pack(anchor="w", pady=(px(2), px(10)))
        addresses = st['pc']['addresses']
        if addresses:
            self.label(col, t('pair.typed', address=f"{addresses[0]}:{st['port']}",
                              code=p['code'], key=st['pc']['key']), 8, wrap=330,
                       fg=T["muted"]).pack(anchor="w")
        else:
            self.label(col, t('pair.no_address'), 8, wrap=330, fg=T["gold"]).pack(anchor="w")
        self.button(col, t('pair.stop'), lambda: self.call({'cmd': 'pair.cancel'})).pack(
            anchor="w", pady=(px(12), 0))
        self.label(frame, t('pair.no_camera'), 8, fg=T["muted"]).pack(anchor="w",
                                                                      pady=(px(12), px(4)))
        linkrow = tk.Frame(frame, bg=T["bg"])
        linkrow.pack(fill="x")
        link = tk.Entry(linkrow, font=self.font(8, False), bg=T["out_bg"], fg=T["text"],
                        relief="flat", highlightthickness=1, highlightbackground=T["line"],
                        readonlybackground=T["out_bg"])
        link.insert(0, p['link'])
        link.config(state="readonly")
        link.pack(side="left", fill="x", expand=True, ipady=px(3))

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(p['link'])
            self.say(t('pair.copied'))

        self.button(linkrow, t('pair.copy'), copy).pack(side="left", padx=(px(6), 0))
        self.glitch.now(self.title)

    def start_pairing(self):
        if self.running is False or self.st is None:
            self.say(t('app.starting'))

            def started(why):
                if why:
                    self.say(t('app.start_failed', why=why), error=True)
                    return
                self.running = True
                self.call({'cmd': 'pair.start'})

            self.worker.submit(start_service, started)
        else:
            self.call({'cmd': 'pair.start'})

    def start_service(self):
        self.say(t('app.starting'))
        self.worker.submit(start_service, lambda why: self.say(
            t('app.start_failed', why=why), error=True) if why else self.poll_now())

    # — Features —
    def _build_features(self):
        frame, px = self.views['features'], self.px
        self.toggles: Dict[str, Toggle] = {}
        for name in FEATURES:
            row = tk.Frame(frame, bg=T["bg"])
            row.pack(fill="x", pady=(0, px(10)))
            tog = Toggle(row, t(f'feat.{name}'), False,
                         lambda v, n=name: self.call({'cmd': 'feature', 'name': n, 'on': v}),
                         self.font(8))
            tog.pack(anchor="w")
            self.toggles[name] = tog
            self.label(row, t(f'feat.{name}_about'), 8, wrap=560, fg=T["muted"]).pack(
                anchor="w", padx=(px(2), 0), pady=(px(3), 0))
        self.label(frame, t('feat.local_only'), 8, wrap=560, fg=T["muted"]).pack(
            anchor="w", pady=(px(8), 0))

    def render_features(self):
        feats = (self.st or {}).get('features')
        if not feats or not self.changed('features', feats):
            return
        for name, tog in self.toggles.items():
            if tog.value != feats.get(name, False):
                tog.set(feats.get(name, False))

    # — closing —
    def close(self):
        if self.st and (self.st.get('pairing') or {}).get('active'):
            try:                                   # pairing only while this window is open
                self.ctl.request({'cmd': 'pair.cancel'})
            except Exception:
                pass
        try:
            self.prefs['tab'] = self.tab
            self.prefs['geometry'] = self.root.geometry()
            save_json(os.path.join(config_dir(), 'window.json'), self.prefs)
        except OSError:
            pass
        self.destroy()

    def destroy(self):
        for job in self._afters.values():
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
