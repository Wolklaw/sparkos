# Spark Files

Read [README.md](README.md) first for the conventions every Spark app follows, and load the
`wolklaw-design` skill for the look.

## Why

The owner wants as little software from others as possible. Dolphin is the app SparkOS users open most
after the browser, and it's KDE's. Spark Files replaces it.

## What it does

- **Browse:** a sidebar (Home, Desktop, Documents, Downloads, Pictures, Music, Videos, Games, the Windows
  drives at /var/mnt/<letter>, removable drives, Trash, pinned folders), a path bar you can click or type
  in, back/forward/up, list and grid views, sort by name/date/size/type, hidden files toggle (Ctrl+H),
  thumbnails for images and videos (cached, made in the background), a preview pane.
- **Files:** open with the default app, Open With, copy, cut, paste, drag and drop (inside the app and with
  other windows), rename (F2, and batch rename), new folder, new file, move to Trash and restore, delete for
  good (Shift+Delete, confirmed), properties (size, dates, permissions), compress and extract through
  Spark Archive, "Open terminal here" (Spark Terminal), copy path.
- **Long jobs:** copying or moving big folders runs in the background with progress, pause and cancel, and
  asks about name clashes (replace, skip, keep both, apply to all).
- **Search:** filter the current folder as you type; Ctrl+F searches below it, by name.
- **Tabs and a split view** (F3), because the owner moves files between drives a lot.
- **Watching:** a folder updates by itself when its contents change (GIO file monitors).

## How

- Python 3 and Tk like the other Spark apps; Pillow for thumbnails; GIO (`gi.repository.Gio`, already in the
  image) for the Trash, mounts, file monitoring, default apps and content types. Nothing third-party beyond
  what the image has.
- **Becomes the system's file manager:** the default handler for `inode/directory`, and the
  `org.freedesktop.FileManager1` D-Bus service, so "Show in folder" from Soot, FreeSuite, downloads and other
  apps opens Spark Files at the right file.
- Speed rule from the README: a folder of 10,000 files lists in under a second; never block the window.
- File open/save dialogs inside other apps are Plasma's (KIO) and are not part of this app.

## Replacing Dolphin

Ship Spark Files in the image and on the dock, set it as the default, and hide Dolphin from the menu.
Dolphin stays installed for one release as a fallback; removing it is a separate PR once the owner has used
Spark Files daily without needing it.

## Tests

Unit tests for the file operations (copy/move/rename/trash with clashes, in a temp folder), the sorting and
filtering, and the thumbnail cache; UI tests under Xvfb; in the SparkOS image: `install.sh`, `--self-test`,
opening a folder from `xdg-open`, and "Show in folder" through the D-Bus service.

## Done when

CI passes on Fedora and inside the SparkOS image, Spark Files is the default file manager in a test build,
and the PR is open for the owner.
