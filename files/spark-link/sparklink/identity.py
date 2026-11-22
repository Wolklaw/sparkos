"""This PC's long-term identity: an ECDSA P-256 key and a self-signed certificate made from it,
created on first run in ~/.local/share/spark-link/ (key.pem, cert.pem, id). The certificate's
SHA-256 is the fingerprint phones pin.

The key is made by the `openssl` command (in the SparkOS image) or, if that's missing, Python's
`cryptography` module. Nothing here is written by hand: the private key never leaves OpenSSL."""

import base64
import binascii
import hashlib
import os
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from .config import data_dir, private_dir, write_private

ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
FP_RE = re.compile(r'^[0-9a-f]{64}$')
DAYS = 36500


def new_id() -> str:
    return secrets.token_hex(16)


def fingerprint_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def pem_to_der(pem: str) -> bytes:
    return ssl.PEM_cert_to_DER_cert(pem)


def der_to_pem(der: bytes) -> str:
    return ssl.DER_cert_to_PEM_cert(der)


def short_fp(fp: str) -> str:
    """The key check shown for typing by hand: '3F2A 91C0 7D11 4E8B'."""
    head = fp[:16].upper()
    return ' '.join(head[i:i + 4] for i in range(0, 16, 4))


def cert_from_b64(text: str) -> Optional[bytes]:
    """A certificate sent in pair: standard base64 DER. None if it isn't plausibly one."""
    if not isinstance(text, str) or not 100 <= len(text) <= 16384:
        return None
    try:
        der = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(der) < 64 or der[0] != 0x30:
        return None
    try:
        ssl.DER_cert_to_PEM_cert(der)
    except (ValueError, TypeError):
        return None
    return der


def backend() -> Optional[str]:
    """How keys are made here: 'openssl', 'cryptography' or None."""
    if shutil.which('openssl'):
        return 'openssl'
    try:
        import cryptography.x509  # noqa: F401
        return 'cryptography'
    except ImportError:
        return None


def _make_openssl(key_path: str, cert_path: str, device_id: str) -> None:
    exe = shutil.which('openssl')
    if not exe:
        raise RuntimeError('openssl not found')
    cmd = [exe, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
           '-sha256', '-nodes', '-keyout', key_path, '-out', cert_path, '-days', str(DAYS),
           '-subj', f'/CN={device_id}']
    # a config of our own, so a system openssl.cnf can't add surprises (and Windows has none)
    folder = os.path.dirname(key_path)
    cnf = os.path.join(folder, 'req.cnf')
    with open(cnf, 'w', encoding='ascii') as f:
        f.write('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\n'
                '[ext]\nbasicConstraints=critical,CA:FALSE\n'
                'keyUsage=critical,digitalSignature\n'
                'subjectKeyIdentifier=hash\n')
    cmd += ['-config', cnf]
    env = dict(os.environ, OPENSSL_CONF=cnf)
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                          timeout=60)
    if done.returncode != 0 or not os.path.isfile(cert_path):
        raise RuntimeError('openssl failed: ' + done.stderr.decode('utf-8', 'replace')[-400:])


def _make_cryptography(key_path: str, cert_path: str, device_id: str) -> None:
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, device_id)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def make_key_and_cert(folder: str, device_id: str) -> None:
    """Write key.pem and cert.pem into folder (made private first). Raises on failure."""
    private_dir(folder)
    work = tempfile.mkdtemp(prefix='.new-', dir=folder)
    try:
        os.chmod(work, 0o700)
        key_tmp, cert_tmp = os.path.join(work, 'key.pem'), os.path.join(work, 'cert.pem')
        how = backend()
        if how == 'openssl':
            _make_openssl(key_tmp, cert_tmp, device_id)
        elif how == 'cryptography':
            _make_cryptography(key_tmp, cert_tmp, device_id)
        else:
            raise RuntimeError("can't make a key: neither the openssl command nor Python's "
                               "cryptography module is here")
        # prove the pair loads before keeping it
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_tmp, key_tmp)
        for name in ('key.pem', 'cert.pem'):
            with open(os.path.join(work, name), 'rb') as f:
                write_private(os.path.join(folder, name), f.read())
    finally:
        shutil.rmtree(work, ignore_errors=True)


@dataclass
class Identity:
    id: str
    key_path: str
    cert_path: str
    cert_der: bytes

    @property
    def fp(self) -> str:
        return fingerprint_der(self.cert_der)

    @property
    def cert_b64(self) -> str:
        return base64.b64encode(self.cert_der).decode('ascii')


def load_or_create(folder: Optional[str] = None) -> Identity:
    folder = private_dir(folder or data_dir())
    id_path = os.path.join(folder, 'id')
    key_path, cert_path = os.path.join(folder, 'key.pem'), os.path.join(folder, 'cert.pem')
    device_id = ''
    try:
        with open(id_path, encoding='ascii') as f:
            device_id = f.read().strip()
    except (OSError, UnicodeDecodeError):
        pass
    if not ID_RE.match(device_id):
        device_id = new_id()
        write_private(id_path, (device_id + '\n').encode('ascii'))
        for stale in (key_path, cert_path):          # a new id gets a new key
            try:
                os.unlink(stale)
            except FileNotFoundError:
                pass
    if not (os.path.isfile(key_path) and os.path.isfile(cert_path)):
        make_key_and_cert(folder, device_id)
    with open(cert_path, encoding='ascii') as f:
        der = pem_to_der(f.read())
    return Identity(device_id, key_path, cert_path, der)
