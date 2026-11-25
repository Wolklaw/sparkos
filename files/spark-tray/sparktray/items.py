"""The five tray items. Each one owns a backend (nm, bluez, power, printers, audio), says
whether it should be on the tray at all, and draws its popup and its right-click menu.

An item never touches the tray protocol itself: app.py gives each one a StatusNotifierItem and
calls icon(), tooltip(), menu() and activate() when the tray asks."""

from typing import Callable, Dict, List, Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk   # noqa: E402

from . import audio, core, printers
from .bluez import Bluetooth, PairingAgent, agent_names
from .dbusutil import BusError
from .nm import Network, SecretAgent
from .power import Power, battery_icon, format_time
from .sni import MenuEntry
from .text import t
from . import ui


class Context:
    """What the items share: the buses, the prompter, the config, and the app's callbacks."""

    def __init__(self, system_bus, prompter, config: Dict, changed: Callable[['TrayItem'], None],
                 disable: Callable[[str], None], quit_: Callable[[], None],
                 fake_dir: str = ''):
        self.system_bus, self.prompter, self.config = system_bus, prompter, config
        self.changed, self.disable, self.quit = changed, disable, quit_
        self.fake_dir = fake_dir
        self.items: Dict[str, 'TrayItem'] = {}


def open_settings(page: str, fallback: str = '') -> bool:
    if core.which('spark-settings'):
        return core.spawn(['spark-settings', '--page', page])
    if fallback and core.which(fallback):
        return core.spawn([fallback])
    return False


class TrayItem:
    name = ''
    title_key = ''
    category = 'Hardware'
    settings_key = ''
    settings_fallback = ''

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.popup: Optional[ui.Popup] = None
        self.started = False
        self.error = ''

    # — lifecycle —
    def start(self) -> bool:
        """Open the backend. False when this PC doesn't have what the item needs."""
        return False

    def stop(self) -> None:
        pass

    def recheck(self) -> None:
        """Called every few seconds: a service that wasn't there may be now."""
        if not self.started:
            self.started = self.start()

    def visible(self) -> bool:
        return self.started

    def changed(self) -> None:
        self.ctx.changed(self)

    # — what the tray shows —
    def title(self) -> str:
        return t(self.title_key).title()

    def icon(self) -> str:
        return 'dialog-question'

    def tooltip(self) -> str:
        return ''

    def specific_menu(self) -> List[MenuEntry]:
        return []

    def menu(self) -> List[MenuEntry]:
        entries = [MenuEntry(self.title(), lambda: self.toggle_popup(0, 0))]
        entries += self.specific_menu()
        if self.settings_key:
            entries.append(MenuEntry(t(self.settings_key), self.open_settings))
        entries += [MenuEntry(separator=True),
                    MenuEntry(t('common.hide_icon'), lambda: self.ctx.disable(self.name)),
                    MenuEntry(t('common.quit'), self.ctx.quit)]
        return entries

    def open_settings(self) -> None:
        page = self.name
        open_settings(page, self.settings_fallback)

    def activate(self, x: int, y: int) -> None:
        self.toggle_popup(x, y)

    def secondary(self) -> None:
        pass

    def scroll(self, delta: int, orientation: str) -> None:
        pass

    # — the popup —
    def toggle_popup(self, x: int, y: int) -> None:
        if self.popup is None:
            self.popup = ui.Popup(self.title(), self.ctx.config.get('popup_corner', 'bottom-right'))
        if self.popup.get_visible():
            self.popup.hide()
            return
        self.rebuild_popup()
        self.popup.open_at(x, y)
        self.opened()

    def opened(self) -> None:
        """The popup just opened: scan, poll faster, and so on."""

    def rebuild_popup(self) -> None:
        if self.popup is None:
            return
        ui.clear(self.popup.body)
        head = ui.hbox(8)
        head.pack_start(ui.label(self.title().upper(), 'title'), True, True, 0)
        head.pack_end(ui.button(t('common.close'), self.popup.hide), False, False, 0)
        self.popup.body.pack_start(head, False, False, 0)
        try:
            self.fill(self.popup.body)
        except Exception:                          # noqa: BLE001 - a bad row mustn't blank the app
            core.log.exception("could not draw the %s popup", self.name)
        self.popup.body.show_all()
        self.popup.resize(self.popup.get_default_size()[0], 1)

    def popup_open(self) -> bool:
        return bool(self.popup and self.popup.get_visible())

    def update(self) -> None:
        """Backend changed: redraw the popup if it is up."""
        if self.popup_open():
            self.rebuild_popup()

    def fill(self, body: Gtk.Box) -> None:
        pass

    def say_error(self, err: Optional[BusError]) -> None:
        if err:
            self.error = t('common.failed', reason=str(err))
            core.log.warning("%s: %s", self.name, err)
            if self.popup_open():
                ui.glitch(self.popup)
        else:
            self.error = ''
        self.update()

    def error_label(self, body: Gtk.Box) -> None:
        if self.error:
            body.pack_start(ui.label(self.error, 'bad', wrap=True), False, False, 0)


