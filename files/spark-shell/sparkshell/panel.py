"""The panel: one per monitor. Launcher button, task list (pinned apps + open windows), the
notification bell, the tray (on the first panel only: there is one tray) and the clock."""

import time

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk  # noqa: E402

from . import apps, clockbridge, connectstatus, dnd, layer  # noqa: E402
from .ordering import merge_order  # noqa: E402
from .strings import tr  # noqa: E402
from .windows import match_app  # noqa: E402

PANEL_HEIGHT = 40


def _popover(parent, child):
    pop = Gtk.Popover()
    pop.add_css_class('spark-pop')
    pop.set_parent(parent)
    pop.set_has_arrow(False)
    pop.set_child(child)
    pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
    return pop


def _item(label, callback, pop=None, danger=False):
    button = Gtk.Button()
    button.add_css_class('spark-item')
    text = Gtk.Label(label=label, xalign=0)
    text.add_css_class('spark-text')
    button.set_child(text)

    def clicked(*_):
        if pop is not None:
            pop.popdown()
        callback()
    button.connect('clicked', clicked)
    return button


class ClockButton(Gtk.Button):
    """Time and date; click for a calendar, the next alarm and a way into Spark Clock."""

    def __init__(self):
        super().__init__()
        self.add_css_class('spark-flat')
        self.label = Gtk.Label()
        self.label.add_css_class('spark-clock')
        self.set_child(self.label)
        self.connect('clicked', self._open)
        self._timer = 0
        self._tick()
        self.connect('unrealize', self._stop)

    def _stop(self, *_):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self):
        """Update the label, then wake again just after the next minute starts."""
        now = time.time()
        local = time.localtime(now)
        text = time.strftime('%H:%M', local)
        if self.label.get_text() != text:
            self.label.set_text(text)
            self.set_tooltip_text(time.strftime('%A %d %B %Y', local))
        wait = int((60 - now % 60) * 1000) + 50
        self._timer = GLib.timeout_add(wait, self._tick)
        return False

    def _open(self, *_):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        calendar = Gtk.Calendar()
        box.append(calendar)
        alarm = clockbridge.next_alarm()
        line = Gtk.Label(xalign=0)
        line.add_css_class('spark-dim')
        if alarm:
            when = time.strftime('%a %H:%M', time.localtime(alarm[0]))
            line.set_text(tr('next_alarm') % ('%s %s' % (when, alarm[1])).strip())
        else:
            line.set_text(tr('no_alarm'))
        box.append(line)
        pop = _popover(self, box)
        command = clockbridge.clock_command()
        if command:
            box.append(_item(tr('open_clock'), lambda: apps.run(command), pop))
        pop.popup()


