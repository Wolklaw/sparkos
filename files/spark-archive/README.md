# Spark Archive

Open, extract and make archives on SparkOS. It reads zip, tar (plain, gz, bz2, xz, zst), 7z, rar and iso, plus single `.gz`, `.bz2`, `.xz` and `.zst` files and anything else libarchive knows (tar.lz, tar.lz4, tar.Z, cpio, cab...), also when they come in several parts. It makes zip, 7z and tar.zst, zip and 7z with a password. In English and French. It is meant to replace Ark.

- **Double-click an archive:** the window lists what's inside as folders you can open, with sizes and dates. **Extract all**, **Extract selected**, or **Extract to…** a folder you pick; double-click a file to open just that file with its usual app. **Compress files** picks files and makes a .zip, .7z or .tar.zst next to them, with a password if you turn on **Protect with a password**.
- **Dolphin's right-click menu:** on archives, **Extract ▸ Extract here** and **Extract ▸ Extract to folder**; on any files and folders, **Compress ▸ Compress to .zip**, **to .7z**, **to .tar.zst** and **Compress with a password…** (asks zip or 7z, and the password twice). These open a small window with progress and Cancel, which closes by itself when everything went through cleanly (and never appears for a job that takes under a third of a second).
- **Passwords, opening:** zip (ZipCrypto and AES), 7z, and RAR 4 and 5, including 7z and RAR archives whose file names are encrypted too. It asks, and asks again if the password is wrong.
- **Passwords, making:** zip with AES-256 (7-Zip and most archive apps open it; some built-in zip tools, like Windows Explorer's, can't), and 7z with AES-256 and the file names hidden too. tar.zst can't have a password.
- **Archives in several parts:** `photos.7z.001`, `.002`… (any archive cut into pieces), `photos.part1.rar`, `.part2.rar`… (also `part01`), the older `photos.rar`, `.r00`, `.r01`…, and split zip `photos.z01`, `.z02`…, `photos.zip`. Open any part and you get the whole set; Extract to folder names the folder `photos`. If a part isn't there it says which one, the last one included: a 7z records its full size, every RAR volume says whether another follows, and a split zip's last part says how many came before it. Selecting every part in Dolphin and choosing Extract extracts the set once.
- **French:** the whole interface, chosen from your language settings (`LC_ALL`, `LC_MESSAGES` or `LANG` starting with `fr`). `SPARK_LANG=en` or `SPARK_LANG=fr` overrides it.
- **Overwriting:** if a file is already there it asks: Replace, Skip, Keep both (`name (2).txt`) or Cancel, with "Do this for every file".
- **Cancel** at any time. What that extraction had written is removed again, and a folder it made goes too. A file it was replacing stays whole until its new version is complete, so Cancel never leaves a half file.

Where things go: **Extract here** puts the contents in the archive's folder. **Extract to folder**, **Extract all** and **Extract selected** put them in a new folder named after the archive (`photos.zip` → `photos/`, or `photos (2)/` if that exists). When the archive already holds just one folder with that name, it isn't doubled into `photos/photos/`. Show in folder opens the folder that was made.

## Safe extraction

Nothing an archive contains can land outside the folder it is extracted to. The rules are in [sparkarchive/safety.py](sparkarchive/safety.py) and apply to every format alike, because every file is written by Spark Archive's own writer:

- Names are cleaned first: backslashes count as separators, a leading `/` or drive letter is dropped (`/etc/passwd` becomes `etc/passwd` inside the folder), and a name with a `..` part is left out, even one that would stay inside.
- Folders are walked one part at a time through open folder handles with `O_NOFOLLOW`, so nothing is ever written through a link, whether the archive made it a moment ago or it was already in your folder.
- A link from the archive is made only if its target is relative, stays inside, and has `..` only at its start (`x/../y` is refused: `x` could be a link itself). When the extraction is done, every link made is resolved once more and removed if it leads out.
- Hard links may only point at a file the same extraction wrote.
- Files are written under a temporary name and moved into place when complete.
- Devices, pipes and sockets are left out; setuid, setgid and sticky bits are dropped; your umask applies.
- Before writing, it checks the disk has room for what the archive says it holds.

