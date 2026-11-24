"""Spark Apps' self-test: proves, with a throwaway key, that signature checks work on this
system (good signature accepted, tampered payload and wrong key refused) and that the launcher's
choice falls back to the built-in copy. Needs openssl; touches nothing outside a temp folder."""

import base64
import json
import os
import subprocess
import sys
import tempfile

from . import VERSION, index as index_mod
from .choose import select
from .paths import Paths


def _openssl(*args, data=None):
    return subprocess.run([index_mod.OPENSSL, *args], input=data, capture_output=True,
                          timeout=60, check=True).stdout


def main() -> int:
    print(f"Spark Apps {VERSION} self-test")
    failures = []
    if not os.path.exists(index_mod.OPENSSL):
        print(f"openssl:   MISSING ({index_mod.OPENSSL})")
        return 1
    print("openssl:   " + subprocess.run([index_mod.OPENSSL, 'version'], capture_output=True,
                                         text=True).stdout.strip())
    with tempfile.TemporaryDirectory(prefix='spark-apps-selftest-') as tmp:
        keys = {}
        for name in ('a', 'b'):
            private = os.path.join(tmp, f'{name}.key')
            public = os.path.join(tmp, f'{name}.pub')
            _openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256',
                     '-out', private)
            _openssl('pkey', '-in', private, '-pubout', '-out', public)
            keys[name] = (private, public)
        payload = json.dumps({'type': 'self-test'}).encode()
        payload_file = os.path.join(tmp, 'payload')
        with open(payload_file, 'wb') as f:
            f.write(payload)
        signature = base64.b64encode(_openssl('dgst', '-sha256', '-sign', keys['a'][0],
                                              payload_file)).decode()

        def accepted(data, key):
            try:
                index_mod.verify_signature(data, signature, key)
                return True
            except index_mod.IndexError_:
                return False

        checks = [("good signature accepted", accepted(payload, keys['a'][1])),
                  ("changed payload refused", not accepted(payload + b' ', keys['a'][1])),
                  ("wrong key refused", not accepted(payload, keys['b'][1])),
                  ("missing key refused", not accepted(payload, os.path.join(tmp, 'none')))]
        choice = select(Paths(tmp), 'spark-selftest')
        checks.append(("no live copy means the built-in one", choice.source == 'builtin'))
        for what, ok in checks:
            print(f"check:     {what}: {'yes' if ok else 'NO'}")
            if not ok:
                failures.append(what)
    key = Paths('/').key
    print(f"key:       {key} " + ("present" if os.path.isfile(key) else "not here (not an image)"))
    if failures:
        print("self-test FAILED: " + ', '.join(failures))
        return 1
    print("self-test passed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