class TaskList(Gtk.Box):
    """Pinned apps first, then other open windows, one button per app."""

    def __init__(self, shell, monitor_name, home=False):
        super().__init__(spacing=2)
        self.shell = shell
        self.monitor_name = monitor_name
        self.home = home      # also shows windows whose screen is unknown
        self._shown = None
        self._dragging = False
        self._late = False        # the list changed during a drag: redraw when it ends
        dnd.attach_target(self, 'task', lambda name, after: self._drop(name, None, after),
                          mark=False)
        self.refresh()

    def _mine(self, w):
        """Windows live on the taskbar of the screen they are on, like Windows does."""
        out = w.get('output') or ''
        if out == self.monitor_name:
            return True
        if not self.home:
            return False
        return out not in {p.connector for p in self.shell.panels}

    def groups(self):
        """[(AppInfo or None, key, [windows])] in display order."""
        windows = [w for w in self.shell.tracker.windows if self._mine(w)]
        used = set()
        rows = []
        for desktop_id in self.shell.config['pinned']:
            info = self.shell.catalog.find(desktop_id)
            if info is None:
                continue
            mine = [w for w in windows if match_app(w, info.get_id() or desktop_id)
                    or self.shell.catalog.for_window(w) is info]
            used.update(w['id'] for w in mine)
            rows.append((info, desktop_id, mine))
        loose = {}
        for w in windows:
            if w['id'] in used:
                continue
            info = self.shell.catalog.for_window(w)
            key = (info.get_id() if info else None) or w['app'] or w['cls'] or w['id']
            loose.setdefault(key, [info, []])[1].append(w)
        # unpinned apps keep the order they were dragged to for this session, new ones go last
        for key in merge_order(getattr(self.shell, 'loose_order', []), list(loose)):
            info, mine = loose[key]
            rows.append((info, key, mine))
        return rows

    def refresh(self, force=False):
        if self._dragging:
            self._late = True
            return
        rows = self.groups()
        # The helper sends the whole list on every change (titles change all the time);
        # rebuild only when something this taskbar shows is different.
        shown = [(key, id(info), tuple((w['id'], w['title'][:24] if len(wins) == 1 else '',
                  w['active'], w['attention'], w['minimized']) for w in wins))
                 for info, key, wins in rows]
        if shown == self._shown and not force:
            return
        self._shown = shown
        child = self.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        for info, key, wins in rows:
            self.append(self._button(info, key, wins))

    def _button(self, info, key, wins):
        button = Gtk.Button()
        button.add_css_class('spark-task')
        row = Gtk.Box(spacing=6)
        if info is not None and info.get_icon() is not None:
            image = Gtk.Image.new_from_gicon(info.get_icon())
        else:
            image = Gtk.Image.new_from_icon_name('application-x-executable')
        image.set_pixel_size(22)
        row.append(image)
        if wins:
            button.add_css_class('running')
            if any(w['active'] for w in wins):
                button.add_css_class('active')
            if any(w['attention'] for w in wins):
                button.add_css_class('attention')
            if len(wins) == 1:
                title = Gtk.Label(label=wins[0]['title'][:24])
                title.add_css_class('spark-dim')
                row.append(title)
            else:
                row.append(Gtk.Label(label=str(len(wins))))
        button.set_child(row)
        button.set_tooltip_text((info.get_name() if info else '') or
                                (wins[0]['title'] if wins else key))
        button.connect('clicked', lambda *_: self._primary(info, wins))
        right = Gtk.GestureClick(button=3)
        right.connect('released', lambda *_: self._menu(button, info, key, wins))
        button.add_controller(right)
        middle = Gtk.GestureClick(button=2)
        middle.connect('released', lambda *_: info and apps.launch(info, self.get_display()))
        button.add_controller(middle)
        dnd.attach_source(button, 'task', key, self._drag_begin, self._drag_end)
        dnd.attach_target(button, 'task', lambda name, after: self._drop(name, key, after))
        return button

    def _drag_begin(self):
        self._dragging = True

    def _drag_end(self):
        self._dragging = False
        if self._late:
            self._late = False
            self.refresh()

    def _drop(self, src, dst, after):
        """`src` was dropped before or after `dst` (None: at the end of this list)."""
        pinnable = src.endswith('.desktop') and self.shell.catalog.find(src) is not None
        self._dragging = False
        self.shell.move_task([k for _i, k, _w in self.groups()], src, dst, after, pinnable)
        return True

    def _primary(self, info, wins):
        tracker = self.shell.tracker
        if not wins:
            if info is not None:
                apps.launch(info, self.get_display())
            return
        mine = [w for w in wins if w['output'] == self.monitor_name] or wins
        active = [w for w in mine if w['active']]
        if len(mine) == 1:
            w = mine[0]
            tracker.act('minimize' if w['active'] and not w['minimized'] else 'activate',
                        w['id'])
        else:
            # cycle: the window after the active one
            ids = [w['id'] for w in mine]
            index = (ids.index(active[0]['id']) + 1) % len(ids) if active else 0
            tracker.act('activate', ids[index])

    def _menu(self, button, info, key, wins):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pop = _popover(button, box)
        display = self.get_display()
        if info is not None:
            box.append(_item(tr('new_window'), lambda: apps.launch(info, display), pop))
            if isinstance(info, apps.Gio.DesktopAppInfo):
                for action in info.list_actions():
                    label = info.get_action_name(action)
                    box.append(_item(label, lambda a=action: apps.launch_action(
                        info, a, display), pop))
            ident = info.get_id() or key
            pinned = ident in self.shell.config['pinned']
            box.append(_item(tr('unpin') if pinned else tr('pin'),
                             lambda: self.shell.set_pinned(ident, not pinned), pop))
        for w in wins:
            box.append(_item('%s: %s' % (tr('close_window'), w['title'][:28]),
                             lambda w=w: self.shell.tracker.act('close', w['id']), pop))
        pop.popup()


