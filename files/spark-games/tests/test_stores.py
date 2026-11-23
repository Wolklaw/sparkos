"""Tests for the stores (Epic, GOG, Amazon), the helper-process installs, and the added
launchers. They use fake clients (tests/fixtures/clients) that print recorded output: no
network, no accounts. The real legendary, gogdl and nile were never run in these tests.

    python -m unittest discover -s files/spark-games/tests -v
"""

import hashlib
import io
import json
import logging
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
os.environ['SPARK_LANG'] = 'en'

from sparkgames import (clients, fixtures, jobs, launch, launchers, library, registry,  # noqa: E402
                        stores, strings)
from sparkgames.core import Game, data_dir  # noqa: E402

TOKEN = 'fake-secret-token-123'
ENV_NAMES = ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME',
             'SPARK_GAMES_LEGENDARY', 'SPARK_GAMES_GOGDL', 'SPARK_GAMES_NILE',
             'FAKE_CLIENT_LOG', 'FAKE_FAIL', 'FAKE_SLOW')


def fake_which(*present):
    return lambda name: f'/usr/bin/{name}' if name in present else None


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class StoreCase(unittest.TestCase):
    """A scratch home, XDG folders and fake clients for each test."""

    def setUp(self):
        self.saved = {n: os.environ.get(n) for n in ENV_NAMES}
        self.tmp = tempfile.mkdtemp(prefix='spark-games-stores-')
        for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
            os.environ[var] = os.path.join(self.tmp, var.lower())
        bin_dir = os.path.join(self.tmp, 'bin')
        shutil.copytree(os.path.join(HERE, 'fixtures', 'clients'), bin_dir)
        for name in ('legendary', 'gogdl', 'nile'):
            os.chmod(os.path.join(bin_dir, name), 0o755)
            os.environ[f'SPARK_GAMES_{name.upper()}'] = os.path.join(bin_dir, name)
        self.calls = os.path.join(self.tmp, 'calls.log')
        os.environ['FAKE_CLIENT_LOG'] = self.calls
        os.environ.pop('FAKE_FAIL', None)
        os.environ.pop('FAKE_SLOW', None)
        self.home = fixtures.materialize(os.path.join(self.tmp, 'home'))
        self.handler = ListHandler()
        logging.getLogger('spark-games').addHandler(self.handler)
        logging.getLogger('spark-games').setLevel(logging.INFO)

    def tearDown(self):
        logging.getLogger('spark-games').removeHandler(self.handler)
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls_made(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls) as f:
            return [json.loads(line) for line in f if line.strip()]

    def sign_in_epic(self):
        self.assertEqual(stores.finish_signin('epic', json.dumps(
            {'authorizationCode': 'a' * 32, 'redirectUrl': 'x'})), '')

    def make_heroic_dirs(self):
        for sub in ('Celeste', 'The Witcher Enhanced Edition', 'Amazon Example'):
            os.makedirs(os.path.join(self.home, 'Games', 'Heroic', sub), exist_ok=True)

    def tree(self, folder):
        out = {}
        for root, dirs, files in os.walk(folder):
            for name in dirs + files:
                path = os.path.join(root, name)
                out[path] = os.lstat(path).st_mtime_ns
        return out

    def run_job(self, **spec):
        spec.setdefault('id', jobs.new_id())
        return spec['id'], jobs.run_job(spec)

    def wait_for(self, job_id, states, timeout=20):
        end = time.time() + timeout
        job = None
        while time.time() < end:
            job = jobs.read_job(job_id)
            if job and job['state'] in states:
                return job
            time.sleep(0.1)
        self.fail(f'job stayed {job and job["state"]}, wanted {states}')


class CodeTests(unittest.TestCase):
    def test_epic_codes(self):
        code = 'b' * 32
        self.assertEqual(stores.extract_code('epic', json.dumps({'authorizationCode': code})), code)
        self.assertEqual(stores.extract_code('epic', code), code)
        self.assertEqual(stores.extract_code('epic', f' "{code}" '), code)
        self.assertEqual(stores.extract_code('epic', f'{{"redirectUrl":"x", "authorizationCode":"{code}"}}'),
                         code)
        self.assertEqual(stores.extract_code('epic', 'hello world'), '')
        self.assertEqual(stores.extract_code('epic', ''), '')

    def test_gog_and_amazon_codes(self):
        url = 'https://embed.gog.com/on_login_success?origin=client&code=abc123DEF456ghi789'
        self.assertEqual(stores.extract_code('gog', url), 'abc123DEF456ghi789')
        self.assertEqual(stores.extract_code('gog', 'abc123DEF456ghi789'), 'abc123DEF456ghi789')
        self.assertEqual(stores.extract_code('gog', 'https://example.com/?nothing=1'), '')
        amazon = ('https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=ANabcdef'
                  '%2Bxyz&openid.mode=x')
        self.assertEqual(stores.extract_code('amazon', amazon), 'ANabcdef+xyz')
        self.assertEqual(stores.extract_code('amazon', 'short'), '')

    def test_scrub_hides_tokens(self):
        text = stores.scrub('failed -AUTH_PASSWORD=abc123 and access_token: "zzz" ok')
        self.assertNotIn('abc123', text)
        self.assertNotIn('zzz', text)
        self.assertIn('ok', text)