def _toggle_row(text: str, on: bool, callback: Callable[[bool], None]) -> Gtk.Box:
    row = ui.hbox(8)
    row.pack_start(ui.label(text), True, True, 0)
    row.pack_end(ui.switch(on, callback), False, False, 0)
    return row


# ─── Network ───────────────────────────────────────────────

class NetworkItem(TrayItem):
    name = 'network'
    title_key = 'net.title'
    category = 'Hardware'
    settings_key = 'net.settings'
    settings_fallback = 'nm-connection-editor'

    def start(self) -> bool:
        self.net = getattr(self, 'net', None) or Network(self.ctx.system_bus, self._backend_changed)
        if not self.net.start():
            return False
        self.agent = SecretAgent(self.ctx.system_bus, self.ctx.prompter, self._label)
        self.agent.start()
        return True

    def stop(self) -> None:
        if getattr(self, 'agent', None):
            self.agent.stop()
        if getattr(self, 'net', None):
            self.net.stop()
        self.started = False

    @staticmethod
    def _label(key: str) -> str:
        return t('net.secret') if key.startswith('wifi') or key == 'psk' else t('net.secret.other')

    def _backend_changed(self) -> None:
        self.changed()

    def state(self):
        return self.net.state()

    # airplane mode covers Bluetooth too, so the controller's other item is asked
    def airplane_on(self) -> bool:
        s = self.state()
        bt = self.ctx.items.get('bluetooth')
        bt_off = True
        if bt and bt.started:
            b = bt.bt.state()
            bt_off = not (b.available and b.powered)
        return s.wifi_present and not s.wifi_enabled and bt_off

    def set_airplane(self, on: bool) -> None:
        try:
            self.net.set_airplane(on)
        except BusError as exc:
            self.say_error(exc)
            return
        bt = self.ctx.items.get('bluetooth')
        if bt and bt.started:
            b = bt.bt.state()
            if b.available and b.adapter:
                try:
                    bt.bt.set_power(b.adapter, not on)
                except BusError as exc:
                    self.say_error(exc)

    def icon(self) -> str:
        try:
            s = self.state()
        except BusError:
            return 'network-error'
        if s.wifi_present and not s.wifi_enabled and not any(w.connected for w in s.wired):
            return 'network-wireless-disabled' if self.airplane_on() else 'network-offline'
        if any(w.connected for w in s.wired):
            return 'network-wired'
        if s.active_ssid:
            ap = next((a for a in s.aps if a.active), None)
            n = ap.strength if ap else 0
            return ('network-wireless-signal-excellent' if n >= 75 else
                    'network-wireless-signal-good' if n >= 50 else
                    'network-wireless-signal-ok' if n >= 25 else 'network-wireless-signal-weak')
        return 'network-wireless-offline' if s.wifi_present else 'network-offline'

    def tooltip(self) -> str:
        s = self.state()
        if self.airplane_on():
            return t('net.tip.airplane')
        for w in s.wired:
            if w.connected:
                return t('net.tip.wired', name=w.connection or w.interface)
        if s.active_ssid:
            ap = next((a for a in s.aps if a.active), None)
            return t('net.tip.wifi', ssid=s.active_ssid, signal=ap.strength if ap else 0)
        return t('net.tip.offline')

    def specific_menu(self) -> List[MenuEntry]:
        s = self.state()
        out = []
        if s.active_ssid and s.active_path:
            out.append(MenuEntry(t('net.menu.disconnect', ssid=s.active_ssid),
                                 lambda: self.net.disconnect(s.active_path, self.say_error)))
        if s.wifi_present:
            out.append(MenuEntry(t('net.wifi'), lambda: self.net.set_wifi(not s.wifi_enabled),
                                 checked=s.wifi_enabled))
        out.append(MenuEntry(t('net.airplane'), lambda: self.set_airplane(not self.airplane_on()),
                             checked=self.airplane_on()))
        return out

    def opened(self) -> None:
        s = self.state()
        if s.wifi_device and s.wifi_enabled:
            self.net.rescan(s.wifi_device)

    # — the popup —
    def fill(self, body: Gtk.Box) -> None:
        s = self.state()
        self.error_label(body)
        body.pack_start(_toggle_row(t('net.airplane'), self.airplane_on(), self.set_airplane),
                        False, False, 0)
        body.pack_start(ui.micro(t('net.wired')), False, False, 0)
        if not s.wired:
            body.pack_start(ui.label(t('net.none_wired'), 'muted'), False, False, 0)
        for w in s.wired:
            row = ui.row_box(w.connected)
            state = (t('net.wired.connected', name=f": {w.connection}" if w.connection else '')
                     if w.connected else t('net.wired.disconnected') if w.cable
                     else t('net.wired.unplugged'))
            row.pack_start(ui.label(w.interface), False, False, 0)
            row.pack_start(ui.label(state, 'muted' if not w.connected else 'ok'), True, True, 0)
            body.pack_start(row, False, False, 0)

        body.pack_start(ui.micro(t('net.wifi')), False, False, 0)
        if not s.wifi_present:
            body.pack_start(ui.label(t('net.no_wifi'), 'muted'), False, False, 0)
        else:
            body.pack_start(_toggle_row(t('net.wifi'), s.wifi_enabled, self.net.set_wifi),
                            False, False, 0)
            if not s.wifi_enabled:
                body.pack_start(ui.label(t('net.wifi_off'), 'muted'), False, False, 0)
            elif not s.aps:
                body.pack_start(ui.label(t('net.no_networks'), 'muted'), False, False, 0)
            for ap in s.aps[:12]:
                body.pack_start(self._ap_row(s, ap), False, False, 0)
            if s.wifi_enabled:
                body.pack_start(ui.button(t('net.rescan'),
                                          lambda: self.net.rescan(s.wifi_device)),
                                False, False, 0)

        if s.vpns:
            body.pack_start(ui.micro(t('net.vpn')), False, False, 0)
            for v in s.vpns:
                body.pack_start(_toggle_row(
                    v.name, v.active,
                    lambda on, v=v: self.net.set_vpn(v, on, self.say_error)), False, False, 0)

    def _ap_row(self, s, ap) -> Gtk.Box:
        row = ui.row_box(ap.active)
        row.pack_start(ui.label(ui.signal_bars(ap.strength), 'muted'), False, False, 0)
        row.pack_start(ui.label(ap.ssid), True, True, 0)
        tag = (t('net.connected') if ap.active else t('net.saved') if ap.known
               else t('net.enterprise').split('.')[0] if ap.enterprise
               else t('net.secured') if ap.secured else t('net.open'))
        row.pack_start(ui.label(tag, 'ok' if ap.active else 'muted'), False, False, 0)
        if ap.active:
            row.pack_end(ui.button(t('net.disconnect'),
                                   lambda: self.net.disconnect(s.active_path, self.say_error)),
                         False, False, 0)
        else:
            row.pack_end(ui.button(t('net.connect'), lambda: self.join(s, ap), 'primary'),
                         False, False, 0)
        return row

    def join(self, s, ap) -> None:
        if ap.enterprise and not ap.known:
            self.ctx.prompter.notify(t('net.enterprise'))
            return
        if ap.secured and not ap.known:
            self.ctx.prompter.ask_password(
                ap.ssid, lambda pw: pw and self.net.connect(ap, s.wifi_device, pw, self.say_error))
        else:
            self.net.connect(ap, s.wifi_device, None, self.say_error)


