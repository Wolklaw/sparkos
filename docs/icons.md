# SparkOS icons

SparkOS has its own icon theme, `SparkOS`, in [files/sparkos-icons/SparkOS](../files/sparkos-icons/SparkOS).
It **inherits Breeze Dark**: any icon it doesn't draw yet comes from Breeze, so nothing goes missing
while it grows. It is drawn in four batches ([brief](../briefs/sparkos-icons.md)); this page is the
style sheet every batch follows.

![Batch 1 contact sheet: each icon at 16, 22, 24, 32, 48 and 128 px, on the dark background and on a light one](icons-batch-1.png)

## What's drawn

| Batch | Icons | Status |
|---|---|---|
| 1. Theme and the taskbar | System Settings (`preferences-system`, `systemsettings`), Steam (`steam`, `com.valvesoftware.Steam`), generic app (`application-x-executable`, `application-default-icon`), folder (`folder`, `inode-directory`), Trash (`user-trash`, `user-trash-full`); symbolic versions of all but Steam | Done |
| 2. Folders and places | Home, Desktop, Documents, Downloads, Music, Pictures, Videos, Games, Windows drives, network, removable drives, the sidebar | Done (see "Batch 2" below) |
| 3. File types | text, code, archives, images, audio, video, PDF, office, .exe/.msi, APK, ISO, fonts, generic file (`unknown`) | Not started |
| 4. Tray and status | network, Bluetooth, volume, battery, updates, notifications, Caps Lock | Not started |

The Spark apps, Soot, FreeSuite and Nova keep the icons they ship; the theme never draws over them.

## Where it is set

- The image installs it at `/usr/share/icons/SparkOS` ([sparkos-icons.sh](../files/scripts/sparkos-icons.sh),
  just before `sparkos-theme.sh`).
- `/etc/xdg/kdeglobals` (`[Icons] Theme=SparkOS`) makes it the default for everyone who hasn't picked
  a theme, new users and existing ones. The SparkOS look-and-feel package says SparkOS too, so applying
  the SparkOS look keeps it.
- [sparkos-icons-default](../files/system/usr/libexec/sparkos-icons-default) runs once per user at
  sign-in: if the user's own settings say `breeze-dark` (the old SparkOS default, written there when the
  SparkOS look was applied), it removes that line so the SparkOS default applies from the next sign-in.
  Any other choice is left alone, and it never runs a second time.
- To go back: System Settings > Colors & Themes > Icons > Breeze Dark.

## Grid and sizes

| Folder | Grid | Used for |
|---|---|---|
| `scalable/` | 48 x 48 viewBox | 32 px and up (the taskbar at its default size, menus, file views) |
| `22/` | 22 x 22 | toolbars, the panel at small sizes |
| `24/` | the 22 px drawing with a 1 px margin (`viewBox="-1 -1 24 24"`) | 24 px requests, kept sharp |
| `16/` | 16 x 16 | lists, the file manager sidebar, menus |
| `symbolic/` | 16 x 16, one colour | toolbars and the tray (`-symbolic` names) |

- Small sizes are drawn again, not shrunk: fewer parts (two sliders instead of three, two wisps instead
  of three, two ribs instead of three), edges on whole pixels, 1 px lines.
- `24/` files are copies of `22/` with only the first two lines changed. After editing a 22 px icon,
  copy it again; [check.py](../files/sparkos-icons/check.py) fails when they differ.
- Aliases are symbolic links in the same folder (`inode-directory.svg -> folder.svg`).

## Shapes and strokes

- App icons sit on a tile: 3 px corners at 48 (2 at 22, 1.5 at 16), fill `#141233`, a 1 px edge of
  `#ece9ff` at 22% opacity. Places (folders, Trash) have no tile.
- Straight edges, square cuts (the folder tab is cut at 45 degrees), no gradients, no shadows, no
  rounded ends.
- Strokes at 48: 2 to 3 px; at 22 and 16: 1 px, or solid shapes. Prefer filled rectangles on whole
  pixels over strokes at the small sizes.

## Palette

