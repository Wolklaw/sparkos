"""The installed apps: what the launcher lists, what the task list shows icons for, and how an
app is started. Gio only."""

import logging
import subprocess

from gi.repository import Gio

log = logging.getLogger('spark-shell')


def desktop_name(app_id: str) -> str:
    return app_id[:-8] if app_id.endswith('.desktop') else app_id


class Catalog:
    """All apps that should show in menus, with lookups by desktop id and window class."""

    def __init__(self):
        self.apps = []
        self.by_id = {}
        self.by_class = {}
        self.reload()

    def reload(self):
        self.apps, self.by_id, self.by_class = [], {}, {}
        for info in Gio.AppInfo.get_all():
            if not info.should_show():
                continue
            ident = info.get_id() or ''
            self.apps.append(info)
            self.by_id[desktop_name(ident).lower()] = info
            wm = ''
            if isinstance(info, Gio.DesktopAppInfo):
                wm = info.get_startup_wm_class() or ''
            if wm:
                self.by_class.setdefault(wm.lower(), info)
        self.apps.sort(key=lambda a: (a.get_name() or '').lower())

    def find(self, app_id: str):
        """AppInfo for 'x.desktop', 'x' or a window class, or None."""
        key = desktop_name(app_id or '').lower()
        if not key:
            return None
        return self.by_id.get(key) or self.by_class.get(key)

    def for_window(self, window: dict):
        return self.find(window.get('app', '')) or self.find(window.get('cls', ''))

    def entries(self):
        """The dicts launcher_logic ranks: name, description, id, plus the AppInfo."""
        return [{'name': a.get_name() or '', 'description': a.get_generic_name() or
                 a.get_description() or '', 'id': a.get_id() or '', 'info': a}
                for a in self.apps]


def launch(info, display=None) -> bool:
    """Start an app. Errors are logged, not raised: a broken launcher entry mustn't crash us."""
    try:
        context = display.get_app_launch_context() if display is not None else None
        return info.launch([], context)
    except Exception as e:
        log.warning('could not start %s: %s', info.get_id(), e)
        return False


def launch_action(info, action: str, display=None) -> bool:
    try:
        context = display.get_app_launch_context() if display is not None else None
        info.launch_action(action, context)
        return True
    except Exception as e:
        log.warning('could not run %s of %s: %s', action, info.get_id(), e)
        return False


def run(command, **kwargs):
    """Fire and forget a command (power actions, spark-store...)."""
    try:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True, **kwargs)
    except OSError as e:
        log.warning('could not run %s: %s', command, e)
        return None
