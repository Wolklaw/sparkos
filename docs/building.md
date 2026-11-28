# How SparkOS is built

SparkOS is two container images built from SparkOS's own [Containerfile](../Containerfile) with
plain `podman build`, signed with SparkOS's key, and published by
[build.yml](../.github/workflows/build.yml):

- `ghcr.io/wolklaw/sparkos:latest` for AMD and Intel graphics (the kernel's own drivers and Mesa)
- `ghcr.io/wolklaw/sparkos-nvidia:latest` for Nvidia graphics: the same image plus Nvidia's driver
  (build-arg `GPU=nvidia`, see [nvidia.sh](../build_files/nvidia.sh)). It needs a GTX 16, RTX 20 or
  newer card, because it ships Nvidia's open kernel modules. It hasn't been tried on a real Nvidia
  PC yet.

Every SparkOS PC updates from the image it was installed with.

Until 2026-11-20 the image was built by [BlueBuild](https://blue-build.org) from a recipe. BlueBuild
was one more project SparkOS depended on ([PLAN.md, Independence roadmap](../PLAN.md)), and what it
generated for SparkOS was ordinary container build steps, so SparkOS now owns them: about 150 lines
of Containerfile and 250 lines of shell in [build_files/](../build_files). Before the switch the two
builds ran side by side and were compared (see [Before the switch](#before-the-switch)).

## The steps

| # | Step | What it does |
|---|---|---|
| 0 | `FROM … AS capslock-build` | compiles [sparkos-capslock](../files/sparkos-capslock) (Caps Lock toggles when pressed) on the same base with `gcc` and `libevdev-devel`; only the program goes into the image, in step 4 |
| 0b | `FROM … AS kmods-build` | builds the out-of-tree kernel modules ([kmods.sh](../build_files/kmods.sh): Xbox wireless, racing wheels, zenergy, ryzen_smu, v4l2loopback, vhba) against the base's kernel, from pinned commits; for the Nvidia image also Nvidia's open modules from RPM Fusion's akmod ([nvidia.sh](../build_files/nvidia.sh)) |
| 1 | `FROM quay.io/fedora-ostree-desktops/base-atomic@sha256:…` | the base, Fedora base-atomic 45 (Fedora's atomic desktop image without a desktop): the workflow resolves the Containerfile's `BASE_IMAGE` tag to a digest when the build starts and records it in the labels. Until 2026-11-26 it was Fedora Kinoite, until 2026-11-23 Bazzite ([fedora-base.md](fedora-base.md)) |
| 2 | `COPY cosign.pub` | the public key updates are checked against, as `/etc/pki/containers/sparkos.pub` (named after the image) |
| 3 | [pre-build.sh](../build_files/pre-build.sh) | makes `/opt` a link to `/usr/lib/opt` during the build, so things installed in `/opt` land in the image |
| 4 | [copy-files.sh](../build_files/copy-files.sh) | copies `files/system/*` into the image root, then `sparkos-capslock` from step 0 to `/usr/libexec` |
| 5 | [packages.sh](../build_files/packages.sh) | installs what base-atomic lacks for a desktop, gaming and everyday use (printing, scanning, the gaming layer, tools, fonts), RPM Fusion's full FFmpeg and Mesa video drivers, umu-launcher from Terra, and SparkOS's own list (ROCm only in the AMD image); the script says why each one is there |
| 5b | [kmods.sh](../build_files/kmods.sh) `install` | puts the modules from step 0b in `/usr/lib/modules/<kernel>/extra` with their firmware and udev rules; stops the build if the kernel changed in between; the Nvidia image also gets the driver's userspace of the same version, the nouveau blacklist and `nvidia-drm.modeset=1` |
| 6 | [run-scripts.sh](../build_files/run-scripts.sh) | runs SparkOS's scripts in `files/scripts`, in order, with `CONFIG_DIRECTORY=/tmp/files`: identity, removing the base's few third-party apps, the gaming device rules and kernel settings, tuning, Homebrew's shell setup, the parity tools, then Soot, FreeSuite, the Spark apps and the theme |
| 7 | [flathub.sh](../build_files/flathub.sh) | two services, `system-flatpak-setup` and `user-flatpak-setup`, that add Flathub at boot and at login ([flathub-setup](../build_files/flathub-setup), 40 lines of shell); installs no apps |
| 8 | [signing.sh](../build_files/signing.sh) | the `sigstoreSigned` entry for `ghcr.io/wolklaw/sparkos` in `/etc/containers/policy.json`, and `registries.d/Wolklaw-sparkos.yaml`; and `/usr/lib/bootc/install/20-sparkos.toml`, so installs deploy the image as signed |
| 9 | [post-build.sh](../build_files/post-build.sh) | tmpfiles links for `/opt/*`, empties `/tmp` and `/var`, makes `/opt` the usual link into `/var`, hard-links the rpm database for rpm-ostree |
| 10 | `LABEL`s | title, description, source, base name and digest, build date, and `revision` (the SparkOS commit) |

Package caches are build-time cache mounts, so they never end up in the image. The workflow also
runs `bootc container lint` on the result, for information only (it's in each run's summary).

**Adding to the image:** a new package goes in [packages.sh](../build_files/packages.sh); a new build script goes in `files/scripts/` and in the
list in step 6, in the right place (apps before `spark-update.sh`, `sparkos-theme.sh` last).

## Tags

The same tags BlueBuild used, so the boot test, the installer and every PC keep working. Both images
get the same tags, each in its own repository (`sparkos` and `sparkos-nvidia`):

| Build | Tags |
|---|---|
| main (a push, the daily 06:00 UTC build, or Run workflow) | `<commit>-45`, `YYYYMMDD-45`, `YYYYMMDD`, `45`, `latest` |
| another branch (Run workflow on it; a push to a branch doesn't build) | `br-<branch>-45` only, for testing with the boot test's `image_tag` |
| a pull request (only if it touches the Containerfile, build_files, files/ outside a Spark app's folder, or an app's install.sh or spark-app.json) | built and checked, not pushed (Dependabot's and forks' PRs get no signing key) |

## Signing

- The first tag is pushed, then signed by digest with the private key in the `SIGNING_SECRET`
  repo secret:
  `cosign sign --key=env://COSIGN_PRIVATE_KEY --new-bundle-format=false --use-signing-config=false --recursive ghcr.io/wolklaw/sparkos@<digest>`.
  `--new-bundle-format=false` matters: rpm-ostree and bootc look for the classic signature (a
  `sha256-<digest>.sig` tag next to the image), which is what `use-sigstore-attachments: true` in
  `registries.d` points them to. cosign comes from `sigstore/cosign-installer`, pinned by commit.
- `cosign verify --key=cosign.pub` then checks it, the same check a SparkOS PC makes with
  `/etc/pki/containers/sparkos.pub`.
- Only then do the other tags, `latest` included, move to that digest (a manifest copy, so the
  digest and its signature stay the same). A PC never sees a `latest` whose signature isn't there yet.

## Module signing (Secure Boot)

The out-of-tree kernel modules ([kmods.sh](../build_files/kmods.sh)) are signed in step 4b so
they load with Secure Boot on. The public certificate is [secureboot/sparkos-kmods.der](../secureboot);
the private key is the `KMOD_SIGNING_KEY` repo secret, handed to `podman build` as a build secret
(written to a file in the runner's temp folder and passed as `--secret id=kmod_signing_key,src=...`;
`env=` doesn't work there because `sudo` drops the step's environment) and mounted only in that step, so it is in no
layer. No secret (a PR from a fork, Dependabot, a local build): the build logs `NOT SIGNING` and
leaves the modules unsigned. With the secret, the build fails if a module has no signer
(`modinfo -F signer`) or if the key isn't the certificate's.

Make the key once, on your own PC:

1. `build_files/make-kmod-key.sh ~/sparkos-kmod-key` writes `kmod-signing.key` (private) and
   `sparkos-kmods.der` (public).
2. `gh secret set KMOD_SIGNING_KEY --repo Wolklaw/sparkos < ~/sparkos-kmod-key/kmod-signing.key`
3. Copy `sparkos-kmods.der` to `secureboot/sparkos-kmods.der` and commit it. Never commit the key;
   keep a copy of it somewhere safe, then delete it from the PC.
4. Merge. The next build signs; on each SparkOS PC run `spark secureboot enroll` once.

A new key means every PC enrolls again. A local build can sign too: add
`--secret id=kmod_signing_key,src=PATH-TO-KEY`.

## Testing

[boot-test.yml](../.github/workflows/boot-test.yml) runs after every build of main: it installs the
image on a disk with image-builder, boots it in QEMU and checks it over SSH (everything on Sundays,
or by hand with "full"). A branch build can be tested before merging: Run workflow with
`image_tag` = `br-<branch>-45`. With `update_from` it installs that tag first, updates it to the
tested image the way a PC does (a signed `rpm-ostree rebase`, then a restart) and runs the checks on
the updated system.

Every run also signs in at the Spark Greeter in the VM (the password typed on the VM's keyboard)
and opens each app in the menu (the Spark apps, Soot and FreeSuite) in the Spark session, then once
more in French (Spark apps):
[.github/scripts/desktop-smoke.py](../.github/scripts/desktop-smoke.py) waits for the window in the
compositor's window list, screenshots the screen with grim, fails on a Python traceback, and closes
the app. The screenshots are in the run's `desktop-screenshots` artifact, and the run's summary has
a table of window titles and opening times. Branch test runs queue per branch, so they never cancel
a run of main's.

## Keeping it running

These workflows watch the distro between changes. Each one opens an issue when it finds a
problem, comments on that issue while the problem lasts, and closes it once it's fixed.

| Workflow | When | What it does |
|---|---|---|
| [build-watch.yml](../.github/workflows/build-watch.yml) | after each build of main | opens an issue when a build fails, naming the failed jobs and steps; the next passing build closes it |
| [package-checkup.yml](../.github/workflows/package-checkup.yml) | Mondays | the published image is over 2 days old, or packages are half-upgraded: starts a build and opens an issue |
| [pin-check.yml](../.github/workflows/pin-check.yml) | Wednesdays | moves the kernel-module pins in `build_files/kmods.sh` to their projects' newest commits ([tools/pin-check.sh](../tools/pin-check.sh)), opens a pull request on `bot/kmod-pins` and builds that branch. A pin from another branch is reported, not moved |
| [fedora-next.yml](../.github/workflows/fedora-next.yml) | Saturdays | trial build on the next Fedora (base-atomic:46 once Fedora branches it, rawhide before), nothing pushed; a failure opens an issue |
| [boot-test.yml](../.github/workflows/boot-test.yml) | after each build of main, full on Sundays | see Testing |

`tools/pin-check.sh` also runs locally: it reports without changing anything, and `--write`
rewrites the pins.

## Building it yourself

From the repo root on any Linux machine with podman (SparkOS has it):

```bash
sudo podman build -t localhost/sparkos:test .
# the Nvidia image
sudo podman build --build-arg GPU=nvidia --build-arg IMAGE_NAME=sparkos-nvidia -t localhost/sparkos-nvidia:test .
```

Building as root is simplest (the steps install packages and set file ownership). It downloads the
Fedora base-atomic image and needs about 40 GB free. Check the result with
`sudo podman run --rm -it localhost/sparkos:test bash`, or install it in a VM with
[vm-test.md](vm-test.md).

## Before the switch

This is the BlueBuild-to-Containerfile switch, on the Bazzite base. From 2026-11-20 the Containerfile was built next to BlueBuild, published only as a test tag
(`containerfile`), compared file by file with BlueBuild's image of the same commit and boot-tested
in full. The last comparison, [run 44756683699](https://github.com/Wolklaw/sparkos/actions/runs/44756683699),
against `53f54a8-45` (the first release), same Bazzite base:

| | BlueBuild | Containerfile |
|---|---|---|
| Packages | 2634 | 2634, **all the same** |
| `os-release`, kernel arguments, enabled units, `registries.d`, the signing key, `policy.json` | same | same |
| Paths only in one image | 22 | 3 |
| Download (compressed) | 5.43 GB | 5.18 GB |
| Size on disk | 13.18 GB | 12.44 GB |
| Build time on GitHub | about 7 minutes | about 7 minutes |

What PCs lose on their first update from a BlueBuild image, none of which SparkOS uses:
BlueBuild's CLI (`/usr/bin/bluebuild`), Nushell and its plugins (`/usr/libexec/bluebuild/nu`),
BlueBuild's Nushell Flatpak scripts and `bluebuild-flatpak-manager` (about 225 MB, stored twice in
BlueBuild's layers, hence the size difference), and BlueBuild's own cosign, which overwrote
Bazzite's `/usr/bin/cosign` (Bazzite's comes back). The two Flatpak services keep their names, so
their enable links stay valid. `sparkos-signing-fix.sh` went too: it only corrected the policy
entry BlueBuild's signing module wrote with a capital W; `signing.sh` writes it right.

All three full boot tests of the test tag passed, with boot and idle figures within the noise of
the test VM (13.7 to 22.1 s, 1216 to 1243 MB, against 20.1 s and 1240 MB for BlueBuild's image the
same day).

## What SparkOS still depends on

For honesty: Fedora (the base image and its packages), RPM Fusion (FFmpeg and the full Mesa video
drivers), Terra (umu-launcher and the VRAM booster), the upstream projects of the kernel modules,
podman and buildah (on GitHub's runners), cosign and Sigstore's transparency log, GitHub Actions and
the GitHub container registry, and image-builder for the boot test. Bazzite was the base until
2026-11-23; [fedora-base.md](fedora-base.md) has the move.
