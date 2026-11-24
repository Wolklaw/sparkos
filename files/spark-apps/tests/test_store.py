import json
import os
import unittest

from helpers import (HAVE_OPENSSL, NOW, Fixture, app_files, bundle_bytes, entry_for,
                     signed_index)
from sparkapps import fetch as fetch_mod, store
from sparkapps.choose import select


class FakeNet:
    """Stands in for fetch.fetch: url -> bytes, or an exception."""

    def __init__(self, files):
        self.files = files
        self.asked = []

    def __call__(self, url, max_bytes, out=None, **kw):
        self.asked.append(url)
        got = self.files.get(url)
        if got is None:
            raise fetch_mod.FetchError("can't download: no route", offline=True)
        if isinstance(got, Exception):
            raise got
        if len(got) > max_bytes:
            raise fetch_mod.FetchError("the download is bigger than the limit")
        if out is not None:
            out.write(got)
            return b''
        return got


INDEX_URL = 'https://index.test/index.json'


@unittest.skipUnless(HAVE_OPENSSL, 'needs /usr/bin/openssl')
class StoreTests(Fixture):
    slug = 'spark-calc'

    def setUp(self):
        super().setUp()
        self.image_app(self.slug, '1.0.0', 1)

    def release(self, version, api=1, files=None, serial=1, key=None, **entry):
        data = bundle_bytes(files if files is not None else app_files(self.slug, version, api))
        e = entry_for(self.slug, version, data, api)
        e.update(entry)
        return data, e, serial

    def net(self, *releases, key=None, serial=None):
        apps, files = {}, {}
        for data, e, ser in releases:
            apps[self.slug] = e
            files[e['url']] = data
            serial = serial or ser
        files[INDEX_URL] = signed_index(key or self.priv, apps, serial=serial or 1)
        return FakeNet(files)

    def update(self, net, **kw):
        return store.run_update(self.paths, index_url=INDEX_URL, now=NOW, fetcher=net,
                                compile_pyc=False, **kw)

    def state(self):
        return store.load_state(self.paths)

    def pick(self):
        return select(self.paths, self.slug, trusted_uid=self.whoami())

    # --- install ---

    def test_installs_a_newer_version(self):
        results = self.update(self.net(self.release('1.0.1')))
        self.assertEqual(results, {self.slug: 'installed'})
        self.assertEqual(self.state()['apps'][self.slug]['active'], '1.0.1')
        self.assertEqual(self.state()['last_result'], 'ok')
        choice = self.pick()
        self.assertEqual((choice.source, choice.version), ('live', '1.0.1'))
        self.assertEqual(oct(os.stat(choice.directory).st_mode & 0o777), '0o755')

    def test_current_and_older_versions_are_not_installed(self):
        for version in ('1.0.0', '0.9.0'):
            net = self.net(self.release(version))
            self.assertEqual(self.update(net), {self.slug: 'current'})
            self.assertEqual(net.asked, [INDEX_URL], "no bundle downloaded")

    def test_second_run_does_nothing(self):
        net = self.net(self.release('1.0.1'))
        self.update(net)
        net.asked.clear()
        self.assertEqual(self.update(net), {self.slug: 'current'})
        self.assertEqual(net.asked, [INDEX_URL])

    def test_keeps_previous_and_prunes_the_rest(self):
        for version, serial in (('1.0.1', 1), ('1.0.2', 2), ('1.0.3', 3)):
            self.update(self.net(self.release(version, serial=serial)))
        self.assertEqual(sorted(os.listdir(self.paths.app_dir(self.slug))), ['1.0.2', '1.0.3'])
        app = self.state()['apps'][self.slug]
        self.assertEqual((app['active'], app['previous']), ('1.0.3', '1.0.2'))

    def test_nothing_left_in_the_stage_folder(self):
        self.update(self.net(self.release('1.0.1')))
        self.assertEqual([n for n in os.listdir(self.paths.state_dir) if n.startswith('.stage')],
                         [])

    # --- refusals ---

    def test_sha_mismatch(self):
        data, e, ser = self.release('1.0.1')
        evil = bundle_bytes(app_files(self.slug, '1.0.1', 1, {'extra.py': b'evil'}))
        net = self.net((data, e, ser))
        net.files[e['url']] = evil
        e['size'] = len(evil)
        net.files[INDEX_URL] = signed_index(self.priv, {self.slug: e})
        results = self.update(net)
        self.assertEqual(results, {self.slug: 'failed'})
        self.assertIn('sha256', self.state()['apps'][self.slug]['last_error'])
        self.assertEqual(self.pick().source, 'builtin')
        self.assertFalse(os.path.exists(self.paths.app_dir(self.slug)))

    def test_size_mismatch(self):
        results = self.update(self.net(self.release('1.0.1', size=5)))
        self.assertEqual(results, {self.slug: 'failed'})

    def test_bad_index_signature(self):
        net = self.net(self.release('1.0.1'), key=self.priv2)
        self.assertEqual(self.update(net), {})
        self.assertEqual(self.state()['last_result'], 'refused')
        self.assertEqual(net.asked, [INDEX_URL], "no bundle downloaded")
        self.assertEqual(self.pick().source, 'builtin')

    def test_rollback_serial_is_refused(self):
        self.update(self.net(self.release('1.0.1', serial=5)))
        results = self.update(self.net(self.release('1.0.2', serial=4)))
        self.assertEqual(results, {})
        self.assertEqual(self.state()['last_result'], 'refused')
        self.assertEqual(self.state()['apps'][self.slug]['active'], '1.0.1')
        self.assertEqual(self.state()['serial'], 5)

    def test_expired_index_is_refused(self):
        net = self.net(self.release('1.0.1'))
        results = store.run_update(self.paths, index_url=INDEX_URL, now=NOW + 86400 * 400,
                                   fetcher=net, compile_pyc=False)
        self.assertEqual(results, {})
        self.assertEqual(self.state()['last_result'], 'refused')

    def test_system_api_mismatch_waits_for_the_os(self):
        net = self.net(self.release('2.0.0', api=2))
        self.assertEqual(self.update(net), {self.slug: 'needs-os'})
        self.assertEqual(net.asked, [INDEX_URL])
        self.assertEqual(self.state()['apps'][self.slug]['waiting'], 'needs-os')
        self.assertEqual(self.pick().source, 'builtin')

    def test_bundle_lying_about_its_api(self):
        files = app_files(self.slug, '1.0.1', api=2)           # index says 1, manifest says 2
        results = self.update(self.net(self.release('1.0.1', files=files)))
        self.assertEqual(results, {self.slug: 'failed'})

    def test_bundle_for_another_app_or_version(self):
        for files in (app_files('spark-edit', '1.0.1'), app_files(self.slug, '1.0.9')):
            self.assertEqual(self.update(self.net(self.release('1.0.1', files=files))),
                             {self.slug: 'failed'})

    def test_bundle_with_a_path_trick(self):
        files = app_files(self.slug, '1.0.1', 1, {'../../escape': b'x'})
        self.assertEqual(self.update(self.net(self.release('1.0.1', files=files))),
                         {self.slug: 'failed'})
        self.assertFalse(os.path.exists(os.path.join(self.paths.state_dir, '..', 'escape')))

    def test_app_not_in_this_image(self):
        os.unlink(self.paths.image_record(self.slug))
        self.assertEqual(self.update(self.net(self.release('1.0.1'))), {self.slug: 'not-live'})

    def test_offline_is_quiet(self):
        self.assertEqual(self.update(FakeNet({})), {})
        self.assertEqual(self.state()['last_result'], 'offline')

    def test_failed_bundle_download_keeps_the_old_copy(self):
        self.update(self.net(self.release('1.0.1', serial=1)))
        data, e, _ = self.release('1.0.2')
        net = self.net((data, e, 2))
        net.files[e['url']] = fetch_mod.FetchError("the server answered 503", offline=True)
        self.assertEqual(self.update(net), {self.slug: 'failed'})
        self.assertEqual(self.pick().version, '1.0.1')

    # --- roll back ---

    def test_use_builtin_and_back(self):
        self.update(self.net(self.release('1.0.1')))
        store.use_builtin(self.paths, self.slug)
        self.assertEqual(self.pick().source, 'builtin')
        net = self.net(self.release('1.0.2', serial=2))
        self.assertEqual(self.update(net), {self.slug: 'held'}, "updates leave it alone")
        store.use_live(self.paths, self.slug)
        self.assertEqual(self.pick().version, '1.0.1')
        self.assertEqual(self.update(net), {self.slug: 'installed'})
        self.assertEqual(self.pick().version, '1.0.2')

    def test_use_previous(self):
        self.update(self.net(self.release('1.0.1', serial=1)))
        self.update(self.net(self.release('1.0.2', serial=2)))
        store.use_previous(self.paths, self.slug)
        self.assertEqual(self.pick().version, '1.0.1')
        self.assertEqual(os.listdir(self.paths.app_dir(self.slug)), ['1.0.1'])
        # the version just left is not installed again
        self.assertEqual(self.update(self.net(self.release('1.0.2', serial=3))),
                         {self.slug: 'current'})
        # a newer one is
        self.assertEqual(self.update(self.net(self.release('1.0.3', serial=4))),
                         {self.slug: 'installed'})

    def test_use_previous_without_one(self):
        self.update(self.net(self.release('1.0.1')))
        with self.assertRaises(store.StoreError):
            store.use_previous(self.paths, self.slug)

    def test_bad_slug_is_refused(self):
        for call in (store.use_builtin, store.use_live, store.use_previous):
            with self.assertRaises(store.StoreError):
                call(self.paths, '../../etc')

    # --- after an OS update ---

    def test_image_catches_up(self):
        self.update(self.net(self.release('1.0.1')))
        self.image_app(self.slug, '1.0.1', 1)                 # the next image has 1.0.1 built in
        self.update(self.net(self.release('1.0.1', serial=2)))
        self.assertFalse(os.path.exists(self.paths.app_dir(self.slug)))
        self.assertEqual(self.pick().source, 'builtin')

    def test_image_changes_system_api(self):
        self.update(self.net(self.release('1.0.1')))
        self.image_app(self.slug, '1.0.0', 2)
        self.update(self.net(self.release('1.0.1', serial=2)))
        self.assertFalse(os.path.exists(self.paths.app_dir(self.slug)))
        self.assertEqual(self.pick().source, 'builtin')

    def test_unknown_folders_are_removed(self):
        os.makedirs(self.paths.version_dir(self.slug, '9.9.9'))
        os.makedirs(os.path.join(self.paths.state_dir, '.stage-leftover'))
        self.update(self.net(self.release('1.0.0')))
        self.assertFalse(os.path.exists(self.paths.version_dir(self.slug, '9.9.9')))
        self.assertFalse(os.path.exists(os.path.join(self.paths.state_dir, '.stage-leftover')))

    # --- settings ---

    def test_automatic_setting(self):
        self.assertTrue(store.automatic_enabled(self.paths))
        os.makedirs(os.path.dirname(self.paths.conf))
        for text, want in (('automatic = no\n', False), ('# automatic = no\n', True),
                           ('automatic=yes\n', True), ('automatic = "off"\n', False)):
            with open(self.paths.conf, 'w') as f:
                f.write(text)
            self.assertEqual(store.automatic_enabled(self.paths), want, text)


if __name__ == '__main__':
    unittest.main()
