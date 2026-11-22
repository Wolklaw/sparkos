# Build SparkOS without BlueBuild (side by side, not switched)

Read [README.md](README.md) first. This changes how the image is built, so it runs **next to** the
real build, not instead of it. Work only in new files: `Containerfile`, `build_files/` (or similar),
`.github/workflows/build-containerfile.yml`, `docs/building.md`. Don't edit `recipes/recipe.yml`,
`build.yml`, `boot-test.yml` or any existing script. Publish only to a test tag,
`ghcr.io/wolklaw/sparkos:containerfile` (never `latest`).

## Why

BlueBuild is the build tool: it turns `recipes/recipe.yml` into a Containerfile, runs its modules
(files, dnf, script, default-flatpaks, signing) and signs the image. It's another project in the
chain. The owner wants as few ties as possible ([PLAN.md, Independence roadmap](../PLAN.md)).
Most of what BlueBuild generates is plain container steps that SparkOS can own.

## What to do

1. Read what BlueBuild generates for this recipe (the build log prints the Containerfile; its
   modules are public) and list each step and what it does.
2. Write SparkOS's own `Containerfile` that produces the same image from the same base: copy
   `files/system`, install and remove the same packages with `dnf`, run the same scripts in the
   same order, set up Flathub, install the signing policy (and keep `sparkos-signing-fix.sh`'s
   result), and whatever cleanup BlueBuild does (`ostree container commit` or `bootc container
   lint`, caches).
3. A workflow that builds it, signs it with cosign using `SIGNING_SECRET` exactly like the real
   build, and pushes the test tag.
4. Compare the two images: package list (`rpm -qa`), `/etc` and `/usr` file lists, os-release,
   signing policy, size. Then boot the test tag with the boot test's steps (copied into your
   workflow) and run the same checks.
5. Write `docs/building.md`: how the image is built without BlueBuild, the comparison, and what's
   left before switching.

The prototype in `briefs/sparkos-on-fedora.md` (another session) changes the base image; this one
keeps Bazzite and changes only the build tool. Don't overlap: if you both need a Containerfile,
yours is `Containerfile`, theirs is separate.

## Done when

The test tag builds, is signed, matches the real image (differences listed and explained) and
passes the boot test's checks; `docs/building.md` is written; a PR from `build-without-bluebuild`
is open for the owner. Switching the real build is the owner's call later.