# ─── Bluetooth ─────────────────────────────────────────────

class BluetoothItem(TrayItem):
    name = 'bluetooth'
    title_key = 'bt.title'
    settings_key = 'bt.settings'
    settings_fallback = 'blueman-manager'

    def start(self) -> bool:
        self.bt = getattr(self, 'bt', None) or Bluetooth(self.ctx.system_bus, self.changed)
        if not self.bt.start() or not self.bt.state().available:
            self.bt.stop()
            return False
        self.agent = PairingAgent(self.ctx.system_bus, self.ctx.prompter,
                                  agent_names(self.bt.state), t)
        self.agent.start()
        return True

    def stop(self) -> None:
        if getattr(self, 'agent', None):
            self.agent.stop()
        if getattr(self, 'bt', None):
            self.bt.stop()
        self.started = False

    def visible(self) -> bool:
        return self.started and self.bt.state().available

    def icon(self) -> str:
        s = self.bt.state()
        if not s.powered:
            return 'bluetooth-disabled'
        return 'bluetooth-active' if s.connected else 'bluetooth'

    def tooltip(self) -> str:
        s = self.bt.state()
        if not s.powered:
            return t('bt.tip.off')
        if s.connected:
            return t('bt.tip.connected', names=', '.join(d.name for d in s.connected))
        return t('bt.tip.on')

    def specific_menu(self) -> List[MenuEntry]:
        s = self.bt.state()
        out = [MenuEntry(t('bt.power'), lambda: self.bt.set_power(s.adapter, not s.powered),
                         checked=s.powered)]
        for d in s.connected:
            out.append(MenuEntry(f"{t('bt.disconnect')} {d.name}",
                                 lambda d=d: self.bt.disconnect(d, self.say_error)))
        return out

    def opened(self) -> None:
        s = self.bt.state()
        if s.powered and not s.discovering:
            self.bt.scan(s.adapter, True, self.say_error)

    def fill(self, body: Gtk.Box) -> None:
        s = self.bt.state()
        self.error_label(body)
        body.pack_start(_toggle_row(t('bt.power'), s.powered,
                                    lambda on: self.bt.set_power(s.adapter, on)), False, False, 0)
        if not s.powered:
            body.pack_start(ui.label(t('bt.off'), 'muted'), False, False, 0)
            return
        scan = ui.hbox(8)
        scan.pack_start(ui.label(t('bt.scanning') if s.discovering else '', 'muted'), True, True, 0)
        scan.pack_end(ui.button(t('bt.stop_scan') if s.discovering else t('bt.scan'),
                                lambda: self.bt.scan(s.adapter, not s.discovering,
                                                     self.say_error)), False, False, 0)
        body.pack_start(scan, False, False, 0)
        if not s.devices:
            body.pack_start(ui.label(t('bt.no_devices'), 'muted', wrap=True), False, False, 0)
        for d in s.devices[:14]:
            body.pack_start(self._device_row(s, d), False, False, 0)

    def _device_row(self, s, d) -> Gtk.Box:
        row = ui.row_box(d.connected)
        row.pack_start(ui.label(d.name), True, True, 0)
        bits = [t('bt.connected') if d.connected else t('bt.paired') if d.paired else t('bt.new')]
        if d.battery is not None:
            bits.append(t('bt.battery', percent=d.battery))
        row.pack_start(ui.label(' · '.join(bits), 'ok' if d.connected else 'muted'),
                       False, False, 0)
        if d.connected:
            row.pack_end(ui.button(t('bt.disconnect'),
                                   lambda: self.bt.disconnect(d, self.say_error)), False, False, 0)
        elif d.paired:
            row.pack_end(ui.button(t('bt.forget'),
                                   lambda: self.bt.forget(s.adapter, d, self.say_error),
                                   'danger'), False, False, 0)
            row.pack_end(ui.button(t('bt.connect'), lambda: self.bt.connect(d, self.say_error),
                                   'primary'), False, False, 0)
        else:
            row.pack_end(ui.button(t('bt.pair'), lambda: self.bt.pair(d, self.say_error),
                                   'primary'), False, False, 0)
        return row


