"""The panel: one per monitor. Launcher button, task list (pinned apps + open windows), the
notification bell, the tray (on the first panel only: there is one tray) and the clock."""

import time

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk  # noqa: E402

from . import apps, clockbridge, layer  # noqa: E402
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
        for key, (info, mine) in loose.items():
            rows.append((info, key, mine))
        return rows

    def refresh(self):
        rows = self.groups()
        # The helper sends the whole list on every change (titles change all the time);
        # rebuild only when something this taskbar shows is different.
        shown = [(key, id(info), tuple((w['id'], w['title'][:24] if len(wins) == 1 else '',
                  w['active'], w['attention'], w['minimized']) for w in wins))
                 for info, key, wins in rows]
        if shown == self._shown:
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
        return button

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
        self.tray = None
        if with_tray:
            from .trayui import TrayView
            self.tray = TrayView(shell.tray)
            right.append(self.tray)
        right.append(shell.notifications_ui.bell())
        right.append(ClockButton())
        bar.set_end_widget(right)
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
