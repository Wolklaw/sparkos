"""Read a GNOME Keyring file (login.keyring and its kind) and copy its items into Spark Secrets.

The format (gnome-keyring's binary keyring, version 0):
  "GnomeKeyring\\n\\r\\0\\n", version/crypto/hash bytes, name, ctime, mtime, flags, lock timeout,
  hash iterations, 8-byte salt, 4 reserved words, then for each item its id, type and hashed
  attributes, then the encrypted part. That part is AES-128-CBC; key and IV come from the
  password: SHA-256 over password + salt, hashed again `iterations` times, more rounds chained on
  if more bytes are needed. Decrypted, it starts with the MD5 of the rest (the password check).

Numbers are big-endian; a string is a length and its bytes (0xFFFFFFFF length means none).
"""

import hashlib
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import secrets_store as store

MAGIC = b'GnomeKeyring\n\r\0\n'
ITEM_TYPES = {0: 'org.freedesktop.Secret.Generic', 1: 'org.gnome.keyring.NetworkPassword',
              2: 'org.gnome.keyring.Note'}


class ImportError_(Exception):
    pass


class WrongPassword(ImportError_):
    pass


class Reader:
    def __init__(self, data: bytes, offset=0):
        self.data, self.pos = data, offset

    def _take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ImportError_('the keyring file is cut short')
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self._take(1)[0]

    def u32(self):
        return struct.unpack('>I', self._take(4))[0]

    def u64(self):
        return struct.unpack('>Q', self._take(8))[0]

    def raw(self, n):
        return self._take(n)

    def string(self):
        n = self.u32()
        return None if n == 0xFFFFFFFF else self._take(n)


def derive(password: bytes, salt: bytes, iterations: int, hash_name: str, size=32) -> bytes:
    out, prev = b'', b''
    while len(out) < size:
        digest = hashlib.new(hash_name, prev + password + salt).digest()
        for _ in range(max(iterations, 1) - 1):
            digest = hashlib.new(hash_name, digest).digest()
        prev = digest
        out += digest
    return out[:size]


def _text(raw):
    return '' if raw is None else raw.decode('utf-8', 'replace')


def parse_keyring(data: bytes, password: bytes):
    """(name, ctime, mtime, [dict(label, attrs, secret, created, modified, type)]).
    WrongPassword if the password does not open it; ImportError_ for a file that is not one."""
    if not data.startswith(MAGIC):
        raise ImportError_('not a GNOME Keyring file (a newer or different format)')
    r = Reader(data, len(MAGIC))
    major, minor, crypto, hash_algo = r.u8(), r.u8(), r.u8(), r.u8()
    if (major, crypto) != (0, 0):
        raise ImportError_(f'keyring version {major}.{minor}, crypto {crypto} is not supported')
    name = _text(r.string())
    ctime, mtime = r.u64(), r.u64()
    r.u32()                     # flags
    r.u32()                     # lock timeout
    iterations = r.u32()
    salt = r.raw(8)
    for _ in range(4):
        r.u32()
    count = r.u32()
    types = []
    for _ in range(count):
        r.u32()                 # id
        types.append(r.u32())
        for _ in range(r.u32()):    # hashed attributes: name, kind, hash
            r.string()
            r.u32()
            r.string()
    size = r.u32()
    blob = r.raw(size)
    if size % 16 or not size:
        raise ImportError_('the encrypted part has a wrong size')

    # hash byte 0 is what gnome-keyring writes today and means SHA-256; MD5 is tried as well
    plain = None
    for hash_name in ('sha256', 'md5') if hash_algo == 0 else ('md5', 'sha256'):
        key = derive(password, salt, iterations, hash_name)
        dec = Cipher(algorithms.AES(key[:16]), modes.CBC(key[16:32])).decryptor()
        attempt = dec.update(blob) + dec.finalize()
        if hashlib.md5(attempt[16:]).digest() == attempt[:16]:
            plain = attempt[16:]
            break
    if plain is None:
        raise WrongPassword('that password does not open this keyring')

    d = Reader(plain)
    items = []
    for kind in types:
        label = _text(d.string())
        secret = d.string() or b''
        created, modified = d.u64(), d.u64()
        d.string()              # reserved
        for _ in range(4):
            d.u32()
        attrs = {}
        for _ in range(d.u32()):
            key_name = _text(d.string())
            attr_kind = d.u32()
            attrs[key_name] = str(d.u32()) if attr_kind == 1 else _text(d.string())
        for _ in range(d.u32()):    # access control list: which programs may read it; not kept
            d.u32()
            d.string()
            d.string()
            d.string()
            d.u32()
            d.u32()
        items.append({'label': label, 'attrs': attrs, 'secret': secret, 'created': created,
                      'modified': modified, 'type': ITEM_TYPES.get(kind, '')})
    return name, ctime, mtime, items


def import_items(vault, collection, items):
    """Copy the items in. An item already there (same attributes and label; for an item with no
    attributes, same label and secret) is left as it is, so running the import twice adds nothing.
    Returns (added, skipped)."""
    added = skipped = 0
    for it in items:
        same = None
        for old in collection.items.values():
            if it['attrs']:
                if old.attrs == it['attrs'] and old.label == it['label']:
                    same = old
                    break
            elif not old.attrs and old.label == it['label'] and old.secret == it['secret']:
                same = old
                break
        if same is not None:
            skipped += 1
            continue
        vault.create_item(collection, it['label'], it['attrs'], it['secret'],
                          item_type=it['type'], created=it['created'] or None,
                          modified=it['modified'] or None)
        added += 1
    return added, skipped