class WorkspaceSwitcher(Gtk.Box):
    """Numbered cells for the compositor's workspaces (the current one lit, the ones with windows
    marked), plus a tile toggle. Hidden until the compositor's control socket reports more than
    one workspace. Click goes there; the wheel steps through them."""

    def __init__(self, link):
        super().__init__(spacing=2)
        self.link = link
        self._count = 0
        self.cells = []
        self.set_visible(False)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self._scroll)
        self.add_controller(scroll)
        self.tile = Gtk.Button(label='\u25a6')
        self.tile.add_css_class('spark-ws')
        self.tile.add_css_class('spark-ws-tile')
        self.tile.connect('clicked', lambda *_: link.toggle_tiling())

    def _scroll(self, _c, _dx, dy):
        if dy:
            self.link.scroll(1 if dy > 0 else -1)
        return True

    def update(self):
        link = self.link
        show = link.visible()
        self.set_visible(show)
        if not show:
            return
        if link.count != self._count:
            self._count = link.count
            child = self.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.remove(child)
                child = nxt
            self.cells = []
            for n in range(1, link.count + 1):
                button = Gtk.Button(label=str(n))
                button.add_css_class('spark-ws')
                button.set_tooltip_text(tr('ws_cell') % n)
                button.connect('clicked', lambda _b, n=n: self.link.go_to(n))
                self.append(button)
                self.cells.append(button)
            self.append(self.tile)
        for n, button in enumerate(self.cells, 1):
            for name, on in (('current', n == link.current), ('occupied', n in link.occupied)):
                if on:
                    button.add_css_class(name)
                else:
                    button.remove_css_class(name)
        self.tile.set_visible(link.tiling is not None)
        if link.tiling:
            self.tile.add_css_class('on')
        else:
            self.tile.remove_css_class('on')
        self.tile.set_tooltip_text(tr('ws_tile_on') if link.tiling else tr('ws_tile_off'))
        self.set_tooltip_text(tr('ws_tip') % (link.current, link.count))


class ConnectButton(Gtk.Button):
    """Spark Connect's status in the panel: a dot (ok, warning, down, unknown) and the number of
    problems. Click lists every machine and site; right-click moves or removes it; it can be
    dragged to another screen's panel. Only the panel the setting names shows it."""

    def __init__(self, shell, panel):
        super().__init__()
        self.shell, self.panel = shell, panel
        self.add_css_class('spark-flat')
        row = Gtk.Box(spacing=4)
        self.dot = Gtk.Label(label='\u25cf')
        self.dot.add_css_class('spark-dot')
        self.count = Gtk.Label()
        self.count.add_css_class('spark-count')
        row.append(self.dot)
        row.append(self.count)
        self.set_child(row)
        self.set_visible(False)
        self.connect('clicked', lambda *_: self._open())
        right = Gtk.GestureClick(button=3)
        right.connect('released', lambda *_: self._menu())
        self.add_controller(right)
        dnd.attach_source(self, 'connect', 'widget')

    def update(self):
        shell = self.shell
        connect = shell.connect_status
        show = connect.available() and shell.connect_host() == self.panel.connector
        self.set_visible(show)
        if not show:
            return
        status = connect.status
        state = connectstatus.widget_state(status)
        for name in ('ok', 'warn', 'down', 'unknown'):
            if name == state:
                self.dot.add_css_class(name)
            else:
                self.dot.remove_css_class(name)
        n = connectstatus.problem_count(status)
        self.count.set_text(str(n) if n else '')
        self.count.set_visible(bool(n))
        self.set_tooltip_text(connectstatus.summary_text(status))

    def _open(self):
        connect = self.shell.connect_status
        status = connect.status
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pop = _popover(self, box)
        box.append(Gtk.Label(label=connectstatus.summary_text(status), xalign=0))
        if status and status['machines']:
            head = Gtk.Label(label=tr('connect_machines'), xalign=0)
            head.add_css_class('spark-label')
            box.append(head)
            for m in status['machines']:
                box.append(self._line(m['state'], m['name'], m['verdict']))
                for problem in m['problems']:
                    note = Gtk.Label(label=problem, xalign=0, wrap=True, max_width_chars=48)
                    note.add_css_class('spark-dim')
                    note.set_margin_start(24)
                    box.append(note)
        if status and status['sites']:
            head = Gtk.Label(label=tr('connect_sites'), xalign=0)
            head.add_css_class('spark-label')
            box.append(head)
            for site in status['sites']:
                box.append(self._line(site['state'], site['name'],
                                      connectstatus.site_text(site)))
        when = connectstatus.checked_text(status)
        if when:
            line = Gtk.Label(label=when, xalign=0)
            line.add_css_class('spark-dim')
            box.append(line)
        box.append(Gtk.Separator())
        box.append(_item(tr('connect_check_now'), connect.check, pop))
        box.append(_item(tr('connect_open'), self._launch, pop))
        pop.popup()

    @staticmethod
    def _line(state, name, detail):
        row = Gtk.Box(spacing=8)
        dot = Gtk.Label(label='\u25cf')
        dot.add_css_class('spark-dot')
        dot.add_css_class(state if state in ('ok', 'warn', 'down', 'rebooting') else 'unknown')
        row.append(dot)
        label = Gtk.Label(label=name, xalign=0)
        label.add_css_class('spark-text')
        row.append(label)
        if detail:
            more = Gtk.Label(label=detail, xalign=0)
            more.add_css_class('spark-dim')
            row.append(more)
        return row

    def _launch(self):
        info = self.shell.catalog.find(connectstatus.DESKTOP_ID)
        if info is None or not apps.launch(info, self.get_display()):
            apps.run(['spark-connect'])

    def _menu(self):
        shell = self.shell
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pop = _popover(self, box)
        connectors = [p.connector for p in shell.panels]
        if len(connectors) > 1:
            head = Gtk.Label(label=tr('connect_move'), xalign=0)
            head.add_css_class('spark-label')
            box.append(head)
            here = shell.connect_host()
            for name in connectors:
                mark = '\u2713 ' if name == here else '   '
                box.append(_item(mark + name, lambda n=name: shell.set_connect_monitor(n), pop))
            box.append(Gtk.Separator())
        box.append(_item(tr('connect_remove'), lambda: shell.set_connect_enabled(False), pop))
        pop.popup()


