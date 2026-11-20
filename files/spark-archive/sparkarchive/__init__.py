"""Spark Archive: open zip, tar (gz, bz2, xz, zst), 7z, rar and iso files, also in several
parts, extract them safely, and make zip, 7z and tar.zst archives, zip and 7z with a password.
Dolphin's right-click menu gets Extract here, Extract to folder, and Compress to .zip, .7z,
.tar.zst or with a password. English and French.

zip and tar are read with Python's own zipfile and tarfile; 7z, rar and iso with libarchive
(already in SparkOS for rpm, ostree and flatpak), loaded in-process. Password-protected 7z,
split zip, and anything libarchive can't decrypt go through the 7z command; password-protected
RAR through unrar. Every file is written by this package's own safe writer, never by an
outside tool straight into your folders.
"""

APP_NAME = "Spark Archive"
APP_SLUG = "spark-archive"       # command, folders, log names
APP_CLASS = "SparkArchive"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkArchive"
VERSION = "1.1.0"