# ─── Power ─────────────────────────────────────────────────

class PowerItem(TrayItem):
    name = 'power'
    title_key = 'pw.title'
    settings_key = 'pw.settings'

    def start(self) -> bool:
        self.pw = getattr(self, 'pw', None) or Power(self.ctx.system_bus, self.changed)
        return self.pw.start()

    def stop(self) -> None:
        if getattr(self, 'pw', None):
            self.pw.stop()
        self.started = False

    def visible(self) -> bool:
        """A desktop has no battery, so no icon, unless the config asks for one."""
        return self.started and (self.pw.has_battery()
                                 or bool(self.ctx.config.get('power_show_without_battery')))

    def icon(self) -> str:
        if self.pw.has_battery():
            return battery_icon(self.pw.battery())
        return 'system-shutdown'

    def tooltip(self) -> str:
        if self.pw.has_battery():
            b = self.pw.battery()
            text = t('pw.tip', percent=round(b.percent))
            extra = format_time(b.seconds) if b.seconds else ''
            if extra and not b.full:
                text += ', ' + (t('pw.time_full', time=extra) if b.charging
                                else t('pw.time_left', time=extra))
            return text
        s = self.pw.state()
        return t('pw.tip.plain', profile=_profile_name(s.profile)) if s.profile else t('pw.title')

    def specific_menu(self) -> List[MenuEntry]:
        s = self.pw.state()
        out = []
        for p in s.profiles:
            out.append(MenuEntry(_profile_name(p), lambda p=p: self._set_profile(p),
                                 checked=p == s.profile))
        out.append(MenuEntry(separator=True))
        for action in ('sleep', 'restart', 'shutdown'):
            out.append(MenuEntry(t(f'pw.{action}'), lambda a=action: self.confirm(a),
                                 enabled=s.can.get(action, False)))
        return out

    def _set_profile(self, name: str) -> None:
        try:
            self.pw.set_profile(name)
        except BusError as exc:
            self.say_error(exc)

    def confirm(self, action: str) -> None:
        self.ctx.prompter.confirm(
            t(f'pw.{action}') + '\n' + t(f'pw.confirm.{action}'),
            lambda yes: yes and self.pw.act(action, self.say_error),
            danger=action != 'sleep', ok_label=t(f'pw.{action}'))

    def fill(self, body: Gtk.Box) -> None:
        s = self.pw.state()
        self.error_label(body)
        if self.pw.has_battery():
            b = s.battery
            body.pack_start(ui.micro(t('pw.battery')), False, False, 0)
            row = ui.row_box(b.charging)
            row.pack_start(ui.label(t('pw.percent', percent=round(b.percent)), 'title'),
                           False, False, 0)
            state = (t('pw.full') if b.full else t('pw.charging') if b.charging
                     else t('pw.empty') if b.percent <= 0 else t('pw.discharging'))
            row.pack_start(ui.label(state, 'ok' if b.charging or b.full else 'muted'), True, True, 0)
            if b.seconds and not b.full:
                row.pack_end(ui.label(t('pw.time_full' if b.charging else 'pw.time_left',
                                        time=format_time(b.seconds)), 'muted'), False, False, 0)
            body.pack_start(row, False, False, 0)
        body.pack_start(ui.micro(t('pw.profile')), False, False, 0)
        if not s.profiles:
            body.pack_start(ui.label(t('pw.no_profiles'), 'muted'), False, False, 0)
        else:
            row = ui.hbox(6)
            for p in s.profiles:
                b = ui.button(_profile_name(p), lambda p=p: self._set_profile(p),
                              'primary' if p == s.profile else '')
                row.pack_start(b, True, True, 0)
            body.pack_start(row, False, False, 0)
        row = ui.hbox(6)
        for action in ('sleep', 'restart', 'shutdown'):
            b = ui.button(t(f'pw.{action}'), lambda a=action: self.confirm(a),
                          'danger' if action == 'shutdown' else '')
            b.set_sensitive(bool(s.can.get(action)))
            row.pack_start(b, True, True, 0)
        body.pack_start(row, False, False, 0)


