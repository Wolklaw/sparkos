# Spark Archive

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-archive/`, `install.sh` with `--deps` and `--user`, `spark-app.json`,
`--self-test`, tests, workflow, build step `files/scripts/spark-archive.sh`). Don't edit
`recipes/recipe.yml`, `boot-test.yml` or `sparkos-defaults.sh`; the main session wires it in and
removes Ark at merge. Say in the PR which MIME types it should own and whether Ark can go.

## Why

Ark (KDE's archive tool) is SparkOS's only zip handler. The owner wants as few ties to other
projects as possible and small, fast Spark tools ([PLAN.md, Independence roadmap](../PLAN.md)).

## What it does

- Double-click an archive: see what's inside (folders, sizes, dates), extract all or the selected
  files.
- Dolphin right-click menu (a KIO service menu, installed by the build step): **Extract here**,
  **Extract to folder**, and on files and folders **Compress to .zip** and **Compress to .tar.zst**.
- Formats: zip, tar (gz, bz2, xz, zst), 7z, rar (read), iso (read). Python's `zipfile`/`tarfile`
  where they're enough, `bsdtar` (libarchive) for 7z, rar and iso if it's in the image; check, and
  if a format needs a new package, name it and its size in the PR.
- Safe extraction: no paths escaping the target folder (`../`, absolute paths, symlinks pointing
  out), and a clear question before overwriting.
- Password-protected zip and 7z: ask for the password.
- Progress and Cancel for big archives; the window never freezes.

## Done when

CI passes in Fedora and inside `ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`),
tests cover every format and the path-escape cases, the build step and service menu exist, and a
PR from `spark-archive` is open for the owner.
