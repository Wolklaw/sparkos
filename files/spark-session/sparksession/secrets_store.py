"""Spark Secrets, the storage and the crypto. No D-Bus and no GTK in here, so tests reach all of it.

Layout of ~/.local/share/spark-secrets (directory 0700, files 0600):
  master.json            the master key (32 random bytes), AES-GCM-wrapped by the wrapping key
  collections/NAME.json  one file per collection: label, dates, a search index, and one AES-GCM
                         blob (master key) with every item: label, attributes, secret

The wrapping key is scrypt(sign-in password), salt b"spark-secrets/v1/" + user name, so the PAM
helper can make it at sign-in without reading anything from the home folder. A password change
only has to re-wrap the master key; the collections are not touched.

The index holds a SHA-256 of each "name NUL value" attribute pair of each item, so a search can
tell which items match while the store is locked (clients then ask to unlock). It leaks which
attribute values exist for an item, as GNOME Keyring's own files do. Labels and secrets stay in the blob.
"""

import base64
import hashlib
import json
import os
import re
import tempfile
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SCRYPT = {'n': 2 ** 15, 'r': 8, 'p': 1}
SALT_PREFIX = b'spark-secrets/v1/'
MASTER_AAD = b'spark-secrets/v1 master'
COLLECTION_AAD = b'spark-secrets/v1 collection '
DEFAULT_TYPE = 'text/plain; charset=utf8'


class StoreError(Exception):
    pass


class Locked(StoreError):
    pass


class NoSuchObject(StoreError):
    pass


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))


# --- keys -------------------------------------------------------------------------------------

def wrapping_key(password: bytes, user: str, params=None) -> bytes:
    """The key made from the sign-in password. 32 bytes."""
    p = dict(SCRYPT, **(params or {}))
    salt = SALT_PREFIX + user.encode()
    return Scrypt(salt=salt, length=32, n=p['n'], r=p['r'], p=p['p']).derive(password)


def _gcm_seal(key: bytes, plain: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plain, aad)


def _gcm_open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < 12 + 16:
        raise InvalidTag()
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


# --- the Secret Service session crypto (DH) --------------------------------------------------

# RFC 2409 section 6.2, the second Oakley group (1024 bits), generator 2
DH_PRIME = int(
    'FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74'
    '020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F1437'
    '4FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED'
    'EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE65381FFFFFFFFFFFFFFFF', 16)
DH_GENERATOR = 2
DH_BYTES = 128