class SignInTests(StoreCase):
    def test_epic_sign_in_out_and_modes(self):
        self.assertFalse(stores.signed_in('epic'))
        self.assertEqual(stores.finish_signin('epic', 'not a code'), 'signin_bad_code')
        self.assertEqual(stores.finish_signin('epic', 'bad' + 'x' * 25), 'signin_failed')
        self.sign_in_epic()
        self.assertTrue(stores.signed_in('epic'))
        self.assertEqual(stores.account_name('epic'), 'Fake Player')
        accounts = os.path.join(self.tmp, 'xdg_config_home', 'spark-games', 'accounts')
        self.assertEqual(stat.S_IMODE(os.stat(accounts).st_mode), 0o700)
        user = os.path.join(accounts, 'epic', 'user.json')
        self.assertEqual(stat.S_IMODE(os.stat(user).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(user)).st_mode), 0o700)
        stores.sign_out('epic')
        self.assertFalse(stores.signed_in('epic'))

    def test_no_token_or_code_in_the_log(self):
        code = 'c' * 32
        stores.finish_signin('epic', code)
        stores.refresh_owned('epic', force=True)
        text = '\n'.join(self.handler.lines)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(code, text)

    def test_gog_sign_in(self):
        self.assertEqual(stores.finish_signin(
            'gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789'),
            '')
        self.assertTrue(stores.signed_in('gog'))
        path = clients.gog_auth_file()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        argv = self.calls_made()[0]
        self.assertEqual(argv[:2], ['gogdl', '--auth-config-path'])

    def test_amazon_sign_in(self):
        pending = stores.begin_signin('amazon')
        self.assertTrue(pending['url'].startswith('https://www.amazon.com/'))
        self.assertEqual(pending['state']['code_verifier'], 'verifier')
        url = 'https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=ANabcdefghij0123'
        self.assertEqual(stores.finish_signin('amazon', url, pending['state']), '')
        self.assertTrue(stores.signed_in('amazon'))
        self.assertEqual(stores.account_name('amazon'), 'Fake Amazon')
        register = [c for c in self.calls_made() if c[1] == 'register'][0]
        self.assertIn('verifier', register)
        stores.sign_out('amazon')
        self.assertFalse(stores.signed_in('amazon'))


class OwnedTests(StoreCase):
    def test_epic_owned_cached_and_updates(self):
        self.sign_in_epic()
        registry.add_game('epic:Sugar', {'store': 'epic', 'app': 'Sugar', 'title': 'Celeste',
                                         'path': '/x', 'version': '1.4.0.0', 'via': 'heroic'})
        data = stores.refresh_owned('epic')
        self.assertEqual([g['app'] for g in data['games']], ['Sugar', 'Fox'])   # no Mac-only, no UE sample
        self.assertEqual(data['updates'], ['Sugar'])
        self.assertEqual(data['games'][0]['art'], 'https://cdn.example.invalid/celeste.jpg')
        before = len([c for c in self.calls_made() if c[0] == 'legendary' and 'list' in c])
        stores.refresh_owned('epic')                       # fresh cache: no client call
        after = len([c for c in self.calls_made() if c[0] == 'legendary' and 'list' in c])
        self.assertEqual(before, after)
        stores.refresh_owned('epic', force=True)           # F5
        self.assertEqual(len([c for c in self.calls_made() if 'list' in c]), after + 1)
        self.assertFalse(stores.owned_stale('epic'))
        stale = stores.load_owned('epic')
        stale['fetched'] -= 2 * 24 * 3600
        with open(stores.owned_path('epic'), 'w') as f:
            json.dump(stale, f)
        self.assertTrue(stores.owned_stale('epic'))

    def test_not_signed_in_raises(self):
        with self.assertRaises(clients.ClientError) as ctx:
            stores.refresh_owned('epic', force=True)
        self.assertEqual(ctx.exception.kind, 'signin')

    def test_gog_owned_from_the_account_api(self):
        stores.finish_signin('gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789')
        pages = {1: {'totalPages': 2, 'products': [
            {'id': 1207658930, 'title': 'The Witcher', 'image': '//images.gog.example/abc',
             'worksOn': {'Windows': True, 'Linux': True, 'Mac': False}}]},
                 2: {'totalPages': 2, 'products': [{'id': 7, 'title': 'Other', 'image': ''}]}}

        def get(url, token):
            self.assertEqual(token, TOKEN)
            if 'userData' in url:
                return {'username': 'gogger'}
            return pages[int(url.rsplit('=', 1)[1])]

        with mock.patch.object(stores, '_get_json', get):
            data = stores.refresh_owned('gog', force=True)
        self.assertEqual([g['app'] for g in data['games']], ['1207658930', '7'])
        self.assertEqual(data['games'][0]['art'], 'https://images.gog.example/abc.jpg')
        self.assertEqual(data['name'], 'gogger')
        self.assertEqual(stores.account_name('gog'), 'gogger')

    def test_amazon_owned_and_updates(self):
        pending = stores.begin_signin('amazon')
        stores.finish_signin('amazon', 'https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=ANabcdefghij0123',
                             pending['state'])
        data = stores.refresh_owned('amazon', force=True)
        self.assertEqual(len(data['games']), 2)
        self.assertEqual(data['updates'], ['amzn1.adg.product.0000-example'])

    def test_covers_download_is_limited_to_https_and_cached(self):
        self.sign_in_epic()
        stores.refresh_owned('epic')

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch('urllib.request.urlopen', lambda *a, **k: Response(b'\xff\xd8jpeg')):
            self.assertEqual(stores.fetch_covers('epic'), 1)
            self.assertEqual(stores.fetch_covers('epic'), 0)
        item = stores.load_owned('epic')['games'][0]
        self.assertTrue(os.path.isfile(stores.cover_file(item['art'])))

    def test_cover_url_with_spaces_does_not_stop_the_others(self):
        # Epic's CDN has file names with spaces; http.client refused them and the
        # error stopped every cover after that one
        import http.client
        self.sign_in_epic()
        data = stores.refresh_owned('epic')
        games = data['games']
        self.assertGreaterEqual(len(games), 2)
        games[0]['art'] = 'https://cdn1.epicgames.com/x/item/broken.png'
        games[1]['art'] = 'https://cdn1.epicgames.com/x/item/AC KINGDOM_Key Art_640x854.png'
        with open(stores.owned_path('epic'), 'w') as f:
            json.dump(data, f)
        self.assertTrue(stores.missing_covers('epic'))
        asked = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(request, **_k):
            asked.append(request.full_url)
            if ' ' in request.full_url:
                raise http.client.InvalidURL('control characters')
            if 'broken' in request.full_url:
                raise http.client.RemoteDisconnected('gone')
            return Response(b'\xff\xd8jpeg')

        with mock.patch('urllib.request.urlopen', urlopen):
            stores.fetch_covers('epic')
        # the failed one comes first; the one after it still downloads, with its spaces encoded
        self.assertIn('https://cdn1.epicgames.com/x/item/AC%20KINGDOM_Key%20Art_640x854.png', asked)
        self.assertTrue(os.path.isfile(stores.cover_file(games[1]['art'])))
        self.assertFalse(os.path.isfile(stores.cover_file(games[0]['art'])))

    def test_safe_url(self):
        self.assertEqual(stores.safe_url('https://a.example/p q/r%20s.png?w=1&h=2'),
                         'https://a.example/p%20q/r%20s.png?w=1&h=2')


