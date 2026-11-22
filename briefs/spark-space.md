# Spark Space: disk usage

Optional Spark app. Not in the image; installs per user with `install.sh --user`.

## Why

The owner's drives fill up with games, AI models, videos and caches, and KDE's tools for finding out
where the space went (Filelight, Dolphin's folder sizes) are third-party apps the owner wants to
replace with Spark apps. Spark Space answers one question fast: what takes the room, and can it go.

## What

- A start screen with one card per drive (home, system, each Windows drive SparkOS mounts) showing
  used and free space, and a folder picker.
- A scan in background threads: space used on disk (allocated blocks), hard links counted once,
  symlinks not followed, other drives mounted inside left out, unreadable folders counted. Cancel
  keeps what was measured. The window never waits on the scan.
- Results: a treemap (blocks coloured by kind of file; click, double-click to go in, back out), the
  current folder's list, the largest files, totals per type, and hints for space that is usually safe
  to get back (caches, trash, unused Flatpak runtimes, container images, system log, Steam shader
  cache and unfinished downloads). Hints explain and show a command; the app runs none of them.
- Open, Show in folder (Spark Files, else `xdg-open` on the parent) and Move to trash, after a
  confirm, through the freedesktop.org trash.

### Safety rules (owner's)

- Never a permanent delete. There is no delete or empty-trash code in the package; a test fails if
  `rmtree`, `os.remove`, `os.rmdir`, `shutil.move` or `unlink` appears in it (the one exception:
  the trash code removes its own `.trashinfo` note when a move fails).
- The D: drive is look-only: `/var/mnt/d`, `/mnt/d`, and wherever SparkOS's Windows-drive list says D:
  is mounted, whatever the mount mode.
- No trash on a read-only mount or in a folder the user can't write to.
- Also refused: system folders, mount points, the home folder and scanned folder themselves, what's
  already in a trash, and Windows' own top-level files on a Windows drive.

## Status

Built 2026-11-22 in [files/spark-space](../files/spark-space); PR open. Optional, not in the image.

- 33 unit and window tests pass under Xvfb in English and French (in a local Fedora container, not
  yet in CI). The self-test passes on the owner's PC.
- On the owner's home folder (466,490 files, 42,571 folders, 231 GB) the scan takes 2.7 s.
- The window was driven on the owner's PC only to scan and view; it has only been seen under Xvfb
  (the session's rootless Xwayland doesn't map test windows). Moving to the trash has only been tried
  in temporary folders.

Open questions for the owner:

- Keep the Windows system-file refusal (Windows, Program Files, pagefile.sys... on C: and E:)?
- Scanning `/` or `/var` as a normal user shows many unreadable folders. Running it as root is not
  offered; is that right?
- On btrfs, sizes are before compression. Showing compressed sizes would need `compsize` or root.
