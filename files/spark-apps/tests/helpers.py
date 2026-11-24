"""Shared test helpers: throwaway keys (openssl), signed indexes, bundles, a fake image root."""

import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'ci'))

from sparkapps import INDEX_TYPE, URL_PREFIX, index as index_mod    # noqa: E402
from sparkapps.paths import Paths                                   # noqa: E402

OPENSSL = shutil.which('openssl') or '/usr/bin/openssl'
HAVE_OPENSSL = os.path.exists(index_mod.OPENSSL)
NOW = 1_800_000_000.0           # a fixed "now" for the tests


def openssl(*args, data=None):
    return subprocess.run([OPENSSL, *args], input=data, capture_output=True, check=True).stdout


def make_key(folder, name):
    private, public = os.path.join(folder, name + '.key'), os.path.join(folder, name + '.pub')
    openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', private)
    openssl('pkey', '-in', private, '-pubout', '-out', public)
    return private, public


def sign_text(private, text):
    """What `cosign sign-blob --output-signature` writes: base64 of a DER ECDSA/SHA-256 signature."""
    path = private + '.payload'
    with open(path, 'wb') as f:
        f.write(text.encode('utf-8'))
    return base64.b64encode(openssl('dgst', '-sha256', '-sign', private, path)).decode()


def bundle_bytes(files, extra=None):
    """A .tar.gz of {name: bytes}; extra is a list of ready TarInfo (+ optional data) members."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info, data in extra or []:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return raw.getvalue()


def app_files(slug, version, api=1, extra=None):
    manifest = {'slug': slug, 'version': version, 'live_update': True, 'system_api': api}
    files = {'spark-app.json': json.dumps(manifest).encode(),
             slug.replace('-', '_') + '.py': f"VERSION = {version!r}\n".encode()}
    files.update(extra or {})
    return files


def entry_for(slug, version, data, api=1, url=None):
    return {'version': version, 'system_api': api,
            'url': url or f"{URL_PREFIX}app-{slug}-{version}/{slug}-{version}.tar.gz",
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}


def payload_text(apps, serial=1, issued=NOW - 100, expires=NOW + 86400 * 30):
    return json.dumps({'type': INDEX_TYPE, 'format': 1, 'serial': serial,
                       'issued': index_mod.format_date(issued),
                       'expires': index_mod.format_date(expires), 'apps': apps})


def signed_index(private, apps, **kw):
    text = payload_text(apps, **kw)
    return index_mod.make_envelope(text, sign_text(private, text)).encode()


class Fixture(unittest.TestCase):
    """A temp "machine": a root folder with the image side (/usr/share/spark-apps) filled in."""

    @classmethod
    def setUpClass(cls):
        cls.keydir = tempfile.mkdtemp(prefix='spark-apps-keys-')
        cls.priv, cls.pub = make_key(cls.keydir, 'good')
        cls.priv2, cls.pub2 = make_key(cls.keydir, 'other')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.keydir, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-apps-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = Paths(self.tmp)
        os.makedirs(self.paths.image_dir)
        shutil.copy(self.pub, self.paths.key)

    def image_app(self, slug='spark-calc', version='1.0.0', api=1, live=True):
        manifest = {'slug': slug, 'version': version, 'system_api': api}
        if live:
            manifest['live_update'] = True
        with open(self.paths.image_record(slug), 'w') as f:
            json.dump(manifest, f)
        os.makedirs(self.paths.builtin(slug), exist_ok=True)

    def install_live(self, slug, version, api=1, state_use='live', previous=None):
        """Put a live copy where the store would have, and name it in state.json."""
        folder = self.paths.version_dir(slug, version)
        os.makedirs(folder)
        for name, data in app_files(slug, version, api).items():
            with open(os.path.join(folder, name), 'wb') as f:
                f.write(data)
        os.makedirs(self.paths.state_dir, exist_ok=True)
        state = {'apps': {slug: {'active': version, 'use': state_use, 'previous': previous}}}
        with open(self.paths.state_file, 'w') as f:
            json.dump(state, f)
        return folder

    def whoami(self):
        return os.getuid()
