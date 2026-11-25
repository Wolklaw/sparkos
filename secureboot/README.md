# Secure Boot certificate for SparkOS's kernel modules

`sparkos-kmods.der` goes here: the public certificate (DER) of the key that signs the
out-of-tree kernel modules (`build_files/kmods.sh`). The image build ships it as
`/usr/share/sparkos/secureboot/sparkos-kmods.der`, and `spark secureboot enroll` enrolls it.

It is public. The private key is never committed; it lives in the `KMOD_SIGNING_KEY` GitHub
Actions secret. Make both with `build_files/make-kmod-key.sh` (steps in docs/building.md).

Until the file exists the image has no certificate and the modules stay unsigned.