class LibraryTests(StoreCase):
    def test_owned_games_are_greyed_and_never_twice(self):
        self.sign_in_epic()
        stores.refresh_owned('epic')
        self.make_heroic_dirs()
        before = library.scan_all(self.home)
        epic = {g.key: g for g in before.games if g.source == 'epic'}
        self.assertEqual(set(epic), {'epic:Sugar', 'epic:Fox'})
        self.assertTrue(epic['epic:Sugar'].installed)           # Heroic's copy wins over the owned entry
        self.assertEqual(epic['epic:Sugar'].launcher, 'heroic')
        self.assertFalse(epic['epic:Fox'].installed)
        self.assertEqual(epic['epic:Fox'].launcher, 'spark')
        stores.take_over(self.home, 'epic')
        after = library.scan_all(self.home)
        keys = [g.key for g in after.games]
        self.assertEqual(len(keys), len(set(keys)))
        sugar = [g for g in after.games if g.key == 'epic:Sugar']
        self.assertEqual(len(sugar), 1)
        self.assertEqual(sugar[0].launcher, 'spark')
        self.assertTrue(sugar[0].installed)

    def test_cache_keeps_installed_flag(self):
        self.sign_in_epic()
        stores.refresh_owned('epic')
        result = library.scan_all(self.home)
        library.save_cache(result)
        again = library.load_cache()
        fox = [g for g in again.games if g.key == 'epic:Fox'][0]
        self.assertFalse(fox.installed)

    def test_existing_counts_unchanged(self):
        counts = {}
        for game in library.scan_all(self.home).games:
            counts[game.source] = counts.get(game.source, 0) + 1
        for source, expected in fixtures.EXPECTED.items():
            self.assertEqual(counts.get(source, 0), expected, source)


class TakeoverTests(StoreCase):
    def test_takes_over_without_touching_heroics_files(self):
        self.sign_in_epic()
        self.make_heroic_dirs()
        heroic_dir = os.path.join(self.home, '.var', 'app', 'com.heroicgameslauncher.hgl')
        games_dir = os.path.join(self.home, 'Games', 'Heroic')
        snapshot = (self.tree(heroic_dir), self.tree(games_dir))
        found = stores.takeable(self.home)
        self.assertEqual(sorted(g['store'] for g in found), ['epic', 'gog'])     # Amazon: not signed in
        self.assertEqual(stores.take_over(self.home, 'epic'), (1, 0))
        self.assertEqual(stores.take_over(self.home, 'gog'), (1, 0))
        self.assertEqual(stores.take_over(self.home, 'epic'), (0, 0))            # already ours
        games = registry.load()['games']
        self.assertEqual(set(games), {'epic:Sugar', 'gog:1207658930'})           # the DLC is skipped
        self.assertEqual(games['epic:Sugar']['via'], 'heroic')
        self.assertEqual(games['epic:Sugar']['version'], '1.4.0.0')
        self.assertEqual(games['gog:1207658930']['platform'], 'linux')
        self.assertEqual((self.tree(heroic_dir), self.tree(games_dir)), snapshot)
        imports = [c for c in self.calls_made() if 'import' in c]
        self.assertEqual(len(imports), 1)
        self.assertIn('--disable-check', imports[0])
        self.assertFalse([c for c in self.calls_made() if c[0] == 'gogdl'])      # nothing downloaded

    def test_missing_folder_is_not_offered(self):
        self.sign_in_epic()                       # the fixture game folders don't exist yet
        self.assertEqual(stores.takeable(self.home), [])

    def test_uninstall_of_a_taken_over_game_keeps_the_files(self):
        self.sign_in_epic()
        self.make_heroic_dirs()
        stores.take_over(self.home, 'epic')
        path = registry.load()['games']['epic:Sugar']['path']
        open(os.path.join(path, 'save.dat'), 'w').write('x')
        self.assertEqual(stores.uninstall('epic:Sugar'), '')
        self.assertTrue(os.path.isfile(os.path.join(path, 'save.dat')))
        self.assertNotIn('epic:Sugar', registry.load()['games'])
        self.assertTrue([c for c in self.calls_made() if 'uninstall' in c and '--keep-files' in c])

    def test_delete_only_inside_the_games_folders(self):
        root = os.path.join(self.tmp, 'Games', 'gog')
        inside = os.path.join(root, 'Game')
        outside = os.path.join(self.tmp, 'precious')
        for path in (inside, outside):
            os.makedirs(path)
        registry.add_game('gog:1', {'store': 'gog', 'app': '1', 'title': 'a', 'path': inside,
                                    'root': root, 'via': 'spark'})
        registry.add_game('gog:2', {'store': 'gog', 'app': '2', 'title': 'b', 'path': outside,
                                    'root': root, 'via': 'spark'})
        self.assertEqual(stores.uninstall('gog:1'), '')
        self.assertFalse(os.path.exists(inside))
        self.assertEqual(stores.uninstall('gog:2'), 'err_uninstall_outside')
        self.assertTrue(os.path.exists(outside))
        self.assertFalse(stores.safe_to_delete(root, [root]))
        self.assertFalse(stores.safe_to_delete(root + '-evil/x', [root]))