class Panel(Gtk.Window):
    def __init__(self, shell, monitor, with_tray):
        super().__init__()
        self.shell = shell
        self.monitor = monitor
        self.set_decorated(False)
        self.add_css_class('spark-panel')
        position = shell.config['panel_position']
        self.add_css_class('top' if position == 'top' else 'bottom')
        self.set_default_size(monitor.get_geometry().width, PANEL_HEIGHT)
        layer.setup(self, 'top', ('left', 'right', position), 'spark-panel', monitor,
                    exclusive=PANEL_HEIGHT)
        self.connector = monitor.get_connector() or ''

        bar = Gtk.CenterBox()
        bar.set_margin_start(6)
        bar.set_margin_end(6)
        bar.set_margin_top(3)
        bar.set_margin_bottom(3)
        self.set_child(bar)

        left = Gtk.Box(spacing=8)
        self.launcher = Gtk.Button(label='SPARK')
        self.launcher.add_css_class('spark-launcher-btn')
        self.launcher.set_tooltip_text(tr('launcher'))
        self.launcher.connect('clicked', lambda *_: shell.toggle_launcher())
        left.append(self.launcher)
        self.tasks = TaskList(shell, self.connector, home=with_tray)
        left.append(self.tasks)
        bar.set_start_widget(left)

        right = Gtk.Box(spacing=6)
        self.workspaces = WorkspaceSwitcher(shell.compositor)
        right.append(self.workspaces)
        self.connect_button = ConnectButton(shell, self)
        right.append(self.connect_button)
        self.tray = None
        if with_tray:
            from .trayui import TrayView
            self.tray = TrayView(shell.tray, shell.config['tray_order'], shell.set_tray_order)
            right.append(self.tray)
        right.append(shell.notifications_ui.bell())
        right.append(ClockButton())
        bar.set_end_widget(right)
        # the Spark Connect widget can be dragged onto any panel
        dnd.attach_target(bar, 'connect', lambda *_: (
            shell.set_connect_monitor(self.connector), True)[1], mark=False)
        self.workspaces.update()
        self._glitch_timer = GLib.timeout_add_seconds(random_delay(), self._glitch)
        self.connect('destroy', lambda *_: self._glitch_timer and GLib.source_remove(self._glitch_timer))

    def _glitch(self):
        """The launcher mark slips for a moment now and then."""
        self.launcher.add_css_class('spark-glitch')
        GLib.timeout_add(220, lambda: (self.launcher.remove_css_class('spark-glitch'), False)[1])
        self._glitch_timer = GLib.timeout_add_seconds(random_delay(), self._glitch)
        return False


def random_delay():
    import random
    return random.randint(25, 70)
