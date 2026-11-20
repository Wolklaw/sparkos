# Building SparkOS without BlueBuild

SparkOS is built today by [BlueBuild](https://blue-build.org) from
[recipes/recipe.yml](../recipes/recipe.yml) ([build.yml](../.github/workflows/build.yml)), and that's
the image every SparkOS machine updates from (`ghcr.io/wolklaw/sparkos:latest`).

Next to it, SparkOS now has its own [Containerfile](../Containerfile), which builds the same image
from the same Bazzite base with plain `podman build`. It's built by
[build-containerfile.yml](../.github/workflows/build-containerfile.yml) and published **only** as
`ghcr.io/wolklaw/sparkos:containerfile`, never `latest`, so no machine changes. Switching the real
build over is the owner's call; [the end of this page](#whats-left-before-switching) lists what
that takes.

Why: BlueBuild is one of the projects SparkOS depends on ([PLAN.md, Independence
roadmap](../PLAN.md)). Most of what it generates is ordinary container build steps, which SparkOS can
own in about 130 lines of Containerfile and 250 lines of shell (plus the Python that checks and
compares the two builds).

## What BlueBuild does for SparkOS today

Read from the log of a real build (BlueBuild CLI v0.9.42, run 44688094563 on main, 2026-11-20) and
BlueBuild's public templates and modules. For this recipe, BlueBuild generates a Containerfile with
these steps:

| # | BlueBuild step | What it does | In SparkOS's Containerfile |
|---|---|---|---|
| 1 | `FROM ghcr.io/ublue-os/bazzite@sha256:…` | the base, `bazzite:stable` resolved to a digest when the build starts | same; the workflow resolves the digest and records it in the labels |
| 2 | Key RUN | copies `cosign.pub` to `/etc/pki/containers/sparkos.pub` | `COPY cosign.pub …` |
| 3 | Bin RUN | copies **`/usr/bin/cosign`** and **`/usr/bin/bluebuild`** (BlueBuild's own CLI) into the image | not done (nothing on SparkOS uses them) |
| 4 | Nushell RUN | copies **Nushell** to `/usr/libexec/bluebuild/nu/` (BlueBuild's modules and its Flatpak services are written in it) | not done |
| 5 | `pre_build.sh` | makes `/opt` a link to `/usr/lib/opt` during the build, so things installed in `/opt` land in the image | [pre-build.sh](../build_files/pre-build.sh) |
| 6 | `files` module | `cp -rf files/system/* /` | [copy-files.sh](../build_files/copy-files.sh) `system /` |
| 7 | `dnf` module | `dnf makecache`, `dnf remove` the 13 apps, `dnf install` the 21 packages (weak dependencies on) | the same three `dnf` commands, written out in the Containerfile |
| 8 | `script` module | runs the 11 scripts in `files/scripts`, in order, with `CONFIG_DIRECTORY=/tmp/files` | [run-scripts.sh](../build_files/run-scripts.sh) with the same list |
| 9 | `default-flatpaks` module | installs two services (`system-flatpak-setup`, `user-flatpak-setup`, written in Nushell) that add Flathub at boot and at login, plus `bluebuild-flatpak-manager` and a config file; installs no apps | [flathub.sh](../build_files/flathub.sh): the same two service names, running [flathub-setup](../build_files/flathub-setup), a 40-line shell script |
| 10 | `signing` module | adds the `sigstoreSigned` entry to `/etc/containers/policy.json` and `registries.d/Wolklaw-sparkos.yaml` | [signing.sh](../build_files/signing.sh), Python instead of jq, already lowercase |
| 11 | `script` module | `sparkos-signing-fix.sh` (lowercases the policy entry BlueBuild writes as `ghcr.io/Wolklaw/sparkos`) | same script, same place; it finds the entry already right and checks it |
| 12 | `post_build.sh` | tmpfiles links for `/opt/*`, empties `/tmp` and `/var`, makes `/opt` the usual link into `/var`, hard-links the rpm database for rpm-ostree | [post-build.sh](../build_files/post-build.sh) |
| 13 | `LABEL`s | title, description, source, base name and digest, build date, BlueBuild's build id and README | the same, minus BlueBuild's two, plus `revision` (the SparkOS commit) |
| 14 | push, then `cosign sign` | pushes 5 tags, signs by digest (see below) | pushes one tag, `containerfile`, signs it the same way |

Package caches are build-time cache mounts in both, so they never end up in the image. BlueBuild
doesn't run `bootc container lint` (it's commented out in its `post_build.sh`); the workflow runs it
on the new image for information only (see the run summary).

Every step runs in the same order as under BlueBuild, with the scripts unchanged: they still find
the repo's files through `CONFIG_DIRECTORY`, so nothing in `files/` had to change.

### Keeping the two in step

While both builds exist, people edit the recipe. [check-recipe-sync.py](../build_files/check-recipe-sync.py)
runs first in every Containerfile build and fails it if the recipe and the Containerfile no longer
have the same base, the same packages removed and installed, or the same scripts in the same order,
and says what's missing. When the main session wires a new script into the recipe, the Containerfile
build goes red until the same line is added to the Containerfile.

## Signing

The workflow signs exactly the way BlueBuild does, with the same tools:

- cosign comes from `sigstore/cosign-installer`, pinned to the same commit BlueBuild's action uses.
- The command is the one in BlueBuild's cosign driver:
  `cosign sign --key=env://COSIGN_PRIVATE_KEY --new-bundle-format=false --use-signing-config=false --recursive ghcr.io/wolklaw/sparkos@<digest>`,
  with the private key from the `SIGNING_SECRET` repo secret. `--new-bundle-format=false` matters:
  rpm-ostree and bootc look for the classic signature (a `sha256-<digest>.sig` tag next to the
  image), which is what `use-sigstore-attachments: true` in `registries.d` points them to.
- Then `cosign verify --key=cosign.pub` against the public key in the repo, the same check a
  SparkOS machine makes with `/etc/pki/containers/sparkos.pub`.

Signatures are per digest, so signing the test tag adds a signature for that image only; it can't
affect `latest`.

## Building it yourself

From the repo root on any Linux machine with podman (SparkOS has it):

```bash
sudo podman build -t localhost/sparkos:test .
```

Building as root is simplest (the steps install packages and set file ownership). It downloads the
Bazzite base (about 5.4 GB) and needs about 40 GB free. The result can be checked with
`sudo podman run --rm -it localhost/sparkos:test bash`, or installed in a VM with
[vm-test.md](vm-test.md).

## How the two images compare

The `compare` job pulls the BlueBuild image built from the same commit (BlueBuild tags each build
`<commit>-45`) and the test tag, writes down what's in each without booting them
([dump-image.sh](../build_files/dump-image.sh)), and lists every difference
([compare-images.py](../build_files/compare-images.py)). The report is in each run's summary and in
its `image-comparison` artifact. Results of [run 44697821712](https://github.com/Wolklaw/sparkos/actions/runs/44697821712) (commit 225b2a6, 2026-11-20), both images
built from the same commit and the same Bazzite base (`sha256:492f83c7…`):

| | BlueBuild | Containerfile |
|---|---|---|
| Packages (`rpm -qa`, name, epoch, version, release, arch) | 2637 | 2637, **all the same** |
| Paths in `/etc` and `/usr` | 276,960 | 276,941 |
| Paths only in one image | 22 | 3 |
| Files with different contents | 91, none of them in `/etc` (see below) | |
| `os-release`, kernel arguments, enabled units, `registries.d`, the signing key | same | same |
| `policy.json` (the signing policy) | same | same, byte for byte |
| Download (compressed) | 5.42 GB in 267 layers | 5.18 GB in 265 layers |
| Size on disk | 13.17 GB | 12.44 GB |
| Build time on GitHub | about 7 minutes | about 7 minutes |

What differs, and why:

- **BlueBuild's own tools are only in the BlueBuild image** (the 22 paths): `/usr/bin/bluebuild`,
  Nushell and its plugins in `/usr/libexec/bluebuild/nu`, BlueBuild's Nushell Flatpak scripts,
  `bluebuild-flatpak-manager` and its config file. About 225 MB of files nobody on SparkOS uses.
- **cosign.** Bazzite ships `/usr/bin/cosign` as a link to `/usr/bin/cosign-linux-amd64`.
  BlueBuild's "Bin RUN" copies its own cosign (v3.1.4) to `/usr/bin/cosign`, which follows the link
  and replaces Bazzite's binary. The Containerfile image keeps Bazzite's. Nothing in SparkOS runs
  cosign on a machine (rpm-ostree checks signatures itself).
- **Size.** BlueBuild's steps 3 and 4 add those tools, and its `pre_build.sh` then changes their
  timestamps, which stores them a second time in the next layer: about 740 MB on disk and 250 MB
  of download that the Containerfile image doesn't have. Everything else is the same layers.
- **Three new paths** in the Containerfile image: `/usr/libexec/sparkos/flathub-setup` (the shell
  script that replaces BlueBuild's Nushell one) and the `/opt` tmpfiles rule named
  `99-sparkos-optfix-freesuite.conf` instead of `99-bluebuild-optfix-freesuite.conf` (same line
  inside).
- **The four Flatpak unit files** have the same names, timers and conditions; their descriptions
  and `ExecStart` point to SparkOS's script.
- **Files rebuilt at build time** (the rest of the 91): Python bytecode of the Spark apps (65 files;
  it records when each source file was checked out), font caches, the initramfs, the PNGs
  `sparkos-theme.sh` renders (ImageMagick writes the time into them), the dnf history and the rpm
  database (install times). These change between any two builds, BlueBuild's included.
- **Labels.** The Containerfile image has no `org.blue-build.build-id`, points its README label at
  SparkOS's README, and sets `revision` to the SparkOS commit (in the BlueBuild image it's Bazzite's
  commit, inherited from the base).
- **bootc's own check** (`bootc container lint`, which BlueBuild doesn't run): the same result for
  both, 13 checks passed and one warning, files left in `/run` (`/run/dnf`, `/run/selinux-policy`).
  `/run` is empty on a running machine, so it's harmless; the Containerfile could clear it later.
- In the first run ([run 44693412793](https://github.com/Wolklaw/sparkos/actions/runs/44693412793)),
  `policy.json` had the same entries in another order; the Containerfile now writes SparkOS's entry
  last, where BlueBuild's image ends up with it.

## Boot test

The `boot` job runs a copy of every step of [boot-test.yml](../.github/workflows/boot-test.yml)
(the full set, as on Sundays) against the test tag: it installs it on a disk with image-builder,
boots it in QEMU and checks over SSH. All of it passed in both runs
([run 44693412793](https://github.com/Wolklaw/sparkos/actions/runs/44693412793),
[run 44697821712](https://github.com/Wolklaw/sparkos/actions/runs/44697821712)): the system installs as `ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:containerfile` with the
`sigstoreSigned` policy, Soot's smoke test, FreeSuite, printing and scanning, the startup sound,
Claude Code, Spark Snip, Media, Welcome, Games and Monitor self-tests, no third-party apps, the
Store and the Windows-style installer, the SparkOS look and the desktop layout.

Boot and idle in the test VM, which is noisy (a nested VM on a shared runner): 22.1 s and 13.7 s
to start in the two runs, 1216 and 1243 MB of memory in use after boot, against 20.1 s and 1240 MB
for the BlueBuild image in the last real boot test. No measurable difference.

One check is added that isn't in boot-test.yml, because it's the only service in this image that
is SparkOS's code instead of BlueBuild's: both Flathub services ran after boot and login, finished
with status 0, and Flathub was listed for the system and for the test user.

## What's left before switching

Switching is the owner's decision. What it takes:

1. **The build workflow.** Make the Containerfile workflow push what `build.yml` pushes today:
   `latest`, `YYYYMMDD`, `45`, `YYYYMMDD-45`, `<commit>-45` on main; `br-<branch>-45` and
   `pr-<n>-45` on branches and pull requests (without `latest`); the daily 06:00 UTC schedule. Then
   delete `build.yml`.
2. **The boot test** starts on `workflow_run: workflows: [bluebuild]`; point it at the new
   workflow's name. Its steps don't change. The copy in `build-containerfile.yml` can then go.
3. **The recipe.** Move its comments (why each package is there) into the Containerfile, delete
   `recipes/recipe.yml` and `check-recipe-sync.py`, and remove the `/Containerfile` line from
   `.gitignore` (left over from BlueBuild's template; the Containerfile is committed with `git add -f`
   until then).
4. **`sparkos-signing-fix.sh`** only fixes what BlueBuild's signing module writes. The Containerfile
   writes the policy right in the first place, so the script can go once BlueBuild does (it does no
   harm until then).
5. **Docs.** README.md and PLAN.md say SparkOS is built with BlueBuild.
6. **First update on existing machines.** Moving from the BlueBuild image to this one is an
   ordinary update: same base, same packages. What machines lose is listed above (cosign,
   the BlueBuild CLI, Nushell, `bluebuild-flatpak-manager`); nothing in SparkOS uses them. The
   Flatpak services keep their names, so their enable links and the installer hook stay valid.
   Worth one VM run of `rpm-ostree rebase` from `latest` to `containerfile` before switching.

What SparkOS would still depend on after switching, for honesty: Bazzite (the base, and through it
Fedora and Universal Blue), podman/buildah (Ubuntu's, on GitHub's runners), cosign and Sigstore's
transparency log, GitHub Actions and the GitHub container registry, and image-builder for the boot
test. The base is what [sparkos-on-fedora](../briefs/sparkos-on-fedora.md) looks at.