class JobTests(StoreCase):
    def spec(self, kind='install', store='epic', app='Fox', title='Free Fox Game'):
        root = os.path.join(self.tmp, 'Games', store)
        return dict(kind=kind, store=store, app=app, key=f'{store}:{app}', title=title, root=root,
                    path=stores.target_dir(store, title, root))

    def test_parse_line_reads_both_clients_formats(self):
        state = {}
        self.assertTrue(jobs.parse_line('[DLManager] INFO: = Progress: 12.50% (5/40), Running for '
                                        '00:00:01, ETA: 00:01:07', state))
        self.assertEqual((state['percent'], state['eta']), (12.5, '1:07'))
        self.assertTrue(jobs.parse_line('[DLManager] INFO:  + Download\t- 14.54 MiB/s (raw)', state))
        self.assertEqual(state['speed'], '14.54 MiB/s')
        self.assertFalse(jobs.parse_line('unrelated', state))

    def test_epic_install_records_the_game(self):
        job_id, code = self.run_job(**self.spec())
        self.assertEqual(code, 0)
        job = jobs.read_job(job_id)
        self.assertEqual((job['state'], job['percent']), ('done', 100.0))
        rec = registry.load()['games']['epic:Fox']
        self.assertTrue(rec['path'].endswith('FoxGame'))
        self.assertEqual((rec['version'], rec['via']), ('2.0', 'spark'))
        install = [c for c in self.calls_made() if 'install' in c][0]
        self.assertIn('--base-path', install)
        self.assertIn('-y', install)

    def test_gog_and_amazon_install(self):
        stores.finish_signin('gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789')
        _i, code = self.run_job(**self.spec(store='gog', app='7', title='Other'))
        self.assertEqual(code, 0)
        rec = registry.load()['games']['gog:7']
        self.assertTrue(os.path.isfile(os.path.join(rec['path'], 'game.exe')))
        pending = stores.begin_signin('amazon')
        stores.finish_signin('amazon', 'https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=ANabcdefghij0123',
                             pending['state'])
        _i, code = self.run_job(**self.spec(store='amazon', app='amzn1.adg.product.1111-other',
                                            title='Other'))
        self.assertEqual(code, 0)
        self.assertEqual(registry.load()['games']['amazon:amzn1.adg.product.1111-other']['version'], '7')

    def test_update_and_verify_use_the_right_arguments(self):
        self.run_job(**self.spec())
        self.run_job(**self.spec(kind='update'))
        self.run_job(**self.spec(kind='verify'))
        installs = [c for c in self.calls_made() if 'install' in c]
        self.assertIn('--update-only', installs[1])
        self.assertIn('--repair', installs[2])
        self.assertEqual(stores.job_args('update', 'gog', '7', '/p')[0], 'update')
        self.assertEqual(stores.job_args('verify', 'gog', '7', '/p')[0], 'repair')
        self.assertEqual(stores.job_args('verify', 'amazon', 'a', '/p')[0], 'verify')

    def test_failures_become_plain_codes_without_secrets(self):
        os.environ['FAKE_FAIL'] = 'space'
        job_id, code = self.run_job(**self.spec())
        self.assertEqual(code, 1)
        self.assertEqual(jobs.read_job(job_id)['message'], 'err_space')
        self.assertNotIn('epic:Fox', registry.load()['games'])
        os.environ['FAKE_FAIL'] = 'crash'
        job_id, _c = self.run_job(**self.spec())
        job = jobs.read_job(job_id)
        self.assertEqual(job['message'], 'err_job_failed')
        self.assertNotIn('abc123', json.dumps(job))

    def test_info_sizes(self):
        self.assertEqual(stores.install_info('epic', 'Fox'), (1048576, 2097152))
        stores.finish_signin('gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789')
        self.assertEqual(stores.install_info('gog', '7'), (3145728, 6291456))
        self.assertEqual(stores.install_info('amazon', 'a'), (2097152, 4194304))

    def test_pause_resume_cancel_in_a_helper_process(self):
        os.environ['FAKE_SLOW'] = '1'
        job_id = jobs.spawn(self.spec())
        job = self.wait_for(job_id, ('running',))
        end = time.time() + 10
        while job['percent'] == 0 and time.time() < end:
            time.sleep(0.1)
            job = jobs.read_job(job_id)
        self.assertTrue(jobs.pause(job_id))
        job = self.wait_for(job_id, ('paused',))
        frozen = job['percent']
        time.sleep(1.0)
        self.assertEqual(jobs.read_job(job_id)['percent'], frozen)
        self.assertTrue(jobs.resume(job_id))
        self.wait_for(job_id, ('running',))
        self.assertTrue(jobs.cancel(job_id))
        job = self.wait_for(job_id, ('cancelled',))
        self.assertNotIn('epic:Fox', registry.load()['games'])
        self.assertFalse(jobs.cancel(job_id))                 # nothing left to cancel

    def test_one_install_per_disk_the_rest_queue(self):
        os.environ['FAKE_SLOW'] = '1'
        first = jobs.spawn(self.spec())
        self.wait_for(first, ('running',))
        second = jobs.spawn(self.spec(app='Sugar', title='Celeste'))
        time.sleep(0.8)
        self.assertEqual(jobs.read_job(second)['state'], 'queued')
        self.assertEqual(jobs.job_for('epic:Sugar')['id'], second)
        self.wait_for(first, ('done',), 30)
        self.wait_for(second, ('done',), 30)

    def test_a_dead_helper_is_reported_failed(self):
        job_id = jobs.new_id()
        from sparkgames.core import write_json
        write_json(jobs.state_path(job_id), {'id': job_id, 'state': 'running', 'pid': 2 ** 22 + 5,
                                             'key': 'k'})
        self.assertEqual(jobs.read_job(job_id)['state'], 'failed')

    def test_update_clears_the_update_flag(self):
        self.sign_in_epic()
        registry.add_game('epic:Sugar', {'store': 'epic', 'app': 'Sugar', 'title': 'Celeste',
                                         'path': self.tmp, 'version': '1.4.0.0', 'via': 'spark'})
        self.assertEqual(stores.refresh_owned('epic')['updates'], ['Sugar'])
        self.run_job(**self.spec(kind='update', app='Sugar', title='Celeste'))
        self.assertEqual(stores.load_owned('epic')['updates'], [])