Whatever was left out is listed at the end with the reason ("its path leads outside the folder", "a link that points outside the folder"...), and the window lists such entries in pink before you extract.

## How it reads each format

| Format | Read with | Notes |
|---|---|---|
| zip | Python's `zipfile` | AES-encrypted zip goes to libarchive, then the 7z command |
| tar, tar.gz, .bz2, .xz | Python's `tarfile` | |
| tar.zst | Python's `tarfile` with `compression.zstd` (Python 3.14+) | libarchive otherwise |
| 7z, iso, others | libarchive, loaded in-process with ctypes | password-protected 7z goes to the 7z command |
| rar | libarchive | password-protected RAR (and RAR with encrypted names) goes to the unrar command |
| .7z.001 … | libarchive, given every part | then the 7z command |
| .part1.rar …, .rar + .r00 … | libarchive, given every part | then unrar |
| .z01 … + .zip | the 7z command | Python's zipfile and libarchive don't read split zip |

libarchive is already in SparkOS because rpm, ostree, rpm-ostree and flatpak need it, so it stays when Ark goes. The **7z command** (Fedora's `7zip` package, 7-Zip 26) is used for password-protected 7z, split zip, making 7z and password-protected zip, and as a last resort. The **unrar command** (RPM Fusion's `unrar`, already in the SparkOS image) is used only for password-protected RAR, since libarchive can't decrypt RAR and Fedora's 7-Zip has no RAR codec.

Both commands unpack into a hidden staging folder inside the target, and Spark Archive then moves each file into place through the same safe writer, refusing links that lead out and copying (never moving) any file the command made as a hard link. When you picked a few files, only those are unpacked into staging (if a command names a member differently than the listing did, it unpacks everything instead, so nothing you picked goes missing). 7-Zip 26 and unrar 7 have their own checks and refuse unsafe links and the writes through them; 7z's refusals are listed as left out ("the 7z command refused it as unsafe"). The password goes to the command on its standard input, never on the command line where other users could read it; for unrar without a password, standard input is closed, so a question for one ends it instead of waiting.

Making archives: zip with Python's `zipfile` (files that are already compressed, like JPEG, MP4 or other archives, are stored rather than compressed again, which is as small and much faster); tar.zst with `tarfile` and Python's zstd at level 3, using several threads where libzstd allows it, or the `zstd` command on an older Python. 7z, and zip with a password, with the 7z command (`-mx=5`; zip AES-256 with `-mem=AES256`; 7z with `-mhe=on` so the names are encrypted too), written in a private folder next to the result and moved into place when complete. Devices and pipes are left out and listed (7z would wait on a pipe forever), and so are files you can't read. Links are stored as links in all of them.

## Speed

The brief asks for a window well under a second and a window that never freezes. `spark-archive --bench 20 [ARCHIVE]` opens the window (and the archive), prints the time to first paint and to the finished listing, counted from the moment the process started (Python's own start-up included), and closes.

Measured by CI on 2026-11-20 (GitHub runner, Fedora 45, Python 3.15, Tk 9.0, Xvfb):

| | After the process starts |
|---|---|
| Window open, no archive (first paint) | 0.10 s |
| Window open with a 20 000-file zip listed | 0.24 s |

Listing and extracting run in a thread; the window reads their progress ten times a second, and the table only builds a folder's rows when you open it, so a big archive doesn't slow the window down. Not measured yet on the owner's PC.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
spark-archive [ARCHIVE]                   # the window
spark-archive --extract-here A.zip ...    # what Dolphin's menu runs
spark-archive --extract-folder A.zip ...
spark-archive --compress zip FILES...     # or 7z, or tar.zst
spark-archive --compress-password FILES...  # asks zip or 7z and a password first
spark-archive --list ARCHIVE              # what's inside, no window (any part of a set)
SPARK_LANG=fr spark-archive               # in French whatever the language settings
spark-archive --self-test                 # what it needs, and a real round trip; no display needed
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has (Python 3 with tkinter, libarchive). It installs to `~/.local/lib/spark-archive/`, `~/.local/bin/spark-archive`, `~/.local/share/applications/`, `~/.local/share/icons/` and the two Dolphin menus in `~/.local/share/kio/servicemenus/` (made executable: Plasma ignores a service menu in your home folder otherwise), and lists every file it wrote in `~/.local/lib/spark-archive/installed-files` for `--uninstall`. It does not make Spark Archive the default app for archives; that is the image's job (or Dolphin's **Open with**).

