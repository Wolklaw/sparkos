#!/usr/bin/bash
# Makes SparkOS's module-signing key and certificate, once. Run it on your own PC, not in CI.
#
#   build_files/make-kmod-key.sh [OUTPUT-FOLDER]     (default: ./sparkos-kmod-key)
#
# Writes in OUTPUT-FOLDER:
#   kmod-signing.key        PEM private key. Secret. Becomes the KMOD_SIGNING_KEY GitHub secret
#                           (gh secret set KMOD_SIGNING_KEY < kmod-signing.key). Keep a copy
#                           somewhere safe, then delete it from the PC; never commit it.
#   sparkos-kmods.der       the public certificate. Copy it to secureboot/sparkos-kmods.der in
#                           the repo and commit it.
# The certificate lasts 100 years: a key that expires would stop the modules loading.
# Losing or replacing the key means every PC enrolls the new certificate again.
set -euo pipefail

out=${1:-./sparkos-kmod-key}
[ ! -e "$out/kmod-signing.key" ] || { echo "make-kmod-key: $out/kmod-signing.key exists; not overwriting it" >&2; exit 1; }
mkdir -p "$out"
umask 077

# The extensions the kernel and shim want of a module-signing certificate: not a CA,
# digitalSignature, code signing, and a subject key id to match signatures against.
openssl req -new -x509 -newkey rsa:3072 -sha256 -nodes -days 36500 \
  -subj "/CN=SparkOS kernel modules/" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=digitalSignature" \
  -addext "extendedKeyUsage=codeSigning" \
  -addext "subjectKeyIdentifier=hash" \
  -keyout "$out/kmod-signing.key" -outform DER -out "$out/sparkos-kmods.der"
chmod 0600 "$out/kmod-signing.key"
chmod 0644 "$out/sparkos-kmods.der"

echo
echo "Made in $out:"
echo "  kmod-signing.key   SECRET. gh secret set KMOD_SIGNING_KEY --repo Wolklaw/sparkos < $out/kmod-signing.key"
echo "  sparkos-kmods.der  public. Copy to secureboot/sparkos-kmods.der and commit it."
openssl x509 -inform DER -in "$out/sparkos-kmods.der" -noout -subject -fingerprint -sha256
