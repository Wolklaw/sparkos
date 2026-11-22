# How SparkOS is built

SparkOS is one container image, `ghcr.io/wolklaw/sparkos:latest`, built from SparkOS's own
[Containerfile](../Containerfile) with plain `podman build`, signed with SparkOS's key, and
published by [build.yml](../.github/workflows/build.yml). Every SparkOS PC updates from it.

Until 2026-11-20 the image was built by [BlueBuild](https://blue-build.org) from a recipe. BlueBuild
was one more project SparkOS depended on ([PLAN.md, Independence roadmap](../PLAN.md)), and what it
generated for SparkOS was ordinary container build steps, so SparkOS now owns them: about 150 lines
of Containerfile and 250 lines of shell in [build_files/](../build_files). Before the switch the two
builds ran side by side and were compared (see [Before the switch](#before-the-switch)).

## The steps

| # | Step | What it does |
|---|---|---|
| 0 | `FROM … AS capslock-build` | compiles [sparkos-capslock](../files/sparkos-capslock) (Caps Lock toggles when pressed) on the same base with `gcc` and `libevdev-devel`; only the program goes into the image, in step 4 |
| 1 | `FROM ghcr.io/ublue-os/bazzite@sha256:…` | the base: the workflow resolves `bazzite:stable` to a digest when the build starts and records it in the labels |
| 2 | `COPY cosign.pub` | the public key updates are checked against, as `/etc/pki/containers/sparkos.pub` (named after the image) |
| 3 | [pre-build.sh](../build_files/pre-build.sh) | makes `/opt` a link to `/usr/lib/opt` during the build, so things installed in `/opt` land in the image |
| 4 | [copy-files.sh](../build_files/copy-files.sh) | copies `files/system/*` into the image root, then `sparkos-capslock` from step 0 to `/usr/libexec` |
| 5 | [packages.sh](../build_files/packages.sh) | removes 18 packages (other projects' apps, the KDE apps a Spark app replaces, Tailscale and Universal Blue's updater) and installs 23; the script says why each one is there |
| 6 | [run-scripts.sh](../build_files/run-scripts.sh) | runs SparkOS's scripts in `files/scripts`, in order, with `CONFIG_DIRECTORY=/tmp/files` |
| 7 | [flathub.sh](../build_files/flathub.sh) | two services, `system-flatpak-setup` and `user-flatpak-setup`, that add Flathub at boot and at login ([flathub-setup](../build_files/flathub-setup), 40 lines of shell); installs no apps |
| 8 | [signing.sh](../build_files/signing.sh) | the `sigstoreSigned` entry for `ghcr.io/wolklaw/sparkos` in `/etc/containers/policy.json`, and `registries.d/Wolklaw-sparkos.yaml`; if the base doesn't already make installs check signatures (Bazzite does), `/usr/lib/bootc/install/20-sparkos.toml` |
| 9 | [post-build.sh](../build_files/post-build.sh) | tmpfiles links for `/opt/*`, empties `/tmp` and `/var`, makes `/opt` the usual link into `/var`, hard-links the rpm database for rpm-ostree |
| 10 | `LABEL`s | title, description, source, base name and digest, build date, and `revision` (the SparkOS commit) |

Package caches are build-time cache mounts, so they never end up in the image. The workflow also
runs `bootc container lint` on the result, for information only (it's in each run's summary).

**Adding to the image:** a new package goes in [packages.sh](../build_files/packages.sh) (the list
for both bases, unless only one needs it); a new build script goes in `files/scripts/` and in the
list in step 6, in the right place (apps before `spark-update.sh`, `sparkos-theme.sh` last).

## The Fedora build

The same Containerfile also builds SparkOS on plain Fedora Kinoite, the test image
`ghcr.io/wolklaw/sparkos-fedora` ([fedora-base.md](fedora-base.md)). Three build arguments switch it:
`BASE_IMAGE=quay.io/fedora/fedora-kinoite:45`, `SPARKOS_BASE=fedora` and
`IMAGE_NAME=sparkos-fedora`. Only two steps differ by base:

- step 5, [packages.sh](../build_files/packages.sh): on Fedora, instead of removing Bazzite's apps,
  it adds what Bazzite brought (printing, scanning, ImageMagick, gamescope, MangoHud, GameMode,
  distrobox, btop, tmux and other tools, `umu-run` from Terra for that one package, and Fedora's
  device rule packages: `steam-devices`, `openrgb-udev-rules`, `solaar-udev`, `ntsync-autoload`)
  and RPM Fusion free's FFmpeg and Mesa video decode, so H.264 and H.265 play
- step 6: an entry `a.sh|b.sh` in the script list runs `a.sh` on Bazzite and `b.sh` on Fedora, and
  `-` means nothing. Fedora gets [fedora-identity.sh](../files/scripts/fedora-identity.sh),
  [fedora-apps.sh](../files/scripts/fedora-apps.sh) (removes Kinoite's apps),
  [fedora-gaming.sh](../files/scripts/fedora-gaming.sh) (the device rules Fedora doesn't package,
  from [files/device-rules](../files/device-rules), `uinput`, gaming kernel settings) and
  [fedora-homebrew.sh](../files/scripts/fedora-homebrew.sh) (Homebrew on PATH in bash, zsh and
  fish, when it's installed)

[build-fedora.yml](../.github/workflows/build-fedora.yml) runs build.yml with `base: fedora` on the
same pushes as the real build and every day at 06:30 UTC, then runs boot-test.yml on the result
with `image_name: sparkos-fedora` (the few checks about Bazzite's own parts are skipped). Because
nothing is copied, a change to main reaches both images.

## Tags

The same tags BlueBuild used, so the boot test, the installer and every PC keep working:

| Build | Tags |
|---|---|
| main (a push, the daily 06:00 UTC build, or Run workflow) | `<commit>-45`, `YYYYMMDD-45`, `YYYYMMDD`, `45`, `latest` |
| another branch | `br-<branch>-45` only, for testing with the boot test's `image_tag` |
| a pull request | built and checked, not pushed (Dependabot's and forks' PRs get no signing key) |

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

## Testing

[boot-test.yml](../.github/workflows/boot-test.yml) runs after every build of main: it installs the
image on a disk with image-builder, boots it in QEMU and checks it over SSH (everything on Sundays,
or by hand with "full"). A branch build can be tested before merging: Run workflow with
`image_tag` = `br-<branch>-45`. With `update_from` it installs that tag first, updates it to the
tested image the way a PC does (a signed `rpm-ostree rebase`, then a restart) and runs the checks on
the updated system.

Every run also signs in to Plasma in the VM and opens each app in the menu (the Spark apps, Soot
and FreeSuite) the way the menu does, then once more in French (Spark apps):
[.github/scripts/desktop-smoke.py](../.github/scripts/desktop-smoke.py) waits for KWin to show the
window, screenshots the screen through KWin, fails on a Python traceback, and closes the app. The
screenshots are in the run's `desktop-screenshots` artifact, and the run's summary has a table of
window titles and opening times. Branch test runs queue per branch, so they never cancel a run of
main's.

## Building it yourself

From the repo root on any Linux machine with podman (SparkOS has it):

```bash
sudo podman build -t localhost/sparkos:test .
```

Building as root is simplest (the steps install packages and set file ownership). It downloads the
Bazzite base (about 5.4 GB) and needs about 40 GB free. For the Fedora build, add
`--build-arg BASE_IMAGE=quay.io/fedora/fedora-kinoite:45 --build-arg SPARKOS_BASE=fedora --build-arg IMAGE_NAME=sparkos-fedora`. Check the result with
`sudo podman run --rm -it localhost/sparkos:test bash`, or install it in a VM with
[vm-test.md](vm-test.md).

## Before the switch

From 2026-11-20 the Containerfile was built next to BlueBuild, published only as a test tag
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

For honesty: Bazzite (the base, and through it Fedora and Universal Blue), podman and buildah (on
GitHub's runners), cosign and Sigstore's transparency log, GitHub Actions and the GitHub container
registry, and image-builder for the boot test. The base is what
[fedora-base.md](fedora-base.md) looks at.
