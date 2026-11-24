"""The root side: state, install, update, roll back, prune. Only /usr/libexec/spark-apps-update
(root, started by systemd) runs this; tests run it on a temp folder.

Everything under /var/lib/spark-apps is written here, by root, after the signature, sha256, size
and system_api checks passed. Each version is unpacked into a hidden stage folder in the same
folder, checked, and moved into place with one rename, so a launch never sees half a copy.
"""

import compileall
import contextlib
import fcntl
import json
import os
import py_compile
import shutil
import tempfile
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

from . import MAX_BUNDLE_BYTES, MAX_INDEX_BYTES, INDEX_URL
from . import archive, fetch as fetch_mod, index as index_mod
from .choose import entry_name, read_json
from .paths import Paths, valid_slug, version_key

SCHEMA = 1


class StoreError(Exception):
    """One app couldn't be installed, or a request can't be done. Says why in plain words."""


def new_state() -> Dict[str, Any]:
    return {'schema': SCHEMA, 'serial': 0, 'issued': 0, 'expires': 0, 'last_check': 0,
            'last_result': '', 'last_error': '', 'apps': {}}


def load_state(paths: Paths) -> Dict[str, Any]:
    state = read_json(paths.state_file)
    if not state or not isinstance(state.get('apps'), dict):
        return new_state()
    base = new_state()
    base.update(state)
    return base


