"""The Spark apps: the owner's own apps for SparkOS, listed first in the Store.

Each Spark app describes itself in a spark-app.json next to its code. The Store reads them from:

  1. its own spark-apps/ folder (install.sh copies every Spark app's spark-app.json and icon
     there; the image build does the same), and the sibling folders when run from the repo;
  2. the installed apps: /usr/lib/<slug>/ (in the image) and ~/.local/lib/<slug>/ (per user).

An app that isn't installed can be installed for you only when its source folder (install.sh
and spark-app.json) is on this PC. How Spark apps will be downloaded (release tarballs checked
against SHA256SUMS, or the owner's own Flatpak repository) isn't decided yet, so nothing is
downloaded here."""

import glob
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import APP_ID
from .appstream import App, fold_fields
from .core import data_dirs, data_home, home, languages, log

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the app folder


@dataclass
class SparkApp:
    id: str
    slug: str
    name: str
    summary: str = ''
    version: str = ''
    size_kb: Optional[int] = None
    license: str = ''
    source_url: str = ''
    desktop: str = ''
    command: str = ''
    in_image: bool = False
    icon_file: str = ''              # a PNG next to the spark-app.json, if any
    folder: str = ''                 # where the spark-app.json was read
    needs: Dict = field(default_factory=dict)

    # filled by refresh_state()
    installed: Optional[str] = None  # 'system', 'user' or None
    desktop_path: str = ''
    source: str = ''                 # a folder with install.sh to install from, if any

    def as_app(self) -> App:
        app = App(id=self.id, name=self.name, summary=self.summary, developer='Wolklaw',
                  verified=True, license=self.license or 'LicenseRef-proprietary',
                  categories=['Spark'], keywords=[self.slug, 'spark', 'sparkos'],
                  kind='spark')
        fold_fields(app)
        return app


def _fallbacks() -> List[dict]:
    """The owner's apps that don't carry a spark-app.json yet (Soot and FreeSuite come from
    their own repositories; Spark Snip and Spark Media predate the file)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'own-apps.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return [d for d in data if isinstance(d, dict)]
    except (OSError, ValueError):
        return []


def search_dirs() -> List[str]:
    """Folders that hold <slug>/spark-app.json, in the order they win."""
    forced = os.environ.get('SPARK_STORE_SPARK_DIRS')
    if forced is not None:
        return [d for d in forced.split(os.pathsep) if d]
    dirs = [os.path.join(HERE, 'spark-apps'),
            os.path.join(home(), '.local', 'lib'), '/usr/lib']
    parent = os.path.dirname(HERE)              # files/ in the repo: run from source
    if os.path.isfile(os.path.join(parent, 'spark-store', 'spark_store.py')):
        dirs.insert(1, parent)
    return dirs


def source_dirs() -> List[str]:
    """Folders that may hold an app's source (<slug>/install.sh) to install it from."""
    forced = os.environ.get('SPARK_STORE_SOURCES')
    if forced is not None:
        return [d for d in forced.split(os.pathsep) if d]
    dirs = [os.path.join(data_home(), 'spark-store', 'sources'),
            '/usr/share/spark-store/sources']
    parent = os.path.dirname(HERE)
    if os.path.isfile(os.path.join(parent, 'spark-store', 'spark_store.py')):
        dirs.append(parent)
    return dirs


def _pick_lang(data: dict, key: str) -> str:
    for lang in languages():
        short = lang.split('_')[0]
        if data.get(f'{key}_{short}'):
            return str(data[f'{key}_{short}'])
    return str(data.get(key) or '')


def parse(data: dict, folder: str = '') -> Optional[SparkApp]:
    """A spark-app.json (the apps don't all use the same keys yet; this reads them all)."""
    app_id = str(data.get('id') or '').strip()
    slug = str(data.get('slug') or data.get('command') or '').strip()
    name = _pick_lang(data, 'name').strip()
    if not app_id or not name:
        return None
    if not slug:
        slug = name.lower().replace(' ', '-')
    summary = _pick_lang(data, 'summary') or _pick_lang(data, 'description')
    size = data.get('size_kb', data.get('installed_size_kb'))
    try:
        size_kb = int(size) if size is not None else None
    except (TypeError, ValueError):
        size_kb = None
    desktop = str(data.get('desktop') or f'{app_id}.desktop')
    icon = ''
    if folder:
        for cand in ('icon.png', str(data.get('icon') or '')):
            if cand and cand.endswith('.png') and os.path.isfile(os.path.join(folder, cand)):
                icon = os.path.join(folder, cand)
                break
    in_image = data.get('in_image')
    return SparkApp(id=app_id, slug=slug, name=name, summary=summary.strip(),
                    version=str(data.get('version') or ''), size_kb=size_kb,
                    license=str(data.get('license') or ''),
                    source_url=str(data.get('source') or ''), desktop=desktop,
                    command=str(data.get('command') or slug), in_image=bool(in_image),
                    icon_file=icon, folder=folder,
                    needs=data.get('needs') if isinstance(data.get('needs'), dict) else {})


