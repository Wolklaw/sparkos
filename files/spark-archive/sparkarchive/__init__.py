"""Spark Archive: open zip, tar (gz, bz2, xz, zst), 7z, rar and iso files, extract them safely,
and make zip and tar.zst archives. Dolphin's right-click menu gets Extract here, Extract to
folder, Compress to .zip and Compress to .tar.zst.

zip and tar are read with Python's own zipfile and tarfile; 7z, rar and iso with libarchive
(already in SparkOS for rpm, ostree and flatpak), loaded in-process. Password-protected 7z, and
anything libarchive can't decrypt, goes through the 7z command when it is installed. Every
file is written by this package's own safe writer, never by an outside tool straight into
your folders.
"""

APP_NAME = "Spark Archive"
APP_SLUG = "spark-archive"       # command, folders, log names
APP_CLASS = "SparkArchive"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkArchive"
VERSION = "1.0.0"