The system-wide install (the image build step, [files/scripts/spark-archive.sh](../scripts/spark-archive.sh)) puts the menus in `/usr/share/kio/servicemenus/` and fails the build if `--self-test` fails. The self-test compresses and extracts a zip, a tar.zst and (with the 7z command) a 7z for real, makes and opens a zip and a 7z with a password, reads the tar.zst back through libarchive, and checks that a zip with `../` and `/` names stays inside its folder. It also says whether unrar is there.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, formats, what it needs, how to install it).

The tests cover every format: zip, tar with each compression, 7z (plain, password-protected, encrypted names), zip with ZipCrypto and AES, RAR 5 and RAR 4 (plain, password-protected, RAR 5 with encrypted names), iso, the single compressed files, cpio through libarchive. Sets of parts: RAR 5 `.partN.rar` (and `part01`), RAR 4 `.rar` + `.r00` and `.partN.rar`, `.7z.001` (plain and password-protected), split zip; opening each part, and a missing first, middle and last part named. Making zip (AES-256) and 7z (names hidden, checked in the file's bytes) with a password and opening them again, a pipe left out instead of hanging 7z, the compress dialog. And every path-escape case: `../`, absolute and drive-letter names, backslashes, links pointing out (absolute, `..`, and the `x/../..` trick), writing through a link the archive made or one already in the folder, hard links out, devices and pipes, setuid bits. The hostile tar is run through all three readers (`tarfile`, libarchive and the 7z command); a hostile password-protected RAR through unrar, and hostile names in RAR volumes. That the 7z and unrar commands unpack only the picked files. That every French string has the same blanks as the English one, and the language rule. Then overwrite answers, Cancel, extract-to-folder naming, selections, the window and the progress window under Xvfb.

The 7z and zip password fixtures in `tests/fixtures` were made with 7-Zip. The RAR files (stored, AES-encrypted RAR 4 and 5, RAR 5 with encrypted names, RAR 4 and 5 volumes), split zips and the ISO are written by [tests/makers.py](tests/makers.py) from the published format notes (rarlab's technote, and unrar's source for how a password becomes a key) with a small pure-Python AES, since there is no free RAR writer and rarlab's `rar` may not be redistributed. They were checked with 7-Zip 26 (which has the RAR codec on Windows), and CI opens them with libarchive and unrar. CI ([workflow](../../.github/workflows/spark-archive.yml)) runs all of it in Fedora as root (with unrar from RPM Fusion), and inside the published SparkOS image as a normal user, where it also installs with `--user`, runs the self-test and uninstalls.

## Known gaps

- **Not tried on a SparkOS desktop yet.** CI runs the windows under Xvfb; nobody has right-clicked in Dolphin on real Plasma 6.8 with it yet. While Ark is still installed, Dolphin shows both Ark's Extract/Compress entries and these.
- **Dolphin's Extract menu isn't on every part.** `.7z.001`, `.rar` and `.part1.rar` have archive file types, but `.r00` and `.z01` parts don't, so Extract isn't offered on those. Opening them in the window works.
- **Making archives in several parts** isn't offered; opening them is.
- **RAR can't be made** (there is no free RAR writer). RAR is open-only, as in Ark.
- **Password-protected RAR needs unrar**, which comes from RPM Fusion (nonfree). It is in the SparkOS image today; if it ever leaves, those archives say the unrar command is needed instead of opening.