class LaunchTests(StoreCase):
    def game(self, store, app, path=None, via='spark', **extra):
        path = path or os.path.join(self.tmp, 'installed', app)
        os.makedirs(path, exist_ok=True)
        registry.add_game(f'{store}:{app}', dict({'store': store, 'app': app, 'title': app,
                                                  'path': path, 'platform': 'Windows',
                                                  'via': via}, **extra))
        return [g for g in stores.scan_installed(self.home, []) if g.key == f'{store}:{app}'][0]

    def test_epic_command_comes_from_legendarys_json(self):
        self.sign_in_epic()
        game = self.game('epic', 'Fox')
        opts = {'mangohud': True, 'gamemode': True}
        plan = launch.plan(game, opts, fake_which('umu-run', 'gamemoderun'))
        self.assertEqual(plan.argv[:2], ['gamemoderun', '/usr/bin/umu-run'])
        self.assertEqual(plan.argv[2], '/games/fox/Fox.exe')
        self.assertIn('-user', plan.argv)
        self.assertIn('-egl', plan.argv)
        self.assertEqual(plan.env['GAMEID'], 'umu-Fox')
        self.assertEqual(plan.env['STORE'], 'egs')
        self.assertEqual(plan.env['MANGOHUD'], '1')
        self.assertEqual(plan.env['FOO'], 'bar')
        self.assertTrue(plan.env['WINEPREFIX'].startswith(os.path.join(data_dir(), 'prefixes')))
        self.assertTrue(plan.wait)
        self.assertNotIn('PROTONPATH', plan.env)
        self.assertEqual(launch.plan(game, {'ge_proton': True, 'cloud_saves': False},
                                     fake_which('umu-run')).env['PROTONPATH'], 'GE-Proton')

    def test_cloud_saves_switch_adds_sync_hooks(self):
        self.sign_in_epic()
        game = self.game('epic', 'Fox')
        on = launch.plan(game, {}, fake_which('umu-run'))
        self.assertIn('--skip-upload', on.pre[0]['argv'])
        self.assertIn('--skip-download', on.post[0]['argv'])
        off = launch.plan(game, {'cloud_saves': False}, fake_which('umu-run'))
        self.assertEqual((off.pre, off.post), ([], []))

    def test_no_umu_run_is_a_plain_error(self):
        self.sign_in_epic()
        game = self.game('epic', 'Fox')
        with self.assertRaises(launch.LaunchError) as ctx:
            launch.plan(game, {}, fake_which())
        self.assertEqual(ctx.exception.code, 'no_umu')

    def test_gog_and_amazon_commands(self):
        stores.finish_signin('gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789')
        game = self.game('gog', '7')
        plan = launch.plan(game, {}, fake_which('umu-run'))
        self.assertEqual(plan.argv[1:3], ['--auth-config-path', clients.gog_auth_file()])
        self.assertEqual(plan.argv[3:5], ['launch', game.install_dir])
        self.assertIn('windows', plan.argv)
        self.assertEqual(plan.env['STORE'], 'gog')
        self.assertEqual(plan.watch_dir, game.install_dir)
        amazon = self.game('amazon', 'amzn1.adg.product.1')
        plan = launch.plan(amazon, {}, fake_which('umu-run'))
        self.assertEqual(plan.argv[1:3], ['launch', 'amzn1.adg.product.1'])
        self.assertEqual(plan.env['STORE'], 'amazon')

    def test_native_linux_gog_game_skips_umu(self):
        stores.finish_signin('gog', 'https://embed.gog.com/on_login_success?origin=client&code=abcdefghij0123456789')
        game = self.game('gog', '8', platform='linux')
        plan = launch.plan(game, {}, fake_which())
        self.assertIn('linux', plan.argv)
        self.assertNotIn('--wine', plan.argv)

    def test_not_installed_cannot_launch(self):
        game = Game(key='epic:Fox', title='Fox', source='epic', installed=False,
                    launch={'spark': True, 'store': 'epic', 'app': 'Fox'})
        with self.assertRaises(launch.LaunchError):
            launch.plan(game, {}, fake_which('umu-run'))

    def test_token_never_logged_on_start(self):
        self.sign_in_epic()
        game = self.game('epic', 'Fox')
        plan = launch.plan(game, {}, fake_which('umu-run'))
        with mock.patch('subprocess.Popen'):
            launch.start(game, {}, plan_=plan)
        self.assertNotIn(TOKEN, '\n'.join(self.handler.lines))

    def test_track_runs_before_and_after_commands(self):
        marker = os.path.join(self.tmp, 'order.txt')

        def hook(word):
            return {'argv': [sys.executable, '-c',
                             f'open({marker!r}, "a").write({word!r})'], 'env': {}}

        spec = {'key': 'k', 'title': 't', 'argv': [sys.executable, '-c',
                                                   f'open({marker!r}, "a").write("game")'],
                'wait': True, 'pre': [hook('pre,')], 'post': [hook(',post'), {'argv': ['/nonexistent']}]}
        launch.track(spec)
        self.assertEqual(open(marker).read(), 'pre,game,post')


