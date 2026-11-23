"""The window, the refresh schedule, the actions and the alerts.

Every SSH call and website check runs on a worker thread; results come back through a queue
that Tk's thread drains, so the window never waits on the network. Refreshes run every 15 s for
the machine that is open and every 60 s for the rest, and stop while the window is hidden."""

import os
import queue
import re
import shlex
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import (APP_CLASS, APP_NAME, APP_SLUG, BACKGROUND_REFRESH_S, OPEN_REFRESH_S, VERSION,
               actions, alerts, config as configmod, core, dialogs, report, screen, sites)
from .core import log, reduced_motion
from .probe import OK, REBOOT_GRACE_S, Problem, Result, problems
from .text import t, verdict_text
from .transport import DONE, NEEDS_PASSWORD, SshTransport
from .screen import DENIED
from .widgets import MONO_FAMILIES, T, Glitch, GlitchText, Mark, Strip

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(APP_DIR, 'machines.example.toml')


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux; Plasma publishes it as Xft.dpi."""
    forced = os.environ.get('SPARK_CONNECT_SCALE')
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


def pick_mono_cached(root: tk.Tk) -> str:
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                "TkFixedFont")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_config(path: Optional[str] = None) -> Tuple[configmod.Config, Optional[str]]:
    path = path or core.config_path()
    try:
        return configmod.load(path), None
    except configmod.ConfigError as exc:
        return configmod.Config(path=path, found=True), str(exc)


class App:
    def __init__(self, config_path: Optional[str] = None, transport=None,
                 site_checker: Optional[Callable] = None, auto_refresh: bool = True,
                 notifier: Optional[Callable[[str, str], bool]] = None):
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.config_path = config_path
        self.config, self.config_error = load_config(config_path)
        self.example_path = EXAMPLE
        self.transport = transport or SshTransport()
        self.check_site = site_checker or sites.check
        self.notifier = notifier or alerts.notify
        self.auto = auto_refresh

        self.results: Dict[str, Result] = {}
        self.previous: Dict[str, Result] = {}
        self.down_since: Dict[str, float] = {}
        self.rebooting: Dict[str, float] = {}       # machine -> when we sent it a reboot
        self.shares: Dict[str, screen.Share] = {}   # machine -> its open screen share
        self._share_timer: Optional[str] = None
        self.site_results: Dict[str, sites.SiteResult] = {}
        self.due: Dict[Tuple, float] = {}
        self.pending: set = set()
        self.queue: "queue.Queue" = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=APP_SLUG)
        self.alerts = alerts.Alerts()
        self.visible = True
        self._timer: Optional[str] = None
        self._polling = False
        self.open_name: Optional[str] = None
        self.machine_view = None

        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.glitch = Glitch(self.root, enabled=not reduced_motion())
        self._build()
        from .views import OverviewView
        self.overview = OverviewView(self)
        self.overview.pack(fill="both", expand=True)
        self._status_idle()
        self.root.deiconify()
        self.root.bind('<Map>', self._mapped, add='+')
        self.root.bind('<Unmap>', self._unmapped, add='+')
        self.glitch.add(self.title, self.mark, self.strip)
        self.reset_schedule()

    # look helpers
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status(t('status.crashed'), T["pink"])
        self.glitch.now(self.title, strong=True)

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(640), px(420))
        for path in (os.path.join(APP_DIR, 'icons', f'{APP_SLUG}-64.png'),
                     os.path.join(APP_DIR, 'icons', f'{APP_SLUG}-256.png')):
            if os.path.isfile(path):
                try:
                    self._icon = tk.PhotoImage(master=root, file=path)
                    root.iconphoto(True, self._icon)
                    break
                except tk.TclError:
                    pass
        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(34), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK CONNECT", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")
        self.body = tk.Frame(root, bg=bg)
        self.body.pack(fill="both", expand=True)
        root.bind("<F5>", lambda _e: self.reload())
        root.bind("<Escape>", lambda _e: self.show_overview())
        root.bind("<Control-w>", lambda _e: self.close())
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(px(1060), int(sw * 0.85))}x{min(px(720), int(sh * 0.85))}")

    # — status line —
    def _status_idle(self):
        self._status_after = None
        if self.config_error:
            self.status.config(text="● " + t('status.config_error'), fg=T["pink"])
        elif not self.config.machines:
            self.status.config(text="● " + t('status.no_config'), fg=T["muted"])
        else:
            n = len(self.config.machines)
            text = t('status.watching_one') if n == 1 else t('status.watching', n=n)
            if not self.visible:
                text = t('status.paused')
            self.status.config(text="● " + text, fg=T["accent"])

    def set_status(self, text: str, colour: str = T["accent"], hold_ms: int = 6000):
        self.status.config(text="● " + text.upper(), fg=colour)
        if getattr(self, '_status_after', None):
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(hold_ms, self._status_idle)

    # — views —
    def show_overview(self):
        if self.machine_view is None:
            return
        self.machine_view.close()
        self.machine_view.destroy()
        self.machine_view = None
        self.open_name = None
        self.overview.pack(fill="both", expand=True)
        self.overview.refresh()
        self.glitch.now(self.title)

    def open_machine(self, name: str):
        machine = self.machine(name)
        if machine is None:
            return
        from .views import MachineView
        if self.machine_view is not None:
            self.machine_view.close()
            self.machine_view.destroy()
        self.overview.pack_forget()
        self.open_name = name
        self.machine_view = MachineView(self, machine)
        self.machine_view.pack(fill="both", expand=True)
        key = ('machine', name)
        result = self.results.get(name)
        if self.auto and (result is None or time.time() - result.at > OPEN_REFRESH_S):
            self.start(key)

    def machine(self, name: str) -> Optional[configmod.Machine]:
        return next((m for m in self.config.machines if m.name == name), None)

    def problems_of(self, machine: configmod.Machine) -> List[Problem]:
        return problems(machine, self.results.get(machine.name),
                        self.down_since.get(machine.name), self.rebooting.get(machine.name))

    def net_rates(self, name: str) -> Dict[str, Tuple[float, float]]:
        new, old = self.results.get(name), self.previous.get(name)
        if not (new and old and new.ok and old.ok):
            return {}
        a, b = new.data, old.data
        if not (a['time'] and b['time']) or a['time'] <= b['time']:
            return {}
        dt = a['time'] - b['time']
        before = {n['iface']: n for n in b['net']}
        rates = {}
        for n in a['net']:
            o = before.get(n['iface'])
            if o and None not in (n['rx'], n['tx'], o['rx'], o['tx']) and n['rx'] >= o['rx']:
                rates[n['iface']] = ((n['rx'] - o['rx']) / dt, (n['tx'] - o['tx']) / dt)
        return rates

    def redraw(self):
        if self.machine_view is not None:
            self.machine_view.refresh()
        else:
            self.overview.refresh()

    # — config —
    def reload(self):
        """F5: read the machine list again and refresh everything now."""
        self.config, self.config_error = load_config(self.config_path)
        names = {m.name for m in self.config.machines}
        for name in list(self.results):
            if name not in names:
                self.results.pop(name)
        if self.machine_view is not None and self.open_name not in names:
            self.show_overview()
        self.overview.build()
        self._status_idle()
        self.reset_schedule(now=True)

    # — the schedule —
    def interval(self, key: Tuple) -> float:
        if key == ('machine', self.open_name):
            return OPEN_REFRESH_S
        return BACKGROUND_REFRESH_S

    def reset_schedule(self, now: bool = True):
        start = time.monotonic() if now else time.monotonic() + BACKGROUND_REFRESH_S
        self.due = {('machine', m.name): start for m in self.config.machines}
        self.due.update({('site', s.name): start for s in self.config.sites})
        if self.config_error:
            self.due = {}
        self.schedule()

    def schedule(self):
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None
        if not self.auto or not self.visible or not self.due:
            return
        waiting = [d for k, d in self.due.items() if k not in self.pending]
        if not waiting:
            return
        delay = max(0.2, min(waiting) - time.monotonic())
        self._timer = self.root.after(int(delay * 1000), self._run_due)

    def _run_due(self):
        self._timer = None
        now = time.monotonic()
        for key, due in list(self.due.items()):
            if due <= now and key not in self.pending:
                self.start(key)
        self.schedule()

    def start(self, key: Tuple):
        """Run one refresh on a worker thread."""
        if key in self.pending:
            return
        if key[0] == 'machine':
            machine = self.machine(key[1])
            if machine is None:
                return
            job = lambda: self.transport.fetch(machine)  # noqa: E731
        else:
            site = next((s for s in self.config.sites if s.name == key[1]), None)
            if site is None:
                return
            job = lambda: self.check_site(site)  # noqa: E731
        self.submit(key, job)

    def submit(self, key: Tuple, job: Callable, done: Optional[Callable] = None):
        self.pending.add(key)
        future = self.pool.submit(job)
        future.add_done_callback(lambda f: self.queue.put((key, f, done)))
        if not self._polling:
            self._polling = True
            self.root.after(100, self._poll)

    def _poll(self):
        while True:
            try:
                key, future, done = self.queue.get_nowait()
            except queue.Empty:
                break
            self.pending.discard(key)
            try:
                value = future.result()
            except Exception as exc:          # a bug in a job, not a machine problem
                log.exception("job %s failed", key)
                value = exc
            if done is not None:
                done(value)
            elif key[0] == 'machine' and isinstance(value, Result):
                self.apply_result(value)
                self.due[key] = time.monotonic() + self.interval(key)
            elif key[0] == 'site' and isinstance(value, sites.SiteResult):
                self.apply_site(value)
                self.due[key] = time.monotonic() + self.interval(key)
        if self.pending:
            self.root.after(100, self._poll)
        else:
            self._polling = False
        self.schedule()

    def refresh_machine(self, name: str):
        self.start(('machine', name))

    # — results —
    def apply_result(self, result: Result):
        name = result.machine
        machine = self.machine(name)
        if machine is None:
            return
        old = self.results.get(name)
        sent = self.rebooting.get(name)
        if sent is not None and (result.at - sent >= REBOOT_GRACE_S or (
                result.ok and result.data.get('uptime_s') is not None
                and result.at - result.data['uptime_s'] > sent - 30)):
            self.rebooting.pop(name)                # back up, or silent for too long
            sent = None
        if result.ok:
            self.down_since.pop(name, None)
            if old is not None and old.ok:
                self.previous[name] = old
        else:
            self.down_since.setdefault(name, result.at)
        self.results[name] = result
        found = self.problems_of(machine)
        if result.ok:
            wrong = {('machine', name, p.key, str(p.unit or p.args.get('mount') or
                                                  p.args.get('name') or '')): verdict_text(p)
                     for p in found if p.level != OK}
            events = self.alerts.update(wrong, scope=('machine', name))
        elif sent is not None:                      # the reboot we sent, not an outage
            events = self.alerts.update({}, scope=('machine', name, 'down'))
        else:
            events = self.alerts.update({('machine', name, 'down'): verdict_text(found[0])},
                                        scope=('machine', name, 'down'))
        self._announce(name, events)
        self.redraw()
        if found and (old is None or problems(machine, old) != found) and \
                found[0].level != OK and self.machine_view is not None:
            self.glitch.now(self.machine_view.title)

    def apply_site(self, result: sites.SiteResult):
        self.site_results[result.name] = result
        wrong = {} if result.ok else {('site', result.name): (
            f"HTTP {result.status}" if result.status else result.error)}
        self._announce(result.name, self.alerts.update(wrong, scope=('site', result.name)))
        if self.machine_view is None:
            self.overview.refresh()

    def _announce(self, title: str, events):
        for kind, _key, text in events:
            body = text if kind == alerts.BAD else t('alert.back', text=text)
            if not self.notifier(f"{APP_NAME}: {title}", body):
                self.set_status(f"{title}: {body}",
                                T["pink"] if kind == alerts.BAD else T["accent"])
            if kind == alerts.BAD:
                self.glitch.now(self.title, self.strip, strong=True)

    # — actions —
    def confirm(self, c: actions.Confirm) -> bool:
        return bool(dialogs._show('warning', c.title, c.message,
                                  [(t('action.cancel').upper(), False, False),
                                   (c.button.upper(), True, True)],
                                  self.root, c.detail, False))

    def ask_restart(self, machine: configmod.Machine, scope: str, unit: str):
        if not machine.can_restart(scope, unit):
            return
        if not self.confirm(actions.confirm_restart(machine, scope, unit)):
            log.info("restart %s:%s on %s cancelled", scope, unit, machine.name)
            return
        self.set_status(f"{t('action.restart')} {unit}…", T["gold"], hold_ms=60000)

        def finished(outcome):
            if not hasattr(outcome, 'outcome'):
                outcome = type('R', (), {'outcome': 'failed', 'message': str(outcome)})()
            if outcome.outcome == DONE:
                self.set_status(t('status.restarted', unit=unit, machine=machine.name))
                self.refresh_machine(machine.name)
            elif outcome.outcome == NEEDS_PASSWORD:
                self._status_idle()
                if dialogs.askyesno(t('result.needs_password_title'),
                                    t('result.needs_password', machine=machine.name,
                                      unit=unit), parent=self.root, detail=outcome.message):
                    self._terminal(machine, actions.typed_not_run(
                        f"sudo systemctl restart {shlex.quote(unit)}"))
            else:
                self._status_idle()
                self.glitch.now(self.title, strong=True)
                dialogs.showerror(t('result.failed_title'),
                                  t('result.failed', unit=unit, machine=machine.name,
                                    message=outcome.message), parent=self.root)

        self.submit(('restart', machine.name, scope, unit),
                    lambda: self.transport.restart(machine, scope, unit), finished)

    def standbys_for(self, machine: configmod.Machine) -> List[str]:
        return [m.name for m in self.config.machines
                if m.failover and m.failover.watches == machine.name]

    def ask_update(self, machine: configmod.Machine):
        result = self.results.get(machine.name)
        pk = result.data.get('packages', {}) if result is not None and result.ok else {}
        command = actions.update_command(pk.get('manager', ''))
        if 'update' not in machine.allow:
            return
        if not command:
            dialogs.showinfo(t('result.update_unknown_title'),
                             t('result.update_unknown', machine=machine.name), parent=self.root)
            return
        if self.confirm(actions.confirm_update(machine, pk['manager'], pk.get('updates'),
                                               pk.get('security'))):
            self._terminal(machine, actions.update_remote(command))

    def ask_reboot(self, machine: configmod.Machine):
        if 'reboot' not in machine.allow:
            return
        if not self.confirm(actions.confirm_reboot(machine, self.standbys_for(machine))):
            log.info("reboot of %s cancelled", machine.name)
            return
        self.set_status(t('status.rebooting', machine=machine.name), T["gold"], hold_ms=60000)

        def finished(outcome):
            if not hasattr(outcome, 'outcome'):
                outcome = type('R', (), {'outcome': 'failed', 'message': str(outcome)})()
            if outcome.outcome == DONE:
                self.rebooting[machine.name] = time.time()
                self.redraw()
                for delay in (20000, 60000, 120000):
                    self.root.after(delay, lambda: self.refresh_machine(machine.name))
            elif outcome.outcome == NEEDS_PASSWORD:
                self._status_idle()
                if dialogs.askyesno(t('result.needs_password_title'),
                                    t('result.reboot_password', machine=machine.name),
                                    parent=self.root, detail=outcome.message):
                    self._terminal(machine, actions.typed_not_run("sudo systemctl reboot"))
            else:
                self._status_idle()
                self.glitch.now(self.title, strong=True)
                dialogs.showerror(t('result.reboot_failed_title'),
                                  t('result.reboot_failed', machine=machine.name,
                                    message=outcome.message), parent=self.root)

        self.submit(('reboot', machine.name), lambda: self.transport.reboot(machine), finished)

    def ask_terminal(self, machine: configmod.Machine):
        if self.confirm(actions.confirm_terminal(machine)):
            self._terminal(machine)

    def ask_console(self, machine: configmod.Machine):
        """See console: always the sudo path, the password is typed in the terminal."""
        if not machine.console:
            return
        if self.confirm(actions.confirm_console(machine)):
            import socket
            self._terminal(machine, actions.console_remote(socket.gethostname()))

    def ask_failback(self, machine: configmod.Machine):
        if not machine.failover or not machine.failover.failback:
            return
        if self.confirm(actions.confirm_failback(machine)):
            self._terminal(machine, actions.typed_not_run(machine.failover.failback))

    def _terminal(self, machine: configmod.Machine, remote: Optional[str] = None):
        if not actions.open_terminal(machine, remote):
            dialogs.showerror(t('result.no_terminal_title'), t('result.no_terminal'),
                              parent=self.root)

    # — screen sharing —
    def sharing_busy(self, name: str) -> bool:
        return name in self.shares or ('share', name) in self.pending

    def ask_share(self, machine: configmod.Machine, sudo: bool = False):
        if not machine.desktop or self.sharing_busy(machine.name):
            return
        if not self.confirm(actions.confirm_share(machine, sudo)):
            log.info("screen share with %s cancelled", machine.name)
            return
        share = screen.Share(machine, self.transport, sudo,
                             terminal=lambda m, remote: actions.open_terminal(m, remote))
        self._start_share(machine, share, share.connect)

    def _start_share(self, machine: configmod.Machine, share, job):
        self.set_status(t('status.sharing', machine=machine.name.upper()), T["gold"],
                        hold_ms=120000)

        def finished(outcome):
            if not isinstance(outcome, screen.ShareResult):
                outcome = screen.ShareResult('failed', 'error', str(outcome))
            if outcome.outcome == DONE:
                self.shares[machine.name] = share
                self.set_status(t('status.sharing', machine=machine.name.upper()), T["pink"],
                                hold_ms=10 * 60 * 1000)
                self.glitch.now(self.title, strong=True)
                self._share_tick()
                return
            self._status_idle()
            if outcome.outcome == NEEDS_PASSWORD and job == share.connect:
                if dialogs.askyesno(t('share.password_title'),
                                    t('share.password', machine=machine.name),
                                    parent=self.root, detail=outcome.message):
                    self._start_share(machine, share, share.connect_handoff)
                self.redraw()
                return
            text = actions.share_error_text(machine, outcome.reason, outcome.message)
            if outcome.outcome == DENIED:
                dialogs.showinfo(t('share.denied_title'), text, parent=self.root)
            else:
                self.glitch.now(self.title, strong=True)
                dialogs.showerror(t('share.failed_title'),
                                  t('share.failed', machine=machine.name, message=text),
                                  parent=self.root)
            self.redraw()

        self.submit(('share', machine.name), job, finished)
        self.redraw()

    def stop_share(self, name: str, why: str = 'stopped'):
        share = self.shares.pop(name, None)
        if share is None:
            return
        self.submit(('stopshare', name), lambda: share.stop(why), lambda _v: None)
        self._status_idle()
        self.set_status(t('status.share_ended', machine=name.upper()))
        self.redraw()

    def _share_tick(self):
        """Every few seconds while a share is open: notice one that ended (the viewer was
        closed, the banner's Stop was pressed, the connection dropped) and keep the minutes
        on the card and in the machine's view current."""
        self._share_timer = None
        for name, share in list(self.shares.items()):
            if not share.alive():
                self.stop_share(name, 'ended')
        if self.shares:
            self.redraw()
            self._share_timer = self.root.after(4000, self._share_tick)

    def copy_report(self, machine: configmod.Machine):
        text = report.build(machine, self.results.get(machine.name),
                            self.down_since.get(machine.name))
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status(t('status.copied'))

    def start_tail(self, machine, scope, unit, on_line):
        """Follow a journal; lines cross to Tk's thread through after_idle-safe polling."""
        lines: "queue.Queue[str]" = queue.Queue()
        tail = self.transport.tail(machine, scope, unit, lines.put)

        def drain():
            if getattr(tail, 'stopped', False):
                return
            try:
                while True:
                    on_line(lines.get_nowait())
            except queue.Empty:
                pass
            except tk.TclError:
                return
            tail._drain = self.root.after(250, drain)

        original_stop = tail.stop

        def stop():
            tail.stopped = True
            if getattr(tail, '_drain', None):
                try:
                    self.root.after_cancel(tail._drain)
                except tk.TclError:
                    pass
            original_stop()

        tail.stop = stop
        drain()
        return tail

    # — visibility —
    def _unmapped(self, event):
        if event.widget is self.root and self.visible:
            self.visible = False
            if self._timer is not None:
                self.root.after_cancel(self._timer)
                self._timer = None
            if self.machine_view is not None and self.machine_view.logs:
                self.machine_view.logs.stop()
            log.info("hidden: refreshes paused")
            self._status_idle()

    def _mapped(self, event):
        if event.widget is self.root and not self.visible:
            self.visible = True
            self._status_idle()
            self._run_due()

    def run(self):
        self.root.mainloop()

    def close(self):
        for share in list(self.shares.values()):
            share.stop('closed')
        self.shares.clear()
        if self.machine_view is not None:
            self.machine_view.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass
