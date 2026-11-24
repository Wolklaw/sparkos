"""Which copy of an app runs: the newest verified live one whose system_api matches the image's,
else the built-in one. This is what the launcher uses, so it imports almost nothing and never
raises: any doubt means the built-in copy.

A live copy is used only when all of this is true:
- the image's record (/usr/share/spark-apps/<slug>.json) says the app takes live updates;
- /var/lib/spark-apps/state.json, which only root writes, names an active version, and the
  app isn't set to "use the built-in version";
- the version folder and every folder above it are real folders (no links), owned by root and
  not writable by anyone else (the launcher checks, even though only root ever writes there);
- the live version is newer than the built-in one;
- the live copy's own spark-app.json says the same version and the same system_api as the image.
"""

import json
import os
import stat
from typing import NamedTuple, Optional

from .paths import Paths, valid_slug, version_key


class Choice(NamedTuple):
    source: str          # 'live' or 'builtin'
    directory: str       # the folder that holds the app's files
    version: str         # '' when unknown
    why: str             # plain words, for logs and tests


def entry_name(slug: str) -> str:
    """spark-calc -> spark_calc.py"""
    return slug.replace('-', '_') + '.py'


def read_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _trusted(path: str, uid: int, want_dir: bool = True) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    kind_ok = stat.S_ISDIR(st.st_mode) if want_dir else stat.S_ISREG(st.st_mode)
    return kind_ok and st.st_uid == uid and not st.st_mode & 0o022


def builtin(paths: Paths, slug: str, why: str) -> Choice:
    rec = read_json(paths.image_record(slug)) or {}
    return Choice('builtin', paths.builtin(slug), str(rec.get('version') or ''), why)


def select(paths: Paths, slug: str, trusted_uid: int = 0) -> Choice:
    try:
        return _select(paths, slug, trusted_uid)
    except Exception as exc:          # noqa: BLE001 - the launcher must always start the app
        return builtin(paths, slug, f"live copy not used ({exc.__class__.__name__})")


def _select(paths: Paths, slug: str, uid: int) -> Choice:
    if not valid_slug(slug):
        raise ValueError("bad slug")
    rec = read_json(paths.image_record(slug))
    if not rec or rec.get('live_update') is not True:
        return builtin(paths, slug, "this app doesn't take live updates")
    image_api = rec.get('system_api')
    if isinstance(image_api, bool) or not isinstance(image_api, int):
        return builtin(paths, slug, "the image doesn't say its system_api")
    base = version_key(rec.get('version'))

    if not _trusted(paths.state_dir, uid) or not _trusted(paths.state_file, uid, want_dir=False):
        return builtin(paths, slug, "no live updates installed")
    state = read_json(paths.state_file) or {}
    apps = state.get('apps')
    app = apps.get(slug) if isinstance(apps, dict) else None
    if not isinstance(app, dict) or not app.get('active'):
        return builtin(paths, slug, "no live copy installed")
    if app.get('use', 'live') != 'live':
        return builtin(paths, slug, "set to use the built-in version")
    version = app['active']
    if version_key(version) <= base:
        return builtin(paths, slug, "the built-in version is as new")

    folder = paths.version_dir(slug, version)
    for part in (paths.app_dir(slug), folder):
        if not _trusted(part, uid):
            return builtin(paths, slug, "live copy isn't root-owned: not used")
    manifest = read_json(os.path.join(folder, 'spark-app.json'))
    if not manifest or manifest.get('version') != version \
            or manifest.get('system_api') != image_api:
        return builtin(paths, slug, "live copy's system_api differs from the image's")
    if not os.path.isfile(os.path.join(folder, entry_name(slug))):
        return builtin(paths, slug, "live copy has no entry file")
    return Choice('live', folder, version, "newest verified live copy")
