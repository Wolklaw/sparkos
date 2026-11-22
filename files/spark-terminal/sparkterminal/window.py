"""A Spark Terminal window: the tab strip, the panes split inside each tab, the search bar,
the menus, and asking before something running gets closed."""

from typing import Callable, List, Optional

from gi.repository import Gdk, Gio, GLib, Gtk

from . import APP_NAME, core
from .core import log
from .pane import Pane, open_uri, search_regex
from .style import Glitch
from .text import t


class Tab(Gtk.Box):
    """One tab: a Pane, or Gtk.Paned splits with Panes at their ends."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.active: Optional[Pane] = None
        self.label: Optional[Gtk.Label] = None
        self.header: Optional[Gtk.Box] = None

    def panes(self) -> List[Pane]:
        found: List[Pane] = []

        def walk(widget):
            if isinstance(widget, Pane):
                found.append(widget)
            elif isinstance(widget, Gtk.Paned):
                for child in (widget.get_start_child(), widget.get_end_child()):
                    if child is not None:
                        walk(child)
        child = self.get_first_child()
        if child is not None:
            walk(child)
        return found


def _swap(parent: Gtk.Widget, old: Gtk.Widget, new: Gtk.Widget) -> None:
    """Put new where old is in parent (a Tab or a Gtk.Paned); old ends up with no parent."""
    if isinstance(parent, Gtk.Paned):
        if parent.get_start_child() is old:
            parent.set_start_child(new)
        else:
            parent.set_end_child(new)
    else:
        parent.remove(old)
        parent.append(new)


class Window(Gtk.ApplicationWindow):

    def __init__(self, app, title: Optional[str] = None):
        super().__init__(application=app)
        self.app = app
        self.fixed_title = title
        self.glitch = Glitch(app.settings['glitch'])
        self.pending_link = None
        self.closing = False
        self.add_css_class('spark-terminal')
        self.set_title(title or APP_NAME)
        self.set_icon_name(app.get_application_id())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)

        nb = self.notebook = Gtk.Notebook()
        nb.add_css_class('tabs')
        nb.set_scrollable(True)
        nb.set_show_border(False)
        nb.set_vexpand(True)
        nb.connect('switch-page', self._on_switch_page)
        nb.connect('page-removed', self._on_page_removed)
        nb.connect('page-reordered', lambda *_: self._update_titles())

        actions = Gtk.Box(spacing=2)
        actions.add_css_class('tab-actions')
        actions.set_margin_end(4)
        new_tab = self._button('+', t('tip.new_tab'), 'win.new-tab')
        menu = Gtk.MenuButton(tooltip_text=t('tip.menu'))
        menu.set_child(Gtk.Label(label='≡'))
        menu.add_css_class('spark')
        menu.set_menu_model(self._main_menu())
        menu.set_valign(Gtk.Align.CENTER)
        actions.append(new_tab)
        actions.append(menu)
        nb.set_action_widget(actions, Gtk.PackType.END)
        box.append(nb)

        box.append(self._build_findbar())
        self._add_actions()
        self.connect('close-request', self._on_close_request)
        GLib.timeout_add(450, self._first_glitch)

    # ─── building ───────────────────────────────────────────

    @staticmethod
    def _button(label: str, tip: str, action: Optional[str] = None,
                on_click: Optional[Callable] = None) -> Gtk.Button:
        button = Gtk.Button(label=label, tooltip_text=tip)
        button.add_css_class('spark')
        button.set_valign(Gtk.Align.CENTER)
        button.set_focus_on_click(False)
        if action:
            button.set_action_name(action)
        if on_click:
            button.connect('clicked', lambda _b: on_click())
        return button

    def _main_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        first = Gio.Menu()
        first.append(t('menu.new_tab'), 'win.new-tab')
        first.append(t('menu.new_window'), 'win.new-window')
        menu.append_section(None, first)
        split = Gio.Menu()
        split.append(t('menu.split_right'), 'win.split-right')
        split.append(t('menu.split_down'), 'win.split-down')
        split.append(t('menu.close_pane'), 'win.close-pane')
        menu.append_section(None, split)
        view = Gio.Menu()
        view.append(t('menu.find'), 'win.find')
        view.append(t('menu.zoom_in'), 'win.zoom-in')
        view.append(t('menu.zoom_out'), 'win.zoom-out')
        view.append(t('menu.zoom_reset'), 'win.zoom-reset')
        view.append(t('menu.reset'), 'win.reset')
        menu.append_section(None, view)
        last = Gio.Menu()
        last.append(t('menu.settings'), 'win.settings')
        last.append(t('menu.keys'), 'win.keys')
        menu.append_section(None, last)
        return menu

    def _build_findbar(self) -> Gtk.Box:
        bar = self.findbar = Gtk.Box(spacing=6, visible=False)
        bar.add_css_class('findbar')
        entry = self.find_entry = Gtk.Entry(placeholder_text=t('find.placeholder'), hexpand=True)
        entry.connect('changed', lambda _e: self.find(backwards=True, restart=True))
        entry.connect('activate', lambda _e: self.find(backwards=True))
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)    # before the entry's Enter
        keys.connect('key-pressed', self._on_find_key)
        entry.add_controller(keys)
        self.find_case = Gtk.ToggleButton(label=t('find.case'))
        self.find_regex = Gtk.ToggleButton(label=t('find.regex'))
        for toggle in (self.find_case, self.find_regex):
            toggle.add_css_class('spark')
            toggle.set_focus_on_click(False)
            toggle.connect('toggled', lambda _b: self.find(backwards=True, restart=True))
        self.find_status = Gtk.Label(xalign=1)
        self.find_status.add_css_class('find-status')
        bar.append(entry)
        bar.append(self.find_status)
        bar.append(self.find_case)
        bar.append(self.find_regex)
        bar.append(self._button('↑', t('find.prev'), on_click=lambda: self.find(backwards=True)))
        bar.append(self._button('↓', t('find.next'), on_click=lambda: self.find(backwards=False)))
        bar.append(self._button('×', 'Esc', on_click=self.hide_find))
        return bar

    def _add_actions(self) -> None:
        simple = {
            'new-tab': lambda: self.new_tab(),
            'new-window': lambda: self.app.new_window(cwd=self.current_cwd()),
            'split-right': lambda: self.split(Gtk.Orientation.HORIZONTAL),
            'split-down': lambda: self.split(Gtk.Orientation.VERTICAL),
            'close-pane': lambda: self.close_pane(self.active_pane()),
            'close-tab': lambda: self.close_tab(self.current_tab()),
            'copy': self.copy,
            'paste': lambda: self._with_pane(lambda p: p.terminal.paste_clipboard()),
            'select-all': lambda: self._with_pane(lambda p: p.terminal.select_all()),
            'find': self.show_find,
            'zoom-in': lambda: self._with_pane(lambda p: p.zoom(1)),
            'zoom-out': lambda: self._with_pane(lambda p: p.zoom(-1)),
            'zoom-reset': lambda: self._with_pane(lambda p: p.zoom(0)),
            'reset': lambda: self._with_pane(lambda p: p.terminal.reset(True, True)),
            'settings': lambda: self.app.show_settings(self),
            'keys': self.show_keys,
            'next-tab': lambda: self._step_tab(1),
            'prev-tab': lambda: self._step_tab(-1),
            'focus-left': lambda: self.focus_direction(-1, 0),
            'focus-right': lambda: self.focus_direction(1, 0),
            'focus-up': lambda: self.focus_direction(0, -1),
            'focus-down': lambda: self.focus_direction(0, 1),
            'open-link': lambda: self.pending_link and open_uri(self.pending_link['target'], self),
            'copy-link': self._copy_link,
            'open-folder': self._open_link_folder,
        }
        for name, func in simple.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _a, _p, f=func: f())
            self.add_action(action)
        goto = Gio.SimpleAction.new('goto-tab', GLib.VariantType.new('i'))
        goto.connect('activate', lambda _a, p: self.goto_tab(p.get_int32()))
        self.add_action(goto)

    # ─── tabs ───────────────────────────────────────────────

    def new_tab(self, argv: Optional[List[str]] = None, cwd: Optional[str] = None,
                hold: bool = False) -> Pane:
        settings = self.app.settings
        if cwd is None:
            cwd = self.current_cwd() or core.start_folder(None, settings)
        tab = Tab()
        pane = self._new_pane()
        tab.append(pane)
        tab.active = pane

        header = Gtk.Box()
        label = Gtk.Label(label=t('tab.shell'), max_width_chars=24, width_chars=8)
        label.set_ellipsize(3)                               # Pango.EllipsizeMode.END
        label.add_css_class('tab-title')
        close = self._button('×', t('tip.close_tab'), on_click=lambda: self.close_tab(tab))
        close.add_css_class('tab-close')
        header.append(label)
        header.append(close)
        middle = Gtk.GestureClick(button=2)
        middle.connect('pressed', lambda *_: self.close_tab(tab))
        header.add_controller(middle)
        tab.label, tab.header = label, header

        index = self.notebook.append_page(tab, header)
        self.notebook.set_tab_reorderable(tab, True)
        self.notebook.set_current_page(index)
        command = bool(argv)
        pane.spawn(argv or core.shell_argv(settings), cwd, hold=hold, command=command)
        pane.terminal.grab_focus()
        if self.notebook.get_n_pages() > 1:
            self.glitch.now(label)
        return pane

    def tabs(self) -> List[Tab]:
        return [self.notebook.get_nth_page(i) for i in range(self.notebook.get_n_pages())]

    def current_tab(self) -> Optional[Tab]:
        page = self.notebook.get_current_page()
        return self.notebook.get_nth_page(page) if page >= 0 else None

    def active_pane(self) -> Optional[Pane]:
        tab = self.current_tab()
        if tab is None:
            return None
        if tab.active is None or tab.active.get_parent() is None:
            panes = tab.panes()
            tab.active = panes[0] if panes else None
        return tab.active

    def current_cwd(self) -> Optional[str]:
        pane = self.active_pane()
        return pane.cwd() if pane else None

    def goto_tab(self, number: int) -> None:
        if 1 <= number <= self.notebook.get_n_pages():
            self.notebook.set_current_page(number - 1)

    def _step_tab(self, step: int) -> None:
        n = self.notebook.get_n_pages()
        if n:
            self.notebook.set_current_page((self.notebook.get_current_page() + step) % n)

    def _on_switch_page(self, _nb, tab, _index) -> None:
        GLib.idle_add(self._focus_active)

    def _focus_active(self) -> bool:
        pane = self.active_pane()
        if pane is not None:
            pane.terminal.grab_focus()
        self._update_titles()
        return False

    def _on_page_removed(self, nb, _child, _index) -> None:
        if nb.get_n_pages() == 0 and not self.closing:
            self.closing = True
            self.destroy()

    # ─── panes ──────────────────────────────────────────────

    def _new_pane(self) -> Pane:
        return Pane(self.app.settings, {
            'exit': self._on_pane_exit, 'title': lambda p: self._update_titles(),
            'focus': self._on_pane_focus, 'bell': self._on_bell, 'context': self._show_context,
        })

    def _with_pane(self, func) -> None:
        pane = self.active_pane()
        if pane is not None:
            func(pane)

    def tab_of(self, pane: Pane) -> Optional[Tab]:
        widget = pane.get_parent()
        while widget is not None and not isinstance(widget, Tab):
            widget = widget.get_parent()
        return widget

    def split(self, orientation: Gtk.Orientation) -> Optional[Pane]:
        old = self.active_pane()
        tab = self.current_tab()
        if old is None or tab is None:
            return None
        cwd = old.cwd() or core.start_folder(None, self.app.settings)
        size = old.get_width() if orientation == Gtk.Orientation.HORIZONTAL else old.get_height()
        paned = Gtk.Paned(orientation=orientation, hexpand=True, vexpand=True)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        _swap(old.get_parent(), old, paned)
        new = self._new_pane()
        paned.set_start_child(old)
        paned.set_end_child(new)
        if size > 0:
            paned.set_position(size // 2)
        tab.active = new
        new.spawn(core.shell_argv(self.app.settings), cwd)
        self._mark_splits(tab)
        new.terminal.grab_focus()
        return new

    def _mark_splits(self, tab: Tab) -> None:
        panes = tab.panes()
        for pane in panes:
            (pane.add_css_class if len(panes) > 1 else pane.remove_css_class)('split')
            (pane.add_css_class if pane is tab.active else pane.remove_css_class)('focused')

    def _on_pane_focus(self, pane: Pane) -> None:
        tab = self.tab_of(pane)
        if tab is not None:
            tab.active = pane
            self._mark_splits(tab)
            self._update_titles()

    def focus_direction(self, dx: int, dy: int) -> None:
        tab, current = self.current_tab(), self.active_pane()
        if tab is None or current is None:
            return

        def centre(pane):
            ok, rect = pane.compute_bounds(tab)
            if not ok:
                return None
            return (rect.get_x() + rect.get_width() / 2, rect.get_y() + rect.get_height() / 2)
        here = centre(current)
        if here is None:
            return
        best, best_score = None, None
        for pane in tab.panes():
            if pane is current:
                continue
            there = centre(pane)
            if there is None:
                continue
            ax, ay = there[0] - here[0], there[1] - here[1]
            along = ax * dx + ay * dy
            if along <= 1:
                continue
            score = along + 2 * abs(ax * dy + ay * dx)        # prefer panes straight ahead
            if best_score is None or score < best_score:
                best, best_score = pane, score
        if best is not None:
            best.terminal.grab_focus()

    def close_pane(self, pane: Optional[Pane], confirm: bool = True) -> None:
        if pane is None:
            return
        what = pane.running()
        if confirm and what and self.app.settings['confirm_close']:
            self._ask(t('ask.close_pane', what=what), lambda: self._remove_pane(pane))
        else:
            self._remove_pane(pane)

    def close_tab(self, tab: Optional[Tab], confirm: bool = True) -> None:
        if tab is None:
            return
        running = [n for n in (p.running() for p in tab.panes()) if n]
        if confirm and running and self.app.settings['confirm_close']:
            self._ask(t('ask.close_one', what=', '.join(running)), lambda: self._remove_tab(tab))
        else:
            self._remove_tab(tab)

    def _remove_tab(self, tab: Tab) -> None:
        for pane in tab.panes():
            pane.stop()
        index = self.notebook.page_num(tab)
        if index >= 0:
            self.notebook.remove_page(index)

    def _remove_pane(self, pane: Pane) -> None:
        tab = self.tab_of(pane)
        pane.stop()
        if tab is None:
            return
        parent = pane.get_parent()
        if isinstance(parent, Gtk.Paned):
            sibling = parent.get_end_child() if parent.get_start_child() is pane \
                else parent.get_start_child()
            parent.set_start_child(None)
            parent.set_end_child(None)
            _swap(parent.get_parent(), parent, sibling)
            remaining = tab.panes()
            tab.active = remaining[0] if remaining else None
            # the pane closest to where the closed one was: the first one in the sibling
            first = sibling if isinstance(sibling, Pane) else None
            if first is None:
                inner = [p for p in remaining if p.is_ancestor(sibling)]
                first = inner[0] if inner else tab.active
            tab.active = first
            self._mark_splits(tab)
            if first is not None:
                first.terminal.grab_focus()
            self._update_titles()
        else:
            self._remove_tab(tab)

    def _on_pane_exit(self, pane: Pane) -> None:
        if pane.hold:
            tab = self.tab_of(pane)
            if tab is not None and tab.label is not None:
                tab.label.add_css_class('exited')
                self.glitch.now(tab.label)
            self._update_titles()
            return
        GLib.idle_add(lambda: self._remove_pane(pane) and False)

    def _on_bell(self, pane: Pane) -> None:
        if self.app.settings['bell'] != 'visual':
            return
        tab = self.tab_of(pane)
        pane.add_css_class('bell')
        GLib.timeout_add(220, lambda: pane.remove_css_class('bell') and False)
        if tab is not None:
            self.glitch.now(tab.label)

    # ─── titles ─────────────────────────────────────────────

    def _update_titles(self) -> None:
        for tab in self.tabs():
            pane = tab.active if tab.active is not None else (tab.panes() or [None])[0]
            if pane is None or tab.label is None:
                continue
            title = pane.title or t('tab.shell')
            count = len(tab.panes())
            tab.label.set_label(f"{title} +{count - 1}" if count > 1 else title)
            tab.header.set_tooltip_text(pane.title or None)
        if not self.fixed_title:
            pane = self.active_pane()
            title = pane.title if pane and pane.title else ''
            self.set_title(f"{title} — {APP_NAME}" if title else APP_NAME)

    def _first_glitch(self) -> bool:
        tab = self.current_tab()
        if tab is not None:
            self.glitch.now(tab.label)
        return False

    # ─── copy, links, context menu ──────────────────────────

    def copy(self) -> None:
        pane = self.active_pane()
        if pane is not None and pane.terminal.get_has_selection():
            from gi.repository import Vte
            pane.terminal.copy_clipboard_format(Vte.Format.TEXT)

    def _copy_link(self) -> None:
        if self.pending_link:
            text = self.pending_link.get('path') or self.pending_link['target']
            self.get_clipboard().set(text)

    def _open_link_folder(self) -> None:
        link = self.pending_link
        if link and link.get('path'):
            import os
            folder = link['path'] if os.path.isdir(link['path']) else os.path.dirname(link['path'])
            open_uri(Gio.File.new_for_path(folder).get_uri(), self)

    def _show_context(self, pane: Pane, x: float, y: float, link) -> None:
        self.pending_link = link
        menu = Gio.Menu()
        if link:
            section = Gio.Menu()
            section.append(t('menu.open_link'), 'win.open-link')
            section.append(t('menu.copy_link'), 'win.copy-link')
            if link.get('path'):
                section.append(t('menu.open_folder'), 'win.open-folder')
            menu.append_section(None, section)
        edit = Gio.Menu()
        if pane.terminal.get_has_selection():
            edit.append(t('menu.copy'), 'win.copy')
        edit.append(t('menu.paste'), 'win.paste')
        edit.append(t('menu.select_all'), 'win.select-all')
        menu.append_section(None, edit)
        tabs = Gio.Menu()
        tabs.append(t('menu.split_right'), 'win.split-right')
        tabs.append(t('menu.split_down'), 'win.split-down')
        tabs.append(t('menu.new_tab'), 'win.new-tab')
        tabs.append(t('menu.close_pane'), 'win.close-pane')
        menu.append_section(None, tabs)
        more = Gio.Menu()
        more.append(t('menu.find'), 'win.find')
        more.append(t('menu.settings'), 'win.settings')
        menu.append_section(None, more)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(pane.terminal)
        popover.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.set_halign(Gtk.Align.START)
        popover.connect('closed', lambda p: GLib.idle_add(lambda: p.unparent() and False))
        popover.popup()

    # ─── search ─────────────────────────────────────────────

    def show_find(self) -> None:
        self.findbar.set_visible(True)
        pane = self.active_pane()
        if pane is not None and pane.terminal.get_has_selection():
            from gi.repository import Vte
            selected = pane.terminal.get_text_selected(Vte.Format.TEXT) or ''
            if selected and '\n' not in selected:
                self.find_entry.set_text(selected)
        self.find_entry.grab_focus()
        self.find_entry.select_region(0, -1)

    def hide_find(self) -> None:
        self.findbar.set_visible(False)
        for tab in self.tabs():
            for pane in tab.panes():
                pane.terminal.search_set_regex(None, 0)
        self._with_pane(lambda p: p.terminal.grab_focus())

    def _on_find_key(self, _ctl, keyval, _code, state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.hide_find()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.SHIFT_MASK:
            self.find(backwards=False)
            return True
        return False

    def find(self, backwards: bool, restart: bool = False) -> bool:
        pane = self.active_pane()
        text = self.find_entry.get_text()
        self.find_status.set_label('')
        self.find_status.remove_css_class('error')
        self.find_entry.remove_css_class('error')
        if pane is None:
            return False
        term = pane.terminal
        if not text:
            term.search_set_regex(None, 0)
            term.unselect_all()
            return False
        try:
            regex = search_regex(text, self.find_regex.get_active(), self.find_case.get_active())
        except GLib.Error:
            self._find_problem(t('find.bad_regex'))
            return False
        if restart or term.search_get_regex() is None:
            term.unselect_all()
        term.search_set_regex(regex, 0)
        term.search_set_wrap_around(True)
        found = term.search_find_previous() if backwards else term.search_find_next()
        if not found:
            self._find_problem(t('find.none'))
        return bool(found)

    def _find_problem(self, message: str) -> None:
        self.find_status.set_label(message)
        self.find_status.add_css_class('error')
        self.find_entry.add_css_class('error')
        self.glitch.now(self.find_entry)

    # ─── closing and asking ─────────────────────────────────

    def _ask(self, detail: str, on_yes: Callable) -> None:
        dialog = Gtk.AlertDialog(message=t('ask.close_title'), detail=detail, modal=True)
        dialog.set_buttons([t('button.cancel'), t('button.close')])
        dialog.set_cancel_button(0)
        dialog.set_default_button(1)

        def done(dlg, result):
            try:
                choice = dlg.choose_finish(result)
            except GLib.Error:
                return
            if choice == 1:
                on_yes()
        dialog.choose(self, None, done)

    def running(self) -> List[str]:
        return [n for tab in self.tabs() for n in (p.running() for p in tab.panes()) if n]

    def _on_close_request(self, _win) -> bool:
        if self.closing:
            return False
        running = self.running()
        if running and self.app.settings['confirm_close']:
            what = ', '.join(sorted(set(running)))
            self._ask(t('ask.close_window', n=len(running), what=what), self.force_close)
            return True
        self.force_close()
        return True

    def force_close(self) -> None:
        self.closing = True
        for tab in self.tabs():
            for pane in tab.panes():
                pane.stop()
        log.info("window closed")
        self.destroy()

    # ─── settings and help ──────────────────────────────────

    def apply_settings(self, settings) -> None:
        self.glitch.enabled = settings['glitch']
        for tab in self.tabs():
            for pane in tab.panes():
                pane.apply_settings(settings)

    def show_keys(self) -> None:
        dialog = Gtk.Window(title=t('keys.title'), transient_for=self, modal=True)
        dialog.add_css_class('spark-terminal-dialog')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(18)
        heading = Gtk.Label(label=t('keys.title').upper(), xalign=0)
        heading.add_css_class('heading')
        box.append(heading)
        grid = Gtk.Grid(column_spacing=18, row_spacing=4)
        for row, line in enumerate(t('keys.list').splitlines()):
            keys, what = line.split('\t')
            k = Gtk.Label(label=keys, xalign=0)
            k.add_css_class('keys')
            grid.attach(k, 0, row, 1, 1)
            grid.attach(Gtk.Label(label=what, xalign=0), 1, row, 1, 1)
        box.append(grid)
        done = self._button(t('button.done'), '', on_click=dialog.close)
        done.add_css_class('primary')
        done.set_halign(Gtk.Align.END)
        box.append(done)
        dialog.set_child(box)
        dialog.present()
        self.glitch.now(heading)
