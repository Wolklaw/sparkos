"""The whole path on one machine, in a temp root: the real release tooling (ci/appindex.py)
builds a bundle from a real app's `install.sh --stage` and signs the index with a throwaway key,
a local http server (test-only: allow_http is a function argument, nothing outside can set it)
serves it, and the root-side code installs it and the launcher picks it."""

import base64
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

import appindex
from helpers import HAVE_OPENSSL, NOW, ROOT, Fixture, openssl, sign_text
from sparkapps import fetch as fetch_mod, index as index_mod, store
from sparkapps.choose import select

REPO = os.path.dirname(os.path.dirname(ROOT))
APP = os.path.join(REPO, 'files', 'spark-calc')


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(HAVE_OPENSSL and os.path.isdir(APP), 'needs openssl and the spark-calc app')
class EndToEnd(Fixture):
    def setUp(self):
        super().setUp()
        self.web = os.path.join(self.tmp, 'web')
        os.makedirs(self.web)
        handler = functools.partial(Quiet, directory=self.web)
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        manifest = read_json(os.path.join(APP, 'spark-app.json'))
        self.slug, self.version = manifest['slug'], manifest['version']
        self.image_app(self.slug, self.version, manifest['system_api'])

    def release(self, version, serial, key=None, days=30, now=None):
        """Build + sign + publish (into the web folder) the way the workflow does."""
        stage = os.path.join(self.tmp, 'stage-' + version)
        shutil.rmtree(stage, ignore_errors=True)
        subprocess.run(['bash', os.path.join(APP, 'install.sh'), '--stage', stage],
                       check=True, capture_output=True)
        manifest_path = os.path.join(stage, 'spark-app.json')
        manifest = read_json(manifest_path)
        manifest['version'] = version
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
        bundle = os.path.join(self.web, f'{self.slug}-{version}.tar.gz')
        appindex.build_bundle(stage, bundle)
        data = read_bytes(bundle)
        entries = {self.slug: {'version': version, 'system_api': manifest['system_api'],
                               'url': f"{self.base}/{self.slug}-{version}.tar.gz",
                               'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}}
        current = os.path.join(self.web, 'index.json')
        payload = appindex.make_payload(appindex.read_current(current), entries,
                                        now=now or NOW - 60, days=days)
        # the real index checks need the real url prefix; the test serves from localhost, so
        # check the rest of the payload the same way and sign it as-is
        text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
        with open(current, 'w') as f:
            f.write(index_mod.make_envelope(text, sign_text(key or self.priv, text)))
        return bundle

    def update(self):
        # the production URL_PREFIX check applies to real indexes; point it at the test server
        from sparkapps import index
        old = index.URL_PREFIX
        index.URL_PREFIX = self.base + '/'
        self.addCleanup(setattr, index, 'URL_PREFIX', old)
        return store.run_update(self.paths, index_url=self.base + '/index.json',
                                allow_http=True, now=NOW, compile_pyc=True)

    def test_release_install_launch_roll_back(self):
        newer = self.version.split('.')
        newer[-1] = str(int(newer[-1]) + 1)
        newer = '.'.join(newer)
        self.release(newer, 1)
        self.assertEqual(self.update(), {self.slug: 'installed'})
        choice = select(self.paths, self.slug, trusted_uid=os.getuid())
        self.assertEqual((choice.source, choice.version), ('live', newer))
        self.assertTrue(os.path.isfile(os.path.join(choice.directory, 'spark_calc.py')))
        self.assertTrue(any(n.endswith('.pyc') for _, _, names in os.walk(choice.directory)
                            for n in names), "root compiled the bytecode")
        store.use_builtin(self.paths, self.slug)
        self.assertEqual(select(self.paths, self.slug, trusted_uid=os.getuid()).source, 'builtin')

    def test_second_release_then_bad_key(self):
        v1, v2 = self.version, '99.0.0'
        self.release('98.0.0', 1)
        self.assertEqual(self.update(), {self.slug: 'installed'})
        self.release(v2, 2, key=self.priv2)                  # signed with the wrong key
        self.assertEqual(self.update(), {})
        self.assertEqual(store.load_state(self.paths)['last_result'], 'refused')
        self.assertEqual(select(self.paths, self.slug, trusted_uid=os.getuid()).version, '98.0.0')
        self.assertTrue(v1)

    def test_deterministic_bundle(self):
        a = self.release('98.0.0', 1)
        first = read_bytes(a)
        os.unlink(a)
        self.release('98.0.0', 1)
        self.assertEqual(read_bytes(a), first)

    def test_fetch_refuses_plain_http_by_default(self):
        with self.assertRaises(fetch_mod.FetchError):
            fetch_mod.fetch(self.base + '/index.json', 1000)

    def test_fetch_size_cap(self):
        self.release('98.0.0', 1)
        with self.assertRaises(fetch_mod.FetchError):
            fetch_mod.fetch(self.base + '/index.json', 10, allow_http=True)

    def test_tools(self):
        """appindex.py as the workflow calls it."""
        self.release(self.version, 1)
        tool = os.path.join(ROOT, 'ci', 'appindex.py')
        out = subprocess.run([sys.executable, tool, 'changed', '--apps-dir',
                              os.path.join(REPO, 'files'), '--index',
                              os.path.join(self.web, 'index.json')],
                             capture_output=True, text=True, check=True).stdout
        changed = json.loads(out)
        self.assertNotIn(self.slug, changed, "its version is released: spark-calc isn't changed")
        self.assertTrue(set(changed) <= {'spark-calc', 'spark-edit', 'spark-emoji', 'spark-space',
                                         'spark-notes', 'spark-clock', 'spark-fonts', 'spark-boxes',
                                         'spark-clips', 'spark-tray'})
        none = subprocess.run([sys.executable, tool, 'changed', '--apps-dir',
                               os.path.join(REPO, 'files'), '--index', 'none'],
                              capture_output=True, text=True, check=True).stdout
        self.assertIn(self.slug, json.loads(none))

    def test_release_pipeline_as_the_workflow_runs_it(self):
        """build -> payload -> sign -> envelope -> verify, with the real url prefix, for every
        opted-in app, twice (the second run carries the first's entries over, serial + 1)."""
        tool = [sys.executable, os.path.join(ROOT, 'ci', 'appindex.py')]
        files = os.path.join(REPO, 'files')
        out = os.path.join(self.tmp, 'out')

        def run(*args):
            return subprocess.run([*tool, *args], capture_output=True, text=True, check=True)

        slugs = json.loads(run('changed', '--apps-dir', files, '--index', 'none').stdout)
        self.assertEqual(sorted(slugs), ['spark-boxes', 'spark-calc', 'spark-clips', 'spark-clock', 'spark-edit',
                                         'spark-emoji', 'spark-fonts', 'spark-notes',
                                         'spark-space', 'spark-tray'])
        run('build', '--apps-dir', files, '--out', out, *slugs)
        index = os.path.join(self.tmp, 'index.json')
        serial = 0
        for round_ in (1, 2):
            payload, sig = os.path.join(self.tmp, 'payload.json'), os.path.join(self.tmp, 'sig')
            run('payload', '--index', index if round_ > 1 else 'none', '--entries',
                os.path.join(out, 'entries.json'), '--out', payload,
                '--now', str(int(time.time())))
            with open(payload, encoding='utf-8') as f:
                text = f.read()
            with open(sig, 'w') as f:
                f.write(sign_text(self.priv, text) + "\n")
            run('envelope', '--payload', payload, '--signature', sig, '--out', index)
            said = run('verify', '--index', index, '--key', self.pub).stdout
            serial += 1
            self.assertIn(f"serial {serial}, 10 app(s)", said)
        with open(os.path.join(out, 'entries.json'), encoding='utf-8') as f:
            entries = json.load(f)
        for slug, entry in entries.items():
            self.assertTrue(entry['url'].startswith(
                f"https://github.com/Wolklaw/sparkos/releases/download/app-{slug}-"))
            bundle = os.path.join(out, f"{slug}-{entry['version']}.tar.gz")
            self.assertEqual(hashlib.sha256(read_bytes(bundle)).hexdigest(), entry['sha256'])

    def test_openssl_and_sign_blob_format(self):
        """cosign sign-blob writes base64(DER ECDSA over SHA-256); this is that, made with
        openssl, checked the way clients check it."""
        sig = sign_text(self.priv, 'hello')
        index_mod.verify_signature(b'hello', sig, self.pub)
        with self.assertRaises(index_mod.IndexError_):
            index_mod.verify_signature(b'hellO', sig, self.pub)
        der = base64.b64decode(sig)
        self.assertEqual(der[0], 0x30, "a DER SEQUENCE, as cosign writes it")
        self.assertIn(b'SEQUENCE', openssl('asn1parse', '-inform', 'DER', data=der))


if __name__ == '__main__':
    unittest.main()
