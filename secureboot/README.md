# Secure Boot certificate for SparkOS's kernel modules

`sparkos-kmods.der` goes here: the public certificate (DER) of the key that signs the
out-of-tree kernel modules (`build_files/kmods.sh`). The image build ships it as
`/usr/share/sparkos/secureboot/sparkos-kmods.der`, and `spark secureboot enroll` enrolls it.

It is public. The private key is never committed; it lives in the `KMOD_SIGNING_KEY` GitHub
Actions secret. Make both with `build_files/make-kmod-key.sh` (steps in docs/building.md).

Made 2026-11-26. SHA-256 fingerprint:
`C8:FE:E4:0B:EC:E3:81:64:FE:AE:5A:A7:D5:BE:3D:E7:C6:94:A3:21:37:21:53:BA:52:6D:DA:B4:E0:ED:B7:62`

With the secret set, a build fails if this file is missing or doesn't match the key.
