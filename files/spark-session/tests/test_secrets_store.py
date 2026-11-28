"""Spark Secrets' storage and crypto: no bus, no display."""

import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sparksession import secrets_store as store  # noqa: E402

FAST = {'n': 2 ** 10}


def new_vault(tmp, sub='s'):
    return store.Vault(os.path.join(tmp, sub), FAST)


class CryptoTests(unittest.TestCase):
    def test_wrapping_key_depends_on_password_and_user(self):
        a = store.wrapping_key(b'pw', 'alice', FAST)
        self.assertEqual(len(a), 32)
        self.assertEqual(a, store.wrapping_key(b'pw', 'alice', FAST))
        self.assertNotEqual(a, store.wrapping_key(b'pw2', 'alice', FAST))
        self.assertNotEqual(a, store.wrapping_key(b'pw', 'bob', FAST))

    def test_dh_both_sides_agree(self):
        private, public = store.dh_server_keys()
        c_private = int.from_bytes(os.urandom(64), 'big') | 2
        c_public = store.int_to_bytes(pow(store.DH_GENERATOR, c_private, store.DH_PRIME))
        k1 = store.dh_session_key(private, c_public)
        k2 = store.dh_session_key(c_private, public)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 16)

    def test_dh_known_vector(self):
        """The shared secret is padded to 128 bytes, then HKDF-SHA256 with no salt and no info."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        private = 12345
        peer = pow(2, 6789, store.DH_PRIME)
        shared = pow(peer, private, store.DH_PRIME).to_bytes(128, 'big')
        want = HKDF(algorithm=hashes.SHA256(), length=16, salt=None, info=b'').derive(shared)
        self.assertEqual(store.dh_session_key(private, peer.to_bytes(128, 'big')), want)

    def test_dh_rejects_bad_public_keys(self):
        for bad in (b'\x00', b'\x01', store.int_to_bytes(store.DH_PRIME), b''):
            with self.assertRaises(ValueError):
                store.dh_session_key(5, bad)

    def test_cbc_round_trip_and_padding(self):
        key = os.urandom(16)
        for plain in (b'', b'a', b'x' * 16, b'y' * 31):
            iv, blob = store.aes_cbc_encrypt(key, plain)
            self.assertEqual(len(blob) % 16, 0)
            self.assertEqual(store.aes_cbc_decrypt(key, iv, blob), plain)
        with self.assertRaises(ValueError):
            store.aes_cbc_decrypt(key, b'short', b'x' * 16)

    def test_pam_password_ends_at_the_nul(self):
        self.assertEqual(store.password_from_stdin(b'hunter2\0'), b'hunter2')
        self.assertEqual(store.password_from_stdin(b'hunter2\0junk'), b'hunter2')
        self.assertEqual(store.password_from_stdin(b'hunter2'), b'hunter2')
        self.assertEqual(store.password_from_stdin(b'hunter2\n'), b'hunter2')


class VaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.key = store.wrapping_key(b'pw', 'u', FAST)

    def tearDown(self):
        self._tmp.cleanup()

    def unlocked(self):
        v = new_vault(self.tmp)
        v.init_master(self.key)
        return v

    def test_new_vault_has_login_session_and_default_alias(self):
        v = new_vault(self.tmp)
        self.assertIn('login', v.collections)
        self.assertFalse(v.collections['session'].persistent)
        self.assertEqual(v.resolve_alias('default'), 'login')
        self.assertTrue(v.is_locked(v.collections['login']))
        self.assertFalse(v.is_locked(v.collections['session']))

    def test_items_survive_a_restart(self):
        v = self.unlocked()
        col = v.collection('login')
        v.create_item(col, 'Mail', {'host': 'a', 'user': 'me'}, b'pass1')
        v2 = new_vault(self.tmp)
        self.assertTrue(v2.has_master())
        self.assertTrue(v2.unlock(self.key))
        it = v2.item(v2.collection('login'), '1')
        self.assertEqual((it.label, it.attrs, it.secret), ('Mail', {'host': 'a', 'user': 'me'}, b'pass1'))

    def test_wrong_key_does_not_unlock(self):
        self.unlocked()
        v2 = new_vault(self.tmp)
        self.assertFalse(v2.unlock(store.wrapping_key(b'other', 'u', FAST)))
        self.assertFalse(v2.unlocked)

    def test_files_on_disk_hold_no_plain_secret_or_label(self):
        v = self.unlocked()
        v.create_item(v.collection('login'), 'LabelXYZ', {'host': 'hostABC'}, b'SECRET-VALUE-1')
        for root, _, files in os.walk(v.dir):
            for name in files:
                with open(os.path.join(root, name), 'rb') as handle:
                    data = handle.read()
                for needle in (b'SECRET-VALUE-1', b'LabelXYZ', b'hostABC'):
                    self.assertNotIn(needle, data, name)

    def test_modes(self):
        v = self.unlocked()
        v.create_item(v.collection('login'), 'a', {}, b'b')
        self.assertEqual(stat.S_IMODE(os.stat(v.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(v.dir, 'collections')).st_mode), 0o700)
        for path in (v.master_path, os.path.join(v.dir, 'collections', 'login.json')):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_tampered_collection_is_refused_not_dropped(self):
        v = self.unlocked()
        v.create_item(v.collection('login'), 'a', {'k': 'v'}, b'b')
        path = os.path.join(v.dir, 'collections', 'login.json')
        with open(path) as handle:
            doc = json.load(handle)
        blob = bytearray(store.b64d(doc['blob']))
        blob[-1] ^= 1
        doc['blob'] = store.b64e(bytes(blob))
        with open(path, 'w') as handle:
            json.dump(doc, handle)
        v2 = new_vault(self.tmp)
        with self.assertRaises(store.StoreError):
            v2.unlock(self.key)
        self.assertFalse(v2.unlocked)

    def test_search_while_locked_uses_the_index(self):
        v = self.unlocked()
        col = v.collection('login')
        v.create_item(col, 'a', {'host': 'x', 'user': 'me'}, b'1')
        v.create_item(col, 'b', {'host': 'y'}, b'2')
        v2 = new_vault(self.tmp)
        c2 = v2.collection('login')
        self.assertTrue(v2.is_locked(c2))
        self.assertEqual(v2.search(c2, {'host': 'x'}), ['1'])
        self.assertEqual(v2.search(c2, {'host': 'x', 'user': 'me'}), ['1'])
        self.assertEqual(v2.search(c2, {'host': 'z'}), [])
        self.assertEqual(sorted(v2.search(c2, {})), ['1', '2'])
        with self.assertRaises(store.Locked):
            v2.item(c2, '1')

    def test_search_unlocked_matches_values_exactly(self):
        v = self.unlocked()
        col = v.collection('login')
        v.create_item(col, 'a', {'host': 'x'}, b'1')
        self.assertEqual(v.search(col, {'host': 'x'}), ['1'])
        self.assertEqual(v.search(col, {'host': 'xx'}), [])

    def test_replace_overwrites_same_attributes(self):
        v = self.unlocked()
        col = v.collection('login')
        a, replaced = v.create_item(col, 'one', {'k': 'v'}, b'1')
        b, replaced2 = v.create_item(col, 'two', {'k': 'v'}, b'2', replace=True)
        self.assertEqual((replaced, replaced2, a.id, b.id), (False, True, '1', '1'))
        self.assertEqual(len(col.items), 1)
        self.assertEqual(col.items['1'].secret, b'2')
        c, _ = v.create_item(col, 'three', {'k': 'v'}, b'3')
        self.assertEqual(c.id, '2')

    def test_update_and_delete(self):
        v = self.unlocked()
        col = v.collection('login')
        it, _ = v.create_item(col, 'a', {'k': 'v'}, b'1')
        v.update_item(col, it, label='b', attrs={'z': '1'}, secret=b'9')
        v2 = new_vault(self.tmp)
        v2.unlock(self.key)
        got = v2.item(v2.collection('login'), '1')
        self.assertEqual((got.label, got.attrs, got.secret), ('b', {'z': '1'}, b'9'))
        self.assertEqual(v2.search(v2.collection('login'), {'k': 'v'}), [])
        v2.delete_item(v2.collection('login'), '1')
        with self.assertRaises(store.NoSuchObject):
            v2.item(v2.collection('login'), '1')

    def test_rewrap_keeps_the_data_under_the_new_key(self):
        v = self.unlocked()
        v.create_item(v.collection('login'), 'a', {}, b'1')
        new = store.wrapping_key(b'new', 'u', FAST)
        v.rewrap(new)
        v2 = new_vault(self.tmp)
        self.assertFalse(v2.unlock(self.key))
        self.assertTrue(v2.unlock(new))
        self.assertEqual(v2.item(v2.collection('login'), '1').secret, b'1')

    def test_session_collection_is_memory_only(self):
        v = self.unlocked()
        s = v.collection('session')
        v.create_item(s, 'tmp', {'a': 'b'}, b'1')
        self.assertFalse(os.path.exists(os.path.join(v.dir, 'collections', 'session.json')))
        v.lock()
        self.assertEqual(v.search(s, {'a': 'b'}), ['1'])

    def test_lock_forgets_items(self):
        v = self.unlocked()
        col = v.collection('login')
        v.create_item(col, 'a', {'k': 'v'}, b'1')
        v.lock()
        self.assertFalse(v.unlocked)
        self.assertEqual(col.items, {})
        with self.assertRaises(store.Locked):
            v.create_item(col, 'b', {}, b'2')

    def test_create_and_delete_collection(self):
        v = self.unlocked()
        c = v.create_collection('My Things!')
        self.assertEqual(c.name, 'my_things')
        c2 = v.create_collection('My Things!')
        self.assertEqual(c2.name, 'my_things_2')
        v.delete_collection('my_things')
        self.assertNotIn('my_things', v.collections)
        with self.assertRaises(store.StoreError):
            v.delete_collection('login')

    def test_attributes_must_be_strings(self):
        v = self.unlocked()
        with self.assertRaises(store.StoreError):
            v.create_item(v.collection('login'), 'a', {'k': 1}, b'1')

    def test_keyfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'k')
            self.assertIsNone(store.read_keyfile(path))
            with open(path, 'w') as handle:
                handle.write(self.key.hex() + '\n')
            self.assertEqual(store.read_keyfile(path), self.key)
            with open(path, 'w') as handle:
                handle.write('zz')
            self.assertIsNone(store.read_keyfile(path))


if __name__ == '__main__':
    unittest.main()