def _profile_name(profile: str) -> str:
    key = f'pw.profile.{profile}'
    text = t(key)
    return text if text != key else profile


# ─── Printers ──────────────────────────────────────────────

class PrintersItem(TrayItem):
    name = 'printers'
    title_key = 'pr.title'
    settings_key = 'pr.add'

    POLL = 10
    POLL_OPEN = 2

    def __init__(self, ctx: Context, runner: Callable = core.run):
        super().__init__(ctx)
        self.printing = printers.Printing(runner)
        self.last = printers.PrintState()
        self._timer = 0

    def start(self) -> bool:
        self.last = self.printing.state()
        if not self.last.available:
            return False
        self._schedule(self.POLL)
        return True

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self.started = False

    def _schedule(self, seconds: int) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(seconds, self._poll)

    def _poll(self) -> bool:
        new = self.printing.state()
        if new != self.last:
            self.last = new
            self.changed()
        self._schedule(self.POLL_OPEN if self.popup_open() else self.POLL)
        return False

    def refresh_now(self) -> None:
        self.last = self.printing.state()
        self.changed()

    def visible(self) -> bool:
        return self.started and self.last.available and bool(self.last.printers)

    def state(self):
        return self.last

    def icon(self) -> str:
        return 'printer-printing' if any(p.state == 'printing' for p in self.last.printers) \
            else 'printer'

    def tooltip(self) -> str:
        n = len(self.last.jobs)
        return t('pr.tip.jobs', n=n) if n else t('pr.tip.idle')

    def open_settings(self) -> None:
        cmd = printers.add_printer_command()
        if cmd:
            core.spawn(cmd)
        else:
            self.ctx.prompter.notify(t('pr.no_add'))

    def opened(self) -> None:
        self._schedule(self.POLL_OPEN)

    def cancel(self, job_id: str) -> None:
        if not self.printing.cancel(job_id):
            self.say_error(BusError(f"cancel {job_id} failed"))
        self.refresh_now()

    def pause(self, name: str, paused: bool) -> None:
        if not self.printing.set_paused(name, paused):
            self.say_error(BusError(f"{name} could not be changed"))
        self.refresh_now()

    def fill(self, body: Gtk.Box) -> None:
        s = self.last
        self.error_label(body)
        if not s.printers:
            body.pack_start(ui.label(t('pr.none'), 'muted'), False, False, 0)
        for p in s.printers:
            row = ui.row_box(p.state == 'printing')
            row.pack_start(ui.label(p.name + (f"  [{t('pr.default')}]" if p.default else '')),
                           True, True, 0)
            row.pack_start(ui.label(t(f'pr.state.{p.state}'),
                                    'ok' if p.state == 'printing' else 'muted'), False, False, 0)
            paused = p.state == 'stopped'
            row.pack_end(ui.button(t('pr.resume') if paused else t('pr.pause'),
                                   lambda p=p, paused=paused: self.pause(p.name, not paused)),
                         False, False, 0)
            body.pack_start(row, False, False, 0)
        body.pack_start(ui.micro(t('pr.jobs')), False, False, 0)
        if not s.jobs:
            body.pack_start(ui.label(t('pr.no_jobs'), 'muted'), False, False, 0)
        for j in s.jobs[:10]:
            row = ui.row_box()
            row.pack_start(ui.label(j.id), True, True, 0)
            row.pack_start(ui.label(j.user, 'muted'), False, False, 0)
            row.pack_end(ui.button(t('pr.cancel'), lambda j=j: self.cancel(j.id), 'danger'),
                         False, False, 0)
            body.pack_start(row, False, False, 0)
        body.pack_start(ui.button(t('pr.add'), self.open_settings), False, False, 0)