From the house style (`wolklaw-design`, the web palette SparkOS's colour scheme uses):

| Use | Colour |
|---|---|
| tile | `#141233` (surface) |
| folder and bin body | `#2c2870`, folder back `#4a45a6` |
| the main mark of an icon | mint `#9be8b8` (SparkOS's accent) |
| secondary lines (slider tracks, bin ribs, text lines) | muted `#b3b0d2` |
| a third-party app's mark (Steam) | gold `#f4c95d`; lilac `#b9a6ff`, pink `#ff9ebb` and sky `#8ec9ff` if more are needed |
| paper in the full bin | lilac `#b9a6ff` and gold |
| the slip | magenta `#ff2e88`, cyan `#22d8ff` |
| symbolic icons | `currentColor` with the `ColorScheme-Text` class (`#f1efff` as written; Plasma swaps in the text colour) |

## The slip

The magenta/cyan channel slip is the only decoration, on one part of each icon, not all of it:

- a copy of that part in magenta shifted left and one in cyan shifted right, drawn under it:
  2 px at 48, 1 px at 22 and 16 (whole pixels only, so it stays sharp);
- on the sliders' knobs (System Settings), the vent (Steam), the window (generic app), the folder's
  top edge, the Trash lid;
- never on symbolic icons (one colour).

## Rules

- Original drawings only, made for SparkOS. Don't trace or copy Breeze, Papirus or any other set, or an
  app's logo. An app icon may hint at what the app does, never at its brand (Steam is vapour over a vent,
  not Valve's logo).
- SVG, one file per icon, written by hand to be read and edited: no editor metadata, no embedded
  bitmaps, no filters or masks (Plasma draws icons with Qt's SVG renderer, which supports the basics).
- Symbolic icons are filled shapes only (GTK recolours symbolic icons by forcing a fill).
- Check every icon on dark and on light. `python3 files/sparkos-icons/check.py --sheet sheet.png`
  checks the theme and draws the contact sheet; CI ([sparkos-icons.yml](../.github/workflows/sparkos-icons.yml))
  runs it on every change and uploads the sheet as an artifact.

## Batch 2: folders and places

![Batch 2 contact sheet: the places icons at 16, 22, 24, 32, 48 and 128 px, on the dark background and on a light one](icons-batch-2.png)

Spark Files draws its own sidebar and file icons in Tk (`sparkfiles/icons.py`) and asks the theme for
no names. These icons are for everything else that asks the theme: Plasma's Places panel and file
dialogs, other apps' sidebars, the desktop's removable-device notifications and Spark apps that use
icon names. Spark Files' own drawings keep the same colours and shapes, so the two look alike.

| Icon names | Drawing |
|---|---|
| `user-home` (`folder-home`) | folder with a house |
| `user-desktop` (`folder-desktop`) | folder with a screen |
| `folder-documents` | folder with a page |
| `folder-download` (`folder-downloads`) | folder with a down arrow |
| `folder-music` | folder with a note |
| `folder-pictures` | folder with a framed hill |
| `folder-videos` (`folder-video`) | folder with a framed play mark |
| `folder-games` | folder with a game pad |
| `drive-harddisk` (`-usb`, `-solidstate`, `-root`) | flat box, vents, light. Every Windows drive at `/var/mnt/<letter>` gets this: SparkOS names no custom icon for them, KDE asks for `drive-harddisk` |
| `drive-removable-media` (`-usb`, `-usb-pendrive`) | USB stick |
| `drive-optical` (`media-optical`) | disc |
| `network-workgroup` (`folder-network`, `folder-remote`) | three linked nodes |
| `network-server` | two rack units |

- Folders keep the batch 1 folder (square tab, indigo body, slip on the top edge) and add a mint mark
  on the body, centred, never touching the edges. The mark is the only part that changes between them.
- Drives and the network icons are not folders: no tab. The slip is on the top strip (drives, server),
  the rim (disc) or the top node (network).
- Marks are mint; secondary parts (arrow base, vents, plug, links) are muted `#b3b0d2`; holes and
  cut-outs are `#141233`. A mark on a folder is never gold or any other accent.
- At 22 and 16 px the marks are redrawn on whole pixels: no strokes thinner than 1 px, the 16 px marks
  are 6 to 7 rows tall, and the slip is 1 px.
- Symbolic versions exist for everything except `folder-games` (Breeze has none either): the folders
  are the folder outline with the mark inside, the others are the mark alone.
- Aliases in brackets are symbolic links, as in batch 1.
- Not drawn: Trash (batch 1), `computer` and `folder-root`, `folder-favorites`, `folder-publicshare`,
  `folder-templates`, `network-wired` and `network-wireless` (batch 4, tray), and the sidebar's own
  action icons (Spark Files draws those itself).
