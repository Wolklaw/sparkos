# SparkOS on plain Fedora (prototype)

Read [README.md](README.md) first. This is a **prototype on a separate image**; it must not change
the real SparkOS build. Work only in new files: `recipes/recipe-fedora.yml` (or a plain
`Containerfile.fedora`), `.github/workflows/build-fedora.yml`, `docs/fedora-base.md`, and any new
`files/scripts/fedora-*.sh`. Don't edit `recipes/recipe.yml`, `build.yml`, `boot-test.yml` or any
existing script. Publish only to `ghcr.io/wolklaw/sparkos-fedora`, never `sparkos`.

## Why

SparkOS is built on Bazzite (Universal Blue), its biggest remaining tie. The owner wants as few
ties to other projects as possible ([PLAN.md, Independence roadmap](../PLAN.md), Release 3: build on
Fedora's own atomic KDE image with SparkOS's own gaming layer). Bazzite does real work; this
prototype finds out exactly what SparkOS would have to own.

## What to do

1. List what Bazzite adds on top of Fedora Kinoite that SparkOS relies on: its kernel against
   Fedora's, Mesa and video codecs (what Fedora leaves out, and whose packages fill the gap: that
   is another tie), gamescope, MangoHud, GameMode, Steam udev rules, controller support, its
   hardware-setup service, firmware, Flathub setup, signing, the update service. Use the `inspect`
   workflow on `ghcr.io/wolklaw/sparkos:latest` and compare with `quay.io/fedora/fedora-kinoite`.
2. Build `ghcr.io/wolklaw/sparkos-fedora` from `quay.io/fedora/fedora-kinoite` (same Fedora
   version) with SparkOS's own layer: the real recipe's files and scripts where they work
   unchanged, plus what step 1 shows is needed for gaming on AMD. Sign it the same way.
3. Boot it in a VM the way `boot-test.yml` does (a test job inside `build-fedora.yml`; don't edit
   the original) and run the same checks.
4. Write `docs/fedora-base.md`: what works, what's missing, what each missing piece costs to own
   (and whose packages it would still need), image size and boot time against the Bazzite-based
   image, and a recommendation.

## Done when

The prototype image builds and boots in CI, the doc has real measurements, and a PR from
`sparkos-on-fedora` is open for the owner. Switching the real build is the owner's decision later.