def read_file(path: str) -> Optional[SparkApp]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    return parse(data, os.path.dirname(path))


def discover() -> List[SparkApp]:
    """Every Spark app the Store knows of, except the Store itself, by name."""
    found: Dict[str, SparkApp] = {}
    for base in search_dirs():
        for path in sorted(glob.glob(os.path.join(base, '*', 'spark-app.json'))):
            app = read_file(path)
            if app and app.id not in found:
                found[app.id] = app
            elif app and not found[app.id].icon_file and app.icon_file:
                found[app.id].icon_file = app.icon_file
    if os.environ.get('SPARK_STORE_SPARK_DIRS') is None:
        for data in _fallbacks():
            app = parse(data)
            if app and app.id not in found:
                found[app.id] = app
    found.pop(APP_ID, None)
    apps = sorted(found.values(), key=lambda a: a.name.lower())
    for app in apps:
        refresh_state(app)
    return apps


def _desktop_dirs() -> List[tuple]:
    return [('user', os.path.join(data_home(), 'applications'))] + \
        [('system', os.path.join(d, 'applications')) for d in data_dirs()]


def refresh_state(app: SparkApp) -> None:
    app.installed, app.desktop_path = None, ''
    for scope, folder in _desktop_dirs():
        path = os.path.join(folder, app.desktop)
        if os.path.isfile(path):
            app.installed, app.desktop_path = scope, path
            break
    if os.path.isfile(user_manifest(app)):
        app.installed = 'user'
    app.source = ''
    for base in source_dirs():
        folder = os.path.join(base, app.slug)
        if os.path.isfile(os.path.join(folder, 'install.sh')) and \
                os.path.isfile(os.path.join(folder, 'spark-app.json')):
            app.source = folder
            break


def user_manifest(app: SparkApp) -> str:
    return os.path.join(home(), '.local', 'lib', app.slug, 'installed-files')


def icon_path(app: SparkApp) -> Optional[str]:
    """A PNG for the app: the installed icon theme's, else the one beside its spark-app.json."""
    bases = [os.path.join(data_home(), 'icons')] + [os.path.join(d, 'icons') for d in data_dirs()]
    for size in (64, 128, 48, 256):
        for base in bases:
            path = os.path.join(base, 'hicolor', f'{size}x{size}', 'apps', f'{app.id}.png')
            if os.path.isfile(path):
                return path
    return app.icon_file or None


# ─── Install, remove, open ───────────────────────────────────

def install_command(app: SparkApp) -> Optional[List[str]]:
    if not app.source:
        return None
    return ['bash', os.path.join(app.source, 'install.sh'), '--user']


def uninstall_command(app: SparkApp) -> Optional[List[str]]:
    """Removing works only for apps installed for you; the ones in the image are part of
    SparkOS. The app's own install.sh does it when its source is here; otherwise the list
    of files it installed (installed-files) is enough."""
    if app.installed != 'user':
        return None
    if app.source:
        return ['bash', os.path.join(app.source, 'install.sh'), '--user', '--uninstall']
    return None


def remove_with_manifest(app: SparkApp) -> str:
    """Delete exactly the files listed in ~/.local/lib/<slug>/installed-files (only inside
    your home), then that folder. Returns an error message, or ''."""
    manifest = user_manifest(app)
    lib = os.path.dirname(manifest)
    mine = os.path.realpath(home()) + os.sep
    try:
        with open(manifest, encoding='utf-8') as f:
            paths = [line.strip() for line in f if line.strip()]
    except OSError as exc:
        return str(exc)
    for path in paths:
        if not os.path.realpath(os.path.dirname(path)).startswith(mine):
            log.warning("not removing %s: outside the home folder", path)
            continue
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.unlink(path)
        except OSError as exc:
            log.warning("could not remove %s: %s", path, exc)
    if os.path.realpath(lib).startswith(mine):
        shutil.rmtree(lib, ignore_errors=True)
    return ''


def launch(app: SparkApp) -> bool:
    candidates = []
    if app.desktop_path and shutil.which('gio'):
        candidates.append(['gio', 'launch', app.desktop_path])
    if shutil.which('gtk-launch'):
        candidates.append(['gtk-launch', app.desktop[:-8] if app.desktop.endswith('.desktop')
                           else app.desktop])
    exe = shutil.which(app.command) or os.path.join(home(), '.local', 'bin', app.command)
    if os.path.isfile(exe):
        candidates.append([exe])
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=os.name == 'posix',
                             close_fds=True)
            return True
        except OSError:
            continue
    return False
