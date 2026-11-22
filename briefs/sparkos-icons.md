# SparkOS icons

Read [README.md](README.md) first for the conventions every Spark app follows, and load the `wolklaw-design`
skill: the house style (dark, sharp 3px corners, magenta/cyan channel slip as the only decoration) applies to
icons too.

## Why

The Spark apps have their own icons, but most of what the owner looks at every day still comes from Breeze
or from the apps' authors: the app launcher button, Dolphin, Konsole, Bazaar, folders, file types, the system
tray. Next to Soot, FreeSuite and Spark Games on the taskbar they look like they belong to another system.

## What

A SparkOS icon theme, `SparkOS`, installed in the image and set as the default. It **inherits `breeze-dark`**,
so anything it doesn't draw yet still has an icon. Each batch below replaces more of Breeze, and each one is
its own session and its own PR.

1. **Theme and the taskbar** (do this first): the theme folder, `index.theme`, the build step that installs it,
   the default setting for new users and the existing user, a short style sheet (`docs/icons.md`: grid, stroke
   widths, the palette from the house style, how the slip is used, sizes) and the icons you see first:
   the app launcher button (`start-here` and Bazzite's own name for it), Dolphin, Konsole, Bazaar, System
   Settings, Steam, the Trash, and the default folder icon.
2. **Folders and places:** Home, Desktop, Documents, Downloads, Music, Pictures, Videos, Games, the Windows
   drives (SparkOS mounts them at /var/mnt/<letter>), network, removable drives, and the Dolphin sidebar.
3. **File types:** the ones the owner opens most: text, code (Python, JS/TS, HTML, CSS, shell, C#), archives,
   images, audio, video, PDF, office documents, .exe/.msi (Spark Run), APK, ISO, fonts, and a generic file.
4. **System tray and status:** network, Bluetooth, volume, battery, updates (Spark Update), notifications,
   Caps Lock. Some of these are Plasma theme SVGs rather than icon-theme icons; find out which and say so.

Apps that ship their own icon on purpose keep it: the Spark apps, Soot, FreeSuite, and Nova (a per-user app
that is never part of the image; its icon lives in the Nova repo).

## Rules

- Original drawings only, made for SparkOS. Don't trace or copy Breeze, Papirus or any other icon set, or
  any app's logo. An app icon may hint at what the app does; it must not imitate the app's brand.
- SVG, one file per icon, readable and hand-editable. Draw the small sizes (16, 22, 24) as their own files
  where the big one doesn't read at that size; symbolic (`-symbolic`) versions for the tray and toolbars.
- Dark-first, but check every icon on a light background too.
- License: the same as the rest of SparkOS's own artwork; add a line to THIRD-PARTY.md only if something
  outside SparkOS is used (fonts, for example).

## Tests

- CI: the theme's `index.theme` parses, every directory it lists exists, every SVG is valid and renders at
  16, 22, 32, 48 and 256 px (`rsvg-convert`), and a contact sheet PNG of the batch is uploaded as an artifact
  so the owner can look at it before merging.
- The boot test: the theme is the default for a new user, and `kreadconfig6 --group Icons --key Theme`
  says `SparkOS`.

## Done when (each batch)

CI passes, the contact sheet is in the PR, and the PR is open for the owner. Batch 1 also changes the default
theme; later batches only add icons.
