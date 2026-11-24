import json
import os

from helpers import Fixture
from sparkapps.choose import select


class ChooseTests(Fixture):
    def pick(self, slug='spark-calc'):
        return select(self.paths, slug, trusted_uid=self.whoami())

    def test_no_live_copy_means_builtin(self):
        self.image_app()
        choice = self.pick()
        self.assertEqual((choice.source, choice.directory),
                         ('builtin', self.paths.builtin('spark-calc')))

    def test_newer_live_copy_wins(self):
        self.image_app(version='1.0.0')
        folder = self.install_live('spark-calc', '1.0.1')
        choice = self.pick()
        self.assertEqual((choice.source, choice.directory, choice.version),
                         ('live', folder, '1.0.1'))

    def test_builtin_as_new_or_newer(self):
        self.image_app(version='1.0.1')
        self.install_live('spark-calc', '1.0.1')
        self.assertEqual(self.pick().source, 'builtin')
        self.image_app(version='1.1.0')
        self.assertEqual(self.pick().source, 'builtin')

    def test_ten_is_newer_than_nine(self):
        self.image_app(version='1.9.0')
        self.install_live('spark-calc', '1.10.0')
        self.assertEqual(self.pick().source, 'live')

    def test_system_api_mismatch(self):
        self.image_app(api=2)
        self.install_live('spark-calc', '1.0.1', api=1)
        choice = self.pick()
        self.assertEqual(choice.source, 'builtin')
        self.assertIn('system_api', choice.why)

    def test_manifest_version_must_match_the_folder(self):
        self.image_app()
        folder = self.install_live('spark-calc', '1.0.1')
        with open(os.path.join(folder, 'spark-app.json'), 'w') as f:
            json.dump({'version': '1.0.9', 'system_api': 1}, f)
        self.assertEqual(self.pick().source, 'builtin')

    def test_use_builtin_setting(self):
        self.image_app()
        self.install_live('spark-calc', '1.0.1', state_use='builtin')
        self.assertEqual(self.pick().source, 'builtin')

    def test_app_that_does_not_take_updates(self):
        self.image_app(live=False)
        self.install_live('spark-calc', '1.0.1')
        self.assertEqual(self.pick().source, 'builtin')

    def test_not_owned_by_the_trusted_user(self):
        self.image_app()
        self.install_live('spark-calc', '1.0.1')
        self.assertEqual(select(self.paths, 'spark-calc', trusted_uid=self.whoami() + 1).source,
                         'builtin')

    def test_group_or_world_writable_folder(self):
        self.image_app()
        folder = self.install_live('spark-calc', '1.0.1')
        os.chmod(folder, 0o775)
        self.assertEqual(self.pick().source, 'builtin')
        os.chmod(folder, 0o755)
        os.chmod(self.paths.state_dir, 0o777)
        self.assertEqual(self.pick().source, 'builtin')

    def test_symlinked_folder(self):
        self.image_app()
        folder = self.install_live('spark-calc', '1.0.1')
        moved = folder + '.real'
        os.rename(folder, moved)
        os.symlink(moved, folder)
        self.assertEqual(self.pick().source, 'builtin')

    def test_missing_entry_file(self):
        self.image_app()
        folder = self.install_live('spark-calc', '1.0.1')
        os.unlink(os.path.join(folder, 'spark_calc.py'))
        self.assertEqual(self.pick().source, 'builtin')

    def test_broken_state_never_raises(self):
        self.image_app()
        self.install_live('spark-calc', '1.0.1')
        for text in ('', '{', '[]', '{"apps": 5}', '{"apps": {"spark-calc": {"active": 5}}}'):
            with open(self.paths.state_file, 'w') as f:
                f.write(text)
            self.assertEqual(self.pick().source, 'builtin', text)

    def test_bad_slug(self):
        self.assertEqual(select(self.paths, '../etc', trusted_uid=0).source, 'builtin')