# ─── Volume ────────────────────────────────────────────────

class VolumeItem(TrayItem):
    name = 'volume'
    title_key = 'vol.title'
    category = 'Hardware'

    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.vol = audio.Volume(self.changed, ctx.fake_dir)
        self._scale: Optional[Gtk.Scale] = None
        self._setting = False

    def start(self) -> bool:
        return self.vol.start()

    def stop(self) -> None:
        self.vol.stop()
        self.started = False

    def visible(self) -> bool:
        return self.started and self.vol.output() is not None

    def icon(self) -> str:
        return audio.icon_for(self.vol.level(), self.vol.muted())

    def tooltip(self) -> str:
        n = self.vol.output()
        if not n:
            return t('vol.no_output')
        name = n.title or n.name
        if self.vol.muted():
            return t('vol.tip.muted', name=name)
        return t('vol.tip', name=name, percent=round((self.vol.level() or 0) * 100))

    def specific_menu(self) -> List[MenuEntry]:
        return [MenuEntry(t('vol.menu.mute'), self.vol.toggle_mute, checked=self.vol.muted()),
                MenuEntry(t('vol.menu.mixer'), self.open_mixer)]

    def open_mixer(self) -> None:
        if not core.spawn(['spark-audio']):
            open_settings('sound')

    def open_settings(self) -> None:
        self.open_mixer()

    def secondary(self) -> None:
        self.vol.toggle_mute()

    def scroll(self, delta: int, orientation: str) -> None:
        if orientation.lower().startswith('h') or not delta:
            return
        self.vol.nudge(1 if delta > 0 else -1)

    def update(self) -> None:
        """Move the slider in place: rebuilding it would drop a drag in progress."""
        if not self.popup_open():
            return
        if self._scale is not None and self.vol.level() is not None:
            self._setting = True
            self._scale.set_value(round((self.vol.level() or 0) * 100))
            self._setting = False
            self._mute_switch.set_active(self.vol.muted())
        else:
            self.rebuild_popup()

    def fill(self, body: Gtk.Box) -> None:
        n = self.vol.output()
        self._scale = None
        if not n:
            body.pack_start(ui.label(t('vol.no_output'), 'muted'), False, False, 0)
            return
        body.pack_start(ui.micro(t('vol.output')), False, False, 0)
        names = self.vol.outputs()
        for node in names:
            row = ui.row_box(node.id == n.id)
            row.pack_start(ui.label(node.title or node.name), True, True, 0)
            if node.id != n.id:
                row.pack_end(ui.button(t('vol.use'),
                                       lambda node=node: self.vol.set_default(node)),
                             False, False, 0)
            body.pack_start(row, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_value(round((self.vol.level() or 0) * 100))
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.connect('value-changed', self._scale_moved)
        self._scale = scale
        body.pack_start(scale, False, False, 0)
        self._mute_row = _toggle_row(t('vol.mute'), self.vol.muted(),
                                     lambda on: on != self.vol.muted() and self.vol.toggle_mute())
        self._mute_switch = self._mute_row.get_children()[-1]
        self._mute_switch.set_active(self.vol.muted())
        body.pack_start(self._mute_row, False, False, 0)
        body.pack_start(ui.button(t('vol.open_mixer'), self.open_mixer), False, False, 0)

    def _scale_moved(self, scale: Gtk.Scale) -> None:
        if not self._setting:
            self.vol.set_level(scale.get_value() / 100.0)


ALL_ITEMS = (NetworkItem, BluetoothItem, PowerItem, PrintersItem, VolumeItem)