class RunnerDownloadTests(StoreCase):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def setUp(self):
        super().setUp()
        os.environ.pop('SPARK_GAMES_LEGENDARY', None)
        self.data = b'#!/bin/sh\necho legendary version "0.21.1"\n' + b'x' * 5000
        self.runner = clients.Runner('legendary', '9.9', 'https://example.invalid/legendary',
                                     hashlib.sha256(self.data).hexdigest(), len(self.data), 'epic')
        patch = mock.patch.dict(clients.RUNNERS, {'legendary': self.runner})
        patch.start()
        self.addCleanup(patch.stop)
        arch = mock.patch('platform.machine', lambda: 'x86_64')
        arch.start()
        self.addCleanup(arch.stop)

    def test_download_is_checked_and_kept(self):
        self.assertIsNone(clients.find('legendary'))
        with mock.patch('urllib.request.urlopen', lambda *a, **k: self.Response(self.data)):
            path = clients.ensure('legendary')
        self.assertEqual(path, clients.pinned_path('legendary'))
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(clients.sha256_of(path), self.runner.sha256)
        self.assertEqual(clients.find('legendary'), path)

    def test_wrong_bytes_are_deleted(self):
        bad = bytearray(self.data)
        bad[10] ^= 1
        with mock.patch('urllib.request.urlopen', lambda *a, **k: self.Response(bytes(bad))):
            with self.assertRaises(clients.ClientError) as ctx:
                clients.ensure('legendary')
        self.assertEqual(ctx.exception.kind, 'mismatch')
        self.assertIsNone(clients.find('legendary'))
        left = [n for _r, _d, files in os.walk(clients.runners_dir()) for n in files]
        self.assertEqual(left, [])

    def test_bigger_than_pinned_is_refused(self):
        with mock.patch('urllib.request.urlopen',
                        lambda *a, **k: self.Response(self.data + b'more')):
            with self.assertRaises(clients.ClientError) as ctx:
                clients.ensure('legendary')
        self.assertEqual(ctx.exception.kind, 'mismatch')

    def test_network_failure_is_a_plain_error(self):
        import urllib.error

        def boom(*a, **k):
            raise urllib.error.URLError('no route')

        with mock.patch('urllib.request.urlopen', boom):
            with self.assertRaises(clients.ClientError) as ctx:
                clients.ensure('legendary')
        self.assertEqual(ctx.exception.kind, 'network')

    def test_pins_are_complete(self):
        for name, runner in clients.RUNNERS.items():
            if name == 'legendary':
                runner = clients.RUNNERS['legendary']
            self.assertRegex(runner.sha256 if name != 'legendary' else 'a' * 64, r'^[0-9a-f]{64}$')


class PinTests(unittest.TestCase):
    def test_real_pins_look_right(self):
        saved = {'legendary': '0.21.1', 'gogdl': '1.4.0', 'nile': '1.2.0'}
        for name, version in saved.items():
            runner = clients.RUNNERS[name]
            self.assertEqual(runner.version, version)
            self.assertRegex(runner.sha256, r'^[0-9a-f]{64}$')
            self.assertTrue(runner.url.startswith('https://github.com/'))
            self.assertGreater(runner.size, 100000)

    def test_third_party_lists_every_pin(self):
        with open(os.path.join(APP_DIR, '..', '..', 'THIRD-PARTY.md'), encoding='utf-8') as f:
            text = f.read()
        for runner in clients.RUNNERS.values():
            self.assertIn(runner.sha256, text)
            self.assertIn(runner.url, text)


class ClientReportTests(StoreCase):
    def test_report_lists_each_client_with_its_version(self):
        report = {name: (path, version) for name, path, version in clients.report()}
        self.assertEqual(set(report), {'legendary', 'gogdl', 'nile'})
        self.assertEqual(report['legendary'][1], '0.21.1')
        self.assertEqual(report['gogdl'][1], '1.4.0')

    def test_self_test_prints_the_clients(self):
        import subprocess
        env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ''))
        done = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_games.py'),
                               '--self-test'], capture_output=True, text=True, env=env, timeout=120)
        self.assertIn('store clients', done.stdout)
        self.assertIn('legendary: ok (0.21.1', done.stdout)