def save_state(paths: Paths, state: Dict[str, Any]) -> None:
    os.makedirs(paths.state_dir, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.state-', suffix='.tmp', dir=paths.state_dir)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=1, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, paths.state_file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def locked(paths: Paths) -> Iterator[None]:
    """One run at a time (the timer and a click on Update now can overlap)."""
    os.makedirs(paths.state_dir, mode=0o755, exist_ok=True)
    fd = os.open(paths.lock_file, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def app_state(state: Dict[str, Any], slug: str) -> Dict[str, Any]:
    entry = state['apps'].get(slug)
    if not isinstance(entry, dict):
        entry = state['apps'][slug] = {}
    entry.setdefault('use', 'live')
    return entry


def image_record(paths: Paths, slug: str) -> Optional[Dict[str, Any]]:
    """What the image says about a built-in app, or None when it doesn't take live updates."""
    rec = read_json(paths.image_record(slug))
    if not rec or rec.get('live_update') is not True:
        return None
    try:
        version_key(rec.get('version'))
    except ValueError:
        return None
    if isinstance(rec.get('system_api'), bool) or not isinstance(rec.get('system_api'), int):
        return None
    return rec


def builtin_records(paths: Paths) -> Dict[str, Dict[str, Any]]:
    """Every built-in app that takes live updates: slug -> its image record."""
    found = {}
    try:
        names = sorted(os.listdir(paths.image_dir))
    except OSError:
        return found
    for name in names:
        if name.endswith('.json') and valid_slug(name[:-5]):
            rec = image_record(paths, name[:-5])
            if rec:
                found[name[:-5]] = rec
    return found


# ─── Install ──────────────────────────────────────────────

def _check_manifest(tree: str, slug: str, entry: index_mod.AppEntry, image_api: int) -> None:
    manifest = read_json(os.path.join(tree, 'spark-app.json'))
    if not manifest:
        raise StoreError("the bundle has no spark-app.json")
    if manifest.get('slug') != slug:
        raise StoreError("the bundle is for another app")
    if manifest.get('version') != entry.version:
        raise StoreError("the bundle's version isn't the one the index promised")
    if manifest.get('live_update') is not True:
        raise StoreError("the bundle doesn't say it takes live updates")
    if manifest.get('system_api') != entry.system_api or entry.system_api != image_api:
        raise StoreError("the bundle's system_api isn't this image's")
    if not os.path.isfile(os.path.join(tree, entry_name(slug))):
        raise StoreError(f"the bundle has no {entry_name(slug)}")


def _compile(tree: str) -> None:
    ok = compileall.compile_dir(tree, quiet=2, force=True, workers=1, legacy=False,
                                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    if not ok:
        raise StoreError("the bundle's Python files don't compile")


def install_bundle(paths: Paths, entry: index_mod.AppEntry, image_api: int,
                   fetcher: Callable[..., bytes], *, allow_http: bool = False,
                   compile_pyc: bool = True) -> None:
    """Download, check, unpack, compile and move one bundle into place; leaves state.json to the
    caller. Raises StoreError, fetch_mod.FetchError or archive.ArchiveError; nothing is left
    behind on failure."""
    slug = entry.slug
    stage = tempfile.mkdtemp(prefix='.stage-', dir=paths.state_dir)
    try:
        bundle = os.path.join(stage, 'bundle.tar.gz')
        with open(bundle, 'wb') as out:
            fetcher(entry.url, min(entry.size, MAX_BUNDLE_BYTES), out, allow_http=allow_http)
        if os.path.getsize(bundle) != entry.size:
            raise StoreError("the bundle's size isn't the one the index promised")
        if fetch_mod.sha256_file(bundle) != entry.sha256:
            raise StoreError("the bundle's sha256 isn't the one the index promised")
        tree = os.path.join(stage, 'tree')
        archive.extract(bundle, tree)
        _check_manifest(tree, slug, entry, image_api)
        if compile_pyc:
            _compile(tree)
        os.makedirs(paths.app_dir(slug), mode=0o755, exist_ok=True)
        final = paths.version_dir(slug, entry.version)
        if os.path.lexists(final):                 # left over from an interrupted run
            shutil.rmtree(final)
        os.rename(tree, final)
        fd = os.open(paths.app_dir(slug), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def prune(paths: Paths, slug: str, keep: List[str]) -> None:
    """Remove every version folder of an app except those in keep."""
    try:
        names = os.listdir(paths.app_dir(slug))
    except OSError:
        return
    for name in names:
        if name not in keep:
            shutil.rmtree(os.path.join(paths.app_dir(slug), name), ignore_errors=True)
    if not keep:
        with contextlib.suppress(OSError):
            os.rmdir(paths.app_dir(slug))


def reconcile(paths: Paths, state: Dict[str, Any]) -> List[str]:
    """After an OS update the image may have caught up with a live copy (same or newer built-in
    version) or changed its system_api: that live copy can never be used again. Remove it.
    Also removes folders state.json doesn't know. Returns the slugs it cleaned."""
    cleaned = []
    records = builtin_records(paths)
    for name in list(os.listdir(paths.state_dir)) if os.path.isdir(paths.state_dir) else []:
        if name.startswith('.stage-'):
            shutil.rmtree(os.path.join(paths.state_dir, name), ignore_errors=True)
    for slug in sorted(set(state['apps']) | set(_app_folders(paths))):
        if not valid_slug(slug):
            continue
        app = state['apps'].get(slug) if isinstance(state['apps'].get(slug), dict) else {}
        rec = records.get(slug)
        stale = False
        for key in ('active', 'previous'):
            version = app.get(key)
            if not version:
                continue
            try:
                usable = rec is not None and version_key(version) > version_key(rec['version'])
            except ValueError:
                usable = False
            manifest = read_json(os.path.join(paths.version_dir(slug, str(version)),
                                              'spark-app.json')) if usable else None
            if not usable or not manifest or manifest.get('system_api') != rec['system_api']:
                app[key] = None
                stale = True
        if stale and slug in state['apps']:
            cleaned.append(slug)
            state['apps'][slug] = app
        keep = [v for v in (app.get('active'), app.get('previous')) if v]
        prune(paths, slug, keep)
    return cleaned


def _app_folders(paths: Paths) -> List[str]:
    try:
        return [n for n in os.listdir(paths.state_dir)
                if valid_slug(n) and os.path.isdir(os.path.join(paths.app_dir(n)))]
    except OSError:
        return []


# ─── The update run ────────────────────────────────────────

def run_update(paths: Paths, *, index_url: str = INDEX_URL, allow_http: bool = False,
               now: Optional[float] = None, openssl: str = index_mod.OPENSSL,
               fetcher: Callable[..., bytes] = fetch_mod.fetch,
               compile_pyc: bool = True, log: Callable[[str], None] = lambda _m: None
               ) -> Dict[str, str]:
    """Fetch the index, and install what is newer. Returns slug -> what happened. The result
    of the run itself (ok, offline, refused) is in state.json's last_result."""
    now = time.time() if now is None else now
    results: Dict[str, str] = {}
    with locked(paths):
        state = load_state(paths)
        state['last_check'] = int(now)
        for slug in reconcile(paths, state):
            log(f"{slug}: the image caught up with the live copy; removed it")
        try:
            data = fetcher(index_url, MAX_INDEX_BYTES, allow_http=allow_http)
            index = index_mod.load(data, paths.key, now=now, last_serial=int(state['serial']),
                                   openssl=openssl)
        except fetch_mod.FetchError as exc:
            state['last_result'] = 'offline' if exc.offline else 'failed'
            state['last_error'] = str(exc)
            save_state(paths, state)
            log(f"index: {exc}")
            return results
        except index_mod.IndexError_ as exc:
            state['last_result'], state['last_error'] = 'refused', str(exc)
            save_state(paths, state)
            log(f"index refused: {exc}")
            return results
        state['serial'], state['issued'], state['expires'] = \
            index.serial, int(index.issued), int(index.expires)
        failures = 0
        records = builtin_records(paths)
        for slug in sorted(index.apps):
            entry = index.apps[slug]
            rec = records.get(slug)
            if rec is None:
                results[slug] = 'not-live'          # not in this image, or doesn't take updates
                continue
            app = app_state(state, slug)
            app['latest'], app['latest_system_api'] = entry.version, entry.system_api
            app['waiting'] = None
            if entry.system_api != rec['system_api']:
                app['waiting'] = 'needs-os'
                results[slug] = 'needs-os'
                continue
            if app.get('use') == 'builtin':
                results[slug] = 'held'
                continue
            floor = version_key(rec['version'])
            if app.get('active'):
                floor = max(floor, version_key(app['active']))
            if version_key(entry.version) <= floor or app.get('rejected') == entry.version:
                results[slug] = 'current'
                continue
            try:
                install_bundle(paths, entry, rec['system_api'], fetcher,
                               allow_http=allow_http, compile_pyc=compile_pyc)
            except (StoreError, fetch_mod.FetchError, archive.ArchiveError, OSError) as exc:
                failures += 1
                results[slug] = 'failed'
                app['last_error'] = str(exc)
                log(f"{slug} {entry.version}: not installed: {exc}")
                continue
            previous = app.get('active')
            app['previous'] = previous if previous != entry.version else app.get('previous')
            app['active'], app['use'], app['last_error'] = entry.version, 'live', ''
            app['installed_at'] = int(now)
            save_state(paths, state)
            prune(paths, slug, [v for v in (app['active'], app.get('previous')) if v])
            results[slug] = 'installed'
            log(f"{slug}: installed {entry.version}")
        state['last_result'] = 'failed' if failures else 'ok'
        state['last_error'] = ''
        save_state(paths, state)
    return results


# ─── Roll back ────────────────────────────────────────────

def _change(paths: Paths, slug: str, fn: Callable[[Dict[str, Any]], None]) -> None:
    if not valid_slug(slug):
        raise StoreError(f"{slug!r} isn't an app name")
    with locked(paths):
        state = load_state(paths)
        fn(app_state(state, slug))
        save_state(paths, state)


def use_builtin(paths: Paths, slug: str) -> None:
    """Run the version that came with the image. The live copy stays on disk; update runs leave
    this app alone until use_live."""
    _change(paths, slug, lambda app: app.update(use='builtin'))


def use_live(paths: Paths, slug: str) -> None:
    def go(app):
        app.update(use='live')
        app.pop('rejected', None)
    _change(paths, slug, go)


def use_previous(paths: Paths, slug: str) -> None:
    """Go back to the live version before the active one. That version isn't installed again."""
    def go(app):
        previous = app.get('previous')
        if not previous or not os.path.isdir(paths.version_dir(slug, str(previous))):
            raise StoreError("there is no earlier live version")
        app['rejected'], app['active'], app['previous'] = app.get('active'), previous, None
        app['use'] = 'live'
    _change(paths, slug, go)
    with locked(paths):
        app = app_state(load_state(paths), slug)
        prune(paths, slug, [v for v in (app.get('active'),) if v])


def automatic_enabled(paths: Paths) -> bool:
    """False when /etc/sparkos/update.conf says automatic = no (the timer then does nothing)."""
    try:
        with open(paths.conf, encoding='utf-8', errors='replace') as f:
            for raw in f:
                line = raw.split('#', 1)[0].strip()
                key, sep, value = line.partition('=')
                if sep and key.strip().lower() == 'automatic':
                    return value.strip().strip('"\'').lower() not in ('no', 'false', 'off', '0')
    except OSError:
        pass
    return True
