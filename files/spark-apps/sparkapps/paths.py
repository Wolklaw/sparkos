"""Every path Spark Apps uses, under an optional root folder (tests use a temp folder)."""

import os
import re

SLUG_RE = re.compile(r'^spark-[a-z0-9]+(-[a-z0-9]+)*$')
VERSION_RE = re.compile(r'^\d{1,6}(\.\d{1,6}){1,3}$')


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and len(slug) <= 40 and SLUG_RE.fullmatch(slug) is not None


def version_key(version):
    """'1.10.0' -> (1, 10, 0, 0). Raises ValueError for anything but a plain dotted number."""
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError(f"not a version: {version!r}")
    parts = [int(p) for p in version.split('.')]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


class Paths:
    def __init__(self, root: str = '/'):
        self.root = root

    def _p(self, path: str) -> str:
        return path if self.root in ('', '/') else os.path.join(self.root, path.lstrip('/'))

    @property
    def state_dir(self) -> str:        # root-owned: the live copies and state.json
        return self._p('/var/lib/spark-apps')

    @property
    def state_file(self) -> str:
        return os.path.join(self.state_dir, 'state.json')

    @property
    def lock_file(self) -> str:
        return os.path.join(self.state_dir, '.lock')

    @property
    def image_dir(self) -> str:        # from the image (/usr): what each built-in app is
        return self._p('/usr/share/spark-apps')

    @property
    def key(self) -> str:              # the public key the index is checked against
        return os.path.join(self.image_dir, 'index-key.pub')

    @property
    def conf(self) -> str:
        return self._p('/etc/sparkos/update.conf')

    def image_record(self, slug: str) -> str:
        return os.path.join(self.image_dir, slug + '.json')

    def builtin(self, slug: str) -> str:
        return self._p('/usr/lib/' + slug)

    def app_dir(self, slug: str) -> str:
        return os.path.join(self.state_dir, slug)

    def version_dir(self, slug: str, version: str) -> str:
        return os.path.join(self.state_dir, slug, version)