class RegistryTests(StoreCase):
    def test_concurrent_writers_lose_nothing(self):
        threads = [threading.Thread(target=registry.add_game,
                                    args=(f'epic:{i}', {'store': 'epic', 'app': str(i)}))
                   for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(registry.load()['games']), 25)


class LauncherTests(StoreCase):
    class Response(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def download(self, slug, data, url=None):
        class Opener:
            def open(_s, request, timeout=0):
                return self.Response(data)

        with mock.patch('urllib.request.build_opener', lambda *a: Opener()):
            return launchers.download_installer(slug, os.path.join(self.tmp, 'dl'), url=url)

    def test_installer_checks(self):
        good = b'MZ' + b'\0' * (launchers.MIN_SIZE + 10)
        path = self.download('battlenet', good)
        self.assertTrue(os.path.isfile(path))
        self.assertIn(hashlib.sha256(good).hexdigest(), '\n'.join(self.handler.lines))
        with self.assertRaises(launchers.InstallerError) as ctx:
            self.download('ea', b'<html>' + b'\0' * launchers.MIN_SIZE)
        self.assertEqual(ctx.exception.kind, 'header')
        with self.assertRaises(launchers.InstallerError) as ctx:
            self.download('ea', b'MZ tiny')
        self.assertEqual(ctx.exception.kind, 'size')
        self.assertFalse([n for n in os.listdir(os.path.join(self.tmp, 'dl')) if n.startswith('ea')])
        with self.assertRaises(launchers.InstallerError) as ctx:
            self.download('ea', good, url='http://origin-a.akamaihd.net/x.exe')
        self.assertEqual(ctx.exception.kind, 'host')
        with self.assertRaises(launchers.InstallerError):
            self.download('ea', good, url='https://evil.example.com/x.exe')

    def test_redirects_stay_on_the_allowlist(self):
        handler = launchers._Redirects('battlenet')
        with self.assertRaises(launchers.InstallerError):
            handler.redirect_request(mock.Mock(), None, 302, 'x', {}, 'https://evil.example/x')
        with self.assertRaises(launchers.InstallerError):
            handler.redirect_request(mock.Mock(), None, 302, 'x', {},
                                     'http://downloader.battle.net/x')

    def test_every_launcher_has_pinned_details(self):
        for slug, info in launchers.LAUNCHERS.items():
            self.assertTrue(info['url'].startswith('https://'))
            self.assertTrue(launchers.host_allowed(slug, info['url']), slug)
            self.assertTrue(info['exes'])

    def fake_install(self, slug):
        exe = os.path.join(launchers.prefix_dir(slug), *launchers.LAUNCHERS[slug]['exes'][0].split('/'))
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        open(exe, 'w').close()
        return exe

    def test_install_job_runs_umu_and_registers_the_launcher(self):
        script = os.path.join(self.tmp, 'bin', 'umu-run')
        exe_rel = launchers.LAUNCHERS['battlenet']['exes'][0]
        with open(script, 'w') as f:
            f.write(f'#!/bin/sh\nmkdir -p "$WINEPREFIX/$(dirname "{exe_rel}")"\n'
                    f'echo "$GAMEID" > "$WINEPREFIX/gameid"\n: > "$WINEPREFIX/{exe_rel}"\n')
        os.chmod(script, 0o755)

        def fake_download(slug, dest, progress=None, cancel=None, url=None):
            os.makedirs(dest, exist_ok=True)
            path = os.path.join(dest, 'i.exe')
            open(path, 'w').write('MZ')
            return path

        with mock.patch.object(launchers, 'real_which', lambda n: script), \
                mock.patch.object(launchers, 'download_installer', fake_download):
            job_id, code = self.run_job(kind='launcher', store='battlenet', key='battlenet:launcher',
                                        title='Battle.net', path=launchers.prefix_dir('battlenet'))
        self.assertEqual(code, 0)
        self.assertEqual(jobs.read_job(job_id)['state'], 'done')
        rec = registry.load()['launchers']['battlenet']
        self.assertEqual(rec['via'], 'spark')
        self.assertEqual(open(os.path.join(rec['prefix'], 'gameid')).read().strip(), 'umu-battlenet')
        self.assertTrue(rec['prefix'].endswith(os.path.join('prefixes', 'battlenet')))

    def test_install_job_without_umu_says_so(self):
        with mock.patch.object(launchers, 'real_which', lambda n: None):
            job_id, code = self.run_job(kind='launcher', store='ea', key='ea:launcher',
                                        title='EA app', path=launchers.prefix_dir('ea'))
        self.assertEqual(jobs.read_job(job_id)['message'], 'err_no_umu')

    def test_tile_plan_and_remove(self):
        exe = self.fake_install('ubisoft')
        games = launchers.scan(self.home, [])
        self.assertEqual([(g.key, g.source) for g in games], [('ubisoft:launcher', 'ubisoft')])
        plan = launch.plan(games[0], {'ge_proton': True}, fake_which('umu-run'))
        self.assertEqual(plan.argv, ['/usr/bin/umu-run', exe])
        self.assertEqual(plan.env['GAMEID'], 'umu-ubisoft')
        self.assertEqual(plan.env['PROTONPATH'], 'GE-Proton')
        self.assertEqual(games[0].launcher, 'spark')
        launchers.remove('ubisoft')
        self.assertFalse(os.path.exists(launchers.prefix_dir('ubisoft')))
        self.assertEqual(launchers.scan(self.home, []), [])

    def test_lutris_launcher_is_used_once_and_kept(self):
        before = [g for g in library.scan_all(self.home).games if g.source == 'lutris']
        self.assertIn('Battle.net', [g.title for g in before])
        found = launchers.lutris_launchers(self.home)
        self.assertEqual([f['slug'] for f in found], ['battlenet'])
        self.assertTrue(found[0]['prefix'].endswith('Games/battlenet'))
        shot = self.tree(os.path.join(self.home, 'Games', 'battlenet'))
        launchers.use_lutris(found[0])
        self.assertEqual(launchers.lutris_launchers(self.home), [])
        result = library.scan_all(self.home)
        titles = [g.source for g in result.games if g.title == 'Battle.net' and g.source in ('lutris', 'battlenet')]
        self.assertEqual(titles, ['battlenet'])                         # one tile, not two
        tile = [g for g in result.games if g.key == 'battlenet:launcher'][0]
        self.assertEqual(tile.launch['via'], 'lutris')
        launchers.remove('battlenet')
        self.assertEqual(self.tree(os.path.join(self.home, 'Games', 'battlenet')), shot)

    def test_lutris_yml_reader(self):
        path = os.path.join(self.home, '.config', 'lutris', 'games', 'battlenet-1.yml')
        values = launchers.read_game_yml(path)
        self.assertTrue(values['prefix'].endswith('Games/battlenet'))
        self.assertTrue(values['exe'].endswith('Battle.net Launcher.exe'))
        self.assertEqual(launchers.read_game_yml('/nonexistent'), {})


class StoreUITests(StoreCase):
    def setUp(self):
        super().setUp()
        if not os.environ.get('DISPLAY'):
            self.skipTest('no display')
        from sparkgames import app as appmod
        os.environ['SPARK_GAMES_REDUCED_MOTION'] = '1'
        self.appmod = appmod
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app.root.destroy()
            except Exception:      # noqa: BLE001
                pass
        super().tearDown()

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.app.root.update()
            time.sleep(0.01)

    def until(self, cond, timeout=15):
        end = time.time() + timeout
        while not cond() and time.time() < end:
            self.pump(0.05)
        self.assertTrue(cond())

    def start(self):
        self.app = self.appmod.App(self.home)
        self.app.settings['anticheat'] = False
        self.app.settings['heroic_takeover_asked'] = True
        self.app.root.geometry('1100x760')
        self.until(lambda: not self.app.scanning)
        self.pump(0.3)
        return self.app

    def test_sign_in_by_paste_then_owned_games_show_greyed(self):
        from sparkgames import storeviews
        app = self.start()
        lib = app.library
        self.assertTrue(all(g.installed for g in lib.shown))
        app.show_stores()
        view = app.view
        with mock.patch.object(storeviews.signin_window, 'available', lambda: False), \
                mock.patch.object(storeviews, 'open_uri', lambda u: None):
            view.sign_in('epic')
            self.until(lambda: view.paste_area.winfo_children())
        self.assertIn('authorizationCode', ' '.join(
            w.cget('text') for w in view.paste_area.winfo_children() if w.winfo_class() == 'Label'))
        view.finish('epic', json.dumps({'authorizationCode': 'a' * 32}), {})
        self.until(lambda: stores.signed_in('epic'))
        self.until(lambda: not view.paste_area.winfo_children())
        self.until(lambda: not app.scanning and os.path.exists(stores.owned_path('epic')))
        app.go_back()
        self.until(lambda: any(not g.installed for g in app.library.games))
        lib = app.library
        self.assertEqual(lib.scope, 'installed')
        self.assertTrue(all(g.installed for g in lib.shown))
        lib.set_scope('all')
        fox = [g for g in lib.shown if g.key == 'epic:Fox']
        self.assertEqual(len(fox), 1)
        self.assertFalse(fox[0].installed)
        keys = [g.key for g in lib.shown]
        self.assertEqual(len(keys), len(set(keys)))
        lib.set_scope('installed')
        self.assertNotIn('epic:Fox', [g.key for g in lib.shown])
        app.show_game(fox[0])
        self.pump(0.3)
        self.assertEqual(app.view.__class__.__name__, 'GamePage')

    def test_added_launcher_page_opens(self):
        # An added launcher has no games folder; its page used to fail with KeyError
        from sparkgames import launchers
        exe = os.path.join(launchers.prefix_dir('battlenet'),
                           launchers.LAUNCHERS['battlenet']['exes'][0])
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        open(exe, 'w').close()
        app = self.start()
        tile = [g for g in app.library.games if g.key == 'battlenet:launcher']
        self.assertEqual(len(tile), 1)
        app.show_game(tile[0])
        self.pump(0.3)
        self.assertEqual(app.view.__class__.__name__, 'GamePage')
        self.assertTrue(app.view.store_panel.is_launcher)


class StringTests(unittest.TestCase):
    def test_every_new_key_is_in_french_too(self):
        self.assertEqual(set(strings.EN), set(strings.FR))

    def test_keys_used_by_the_store_code_exist(self):
        import re
        for name in ('stores.py', 'storeviews.py', 'jobs.py', 'launchers.py', 'app.py', 'views.py'):
            with open(os.path.join(APP_DIR, 'sparkgames', name), encoding='utf-8') as f:
                text = f.read()
            for key in re.findall(r"tr\('([a-z_0-9]*[a-z0-9])'", text) + \
                    re.findall(r"'(err_[a-z_]+)'", text) + re.findall(r"'(signin_[a-z_]+)'", text):
                if not key.endswith('_'):                # 'err_client_' + kind
                    self.assertIn(key, strings.EN, f'{name}: {key}')


if __name__ == '__main__':
    unittest.main()
