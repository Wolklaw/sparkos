"""Windows apps Spark Run knows how to get: `spark-run --get amazon-music` downloads the
vendor's installer, checks its SHA-256 against the one written here, installs it and adds it to
the menu. Asked again, it only reports the app that is already installed.

The fingerprint is the trust, like in sources.py. To move to a newer installer: download it
from the vendor, then change the URL, size and SHA-256 together.
"""

import threading
from dataclasses import dataclass
from typing import Optional

from . import apps, fetch, sources
from .errors import Problem
from .fetch import FetchError


@dataclass(frozen=True)
class CatalogApp:
    key: str                    # what `--get` takes, and the app's menu slug
    name: str
    installer: sources.Download
    silent: bool = False        # ask the installer to skip its wizard


# Amazon's own Windows installer (the 9.4.0.2386 build that winget lists). The app updates
# itself after it is installed.
CATALOG = (
    CatalogApp(
        key='amazon-music',
        name="Amazon Music",
        installer=sources.Download(
            key='amazon-music',
            name="Amazon Music installer",
            version="9.4.0.2386",
            url="https://d2j9xt6n9dg5d3.cloudfront.net/win/"
                "23861115_85d5deb94597adc2d891a921c0bf51c9/AmazonMusicInstaller.exe",
            sha256="d863b2a2ad55c7c5f07f818f1d54ac51a7e3457dc28aba8b78da197d658d90cc",
            size=89754336,
            whose="Amazon (cloudfront.net)",
            page="https://www.amazon.com/music/download",
            folder="",
        ),
    ),
)


def find(key: str) -> Optional[CatalogApp]:
    return next((c for c in CATALOG if c.key == key), None)


def get(item: CatalogApp, report=lambda *a, **k: None,
        cancel: Optional[threading.Event] = None) -> apps.App:
    """The installed app: already there, or downloaded, checked and installed now."""
    existing = apps.load(item.key)
    if existing is not None:
        return existing

    def progress(stage: str, done: int, total: int) -> None:
        report('progress.' + stage, done=done, total=total, name=item.name)

    try:
        path = fetch.download(item.installer, progress, cancel)
    except FetchError as exc:
        raise apps.RunError(Problem(f'error.fetch_{exc.kind}', {'detail': exc.detail})) from exc
    app = apps.install(path, report, name=item.name, mode='installer', cancel=cancel,
                       silent=item.silent)
    if app.slug != item.key:
        # the slug is the menu entry's name; a leftover folder made it 'amazon-music-2'
        apps.uninstall(app)
        raise apps.RunError(Problem('error.nothing_installed', {'code': '0'}))
    return app
