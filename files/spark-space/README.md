# Spark Space

See what takes the space on your drives. Pick a drive or folder; Spark Space measures it and shows a map of every folder (each block sized by what it holds), the largest files, a breakdown by type, and a few hints about space you can usually get back. Anything you no longer want goes to the trash, after you confirm. It never deletes anything for good.

It is an optional Spark app ([brief](../../briefs/spark-space.md)): not in the SparkOS image, installed per user without root.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

## What it shows

- **Start screen:** one card per drive (home, the system, each Windows drive SparkOS mounted) with used and free space, plus "Choose a folder". Read-only drives say so.
- **Map:** nested blocks, biggest first, coloured by type (video, images, games, AI models, archives...). Click selects, double-click goes in, Backspace or Alt+Up goes back out.
- **Folder:** the current folder's items with size, share of the folder, a bar and the file count.
- **Largest:** the biggest files anywhere under the scanned folder. **Types:** totals per kind of file; picking one lists its largest files.
- **Hints:** places that are often big and safe to clear, with what clearing them means: app caches, the trash, unused Flatpak runtimes, container images, the system log, the Steam shader cache, Steam downloads in progress. Hints only explain and, where there is one, show the command to run yourself; Spark Space runs none of them.
- Folders it can't read (other users', some system folders) are counted and listed, not guessed.

## How it measures

Sizes are space used on disk (allocated blocks), so sparse files and small files count as they really do. A file with several hard links is counted once. Symbolic links are not followed. The scan stays on the drive you picked: another drive mounted inside it is left out, so scanning `/` doesn't walk into D: or E:. On btrfs (the SparkOS system drive) sizes are before compression, so a compressed folder can show more than it takes.

The scan runs in a background thread (4 by default, `--threads N`); the window stays responsive and Cancel shows what was measured so far. On the owner's home folder (466,490 files, 42,571 folders, 231 GB) it took 2.7 s.

## What it can do

- **Open** (with the default app) and **Show in folder** (Spark Files selects the item; without it, the folder opens with `xdg-open`).
- **Move to trash**, after a confirm naming the item and its size. It uses the desktop's trash (the freedesktop.org one Spark Files and Dolphin use), so the item can be restored from there.

There is no delete, no "empty trash" and no cleaning by itself. The trash button is off, and the action refuses even if called, for:

- anything on the **D: drive** (`/var/mnt/d`, `/mnt/d`, or wherever SparkOS mounted D:), whatever its mount mode;
- any **read-only** drive, and any folder you can't write to;
- the system's own folders (`/`, `/usr`, `/etc`, `/var`, mount points...), your home folder itself and the scanned folder itself;
- what's already in the trash;
- Windows' own files at the top of a Windows drive (`Windows`, `Program Files`, `pagefile.sys`...).

## Install

Per user, no root (SparkOS):

```
bash install.sh --user
bash install.sh --user --uninstall
```

System-wide, with its dependencies (Python 3, Tk, xdg-utils) on Fedora:

```
sudo bash install.sh --deps
```

`spark-space --self-test` checks Python, Tk, the French text, a scan of a temporary folder and the D: rule, without a display. `spark-space PATH` opens straight on a folder; `spark-space --bench PATH` times a scan without a window.

Files: a log in `~/.local/state/spark-space/`. It keeps no settings and no scan results yet (`~/.config/spark-space/` and `~/.cache/spark-space/` are where they would go).

## Tests

```
python3 -m unittest discover -s tests
SPARK_LANG=fr python3 -m unittest discover -s tests
```

The window tests need a display (CI runs them under Xvfb). Every test writes only in temporary folders, including the trash test, which points the trash at a temporary folder.

## Licence

Published to read under the [SparkOS License](../../LICENSE). Not open source.
