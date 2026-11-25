"""The window: the list of machines on the left, one machine's details on the right, a page for
making a new machine, and a page that says what to do when libvirt can't be reached.

libvirt calls run on a worker thread (work()) so the window never freezes; their results come
back to the main thread through GLib.idle_add."""

import os
import re
import threading
from typing import Callable, Dict, List, Optional

import gi

from . import GTK_VERSION, core, isoinfo, usbdev, xmlgen
from .lang import local_units
from .text import t

gi.require_version('Gtk', GTK_VERSION)
from gi.repository import GLib, Gtk  # noqa: E402

from . import style  # noqa: E402

GIB = 1024 ** 3
NAME_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')


def size_text(count: int) -> str:
    if count >= GIB:
        return local_units(f"{count / GIB:.1f} GB")
    return local_units(f"{count / 1048576:.0f} MB")


def mem_text(mb: int) -> str:
    return local_units(f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB")


def micro(text: str) -> Gtk.Label:
    return style.label(text, 'micro')


def button(text: str, handler: Callable, *classes: str, tip: str = '') -> Gtk.Button:
    widget = Gtk.Button(label=text)
    for name in classes:
        widget.get_style_context().add_class(name)
    if tip:
        widget.set_tooltip_text(tip)
    widget.connect('clicked', lambda *_: handler())
    return widget


def spin(low: int, high: int, value: int, step: int = 1) -> Gtk.SpinButton:
    widget = Gtk.SpinButton.new_with_range(low, high, step)
    widget.set_value(value)
    widget.set_numeric(True)
    return widget


def iso_dialog(parent: Gtk.Window) -> Optional[str]:
    dialog = Gtk.FileChooserNative.new(t('iso.filter'), parent, Gtk.FileChooserAction.OPEN, None, None)
    flt = Gtk.FileFilter()
    flt.set_name(t('iso.filter'))
    flt.add_pattern('*.iso')
    flt.add_pattern('*.ISO')
    dialog.add_filter(flt)
    path = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
    dialog.destroy()
    return path


class BoxesWindow(Gtk.ApplicationWindow):

    def __init__(self, app, manager: core.Manager, glitch: style.Glitch,
                 open_console: Callable[[str], None], iso_picker=iso_dialog):
        super().__init__(application=app, title=t('app.title'))
        self.manager = manager
        self.glitch = glitch
        self.open_console = open_console
        self.pick_iso = iso_picker
        self.vms: List[core.VmInfo] = []
        self.selected = ''
        self.loaded = ''                    # the machine the detail widgets were filled for
        self.rows: Dict[str, Gtk.ListBoxRow] = {}
        self.usb_devices: List[usbdev.UsbDevice] = []
        self.new_iso = ''
        self.refreshing = False
        self.dead = False
        self.set_default_size(1100, 700)
        self.get_style_context().add_class(style.NAME)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        body = Gtk.Box()
        root.pack_start(body, True, True, 0)
        body.pack_start(self._build_side(), False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.add_named(self._build_empty(), 'empty')
        self.stack.add_named(self._build_unavailable(), 'unavailable')
        self.stack.add_named(self._build_detail(), 'detail')
        self.stack.add_named(self._build_new(), 'new')
        body.pack_start(self.stack, True, True, 0)
        footer = Gtk.Box()
        footer.get_style_context().add_class('footer')
        self.status = style.label('', 'status', wrap=True)
        self.status.set_margin_start(12)
        self.status.set_margin_end(12)
        self.status.set_margin_top(6)
        self.status.set_margin_bottom(6)
        footer.pack_start(self.status, True, True, 0)
        self.progress = Gtk.ProgressBar()
        self.progress.set_no_show_all(True)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_size_request(160, -1)
        self.progress.set_margin_end(12)
        footer.pack_end(self.progress, False, False, 0)
        root.pack_start(footer, False, False, 0)

        self.connect('destroy', self._on_destroy)
        self.connect('key-press-event', self._on_key)
        self.show_all()
        self.progress.hide()
        self.stack.set_visible_child_name('empty')
        self.connect_manager()
        self.dirty = False
        self.ticks = 0
        GLib.timeout_add(500, self._tick)

    # --- building the pieces ---

    def _build_side(self) -> Gtk.Widget:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        side.get_style_context().add_class('side')
        side.set_size_request(280, -1)
        for edge in ('top', 'start', 'end', 'bottom'):
            getattr(side, f'set_margin_{edge}')(12)
        head = Gtk.Box(spacing=8)
        self.title = style.label(t('list.title'), 'heading')
        head.pack_start(self.title, True, True, 0)
        self.new_button = button(t('list.new'), self.show_new, 'primary', tip=t('list.new_tip'))
        head.pack_end(self.new_button, False, False, 0)
        side.pack_start(head, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.ListBox()
        self.list.get_style_context().add_class('rows')
        self.list.connect('row-selected', self._on_row_selected)
        scroller.add(self.list)
        side.pack_start(scroller, True, True, 0)
        return side

    def _centered(self, *widgets: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        for widget in widgets:
            box.pack_start(widget, False, False, 0)
        return box

    def _build_empty(self) -> Gtk.Widget:
        self.empty_label = style.label(t('list.empty'), 'body', xalign=0.5, wrap=True)
        return self._centered(self.empty_label)

    def _build_unavailable(self) -> Gtk.Widget:
        self.un_title = style.label('', 'big', xalign=0.5, wrap=True)
        self.un_body = style.label('', 'body', xalign=0.5, wrap=True)
        self.un_retry = button(t('un.retry'), self.connect_manager, 'primary')
        self.un_retry.set_halign(Gtk.Align.CENTER)
        return self._centered(self.un_title, self.un_body, self.un_retry)

    def _build_detail(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for edge in ('top', 'start', 'end', 'bottom'):
            getattr(page, f'set_margin_{edge}')(16)
        top = Gtk.Box(spacing=12)
        self.d_name = style.label('', 'big')
        self.d_state = style.label('', 'state')
        self.d_type = style.label('', 'meta')
        top.pack_start(self.d_name, False, False, 0)
        top.pack_start(self.d_state, False, False, 0)
        top.pack_start(self.d_type, False, False, 0)
        page.pack_start(top, False, False, 0)

        actions = Gtk.Box(spacing=6)
        self.b_start = button(t('act.start'), self.act_start, 'primary', tip=t('act.start_tip'))
        self.b_open = button(t('act.open'), self.act_open)
        self.b_pause = button(t('act.pause'), self.act_pause)
        self.b_shutdown = button(t('act.shutdown'), self.act_shutdown, tip=t('act.shutdown_tip'))
        self.b_force = button(t('act.force'), self.act_force, 'danger', tip=t('act.force_tip'))
        self.b_delete = button(t('act.delete'), self.act_delete, 'danger', tip=t('act.delete_tip'))
        for widget in (self.b_start, self.b_open, self.b_pause, self.b_shutdown, self.b_force):
            actions.pack_start(widget, False, False, 0)
        actions.pack_end(self.b_delete, False, False, 0)
        page.pack_start(actions, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.append_page(self._build_overview(), style.label(t('tab.overview')))
        self.notebook.append_page(self._build_settings(), style.label(t('tab.settings')))
        self.notebook.append_page(self._build_snapshots(), style.label(t('tab.snapshots')))
        self.notebook.append_page(self._build_usb(), style.label(t('tab.usb')))
        self.notebook.connect('switch-page', self._on_tab)
        page.pack_start(self.notebook, True, True, 0)
        return page

    def _tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for edge in ('top', 'start', 'end', 'bottom'):
            getattr(box, f'set_margin_{edge}')(12)
        return box

    def _build_overview(self) -> Gtk.Widget:
        box = self._tab()
        grid = Gtk.Grid(column_spacing=24, row_spacing=10)
        self.ov: Dict[str, Gtk.Label] = {}
        for i, key in enumerate(('type', 'cpu', 'mem', 'disk', 'drivers', 'usb')):
            grid.attach(micro(t(f'ov.{key}')), 0, i, 1, 1)
            value = style.label('', 'title', wrap=True)
            self.ov[key] = value
            grid.attach(value, 1, i, 1, 1)
        box.pack_start(grid, False, False, 0)
        return box

    def _build_settings(self) -> Gtk.Widget:
        box = self._tab()
        self.s_note = style.label(t('set.off_only'), 'status', wrap=True)
        box.pack_start(self.s_note, False, False, 0)
        grid = Gtk.Grid(column_spacing=16, row_spacing=10)
        self.s_cpus = spin(1, 64, 2)
        self.s_mem = spin(xmlgen.MIN_MEMORY_MB, 1048576, 4096, 256)
        self.s_boot_disk = Gtk.RadioButton.new_with_label(None, t('set.boot_disk'))
        self.s_boot_cd = Gtk.RadioButton.new_with_label_from_widget(self.s_boot_disk, t('set.boot_cd'))
        self.s_net = Gtk.Switch()
        self.s_net.set_halign(Gtk.Align.START)
        boot = Gtk.Box(spacing=12)
        boot.pack_start(self.s_boot_disk, False, False, 0)
        boot.pack_start(self.s_boot_cd, False, False, 0)
        for i, (name, widget) in enumerate(((t('set.cpus'), self.s_cpus), (t('set.mem'), self.s_mem),
                                            (t('set.boot'), boot), (t('set.net'), self.s_net))):
            grid.attach(micro(name), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        self.s_apply = button(t('set.apply'), self.act_apply, 'primary')
        grid.attach(self.s_apply, 1, 4, 1, 1)
        box.pack_start(grid, False, False, 0)

        disc = Gtk.Box(spacing=8)
        disc.pack_start(micro(t('set.disc')), False, False, 0)
        self.s_disc = style.label('', 'status')
        disc.pack_start(self.s_disc, False, False, 0)
        self.s_disc_pick = button(t('set.disc_pick'), self.act_pick_disc)
        self.s_disc_eject = button(t('set.disc_eject'), self.act_eject_disc)
        disc.pack_end(self.s_disc_eject, False, False, 0)
        disc.pack_end(self.s_disc_pick, False, False, 0)
        box.pack_start(disc, False, False, 0)

        extra = Gtk.Box(spacing=8)
        extra.pack_start(micro(t('set.add_gb')), False, False, 0)
        self.s_add_gb = spin(1, 4096, 20)
        extra.pack_start(self.s_add_gb, False, False, 0)
        self.s_add = button(t('set.add_disk'), self.act_add_disk)
        extra.pack_start(self.s_add, False, False, 0)
        box.pack_start(extra, False, False, 0)

        drivers = Gtk.Box(spacing=8)
        drivers.pack_start(micro(t('set.drivers')), False, False, 0)
        self.s_drivers = button(t('set.drivers_get'), self.act_drivers, tip=t('set.drivers_tip'))
        drivers.pack_start(self.s_drivers, False, False, 0)
        box.pack_start(drivers, False, False, 0)
        return box

    def _build_snapshots(self) -> Gtk.Widget:
        box = self._tab()
        row = Gtk.Box(spacing=8)
        row.pack_start(micro(t('snap.label')), False, False, 0)
        self.n_label = Gtk.Entry()
        self.n_label.set_text(t('snap.default'))
        row.pack_start(self.n_label, True, True, 0)
        self.n_take = button(t('snap.take'), self.act_snapshot, 'primary')
        row.pack_start(self.n_take, False, False, 0)
        box.pack_start(row, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        self.n_list = Gtk.ListBox()
        self.n_list.get_style_context().add_class('rows')
        self.n_list.connect('row-selected', lambda *_: self._update_snap_buttons())
        scroller.add(self.n_list)
        box.pack_start(scroller, True, True, 0)
        actions = Gtk.Box(spacing=8)
        self.n_revert = button(t('snap.revert'), self.act_revert)
        self.n_forget = button(t('snap.delete'), self.act_forget, 'danger')
        actions.pack_start(self.n_revert, False, False, 0)
        actions.pack_start(self.n_forget, False, False, 0)
        box.pack_start(actions, False, False, 0)
        box.pack_start(style.label(t('snap.note'), 'meta', wrap=True), False, False, 0)
        return box

    def _build_usb(self) -> Gtk.Widget:
        box = self._tab()
        head = Gtk.Box(spacing=8)
        head.pack_start(style.label(t('usb.title'), 'heading'), True, True, 0)
        head.pack_end(button(t('usb.refresh'), self.refresh_usb), False, False, 0)
        box.pack_start(head, False, False, 0)
        self.u_note = style.label(t('usb.start_first'), 'status', wrap=True)
        box.pack_start(self.u_note, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        self.u_list = Gtk.ListBox()
        self.u_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.u_list.get_style_context().add_class('rows')
        scroller.add(self.u_list)
        box.pack_start(scroller, True, True, 0)
        return box

    def _build_new(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_halign(Gtk.Align.CENTER)
        page.set_valign(Gtk.Align.CENTER)
        page.set_size_request(520, -1)
        page.pack_start(style.label(t('new.title'), 'heading'), False, False, 0)
        grid = Gtk.Grid(column_spacing=16, row_spacing=10)
        self.f_name = Gtk.Entry()
        self.f_name.set_hexpand(True)
        self.f_name.connect('changed', lambda *_: self._new_check())
        self.f_iso = style.label(t('new.iso_none'), 'status')
        iso = Gtk.Box(spacing=8)
        iso.pack_start(self.f_iso, True, True, 0)
        self.f_iso_pick = button(t('new.iso_pick'), self.act_new_pick_iso)
        iso.pack_end(self.f_iso_pick, False, False, 0)
        presets = Gtk.Box(spacing=6)
        self.f_presets: Dict[str, Gtk.ToggleButton] = {}
        for key in xmlgen.PRESETS:
            toggle = Gtk.ToggleButton(label=t(f'preset.{key}'))
            toggle.get_style_context().add_class('choice')
            toggle.connect('toggled', self._on_preset, key)
            self.f_presets[key] = toggle
            presets.pack_start(toggle, False, False, 0)
        threads, host_mb = self._host()
        self.f_cpus = spin(1, max(threads, 1), xmlgen.default_cpus(threads))
        self.f_mem = spin(xmlgen.MIN_MEMORY_MB, max(host_mb, xmlgen.MIN_MEMORY_MB), 4096, 256)
        self.f_disk = spin(8, 4096, 40)
        rows = ((t('new.name'), self.f_name), (t('new.iso'), iso), (t('new.preset'), presets),
                (t('new.cpus'), self.f_cpus), (t('new.mem'), self.f_mem), (t('new.disk'), self.f_disk))
        for i, (name, widget) in enumerate(rows):
            grid.attach(micro(name), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        page.pack_start(grid, False, False, 0)
        self.f_note = style.label('', 'status', wrap=True)
        page.pack_start(self.f_note, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.f_create = button(t('new.create'), self.act_create, 'primary')
        self.f_cancel = button(t('new.cancel'), self.hide_new)
        actions.pack_end(self.f_create, False, False, 0)
        actions.pack_end(self.f_cancel, False, False, 0)
        page.pack_start(actions, False, False, 0)
        self.f_presets['win11'].set_active(True)
        return page

    # --- plumbing ---

    def _host(self):
        try:
            return self.manager.host()
        except Exception:
            return 8, 16384

    def say(self, text: str, tone: str = '') -> None:
        self.status.set_text(text)
        ctx = self.status.get_style_context()
        for name in ('ok', 'warn'):
            ctx.remove_class(name)
        if tone:
            ctx.add_class(tone)
            if tone == 'warn':
                self.glitch.now(self.status, self.stack)

    def work(self, call: Callable, done: Optional[Callable] = None, busy: str = '') -> None:
        """Run call() off the main thread; then done(result) here, or the error on the status."""
        if busy:
            self.say(busy)

        def run():
            try:
                result, error = call(), None
            except Exception as exc:        # BoxesError, or a libvirt surprise: both are shown
                result, error = None, exc
            GLib.idle_add(finish, result, error)

        def finish(result, error):
            if self.dead:
                return False
            if error is not None:
                core.log.warning("%s", error)
                self.say(str(error), 'warn')
                self._new_check()
            elif done:
                done(result)
            self.refresh()
            return False

        threading.Thread(target=run, daemon=True).start()

    def progress_to(self, done_bytes: int, total: int) -> None:
        def update():
            if total:
                self.progress.show()
                self.progress.set_fraction(min(1.0, done_bytes / total))
            return False
        GLib.idle_add(update)

    def progress_off(self) -> None:
        self.progress.hide()

    # --- connecting and refreshing ---

    def connect_manager(self) -> None:
        def attempt():
            self.manager.connect()
            self.manager.watch(self._on_event)
            return self.manager.list_vms()

        def run():
            try:
                result, error = attempt(), None
            except core.Unavailable as exc:
                result, error = None, exc
            except Exception as exc:
                result, error = None, core.Unavailable('off', str(exc))
            GLib.idle_add(finished, result, error)

        def finished(result, error):
            if self.dead:
                return False
            if error is not None:
                self.show_unavailable(error)
            else:
                self.say('')
                self.apply_list(result)
            return False

        threading.Thread(target=run, daemon=True).start()

    def _on_event(self, *_args) -> None:
        # libvirt calls this from its own thread; only leave a note, the main thread acts on it
        self.dirty = True

    def show_unavailable(self, error: core.Unavailable) -> None:
        self.un_title.set_text(t(f'un.{error.kind}'))
        self.un_body.set_text(t(f'un.{error.kind}_body'))
        self.new_button.set_sensitive(False)
        self.stack.set_visible_child_name('unavailable')
        self.glitch.now(self.un_title)
        core.log.warning("libvirt unavailable (%s): %s", error.kind, error.detail)

    def _tick(self) -> bool:
        if self.dead:
            return False
        self.ticks += 1
        if self.manager.conn is not None and (self.dirty or self.ticks % 10 == 0):
            self.dirty = False
            self.refresh()
        return True

    def refresh(self) -> bool:
        if self.dead or self.refreshing or self.manager.conn is None:
            return False
        self.refreshing = True

        def run():
            try:
                result = self.manager.list_vms()
            except Exception as exc:
                core.log.warning("refresh: %s", exc)
                result = None
            GLib.idle_add(finished, result)

        def finished(result):
            self.refreshing = False
            if result is not None and not self.dead:
                self.apply_list(result)
            return False

        threading.Thread(target=run, daemon=True).start()
        return False

    def apply_list(self, vms: List[core.VmInfo]) -> None:
        self.new_button.set_sensitive(True)
        self.vms = vms
        names = [v.name for v in vms]
        if list(self.rows) != names:
            for child in self.list.get_children():
                self.list.remove(child)
            self.rows = {}
            for vm in vms:
                row = Gtk.ListBoxRow()
                row.vm_name = vm.name
                row.add(self._row_box(vm))
                self.list.add(row)
                self.rows[vm.name] = row
            self.list.show_all()
        for vm in vms:
            self._update_row(self.rows[vm.name], vm)
        on_new = self.stack.get_visible_child_name() == 'new'
        if self.selected not in names:
            self.selected = names[0] if names else ''
        if self.selected and self.selected in self.rows:
            if self.list.get_selected_row() is not self.rows[self.selected]:
                self.list.select_row(self.rows[self.selected])
        if not on_new:
            if self.selected:
                self.show_vm(self.current())
            else:
                self.stack.set_visible_child_name('empty')

    def _row_box(self, vm: core.VmInfo) -> Gtk.Widget:
        box = Gtk.Box(spacing=10)
        for edge in ('top', 'bottom'):
            getattr(box, f'set_margin_{edge}')(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        glyph = style.label(vm.name[:2].upper(), 'glyph', xalign=0.5)
        box.pack_start(glyph, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        row_name = style.label(vm.name, 'title')
        row_name.set_ellipsize(3)
        row_spec = style.label('', 'meta')
        text.pack_start(row_name, False, False, 0)
        text.pack_start(row_spec, False, False, 0)
        box.pack_start(text, True, True, 0)
        state = style.label('', 'state')
        box.pack_end(state, False, False, 0)
        box.spec, box.state = row_spec, state
        return box

    def _update_row(self, row: Gtk.ListBoxRow, vm: core.VmInfo) -> None:
        box = row.get_child()
        box.spec.set_text(t('row.spec', cpus=vm.cpus, mem=mem_text(vm.memory_mb)))
        box.state.set_text(t(f'state.{vm.state}'))
        ctx = box.state.get_style_context()
        for name in ('running', 'paused'):
            ctx.remove_class(name)
        if vm.state in ('running', 'paused'):
            ctx.add_class(vm.state)

    def current(self) -> Optional[core.VmInfo]:
        return next((v for v in self.vms if v.name == self.selected), None)

    def _on_row_selected(self, _list, row) -> None:
        if row is None or row.vm_name == self.selected and self.loaded == self.selected:
            return
        self.selected = row.vm_name
        self.loaded = ''
        if self.stack.get_visible_child_name() != 'new':
            self.show_vm(self.current())
            self.glitch.now(self.d_name)

    # --- the details ---

    def show_vm(self, vm: Optional[core.VmInfo]) -> None:
        if vm is None:
            return
        self.stack.set_visible_child_name('detail')
        self.d_name.set_text(vm.name)
        self.d_state.set_text(t(f'state.{vm.state}'))
        ctx = self.d_state.get_style_context()
        for name in ('running', 'paused'):
            ctx.remove_class(name)
        if vm.state in ('running', 'paused'):
            ctx.add_class(vm.state)
        self.d_type.set_text(t(f'preset.{vm.preset}') if vm.preset in xmlgen.PRESETS else vm.preset)
        off = vm.state == 'off'
        on = vm.state in ('running', 'paused')
        self.b_start.set_sensitive(off)
        self.b_open.set_sensitive(on)
        self.b_pause.set_label(t('act.resume') if vm.state == 'paused' else t('act.pause'))
        self.b_pause.set_sensitive(on)
        self.b_shutdown.set_sensitive(vm.state == 'running')
        self.b_force.set_sensitive(on)
        self.b_delete.set_sensitive(vm.state != 'other')

        self.ov['type'].set_text(self.d_type.get_text())
        self.ov['cpu'].set_text(str(vm.cpus))
        self.ov['mem'].set_text(mem_text(vm.memory_mb))
        self.ov['disk'].set_text(t('ov.disk_value', used=size_text(vm.disk_used),
                                   total=size_text(vm.disk_bytes)))
        self.ov['drivers'].set_text(t('ov.drivers_yes') if vm.drivers else t('ov.drivers_no'))
        self.ov['usb'].set_text(', '.join(vm.usb) or t('ov.none'))

        for widget in (self.s_cpus, self.s_mem, self.s_boot_disk, self.s_boot_cd, self.s_net,
                       self.s_apply, self.s_add, self.s_add_gb, self.s_disc_pick,
                       self.s_disc_eject):
            widget.set_sensitive(off)
        self.s_note.set_visible(not off)
        self.s_drivers.set_sensitive(off and vm.preset in xmlgen.WINDOWS)
        self.n_take.set_sensitive(True)
        self.u_note.set_visible(not on)
        if self.loaded != vm.name:
            self.loaded = vm.name
            self.s_cpus.set_value(vm.cpus)
            self.s_mem.set_value(vm.memory_mb)
            self.load_settings(vm.name)
            self.refresh_snapshots()
            self.refresh_usb()
        else:
            self._mark_usb(vm)

    def load_settings(self, name: str) -> None:
        def read():
            return (self.manager.boot_first(name), self.manager.network_on(name),
                    self.manager.cdrom(name))

        def show(result):
            if self.selected != name:
                return
            boot, net, disc = result
            (self.s_boot_cd if boot == 'cdrom' else self.s_boot_disk).set_active(True)
            self.s_net.set_active(net)
            self.s_disc.set_text(os.path.basename(disc) if disc else t('set.disc_none'))
        self._quiet(read, show)

    def _quiet(self, call: Callable, done: Callable) -> None:
        """Like work(), but a failure is only logged: it's a read for the screen, not an action."""
        def run():
            try:
                result = call()
            except Exception as exc:
                core.log.warning("%s", exc)
                return
            GLib.idle_add(lambda: (None if self.dead else done(result)) or False)
        threading.Thread(target=run, daemon=True).start()

    # --- actions ---

    def act_start(self):
        self.work(lambda: self.manager.start(self.selected))

    def act_open(self):
        if self.selected:
            self.open_console(self.selected)

    def act_pause(self):
        vm = self.current()
        if vm:
            call = self.manager.resume if vm.state == 'paused' else self.manager.pause
            self.work(lambda: call(vm.name))

    def act_shutdown(self):
        self.work(lambda: self.manager.shutdown(self.selected))

    def act_force(self):
        self.work(lambda: self.manager.force_off(self.selected))

    def act_delete(self):
        name = self.selected
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                   text=t('del.title', name=name), secondary_text=t('del.body'))
        dialog.get_style_context().add_class(style.NAME)
        check = Gtk.CheckButton(label=t('del.disks'))
        dialog.get_message_area().pack_start(check, False, False, 0)
        check.show()
        dialog.add_button(t('del.no'), Gtk.ResponseType.CANCEL)
        dialog.add_button(t('del.yes'), Gtk.ResponseType.OK)
        answer, disks = dialog.run(), check.get_active()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self.loaded = ''
            self.work(lambda: self.manager.delete_vm(name, disks),
                      lambda _r: self.say(t('del.done', name=name), 'ok'))

    def act_apply(self):
        name = self.selected
        cpus, mem = self.s_cpus.get_value_as_int(), self.s_mem.get_value_as_int()
        first = 'cdrom' if self.s_boot_cd.get_active() else 'disk'
        net = self.s_net.get_active()

        def apply():
            self.manager.set_cpus(name, cpus)
            self.manager.set_memory(name, mem)
            self.manager.set_boot_first(name, first)
            if self.manager.network_on(name) != net:
                self.manager.set_network(name, net)
        self.work(apply, lambda _r: self.say(t('set.applied'), 'ok'))

    def act_pick_disc(self):
        path = self.pick_iso(self)
        if not path:
            return
        name = self.selected

        def attach():
            self.manager.set_cdrom(name, self.manager.import_iso(path, self.progress_to))
        self.work(attach, lambda _r: (self.progress_off(), self.load_settings(name)),
                  busy=t('new.working'))

    def act_eject_disc(self):
        name = self.selected
        self.work(lambda: self.manager.set_cdrom(name, None), lambda _r: self.load_settings(name))

    def act_add_disk(self):
        name, gb = self.selected, self.s_add_gb.get_value_as_int()
        self.work(lambda: self.manager.add_disk(name, gb),
                  lambda path: self.say(t('set.disk_added', path=path), 'ok'))

    def act_drivers(self):
        name = self.selected

        def fetch():
            path, digest, pinned = core.download_virtio_win(self.manager, self.progress_to)
            self.manager.attach_virtio_win(name, path)
            return digest, pinned

        def done(result):
            self.progress_off()
            digest, pinned = result
            self.say(t('set.drivers_done') if pinned else t('set.drivers_unpinned', sha=digest), 'ok')
            self.load_settings(name)
        self.work(fetch, done, busy=t('set.drivers_busy'))
        self.s_drivers.set_sensitive(False)

    # snapshots

    def refresh_snapshots(self) -> None:
        name = self.selected

        def show(snaps):
            if self.selected != name:
                return
            for child in self.n_list.get_children():
                self.n_list.remove(child)
            if not snaps:
                row = Gtk.ListBoxRow()
                row.set_selectable(False)
                row.add(style.label(t('snap.empty'), 'status'))
                self.n_list.add(row)
            for snap in snaps:
                row = Gtk.ListBoxRow()
                row.snap_name = snap.name
                box = Gtk.Box(spacing=10)
                box.set_margin_top(6)
                box.set_margin_bottom(6)
                box.set_margin_start(8)
                box.pack_start(style.label(snap.name, 'title'), True, True, 0)
                box.pack_end(style.label(t('snap.running') if snap.running else t('snap.disk'),
                                         'meta'), False, False, 8)
                row.add(box)
                self.n_list.add(row)
            self.n_list.show_all()
            self._update_snap_buttons()
        self._quiet(lambda: self.manager.snapshots(name), show)

    def _update_snap_buttons(self) -> None:
        picked = getattr(self.n_list.get_selected_row(), 'snap_name', None)
        self.n_revert.set_sensitive(bool(picked))
        self.n_forget.set_sensitive(bool(picked))

    def act_snapshot(self):
        name, label = self.selected, self.n_label.get_text()
        self.work(lambda: self.manager.take_snapshot(name, label),
                  lambda snap: (self.say(t('snap.taken', name=snap), 'ok'), self.refresh_snapshots()))

    def act_revert(self):
        name = self.selected
        snap = getattr(self.n_list.get_selected_row(), 'snap_name', None)
        if snap:
            self.work(lambda: self.manager.revert_snapshot(name, snap),
                      lambda _r: self.say(t('snap.reverted', name=snap), 'ok'))

    def act_forget(self):
        name = self.selected
        snap = getattr(self.n_list.get_selected_row(), 'snap_name', None)
        if snap:
            self.work(lambda: self.manager.delete_snapshot(name, snap),
                      lambda _r: (self.say(t('snap.forgot', name=snap), 'ok'),
                                  self.refresh_snapshots()))

    # usb

    def refresh_usb(self) -> None:
        self._quiet(self.manager.usb_list, self._show_usb)

    def _show_usb(self, devices: List[usbdev.UsbDevice]) -> None:
        self.usb_devices = devices
        for child in self.u_list.get_children():
            self.u_list.remove(child)
        if not devices:
            row = Gtk.ListBoxRow()
            row.add(style.label(t('usb.none'), 'status'))
            self.u_list.add(row)
        for device in devices:
            row = Gtk.ListBoxRow()
            row.usb = device
            box = Gtk.Box(spacing=10)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(8)
            box.set_margin_end(8)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.pack_start(style.label(device.name or device.ident, 'title'), False, False, 0)
            why = {'system': t('usb.system'), 'd': t('usb.d'), 'mounted': t('usb.mounted')}
            text.pack_start(style.label(why.get(device.refused, device.ident), 'meta'),
                            False, False, 0)
            box.pack_start(text, True, True, 0)
            give = button(t('usb.give'), lambda d=device: self.act_usb_give(d), 'primary')
            back = button(t('usb.back'), lambda d=device: self.act_usb_back(d))
            row.give, row.back = give, back
            box.pack_end(back, False, False, 0)
            box.pack_end(give, False, False, 0)
            row.add(box)
            self.u_list.add(row)
        self.u_list.show_all()
        self._mark_usb(self.current())

    def _mark_usb(self, vm: Optional[core.VmInfo]) -> None:
        running = vm is not None and vm.state in ('running', 'paused')
        given = set(vm.usb) if vm else set()
        for row in self.u_list.get_children():
            device = getattr(row, 'usb', None)
            if device is None:
                continue
            held = device.ident in given
            row.give.set_sensitive(running and device.allowed and not held)
            row.back.set_sensitive(running and held)

    def act_usb_give(self, device: usbdev.UsbDevice):
        name = self.selected
        self.work(lambda: self.manager.usb_give(name, device),
                  lambda _r: self.say(t('usb.gave', name=device.name), 'ok'))

    def act_usb_back(self, device: usbdev.UsbDevice):
        name = self.selected
        self.work(lambda: self.manager.usb_take_back(name, device),
                  lambda _r: self.say(t('usb.took', name=device.name), 'ok'))

    def _on_tab(self, _book, _page, number) -> None:
        self.glitch.now(self.notebook)
        if number == 3:
            self.refresh_usb()

    # --- new machine ---

    def show_new(self) -> None:
        self.f_name.set_text('')
        self.new_iso = ''
        self.f_iso.set_text(t('new.iso_none'))
        self.f_presets['win11'].set_active(True)
        self._on_preset(self.f_presets['win11'], 'win11')
        self.list.unselect_all()
        self.stack.set_visible_child_name('new')
        self.f_name.grab_focus()
        self._new_check()
        if not os.path.exists('/dev/kvm'):
            self.f_note.set_text(t('new.no_kvm'))

    def hide_new(self) -> None:
        self.loaded = ''
        if self.selected and self.selected in self.rows:
            self.list.select_row(self.rows[self.selected])
            self.show_vm(self.current())
        else:
            self.stack.set_visible_child_name('empty')

    def _on_preset(self, toggle, key: str) -> None:
        if not toggle.get_active():
            if not any(w.get_active() for w in self.f_presets.values()):
                toggle.set_active(True)
            return
        for other, widget in self.f_presets.items():
            if other != key and widget.get_active():
                widget.set_active(False)
        _threads, host_mb = self._host()
        self.f_mem.set_value(xmlgen.default_memory_mb(key, host_mb))
        self.f_disk.set_value(xmlgen.default_disk_gb(key))
        self.f_note.set_text(t('new.win11_note') if key == 'win11' else '')

    def selected_preset(self) -> str:
        return next((k for k, w in self.f_presets.items() if w.get_active()), 'linux')

    def act_new_pick_iso(self):
        path = self.pick_iso(self)
        if path:
            self.set_new_iso(path)

    def set_new_iso(self, path: str) -> None:
        self.new_iso = path
        self.f_iso.set_text(os.path.basename(path))
        guess = isoinfo.guess_preset(isoinfo.volume_label(path), path)
        self.f_presets[guess].set_active(True)
        self._on_preset(self.f_presets[guess], guess)
        self.f_note.set_text(t('new.guess', preset=t(f'preset.{guess}')))
        if not self.f_name.get_text():
            self.f_name.set_text(re.sub(r'[^A-Za-z0-9_-]+', '-', t(f'preset.{guess}')).strip('-'))

    def _new_check(self) -> Optional[str]:
        name = self.f_name.get_text().strip()
        problem = None
        if not name:
            problem = t('new.name_empty')
        elif not NAME_OK.match(name):
            problem = t('new.name_bad')
        elif any(v.name == name for v in self.vms):
            problem = t('new.name_taken', name=name)
        self.f_create.set_sensitive(problem is None)
        return problem

    def act_create(self):
        problem = self._new_check()
        if problem:
            self.say(problem, 'warn')
            return
        spec = xmlgen.VmSpec(name=self.f_name.get_text().strip(), preset=self.selected_preset(),
                             cpus=self.f_cpus.get_value_as_int(),
                             memory_mb=self.f_mem.get_value_as_int(), iso_path=self.new_iso,
                             kvm=os.path.exists('/dev/kvm'))
        disk = self.f_disk.get_value_as_int()
        self.f_create.set_sensitive(False)

        def made(info):
            self.progress_off()
            self.selected = info.name
            self.loaded = ''
            self.say(t('new.made', name=info.name), 'ok')
            self.stack.set_visible_child_name('detail')
        self.work(lambda: self.manager.create_vm(spec, disk, self.progress_to), made,
                  busy=t('new.working'))

    # --- keys and closing ---

    def _on_key(self, _widget, event) -> bool:
        from gi.repository import Gdk
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval == Gdk.KEY_n and self.new_button.get_sensitive():
            self.show_new()
            return True
        if event.keyval == Gdk.KEY_Escape and self.stack.get_visible_child_name() == 'new':
            self.hide_new()
            return True
        return False

    def _on_destroy(self, *_args) -> None:
        self.dead = True
        try:
            self.manager.close()
        except Exception:
            pass