def int_to_bytes(n: int, size=None) -> bytes:
    size = size or max(1, (n.bit_length() + 7) // 8)
    return n.to_bytes(size, 'big')


def dh_server_keys():
    """(private int, public bytes) for one session."""
    while True:
        private = int.from_bytes(os.urandom(DH_BYTES), 'big') % (DH_PRIME - 3) + 2
        public = pow(DH_GENERATOR, private, DH_PRIME)
        return private, int_to_bytes(public)


def dh_session_key(private: int, client_public: bytes) -> bytes:
    """The 16-byte AES key of a dh-ietf1024-sha256-aes128-cbc-pkcs7 session."""
    peer = int.from_bytes(client_public, 'big')
    if not 2 <= peer <= DH_PRIME - 2:
        raise ValueError('bad DH public key')
    shared = int_to_bytes(pow(peer, private, DH_PRIME), DH_BYTES)
    return HKDF(algorithm=hashes.SHA256(), length=16, salt=None, info=b'').derive(shared)


def aes_cbc_encrypt(key: bytes, plain: bytes):
    """(iv, ciphertext) with PKCS7 padding."""
    iv = os.urandom(16)
    pad = padding.PKCS7(128).padder()
    data = pad.update(plain) + pad.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return iv, enc.update(data) + enc.finalize()


def aes_cbc_decrypt(key: bytes, iv: bytes, blob: bytes) -> bytes:
    if len(iv) != 16 or not blob or len(blob) % 16:
        raise ValueError('bad ciphertext')
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    data = dec.update(blob) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return unpad.update(data) + unpad.finalize()


# --- files ------------------------------------------------------------------------------------

def write_atomic(path: str, data: bytes):
    """Write next to the file, flush to disk, rename over it: a crash leaves the old or the new
    file, never half of one. 0600."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='.tmp-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    dfd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _mkdir_private(path: str):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def attr_hashes(attrs: dict):
    return sorted(hashlib.sha256(k.encode() + b'\0' + v.encode()).hexdigest()
                  for k, v in attrs.items())


def safe_name(text: str) -> str:
    """A collection name that is valid in a D-Bus object path."""
    name = re.sub(r'[^A-Za-z0-9_]', '_', text or '').strip('_').lower()
    return name or 'collection'


# --- the store --------------------------------------------------------------------------------

class Item:
    def __init__(self, ident, label='', attrs=None, secret=b'', content_type=DEFAULT_TYPE,
                 item_type='', created=None, modified=None):
        now = int(time.time())
        self.id = str(ident)
        self.label = label
        self.attrs = dict(attrs or {})
        self.secret = secret
        self.content_type = content_type
        self.type = item_type
        self.created = created if created is not None else now
        self.modified = modified if modified is not None else now

    def to_json(self):
        return {'label': self.label, 'attrs': self.attrs, 'secret': b64e(self.secret),
                'content_type': self.content_type, 'type': self.type,
                'created': self.created, 'modified': self.modified}

    @classmethod
    def from_json(cls, ident, d):
        return cls(ident, d.get('label', ''), d.get('attrs'), b64d(d.get('secret', '')),
                   d.get('content_type', DEFAULT_TYPE), d.get('type', ''),
                   d.get('created'), d.get('modified'))


class Collection:
    """`items` is filled while the vault is unlocked; the index is always there."""

    def __init__(self, name, label, persistent=True, created=None):
        now = int(time.time())
        self.name = name
        self.label = label
        self.persistent = persistent
        self.created = created if created is not None else now
        self.modified = now
        self.next_id = 1
        self.items = {}         # id -> Item, only while the vault is unlocked
        self.index = {}         # id -> sorted attribute hashes, always


class Vault:
    """All collections of one user. `session` is in memory only and always unlocked."""

    def __init__(self, directory: str, scrypt_params=None):
        self.dir = directory
        self.params = dict(SCRYPT, **(scrypt_params or {}))
        self.master = None
        self.collections = {}
        self.aliases = {}
        self.broken = {}        # name -> why its file could not be read
        self.collections['session'] = Collection('session', 'session', persistent=False)
        _mkdir_private(self.dir)
        _mkdir_private(os.path.join(self.dir, 'collections'))
        self._load_index()

    # -- loading --
    @property
    def master_path(self):
        return os.path.join(self.dir, 'master.json')

    @property
    def aliases_path(self):
        return os.path.join(self.dir, 'aliases.json')

    def has_master(self):
        return os.path.exists(self.master_path)

    @property
    def unlocked(self):
        return self.master is not None

    def _load_index(self):
        folder = os.path.join(self.dir, 'collections')
        for entry in sorted(os.listdir(folder)):
            if not entry.endswith('.json'):
                continue
            name = entry[:-5]
            try:
                with open(os.path.join(folder, entry), 'rb') as handle:
                    doc = json.load(handle)
                col = Collection(name, doc['label'], True, doc.get('created'))
                col.modified = doc.get('modified', col.modified)
                col.next_id = int(doc.get('next_id', 1))
                col.index = {str(k): v for k, v in doc.get('index', {}).items()}
                self.collections[name] = col
            except (OSError, ValueError, KeyError) as exc:
                self.broken[name] = str(exc)
        try:
            with open(self.aliases_path, 'rb') as handle:
                self.aliases = {str(k): str(v) for k, v in json.load(handle).items()}
        except (OSError, ValueError):
            self.aliases = {}
        if 'login' not in self.collections:
            self.collections['login'] = Collection('login', 'Login')
        self.aliases.setdefault('default', 'login')

    def _read_blob(self, col):
        path = os.path.join(self.dir, 'collections', col.name + '.json')
        with open(path, 'rb') as handle:
            return b64d(json.load(handle)['blob'])

    # -- master key --
    def init_master(self, wrap_key: bytes):
        """First use: make the master key, wrap it, and be unlocked."""
        if self.has_master():
            raise StoreError('the store already has a master key')
        master = os.urandom(32)
        self.master = master
        self._write_master(wrap_key)
        for col in self.collections.values():
            if col.persistent and not os.path.exists(self._col_path(col)):
                self._save(col)

    def _write_master(self, wrap_key):
        doc = {'version': 1, 'kdf': dict(name='scrypt', **self.params),
               'wrapped': b64e(_gcm_seal(wrap_key, self.master, MASTER_AAD))}
        write_atomic(self.master_path, json.dumps(doc).encode())

    def unlock(self, wrap_key: bytes) -> bool:
        """True and unlocked if the key unwraps the master key; False if the key is wrong.
        StoreError if a collection cannot be read (nothing is changed then)."""
        if self.unlocked:
            return True
        with open(self.master_path, 'rb') as handle:
            doc = json.load(handle)
        try:
            master = _gcm_open(wrap_key, b64d(doc['wrapped']), MASTER_AAD)
        except InvalidTag:
            return False
        loaded = {}
        for col in self.collections.values():
            if not col.persistent or not os.path.exists(self._col_path(col)):
                continue
            try:
                plain = _gcm_open(master, self._read_blob(col), COLLECTION_AAD + col.name.encode())
                items = json.loads(plain)['items']
                loaded[col.name] = {i: Item.from_json(i, d) for i, d in items.items()}
            except (InvalidTag, ValueError, KeyError, OSError) as exc:
                raise StoreError(f'collection {col.name} cannot be read: {exc}')
        self.master = master
        for name, items in loaded.items():
            self.collections[name].items = items
        return True

    def rewrap(self, new_key: bytes):
        self._need_unlocked()
        self._write_master(new_key)

    def lock(self):
        self.master = None
        for col in self.collections.values():
            if col.persistent:
                col.items = {}

    def _need_unlocked(self):
        if not self.unlocked:
            raise Locked('the store is locked')

    def is_locked(self, col):
        return col.persistent and not self.unlocked

    # -- saving --
    def _col_path(self, col):
        return os.path.join(self.dir, 'collections', col.name + '.json')

    def _save(self, col):
        if not col.persistent:
            return
        self._need_unlocked()
        col.index = {i: attr_hashes(it.attrs) for i, it in col.items.items()}
        plain = json.dumps({'items': {i: it.to_json() for i, it in col.items.items()}}).encode()
        doc = {'version': 1, 'name': col.name, 'label': col.label, 'created': col.created,
               'modified': col.modified, 'next_id': col.next_id, 'index': col.index,
               'blob': b64e(_gcm_seal(self.master, plain, COLLECTION_AAD + col.name.encode()))}
        write_atomic(self._col_path(col), json.dumps(doc).encode())

    def save_aliases(self):
        write_atomic(self.aliases_path, json.dumps(self.aliases).encode())

    # -- collections --
    def collection(self, name) -> Collection:
        try:
            return self.collections[name]
        except KeyError:
            raise NoSuchObject(name)

    def resolve_alias(self, alias):
        name = self.aliases.get(alias)
        return name if name in self.collections else None

    def create_collection(self, label, name=None) -> Collection:
        base = safe_name(name or label)
        name, n = base, 1
        while name in self.collections or name in self.broken:
            n += 1
            name = f'{base}_{n}'
        col = Collection(name, label)
        if self.unlocked:
            self.collections[name] = col
            self._save(col)
        else:
            raise Locked('the store is locked')
        return col

    def delete_collection(self, name):
        col = self.collection(name)
        if name in ('login', 'session'):
            raise StoreError(f'the {name} collection cannot be deleted')
        if col.persistent:
            self._need_unlocked()
            try:
                os.unlink(self._col_path(col))
            except FileNotFoundError:
                pass
        del self.collections[name]
        for alias in [a for a, n in self.aliases.items() if n == name]:
            del self.aliases[alias]
        self.save_aliases()

    def set_label(self, col, label):
        col.label, col.modified = label, int(time.time())
        self._save(col)

    # -- items --
    def item(self, col, ident) -> Item:
        if self.is_locked(col):
            raise Locked('the store is locked')
        try:
            return col.items[ident]
        except KeyError:
            raise NoSuchObject(ident)

    def item_ids(self, col):
        return sorted(col.index if self.is_locked(col) else col.items, key=int)

    def search(self, col, attrs: dict):
        """Ids of the items whose attributes include all of `attrs`; works while locked."""
        if self.is_locked(col):
            want = set(attr_hashes(attrs))
            return [i for i in sorted(col.index, key=int) if want <= set(col.index[i])]
        return [i for i in sorted(col.items, key=int)
                if all(col.items[i].attrs.get(k) == v for k, v in attrs.items())]

    def create_item(self, col, label, attrs, secret, content_type=DEFAULT_TYPE, item_type='',
                    replace=False, created=None, modified=None):
        """(item, replaced). With `replace`, an item with the same attributes is overwritten."""
        if col.persistent:
            self._need_unlocked()
        for k, v in attrs.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise StoreError('attributes are strings')
        existing = None
        if replace and attrs:
            for it in col.items.values():
                if it.attrs == attrs:
                    existing = it
                    break
        if existing is not None:
            existing.label, existing.secret = label, secret
            existing.content_type, existing.modified = content_type, int(time.time())
            if item_type:
                existing.type = item_type
            col.modified = existing.modified
            self._save(col)
            return existing, True
        ident = str(col.next_id)
        col.next_id += 1
        item = Item(ident, label, attrs, secret, content_type, item_type, created, modified)
        col.items[ident] = item
        col.modified = item.modified
        self._save(col)
        return item, False

    def update_item(self, col, item, label=None, attrs=None, secret=None, content_type=None):
        if label is not None:
            item.label = label
        if attrs is not None:
            item.attrs = dict(attrs)
        if secret is not None:
            item.secret = secret
        if content_type is not None:
            item.content_type = content_type
        item.modified = col.modified = int(time.time())
        self._save(col)

    def delete_item(self, col, ident):
        self.item(col, ident)
        del col.items[ident]
        col.modified = int(time.time())
        self._save(col)

    def find_exact(self, col, attrs):
        """The item with exactly these attributes (what an app-specific secret uses)."""
        for it in col.items.values():
            if it.attrs == attrs:
                return it
        return None


def default_dir() -> str:
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.environ.get('SPARK_SECRETS_DIR') or os.path.join(base, 'spark-secrets')


def keyfile_path(uid=None) -> str:
    uid = os.getuid() if uid is None else uid
    return os.environ.get('SPARK_SECRETS_KEYFILE') or f'/run/spark-secrets/{uid}'


def read_keyfile(path=None):
    """The wrapping key the PAM helper left at sign-in, or None."""
    try:
        with open(path or keyfile_path(), 'rb') as handle:
            raw = handle.read().strip()
        key = bytes.fromhex(raw.decode('ascii'))
        return key if len(key) == 32 else None
    except (OSError, ValueError):
        return None


def password_from_stdin(raw: bytes) -> bytes:
    """pam_exec's expose_authtok hands the password over stdin, ended by a NUL; cut there.
    If a PAM build sends a newline instead, that is dropped (a sign-in password never ends in one)."""
    raw = raw.split(b'\0', 1)[0]
    return raw[:-1] if raw.endswith(b'\n') else raw
